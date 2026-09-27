from types import SimpleNamespace

import numpy as np
import pytest

from orbweaver_query import (
    BindingCache,
    ExplicitPathModel,
    GraphSnapshot,
    Limits,
    NeighborhoodModel,
    QueryPlan,
    ResourceLimitError,
    Session,
    score_bindings,
)
from orbweaver_query.neo4j import Neo4jSource


def runtime():
    graph = GraphSnapshot([[0, 0, 1], [1, 0, 2], [2, 0, 3]],
                           node_ids=("a", "b", "c", "d"), relations=("r",))
    weights = np.zeros((1, 16))
    weights[0, 0] = 2
    return Session(graph, ExplicitPathModel(weights, relations=("r",)),
                   limits=Limits(window_size=2))


def test_candidate_selection_never_crops_evidence_and_preserves_nulls_duplicates():
    session = runtime()
    inputs = [{"head": "a", "relation": "r", "target": t, "row": i}
              for i, t in enumerate(("c", "b", "c", None))]
    result = score_bindings(session, inputs)
    assert [row.score for row in result.rows] == [2.0, None, 2.0, None]
    assert [row.status for row in result.rows] == ["scored", "unsupported", "scored", "null_input"]
    assert [row.binding["row"] for row in result.rows] == [0, 1, 2, 3]
    only_c = score_bindings(session, inputs[:1])
    assert only_c.rows[0].score == result.rows[0].score
    # b is excluded as output but is still required evidence for the a -> c path.
    assert session.graph.node_ids == ("a", "b", "c", "d")
    filtered = result.where_score(2)
    assert [row.binding["row"] for row in filtered.rows] == [0, 2]
    assert filtered.to_records()[0]["prediction"]["score_kind"] == "ranking_logit"
    with pytest.raises(ValueError, match="collides"):
        result.to_records(prediction_column="row")
    with pytest.raises(ValueError):
        result.where_score(float("nan"))
    with pytest.raises(TypeError):
        result.rows[0].binding["head"] = "changed"


def test_invalid_candidate_shapes_and_unknown_endpoints_fail():
    session = runtime()
    for row in ({"head": "a"}, {"head": "a", "relation": "r", "target": "missing"},
                {"head": "a", "relation": "r", "target": 1}):
        with pytest.raises(ValueError):
            score_bindings(session, [row])


def test_projection_keeps_bags_nulls_provenance_and_filter_composition():
    inputs = [{"head": "a", "relation": "r", "target": t, "row": i}
              for i, t in enumerate(("c", None, "c"))]
    original = score_bindings(runtime(), inputs)
    projected = original.project("head", "target")
    assert [dict(row.binding) for row in projected.rows] == [
        {"head": "a", "target": "c"}, {"head": "a", "target": None},
        {"head": "a", "target": "c"}]
    assert [r.score for r in projected.rows] == [2, None, 2]
    assert [r.model_id for r in projected.rows] == [r.model_id for r in original.rows]
    assert [r.snapshot_id for r in projected.rows] == [r.snapshot_id for r in original.rows]
    assert original.where_score(2).project("head", "target").to_records() == projected.where_score(2).to_records()
    assert len(original.project().to_records()) == 3
    assert set(original.project().to_records()[0]) == {"prediction"}
    with pytest.raises(ValueError, match="missing"):
        original.project("absent")
    with pytest.raises(ValueError, match="distinct"):
        original.project("head", "head")


class Cursor:
    def __init__(self, rows=(), query_type="r"):
        self.rows, self.query_type = rows, query_type

    def __iter__(self):
        return iter(self.rows)

    def consume(self):
        return SimpleNamespace(query_type=self.query_type)


class Transaction:
    def __init__(self, responses, calls):
        self.responses, self.calls, self.closed = responses, calls, False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def run(self, query, params):
        self.calls.append((query, params))
        return self.responses[query]


class Connection:
    def __init__(self, transaction):
        self.transaction, self.closed = transaction, False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def begin_transaction(self):
        return self.transaction


class Driver:
    def __init__(self, responses):
        self.calls = []
        self.transaction = Transaction(responses, self.calls)
        self.connection = Connection(self.transaction)

    def session(self, **kwargs):
        assert kwargs["default_access_mode"] == "READ"
        return self.connection


def test_cypher_parameters_readonly_guard_and_lifecycle():
    query = "MATCH (a) RETURN a.id AS head, $r AS relation, 'c' AS target"
    driver = Driver({"EXPLAIN " + query: Cursor(), query: Cursor([
        {"head": "a", "relation": "r", "target": "c"}])})
    source = Neo4jSource(driver)
    result = source.score_pairs(runtime(), query, {"r": "r"})
    assert result.rows[0].score == 2
    assert driver.calls == [("EXPLAIN " + query, {"r": "r"}), (query, {"r": "r"})]
    assert driver.transaction.closed and driver.connection.closed
    writing = Driver({"EXPLAIN CREATE (n)": Cursor(query_type="w")})
    with pytest.raises(ValueError, match="read-only"):
        list(Neo4jSource(writing).iter_candidates("CREATE (n)"))
    assert writing.calls == [("EXPLAIN CREATE (n)", {})]
    assert writing.connection.closed


def test_evidence_export_is_independent_and_rejects_partial_endpoints():
    nodes, edges = "MATCH (n) RETURN n.id AS id", "MATCH (a)-[r]->(b) RETURN a,r,b"
    responses = {"EXPLAIN " + nodes: Cursor(), "EXPLAIN " + edges: Cursor(),
                 nodes: Cursor([{"id": k} for k in ("a", "b", "c", "d")]),
                 edges: Cursor([{"head": "a", "relation": "r", "target": "b"},
                                {"head": "b", "relation": "r", "target": "c"},
                                {"head": "c", "relation": "r", "target": "d"}])}
    snapshot = Neo4jSource(Driver(responses)).snapshot(nodes=nodes, edges=edges, relations=("r",))
    assert snapshot.snapshot_id == runtime().graph.snapshot_id
    responses[edges] = Cursor([{"head": "a", "relation": "r", "target": "outside"}])
    with pytest.raises(ValueError, match="undeclared"):
        Neo4jSource(Driver(responses)).snapshot(nodes=nodes, edges=edges, relations=("r",))


def test_stream_close_releases_database_transaction():
    query = "RETURN 'a' AS head, 'r' AS relation, 'c' AS target"
    driver = Driver({"EXPLAIN " + query: Cursor(), query: Cursor([
        {"head": "a", "relation": "r", "target": "c"}] * 9)})
    stream = Neo4jSource(driver).iter_score_pairs(runtime(), query)
    assert len(next(stream).rows) == 2
    assert not driver.connection.closed
    stream.close()
    assert driver.transaction.closed and driver.connection.closed


def test_composed_cypher_plans_preserve_rows_cache_and_transaction_lifecycle():
    session = runtime()
    query = 'RETURN $head AS head, $relation AS relation, wanted AS target'
    rows = [{'head':'a','relation':'r','target':t} for t in ('c','c',None,'b','d')]
    plan = (QueryPlan(session.graph, limits=session.limits).predict('path',session.model)
            .predict('ra',NeighborhoodModel(relations=session.graph.relations))
            .where_score('ra',.25).project('target','path','ra'))
    cache = BindingCache()
    for warm in (False,True):
        driver = Driver({'EXPLAIN '+query:Cursor(),query:Cursor(rows)})
        result = Neo4jSource(driver).run_plan(plan,query,{'head':'a','relation':'r'},cache=cache)
        assert result.to_records() == plan.run(rows).to_records()
        assert [r['target'] for r in result.rows] == ['c','c']
        assert driver.transaction.closed and driver.connection.closed
        assert driver.calls[1] == (query,{'head':'a','relation':'r'})
        if warm:
            assert result.report()['expansions'] == result.report()['model_calls'] == 0
    driver = Driver({'EXPLAIN '+query:Cursor(),query:Cursor(rows)})
    stream = Neo4jSource(driver).iter_run_plan(plan,query)
    assert len(next(stream).rows)==2
    assert not driver.connection.closed
    stream.close()
    assert driver.transaction.closed and driver.connection.closed


def test_composed_cypher_plan_errors_close_reads_and_never_execute_writes():
    session = runtime()
    plan = QueryPlan(session.graph,limits=Limits(max_type_visits=1)).predict('p',session.model)
    query = "RETURN 'a' AS head, 'r' AS relation, 'c' AS target"
    for streamed in (False,True):
        driver = Driver({'EXPLAIN '+query:Cursor(),query:Cursor([
            {'head':'a','relation':'r','target':'c'}])})
        source = Neo4jSource(driver)
        with pytest.raises(ResourceLimitError):
            if streamed:
                list(source.iter_run_plan(plan,query))
            else:
                source.run_plan(plan,query)
        assert driver.transaction.closed and driver.connection.closed
    writing = Driver({'EXPLAIN CREATE (n)':Cursor(query_type='w')})
    with pytest.raises(ValueError,match='read-only'):
        Neo4jSource(writing).run_plan(plan,'CREATE (n)')
    assert writing.calls == [('EXPLAIN CREATE (n)',{})]
    assert writing.transaction.closed and writing.connection.closed
    for method in ('run_plan','iter_run_plan'):
        with pytest.raises(TypeError,match='QueryPlan'):
            result = getattr(Neo4jSource(writing),method)(None,query)
            if method.startswith('iter_'):
                next(result)
