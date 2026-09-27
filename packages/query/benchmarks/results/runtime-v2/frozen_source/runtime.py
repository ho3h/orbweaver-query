"""Frozen real-evidence experiment, executed from copied source in fresh workers."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import resource
import shutil
import subprocess
import sys
import time


ARMS = ("legacy_consecutive", "packed_independent", "packed_consecutive", "packed_grouped")
WORKLOADS = ("single", "distinct256", "shared256", "interleaved256", "hubs16")
THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read(path):
    return json.loads(Path(path).read_text())


def rss():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def freeze(run, fixture):
    import numpy as np

    run, fixture = Path(run).resolve(), Path(fixture).resolve()
    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[1]
    repository = package.parents[1]
    source = run / "source"
    shutil.copytree(package / "src" / "orbweaver_query", source / "orbweaver_query",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    legacy = source / "research" / "graph_native"
    legacy.mkdir(parents=True)
    for name in ("bounded_flow.py", "explicit_path_numpy.py"):
        origin = repository / "research" / "graph_native" / name
        expected = read(fixture / "manifest.json")["source_sha256"][name]
        if sha(origin) != expected:
            raise ValueError(f"Research reference changed: {name}")
        shutil.copyfile(origin, legacy / name)
    shutil.copyfile(__file__, run / "runtime.py")
    shutil.copyfile(Path(__file__).with_name("PROTOCOL.md"), run / "PROTOCOL.md")
    previous = read(fixture / "manifest.json")
    # Every copied input must be registered in a prior frozen job.
    expected_inputs = {}
    for name in previous["jobs"]:
        for item in read(fixture / name)["inputs"].values():
            expected_inputs[Path(item["path"]).name] = item["sha256"]
    for name in ("graph1.npz", "explicit.npz", *(f"queries1-{w}.npz" for w in WORKLOADS
                                              if w != "interleaved256")):
        if sha(fixture / name) != expected_inputs[name]:
            raise ValueError(f"Frozen input changed: {name}")
        shutil.copyfile(fixture / name, run / name)
    with np.load(run / "queries1-shared256.npz", allow_pickle=False) as saved:
        clustered = saved["queries"]
    if clustered.shape != (256, 2) or len(np.unique(clustered[:, 0])) != 32:
        raise ValueError("Unexpected shared-source fixture")
    if len(np.unique(clustered, axis=0)) != 256:
        raise ValueError("Primary workload must not contain duplicate queries")
    np.savez_compressed(run / "queries1-interleaved256.npz",
                        queries=clustered.reshape(32, 8, 2).transpose(1, 0, 2).reshape(256, 2))
    jobs = [{"arm": arm, "workload": workload, "replicate": replicate}
            for arm in ARMS for workload in WORKLOADS for replicate in range(3)]
    random.Random(20260926).shuffle(jobs)
    frozen = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()}
    manifest = {"format": "orbweaver-query-runtime-v1", "jobs": jobs, "files": frozen,
                "fixture_manifest_sha256": sha(fixture / "manifest.json"),
                "tolerance": {"atol": 1e-12, "rtol": 1e-12}, "minimum_primary_speedup": 1.25,
                "maximum_workload_regression": 1.15,
                "warmup_batches": 1, "timed_batches": 5, "seed": 20260926}
    write_json(run / "manifest.json", manifest)
    return {"run": str(run), "jobs": len(jobs), "manifest_sha256": sha(run / "manifest.json")}


def checked(run):
    manifest = read(run / "manifest.json")
    if manifest["format"] != "orbweaver-query-runtime-v1":
        raise ValueError("Unsupported manifest")
    for name, expected in manifest["files"].items():
        if sha(run / name) != expected:
            raise ValueError(f"Frozen source/input changed: {name}")
    return manifest


def worker(run, index):
    started = time.perf_counter()
    os.environ.update({key: "1" for key in THREADS})
    peak = {"baseline": rss()}
    import numpy as np

    sys.path.insert(0, str(run / "source"))
    from orbweaver_query import ExplicitPathModel, GraphSnapshot, LinkQuery, Session

    imported = time.perf_counter()
    peak["imports"] = rss()
    manifest = checked(run)
    job = manifest["jobs"][index]
    with np.load(run / "graph1.npz", allow_pickle=False) as data:
        triples, n, r = data["edges"], int(data["entities"]), int(data["relations"])
    with np.load(run / "explicit.npz", allow_pickle=False) as data:
        coefficient = data["coefficient"].reshape(r, -1)
    with np.load(run / f"queries1-{job['workload']}.npz", allow_pickle=False) as data:
        queries = data["queries"]
    loaded = time.perf_counter()
    node_ids, relations = tuple(f"e{i}" for i in range(n)), tuple(f"r{i}" for i in range(r))
    if job["arm"] == "legacy_consecutive":
        from research.graph_native.bounded_flow import FlowGraph
        from research.graph_native.explicit_path_numpy import ExplicitRuntime

        graph = FlowGraph(triples, n, r, mark_seed=610071)
        model = ExplicitRuntime(graph, coefficient)

        def batch():
            model.clear_cache()
            outputs = [model.score(int(h), int(k)) for h, k in queries]
            return [(tuple(node_ids[int(i)] for i in nodes), values)
                    for nodes, values in outputs], None

        graph_bytes = graph.numeric_bytes
        model_bytes = model.parameter_bytes
    else:
        graph = GraphSnapshot(triples, node_ids=node_ids, relations=relations)
        model = ExplicitPathModel(coefficient, relations=relations)
        session = Session(graph, model)
        requests = [LinkQuery(node_ids[int(h)], relations[int(k)]) for h, k in queries]

        def batch():
            result = session.run(requests, strategy=job["arm"].removeprefix("packed_"))
            return [(row.candidate_ids, row.scores) for row in result.rows], result.report()

        graph_bytes, model_bytes = graph.numeric_bytes, model.coefficient.nbytes
    del triples, coefficient
    ready = time.perf_counter()
    peak["prepared"] = rss()

    def serialize(outputs):
        # Identical wire representation and work across implementations.
        return json.dumps([{"candidate_ids": list(nodes),
                            "scores": values.tolist()} for nodes, values in outputs],
                          allow_nan=False, separators=(",", ":")).encode()

    outputs, profile = batch()
    payload = serialize(outputs)
    first_done = time.perf_counter()
    reference = [(nodes, scores.copy()) for nodes, scores in outputs]
    offsets = np.r_[0, np.cumsum([len(n) for n, _ in outputs])]
    artifact = run / f"predictions-{index:03d}.npz"
    np.savez_compressed(artifact, offsets=offsets,
                        candidates=np.array([int(node[1:]) for nodes, _ in outputs
                                             for node in nodes], dtype=np.int64),
                        scores=np.concatenate([s for _, s in outputs]))
    timing = []
    for repeat in range(manifest["warmup_batches"] + manifest["timed_batches"]):
        start = time.perf_counter()
        outputs, profile = batch()
        infer_done = time.perf_counter()
        repeated_payload = serialize(outputs)
        end = time.perf_counter()
        for (a, x), (b, y) in zip(outputs, reference):
            np.testing.assert_array_equal(a, b)
            np.testing.assert_array_equal(x, y)
        if repeated_payload != payload:
            raise ValueError("Serialized output changed across repetitions")
        if repeat >= manifest["warmup_batches"]:
            timing.append({"execute_seconds": infer_done - start,
                           "serialize_seconds": end - infer_done, "total_seconds": end - start})
    peak["final"] = rss()
    return {**job, "queries": len(queries), "timings": timing, "peak_rss_bytes": peak,
            "stages_seconds": {"imports": imported - started, "load_verify": loaded - imported,
                               "prepare": ready - loaded, "first_batch": first_done - ready,
                               "worker_to_first": first_done - started},
            "graph_numeric_bytes": graph_bytes, "parameter_bytes": model_bytes,
            "profile": profile, "predictions_sha256": sha(artifact),
            "wire_sha256": hashlib.sha256(payload).hexdigest(), "wire_bytes": len(payload),
            "candidate_scores": int(offsets[-1]),
            "environment": {"python": platform.python_version(), "numpy": np.__version__,
                            "platform": platform.platform(), "threads": {k: os.environ[k] for k in THREADS}}}


def summarize(rows):
    import statistics

    summary = []
    for workload in WORKLOADS:
        for arm in ARMS:
            selected = [row for row in rows if row["arm"] == arm and row["workload"] == workload]
            summary.append({"arm": arm, "workload": workload,
                "median_batch_seconds": statistics.median(
                    statistics.median(t["total_seconds"] for t in row["timings"]) for row in selected),
                "median_execute_seconds": statistics.median(
                    statistics.median(t["execute_seconds"] for t in row["timings"]) for row in selected),
                "median_prepare_seconds": statistics.median(row["stages_seconds"]["prepare"] for row in selected),
                "peak_rss_range": [min(row["peak_rss_bytes"]["final"] for row in selected),
                                   max(row["peak_rss_bytes"]["final"] for row in selected)]})
    return summary


def execute(run):
    manifest = checked(run)
    if (run / "results.json").exists() or list(run.glob("result-*.json")):
        raise FileExistsError("Use a new frozen run; existing timing records are immutable")
    rows = []
    for index in range(len(manifest["jobs"])):
        proc = subprocess.run([sys.executable, str(run / "runtime.py"), "worker", "--run", str(run),
                               "--index", str(index)], text=True, capture_output=True)
        if proc.returncode:
            write_json(run / f"failure-{index:03d}.json", {"stdout": proc.stdout, "stderr": proc.stderr})
            raise RuntimeError(f"Worker {index} failed: {proc.stderr}")
        row = json.loads(proc.stdout)
        write_json(run / f"result-{index:03d}.json", row)
        rows.append(row)
        print(json.dumps({"completed": index + 1, "jobs": len(manifest["jobs"]),
                          "arm": row["arm"], "workload": row["workload"]}), flush=True)
    report = {"manifest_sha256": sha(run / "manifest.json"), "rows": rows,
              "summary": summarize(rows)}
    write_json(run / "results.json", report)
    return {"completed": len(rows), "results": str(run / "results.json")}


def verify(run):
    import numpy as np

    manifest, report = checked(run), read(run / "results.json")
    if report["manifest_sha256"] != sha(run / "manifest.json"):
        raise ValueError("Manifest changed")
    rows = [read(run / f"result-{i:03d}.json") for i in range(len(manifest["jobs"]))]
    if rows != report["rows"] or summarize(rows) != report["summary"]:
        raise ValueError("Raw records/summary mismatch")
    controls = {}
    for index, row in enumerate(rows):
        if row["arm"] == "legacy_consecutive":
            controls.setdefault(row["workload"], index)
    max_error = 0.0
    for index, row in enumerate(rows):
        artifact = run / f"predictions-{index:03d}.npz"
        if sha(artifact) != row["predictions_sha256"]:
            raise ValueError("Prediction artifact changed")
        with np.load(artifact, allow_pickle=False) as saved, np.load(
                run / f"predictions-{controls[row['workload']]:03d}.npz", allow_pickle=False) as reference:
            np.testing.assert_array_equal(saved["offsets"], reference["offsets"])
            np.testing.assert_array_equal(saved["candidates"], reference["candidates"])
            np.testing.assert_allclose(saved["scores"], reference["scores"], **manifest["tolerance"])
            if saved["scores"].size:
                max_error = max(max_error, float(np.max(np.abs(saved["scores"] - reference["scores"]))))
            for lo, hi in zip(saved["offsets"][:-1], saved["offsets"][1:]):
                ids = np.array([f"e{i}" for i in saved["candidates"][lo:hi]])
                actual_order = np.lexsort((ids, -saved["scores"][lo:hi]))[:16]
                expected_order = np.lexsort((ids, -reference["scores"][lo:hi]))[:16]
                np.testing.assert_array_equal(actual_order, expected_order)
    primary = {row["arm"]: row["median_batch_seconds"] for row in report["summary"]
               if row["workload"] == "interleaved256"}
    ratios = {arm: primary[arm] / primary["packed_grouped"] for arm in
              ("legacy_consecutive", "packed_consecutive")}
    costs = {(row["workload"], row["arm"]): row["median_batch_seconds"]
             for row in report["summary"]}
    regressions = {workload: costs[workload, "packed_grouped"] /
                   costs[workload, "legacy_consecutive"] for workload in WORKLOADS}
    result = {"verified_workers": len(rows), "max_absolute_score_error": max_error,
              "top16_order_exact": True, "primary_speedups": ratios,
              "primary_gate_passed": all(x >= manifest["minimum_primary_speedup"] for x in ratios.values()),
              "workload_cost_ratios_vs_legacy": regressions,
              "regression_gate_passed": all(x <= manifest["maximum_workload_regression"]
                                            for x in regressions.values()),
              "scope": "fixed-model execution only; database and quality release gates remain open",
              "results_sha256": sha(run / "results.json")}
    write_json(run / "verification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "execute", "worker", "verify"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    run = args.run.resolve()
    if args.action == "freeze":
        value = freeze(run, args.fixture)
    elif args.action == "worker":
        value = worker(run, args.index)
    else:
        value = {"execute": execute, "verify": verify}[args.action](run)
    print(json.dumps(value, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
