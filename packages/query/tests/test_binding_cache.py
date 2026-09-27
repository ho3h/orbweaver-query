"""Persistent exact memoization must not change artifact or null semantics."""

import numpy as np
import pytest
from test_bindings import runtime

from orbweaver_query import (
    BindingCache,
    ExplicitPathModel,
    GraphSnapshot,
    Limits,
    ResourceLimitError,
    score_bindings,
)


def test_cached_scores_unsupported_nulls_and_duplicates():
    session, cache = runtime(), BindingCache()
    rows = [{"head": "a", "relation": "r", "target": target} for target in ("c", "b", None)]
    expected = score_bindings(session, rows).to_records()
    first = score_bindings(session, rows, cache=cache)
    assert first.to_records() == expected
    assert cache.info().entries == 2
    warm = score_bindings(session, rows, cache=cache)
    assert warm.to_records() == expected
    assert sum(p.expansions for p in warm.profiles) == 0
    assert cache.info().hits == 2
    cache.clear()
    repeated = score_bindings(session, [rows[0]]*2, cache=cache)
    assert repeated.to_records() == [expected[0]]*2
    assert repeated.profiles[0].queries == 1
    assert cache.info().entries == cache.info().misses == 1


def test_graph_and_model_replacement_cannot_hit_stale_cache():
    session, cache = runtime(), BindingCache()
    rows = [{"head": "a", "relation": "r", "target": "c"}]
    first = score_bindings(session, rows, cache=cache)
    weights = np.zeros((1, 16))
    weights[0, 0] = 9
    session.model = ExplicitPathModel(weights, relations=("r",))
    changed = score_bindings(session, rows, cache=cache)
    assert changed.rows[0].score == 9 and first.rows[0].score == 2
    session.graph = GraphSnapshot([[0, 0, 2]], node_ids=("a", "b", "c", "d"), relations=("r",))
    unsupported = score_bindings(session, rows, cache=cache)
    assert unsupported.rows[0].status == "unsupported"
    assert cache.info().hits == 0 and cache.info().misses == 3
    assert len({x.rows[0].model_id for x in (first, changed)}) == 2
    assert changed.rows[0].snapshot_id != unsupported.rows[0].snapshot_id


def test_lru_eviction_and_failed_window_does_not_commit_predictions():
    session, cache = runtime(), BindingCache(max_entries=1)
    rows = [{"head": "a", "relation": "r", "target": target} for target in ("c", "d")]
    score_bindings(session, rows, cache=cache)
    assert cache.info().entries == cache.info().evictions == 1
    score_bindings(session, rows[1:], cache=cache)
    assert cache.info().hits == 1
    cache.clear()
    session.limits = Limits(max_type_visits=1)
    with pytest.raises(ResourceLimitError):
        score_bindings(session, rows, cache=cache)
    assert cache.info().entries == 0


def test_validation_precedes_cache_lookup_and_null_short_circuit():
    session, cache = runtime(), BindingCache()
    with pytest.raises(ValueError):
        score_bindings(session, [{"head": "a", "relation": "r", "target": "unknown"}], cache=cache)
    assert cache.info().misses == 0
    result = score_bindings(session, [{"head": "unknown", "relation": "missing", "target": None}], cache=cache)
    assert result.rows[0].status == "null_input" and cache.info().entries == 0
    for maximum in (True, 0, -1, 1.5):
        with pytest.raises(ValueError):
            BindingCache(max_entries=maximum)
