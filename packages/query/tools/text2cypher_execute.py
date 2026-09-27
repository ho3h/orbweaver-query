"""Frozen corpus execution against a disposable local database, never a remote demo."""

import argparse
import gzip
import hashlib
import json
import logging
import re
import time
import urllib.request
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from disposable_neo4j import disposable_database
from text2cypher_audit import SOURCES, TOKEN, indicators, layout_key, sha

MOVIES_REVISION = "51cf90d18c1a7f74bce7a77083543697dfb0139d"
MOVIES_URL = f"https://raw.githubusercontent.com/neo4j-graph-examples/movies/{MOVIES_REVISION}/scripts/movies.cypher"
MOVIES_SHA = "7be04aba2193790e0051308e6aa8550236e651cae652ea7da44b7dc01f4c4e69"
ALIAS = "neo4jlabs_demo_db_movies"
CAP = 5000
PROTOCOL = "TEXT2CYPHER_EXECUTION_PROTOCOL.md"
REQUIRED = ("MATCH", "WHERE", "WITH", "AGGREGATE_CALL", "ORDER_BY", "LIMIT", "DISTINCT",
            "OPTIONAL_MATCH", "UNWIND")


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def sources():
    root = Path(__file__).resolve().parents[1]
    return {"tools/" + name: root / "tools" / name for name in
            ("text2cypher_execute.py", "text2cypher_audit.py", "disposable_neo4j.py")} | {
        "runtime/" + p.name: p for p in (root / "src" / "orbweaver_query").glob("*.py")} | {
        PROTOCOL: root / "benchmarks" / PROTOCOL}


def freeze(run, parquet):
    import pyarrow.parquet as pq

    run, parquet = Path(run), Path(parquet).resolve()
    if run.exists() and any(run.iterdir()):
        raise ValueError("Fresh run directory required")
    if sha(parquet) != SOURCES[0]["sha256"]:
        raise ValueError("Corpus checksum mismatch")
    grouped, count = {}, 0
    for row in pq.read_table(parquet).to_pylist():
        if row["database_reference_alias"] != ALIAS:
            continue
        count += 1
        query = layout_key(row["cypher"])
        grouped.setdefault(query, []).append(row["instance_id"])
    inventory = []
    for query, instances in sorted(grouped.items()):
        tokens = " ".join(m.group().upper() for m in TOKEN.finditer(query) if not m.group("ignore"))
        blocked = "LOAD CSV" in tokens or ("CALL" in tokens and
                   not re.fullmatch(r"CALL\s+db\.schema\.visualization\(\)\s*;?", query, re.IGNORECASE))
        inventory.append({"query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "query": query, "instance_ids": sorted(instances), "indicators": indicators(query),
            "excluded_external_input": blocked})
    run.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(MOVIES_URL, timeout=60) as response:
        script = response.read()
    if hashlib.sha256(script).hexdigest() != MOVIES_SHA:
        raise ValueError("Fixture checksum mismatch")
    (run / "movies.cypher").write_bytes(script)
    write_json(run / "inventory.json", inventory)
    frozen = {}
    for name, source in sources().items():
        target = run / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        frozen[name] = sha(target)
    manifest = {"schema": "text2cypher-movies-execution-v2", "dataset": SOURCES[0],
        "corpus_path": str(parquet), "database_alias": ALIAS, "source_rows": count,
        "unique_queries": len(inventory), "inventory_sha256": sha(run / "inventory.json"),
        "fixture_url": MOVIES_URL, "fixture_sha256": MOVIES_SHA, "row_cap": CAP,
        "transaction_timeout": "5s", "source_sha256": frozen}
    write_json(run / "manifest.json", manifest)
    return {k: manifest[k] for k in ("schema", "source_rows", "unique_queries")}


def checked(run, *, current=True):
    run = Path(run)
    m = json.loads((run / "manifest.json").read_text())
    if (m["schema"] != "text2cypher-movies-execution-v2" or m["dataset"] != SOURCES[0]
            or sha(m["corpus_path"]) != SOURCES[0]["sha256"]
            or sha(run / "movies.cypher") != MOVIES_SHA or m["fixture_sha256"] != MOVIES_SHA
            or sha(run / "inventory.json") != m["inventory_sha256"]
            or m["row_cap"] != CAP or m["transaction_timeout"] != "5s"):
        raise ValueError("Changed corpus/fixture/inventory/config")
    for name, digest in m["source_sha256"].items():
        if sha(run / "source" / name) != digest or (current and sha(sources()[name]) != digest):
            raise ValueError(f"Changed frozen source {name}")
    return m


def statements(script):
    """Split only unquoted semicolons in the pinned fixture's Cypher text."""
    start = 0
    for token in TOKEN.finditer(script):
        if token.group() == ";" and not token.group("ignore"):
            value = script[start:token.start()].strip()
            if value:
                yield value
            start = token.end()
    if script[start:].strip():
        yield script[start:].strip()


def canonical(value):
    from neo4j.graph import Node, Relationship
    from neo4j.graph import Path as GraphPath

    if isinstance(value, Node):
        return {"$node": value.element_id, "labels": sorted(value.labels),
                "properties": canonical(dict(value))}
    if isinstance(value, Relationship):
        return {"$relationship": value.element_id, "type": value.type,
                "start": value.start_node.element_id, "end": value.end_node.element_id,
                "properties": canonical(dict(value))}
    if isinstance(value, GraphPath):
        return {"$path": [canonical(v) for v in value.nodes],
                "relationships": [canonical(v) for v in value.relationships]}
    if isinstance(value, dict):
        return {"$map": [[str(k), canonical(v)] for k, v in sorted(value.items())]}
    if isinstance(value, (list, tuple)):
        return {"$list": [canonical(v) for v in value]}
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        return {"$float": value.hex()}
    raise TypeError(f"Unsupported result value {type(value).__name__}")


class RowLimit(RuntimeError):
    pass


def direct(driver, query):
    with (driver.session(default_access_mode="READ") as connection,
          connection.begin_transaction() as tx):
        if tx.run("EXPLAIN " + query).consume().query_type != "r":
            raise ValueError("Query is not read-only")
        for row in tx.run(query):
            yield dict(row)


def digest(rows):
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def normalize_virtual_schema(encoded):
    """Alpha-rename only schema visualization's ephemeral virtual entities.

    Preserve every label/property, endpoint, edge type and multiplicity. Lists
    of virtual entities are compared as schema sets, not meaningful list order.
    Ordinary database entities and all other corpus queries retain exact IDs.
    """
    record = json.loads(encoded)
    if set(record) != {"$map"} or {k for k, _ in record["$map"]} != {"nodes", "relationships"}:
        raise ValueError("Unexpected schema visualization shape")
    values = dict(record["$map"])
    nodes = values["nodes"]["$list"]
    relationships = values["relationships"]["$list"]
    keys = [json.dumps([n["labels"], n["properties"]], sort_keys=True) for n in nodes]
    if len(set(keys)) != len(keys):
        raise ValueError("Nonunique virtual schema node descriptions")
    mapping = {}
    ordered_nodes = []
    for index, (_, node) in enumerate(sorted(zip(keys, nodes), key=lambda pair: pair[0])):
        if set(node) != {"$node", "labels", "properties"} or not re.fullmatch(r"-\d+", node["$node"]):
            raise ValueError("Expected virtual schema node identity")
        mapping[node["$node"]] = f"schema-node-{index}"
        ordered_nodes.append({**node, "$node": mapping[node["$node"]]})
    edges = []
    for rel in relationships:
        if (set(rel) != {"$relationship", "start", "end", "type", "properties"}
                or not re.fullmatch(r"-\d+", rel["$relationship"])):
            raise ValueError("Expected virtual schema relationship identity")
        edges.append({k: mapping[v] if k in ("start", "end") else v
                      for k, v in rel.items() if k != "$relationship"})
    edges.sort(key=lambda edge: json.dumps(edge, sort_keys=True))
    # Occurrence IDs preserve duplicate virtual edges rather than collapsing them.
    edges = [{**edge, "$relationship": f"schema-edge-{i}"} for i, edge in enumerate(edges)]
    return json.dumps({"$map": [["nodes", {"$list": ordered_nodes}],
                                ["relationships", {"$list": edges}]]},
                       sort_keys=True, separators=(",", ":"))


def capture(iterator, *, schema_visualization=False):
    started, rows = time.perf_counter(), []
    try:
        for row in iterator:
            if len(rows) == CAP:
                raise RowLimit("Exceeded retained-row cap")
            rows.append(json.dumps(canonical(row), sort_keys=True, separators=(",", ":")))
        compared = [normalize_virtual_schema(row) for row in rows] if schema_visualization else rows
        result = {"status": "ok", "row_count": len(rows),
                  "comparison": "virtual_schema_structure" if schema_visualization else "exact",
                  "bag_sha256": digest(sorted(compared)), "sequence_sha256": digest(compared),
                  "raw_bag_sha256": digest(sorted(rows)), "raw_sequence_sha256": digest(rows)}
    # Conformance records unexpected conversion failures too, without aborting the corpus.
    except Exception as error:  # noqa: BLE001
        result = {"status": "error", "class": type(error).__name__,
                  "code": getattr(error, "code", None), "message": str(error)[:300]}
    finally:
        iterator.close()
    result["seconds"] = time.perf_counter() - started
    return result, rows


def aggregate(rows, inventory):
    by_id = {row["query_sha256"]: row for row in inventory}
    statuses, nonempty, mismatches, sequences, raw_matches = Counter(), Counter(), [], 0, 0
    for row in rows:
        if row.get("excluded_external_input"):
            statuses["excluded_external_input"] += 1
            continue
        a, b = row["adapter"], row["direct"]
        if a["status"] == b["status"] == "ok":
            statuses["joint_success"] += 1
            statuses["nonempty_success" if a["row_count"] else "empty_success"] += 1
            same = a["row_count"] == b["row_count"] and a["bag_sha256"] == b["bag_sha256"]
            sequences += a["sequence_sha256"] == b["sequence_sha256"]
            raw_matches += a.get("raw_bag_sha256", a["bag_sha256"]) == b.get("raw_bag_sha256", b["bag_sha256"])
            if same and a["row_count"]:
                nonempty.update(k for k, v in by_id[row["query_sha256"]]["indicators"].items() if v)
        else:
            statuses["joint_failure" if a["status"] == b["status"] else "one_path_failure"] += 1
            same = (a["status"] == b["status"] and a.get("class") == b.get("class")
                    and a.get("code") == b.get("code"))
        if not same:
            mismatches.append(row["query_sha256"])
    missing = sorted(set(REQUIRED) - set(nonempty))
    return {"counts": dict(statuses), "nonempty_indicator_coverage": dict(nonempty),
        "identical_sequences": sequences, "raw_identical_bags": raw_matches, "mismatches": mismatches,
        "missing_required_coverage": missing,
        "gate_passed": len(rows) == len(inventory) and not mismatches and not missing}


@contextmanager
def log_notifications(path):
    logger = logging.getLogger("neo4j.notifications")
    handler = logging.FileHandler(path, mode="x")
    previous_propagation = logger.propagate
    logger.addHandler(handler)
    logger.propagate = False
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.propagate = previous_propagation
        handler.close()


def execute(run, neo4j_home, java):
    from neo4j import GraphDatabase

    from orbweaver_query.neo4j import Neo4jSource

    run = Path(run)
    manifest = checked(run)
    inventory = json.loads((run / "inventory.json").read_text())
    write_json(run / "started.json", {"manifest_sha256": sha(run / "manifest.json")})
    rows = []
    # Retain server notifications in the run log instead of flooding the console.
    with (log_notifications(run / "notifications.log"),
          disposable_database(neo4j_home, java, transaction_timeout="5s") as uri,
          GraphDatabase.driver(uri, auth=None, warn_notification_severity=None) as driver):
        with driver.session() as connection:
            for statement in statements((run / "movies.cypher").read_text()):
                connection.run(statement).consume()
            fixture = connection.run("""MATCH (n) RETURN count(n) AS nodes,
                sum(COUNT { (n)-->() }) AS relationships,
                collect(DISTINCT labels(n)) AS labels""").single().data()
            fixture["property_keys"] = [row[0] for row in connection.run("CALL db.propertyKeys()")]
            server = connection.run("CALL dbms.components() YIELD name, versions, edition RETURN *").data()
        source = Neo4jSource(driver)
        with gzip.open(run / "raw-responses.jsonl.gz", "xt") as raw:
            for index, item in enumerate(inventory):
                row = {"query_sha256": item["query_sha256"]}
                if item["excluded_external_input"]:
                    row["excluded_external_input"] = True
                else:
                    is_schema = bool(re.fullmatch(r"CALL\s+db\.schema\.visualization\(\)\s*;?",
                                                  item["query"], re.IGNORECASE))
                    a, raw_a = capture(source.iter_candidates(item["query"]), schema_visualization=is_schema)
                    b, raw_b = capture(direct(driver, item["query"]), schema_visualization=is_schema)
                    row.update(adapter=a, direct=b)
                    raw.write(json.dumps({"query_sha256": item["query_sha256"],
                                          "adapter": raw_a, "direct": raw_b}) + "\n")
                rows.append(row)
                if (index+1) % 100 == 0:
                    print(f"Executed {index+1}/{len(inventory)} corpus queries", flush=True)
    result = {"manifest_sha256": sha(run / "manifest.json"), "fixture": fixture,
              "server": server, "source_rows": manifest["source_rows"], "queries": rows,
              "raw_responses_sha256": sha(run / "raw-responses.jsonl.gz"),
              "aggregate": aggregate(rows, inventory)}
    write_json(run / "results.json", result)
    return result["aggregate"]


def verify(run):
    run = Path(run)
    checked(run, current=False)
    result = json.loads((run / "results.json").read_text())
    inventory = json.loads((run / "inventory.json").read_text())
    if (sha(run / "manifest.json") != result["manifest_sha256"]
            or sha(run / "raw-responses.jsonl.gz") != result["raw_responses_sha256"]
            or [q["query_sha256"] for q in result["queries"]] != [q["query_sha256"] for q in inventory]):
        raise ValueError("Changed source/result inventory")
    by_id = {q["query_sha256"]: q for q in result["queries"]}
    seen = set()
    with gzip.open(run / "raw-responses.jsonl.gz", "rt") as stream:
        for line in stream:
            raw = json.loads(line)
            key = raw["query_sha256"]
            if key in seen:
                raise ValueError("Repeated raw response")
            seen.add(key)
            for arm in ("adapter", "direct"):
                row = by_id[key][arm]
                if row["status"] == "ok":
                    compared = ([normalize_virtual_schema(v) for v in raw[arm]]
                                if row["comparison"] == "virtual_schema_structure" else raw[arm])
                    if (len(raw[arm]) != row["row_count"]
                            or digest(raw[arm]) != row["raw_sequence_sha256"]
                            or digest(sorted(raw[arm])) != row["raw_bag_sha256"]
                            or digest(compared) != row["sequence_sha256"]
                            or digest(sorted(compared)) != row["bag_sha256"]):
                        raise ValueError("Raw results differ from reported output identity")
    if seen != {r["query_sha256"] for r in result["queries"] if not r.get("excluded_external_input")}:
        raise ValueError("Raw response inventory mismatch")
    if aggregate(result["queries"], inventory) != result["aggregate"]:
        raise ValueError("Recomputed aggregate/gate mismatch")
    receipt = {"verified": True, "results_sha256": sha(run / "results.json"),
               "gate_passed": result["aggregate"]["gate_passed"]}
    write_json(run / "verification.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "execute", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--parquet", type=Path)
    parser.add_argument("--neo4j-home", type=Path)
    parser.add_argument("--java", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        result = freeze(args.run, args.parquet)
    elif args.action == "execute":
        if args.neo4j_home is None or args.java is None:
            parser.error("execute requires --neo4j-home and --java")
        result = execute(args.run, args.neo4j_home, args.java)
    else:
        result = verify(args.run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
