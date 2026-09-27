"""Independent path enumeration and semantic boundary checks."""

import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from orbweaver_query import (
    ExplicitPathModel,
    GraphSnapshot,
    Limits,
    LinkQuery,
    ResourceLimitError,
    Session,
)


def fixture(seed=1, n=9, r=3):
    rng = np.random.default_rng(seed)
    edges = np.array([(h, k, t) for h in range(n) for t in range(n)
                      for k in range(r) if h != t and rng.random() < .10], dtype=np.int64)
    edges = edges.reshape(-1, 3)
    relations = tuple(f"r{i}" for i in range(r))
    graph = GraphSnapshot(edges, node_ids=[f"n{i}" for i in range(n)], relations=relations)
    model = ExplicitPathModel(rng.normal(size=(r, 4 + (2*r)**2 + (2*r)**3)),
                              relations=relations)
    return edges, graph, model


def enumerate_reference(edges, n, r, head, relation, coefficient):
    """Enumerate individual walks, without the runtime's merged prefix states."""
    neighbors = [defaultdict(set) for _ in range(n)]
    for h, k, t in edges:
        neighbors[int(h)][int(t)].add(int(k))
        neighbors[int(t)][int(h)].add(int(k) + r)
    paths, terminal = [(head, (), 1.0)], defaultdict(lambda: defaultdict(float))
    excluded = {head, *neighbors[head]}
    for depth in range(1, 4):
        following = []
        for node, symbols, mass in paths:
            for dest, types in sorted(neighbors[node].items()):
                for symbol in sorted(types):
                    next_mass = mass / len(neighbors[node]) / len(types)
                    sequence = (*symbols, symbol)
                    following.append((dest, sequence, next_mass))
                    if depth >= 2 and dest not in excluded:
                        terminal[dest][sequence] += (2/3 if depth == 2 else 1/3) * next_mass
        paths = following
    output = {}
    for node, features in terminal.items():
        mass = sum(features.values())
        two_mass = sum(value for path, value in features.items() if len(path) == 2)
        row = np.zeros(coefficient.shape[1])
        row[:4] = (1, np.log(mass), np.log1p(len(neighbors[node])), two_mass / mass)
        for path, value in features.items():
            code = 0
            for symbol in path:
                code = code * 2*r + symbol
            row[4 + (0 if len(path) == 2 else (2*r)**2) + code] += value / mass
        output[f"n{node}"] = float(row @ coefficient[relation])
    return output


@pytest.mark.parametrize("seed", range(12))
def test_exact_scores_against_independent_walk_enumeration(seed):
    edges, graph, model = fixture(seed)
    queries = [LinkQuery(f"n{h}", f"r{r}") for r in range(3) for h in range(9)]
    result = Session(graph, model).run(queries)
    for row in result.rows:
        head, relation = int(row.query.head[1:]), int(row.query.relation[1:])
        expected = enumerate_reference(edges, 9, 3, head, relation, model.coefficient)
        assert set(row.candidate_ids) == set(expected)
        np.testing.assert_allclose(row.scores, [expected[k] for k in row.candidate_ids],
                                   atol=1e-12, rtol=1e-12)


def assert_same(a, b):
    assert len(a.rows) == len(b.rows)
    for x, y in zip(a.rows, b.rows):
        assert x.query == y.query and x.candidate_ids == y.candidate_ids
        assert x.snapshot_id == y.snapshot_id and x.model_id == y.model_id
        np.testing.assert_array_equal(x.scores, y.scores)


def test_interleaved_duplicates_preserve_bag_order_and_reuse_only_compatible_state():
    _, graph, model = fixture()
    queries = [LinkQuery(f"n{h}", f"r{r}") for r in (0, 1, 0, 2) for h in range(9)]
    session = Session(graph, model)
    naive, cached, planned = [session.run(queries, strategy=s) for s in
                              ("independent", "consecutive", "grouped")]
    assert_same(naive, cached)
    assert_same(naive, planned)
    assert naive.profile.expansions == cached.profile.expansions == 36
    assert planned.profile.expansions == 9
    assert planned.profile.model_calls == 27 and planned.profile.reused_scores == 9
    assert [row.query for row in planned.rows] == queries
    order = np.random.default_rng(42).permutation(len(queries))
    permuted = session.run([queries[int(i)] for i in order])
    for j, i in enumerate(order):
        np.testing.assert_array_equal(permuted.rows[j].scores, naive.rows[int(i)].scores)


def test_already_clustered_workload_has_strong_consecutive_cache():
    _, graph, model = fixture()
    queries = [LinkQuery(f"n{h}", f"r{r}") for h in range(9) for r in range(3)]
    a = Session(graph, model).run(queries, strategy="consecutive")
    b = Session(graph, model).run(queries)
    assert a.profile.expansions == b.profile.expansions == 9
    assert_same(a, b)


def test_bounded_windows_stream_without_consuming_future_input():
    _, graph, model = fixture()
    consumed = []

    def requests():
        for i in range(7):
            consumed.append(i)
            yield LinkQuery("n0", "r0")

    session = Session(graph, model, limits=Limits(window_size=3))
    batches = session.iter_batches(requests())
    first = next(batches)
    assert consumed == [0, 1, 2] and first.profile.expansions == 1
    rest = list(batches)
    assert [len(b.rows) for b in rest] == [3, 1]
    result = session.run([LinkQuery("n0", "r0")] * 7)
    assert result.profile.windows == result.profile.expansions == 3
    assert result.profile.reused_scores == 4


def test_snapshot_canonicalization_immutability_and_identity():
    edges, graph, model = fixture()
    duplicate = GraphSnapshot(np.vstack((edges[::-1], edges)), node_ids=graph.node_ids,
                               relations=graph.relations)
    assert graph.snapshot_id == duplicate.snapshot_id
    for obj, attr in ((graph, "indices"), (model, "coefficient")):
        with pytest.raises(ValueError):
            getattr(obj, attr).flags.writeable = True
        with pytest.raises(FrozenInstanceError):
            setattr(obj, attr, None)
    with pytest.raises(TypeError):
        graph._node_index["n0"] = 10
    old = graph.snapshot_id
    edges[:] = 0
    assert graph.snapshot_id == old and np.any(graph.indices != 0)
    changed = GraphSnapshot(np.array([[0, 0, 1]]), node_ids=graph.node_ids,
                             relations=graph.relations)
    assert changed.snapshot_id != graph.snapshot_id
    different_model = ExplicitPathModel(model.coefficient + .01, relations=model.relations)
    assert different_model.model_id != model.model_id


def test_direction_multitype_and_inverse_relations_are_distinct():
    edges = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 1], [0, 0, 1]])
    graph = GraphSnapshot(edges, node_ids=("a", "b", "c"), relations=("x", "y"))
    assert graph.neighbors(0).tolist() == [1]
    assert graph.symbols[graph.type_indptr[0]:graph.type_indptr[1]].tolist() == [0, 1, 2]
    assert graph.symbols[graph.type_indptr[1]:graph.type_indptr[2]].tolist() == [0, 2, 3]
    assert graph.degree.tolist() == [1, 1, 0]


def test_new_evidence_and_model_do_not_reuse_previous_predictions():
    nodes, relations = ("a", "b", "c", "d"), ("r",)
    original = GraphSnapshot([[0, 0, 1], [1, 0, 2], [2, 0, 3]],
                             node_ids=nodes, relations=relations)
    changed = GraphSnapshot([[0, 0, 1], [1, 0, 2], [2, 0, 3], [0, 0, 2]],
                            node_ids=nodes, relations=relations)
    weights = np.zeros((1, 16))
    weights[0, 0] = 1
    first_model = ExplicitPathModel(weights, relations=relations)
    weights[0, 0] = 2
    second_model = ExplicitPathModel(weights, relations=relations)
    queries = [LinkQuery("a", "r")] * 2
    original_session = Session(original, first_model)
    before = original_session.run(queries)
    rescored = Session(original, second_model).run(queries)
    reprojected = Session(changed, second_model).run(queries)
    assert before.rows[0].top(3) == [("c", 1.0), ("d", 1.0)]
    assert rescored.rows[0].top(3) == [("c", 2.0), ("d", 2.0)]
    assert reprojected.rows[0].top(3) == [("d", 2.0)]
    assert before.rows[0].model_id != rescored.rows[0].model_id
    assert rescored.rows[0].snapshot_id != reprojected.rows[0].snapshot_id
    assert_same(before, original_session.run(queries))


def test_empty_graph_isolated_nodes_and_empty_query():
    graph = GraphSnapshot(np.empty((0, 3), dtype=np.int64), node_ids=("alone",), relations=("r",))
    model = ExplicitPathModel(np.zeros((1, 16)), relations=("r",))
    session = Session(graph, model)
    row = session.run([LinkQuery("alone", "r")]).rows[0]
    assert row.candidate_ids == () and row.scores.shape == (0,) and row.top(3) == []
    assert row.score_for("alone") is None
    result = session.run([])
    assert result.rows == () and result.profile.expansions == result.profile.windows == 0
    empty = GraphSnapshot(np.empty((0, 3), dtype=np.int64), node_ids=(), relations=("r",))
    assert Session(empty, model).run([]).rows == ()
    with pytest.raises(ValueError):
        empty.neighbors(0)


def test_zero_scores_are_supported_and_ties_use_external_ids():
    edges = np.array([[0, 0, 1], [1, 0, 2], [1, 0, 3]])
    graph = GraphSnapshot(edges, node_ids=("source", "middle", "z", "a"), relations=("r",))
    model = ExplicitPathModel(np.zeros((1, 16)), relations=("r",))
    row = Session(graph, model).run([LinkQuery("source", "r")]).rows[0]
    assert row.top(2) == [("a", 0.0), ("z", 0.0)]
    assert row.score_for("a") == 0.0 and row.score_for("middle") is None
    assert row.top(0) == []
    with pytest.raises(ValueError):
        row.top(-1)


def test_id_permutation_preserves_semantics_and_order_independent_ties():
    edges, graph, model = fixture(8)
    permutation = np.random.default_rng(9).permutation(len(graph.node_ids))
    inverse = np.argsort(permutation)
    copied = edges.copy()
    copied[:, (0, 2)] = inverse[copied[:, (0, 2)]]
    other = GraphSnapshot(copied, node_ids=[graph.node_ids[i] for i in permutation],
                          relations=graph.relations)
    queries = [LinkQuery("n0", "r1"), LinkQuery("n2", "r2")]
    a, b = Session(graph, model).run(queries), Session(other, model).run(queries)
    for x, y in zip(a.rows, b.rows):
        assert set(x.candidate_ids) == set(y.candidate_ids)
        for node in x.candidate_ids:
            assert x.score_for(node) == pytest.approx(y.score_for(node), abs=1e-12)
        assert [k for k, _ in x.top(9)] == [k for k, _ in y.top(9)]


def test_exact_budget_failure_never_silently_truncates():
    _, graph, model = fixture()
    for limits in (Limits(max_type_visits=1), Limits(max_expansion_states=1)):
        with pytest.raises(ResourceLimitError):
            Session(graph, model, limits=limits).run([LinkQuery("n0", "r0")])
    # Failed execution leaves no partial cache to affect later sessions.
    assert_same(Session(graph, model).run([LinkQuery("n0", "r0")]),
                Session(graph, model).run([LinkQuery("n0", "r0")], strategy="independent"))


def test_model_roundtrip_and_tampering_detection(tmp_path):
    _, graph, model = fixture()
    path = tmp_path / "model.npz"
    model.save(path)
    with pytest.raises(FileExistsError):
        model.save(path)
    reloaded = ExplicitPathModel.load(path)
    assert reloaded.model_id == model.model_id
    assert_same(Session(graph, model).run([LinkQuery("n0", "r0")]),
                Session(graph, reloaded).run([LinkQuery("n0", "r0")]))
    with np.load(path) as saved:
        contents = {k: saved[k] for k in saved.files}
    contents["coefficient"][0, 0] += 1
    np.savez(path, **contents)
    with pytest.raises(ValueError, match="identity"):
        ExplicitPathModel.load(path)


@pytest.mark.parametrize("bad", [0, -1, True, 1.2])
def test_invalid_limits(bad):
    with pytest.raises(ValueError):
        Limits(window_size=bad)


def test_reject_unknown_inputs_and_schema_reordering():
    _, graph, model = fixture()
    with pytest.raises(ValueError, match="schemas"):
        Session(graph, ExplicitPathModel(model.coefficient, relations=model.relations[::-1]))
    session = Session(graph, model)
    for query in (LinkQuery("missing", "r0"), LinkQuery("n0", "missing"), LinkQuery(None, "r0")):
        with pytest.raises(ValueError):
            session.run([query])
    with pytest.raises(TypeError):
        session.run([(0, 0)])
    with pytest.raises(ValueError):
        session.run([], strategy="unknown")
    for edges in ([[0., 0., 1.]], [[0, 0, 0]], [[0, 0, 9]], [[0, -1, 1]]):
        with pytest.raises(ValueError):
            GraphSnapshot(edges, node_ids=("a", "b"), relations=("r",))
    for values in (("a", "a"), ("a", ""), (0, 1)):
        with pytest.raises(ValueError):
            GraphSnapshot([[0, 0, 1]], node_ids=values, relations=("r",))


def test_package_imports_without_training_frameworks():
    from pathlib import Path

    import orbweaver_query

    # Exercise whichever package pytest selected, including an installed wheel.
    package_root = str(Path(orbweaver_query.__file__).resolve().parent.parent)
    code = f"import sys,json; sys.path.insert(0, {package_root!r})\n" + """import orbweaver_query
print(json.dumps(sorted(set(sys.modules) & {'torch','mlx','scipy','sklearn','research'})))
"""
    proc = subprocess.run([sys.executable, "-I", "-c", code], text=True,
                          capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == []
