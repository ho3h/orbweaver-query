"""Check path execution on a second public graph family with an independent oracle."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request

from disposable_neo4j import disposable_database
from text2cypher_execute import MOVIES_SHA, MOVIES_URL, statements


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(run):
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[1]
    with urllib.request.urlopen(MOVIES_URL, timeout=60) as response:
        script = response.read()
    if hashlib.sha256(script).hexdigest() != MOVIES_SHA:
        raise ValueError("Changed public fixture")
    (run / "movies.cypher").write_bytes(script)
    source = run / "source"
    source.mkdir()
    for name in ("public_movies_check.py", "disposable_neo4j.py", "text2cypher_execute.py", "text2cypher_audit.py"):
        shutil.copyfile(package / "tools" / name, source / name)
    shutil.copyfile(package / "benchmarks" / "cache_reference.py", source / "cache_reference.py")
    shutil.copytree(package / "src" / "orbweaver_query", source / "orbweaver_query",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    files = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob("*")) if p.is_file()}
    manifest = {"format": "orbweaver-public-movies-check-v1", "files": files,
        "fixture_url": MOVIES_URL, "fixture_sha256": MOVIES_SHA,
        "coefficient_seed": 81720, "source_selection_seed": 20260927,
        "coefficient_standard_deviation": .05, "oracle_random_sources": 16,
        "oracle_high_degree_sources": 4, "atol": 1e-12, "rtol": 1e-12,
        "scope": "Runtime correctness on a different graph/schema; random test coefficients have no predictive-quality claim"}
    write(run / "manifest.json", manifest)
    return {"manifest_sha256": sha(run / "manifest.json"), "scope": manifest["scope"]}


def checked(run):
    m = json.loads((run / "manifest.json").read_text())
    if m["format"] != "orbweaver-public-movies-check-v1":
        raise ValueError("Wrong fixture check format")
    for name, identity in m["files"].items():
        if sha(run / name) != identity:
            raise ValueError("Frozen source/fixture changed")
    return m


def brute_features(adj, head, r):
    """Enumerate separate individual walks; never merge prefix states."""
    import numpy as np

    paths = [(head, (), 1.)]
    terminal = defaultdict(lambda: defaultdict(float))
    excluded = {head, *adj[head]}
    for length in (1, 2, 3):
        following = []
        for node, sequence, mass in paths:
            for target, symbols in sorted(adj[node].items()):
                for symbol in sorted(symbols):
                    path = (*sequence, symbol)
                    value = mass / len(adj[node]) / len(symbols)
                    following.append((target, path, value))
                    if length >= 2 and target not in excluded:
                        terminal[target][path] += value * (2/3 if length == 2 else 1/3)
        paths = following
    candidates = sorted(terminal)
    x = np.zeros((len(candidates), 4 + (2*r)**2 + (2*r)**3))
    for i, target in enumerate(candidates):
        features = terminal[target]
        mass = sum(features.values())
        short = sum(value for path, value in features.items() if len(path) == 2)
        x[i, :4] = (1, np.log(mass), np.log1p(len(adj[target])), short/mass)
        for sequence, value in features.items():
            code = 0
            for symbol in sequence:
                code = code*2*r + symbol
            x[i, 4 + (0 if len(sequence) == 2 else (2*r)**2) + code] = value/mass
    return np.array(candidates), x


def check_model(graph, model, manifest):
    import numpy as np
    from cache_reference import lru_predict
    from orbweaver_query import Limits, LinkQuery, Session

    r = len(graph.relations)
    adj = [defaultdict(set) for _ in graph.node_ids]
    for h, relation, t in graph.triples():
        adj[int(h)][int(t)].add(int(relation))
        adj[int(t)][int(h)].add(int(relation)+r)
    rng = np.random.default_rng(manifest["source_selection_seed"])
    random = rng.choice(len(adj), manifest["oracle_random_sources"], replace=False)
    hubs = np.lexsort((np.arange(len(adj)), -graph.degree))
    heads = sorted(set(random.tolist()) | set(hubs[:manifest["oracle_high_degree_sources"]].tolist()))
    max_error, pairs = 0., 0
    for head in heads:
        expected_candidates, expected_x = brute_features(adj, head, r)
        actual = model.expand(graph, head, Limits())
        np.testing.assert_array_equal(actual.candidates, expected_candidates)
        for relation in range(r):
            expected = expected_x @ model.coefficient[relation]
            scores = model.score(actual, relation)
            np.testing.assert_allclose(scores, expected, atol=manifest["atol"], rtol=manifest["rtol"])
            max_error = max(max_error, float(np.max(np.abs(scores-expected), initial=0)))
            pairs += len(scores)
    sources = rng.choice(len(adj), 128, replace=False)
    clustered = [LinkQuery(graph.node_ids[h], relation) for h in sources[:32] for relation in graph.relations]
    workloads = {
        "distinct128": [LinkQuery(graph.node_ids[h], graph.relations[i % r]) for i, h in enumerate(sources)],
        "clustered192": clustered,
        "interleaved192": [LinkQuery(graph.node_ids[h], relation) for relation in graph.relations for h in sources[:32]],
        "hubs16": [LinkQuery(graph.node_ids[h], graph.relations[i % r]) for i, h in enumerate(hubs[:16])],
    }
    session = Session(graph, model)
    reports = {}
    for name, queries in workloads.items():
        outputs, work = {}, {}
        for strategy in ("independent", "consecutive", "grouped", "lru"):
            if strategy == "lru":
                rows, stats = lru_predict(session, queries)
            else:
                result = session.run(queries, strategy=strategy)
                rows = result.rows
                stats = {k: result.report()[k] for k in ("expansions", "model_calls", "type_visits", "peak_feature_bytes")}
            payload = [{"head": row.query.head, "relation": row.query.relation,
                        "candidates": row.candidate_ids, "scores": row.scores.tolist()} for row in rows]
            outputs[strategy] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            work[strategy] = stats
        if len(set(outputs.values())) != 1:
            raise ValueError("Strategy outputs differ on movies graph")
        reports[name] = {"queries": len(queries), "output_sha256": outputs["grouped"], "work": work}
    return {"oracle_sources": heads, "oracle_score_pairs": pairs, "max_absolute_error": max_error,
            "workloads": reports, "passed": True}


def execute(run, neo4j_home, java):
    manifest = checked(run)
    write(run / "started.json", {"manifest_sha256": sha(run / "manifest.json")})
    sys.path.insert(0, str(run / "source"))
    import numpy as np
    from neo4j import GraphDatabase
    from orbweaver_query import ExplicitPathModel
    from orbweaver_query.neo4j import Neo4jSource

    with disposable_database(neo4j_home, java) as uri:
        with GraphDatabase.driver(uri, auth=None) as driver:
            with driver.session() as connection:
                for statement in statements((run / "movies.cypher").read_text()):
                    connection.run(statement).consume()
                relations = sorted(row[0] for row in connection.run("MATCH ()-[r]->() RETURN DISTINCT type(r)"))
            source = Neo4jSource(driver)
            graph = source.snapshot(
                nodes="""MATCH (n) RETURN CASE WHEN n:Person THEN 'p:' + n.name ELSE 'm:' + n.title END AS id ORDER BY id""",
                edges="""MATCH (a)-[r]->(b)
                    RETURN CASE WHEN a:Person THEN 'p:' + a.name ELSE 'm:' + a.title END AS head,
                    type(r) AS relation,
                    CASE WHEN b:Person THEN 'p:' + b.name ELSE 'm:' + b.title END AS target""",
                relations=relations)
    if len(relations) != 6:
        raise ValueError("Fixture relation count differs from predeclared 192-query workloads")
    r = len(relations)
    weights = np.random.default_rng(manifest["coefficient_seed"]).normal(
        0, manifest["coefficient_standard_deviation"], size=(r, 4+(2*r)**2+(2*r)**3))
    model = ExplicitPathModel(weights, relations=relations)
    graph.save(run / "graph.npz")
    model.save(run / "test-model.npz")
    report = {"manifest_sha256": sha(run / "manifest.json"), "scope": manifest["scope"],
        "nodes": len(graph.node_ids), "edges": len(graph.triples()), "relations": relations,
        "max_neighbor_degree": int(graph.degree.max()), "graph_id": graph.snapshot_id,
        "model_id": model.model_id, "checks": check_model(graph, model, manifest),
        "artifacts": {name: sha(run / name) for name in ("graph.npz", "test-model.npz")}}
    write(run / "results.json", report)
    return {k: report[k] for k in ("nodes", "edges", "relations", "max_neighbor_degree", "checks")}


def verify(run):
    manifest = checked(run)
    report = json.loads((run / "results.json").read_text())
    sys.path.insert(0, str(run / "source"))
    from orbweaver_query import ExplicitPathModel, GraphSnapshot

    if report["manifest_sha256"] != sha(run / "manifest.json"):
        raise ValueError("Manifest/report mismatch")
    for name, identity in report["artifacts"].items():
        if sha(run / name) != identity:
            raise ValueError("Changed graph/model artifact")
    graph, model = GraphSnapshot.load(run / "graph.npz"), ExplicitPathModel.load(run / "test-model.npz")
    if graph.snapshot_id != report["graph_id"] or model.model_id != report["model_id"]:
        raise ValueError("Context identity mismatch")
    if check_model(graph, model, manifest) != report["checks"]:
        raise ValueError("Independent replay differs")
    receipt = {"verified": True, "results_sha256": sha(run / "results.json"), "passed": True}
    write(run / "verification.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "execute", "verify"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--neo4j-home", type=Path)
    parser.add_argument("--java", type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    if args.action == "freeze":
        result = freeze(run)
    elif args.action == "execute":
        result = execute(run, args.neo4j_home, args.java)
    else:
        result = verify(run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
