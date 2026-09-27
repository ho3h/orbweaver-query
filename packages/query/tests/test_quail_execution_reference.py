"""Validate the actual request baseline without simulating inference performance."""

# ruff: noqa: E402
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

pytest.importorskip("quail")
from quail.physical import RequestExecution
from quail.specs import QWEN3_4B_FP8

path = Path(__file__).parents[1]/"benchmarks/v1/quail_execution_reference.py"
spec = importlib.util.spec_from_file_location("quail_execution_reference", path)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def encode(text):
    if text.strip().upper() == "TRUE":
        return [1]
    if text.strip().upper() == "FALSE":
        return [2]
    return [byte+3 for byte in text.encode()]


@pytest.mark.parametrize("long_side", ["head", "target"])
def test_actual_request_runtime_receives_only_candidate_pairs_and_identical_tokens(long_side):
    rows = [dict(head=head, target=target, head_text=head*(200 if long_side == "head" else 5),
                 target_text=target*(200 if long_side == "target" else 5), ordinal=i)
            for i, (head, target) in enumerate([
                ("c2", "d3"), ("c0", "d2"), ("c1", "d1"), ("c2", "d3"), ("c1", "d0")])]
    with reference.session(encode) as session:
        bound = reference.QuailPairs(rows).bind(session, reference.PREDICATE, kind="barrier")
        audit = reference.prompt_audit(bound)
        lowered = reference.reference_plan(bound)
        request, = lowered.graph.nodes_by_type(RequestExecution.type_name)
        assert request.joins[0].anchor == audit["anchor"]
        assert any(port.source.port == "pairs:0" for port in request.inputs)
        checked = reference.recording_preflight(bound)
        assert checked["pairs"] == 4  # No manufactured 3x4 cross product.
        assert checked["prompt_multiset_equal"] and checked["decisions_equal"]
        assert checked["prefix_cache_resets"] == 1
        assert checked["requested_tokens"] == audit["requested_tokens"]


def test_tuned_baseline_pins_revision_without_disabling_prefix_cache():
    options = reference.PinnedTokenVLLMEngine().llm_kwargs(QWEN3_4B_FP8)
    assert options["revision"] == options["tokenizer_revision"] == QWEN3_4B_FP8.revision
    assert options["enable_prefix_caching"] is True
    assert options["max_num_batched_tokens"] == 25305
    assert options["max_num_seqs"] == 4096
    assert options["dtype"] == "bfloat16"


def test_binary_quality_counts_all_false_positives_and_negatives():
    truth = {"a": True, "b": True, "c": False, "d": False, "e": False}
    actual = {"a": True, "b": False, "c": True, "d": False, "e": False}
    assert reference.binary_metrics(truth, actual) == dict(
        tp=1, tn=2, fp=1, fn=1, precision=.5, recall=.5, support_f1=.5,
        macro_f1=(.5+2/3)/2, accuracy=.6)
    with pytest.raises(ValueError, match="complete"):
        reference.binary_metrics(truth, {"a": True})
    with pytest.raises(ValueError, match="unique"):
        reference.decisions_by_pair([dict(head="a", target="b", answer=True)]*2)


def test_cpu_worker_records_failure_before_model_download(tmp_path, monkeypatch):
    reference.write(tmp_path/"manifest.json", {})
    monkeypatch.setattr(reference, "verify", lambda _: {})
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False)))
    with pytest.raises(RuntimeError, match="H100"):
        reference.worker(tmp_path, "quail", tmp_path/"worker", 3)
    assert "H100" in reference.read(tmp_path/"worker/failure.json")["traceback"]
    assert not (tmp_path/"worker/complete.json").exists()
    assert not list((tmp_path/"worker").glob("trial-*.json"))


def test_summary_requires_all_workers_and_exposes_answer_disagreement(tmp_path, monkeypatch):
    reference.write(tmp_path/"manifest.json", {})
    monkeypatch.setattr(reference, "verify", lambda _: {})
    truth = [dict(head="a", target="b", answer=True), dict(head="c", target="d", answer=False)]
    reference.write(tmp_path/"truth.json", truth)
    with pytest.raises(ValueError, match="Missing"):
        reference.summarize(tmp_path)
    for arm in ("quail", "vllm"):
        for repetition in range(3):
            folder = tmp_path/"workers"/f"{arm}-{repetition}"
            folder.mkdir(parents=True)
            reference.write(folder/"started.json", dict(arm=arm, repeats=3,
                manifest_sha256=reference.sha(tmp_path/"manifest.json")))
            reference.write(folder/"complete.json", dict(arm=arm, measured_trials=3, cold_boot_trials=1))
            reference.write(folder/"environment.json", dict(model_files_verified=True))
            for trial in range(4):
                decisions = truth if arm == "quail" else [{**row, "answer": True} for row in truth]
                reference.write(folder/f"trial-{trial:02d}.json", dict(trial=trial, cold_boot=trial == 0,
                    elapsed_s=1.0 if arm == "quail" else 2.0, decisions=decisions, output_sha256="fixture"))
    result = reference.summarize(tmp_path)
    assert result["descriptive_vllm_over_quail_ratio"] == 2.0
    assert result["decision_disagreements"] == [["c", "d"]]
    assert result["exact_answer_comparison_valid"] is False
    assert result["acceptance_gate_closed"] is False
    reference.write(tmp_path/"workers/vllm-2/failure.json", {"traceback": "fixture failure"})
    with pytest.raises(ValueError, match="failed"):
        reference.summarize(tmp_path)
