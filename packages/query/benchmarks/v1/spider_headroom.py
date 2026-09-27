"""Freeze and diagnose the existing transformer classifier's execution costs."""

import argparse
import hashlib
import importlib.util
import json
import platform
import random
import shutil
import sys
import time
import traceback
from collections import OrderedDict
from pathlib import Path

REVISION = "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b"
ARMS = ("scalar", "batch4", "batch8", "prefix_input", "prefix_sorted")
SHAPES = ("independent_events", "pair_scan", "scoped_review")


def read(path):
    return json.loads(path.read_text())


def write(path, value, *, sort_keys=True):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=sort_keys, allow_nan=False)
        stream.write("\n")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(2**20):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def common_prefix(left, right):
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right))


def prefix_bound(sequences):
    """Unlimited exact prefix reuse; each request still evaluates its final token."""
    prior, fresh, attention, reused = [], 0, 0, 0
    for tokens in sorted(sequences):
        prefix = min(common_prefix(prior, tokens), len(tokens)-1)
        fresh += len(tokens)-prefix
        reused += prefix
        attention += (len(tokens)*(len(tokens)+1)-prefix*(prefix+1))//2
        prior = tokens
    return {"requested_tokens": sum(map(len, sequences)), "fresh_tokens": fresh,
            "reused_tokens": reused, "causal_attention_pairs": attention,
            "uncached_attention_pairs": sum(len(t)*(len(t)+1)//2 for t in sequences)}


def tokenize(loader, tokenizer, scenario):
    messages = [{"role": "system", "content": loader.SPIDER_SYSTEM_PROMPT},
                {"role": "user", "content": loader._build_user_prompt(scenario)}]
    # Transformers 5 defaults to a BatchEncoding. Request the original list
    # explicitly so iterating it cannot silently freeze dictionary key names.
    tokens = tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                            tokenize=True, return_dict=False)
    if not isinstance(tokens, list) or not tokens or any(type(t) is not int for t in tokens):
        raise ValueError("Expected a nonempty flat list of integer token IDs")
    return tokens[-4096:]


def capture(run, model_path, neo4j_home, java):
    from mlx_lm.utils import load_tokenizer
    from neo4j import GraphDatabase

    repo = Path(__file__).resolve().parents[4]
    sys.path[:0] = [str(repo), str(repo / "packages/query/tools")]
    from disposable_neo4j import disposable_database
    from orbweaver.blocking import all_blockers
    from orbweaver.neo4j_sandbox import SandboxHandle, load_cypher
    from orbweaver.spider import subgraph_snapshot

    run.mkdir(parents=True, exist_ok=False)
    source = run / "source"
    source.mkdir()
    for name in ("spider_headroom.py", "SPIDER_HEADROOM_PROTOCOL.md"):
        shutil.copyfile(Path(__file__).with_name(name), run / name)
    shutil.copytree(repo / "orbweaver", source / "orbweaver",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(repo / "packages/query/tools/disposable_neo4j.py", source / "disposable_neo4j.py")
    artifact = repo / "dist/orbweaver-qwen3-4b-spider-v0.1"
    for name in ("loader.py", "head_config.json", "head.safetensors", "calibration.json"):
        shutil.copyfile(artifact / name, source / name)
    input_file = repo / "data/v1.5/train_mixed.jsonl"
    themes, selected = set(), []
    for line in input_file.read_text().splitlines():
        row = json.loads(line)
        theme = row["_meta"]["theme"]
        if theme not in themes:
            selected.append({"id": row["id"], "theme": theme,
                             "graph_snapshot_cypher": row["graph_snapshot_cypher"],
                             "events_since_last_tick": row["events_since_last_tick"]})
            themes.add(theme)
        if len(selected) == 3:
            break
    if len(selected) != 3:
        raise ValueError("Expected three distinct application themes")
    loader = load_module(source / "loader.py", "headroom_loader")
    tokenizer = load_tokenizer(model_path, eos_token_ids=read(model_path / "config.json").get("eos_token_id"))
    cases = {s: [] for s in SHAPES}
    try:
        with (disposable_database(neo4j_home, java) as uri,
              GraphDatabase.driver(uri, auth=None) as driver):
            for row in selected:
                driver.execute_query("MATCH (n) DETACH DELETE n")
                load_cypher(SandboxHandle(driver, "neo4j", uri, "", ""), row["graph_snapshot_cypher"])
                cases["independent_events"].append({"graph": row["id"], "scenario": row})
                candidates = list(all_blockers(driver, limit_per_blocker=3))
                for candidate in candidates:
                    event = {"type": "candidate_pair_review", "left_id": candidate.left_id,
                             "right_id": candidate.right_id, "blocker": candidate.blocker,
                             "signals": candidate.signals}
                    snapshot = subgraph_snapshot(driver, [candidate.left_id, candidate.right_id])
                    if not snapshot:
                        raise ValueError("Selected candidate has empty context")
                    for shape, graph in (("pair_scan", snapshot),
                                         ("scoped_review", row["graph_snapshot_cypher"])):
                        cases[shape].append({"graph": row["id"], "scenario": {
                            "graph_snapshot_cypher": graph, "events_since_last_tick": [event]}})
        for rows in cases.values():
            for row in rows:
                row["tokens"] = tokenize(loader, tokenizer, row["scenario"])
        # Event object order is part of the shipped prompt's JSON rendering.
        write(run / "cases.json", cases, sort_keys=False)
        for rows in read(run / "cases.json").values():
            for row in rows:
                if tokenize(loader, tokenizer, row["scenario"]) != row["tokens"]:
                    raise ValueError("Capture round-trip changed prompt token IDs")
        write(run / "capture.json", {"selected": selected, "input_file": str(input_file.relative_to(repo)),
                                      "input_sha256": sha(input_file),
                                      "scope": "existing synthetic application fixtures; no quality labels used"})
        write(run / "bounds.json", {s: {"rows": len(rows),
            "lengths": [len(r["tokens"]) for r in rows],
            "distinct_graph_snapshots": len({r["scenario"]["graph_snapshot_cypher"] for r in rows}),
            "prefix_work_bound": prefix_bound([r["tokens"] for r in rows])}
            for s, rows in cases.items()})
        files = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*"))
                 if p.is_file() and "__pycache__" not in p.parts}
        base = {p.name: sha(p) for p in sorted(model_path.iterdir()) if p.is_file()}
        write(run / "manifest.json", {"format": "orbweaver-spider-headroom-v1", "files": files,
              "model": "mlx-community/Qwen3-4B-Instruct-2507-4bit", "revision": REVISION,
              "model_files": base, "arms": ARMS, "shapes": SHAPES, "repetitions": 3,
              "seed": 20260927, "kv_budget_bytes": 512*2**20, "max_batch_tokens": 16384})
        return read(run / "bounds.json")
    except Exception:
        write(run / "capture-error.json", {"traceback": traceback.format_exc()})
        raise


def checked(run, model_path=None):
    manifest = read(run / "manifest.json")
    for name, digest in manifest["files"].items():
        if sha(run / name) != digest:
            raise ValueError(f"Frozen file changed: {name}")
    if model_path is not None:
        for name, digest in manifest["model_files"].items():
            if sha(model_path / name) != digest:
                raise ValueError(f"Base model file changed: {name}")
    return manifest


class PrefixLRU:
    """Conventional longest-token-prefix lookup over compact immutable KV arrays."""

    def __init__(self, budget):
        self.budget, self.entries = budget, OrderedDict()
        self.bytes = self.peak = self.evictions = 0

    def get(self, tokens):
        best, matched = None, 0
        for key in self.entries:
            length = common_prefix(key, tokens[:-1])
            if length > matched:
                best, matched = key, length
        if best is None:
            return 0, None
        self.entries.move_to_end(best)
        return matched, self.entries[best][0]

    def put(self, key, states):
        size = sum(k.nbytes+v.nbytes for k, v in states)
        if size > self.budget:
            return
        if key in self.entries:
            _, old = self.entries.pop(key)
            self.bytes -= old
        while self.bytes+size > self.budget:
            _, (_, old) = self.entries.popitem(last=False)
            self.bytes -= old
            self.evictions += 1
        self.entries[key] = states, size
        self.bytes += size
        self.peak = max(self.peak, self.bytes)


def execute(spider, loader, rows, arm, manifest):
    import mlx.core as mx
    import numpy as np
    from mlx_lm.models.cache import KVCache, make_prompt_cache

    before = time.perf_counter()
    ids = [tokenize(loader, spider.tokenizer, row["scenario"]) for row in rows]
    if ids != [r["tokens"] for r in rows]:
        raise ValueError("Runtime tokenization differs from frozen tokens")
    token_seconds = time.perf_counter()-before
    elapsed = {"tokenization": token_seconds, "body": 0., "head_and_transfer": 0.,
               "cache_and_ordering": 0.}
    counts = {"requested_tokens": sum(map(len, ids)), "fresh_tokens": 0,
              "padded_tokens": 0, "body_calls": 0, "reused_tokens": 0}
    output = [None]*len(rows)
    prefix = PrefixLRU(manifest["kv_budget_bytes"])
    began = time.perf_counter()
    order = list(range(len(rows)))
    if arm.startswith("batch"):
        order.sort(key=lambda i: len(ids[i]))
    elif arm == "prefix_sorted":
        order.sort(key=lambda i: ids[i])
    elapsed["cache_and_ordering"] += time.perf_counter()-began
    while order:
        began = time.perf_counter()
        group = [order.pop(0)]
        batch = int(arm.removeprefix("batch")) if arm.startswith("batch") else 1
        while (order and len(group) < batch and
               (len(group)+1)*max(len(ids[order[0]]), len(ids[group[-1]])) <= manifest["max_batch_tokens"]):
            group.append(order.pop(0))
        sequences = [ids[i] for i in group]
        matched, states = prefix.get(sequences[0]) if arm.startswith("prefix") else (0, None)
        if arm.startswith("batch"):
            length = max(map(len, sequences))
            padding = [length-len(t) for t in sequences]
            # Causal attention makes trailing padding invisible to every real
            # token. Gather each sequence's own final hidden state; no KV writes
            # or left-padding position machinery are needed for this control.
            cache = None
            tokens = mx.array([t+[0]*p for p, t in zip(padding, sequences)])
            counts["padded_tokens"] += sum(padding)
        elif arm.startswith("prefix"):
            cache = make_prompt_cache(spider.base)
            if states is not None:
                for layer, (keys, values) in zip(cache, states):
                    if not isinstance(layer, KVCache):
                        raise TypeError("Diagnostic requires the pinned model's ordinary KV cache")
                    layer.state = keys[..., :matched, :], values[..., :matched, :]
            tokens = mx.array([sequences[0][matched:]])
        else:
            tokens, cache = mx.array(sequences), None
        elapsed["cache_and_ordering"] += time.perf_counter()-began
        began = time.perf_counter()
        hidden = spider.base.model(tokens, cache=cache)
        hidden = (hidden[mx.arange(len(group)), mx.array([len(t)-1 for t in sequences])]
                  if arm.startswith("batch") else hidden[:, -1, :]).astype(mx.float32)
        mx.eval(hidden)
        elapsed["body"] += time.perf_counter()-began
        counts["body_calls"] += 1
        counts["fresh_tokens"] += sum(map(len, sequences))-matched
        counts["reused_tokens"] += matched
        began = time.perf_counter()
        # Match the shipped loader's float32 CPU-hidden-state transfer boundary.
        last = np.array(hidden)
        logits = spider.head(mx.array(last))
        mx.eval(logits)
        logits = np.asarray(logits)
        for index, values in zip(group, logits):
            probs = loader.softmax(values.tolist())
            ranked = sorted(zip(loader.VERB_LABELS, probs), key=lambda x: -x[1])
            threshold = loader._aps_threshold(spider.calibration_scores, spider.target_coverage)
            selected, cumulative = [], 0.
            for verb, probability in ranked:
                selected.append(verb)
                cumulative += probability
                if cumulative >= threshold:
                    break
            output[index] = {"logits": values.tolist(), "probabilities": probs,
                             "top_class": ranked[0][0], "prediction_set": selected}
        elapsed["head_and_transfer"] += time.perf_counter()-began
        began = time.perf_counter()
        if arm.startswith("prefix"):
            keep = len(sequences[0])-1
            compact = [(mx.contiguous(c.keys[..., :keep, :]),
                        mx.contiguous(c.values[..., :keep, :])) for c in cache]
            mx.eval(compact)
            prefix.put(tuple(sequences[0][:-1]), compact)
        elapsed["cache_and_ordering"] += time.perf_counter()-began
    json.dumps(output, allow_nan=False)
    return {"seconds": time.perf_counter()-before, "phases_seconds": elapsed,
            "work": counts, "peak_retained_kv_bytes": prefix.peak,
            "kv_evictions": prefix.evictions, "output": output}


def probe(run, model_path):
    import inspect
    from importlib.metadata import version

    import mlx.core as mx
    from mlx.utils import tree_unflatten
    from mlx_lm import load
    from mlx_lm import tokenizer_utils
    from mlx_lm.models import cache, qwen3

    manifest = checked(run, model_path)
    loader = load_module(run / "source/loader.py", "headroom_loader")
    before = time.perf_counter()
    base, tokenizer = load(str(model_path))
    base.freeze()
    config, calibration = read(run / "source/head_config.json"), read(run / "source/calibration.json")
    head = loader.ClassifierHead(config["in_features"], config["out_features"], config["dropout"])
    head.update(tree_unflatten(list(mx.load(str(run / "source/head.safetensors")).items())))
    head.eval()
    mx.eval(head.parameters())
    spider = loader.Spider(base, tokenizer, head, config, calibration["nonconformity_scores"],
                           calibration["target_coverage"])
    write(run / "environment.json", {"model_load_seconds": time.perf_counter()-before,
          "device": mx.device_info(), "platform": platform.platform(), "python": sys.version,
          "versions": {p: version(p) for p in ("mlx", "mlx-lm", "numpy", "transformers", "neo4j")},
          "runtime_source_sha256": {m.__name__: sha(Path(inspect.getfile(m)))
                                    for m in (cache, qwen3, tokenizer_utils)}})
    cases = read(run / "cases.json")
    warmups = []
    for arm in ARMS:
        warmups.append({"arm": arm, **execute(spider, loader, cases["independent_events"][:1], arm, manifest)})
    write(run / "warmup.json", warmups)
    jobs = [{"shape": shape, "arm": arm, "replicate": rep} for shape in SHAPES
            for arm in ARMS for rep in range(manifest["repetitions"])]
    random.Random(manifest["seed"]).shuffle(jobs)
    folder = run / "workers"
    folder.mkdir(exist_ok=False)
    for index, job in enumerate(jobs):
        try:
            mx.clear_cache()
            mx.reset_peak_memory()
            result = execute(spider, loader, cases[job["shape"]], job["arm"], manifest)
            result.update(job=job, mlx_peak_bytes=mx.get_peak_memory(),
                          manifest_sha256=sha(run / "manifest.json"))
            write(folder / f"{index:03d}.json", result)
        except Exception:  # noqa: BLE001 - retain each failed diagnostic, including backend errors
            write(folder / f"{index:03d}-error.json", {"job": job, "traceback": traceback.format_exc()})
        print(json.dumps({"finished": index+1, "total": len(jobs), "job": job}), flush=True)
    return {"jobs": len(jobs), "errors": len(list(folder.glob("*-error.json")))}


def summarize(run):
    import numpy as np

    manifest = checked(run)
    records = [read(p) for p in sorted((run / "workers").glob("*.json"))]
    jobs = [{"shape": shape, "arm": arm, "replicate": rep} for shape in SHAPES
            for arm in ARMS for rep in range(manifest["repetitions"])]
    random.Random(manifest["seed"]).shuffle(jobs)
    if [r["job"] for r in records] != jobs:
        raise ValueError("Incomplete or mismatched diagnostic jobs")
    failures = [r for r in records if "traceback" in r]
    outcomes, differences = {}, []
    for shape in SHAPES:
        group = [r for r in records if r["job"]["shape"] == shape and "output" in r]
        reference = next(r for r in group if r["job"]["arm"] == "scalar")
        arms = {}
        for arm in ARMS:
            selected = [r for r in group if r["job"]["arm"] == arm]
            if not selected:
                arms[arm] = {"completed": 0}
                continue
            for record in selected:
                if record["manifest_sha256"] != sha(run / "manifest.json"):
                    raise ValueError("Wrong provenance")
                if len(record["output"]) != len(reference["output"]):
                    raise ValueError("Wrong row count")
                for i, (actual, wanted) in enumerate(zip(record["output"], reference["output"])):
                    for key, atol in (("probabilities", 1e-3), ("logits", 1e-2)):
                        if not np.allclose(actual[key], wanted[key], atol=atol, rtol=1e-3):
                            differences.append({"job": record["job"], "row": i, "field": key,
                                "max_absolute_error": float(np.max(np.abs(np.array(actual[key])-wanted[key])))})
                    for key in ("top_class", "prediction_set"):
                        if actual[key] != wanted[key]:
                            differences.append({"job": record["job"], "row": i, "field": key,
                                                "actual": actual[key], "expected": wanted[key]})
            arms[arm] = {"completed": len(selected),
                "median_seconds": float(np.median([r["seconds"] for r in selected])),
                "samples_seconds": [r["seconds"] for r in selected],
                "phases_seconds": {k: float(np.median([r["phases_seconds"][k] for r in selected]))
                                    for k in selected[0]["phases_seconds"]},
                "work": selected[0]["work"],
                "peak_retained_kv_bytes": max(r["peak_retained_kv_bytes"] for r in selected),
                "mlx_peak_bytes": max(r["mlx_peak_bytes"] for r in selected)}
        outcomes[shape] = arms
    scoped = next(r for r in records if r["job"] == {"shape": "scoped_review", "arm": "scalar", "replicate": 0})
    existing = {}
    for row, answer in zip(read(run / "cases.json")["scoped_review"], scoped["output"]):
        state = existing.setdefault(row["graph"], {"candidates": 0, "needed": 0, "exists": False})
        state["candidates"] += 1
        if not state["exists"]:
            state["needed"] += 1
            state["exists"] = answer["prediction_set"] in (["add_link"], ["merge_entities"])
    result = {"manifest_sha256": sha(run / "manifest.json"), "outcomes": outcomes,
              "failures": failures, "differences": differences,
              "inference_parity": not failures and not differences,
              "existence_work_bound": existing, "release_gates_closed": False,
              "scope": "single-process local diagnostic on synthetic application fixtures"}
    write(run / "results.json", result)
    return {k: v for k, v in result.items() if k != "outcomes"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "probe", "summarize", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--neo4j-home", type=Path)
    parser.add_argument("--java", type=Path)
    args = parser.parse_args()
    if args.command == "capture":
        result = capture(args.run.resolve(), args.model_path, args.neo4j_home, args.java)
    elif args.command == "probe":
        try:
            result = probe(args.run.resolve(), args.model_path)
        except Exception:
            write(args.run / "probe-error.json", {"traceback": traceback.format_exc()})
            raise
    elif args.command == "summarize":
        result = summarize(args.run.resolve())
    else:
        result = {"verified_files": len(checked(args.run.resolve(), args.model_path)["files"])}
    print(json.dumps(result, allow_nan=False))
