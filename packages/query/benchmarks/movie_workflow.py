"""Fixed native-Mac movie workflow comparison; see MOVIE_WORKFLOW_PROTOCOL.md."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "examples"))
sys.path.insert(0, str(PACKAGE / "benchmarks"))
from mac_release import activity, host, installed_identity  # noqa: E402
from movie_recommendations import (  # noqa: E402
    CANDIDATES,
    NATIVE,
    compare,
    fetch_fixture,
    import_fixture,
    make_plan,
    normalize_native,
    prediction,
    snapshot,
)
from disposable_neo4j import disposable_database, native_runtime_identity  # noqa: E402

ARMS = (
    "native_cypher",
    "manual_intersection",
    "full_source_shared",
    "plan",
    "plan_unfused",
    "warm_pair_cache",
    "precomputed_scores",
)
WORKLOADS = {
    "single": {"titles": ["The Matrix"], "since": 1990, "minimum": 1},
    "basket_with_repeat": {
        "titles": ["The Matrix", "Top Gun", "Apollo 13", "The Matrix"],
        "since": 1990,
        "minimum": 1,
    },
    "filtered_basket": {
        "titles": ["The Matrix", "Top Gun", "Apollo 13", "The Matrix"],
        "since": 2000,
        "minimum": 2,
    },
}
THREADS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "BLIS_NUM_THREADS",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def software(home, java):
    return {
        "neo4j_driver": importlib.metadata.version("neo4j"),
        "java": native_runtime_identity(java),
        "neo4j_libraries": {p.name: sha(p) for p in sorted((home / "lib").glob("*.jar"))},
    }


def models():
    from orbweaver_query import NeighborhoodModel

    return {
        name: NeighborhoodModel(relations=("ACTED_IN",), metric=metric)
        for name, metric in (
            ("shared_cast", "common_neighbors"),
            ("affinity", "resource_allocation"),
        )
    }


def manual_scores(graph, rows, methods, minimum, *, adj=None, prepared=None, full=False):
    """Independent intersections or a shared full-feature control, restoring row bags."""
    output, features_by_head = [], {}
    for row in rows:
        h, t = graph.node_index(row["head"]), graph.node_index(row["target"])
        if prepared is not None:
            count, affinity = prepared[h, t]
        elif full:
            if h not in features_by_head:
                from orbweaver_query import Limits

                features = methods["shared_cast"].expand(graph, h, Limits())
                # Both controls get the same one-pass feature-sharing opportunity.
                counts = methods["shared_cast"].score(features, 0)
                affinities = methods["affinity"].score(features, 0)
                features_by_head[h] = {
                    int(n): (float(a), float(b))
                    for n, a, b in zip(features.candidates, counts, affinities)
                }
            count, affinity = features_by_head[h][t]
        else:
            common = sorted(adj[h] & adj[t])
            count, affinity = float(len(common)), sum(1.0 / len(adj[n]) for n in common)
        if count >= minimum:
            output.append(
                {
                    **row,
                    "shared_cast": prediction(count, graph.snapshot_id, methods["shared_cast"]),
                    "affinity": prediction(affinity, graph.snapshot_id, methods["affinity"]),
                }
            )
    return output


def checked(run):
    manifest = read(run / "manifest.json")
    if manifest["format"] != "mac-movie-workflow-v1":
        raise ValueError("Unexpected workflow format")
    for name, digest in manifest["files"].items():
        if sha(run / name) != digest:
            raise ValueError(f"Frozen file changed: {name}")
    return manifest


def freeze(run, wheel, home, java, cache):
    import zipfile
    from neo4j import GraphDatabase
    from orbweaver_query.neo4j import Neo4jSource

    installed = installed_identity()
    with zipfile.ZipFile(wheel) as archive:
        members = {
            n.removeprefix("orbweaver_query/"): hashlib.sha256(archive.read(n)).hexdigest()
            for n in archive.namelist()
            if n.startswith("orbweaver_query/") and not n.endswith("/")
        }
    if members != installed["files"]:
        raise ValueError("Installed package does not match supplied wheel")
    fixture = fetch_fixture(cache)
    run.mkdir(parents=True, exist_ok=False)
    files = (
        "examples/movie_recommendations.py",
        "benchmarks/movie_workflow.py",
        "benchmarks/MOVIE_WORKFLOW_PROTOCOL.md",
        "benchmarks/mac_release.py",
        "benchmarks/v1/targeted.py",
        "tools/disposable_neo4j.py",
        "tools/text2cypher_execute.py",
        "tools/text2cypher_audit.py",
    )
    for name in files:
        (run / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PACKAGE / name, run / name)
    shutil.copyfile(wheel, run / wheel.name)
    shutil.copyfile(fixture, run / "movies.cypher")
    # Fixture preparation and answer checks only; these are not benchmark samples.
    with disposable_database(home, java, entrypoint="org.neo4j.server.Neo4jCommunity") as uri:
        with GraphDatabase.driver(uri, auth=None) as driver:
            import_fixture(driver, fixture)
            source = Neo4jSource(driver)
            graph = snapshot(source)
            graph.save(run / "graph.npz")
            server = [r.data() for r in driver.execute_query("CALL dbms.components()")[0]]
            expected = {}
            for name, params in WORKLOADS.items():
                rows = list(source.iter_candidates(CANDIDATES, params))
                plan = make_plan(graph, params["minimum"])
                result = plan.run(rows).to_records()
                reference = normalize_native(
                    source.iter_candidates(NATIVE, params), graph.snapshot_id, models()
                )
                compare(result, reference)
                expected[name] = {"candidates": rows, "records": reference}
            write(run / "expected.json", expected)
    jobs = [
        {"workload": name, "arm": arm, "replicate": r}
        for name in WORKLOADS
        for arm in ARMS
        for r in range(3)
    ]
    random.Random(2026092801).shuffle(jobs)
    manifest = {
        "format": "mac-movie-workflow-v1",
        "jobs": jobs,
        "workloads": WORKLOADS,
        "samples": 7,
        "installed": installed,
        "environment": host(),
        "software": software(home, java),
        "server": server,
        "wheel": wheel.name,
        "graph_id": graph.snapshot_id,
        "files": {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()},
    }
    write(run / "manifest.json", manifest)
    return {
        "jobs": len(jobs),
        "manifest_sha256": sha(run / "manifest.json"),
        "graph_id": graph.snapshot_id,
    }


def worker(run, index, uri):
    import resource
    from neo4j import GraphDatabase
    from orbweaver_query import BindingCache
    from orbweaver_query.neo4j import Neo4jSource

    manifest = checked(run)
    if installed_identity() != manifest["installed"] or host() != manifest["environment"]:
        raise ValueError("Runtime/host changed since freeze")
    if importlib.metadata.version("neo4j") != manifest["software"]["neo4j_driver"]:
        raise ValueError("Neo4j driver changed since freeze")
    job = manifest["jobs"][index]
    params, arm = manifest["workloads"][job["workload"]], job["arm"]
    observation = activity()
    started = time.perf_counter()
    with GraphDatabase.driver(uri, auth=None) as driver:
        driver.verify_connectivity()
        connection_seconds = time.perf_counter() - started
        source = Neo4jSource(driver)
        methods = models()
        graph, plan, adj, precomputed = None, None, None, None
        cache = BindingCache(max_entries=16384)
        export_seconds = preparation_seconds = 0.0
        if arm != "native_cypher":
            begin = time.perf_counter()
            graph = snapshot(source)
            if graph.snapshot_id != manifest["graph_id"]:
                raise ValueError("Database evidence changed")
            export_seconds = time.perf_counter() - begin
            begin = time.perf_counter()
            plan = make_plan(graph, params["minimum"])
            if arm in ("manual_intersection", "precomputed_scores"):
                adj = [set(map(int, graph.neighbors(i))) for i in range(len(graph.node_ids))]
            if arm == "precomputed_scores":
                # Favorable oracle: all requested sources, all movie targets.
                heads = [graph.node_index("movie:" + title) for title in set(params["titles"])]
                targets = [i for i, name in enumerate(graph.node_ids) if name.startswith("movie:")]
                precomputed = {}
                for h in heads:
                    for t in targets:
                        if h != t:
                            common = sorted(adj[h] & adj[t])
                            precomputed[h, t] = (
                                float(len(common)),
                                sum(1.0 / len(adj[n]) for n in common),
                            )
            if arm == "warm_pair_cache":
                plan.run(list(source.iter_candidates(CANDIDATES, params)), cache=cache)
            preparation_seconds = time.perf_counter() - begin
        samples, reference, identity = [], None, None
        work = {}
        for iteration in range(1 + manifest["samples"]):
            begin = time.perf_counter()
            if arm == "native_cypher":
                native = list(source.iter_candidates(NATIVE, params))
                query_end = time.perf_counter()
                payload = normalize_native(native, manifest["graph_id"], methods)
                work = {"native_query": True}
            else:
                rows = list(source.iter_candidates(CANDIDATES, params))
                query_end = time.perf_counter()
                if arm in ("plan", "plan_unfused", "warm_pair_cache"):
                    result = plan.run(
                        rows,
                        fused=arm != "plan_unfused",
                        cache=cache if arm == "warm_pair_cache" else None,
                    )
                    payload, work = result.to_records(), result.report()
                else:
                    payload = manual_scores(
                        graph,
                        rows,
                        methods,
                        params["minimum"],
                        adj=adj,
                        prepared=precomputed,
                        full=arm == "full_source_shared",
                    )
                    work = {"manual": arm}
            scored = time.perf_counter()
            encoded = json.dumps(payload, sort_keys=True, allow_nan=False).encode()
            done = time.perf_counter()
            sample = {
                "total_seconds": done - begin,
                "query_transfer_seconds": query_end - begin,
                "local_materialize_seconds": scored - query_end,
                "json_seconds": done - scored,
            }
            digest = hashlib.sha256(encoded).hexdigest()
            if reference is None:
                reference, identity, first = payload, digest, sample
                first_use_seconds = done - started
            elif digest != identity:
                raise ValueError("Repeated request changed output")
            if iteration:
                samples.append(sample)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "job": job,
        "connection_seconds": connection_seconds,
        "snapshot_export_seconds": export_seconds,
        "preparation_seconds": preparation_seconds,
        "first": first,
        "samples": samples,
        "output": reference,
        "output_sha256": identity,
        "median_seconds": statistics.median(x["total_seconds"] for x in samples),
        "first_use_seconds": first_use_seconds,
        "peak_client_rss_bytes": rss,
        "work": work,
        "activity_before": observation,
        "activity_after": activity(),
    }


def execute(run, home, java, *, preflight, host_use):
    from neo4j import GraphDatabase

    manifest = checked(run)
    if software(home, java) != manifest["software"]:
        raise ValueError("Neo4j/Java software changed since freeze")
    output = run / ("preflight" if preflight else "workers")
    output.mkdir(exist_ok=False)
    started = time.perf_counter()
    with disposable_database(home, java, entrypoint="org.neo4j.server.Neo4jCommunity") as uri:
        startup = time.perf_counter() - started
        with GraphDatabase.driver(uri, auth=None) as driver:
            begin = time.perf_counter()
            import_fixture(driver, run / "movies.cypher")
            imported = time.perf_counter() - begin
        write(
            output / "campaign.json",
            {
                "preflight": preflight,
                "host_use": host_use,
                "database_startup_seconds": startup,
                "fixture_import_seconds": imported,
                "database_heap_mib": 256,
                "page_cache_mib": 64,
            },
        )
        seen = set()
        for i, job in enumerate(manifest["jobs"]):
            if preflight and (job["workload"] != "basket_with_repeat" or job["arm"] in seen):
                continue
            seen.add(job["arm"])
            command = [
                sys.executable,
                "-I",
                str(run / "benchmarks/movie_workflow.py"),
                "worker",
                str(run),
                "--index",
                str(i),
                "--uri",
                uri,
            ]
            begin = time.perf_counter()
            try:
                result = subprocess.run(
                    command,
                    env={**os.environ, **{k: "1" for k in THREADS}},
                    text=True,
                    capture_output=True,
                    timeout=90,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                write(
                    output / f"{i:03d}-error.json",
                    {"job": job, "error": "timeout", "stderr": str(error.stderr)},
                )
                raise
            if result.returncode:
                write(
                    output / f"{i:03d}-error.json",
                    {"job": job, "stdout": result.stdout, "stderr": result.stderr},
                )
                raise RuntimeError("Worker failed; retained error record")
            try:
                value = json.loads(result.stdout)
            except (ValueError, TypeError):
                write(
                    output / f"{i:03d}-error.json",
                    {"job": job, "stdout": result.stdout, "stderr": result.stderr},
                )
                raise
            value["subprocess_wall_seconds"] = time.perf_counter() - begin
            # Retain measured output even if the answer check fails.
            write(output / f"{i:03d}.json", value)
            compare(value["output"], read(run / "expected.json")[job["workload"]]["records"])
            print(f"Verified {job['workload']} / {job['arm']} / {job['replicate']}", flush=True)
    return {"completed": True, "mode": "preflight" if preflight else "campaign"}


def verify(run):
    manifest = checked(run)
    expected = read(run / "expected.json")
    records = [read(run / "workers" / f"{i:03d}.json") for i in range(len(manifest["jobs"]))]
    for job, record in zip(manifest["jobs"], records):
        if job != record["job"] or len(record["samples"]) != manifest["samples"]:
            raise ValueError("Incomplete or mismatched worker")
        compare(record["output"], expected[job["workload"]]["records"])
        raw = json.dumps(record["output"], sort_keys=True, allow_nan=False).encode()
        if hashlib.sha256(raw).hexdigest() != record["output_sha256"]:
            raise ValueError("Output digest mismatch")
        for sample in record["samples"]:
            if not all(math.isfinite(v) and v >= 0 for v in sample.values()):
                raise ValueError("Invalid timing sample")
            if not math.isclose(
                sample["total_seconds"],
                sum(
                    sample[k]
                    for k in ("query_transfer_seconds", "local_materialize_seconds", "json_seconds")
                ),
                abs_tol=1e-9,
            ):
                raise ValueError("Timing components do not sum")
        if (
            statistics.median(x["total_seconds"] for x in record["samples"])
            != record["median_seconds"]
        ):
            raise ValueError("Median mismatch")
    conditions = []
    for name in manifest["workloads"]:
        arms = {}
        for arm in ARMS:
            chosen = [r for r in records if r["job"]["workload"] == name and r["job"]["arm"] == arm]
            arms[arm] = {
                "request_ms": statistics.median(r["median_seconds"] for r in chosen) * 1000,
                "first_use_ms": statistics.median(r["first_use_seconds"] for r in chosen) * 1000,
                "export_ms": statistics.median(r["snapshot_export_seconds"] for r in chosen) * 1000,
                "preparation_ms": statistics.median(r["preparation_seconds"] for r in chosen)
                * 1000,
                "peak_client_rss_mib": max(r["peak_client_rss_bytes"] for r in chosen) / 2**20,
            }
        best = min(
            ("native_cypher", "manual_intersection", "full_source_shared"),
            key=lambda a: arms[a]["request_ms"],
        )
        conditions.append(
            {
                "workload": name,
                "arms": arms,
                "strongest_ondemand": best,
                "plan_speedup": arms[best]["request_ms"] / arms["plan"]["request_ms"],
                "output_rows": len(expected[name]["records"]),
            }
        )
    report = {
        "format": manifest["format"],
        "manifest_sha256": sha(run / "manifest.json"),
        "campaign": read(run / "workers/campaign.json"),
        "checked_workers": len(records),
        "environment": manifest["environment"],
        "conditions": conditions,
        "numerical_parity": True,
        "release_gate_complete": False,
        "scope": "One small public movie graph; startup/import separate; no general speedup claim.",
    }
    write(run / "results.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "preflight", "execute", "worker", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--neo4j-home", type=Path)
    parser.add_argument("--java", type=Path)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/orbweaver-query/movies")
    parser.add_argument("--host-use", choices=("quiet-window", "normal-mixed-use"))
    parser.add_argument("--index", type=int)
    parser.add_argument("--uri")
    args = parser.parse_args()
    run = args.run.resolve()
    if args.command in ("freeze", "preflight", "execute") and (
        args.neo4j_home is None or args.java is None
    ):
        parser.error("--neo4j-home and --java are required")
    if args.command == "freeze":
        if args.wheel is None:
            parser.error("--wheel is required")
        result = freeze(
            run, args.wheel.resolve(), args.neo4j_home.resolve(), args.java.resolve(), args.cache
        )
    elif args.command in ("preflight", "execute"):
        if args.command == "execute" and args.host_use is None:
            parser.error("--host-use must explicitly describe this measurement session")
        result = execute(
            run,
            args.neo4j_home.resolve(),
            args.java.resolve(),
            preflight=args.command == "preflight",
            host_use=args.host_use or "preflight-only",
        )
    elif args.command == "worker":
        if args.index is None or args.uri is None:
            parser.error("--index and --uri are required")
        result = worker(run, args.index, args.uri)
    else:
        result = verify(run)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
