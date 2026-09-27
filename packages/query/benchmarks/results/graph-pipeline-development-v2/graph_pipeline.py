"""Frozen development experiment for prediction-dependent graph expansion."""

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

DATASETS = ("collaboration", "friendship", "communication")
SHAPES = ("one_expansion", "two_expansions")
ARMS = ("automatic", "automatic_unprepared", "eager", "manual_targeted",
        "manual_full_lru", "manual_prepared")
THRESHOLDS = (0.0, 0.2)
THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def checked(run):
    manifest = read(run / "manifest.json")
    for name, digest in manifest["files"].items():
        if sha(run / name) != digest:
            raise ValueError(f"Frozen file changed: {name}")
    return manifest


def freeze(run, inputs):
    import numpy as np
    from plan_archive import verify

    from orbweaver_query import GraphSnapshot

    verify(inputs)
    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[2]
    shutil.copytree(package / "src/orbweaver_query", run / "source/orbweaver_query",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for filename in ("graph_pipeline.py", "plan_reference.py", "GRAPH_PIPELINE_PROTOCOL.md"):
        shutil.copyfile(Path(__file__).with_name(filename), run / filename)
    for name in DATASETS:
        for suffix in ("outer.npz", "path-model.npz"):
            shutil.copyfile(inputs / f"{name}-{suffix}", run / f"{name}-{suffix}")
        graph = GraphSnapshot.load(run / f"{name}-outer.npz")
        rng = np.random.default_rng(8501)
        selected = []
        for head in rng.permutation(np.flatnonzero(graph.degree)):
            direct = {int(n) for n in graph.neighbors(int(head))}
            second = {int(n) for mid in direct for n in graph.neighbors(mid)} - direct - {int(head)}
            if not second:
                continue
            targets = rng.choice(sorted(second), min(2, len(second)), replace=False)
            selected.append((int(head), [int(t) for t in targets]))
            if len(selected) == 8:
                break
        queries = {}
        for shape in SHAPES:
            pairs = [(h, t) for h, targets in selected[:8 if shape == "one_expansion" else 2]
                     for t in targets[:2 if shape == "one_expansion" else 1]]
            rows = [{"head": graph.node_ids[h], "relation": "LINK", "seed": graph.node_ids[t],
                     "ordinal": i} for i, (h, t) in enumerate(pairs)]
            queries[shape] = [*rows, {**rows[0], "ordinal": 1000},
                              {"head": None, "relation": "LINK", "seed": None, "ordinal": -1}]
        write(run / f"{name}-queries.json", queries)
    jobs = [{"dataset": d, "shape": s, "threshold": t, "arm": a, "replicate": r}
            for d in DATASETS for s in SHAPES for t in THRESHOLDS for a in ARMS for r in range(3)]
    random.Random(8502).shuffle(jobs)
    files = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()}
    write(run / "manifest.json", {"format": "orbweaver-graph-pipeline-development-v2",
                                  "files": files, "jobs": jobs, "warmup": 1, "samples": 3,
                                  "input_archive_sha256": sha(inputs / "ARCHIVE.json")})
    return {"workers": len(jobs), "manifest_sha256": sha(run / "manifest.json")}


def make_plan(graph, path, structural, shape, threshold=.2):
    from orbweaver_query import QueryPlan

    plan = QueryPlan(graph).expand(source="seed", target="one", direction="both")
    if shape == "two_expansions":
        plan = plan.expand(source="one", target="two", direction="both")
    plan = plan.predict("root", structural, target="seed").where_score("root", threshold)
    if shape == "two_expansions":
        plan = plan.predict("middle", structural, target="one").where_score("middle", threshold)
    final = "one" if shape == "one_expansion" else "two"
    plan = plan.predict("leaf", path, target=final)
    columns = ["ordinal", "head", "seed", "one"]
    if shape == "two_expansions":
        columns.append("two")
    columns += ["root", *(["middle"] if shape == "two_expansions" else []), "leaf"]
    return plan.project(*columns)


class PackedAdjacency:
    """Independent vector traversal of the existing packed evidence; no second index."""

    def __init__(self, graph):
        self.graph = graph

    def get(self, source, default=()):
        import numpy as np

        if source is None:
            return default
        graph = self.graph
        head = graph.node_index(source)
        start, stop = graph.indptr[head:head + 2]
        nodes = np.repeat(graph.indices[start:stop], np.diff(graph.type_indptr[start:stop + 1]))
        return tuple(graph.node_ids[n] for n in nodes.tolist())


def adjacency(graph):
    return PackedAdjacency(graph)


class PreparedModel:
    """Hand-managed path-prefix reuse, independent of query-plan scheduling."""

    def __init__(self, model):
        self.model = model
        self.model_id, self.relations = model.model_id, model.relations
        self.feature_id, self.candidate_support = model.feature_id, model.candidate_support
        self.score_kind = model.score_kind
        self.reset()

    def reset(self):
        from orbweaver_query.preparation import PreparationScope

        self.scope, self.seen = PreparationScope(16 * 2**20), set()

    def expand_targets(self, graph, head, targets, limits):
        from dataclasses import replace

        key = self.scope.key(self.model, graph, head)
        if key not in self.seen:
            self.seen.add(key)
            self.scope.eligible.add(key)
        features, cost = self.scope.expand(self.model, graph, head, targets, limits)
        return replace(features, type_visits=features.type_visits + cost)

    def score(self, features, relation):
        return self.model.score(features, relation)

    def rejects_pair(self, graph, head, target):
        return self.model.rejects_pair(graph, head, target)


def manual(graph, path, structural, shape, rows, neighbors, columns, pair_cache, threshold=.2):
    from orbweaver_query import Limits, ResourceLimitError, Session, score_bindings

    limits = Limits()
    counters = {"expansions": 0, "model_calls": 0, "edge_visits": 0, "type_visits": 0}

    def score(rows, model, name, target, threshold=None):
        result = score_bindings(Session(graph, model, limits=limits), rows,
                                target=target, cache=pair_cache)
        for profile in result.profiles:
            for key in ("expansions", "model_calls", "type_visits"):
                counters[key] += getattr(profile, key)
        if threshold is not None:
            result = result.where_score(threshold)
        return result.to_records(prediction_column=name)

    def expand(rows, source, target):
        result, visits = [], 0
        for row in rows:
            for value in neighbors.get(row[source], ()):
                visits += 1
                if visits > limits.max_type_visits or visits > limits.max_neighbor_visits:
                    raise ResourceLimitError("Manual traversal exceeds visit budget")
                if len(result) >= limits.max_intermediate_rows:
                    raise ResourceLimitError("Manual traversal exceeds max_intermediate_rows")
                result.append({**row, target: value})
        counters["edge_visits"] += visits
        return result

    rows = score(rows, structural, "root", "seed", threshold)
    rows = expand(rows, "seed", "one")
    if shape == "two_expansions":
        rows = score(rows, structural, "middle", "one", threshold)
        rows = expand(rows, "one", "two")
    rows = score(rows, path, "leaf", "one" if shape == "one_expansion" else "two")
    return [{c: row[c] for c in columns} for row in rows], counters


def worker(run, index):
    sys.path[:0] = [str(run / "source"), str(run)]
    import resource

    import numpy as np
    from plan_reference import CachedModel, SharedFeatureLRU

    from orbweaver_query import BindingCache, ExplicitPathModel, GraphSnapshot, NeighborhoodModel

    manifest = checked(run)
    job = manifest["jobs"][index]
    before = time.perf_counter()
    graph = GraphSnapshot.load(run / f"{job['dataset']}-outer.npz")
    path = ExplicitPathModel.load(run / f"{job['dataset']}-path-model.npz")
    structural = NeighborhoodModel(relations=graph.relations)
    common_setup = time.perf_counter() - before
    rows = read(run / f"{job['dataset']}-queries.json")[job["shape"]]
    before = time.perf_counter()
    plan = make_plan(graph, path, structural, job["shape"], job["threshold"])
    neighbors = adjacency(graph) if job["arm"].startswith("manual") else None
    full = SharedFeatureLRU(16 * 2**20) if job["arm"] == "manual_full_lru" else None
    if full is not None:
        path, structural = CachedModel(path, full), CachedModel(structural, full)
    if job["arm"] == "manual_prepared":
        path = PreparedModel(path)
    setup = time.perf_counter() - before
    samples, identity = [], None
    for sample in range(manifest["warmup"] + manifest["samples"]):
        before = time.perf_counter()
        pair_cache = BindingCache(max_entries=2**20)
        if full is not None:
            full.clear()
        if isinstance(path, PreparedModel):
            path.reset()
        if neighbors is not None:
            output, work = manual(graph, path, structural, job["shape"], rows, neighbors,
                                  plan.projection, pair_cache, job["threshold"])
        else:
            result = plan.run(rows, optimize=job["arm"] != "eager", cache=pair_cache,
                              reuse_preparation=job["arm"] != "automatic_unprepared")
            output, work = result.to_records(), result.report()
        if isinstance(path, PreparedModel):
            work.update(preparation_builds=path.scope.builds, preparation_hits=path.scope.hits,
                        peak_preparation_bytes=path.scope.peak_bytes)
        encoded = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        elapsed = time.perf_counter() - before
        digest = hashlib.sha256(encoded).hexdigest()
        if identity is not None and identity != digest:
            raise ValueError("Repeated execution changed answers")
        identity = digest
        if sample >= manifest["warmup"]:
            samples.append(elapsed)
    return {"job": job, "manifest_sha256": sha(run / "manifest.json"),
            "samples_seconds": samples, "median_seconds": float(np.median(samples)),
            "setup_seconds": setup, "common_setup_seconds": common_setup,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                              (1 if sys.platform == "darwin" else 1024),
            "output": output, "output_sha256": identity, "work": work,
            "full_cache": None if full is None else full.info(),
            "plan": plan.explain(optimize=job["arm"] != "eager",
                                 reuse_preparation=job["arm"] != "automatic_unprepared"),
            "environment": {"python": sys.version, "platform": platform.platform()}}


def execute(run):
    manifest = checked(run)
    folder = run / "workers"
    folder.mkdir(exist_ok=True)
    env = {**os.environ, **dict.fromkeys(THREADS, "1")}
    for index, job in enumerate(manifest["jobs"]):
        if (folder / f"{index:04d}.json").exists() or (folder / f"{index:04d}-error.json").exists():
            continue
        try:
            result = subprocess.run([sys.executable, str(run / "graph_pipeline.py"), "worker",
                                     str(run), "--index", str(index)], env=env, capture_output=True,
                                    text=True, timeout=300, check=False)
            if result.returncode:
                write(folder / f"{index:04d}-error.json",
                      {"job": job, "returncode": result.returncode, "stderr": result.stderr})
            else:
                write(folder / f"{index:04d}.json", json.loads(result.stdout))
        except subprocess.TimeoutExpired:
            write(folder / f"{index:04d}-error.json", {"job": job, "timeout_seconds": 300})
        print(json.dumps({"finished": index + 1, "total": len(manifest["jobs"])}), flush=True)
    return {"workers": len(manifest["jobs"]), "failures": len(list(folder.glob("*-error.json")))}


def summarize(run):
    import numpy as np

    manifest = checked(run)
    workers, failures = [], []
    for i, job in enumerate(manifest["jobs"]):
        success, failure = run / "workers" / f"{i:04d}.json", run / "workers" / f"{i:04d}-error.json"
        if success.exists() == failure.exists():
            raise ValueError("Expected exactly one terminal record per worker")
        value = read(success if success.exists() else failure)
        if value["job"] != job:
            raise ValueError("Worker job differs")
        if success.exists():
            if value["manifest_sha256"] != sha(run / "manifest.json"):
                raise ValueError("Worker provenance differs")
            workers.append(value)
        else:
            failures.append(value)
    outcomes, error, complete_primary = [], 0., True
    condition_records = []
    controls = ("manual_targeted", "manual_full_lru", "manual_prepared")
    for dataset in DATASETS:
        for shape in SHAPES:
            for threshold in THRESHOLDS:
                records = [r for r in workers if r["job"]["dataset"] == dataset and
                           r["job"]["shape"] == shape and r["job"]["threshold"] == threshold]
                condition_records.append(records)
                references = [r for r in records if r["job"]["arm"] in controls]
                if not references:
                    raise ValueError("No independent completed control for a declared condition")
                expected = references[0]["output"]
                for record in records:
                    if len(record["output"]) != len(expected):
                        raise ValueError("Output bag length differs")
                    for actual, wanted in zip(record["output"], expected):
                        if actual.keys() != wanted.keys():
                            raise ValueError("Output columns differ")
                        for key, value in actual.items():
                            if not isinstance(value, dict):
                                if value != wanted[key]:
                                    raise ValueError("Output order/bag differs")
                            else:
                                a, b = dict(value), dict(wanted[key])
                                x, y = a.pop("score"), b.pop("score")
                                if a != b or ((x is None or y is None) and x != y):
                                    raise ValueError("Score status/provenance differs")
                                if x is not None and y is not None:
                                    np.testing.assert_allclose(x, y, rtol=1e-12, atol=1e-12)
                                    error = max(error, abs(x - y))
                arms = {}
                for arm in ARMS:
                    selected = [r for r in records if r["job"]["arm"] == arm]
                    if len(selected) != 3 and arm in ("automatic", *controls):
                        complete_primary = False
                    if not selected:
                        arms[arm] = {"status": "failed", "completed_workers": 0}
                        continue
                    arms[arm] = {"completed_workers": len(selected),
                                 "ms": 1000 * float(np.median([r["median_seconds"] for r in selected])),
                                 "setup_ms": 1000 * float(np.median([r["setup_seconds"] for r in selected])),
                                 "peak_rss_mib": max(r["peak_rss_bytes"] for r in selected) / 2**20,
                                 "work": {k: selected[0]["work"][k] for k in
                                          ("edge_visits", "expansions", "model_calls", "type_visits",
                                           "preparation_builds", "preparation_hits", "peak_preparation_bytes")
                                          if k in selected[0]["work"]}}
                outcomes.append({"dataset": dataset, "shape": shape, "threshold": threshold,
                                 "output_rows": len(expected), "arms": arms})
    ratios = {}
    if complete_primary:
        for regime in ("steady", "one_request"):
            def ratio(records, regime=regime):
                values = {a: np.median([r["median_seconds"] +
                          (r["setup_seconds"] if regime == "one_request" else 0)
                          for r in records if r["job"]["arm"] == a]) for a in ("automatic", *controls)}
                return min(values[a] for a in controls) / values["automatic"]
            point = float(np.exp(np.mean(np.log([ratio(c) for c in condition_records]))))
            rng, samples = np.random.default_rng(8503), []
            for _ in range(10000):
                values = []
                for c in condition_records:
                    resampled = []
                    for a in ("automatic", *controls):
                        group = [r for r in c if r["job"]["arm"] == a]
                        resampled.extend(group[int(i)] for i in rng.integers(0, len(group), len(group)))
                    values.append(ratio(resampled))
                samples.append(float(np.exp(np.mean(np.log(values)))))
            ratios[regime] = {"geometric_mean_speedup": point,
                              "conditional_process_bootstrap_95_interval": np.quantile(samples, [.025, .975]).tolist()}
    result = {"manifest_sha256": sha(run / "manifest.json"), "verified_workers": len(workers),
              "numerical_parity": True, "parity_scope": "completed workers only",
              "failed_workers": len(failures), "failures": failures,
              "max_absolute_error": error, "outcomes": outcomes,
              "complete_primary_comparison": complete_primary,
              "automatic_vs_strongest_manual": ratios, "release_gates_closed": False}
    write(run / "results.json", result)
    return {k: v for k, v in result.items() if k not in ("outcomes", "failures")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "execute", "worker", "summarize"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    root = args.run.resolve()
    if args.command == "freeze":
        report = freeze(root, args.inputs)
    elif args.command == "worker":
        report = worker(root, args.index)
    elif args.command == "execute":
        report = execute(root)
    else:
        report = summarize(root)
    print(json.dumps(report, allow_nan=False))
