"""Check native Neo4j -> actual Quail pair restriction, without model inference.

Only an owned disposable Neo4j database is modified. Fixed hash decisions test
row semantics, not accuracy. Byte tokenization tests plans, not model costs.
"""

import argparse
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys

from neo4j import GraphDatabase
import quail
from quail.execution.runner import ExecutionContext, ForeignRuntime
from quail.physical import AiJoin, Foreign, PortRef

from orbweaver_query.neo4j import Neo4jSource
from orbweaver_query.quail import QuailPairs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from disposable_neo4j import disposable_database  # noqa: E402

PIN = "41b883b838687cfbf018080f068f3e81bf2f8e64"
EXPORT = """MATCH (c:BridgeClaim)
OPTIONAL MATCH (c)-[e:CITES]->(d:BridgeDocument)
RETURN c.id AS head, d.id AS target, c.text AS head_text,
       d.text AS target_text, e.ordinal AS ordinal
ORDER BY head, ordinal, target"""
POSITIVE = """MATCH (c:BridgeClaim)-[e:CITES]->(d:BridgeDocument)
WHERE c.text IS NOT NULL AND d.text IS NOT NULL AND e.keep
RETURN c.id AS head, d.id AS target, c.text AS head_text,
       d.text AS target_text, e.ordinal AS ordinal
ORDER BY head, ordinal, target"""


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fixture(inputs):
    if inputs is None:
        edges = [dict(claim_id=c, document_id=d, claim=f"Claim {c}", title=f"Document {d}",
                      abstract=["Fixture evidence."], source_occurrences=n)
                 for c, d, n in [(1, 1, 2), (1, 2, 1), (2, 2, 1), (3, 1, 1)]]
    else:
        edges = json.loads(inputs.read_text())["edges"]
    rows = []
    for edge in edges:
        head, target = f"claim:{edge['claim_id']}", f"document:{edge['document_id']}"
        keep = int(digest([head, target])[:8], 16) % 3 == 0
        for _ in range(edge["source_occurrences"]):
            rows.append(dict(head=head, target=target, head_text=edge["claim"],
                target_text=edge["title"]+"\n\n"+" ".join(edge["abstract"]),
                ordinal=len(rows), keep=keep))
    return rows


def verify(driver, rows):
    with driver.session() as connection:
        connection.run("""UNWIND $rows AS row
            MERGE (c:BridgeClaim {id:row.head}) SET c.text=row.head_text
            MERGE (d:BridgeDocument {id:row.target}) SET d.text=row.target_text
            CREATE (c)-[:CITES {ordinal:row.ordinal, keep:row.keep}]->(d)""", rows=rows).consume()
        connection.run("""CREATE (:BridgeClaim {id:'null:orphan', text:'No citation'}),
            (c:BridgeClaim {id:'null:claim', text:'Missing document text'}),
            (d:BridgeDocument {id:'null:document'}),
            (c)-[:CITES {ordinal:-1, keep:true}]->(d),
            (:BridgeDocument {id:'unused:document', text:'Not a candidate'})""").consume()
    source = Neo4jSource(driver, fetch_size=7)
    captured = QuailPairs.from_neo4j(source, EXPORT)
    expected = tuple(source.iter_candidates(POSITIVE))
    expected_pairs = {(row["head"], row["target"]) for row in rows}
    assert set(captured.candidate_pairs) == expected_pairs
    assert captured.describe()["input_bindings"] == len(rows)+2
    assert captured.describe()["null_bindings"] == 2
    reports = []
    for kind in ("per_batch", "barrier"):
        with quail.Session(quail.EngineConfig(model="qwen3-4b-fp8", device="h100-sxm"),
                           tokenizer=lambda text: list(text.encode())) as session:
            bound = captured.bind(session, "Does {1} support {0}?", kind=kind)
            plan = bound.query.plan()
            plan.graph.validate(runtime_keys=set(session.registry.runtimes))
            plan.graph.validate_backend(plan.backend)
            foreign, = plan.graph.nodes_by_type(Foreign.type_name)
            join, = plan.graph.nodes_by_type(AiJoin.type_name)
            assert join.stages[0].pairs_from == foreign.node_id
            assert PortRef(foreign.node_id, f"pairs:{foreign.written_pos}") in {
                port.source for port in join.inputs}
            request = bound.query._prepare_physical()
            tables = request.column_tables()
            ids = {alias: list(reversed(range(table.num_rows))) for alias, table in tables.items()}
            inputs = {port.name: ids[port.source.port.split(":")[1]] for port in foreign.inputs}
            result = ForeignRuntime().execute(foreign, inputs, ExecutionContext(
                runtimes=session.registry.runtimes, sources=request.relations,
                functions=session.registry.functions))
            pair_table = result.outputs[f"pairs:{foreign.written_pos}"]
            pairs = [(tables["l"]["id"][left].as_py(), tables["r"]["id"][right].as_py())
                     for left, right in zip(pair_table["l"].to_pylist(), pair_table["r"].to_pylist())]
            assert len(pairs) == len(set(pairs)) == len(expected_pairs)
            assert set(pairs) == expected_pairs
            decisions = [pair for pair in pairs if int(digest(pair)[:8], 16) % 3 == 0]
            actual = captured.restore(decisions)
            assert actual == expected
            reports.append(dict(kind=kind, candidate_pairs=len(pairs),
                pair_domain_sha256=digest(sorted(pairs)), output_bindings=len(actual),
                output_sha256=digest(actual), native_rows_equal=True, plan=plan.graph.explain()))
    # The shared source's database-side read-only guard remains active.
    try:
        QuailPairs.from_neo4j(source, "CREATE (:ForbiddenBridgeWrite)")
    except ValueError as error:
        assert "read-only" in str(error)
    else:
        raise AssertionError("write query was accepted")
    with driver.session() as connection:
        assert connection.run("MATCH (n:ForbiddenBridgeWrite) RETURN count(n) AS n").single()["n"] == 0
    return dict(candidates=captured.describe(), conditions=reports, readonly_guard=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j-home", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, help="Frozen SciFact inputs.json; omit for tiny fixture")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a new output path; retain previous evidence")
    upstream = Path(quail.__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if commit != PIN or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=upstream, text=True).strip():
        raise ValueError("This check requires the clean pinned Quail checkout")
    rows = fixture(args.inputs)
    with disposable_database(args.neo4j_home, args.java) as uri:
        with GraphDatabase.driver(uri, auth=None) as driver:
            result = verify(driver, rows)
    sources = [Path(__file__), Path(__file__).parents[2]/"src/orbweaver_query/quail.py",
               Path(__file__).parents[2]/"src/orbweaver_query/neo4j.py",
               Path(__file__).parents[2]/"tools/disposable_neo4j.py"]
    result.update(kind="CPU integration correctness; no inference, quality or performance claim",
        quail_commit=commit, python=platform.python_version(), platform=platform.platform(),
        dependencies={name: version(name) for name in ("quail-engine", "pyarrow", "neo4j", "numpy")},
        input_sha256=sha256(args.inputs.read_bytes()).hexdigest() if args.inputs else None,
        source_sha256={path.name: sha256(path.read_bytes()).hexdigest() for path in sources},
        oracle="sha256([head,target]) first 32 bits modulo 3 equals 0; not model predictions")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"output": str(args.output), "candidates": result["candidates"],
                      "conditions": len(result["conditions"]), "passed": True}))


if __name__ == "__main__":
    main()
