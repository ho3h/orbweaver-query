"""Opt-in integration against a disposable database supplied by the test runner."""

import os
import uuid

import numpy as np
import pytest

from orbweaver_query import (
    BindingCache,
    ExplicitPathModel,
    Limits,
    NeighborhoodModel,
    QueryPlan,
    Session,
)
from orbweaver_query.neo4j import Neo4jSource


@pytest.fixture
def database():
    uri = os.environ.get("ORBWEAVER_QUERY_TEST_URI")
    if not uri:
        pytest.skip("Set ORBWEAVER_QUERY_TEST_URI to a disposable Neo4j database")
    neo4j = pytest.importorskip("neo4j")
    driver = neo4j.GraphDatabase.driver(uri, auth=None)
    tag = str(uuid.uuid4())
    with driver.session() as connection:
        connection.run("UNWIND ['a','b','c','d'] AS id CREATE (:OrbQueryFixture {id:id, run:$run})",
                       run=tag).consume()
        connection.run("""UNWIND [['a','b'],['b','c'],['c','d']] AS pair
            MATCH (a:OrbQueryFixture {run:$run, id:pair[0]}),
                  (b:OrbQueryFixture {run:$run, id:pair[1]})
            CREATE (a)-[:REL]->(b)""", run=tag).consume()
    try:
        yield driver, tag
    finally:
        with driver.session() as connection:
            connection.run("MATCH (n:OrbQueryFixture {run:$run}) DETACH DELETE n", run=tag).consume()
        driver.close()


def test_live_export_query_scoring_and_readonly_guard(database):
    driver, tag = database
    source = Neo4jSource(driver, database="neo4j", fetch_size=2)
    graph = source.snapshot(
        nodes="MATCH (n:OrbQueryFixture {run:$run}) RETURN n.id AS id ORDER BY id",
        edges="""MATCH (a:OrbQueryFixture {run:$run})-[:REL]->(b:OrbQueryFixture {run:$run})
                 RETURN a.id AS head, 'REL' AS relation, b.id AS target""",
        relations=("REL",), parameters={"run": tag})
    weights = np.zeros((1, 16))
    weights[0, 0] = 2
    session = Session(graph, ExplicitPathModel(weights, relations=("REL",)))
    query = """MATCH (a:OrbQueryFixture {run:$run})-[:REL]->()-[:REL]->(b)
               RETURN a.id AS head, $kind AS relation, b.id AS target ORDER BY head"""
    result = source.score_pairs(session, query, {"run": tag, "kind": "REL"})
    assert [(row.binding["head"], row.binding["target"], row.score) for row in result.rows] == [
        ("a", "c", 2.0), ("b", "d", 2.0)]
    plan = (QueryPlan(graph).predict('path',session.model)
            .predict('ra',NeighborhoodModel(relations=graph.relations)).where_score('ra',.25)
            .project('head','target','path','ra'))
    cache = BindingCache()
    composed = source.run_plan(plan,query,{'run':tag,'kind':'REL'},cache=cache)
    assert [(r['head'],r['target'],r['path'].score,r['ra'].score) for r in composed.rows] == [
        ('a','c',2.,.5),('b','d',2.,.5)]
    repeated = source.run_plan(plan,query,{'run':tag,'kind':'REL'},cache=cache)
    assert repeated.to_records() == composed.to_records()
    assert repeated.report()['expansions'] == 0
    # Real server OPTIONAL MATCH semantics preserve the null before inference.
    nulls = source.score_pairs(session, """
        MATCH (a:OrbQueryFixture {run:$run, id:'d'})
        OPTIONAL MATCH (a)-[:REL]->(b)
        RETURN a.id AS head, $kind AS relation, b.id AS target
        """, {"run": tag, "kind": "REL"})
    assert len(nulls.rows) == 1 and nulls.rows[0].status == "null_input"
    with pytest.raises(ValueError, match="read-only"):
        list(source.iter_candidates("CREATE (:OrbQueryFixture {run:$run, id:'forbidden'})",
                                     {"run": tag}))
    with pytest.raises(ValueError, match='read-only'):
        source.run_plan(plan,'CREATE (:OrbQueryFixture {run:$run, id:"forbidden"})',{'run':tag})
    with driver.session() as connection:
        count = connection.run("MATCH (n:OrbQueryFixture {run:$run}) RETURN count(n) AS n",
                               run=tag).single()["n"]
    assert count == 4


def test_live_prediction_dependent_expansion_matches_native_cypher(database):
    driver, tag = database
    source = Neo4jSource(driver, fetch_size=2)
    graph = source.snapshot(
        nodes="MATCH (n:OrbQueryFixture {run:$run}) RETURN n.id AS id ORDER BY id",
        edges="""MATCH (a:OrbQueryFixture {run:$run})-[:REL]->(b:OrbQueryFixture {run:$run})
                 RETURN a.id AS head, 'REL' AS relation, b.id AS target""",
        relations=("REL",), parameters={"run": tag})
    cn = NeighborhoodModel(relations=graph.relations, metric="common_neighbors")
    plan = (QueryPlan(graph)
            .expand(source="seed", target="next", direction="both", optional=True)
            .predict("keep", cn, target="seed").where_score("keep", 1)
            .project("ordinal", "head", "seed", "next", "keep"))
    parameters = {"run": tag, "seeds": ["c", "d", "c"]}
    candidates = """UNWIND range(0, size($seeds)-1) AS ordinal
        RETURN ordinal, 'a' AS head, 'REL' AS relation, $seeds[ordinal] AS seed
        ORDER BY ordinal"""
    optimized = source.run_plan(plan, candidates, parameters)
    eager = source.run_plan(plan, candidates, parameters, optimize=False)
    assert optimized.to_records() == eager.to_records()
    native = list(source.iter_candidates("""
        UNWIND range(0, size($seeds)-1) AS ordinal
        MATCH (head:OrbQueryFixture {run:$run, id:'a'}),
              (seed:OrbQueryFixture {run:$run, id:$seeds[ordinal]})
        CALL {
            WITH head, seed
            MATCH (head)-[:REL]-(common)-[:REL]-(seed)
            RETURN count(DISTINCT common) AS score
        }
        WITH ordinal, head, seed, score WHERE score >= 1
        OPTIONAL MATCH (seed)-[:REL]-(next:OrbQueryFixture {run:$run})
        RETURN ordinal, head.id AS head, seed.id AS seed, next.id AS next, score
        ORDER BY ordinal, next
        """, parameters))
    actual = [{**{k: row[k] for k in ("ordinal", "head", "seed", "next")},
               "score": row["keep"].score} for row in optimized.rows]
    assert actual == native
    assert len(actual) == 4
    assert optimized.report()["edge_visits"] < eager.report()["edge_visits"]
    # The adapter's existing generator cleanup also applies to pipeline results.
    batches = source.iter_run_plan(plan, candidates, parameters)
    assert next(batches).rows
    batches.close()
    with pytest.raises(ValueError, match="read-only"):
        source.run_plan(plan, "CREATE (:OrbQueryFixture {run:$run})", parameters)


def test_live_target_coalescing_preserves_native_expansion_and_model_answers(database):
    driver, tag = database
    with driver.session() as connection:
        connection.run("""UNWIND ['e','f','g'] AS id
            MATCH (c:OrbQueryFixture {run:$run, id:'c'})
            CREATE (c)-[:REL]->(:OrbQueryFixture {id:id, run:$run})""", run=tag).consume()
    source = Neo4jSource(driver, fetch_size=2)
    graph = source.snapshot(
        nodes="MATCH (n:OrbQueryFixture {run:$run}) RETURN n.id AS id ORDER BY id",
        edges="""MATCH (a:OrbQueryFixture {run:$run})-[:REL]->(b:OrbQueryFixture {run:$run})
                 RETURN a.id AS head, 'REL' AS relation, b.id AS target""",
        relations=("REL",), parameters={"run": tag})
    weights = np.zeros((1, 16))
    weights[0, 0] = 2
    model = ExplicitPathModel(weights, relations=graph.relations)
    plan = (QueryPlan(graph, limits=Limits(window_size=2))
            .expand(source="seed", target="next", direction="both")
            .predict("path", model, target="next").project("next", "path"))
    candidates = "RETURN 'a' AS head, 'REL' AS relation, 'c' AS seed"
    coalesced = source.run_plan(plan, candidates)
    prefix = source.run_plan(plan, candidates, coalesce_targets=False)
    assert coalesced.to_records() == prefix.to_records()
    native = list(source.iter_candidates("""
        MATCH (:OrbQueryFixture {run:$run, id:'c'})-[:REL]-(n:OrbQueryFixture {run:$run})
        RETURN n.id AS next ORDER BY next""", {"run": tag}))
    assert [{"next": r["next"]} for r in coalesced.rows] == native
    assert [r["path"].status for r in coalesced.rows] == ["unsupported", *["scored"] * 4]
    work = coalesced.report()
    assert work["target_preparation_builds"] == 1 and work["target_preparation_hits"] > 0
    assert work["type_visits"] < prefix.report()["type_visits"]
