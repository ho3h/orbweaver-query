"""Exact-prefix accounting and ordinary classifier controls, not speed assertions."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

DIRECTORY = Path(__file__).resolve().parents[1] / "benchmarks/v1"
spec = importlib.util.spec_from_file_location("spider_headroom", DIRECTORY / "spider_headroom.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_tokenization_requests_ids_and_rejects_mapping_keys_before_capture():
    loader = SimpleNamespace(SPIDER_SYSTEM_PROMPT="system", _build_user_prompt=lambda s: "prompt")

    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["return_dict"] is False
            return list(range(5000))

    assert benchmark.tokenize(loader, Tokenizer(), {}) == list(range(904, 5000))
    bad = SimpleNamespace(apply_chat_template=lambda *a, **k: {"input_ids": [1, 2]})
    with pytest.raises(ValueError, match="integer token IDs"):
        benchmark.tokenize(loader, bad, {})


def test_frozen_scenarios_preserve_event_rendering_order(tmp_path):
    scenario = {"events_since_last_tick": [{"type": "review", "left_id": "a",
                                          "signals": {"shared_neighbors": ["b"], "count": 1}}]}
    path = tmp_path / "cases.json"
    benchmark.write(path, scenario, sort_keys=False)
    assert json.dumps(benchmark.read(path)) == json.dumps(scenario)


def test_prefix_work_bound_matches_independent_trie_including_identical_requests():
    sequences = [[1, 2, 3], [1, 2, 4, 5], [1, 2, 3], [2, 1], [1]]
    seen = set()
    fresh = pairs = 0
    for tokens in sorted(sequences):
        for i in range(len(tokens)):
            prefix = tuple(tokens[:i+1])
            if i == len(tokens)-1 or prefix not in seen:
                fresh += 1
                pairs += i+1
            # The last token cannot be used as a cached answer but can supply
            # prefix state for a longer later request in the unlimited bound.
            seen.add(prefix)
    result = benchmark.prefix_bound(sequences)
    assert result["fresh_tokens"] == fresh
    assert result["causal_attention_pairs"] == pairs
    assert result["requested_tokens"] == sum(map(len, sequences))


def test_prefix_lru_never_reuses_nonprefix_context_and_obeys_numeric_budget():
    cache = benchmark.PrefixLRU(32)
    state = [(np.zeros((2,), dtype=np.float32), np.ones((2,), dtype=np.float32))]
    cache.put((1, 2, 3), state)
    cache.put((2, 3, 4), state)
    assert cache.get([9, 1, 2, 3]) == (0, None)
    assert cache.get([1, 2, 3, 7])[0] == 3
    cache.put((4, 5), state)
    assert (2, 3, 4) not in cache.entries
    assert cache.bytes == cache.peak == 32 and cache.evictions == 1
    # Even a complete repeat must execute its final token.
    assert cache.get([1, 2, 3])[0] == 2
    cache.put((8,), [(np.zeros(100), np.zeros(100))])
    assert (8,) not in cache.entries and cache.bytes == 32


def test_mlx_batch_padding_and_mutable_prefix_caches_preserve_classifier_outputs():
    mx = pytest.importorskip("mlx.core")
    nn = pytest.importorskip("mlx.nn")
    qwen3 = pytest.importorskip("mlx_lm.models.qwen3")
    mx.random.seed(7)
    args = qwen3.ModelArgs(model_type="qwen3", hidden_size=16, num_hidden_layers=2,
                          intermediate_size=32, num_attention_heads=2, rms_norm_eps=1e-6,
                          vocab_size=32, num_key_value_heads=1, max_position_embeddings=128,
                          rope_theta=10000, head_dim=8, tie_word_embeddings=True)
    base, head = qwen3.Model(args), nn.Linear(16, 6)
    base.freeze()
    head.eval()

    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            return json.loads(messages[-1]["content"])

    def softmax(values):
        e = np.exp(np.array(values)-max(values))
        return (e/e.sum()).tolist()

    loader = SimpleNamespace(SPIDER_SYSTEM_PROMPT="system", VERB_LABELS=tuple("abcdef"),
                             _build_user_prompt=lambda s: s["graph_snapshot_cypher"],
                             softmax=softmax, _aps_threshold=lambda *_: .9)
    spider = SimpleNamespace(base=base, head=head, tokenizer=Tokenizer(),
                             calibration_scores=[.9], target_coverage=.9)
    tokens = [[1, 2, 3, 4, 5], [1, 2, 3, 7], [9, 8], [1, 2, 3, 4, 5], [1]]
    rows = [{"scenario": {"graph_snapshot_cypher": json.dumps(t)}, "tokens": t} for t in tokens]
    manifest = {"kv_budget_bytes": 2048, "max_batch_tokens": 32}
    reference = benchmark.execute(spider, loader, rows, "scalar", manifest)
    for arm in benchmark.ARMS:
        result = benchmark.execute(spider, loader, rows, arm, manifest)
        for actual, wanted in zip(result["output"], reference["output"]):
            # Use the diagnostic's predeclared numerical contract. Metal's
            # masked batched and causal single-row attention kernels need not
            # agree at float32 machine precision.
            np.testing.assert_allclose(actual["logits"], wanted["logits"], atol=1e-2, rtol=1e-3,
                                       err_msg=arm)
            np.testing.assert_allclose(actual["probabilities"], wanted["probabilities"],
                                       atol=1e-3, rtol=1e-3, err_msg=arm)
            assert actual["top_class"] == wanted["top_class"]
            assert actual["prediction_set"] == wanted["prediction_set"]
        assert result["peak_retained_kv_bytes"] <= manifest["kv_budget_bytes"]
        if arm.startswith("prefix"):
            assert result["work"]["reused_tokens"] > 0
            assert result["work"]["fresh_tokens"]+result["work"]["reused_tokens"] == sum(map(len, tokens))
        elif arm.startswith("batch"):
            assert result["work"]["body_calls"] < len(rows)
