"""Frozen real Cypher -> trained inference workflow with a multi-source cache control."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

ARMS = ("independent", "consecutive", "lru", "grouped")
WORKLOADS = ("distinct256", "clustered256", "interleaved256")
THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")
PROTOCOL = "NEO4J_WORKFLOW_PROTOCOL.md"
CANDIDATES = """UNWIND $queries AS q
MATCH (a:Entity {id: q.head})
OPTIONAL MATCH (a)--()--(b:Entity)
WHERE b <> a AND NOT (a)--(b)
WITH q, min(b.id) AS target
RETURN q.ordinal AS request_id, q.head AS head, q.relation AS relation, target
ORDER BY request_id"""
NODES = "MATCH (n:Entity) RETURN n.id AS id ORDER BY id"
EDGES = """MATCH (a:Entity)-[r]->(b:Entity)
RETURN a.id AS head, type(r) AS relation, b.id AS target"""


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


def freeze(run, runtime_run):
    run, parent = Path(run).resolve(), Path(runtime_run).resolve()
    manifest, receipt, results = [read(parent / name) for name in
                                   ("manifest.json", "verification.json", "results.json")]
    if (manifest["format"] != "orbweaver-query-standalone-runtime-v1"
            or receipt["results_sha256"] != sha(parent / "results.json")
            or not receipt["verified"] or not receipt["output_parity"]
            or results["manifest_sha256"] != sha(parent / "manifest.json")):
        raise ValueError("Expected a verified standalone runtime campaign")
    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[1]
    shutil.copytree(package / "src" / "orbweaver_query", run / "source" / "orbweaver_query",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name, source in {"neo4j_workflow.py": Path(__file__),
                         PROTOCOL: Path(__file__).with_name(PROTOCOL),
                         "source/cache_reference.py": Path(__file__).with_name("cache_reference.py"),
                         "source/disposable_neo4j.py": package / "tools" / "disposable_neo4j.py"}.items():
        shutil.copyfile(source, run / name)
    for name in ("71-model.npz", "71-graph.npz", "71-queries.npz"):
        if sha(parent / name) != manifest["files"][name]:
            raise ValueError("Frozen parent artifact changed")
        shutil.copyfile(parent / name, run / name)
    jobs = [{"strategy": arm, "workload": workload, "replicate": replicate}
            for arm in ARMS for workload in WORKLOADS for replicate in range(3)]
    random.Random(20260927).shuffle(jobs)
    files = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()}
    output = {"format": "orbweaver-query-neo4j-workflow-v1", "jobs": jobs, "files": files,
        "parent_manifest_sha256": sha(parent / "manifest.json"), "query": CANDIDATES,
        "node_query": NODES, "edge_query": EDGES, "timed_batches": 5, "warmup_batches": 1,
        "cache_max_sources": 256, "cache_max_numeric_bytes": 16*2**20,
        "minimum_primary_speedup": 1.25}
    write(run / "manifest.json", output)
    return {"jobs": len(jobs), "manifest_sha256": sha(run / "manifest.json")}


def checked(run):
    manifest = read(run / "manifest.json")
    if manifest["format"] != "orbweaver-query-neo4j-workflow-v1":
        raise ValueError("Wrong workflow format")
    for name, expected in manifest["files"].items():
        if sha(run / name) != expected:
            raise ValueError(f"Changed frozen file {name}")
    return manifest


def import_graph(driver, graph):
    """Only called on a newly provisioned disposable database by execute()."""
    with driver.session() as connection:
        if connection.run("MATCH (n) RETURN count(n)").single()[0] != 0:
            raise ValueError("Fixture import requires an empty disposable database")
        connection.run("CREATE CONSTRAINT entity_id FOR (n:Entity) REQUIRE n.id IS UNIQUE").consume()
        for start in range(0, len(graph.node_ids), 1000):
            connection.run("UNWIND $ids AS id CREATE (:Entity {id: id})",
                           ids=list(graph.node_ids[start:start+1000])).consume()
        triples = graph.triples()
        for relation, name in enumerate(graph.relations):
            edges = triples[triples[:, 1] == relation]
            escaped = name.replace("`", "``")
            query = ("UNWIND $edges AS e MATCH (a:Entity {id: e.head}), (b:Entity {id: e.target}) "
                     f"CREATE (a)-[:`{escaped}`]->(b)")
            for start in range(0, len(edges), 1000):
                connection.run(query, edges=[{"head": graph.node_ids[h], "target": graph.node_ids[t]}
                                             for h, _, t in edges[start:start+1000]]).consume()
        counts = connection.run("MATCH (n) RETURN count(n) AS nodes, sum(COUNT { (n)-->() }) AS edges").single().data()
        if counts != {"nodes": len(graph.node_ids), "edges": len(triples)}:
            raise ValueError("Imported fixture counts differ")
        return counts


def packed_work(result):
    return {"expansions": sum(p.expansions for p in result.profiles),
            "model_calls": sum(p.model_calls for p in result.profiles),
            "type_visits": sum(p.type_visits for p in result.profiles),
            "peak_source_feature_bytes": max((p.peak_feature_bytes for p in result.profiles), default=0)}


def encode(rows):
    return json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def worker(run, index, uri):
    started = time.perf_counter()
    sys.path.insert(0, str(run / "source"))
    import numpy as np
    import neo4j
    from cache_reference import lru_score_bindings
    from orbweaver_query import ExplicitPathModel, GraphSnapshot, Session, score_bindings
    from orbweaver_query.neo4j import Neo4jSource

    imported = time.perf_counter()
    manifest = checked(run)
    job = manifest["jobs"][index]
    before = time.perf_counter()
    model = ExplicitPathModel.load(run / "71-model.npz")
    model_seconds = time.perf_counter() - before
    # Artifact validation is separate from measured database export.
    expected = GraphSnapshot.load(run / "71-graph.npz").snapshot_id
    with np.load(run / "71-queries.npz", allow_pickle=False) as data:
        pairs = data[job["workload"]]
    with neo4j.GraphDatabase.driver(uri, auth=None) as driver:
        before = time.perf_counter()
        driver.verify_connectivity()
        connected = time.perf_counter()
        source = Neo4jSource(driver)
        graph = source.snapshot(nodes=manifest["node_query"], edges=manifest["edge_query"],
                                relations=model.relations)
        exported = time.perf_counter()
        if graph.snapshot_id != expected:
            raise ValueError("Database export differs from frozen model evidence")
        session = Session(graph, model)
        parameters = {"queries": [{"head": graph.node_ids[h], "relation": graph.relations[r], "ordinal": i}
                                  for i, (h, r) in enumerate(pairs)]}
        samples, reference, binding_reference = [], None, None
        for repeat in range(manifest["warmup_batches"] + manifest["timed_batches"]):
            begin = time.perf_counter()
            bindings = list(source.iter_candidates(manifest["query"], parameters))
            queried = time.perf_counter()
            if job["strategy"] == "lru":
                result, work = lru_score_bindings(session, bindings,
                    max_sources=manifest["cache_max_sources"], max_numeric_bytes=manifest["cache_max_numeric_bytes"])
            else:
                result = score_bindings(session, bindings, strategy=job["strategy"])
                work = packed_work(result)
            inferred = time.perf_counter()
            payload = encode(result.to_records())
            serialized = time.perf_counter()
            output_sha = hashlib.sha256(payload).hexdigest()
            binding_sha = hashlib.sha256(encode(bindings)).hexdigest()
            if len(bindings) != len(pairs) or [r["request_id"] for r in bindings] != list(range(len(pairs))):
                raise ValueError("Candidate query lost, reordered or duplicated request ordinals")
            if reference is None:
                reference, binding_reference = output_sha, binding_sha
            elif reference != output_sha or binding_reference != binding_sha:
                raise ValueError("Repeated complete workflow changed bindings or scores")
            measurement = {"candidate_query_transfer_seconds": queried-begin,
                "inference_seconds": inferred-queried, "serialization_seconds": serialized-inferred,
                "workflow_seconds": serialized-begin}
            if repeat == 0:
                first = {**measurement, "worker_start_to_first_result_seconds": serialized-started}
            else:
                samples.append(measurement)
    report = {"job": job, "import_seconds": imported-started, "model_load_seconds": model_seconds,
        "connection_seconds": connected-before, "evidence_export_pack_seconds": exported-connected,
        "first_batch": first, "samples": samples, "work": work,
        "graph_id": graph.snapshot_id, "model_id": model.model_id,
        "binding_sha256": binding_reference, "output_sha256": reference,
        "output_bytes": len(payload), "row_count": len(bindings),
        "null_inputs": sum(r.status == "null_input" for r in result.rows),
        "peak_client_process_rss_bytes": rss(),
        "environment": {"python": sys.version, "numpy": np.__version__,
                        "neo4j_driver": neo4j.__version__, "platform": sys.platform}}
    write(run / f"worker-{index:03d}.json", report)


def summarize(run, manifest):
    import numpy as np

    workers = []
    for index, job in enumerate(manifest["jobs"]):
        row = read(run / f"worker-{index:03d}.json")
        if row["job"] != job or len(row["samples"]) != manifest["timed_batches"]:
            raise ValueError("Worker inventory mismatch")
        workers.append(row)
    if len({w["graph_id"] for w in workers}) != 1 or len({w["model_id"] for w in workers}) != 1:
        raise ValueError("Worker context changed")
    conditions, comparisons = {}, []
    for workload in WORKLOADS:
        subset = [w for w in workers if w["job"]["workload"] == workload]
        if (len(subset) != len(ARMS)*3 or len({w["output_sha256"] for w in subset}) != 1
                or len({w["binding_sha256"] for w in subset}) != 1):
            raise ValueError("Complete workflow outputs/bindings differ across strategies")
        for arm in ARMS:
            rows = [w for w in subset if w["job"]["strategy"] == arm]
            samples = [sample for w in rows for sample in w["samples"]]
            conditions[f"{workload}/{arm}"] = {
                **{key: {"median": float(np.median([s[key] for s in samples])),
                         "p95": float(np.percentile([s[key] for s in samples], 95))}
                   for key in samples[0]},
                "evidence_export_pack_seconds": [w["evidence_export_pack_seconds"] for w in rows],
                "first_batches": [w["first_batch"] for w in rows],
                "peak_client_process_rss_bytes": [w["peak_client_process_rss_bytes"] for w in rows],
                "work": [w["work"] for w in rows], "row_count": rows[0]["row_count"],
                "null_inputs": rows[0]["null_inputs"], "output_bytes": rows[0]["output_bytes"]}
        grouped = conditions[f"{workload}/grouped"]["workflow_seconds"]["median"]
        for control in ("independent", "consecutive", "lru"):
            baseline = conditions[f"{workload}/{control}"]["workflow_seconds"]["median"]
            comparisons.append({"workload": workload, "control": control, "grouped_speedup": baseline/grouped})
    primary = next(c for c in comparisons if c["workload"] == "interleaved256" and c["control"] == "consecutive")
    return {"conditions": conditions, "comparisons": comparisons, "output_parity": True,
            "primary_gate_passed": primary["grouped_speedup"] >= manifest["minimum_primary_speedup"]}


def execute(run, neo4j_home, java):
    manifest = checked(run)
    write(run / "started.json", {"manifest_sha256": sha(run / "manifest.json")})
    sys.path.insert(0, str(run / "source"))
    from disposable_neo4j import disposable_database
    from neo4j import GraphDatabase
    from orbweaver_query import GraphSnapshot

    graph = GraphSnapshot.load(run / "71-graph.npz")
    cold = []
    with disposable_database(neo4j_home, java) as uri:
        with GraphDatabase.driver(uri, auth=None) as driver:
            before = time.perf_counter()
            counts = import_graph(driver, graph)
            import_seconds = time.perf_counter()-before
            with driver.session() as connection:
                server = connection.run("CALL dbms.components() YIELD name, versions, edition RETURN *").data()
        print(f"Imported {counts['nodes']} nodes and {counts['edges']} edges in {import_seconds:.2f}s", flush=True)
        env = {**os.environ, **{name: "1" for name in THREADS}}
        for index, job in enumerate(manifest["jobs"]):
            before = time.perf_counter()
            subprocess.run([sys.executable, str(run / "neo4j_workflow.py"), "worker", str(run),
                            "--index", str(index), "--uri", uri], env=env, check=True)
            cold.append({"job": job, "fresh_client_process_wall_seconds": time.perf_counter()-before})
            print(f"Completed workflow worker {index+1}/{len(manifest['jobs'])}", flush=True)
    result = {"manifest_sha256": sha(run / "manifest.json"), "server": server,
        "fixture": counts, "fixture_import_seconds": import_seconds,
        "summary": summarize(run, manifest), "cold_client_processes": cold,
        "worker_sha256": {f"worker-{i:03d}.json": sha(run / f"worker-{i:03d}.json")
                          for i in range(len(manifest["jobs"]))}}
    write(run / "results.json", result)
    return {k: result["summary"][k] for k in ("output_parity", "primary_gate_passed", "comparisons")}


def verify(run):
    manifest, result = checked(run), read(run / "results.json")
    expected = {f"worker-{i:03d}.json" for i in range(len(manifest["jobs"]))}
    if result["manifest_sha256"] != sha(run / "manifest.json") or set(result["worker_sha256"]) != expected:
        raise ValueError("Manifest or worker inventory mismatch")
    for name, digest in result["worker_sha256"].items():
        if sha(run / name) != digest:
            raise ValueError("Worker observations changed")
    if summarize(run, manifest) != result["summary"]:
        raise ValueError("Recomputed measurements/gate differ")
    receipt = {"verified": True, "results_sha256": sha(run / "results.json"),
               "output_parity": True, "primary_gate_passed": result["summary"]["primary_gate_passed"]}
    write(run / "verification.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "execute", "worker", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--runtime-run", type=Path)
    parser.add_argument("--neo4j-home", type=Path)
    parser.add_argument("--java", type=Path)
    parser.add_argument("--uri")
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    run = args.run.resolve()
    if args.action == "freeze":
        result = freeze(run, args.runtime_run)
    elif args.action == "execute":
        if args.neo4j_home is None or args.java is None:
            parser.error("execute requires --neo4j-home and --java")
        result = execute(run, args.neo4j_home, args.java)
    elif args.action == "verify":
        result = verify(run)
    else:
        result = worker(run, args.index, args.uri)
    if result is not None:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
