"""Frozen standalone training/evaluation: python -m orbweaver_query.reproduce."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

from .datasets import (
    WN18RR_REVISION,
    WN18RR_TRAIN_SHA256,
    fetch_wn18rr_train,
    load_triples,
    positives_by_query,
    sha256,
    split_pairs,
)
from .graph import GraphSnapshot
from .model import ExplicitPathModel, Limits
from .training import (
    fit_controls,
    local_view,
    marginal_projection,
    prepare_examples,
    rank_target,
    sparse_features,
)

SEEDS = (71, 83, 97)
METHODS = ("base", "marginal", "pattern", "permuted", "uniform")
BUDGETS = (16, 64, 256)
PROTOCOL = "MODEL_REPRODUCTION_PROTOCOL.md"


def config():
    return {"seeds": list(SEEDS), "methods": list(METHODS), "budgets": list(BUDGETS),
            "negative_samples": 16, "fit_sampling_offset": 710000,
            "fit_permutation_offset": 720000, "dev_permutation_offset": 730000,
            "C": 10, "solver": "liblinear", "max_iter": 2000, "tol": 1e-6,
            "fit_intercept": False, "random_state": 0, "native_threads": 1,
            "limits": vars(Limits()), "distributable_seed": 71,
            "source_revision": WN18RR_REVISION}


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def hash_arrays(*arrays):
    digest = hashlib.sha256()
    for a in arrays:
        a = np.ascontiguousarray(a)
        digest.update(str(a.dtype).encode() + str(a.shape).encode() + a.tobytes())
    return digest.hexdigest()


def sparse_identity(x):
    x = x.copy()
    x.sort_indices()
    return {"shape": list(x.shape), "nnz": int(x.nnz),
            "sha256": hash_arrays(x.data, x.indices.astype("<i8"), x.indptr.astype("<i8")),
            "numeric_bytes": x.data.nbytes + x.indices.nbytes + x.indptr.nbytes}


def sources():
    root = Path(__file__).parent
    return sorted(root.glob("*.py")) + [root / PROTOCOL]


def freeze(run, train):
    run = Path(run).resolve()
    if run.exists() and any(run.iterdir()):
        raise ValueError("Freeze requires a new or empty run directory")
    train = Path(train).resolve()
    if sha256(train) != WN18RR_TRAIN_SHA256:
        raise ValueError("Pinned training source checksum mismatch")
    (run / "source").mkdir(parents=True)
    identity = {}
    for source in sources():
        target = run / "source" / source.name
        target.write_bytes(source.read_bytes())
        identity[source.name] = sha256(target)
    manifest = {"schema": "orbweaver-query-model-reproduction-v1", "config": config(),
                "train_path": str(train), "train_sha256": sha256(train),
                "source_sha256": identity}
    write_json(run / "manifest.json", manifest)
    return manifest


def checked(run):
    run = Path(run)
    m = json.loads((run / "manifest.json").read_text())
    if (m["schema"] != "orbweaver-query-model-reproduction-v1" or m["config"] != config()
            or m["train_sha256"] != WN18RR_TRAIN_SHA256
            or sha256(m["train_path"]) != WN18RR_TRAIN_SHA256
            or set(m["source_sha256"]) != {p.name for p in sources()}):
        raise ValueError("Manifest/data/config identity mismatch")
    for source in sources():
        digest = m["source_sha256"][source.name]
        if sha256(source) != digest or sha256(run / "source" / source.name) != digest:
            raise ValueError(f"Source changed after freeze: {source.name}")
    return m


def evaluate(graph, dev, seed, model, controls, known):
    """Evaluate full candidate pools; no development label is passed to expansion."""
    n, r, width = len(dev), len(graph.relations), model.coefficient.shape[1]
    outcomes = {"queries": dev, "raw_rank": np.full((len(METHODS), n), np.inf),
                "filtered_rank": np.full((len(METHODS), n), np.inf),
                "recall": np.zeros((len(METHODS), n, len(BUDGETS))),
                "candidate_count": np.zeros(n, np.int64)}
    grouped = {}
    for row, (head, relation, _) in enumerate(dev):
        grouped.setdefault(int(head), {}).setdefault(int(relation), []).append(row)
    digests = {name: hashlib.sha256() for name in METHODS}
    projection = marginal_projection(2*r)
    largest_error, candidate_rows, visits, peak_states = 0.0, 0, 0, 0
    for head, relation_rows in sorted(grouped.items()):
        features = model.expand(graph, head, Limits())
        candidates, x = features.candidates, sparse_features(features, width)
        visits += features.type_visits
        peak_states = max(peak_states, features.peak_states)
        for relation, rows in sorted(relation_rows.items()):
            permutation = np.random.default_rng(730000 + seed + head*r + relation).permutation(len(candidates))
            # Log is monotonic in walk mass and preserves the extractor's exact ties.
            scores = {"uniform": features.base[:, 1]}
            for name in METHODS[:-1]:
                view = local_view(x, 2*r, name, permutation=permutation, projection=projection)
                scores[name] = np.asarray(view @ controls[name][relation])
            portable = model.score(features, relation)
            error = float(np.max(np.abs(portable - scores["pattern"]), initial=0.0))
            largest_error = max(error, largest_error)
            if not np.allclose(portable, scores["pattern"], atol=1e-12, rtol=1e-12):
                raise ValueError("Exported scorer differs from fitted sparse predictor")
            # The public scorer is the evaluated implementation, including tie behavior.
            scores["pattern"] = portable
            candidate_rows += len(candidates)
            for j, name in enumerate(METHODS):
                digests[name].update(hash_arrays(np.array([head, relation]), candidates, scores[name]).encode())
                for row in rows:
                    raw, filtered, recall = rank_target(candidates, scores[name], int(dev[row, 2]),
                                                        known.get((head, relation), set()), BUDGETS)
                    outcomes["raw_rank"][j, row] = raw
                    outcomes["filtered_rank"][j, row] = filtered
                    outcomes["recall"][j, row] = recall
            outcomes["candidate_count"][rows] = len(candidates)

    def metrics(j, mask):
        return {"queries": int(np.count_nonzero(mask)),
                "coverage": float(np.mean(np.isfinite(outcomes["raw_rank"][j, mask]))),
                "raw_mrr": float(np.mean(1 / outcomes["raw_rank"][j, mask])),
                "filtered_mrr": float(np.mean(1 / outcomes["filtered_rank"][j, mask])),
                "recall_at": {str(b): float(np.mean(outcomes["recall"][j, mask, k]))
                              for k, b in enumerate(BUDGETS)}}

    report = {"models": {}, "candidate_rows_per_model": candidate_rows,
              "unique_heads": len(grouped),
              "unique_head_relation_queries": sum(map(len, grouped.values())),
              "export_max_absolute_error": largest_error,
              "type_visits": visits, "peak_expansion_states": peak_states}
    for j, name in enumerate(METHODS):
        report["models"][name] = {
            **metrics(j, np.ones(n, bool)), "candidate_score_sha256": digests[name].hexdigest(),
            "relations": {graph.relations[int(relation)]: metrics(j, dev[:, 1] == relation)
                          for relation in np.unique(dev[:, 1])}}
    return outcomes, report


def gate(evaluations):
    comparisons = []
    for row in evaluations:
        models = row["metrics"]["models"]
        for control in ("base", "marginal", "permuted", "uniform"):
            for budget in ("16", "64"):
                delta = models["pattern"]["recall_at"][budget] - models[control]["recall_at"][budget]
                comparisons.append({"seed": row["seed"], "control": control, "budget": budget,
                                    "difference": delta, "passed": delta > 0})
    return {"passed": [r["seed"] for r in evaluations] == list(SEEDS)
            and all(c["passed"] for c in comparisons), "comparisons": comparisons,
            "scope": "Reproduction on reused transductive development splits of one dataset"}


def peak_rss():
    try:
        import resource
    except ImportError:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value*1024)


def execute(run):
    from scipy import sparse
    from threadpoolctl import threadpool_limits

    run = Path(run)
    m = checked(run)
    receipt = {"manifest_sha256": sha256(run / "manifest.json")}
    write_json(run / "started.json", receipt)
    triples, nodes, relations = load_triples(m["train_path"], expected_sha256=m["train_sha256"])
    report = {**receipt, "nodes": len(nodes), "relations": relations, "triples": len(triples),
              "fits": [], "evaluations": [], "artifacts": {}, "environment": {
                  "python": sys.version, "platform": platform.platform(),
                  "dependencies": {name: importlib.metadata.version(name)
                                   for name in ("numpy", "scipy", "scikit-learn", "threadpoolctl")}}}

    def record(name):
        report["artifacts"][name] = sha256(run / name)

    with threadpool_limits(limits=1):
        # Complete every fit before running any development scoring.
        for seed in SEEDS:
            start = time.perf_counter()
            context, fit, dev = split_pairs(triples, seed)
            graph = GraphSnapshot(context, node_ids=nodes, relations=relations)
            examples, x, audit = prepare_examples(graph, fit,
                positives_by_query(np.concatenate((context, fit))), seed=seed+710000)
            prepared = time.perf_counter()
            model, controls, fitting = fit_controls(x, examples, relations, seed=seed+720000)
            fitted = time.perf_counter()
            graph.save(run / f"{seed}-graph.npz")
            model.save(run / f"{seed}-model.npz")
            np.savez_compressed(run / f"{seed}-controls.npz", **controls)
            np.savez_compressed(run / f"{seed}-examples.npz", **examples)
            sparse.save_npz(run / f"{seed}-features.npz", x)
            for suffix in ("graph", "model", "controls", "examples", "features"):
                record(f"{seed}-{suffix}.npz")
            report["fits"].append({"seed": seed, "context_triples": len(context),
                "fit_triples": len(fit), "dev_triples": len(dev), "sampling": audit,
                "features": sparse_identity(x), "fitting": fitting,
                "graph_id": graph.snapshot_id, "model_id": model.model_id,
                "prepare_seconds": prepared-start, "fit_seconds": fitted-prepared})
            print(f"seed {seed}: fitted all four controls on {len(examples['labels'])} rows", flush=True)
        write_json(run / "fitted.json", report)
        known = positives_by_query(triples)
        for seed in SEEDS:
            graph = GraphSnapshot.load(run / f"{seed}-graph.npz")
            model = ExplicitPathModel.load(run / f"{seed}-model.npz")
            with np.load(run / f"{seed}-controls.npz", allow_pickle=False) as data:
                controls = dict(data)
            dev = split_pairs(triples, seed)[2]
            start = time.perf_counter()
            outcomes, metrics = evaluate(graph, dev, seed, model, controls, known)
            np.savez_compressed(run / f"{seed}-outcomes.npz", **outcomes)
            record(f"{seed}-outcomes.npz")
            report["evaluations"].append({"seed": seed, "metrics": metrics,
                                          "seconds": time.perf_counter()-start})
            print(f"seed {seed}: evaluated all {len(dev)} development triples", flush=True)
    report["gate"] = gate(report["evaluations"])
    report["peak_process_rss_bytes"] = peak_rss()
    write_json(run / "results.json", report)
    return report["gate"]


def verify(run):
    from scipy import sparse
    from threadpoolctl import threadpool_limits

    run = Path(run)
    m = checked(run)
    report = json.loads((run / "results.json").read_text())
    if report["manifest_sha256"] != sha256(run / "manifest.json"):
        raise ValueError("Results/manifest identity mismatch")
    expected = {f"{seed}-{suffix}.npz" for seed in SEEDS
                for suffix in ("graph", "model", "controls", "examples", "features", "outcomes")}
    if set(report["artifacts"]) != expected:
        raise ValueError("Artifact inventory mismatch")
    for name, digest in report["artifacts"].items():
        if sha256(run / name) != digest:
            raise ValueError(f"Changed artifact: {name}")
    triples, nodes, relations = load_triples(m["train_path"], expected_sha256=m["train_sha256"])
    if (report["nodes"] != len(nodes) or report["relations"] != relations
            or report["triples"] != len(triples)
            or [row["seed"] for row in report["fits"]] != list(SEEDS)):
        raise ValueError("Data/split report mismatch")
    evaluations = []
    with threadpool_limits(limits=1):
        for seed, fit_report, evaluation in zip(SEEDS, report["fits"], report["evaluations"], strict=True):
            context, fit, dev = split_pairs(triples, seed)
            graph = GraphSnapshot(context, node_ids=nodes, relations=relations)
            saved = GraphSnapshot.load(run / f"{seed}-graph.npz")
            if graph.snapshot_id != saved.snapshot_id or graph.snapshot_id != fit_report["graph_id"]:
                raise ValueError("Rebuilt evidence graph mismatch")
            model = ExplicitPathModel.load(run / f"{seed}-model.npz")
            if model.model_id != fit_report["model_id"]:
                raise ValueError("Model report mismatch")
            examples, x, audit = prepare_examples(graph, fit,
                positives_by_query(np.concatenate((context, fit))), seed=seed+710000)
            if audit != fit_report["sampling"] or sparse_identity(x) != fit_report["features"]:
                raise ValueError("Rebuilt sampling/features mismatch")
            if sparse_identity(sparse.load_npz(run / f"{seed}-features.npz")) != sparse_identity(x):
                raise ValueError("Saved feature mismatch")
            with np.load(run / f"{seed}-examples.npz", allow_pickle=False) as data:
                for key in examples:
                    np.testing.assert_array_equal(examples[key], data[key])
            with np.load(run / f"{seed}-controls.npz", allow_pickle=False) as data:
                controls = dict(data)
            np.testing.assert_array_equal(model.coefficient, controls["pattern"])
            outcomes, metrics = evaluate(graph, dev, seed, model, controls, positives_by_query(triples))
            with np.load(run / f"{seed}-outcomes.npz", allow_pickle=False) as data:
                for key in outcomes:
                    np.testing.assert_array_equal(outcomes[key], data[key])
            if metrics != evaluation["metrics"] or evaluation["seed"] != seed:
                raise ValueError("Replayed evaluation aggregates/digests differ")
            evaluations.append({"seed": seed, "metrics": metrics})
            print(f"seed {seed}: rebuilt data/features and replayed every prediction", flush=True)
    if gate(evaluations) != report["gate"]:
        raise ValueError("Replayed gate differs")
    result = {"verified": True, "manifest_sha256": sha256(run / "manifest.json"),
              "results_sha256": sha256(run / "results.json"), "gate_passed": report["gate"]["passed"],
              "checks": "Rebuilt evidence, sampling/features, model parity, all outcomes/digests/metrics/gates"}
    write_json(run / "verification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "execute", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--train", type=Path, help="Existing checksum-pinned train.txt (freeze only)")
    parser.add_argument("--data-dir", type=Path, default=Path(".orbweaver-data/wn18rr"))
    args = parser.parse_args()
    if args.action == "freeze":
        train = args.train if args.train else fetch_wn18rr_train(args.data_dir)
        result = freeze(args.run, train)
    elif args.action == "execute":
        result = execute(args.run)
    else:
        result = verify(args.run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
