"""Compare labeled application query sets with native Cypher in an owned database."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

QUERIES = {
    "supported": """MATCH (c:SciClaim)
        WHERE EXISTS { MATCH (c)-[r:CITES]->() WHERE r.label = 'SUPPORT' }
        RETURN c.id AS claim ORDER BY claim""",
    "uncontested": """MATCH (c:SciClaim)
        WHERE EXISTS { MATCH (c)-[r:CITES]->() WHERE r.label = 'SUPPORT' }
        AND NOT EXISTS { MATCH (c)-[r:CITES]->() WHERE r.label = 'CONTRADICT' }
        RETURN c.id AS claim ORDER BY claim""",
    "disagreement": """MATCH (c:SciClaim)-[a:CITES]->(d:SciDocument)<-[b:CITES]-(other:SciClaim)
        WHERE a.label = 'SUPPORT' AND b.label = 'CONTRADICT' AND c <> other
        RETURN DISTINCT c.id AS claim, d.id AS document, other.id AS other_claim
        ORDER BY claim, document, other_claim""",
}


def verify_graph(run, neo4j_home, java, *, prediction_folder="predictions", prediction_name="qwen3"):
    from neo4j import GraphDatabase

    if prediction_name in {"gold", "training_majority", "all_nei"}:
        raise ValueError("Prediction name collides with a reference arm")
    helper = Path(__file__).with_name("disposable_neo4j.py")
    helper_dir = (helper.parent if helper.is_file()
                  else Path(__file__).resolve().parents[4] / "packages/query/tools")
    sys.path.insert(0, str(helper_dir))
    from disposable_neo4j import disposable_database

    spec = importlib.util.spec_from_file_location("frozen_scifact", run / "scifact_reference.py")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    reference.verify(run)
    inputs, truth = reference.read(run / "inputs.json"), reference.read(run / "truth.json")
    raw = [reference.read(p) for p in sorted((run / prediction_folder).glob("*.json"))]
    if [r["index"] for r in raw] != list(range(len(inputs["edges"]))):
        raise ValueError("Incomplete inference output")
    labels = {"gold": truth["labels"], prediction_name: [r["label"] for r in raw],
              "training_majority": [truth["training_majority"]]*len(raw),
              "all_nei": [reference.LABELS[2]]*len(raw)}
    receipts = {}
    with (disposable_database(neo4j_home, java) as uri,
          GraphDatabase.driver(uri, auth=None) as driver):
        driver.execute_query("CREATE CONSTRAINT claim_id FOR (c:SciClaim) REQUIRE c.id IS UNIQUE")
        driver.execute_query("CREATE CONSTRAINT document_id FOR (d:SciDocument) REQUIRE d.id IS UNIQUE")
        driver.execute_query("UNWIND $ids AS id CREATE (:SciClaim {id:id})", ids=inputs["claims"])
        driver.execute_query("UNWIND $ids AS id CREATE (:SciDocument {id:id})",
                             ids=sorted({r["document_id"] for r in inputs["edges"]}))
        edges = [{"claim": r["claim_id"], "document": r["document_id"], "index": i}
                 for i, r in enumerate(inputs["edges"])]
        driver.execute_query("""UNWIND $rows AS row MATCH (c:SciClaim {id:row.claim}),
            (d:SciDocument {id:row.document}) CREATE (c)-[:CITES {index:row.index}]->(d)""", rows=edges)
        version = driver.execute_query("CALL dbms.components() YIELD versions RETURN versions").records[0]["versions"]
        for name, values in labels.items():
            driver.execute_query("""UNWIND $rows AS row MATCH ()-[r:CITES {index:row.index}]->()
                SET r.label = row.label""", rows=[{"index": i, "label": label} for i, label in enumerate(values)])
            actual = {}
            for shape, query in QUERIES.items():
                records = driver.execute_query(query).records
                actual[shape] = ([list(r.values()) for r in records] if shape == "disagreement"
                                 else [r["claim"] for r in records])
            if actual != reference.query_answers(inputs, values):
                raise ValueError(f"Native graph results differ for {name}")
            receipts[name] = {key: len(rows) for key, rows in actual.items()}
    result = {"native_queries_matched": len(labels)*len(QUERIES), "counts": receipts, "neo4j_versions": version,
              "manifest_sha256": reference.sha(run / "manifest.json"),
              "verifier_sha256": reference.sha(Path(__file__)), "queries": QUERIES}
    reference.write(run / "graph-verification.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--neo4j-home", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--prediction-folder", default="predictions")
    parser.add_argument("--prediction-name", default="qwen3")
    args = parser.parse_args()
    print(json.dumps(verify_graph(args.run, args.neo4j_home, args.java,
        prediction_folder=args.prediction_folder, prediction_name=args.prediction_name)))
