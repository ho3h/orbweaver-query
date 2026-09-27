"""Public recipes preserve data IDs, result meaning and the strong native boundary."""

import importlib.util
import sys
from pathlib import Path

import pytest

from orbweaver_query import GraphSnapshot, NeighborhoodModel, Session, score_bindings


def module(name, folder="examples"):
    path = Path(__file__).parents[1] / folder / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def csv_fixture(tmp_path):
    values = {
        "nodes.csv": "id\n001\n002\n003\n004\n",
        "edges.csv": "head,relation,target\n001,R,002\n002,R,003\n",
        "candidates.csv": "head,relation,target,request_id\n001,R,003,one\n001,R,004,zero\n001,R,002,adjacent\n001,R,,null\n001,R,003,repeat\n",
    }
    for name, value in values.items():
        (tmp_path / name).write_text(value)
    return [tmp_path / name for name in values]


def test_csv_recipe_preserves_string_ids_nulls_zero_and_duplicate_requests(tmp_path):
    recipe = module("score_csv")
    nodes, edges, candidates = csv_fixture(tmp_path)
    graph = recipe.load_graph(nodes, edges, ("R",))
    assert graph.node_ids == ("001", "002", "003", "004")
    session = Session(graph, NeighborhoodModel(relations=("R",)))
    rows = score_bindings(session, recipe.candidate_rows(candidates)).to_records()
    assert [r["prediction"]["score"] for r in rows] == [0.5, 0.0, None, None, 0.5]
    assert [r["prediction"]["status"] for r in rows] == [
        "scored",
        "scored",
        "unsupported",
        "null_input",
        "scored",
    ]
    assert [r["request_id"] for r in rows] == ["one", "zero", "adjacent", "null", "repeat"]


def test_csv_recipe_rejects_bad_headers_unknown_evidence_and_limits(tmp_path):
    recipe = module("score_csv")
    nodes, edges, candidates = csv_fixture(tmp_path)
    with pytest.raises(ValueError, match="max_nodes"):
        recipe.load_graph(nodes, edges, ("R",), max_nodes=2)
    with pytest.raises(ValueError, match="max_edges"):
        recipe.load_graph(nodes, edges, ("R",), max_edges=1)
    with pytest.raises(ValueError, match="undeclared"):
        recipe.load_graph(nodes, edges, ("OTHER",))
    candidates.write_text("head,head,target\na,b,c\n")
    with pytest.raises(ValueError):
        list(recipe.candidate_rows(candidates))
    candidates.write_text("head,relation,target\na,R\n")
    with pytest.raises(ValueError, match="header"):
        list(recipe.candidate_rows(candidates))


def movie_fixture():
    # Two movie pairs share cast; one candidate has no shared cast. Duplicate input
    # requests must survive and min-cast filters must apply consistently.
    graph = GraphSnapshot(
        [(3, 0, 0), (3, 0, 1), (4, 0, 0), (4, 0, 1), (4, 0, 2)],
        node_ids=("movie:a", "movie:b", "movie:c", "person:x", "person:y"),
        relations=("ACTED_IN",),
    )
    rows = [
        {
            "ordinal": i,
            "head": "movie:a",
            "relation": "ACTED_IN",
            "target": target,
            "source_title": "a",
            "title": target[6:],
            "released": 2001,
            "shared_names": ["x", "y"] if target == "movie:b" else ["y"],
        }
        for i, target in enumerate(("movie:b", "movie:c", "movie:b"))
    ]
    return graph, rows


def test_movie_manual_and_shared_full_controls_preserve_bags_and_thresholds():
    workflow = module("movie_workflow", "benchmarks")
    graph, rows = movie_fixture()
    adj = [set(map(int, graph.neighbors(i))) for i in range(len(graph.node_ids))]
    for minimum in (1, 2, 3):
        plan = workflow.make_plan(graph, minimum)
        expected = plan.run(rows).to_records()
        for kwargs in ({"adj": adj}, {"full": True}):
            actual = workflow.manual_scores(graph, rows, workflow.models(), minimum, **kwargs)
            workflow.compare(expected, actual)
        assert len(expected) == {1: 3, 2: 2, 3: 0}[minimum]
        workflow.compare(expected, plan.run(rows, fused=False).to_records())


def test_movie_comparison_detects_score_provenance_order_and_multiplicity_changes():
    movie = module("movie_recommendations")
    graph, rows = movie_fixture()
    expected = movie.make_plan(graph, 1).run(rows).to_records()
    import copy

    for change in ("score", "provenance", "order", "bag"):
        bad = copy.deepcopy(expected)
        if change == "score":
            bad[0]["affinity"]["score"] += 0.01
        elif change == "provenance":
            bad[0]["affinity"]["snapshot_id"] = "different"
        elif change == "order":
            bad.reverse()
        else:
            bad.pop()
        with pytest.raises(ValueError):
            movie.compare(expected, bad)


def test_movie_download_refuses_changed_cache(tmp_path):
    movie = module("movie_recommendations")
    (tmp_path / "movies.cypher").write_text("CREATE (:Changed)")
    with pytest.raises(ValueError, match="checksum"):
        movie.fetch_fixture(tmp_path)


def test_movie_report_escapes_untrusted_titles_and_names():
    movie = module("movie_recommendations")
    graph, rows = movie_fixture()
    rows[0]["title"] = "<script>alert(1)</script>"
    rows[0]["shared_names"] = ["<img src=x onerror=alert(1)>"]
    plan = movie.make_plan(graph, 1)
    result = plan.run(rows)
    report = {
        "parameters": {"titles": ["<script>source</script>", "a", "a"]},
        "records": result.to_records(),
        "work": result.report(),
        "candidate_count": len(rows),
        "unfused_work": plan.run(rows, fused=False).report(),
        "plan": plan.explain(),
        "provenance": {"fixture": "public test"},
    }
    html = movie.document(report)
    assert "<script>alert(1)</script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
