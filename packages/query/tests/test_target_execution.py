"""Target pushdown must preserve full-evidence path probabilities and row semantics."""

import numpy as np
import pytest
from test_execution import enumerate_reference, fixture

from orbweaver_query import ExplicitPathModel, GraphSnapshot, Limits, Session, score_bindings


@pytest.mark.parametrize("seed", range(12))
def test_target_pushdown_against_full_expansion_and_independent_walks(seed):
    edges, graph, model = fixture(seed)
    for head in range(9):
        full = model.expand(graph, head, Limits())
        for targets in ((), (head,), (0,), (1, 4, 7), tuple(range(9))):
            selected = model.expand_targets(graph, head, targets, Limits())
            indices = [i for i, n in enumerate(full.candidates) if n in targets]
            np.testing.assert_array_equal(selected.candidates, full.candidates[indices])
            np.testing.assert_array_equal(selected.base, full.base[indices])
            for relation in range(3):
                expected = enumerate_reference(edges, 9, 3, head, relation, model.coefficient)
                scores = model.score(selected, relation)
                np.testing.assert_allclose(scores, model.score(full, relation)[indices],
                                           atol=1e-12, rtol=1e-12)
                np.testing.assert_allclose(scores, [expected[f"n{n}"] for n in selected.candidates],
                                           atol=1e-12, rtol=1e-12)


def test_bound_windows_duplicates_nulls_and_reordered_input():
    _, graph, model = fixture(19, n=30)
    rng = np.random.default_rng(42)
    rows = [{"head": f"n{h}", "relation": f"r{r}", "target": f"n{t}", "ordinal": i}
            for i, (h, r, t) in enumerate(zip(rng.integers(0, 5, 130),
                                             rng.integers(0, 3, 130), rng.integers(0, 30, 130)))]
    rows += [rows[0], {"head": "unknown", "relation": "r0", "target": None}]
    session = Session(graph, model, limits=Limits(window_size=17))
    full = score_bindings(session, rows, execution="full")
    for strategy in ("independent", "consecutive", "grouped"):
        selected = score_bindings(session, rows, strategy=strategy, execution="targeted")
        for a, b in zip(full.rows, selected.rows):
            assert a.binding == b.binding and a.status == b.status
            assert a.snapshot_id == b.snapshot_id and a.model_id == b.model_id
            if a.score is None:
                assert b.score is None
            else:
                assert a.score == pytest.approx(b.score, rel=1e-12, abs=1e-12)
        assert all(p.queries == 0 or p.candidate_selection == "bound_targets"
                   for p in selected.profiles)


def test_target_validation_and_unknown_backend_fallback():
    _, graph, model = fixture()
    for targets in ((True,), (-1,), (9,), (0.0,)):
        with pytest.raises(ValueError, match="Target index"):
            model.expand_targets(graph, 0, targets, Limits())

    class OtherBackend:
        relations = model.relations
        model_id = "other-backend"
        expand = model.expand
        score = model.score

    session = Session(graph, OtherBackend())
    row = {"head": "n0", "relation": "r0", "target": "n3"}
    automatic = score_bindings(session, [row])
    assert automatic.rows[0].score_kind == "backend_score"
    assert automatic.profiles[0].candidate_selection == "all"
    assert session.explain()["candidate_support"] == "backend_defined"
    with pytest.raises(ValueError, match="does not support"):
        score_bindings(session, [row], execution="targeted")


def test_predecessor_budget_fallback_keeps_exact_support():
    graph = GraphSnapshot([(1, 0, 2), (2, 0, 0), *[(0, 0, n) for n in range(3, 24)]],
                          node_ids=[f"n{i}" for i in range(24)], relations=("r",))
    model = ExplicitPathModel(np.ones((1, 16)), relations=("r",))
    # Target degree exceeds the reverse-index budget; retained states still fit.
    limited = model.expand_targets(graph, 1, (0,), Limits(max_expansion_states=4))
    regular = model.expand_targets(graph, 1, (0,), Limits())
    np.testing.assert_array_equal(limited.candidates, regular.candidates)
    np.testing.assert_array_equal(limited.base, regular.base)
