"""Ensure a stronger benchmark cache is semantically equivalent under eviction."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from orbweaver_query import ExplicitPathModel, GraphSnapshot, LinkQuery, Session, score_bindings


def reference():
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "cache_reference.py"
    spec = importlib.util.spec_from_file_location("cache_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("sources,byte_limit", [(1, 2**20), (256, 1), (3, 2**20), (256, 2**20)])
def test_cache_outputs_survive_eviction_and_bypass(sources, byte_limit):
    graph = GraphSnapshot([[i, i % 2, i+1] for i in range(8)],
                          node_ids=[str(i) for i in range(10)], relations=["a", "b"])
    model = ExplicitPathModel(np.random.default_rng(16).normal(size=(2, 84)), relations=graph.relations)
    session = Session(graph, model)
    queries = [LinkQuery(str(h), r) for r in ("a", "b", "a") for h in range(10)]
    actual, work = reference().lru_predict(session, queries, max_sources=sources,
                                          max_numeric_bytes=byte_limit)
    expected = session.run(queries, strategy="independent").rows
    for a, b in zip(actual, expected, strict=True):
        assert a.query == b.query and a.candidate_ids == b.candidate_ids
        np.testing.assert_array_equal(a.scores, b.scores)
    assert work["peak_cached_numeric_bytes"] <= byte_limit
    assert work["cached_sources_at_end"] <= sources
    if sources == 256 and byte_limit > 1:
        assert work["expansions"] == 10 and work["model_calls"] == 20
    rows = [{"head": "0", "relation": "a", "target": t} for t in ("2", None, "1", "2")]
    result, _ = reference().lru_score_bindings(session, rows)
    assert result.to_records() == score_bindings(session, rows).to_records()
