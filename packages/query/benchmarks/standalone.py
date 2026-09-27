"""Portable runtime benchmark using verified public graph/model reproductions."""

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

SEEDS = (71, 83, 97)
ARMS = ("independent", "consecutive", "grouped")
WORKLOADS = ("single", "distinct256", "clustered256", "interleaved256",
             "duplicates256", "hubs16", "interleaved1024")
THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")
PROTOCOL = "STANDALONE_RUNTIME_PROTOCOL.md"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def read(path):
    return json.loads(Path(path).read_text())


def rss():
    try:
        import resource
    except ImportError:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value*1024)


def freeze(run, model_run):
    import numpy as np

    from orbweaver_query import ExplicitPathModel, GraphSnapshot

    run, model_run = Path(run).resolve(), Path(model_run).resolve()
    report, receipt = read(model_run / "results.json"), read(model_run / "verification.json")
    if (receipt["results_sha256"] != sha(model_run / "results.json")
            or not receipt["verified"] or not receipt["gate_passed"]
            or report["manifest_sha256"] != sha(model_run / "manifest.json")
            or receipt["manifest_sha256"] != report["manifest_sha256"]):
        raise ValueError("Parent reproduction is not verified")
    if [r["seed"] for r in report["fits"]] != list(SEEDS):
        raise ValueError("Expected all three preselected graph/model exports")
    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[1]
    shutil.copytree(package / "src" / "orbweaver_query", run / "source" / "orbweaver_query",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(__file__, run / "standalone.py")
    shutil.copyfile(Path(__file__).with_name(PROTOCOL), run / PROTOCOL)
    for seed, fitted in zip(SEEDS, report["fits"], strict=True):
        for suffix in ("graph", "model"):
            name = f"{seed}-{suffix}.npz"
            if sha(model_run / name) != report["artifacts"][name]:
                raise ValueError(f"Parent artifact changed: {name}")
            shutil.copyfile(model_run / name, run / name)
        graph = GraphSnapshot.load(run / f"{seed}-graph.npz")
        model = ExplicitPathModel.load(run / f"{seed}-model.npz")
        if graph.snapshot_id != fitted["graph_id"] or model.model_id != fitted["model_id"]:
            raise ValueError("Parent graph/model identity differs")
        rng = np.random.default_rng(20260926 + seed)
        heads = rng.choice(np.flatnonzero(graph.degree), 256, replace=False)
        relations = np.arange(8)
        clustered = np.array([(h, r) for h in heads[:32] for r in relations], np.int64)
        workloads = {"single": np.array([[heads[0], 0]]),
            "distinct256": np.column_stack((heads, np.arange(256) % len(graph.relations))),
            "clustered256": clustered,
            "interleaved256": clustered.reshape(32, 8, 2).transpose(1, 0, 2).reshape(256, 2),
            "duplicates256": np.tile([[heads[0], 0]], (256, 1)),
            "hubs16": np.column_stack((np.lexsort((np.arange(len(graph.degree)), -graph.degree))[:16],
                                        np.arange(16) % len(graph.relations))),
            "interleaved1024": np.array([(h, r) for r in relations for h in heads[:128]])}
        np.savez_compressed(run / f"{seed}-queries.npz", **workloads)
    jobs = [{"seed": seed, "strategy": arm, "workload": workload, "replicate": replicate}
            for seed in SEEDS for arm in ARMS for workload in WORKLOADS for replicate in range(3)]
    random.Random(20260926).shuffle(jobs)
    files = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()}
    manifest = {"format": "orbweaver-query-standalone-runtime-v1", "files": files, "jobs": jobs,
        "parent_manifest_sha256": report["manifest_sha256"], "parent_results_sha256": receipt["results_sha256"],
        "warmup_batches": 1, "timed_batches": 5, "primary_min_speedup": 1.25,
        "maximum_regression": 1.15}
    write(run / "manifest.json", manifest)
    return {"jobs": len(jobs), "manifest_sha256": sha(run / "manifest.json")}


def checked(run):
    manifest = read(run / "manifest.json")
    if manifest["format"] != "orbweaver-query-standalone-runtime-v1":
        raise ValueError("Wrong benchmark format")
    for name, expected in manifest["files"].items():
        if sha(run / name) != expected:
            raise ValueError(f"Frozen file changed: {name}")
    return manifest


def worker(run, index):
    started = time.perf_counter()
    sys.path.insert(0, str(run / "source"))
    import numpy as np

    from orbweaver_query import ExplicitPathModel, GraphSnapshot, Limits, LinkQuery, Session

    imported = time.perf_counter()
    manifest = checked(run)
    job = manifest["jobs"][index]
    seed = job["seed"]
    prep_start = time.perf_counter()
    graph = GraphSnapshot.load(run / f"{seed}-graph.npz")
    model = ExplicitPathModel.load(run / f"{seed}-model.npz")
    with np.load(run / f"{seed}-queries.npz", allow_pickle=False) as data:
        pairs = data[job["workload"]]
    queries = [LinkQuery(graph.node_ids[h], graph.relations[r]) for h, r in pairs]
    session = Session(graph, model, limits=Limits(window_size=1024 if len(queries) == 1024 else 256))
    prepared = time.perf_counter()
    reference, samples = None, []
    for repeat in range(manifest["warmup_batches"] + manifest["timed_batches"]):
        before = time.perf_counter()
        result = session.run(queries, strategy=job["strategy"])
        scored = time.perf_counter()
        payload = json.dumps([{"head": row.query.head, "relation": row.query.relation,
                              "candidate_ids": row.candidate_ids, "scores": row.scores.tolist()}
                             for row in result.rows], separators=(",", ":"), allow_nan=False).encode()
        serialized = time.perf_counter()
        identity = hashlib.sha256(payload).hexdigest()
        if reference is None:
            reference = identity
            cold_first = {"first_inference_seconds": scored-before,
                          "first_serialization_seconds": serialized-scored,
                          "worker_start_to_first_result_seconds": serialized-started}
        elif identity != reference:
            raise ValueError("Repeated batch predictions differ")
        if repeat >= manifest["warmup_batches"]:
            samples.append({"inference_seconds": scored-before,
                "serialization_seconds": serialized-scored, "batch_seconds": serialized-before})
    report = {"job": job, "output_sha256": reference, "output_bytes": len(payload),
        "import_seconds": imported-started, "artifact_preparation_seconds": prepared-prep_start,
        "cold_first": cold_first,
        "peak_process_rss_bytes": rss(), "samples": samples, "profile": result.report(),
        "graph_id": graph.snapshot_id, "model_id": model.model_id,
        "graph_numeric_bytes": graph.numeric_bytes, "model_numeric_bytes": model.coefficient.nbytes,
        "environment": {"python": sys.version, "numpy": np.__version__, "platform": sys.platform}}
    write(run / f"worker-{index:03d}.json", report)


def summarize(run, manifest):
    import numpy as np

    workers = []
    for index, job in enumerate(manifest["jobs"]):
        row = read(run / f"worker-{index:03d}.json")
        if row["job"] != job or len(row["samples"]) != manifest["timed_batches"]:
            raise ValueError("Worker identity/sample count mismatch")
        workers.append(row)
    conditions, checks = {}, []
    for seed in SEEDS:
        for workload in WORKLOADS:
            subset = [w for w in workers if w["job"]["seed"] == seed and w["job"]["workload"] == workload]
            if len(subset) != len(ARMS)*3 or len({w["output_sha256"] for w in subset}) != 1:
                raise ValueError("Cross-strategy predictions or repetitions differ")
            medians = {}
            for arm in ARMS:
                rows = [w for w in subset if w["job"]["strategy"] == arm]
                samples = [sample for w in rows for sample in w["samples"]]
                metrics = {name: {"median": float(np.median([s[name] for s in samples])),
                                   "p95": float(np.percentile([s[name] for s in samples], 95))}
                           for name in ("batch_seconds", "inference_seconds", "serialization_seconds")}
                medians[arm] = metrics["batch_seconds"]["median"]
                conditions[f"{seed}/{workload}/{arm}"] = {**metrics,
                    "import_seconds": [w["import_seconds"] for w in rows],
                    "cold_first": [w["cold_first"] for w in rows],
                    "artifact_preparation_seconds": [w["artifact_preparation_seconds"] for w in rows],
                    "peak_process_rss_bytes": [w["peak_process_rss_bytes"] for w in rows],
                    "expansions": [w["profile"]["expansions"] for w in rows],
                    "model_calls": [w["profile"]["model_calls"] for w in rows],
                    "output_sha256": rows[0]["output_sha256"]}
            speedup = medians["consecutive"] / medians["grouped"]
            if workload == "interleaved256":
                checks.append({"seed": seed, "workload": workload, "speedup": speedup,
                               "passed": speedup >= manifest["primary_min_speedup"]})
            elif workload in ("single", "distinct256", "clustered256", "hubs16"):
                checks.append({"seed": seed, "workload": workload, "speedup": speedup,
                               "passed": 1 / speedup <= manifest["maximum_regression"]})
    return {"conditions": conditions, "checks": checks, "passed": all(c["passed"] for c in checks),
            "output_parity": True, "worker_count": len(workers)}


def execute(run):
    manifest = checked(run)
    write(run / "started.json", {"manifest_sha256": sha(run / "manifest.json")})
    env = {**os.environ, **{name: "1" for name in THREADS}}
    cold = []
    for index, job in enumerate(manifest["jobs"]):
        before = time.perf_counter()
        subprocess.run([sys.executable, str(run / "standalone.py"), "worker", str(run),
                        "--index", str(index)], env=env, check=True)
        cold.append({"job": job, "fresh_process_wall_seconds": time.perf_counter()-before})
        if (index+1) % 15 == 0:
            print(f"Completed {index+1}/{len(manifest['jobs'])} isolated workers", flush=True)
    report = {"manifest_sha256": sha(run / "manifest.json"), "summary": summarize(run, manifest),
        "cold_processes": cold, "worker_sha256": {f"worker-{i:03d}.json": sha(run / f"worker-{i:03d}.json")
                                                  for i in range(len(manifest["jobs"]))}}
    write(run / "results.json", report)
    return {k: report["summary"][k] for k in ("passed", "output_parity", "checks")}


def verify(run):
    manifest, result = checked(run), read(run / "results.json")
    if result["manifest_sha256"] != sha(run / "manifest.json"):
        raise ValueError("Results/manifest mismatch")
    expected = {f"worker-{i:03d}.json" for i in range(len(manifest["jobs"]))}
    if set(result["worker_sha256"]) != expected:
        raise ValueError("Worker inventory mismatch")
    for name, identity in result["worker_sha256"].items():
        if sha(run / name) != identity:
            raise ValueError("Worker observations changed")
    if summarize(run, manifest) != result["summary"]:
        raise ValueError("Recomputed summaries/gates differ")
    receipt = {"verified": True, "results_sha256": sha(run / "results.json"),
               "gate_passed": result["summary"]["passed"], "output_parity": True}
    write(run / "verification.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "execute", "worker", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--model-run", type=Path)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    run = args.run.resolve()
    if args.action == "freeze":
        result = freeze(run, args.model_run)
    elif args.action == "execute":
        result = execute(run)
    elif args.action == "verify":
        result = verify(run)
    else:
        result = worker(run, args.index)
    if result is not None:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
