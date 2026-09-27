"""Related films from a pinned public graph; uses only an owned temporary Neo4j."""

import argparse
import hashlib
import html
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from disposable_neo4j import disposable_database, native_runtime_identity
from text2cypher_execute import MOVIES_SHA, MOVIES_URL, statements

NODES = """
MATCH (n) WHERE n:Movie OR (n:Person AND EXISTS { (n)-[:ACTED_IN]->(:Movie) })
RETURN CASE WHEN n:Movie THEN 'movie:' + n.title ELSE 'person:' + n.name END AS id
ORDER BY id
"""
EDGES = """
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN DISTINCT 'person:' + p.name AS head, 'ACTED_IN' AS relation, 'movie:' + m.title AS target
ORDER BY head, target
"""
PAIRS = """
UNWIND range(0, size($titles)-1) AS ordinal
MATCH (h:Movie {title:$titles[ordinal]})<-[:ACTED_IN]-(p:Person)-[:ACTED_IN]->(t:Movie)
WHERE h <> t AND t.released >= $since
WITH DISTINCT ordinal, h, t, p
ORDER BY ordinal, t.title, p.name
"""
CANDIDATES = (
    PAIRS
    + """
WITH ordinal, h, t, collect(p.name) AS shared_names
RETURN ordinal, 'movie:' + h.title AS head, 'ACTED_IN' AS relation,
       'movie:' + t.title AS target, h.title AS source_title, t.title AS title,
       t.released AS released, shared_names
ORDER BY ordinal, title
"""
)
NATIVE = (
    PAIRS
    + """
WITH ordinal, h, t, collect(p) AS shared
WHERE size(shared) >= $minimum
WITH ordinal, h, t, shared,
     reduce(score=0.0, p IN shared |
       score + 1.0 / COUNT { MATCH (p)-[:ACTED_IN]->(m:Movie) RETURN DISTINCT m }) AS affinity
RETURN ordinal, 'movie:' + h.title AS head, 'ACTED_IN' AS relation,
       'movie:' + t.title AS target, h.title AS source_title, t.title AS title,
       t.released AS released, [p IN shared | p.name] AS shared_names,
       toFloat(size(shared)) AS shared_cast, affinity
ORDER BY ordinal, title
"""
)
PROJECTION = (
    "ordinal",
    "head",
    "relation",
    "target",
    "source_title",
    "title",
    "released",
    "shared_names",
    "shared_cast",
    "affinity",
)
DEFAULT_TITLES = ("The Matrix", "Top Gun", "Apollo 13")


def fetch_fixture(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "movies.cypher"
    if path.exists():
        raw = path.read_bytes()
    else:
        with urllib.request.urlopen(MOVIES_URL, timeout=60) as response:
            raw = response.read()
        if hashlib.sha256(raw).hexdigest() != MOVIES_SHA:
            raise ValueError("Upstream movie fixture changed; refusing to execute it")
        # Only a fully downloaded, validated fixture is placed in the cache.
        path.write_bytes(raw)
    if hashlib.sha256(raw).hexdigest() != MOVIES_SHA:
        raise ValueError("Cached movie fixture checksum mismatch")
    return path


def import_fixture(driver, path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != MOVIES_SHA:
        raise ValueError("Movie fixture checksum mismatch")
    with driver.session() as connection:
        for statement in statements(raw.decode()):
            connection.run(statement).consume()


def snapshot(source):
    return source.snapshot(
        nodes=NODES, edges=EDGES, relations=("ACTED_IN",), max_nodes=10000, max_edges=100000
    )


def make_plan(graph, minimum):
    from orbweaver_query import NeighborhoodModel, QueryPlan

    cn = NeighborhoodModel(relations=graph.relations, metric="common_neighbors")
    ra = NeighborhoodModel(relations=graph.relations, metric="resource_allocation")
    return (
        QueryPlan(graph)
        .predict("shared_cast", cn)
        .where_score("shared_cast", minimum)
        .predict("affinity", ra)
        .project(*PROJECTION)
    )


def prediction(score, graph_id, model):
    return {
        "score": score,
        "status": "scored",
        "snapshot_id": graph_id,
        "model_id": model.model_id,
        "score_kind": model.score_kind,
    }


def normalize_native(rows, graph_id, models):
    return [
        {
            **{k: row[k] for k in PROJECTION if k not in models},
            **{k: prediction(float(row[k]), graph_id, model) for k, model in models.items()},
        }
        for row in rows
    ]


def compare(left, right):
    """Check the full contract independently of the runtime's result objects."""
    import math

    if len(left) != len(right):
        raise ValueError("Reference and plan returned different row counts")
    for a, b in zip(left, right):
        a, b = dict(a), dict(b)
        for column in ("shared_cast", "affinity"):
            pa, pb = dict(a.pop(column)), dict(b.pop(column))
            va, vb = pa.pop("score"), pb.pop("score")
            if pa != pb or not math.isclose(va, vb, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("Reference and plan predictions differ")
        if a != b:
            raise ValueError("Reference and plan bindings/order differ")


def document(report):
    """Self-contained local report: no external scripts, fonts or network calls."""
    rows = report["records"]
    cards = []
    for ordinal, title in enumerate(report["parameters"]["titles"]):
        ranked = sorted(
            (r for r in rows if r["ordinal"] == ordinal),
            key=lambda r: (-r["affinity"]["score"], r["title"]),
        )
        items = "".join(
            "<tr><td>"
            + html.escape(r["title"])
            + "</td><td>"
            + str(r["released"])
            + "</td><td>"
            + f"{r['affinity']['score']:.3f}"
            + "</td><td>"
            + html.escape(", ".join(r["shared_names"]))
            + "</td></tr>"
            for r in ranked
        )
        cards.append(
            "<section><h2>Because you chose "
            + html.escape(title)
            + "</h2>"
            + (
                "<table><thead><tr><th>Related film</th><th>Year</th><th>Affinity</th>"
                "<th>Shared cast</th></tr></thead><tbody>" + items + "</tbody></table>"
                if items
                else "<p>No films meet the selected threshold.</p>"
            )
            + "</section>"
        )
    work, separate = report["work"], report["unfused_work"]
    saved = separate["expansions"] - work["expansions"]
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orbweaver Query · Movie night</title>
<style>body{font:16px/1.55 system-ui,sans-serif;background:#f4f2eb;color:#203230;max-width:1100px;margin:0 auto;padding:36px 24px}header{border-bottom:2px solid #203230;margin-bottom:28px}h1{font-size:44px;letter-spacing:-1.5px;margin:10px 0}h2{font-size:23px}small,.muted{color:#52635f}.badge{display:inline-block;background:#d8eadd;padding:5px 12px;border-radius:20px;font-size:13px}section{background:white;border:1px solid #d9dfd9;border-radius:12px;padding:22px;margin:20px 0;overflow:auto}table{border-collapse:collapse;width:100%;text-align:left}th,td{padding:10px 12px;border-bottom:1px solid #e3e7e3;vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}summary{cursor:pointer;font-weight:650}input{font:inherit;padding:10px;border:1px solid #899f98;border-radius:6px;width:min(360px,90%)}a{color:#17664f}.metric{font-size:28px;font-weight:700}footer{font-size:13px;margin-top:30px}</style>
<header><span class="badge">Public data · Local scoring · Development preview</span>
<h1>Movie night, with evidence.</h1><p>Find related films through shared cast, then inspect every ranking.</p></header>
<p>Affinity sums <code>1 / actor's film count</code> for each shared cast member in this fixture.
A less frequent cast member contributes more. This is a conventional structural score—not a
learned taste model, probability, or claim that you will enjoy a film.</p>
<label>Filter visible recommendations <input id="filter" placeholder="Film or cast member"></label>
"""
        + "".join(cards)
        + f"""
<section><h2>What the plan did</h2><p class="metric">{report["candidate_count"]} candidates → {len(rows)} matching rows</p>
<p>The composed plan shares neighborhood preparation between the cast-count filter and affinity score.
It built {work["expansions"]} source expansions versus {separate["expansions"]} with sharing disabled: {saved} fewer expansions.
Both plans and the independent native Cypher query return the same records within 1e-12.</p>
<p class="muted">These are work counts. This demonstration does not claim a speedup over Neo4j.
The separate end-to-end benchmark charges snapshot export, transfer and serialization.</p>
<details><summary>Inspect the physical plan and work</summary><pre>{html.escape(json.dumps({"plan": report["plan"], "work": work, "without_sharing": separate}, indent=2))}</pre></details>
<details><summary>Inspect the candidate Cypher</summary><pre>{html.escape(CANDIDATES)}</pre></details>
<details><summary>Data and snapshot identity</summary><pre>{html.escape(json.dumps(report["provenance"], indent=2))}</pre></details>
</section><footer>The graph includes only Movie, acting Person and ACTED_IN evidence. It is an intentionally small
Neo4j example, not a complete film database. Direction/type information is ignored by the two structural scorers.
JSON beside this file retains every row, plan and timing boundary. Results are ranked only for display;
the JSON retains candidate order and duplicate request identity.</footer>
<script>document.querySelector('#filter').addEventListener('input',e=>{{const q=e.target.value.toLocaleLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLocaleLowerCase().includes(q));}});</script></html>"""
    )


def run_demo(source, parameters):
    start = time.perf_counter()
    graph = snapshot(source)
    export_seconds = time.perf_counter() - start
    plan = make_plan(graph, parameters["minimum"])
    candidates = list(source.iter_candidates(CANDIDATES, parameters))
    result = plan.run(candidates)
    unfused = plan.run(candidates, fused=False)
    records = result.to_records()
    models = {p.name: p.model for p in plan.predictions}
    native = normalize_native(source.iter_candidates(NATIVE, parameters), graph.snapshot_id, models)
    compare(records, native)
    compare(records, unfused.to_records())
    return {
        "parameters": parameters,
        "candidate_count": len(candidates),
        "records": records,
        "work": result.report(),
        "unfused_work": unfused.report(),
        "plan": plan.explain(),
        "snapshot_export_seconds": export_seconds,
        "provenance": {
            "source_url": MOVIES_URL,
            "source_sha256": MOVIES_SHA,
            "snapshot_id": graph.snapshot_id,
            "nodes": len(graph.node_ids),
            "edges": len(graph.triples()),
            "evidence_relations": graph.relations,
            "score_kind": "conventional structural ranking; no fitted model",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neo4j-home", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--entrypoint", default="org.neo4j.server.Neo4jCommunity")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/orbweaver-query/movies")
    parser.add_argument("--output", type=Path, default=Path("movie-demo"))
    parser.add_argument(
        "--title", action="append", help="Repeat for multiple films; defaults to three examples"
    )
    parser.add_argument("--since", type=int, default=1990)
    parser.add_argument("--minimum-shared-cast", type=int, default=1)
    args = parser.parse_args()
    if args.minimum_shared_cast < 1:
        parser.error("--minimum-shared-cast must be positive")
    if args.output.exists():
        parser.error("Choose a new output directory; existing reports are never overwritten")
    identity = native_runtime_identity(args.java)
    fixture = fetch_fixture(args.cache)
    from neo4j import GraphDatabase
    from orbweaver_query.neo4j import Neo4jSource

    with disposable_database(args.neo4j_home, args.java, entrypoint=args.entrypoint) as uri:
        with GraphDatabase.driver(uri, auth=None) as driver:
            import_fixture(driver, fixture)
            params = {
                "titles": args.title or list(DEFAULT_TITLES),
                "since": args.since,
                "minimum": args.minimum_shared_cast,
            }
            available = {
                r["title"]
                for r in driver.execute_query("MATCH (m:Movie) RETURN m.title AS title")[0]
            }
            unknown = set(params["titles"]) - available
            if unknown:
                parser.error(f"Films absent from the public fixture: {sorted(unknown)}")
            report = run_demo(Neo4jSource(driver), params)
    report["runtime"] = identity
    args.output.mkdir(parents=True)
    (args.output / "results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (args.output / "index.html").write_text(document(report))
    print(
        f"Verified {len(report['records'])} matching rows from {report['candidate_count']} candidates."
    )
    print(f"Open {(args.output / 'index.html').resolve()}")


if __name__ == "__main__":
    main()
