"""The native application boundary must rank each source without losing zeros."""

import importlib.util
import math
import os
from pathlib import Path

import numpy as np
import pytest

from orbweaver_query import GraphSnapshot, NeighborhoodModel


def harness(name='gds_ranking'):
    path = Path(__file__).resolve().parents[1]/f'benchmarks/v1/{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture():
    rng = np.random.default_rng(531)
    pairs = set(map(tuple, np.argwhere(np.triu(rng.random((94, 94)) < .07, 1))))
    pairs.update((i, 93) for i in range(93))
    graph = GraphSnapshot(np.array([(int(a), 0, int(b)) for x, y in sorted(pairs)
                                   for a, b in ((x, y), (y, x))]),
                          node_ids=[f'n{i}' for i in range(96)], relations=('LINK',))
    return graph, np.array([0, 3, 12, 93, 94, 95], dtype=np.int64)


def test_local_ranking_matches_independent_sparse_scores():
    pytest.importorskip('scipy', reason='Independent sparse oracle requires the train extra')
    h = harness()
    graph, sources = fixture()
    for metric in ('resource_allocation', 'adamic_adar'):
        oracle = h.structural_scores(graph, sources, metric)
        actual = h.local_scores(graph, sources, NeighborhoodModel(relations=('LINK',), metric=metric))
        np.testing.assert_allclose(actual, oracle, atol=1e-12, rtol=1e-12)
        assert h.rank_scores(actual, graph, sources, 16) == h.rank_scores(oracle, graph, sources, 16)
        ranked = h.rank_scores(actual, graph, sources, 16)
        assert len(ranked[-3]['recommendations']) == 2
        assert all(r['score'] == 0 for r in ranked[-1]['recommendations'])
        assert [r['target'] for r in ranked[-1]['recommendations']][:4] == ['n0', 'n1', 'n10', 'n11']


def test_stream_coverage_rejects_truncation_duplicates_and_bad_values():
    h = harness()
    graph, sources = fixture()
    mask = h.candidate_mask(graph, sources)
    rows = [{'head': int(sources[i]), 'target': int(t), 'score': .5}
            for i, t in np.argwhere(mask)]
    scores = h.from_stream(rows, graph, sources)
    assert np.isfinite(scores).sum() == mask.sum()
    for bad, message in ((rows[:-1], 'Incomplete'), (rows+[rows[0]], 'Duplicate'),
                         ([{**rows[0], 'score': math.nan}]+rows[1:], 'probability'),
                         ([{**rows[0], 'target': rows[0]['head']}]+rows[1:], 'domain')):
        with pytest.raises(ValueError, match=message):
            h.from_stream(bad, graph, sources)


def test_missing_support_does_not_become_zero_and_empty_heads_survive():
    h = harness()
    graph, sources = fixture()
    scores = np.full((len(sources), len(graph.node_ids)), np.nan)
    ranked = h.rank_scores(scores, graph, sources, 16)
    assert [r['head'] for r in ranked] == [graph.node_ids[i] for i in sources]
    assert all(r['recommendations'] == [] for r in ranked)
    for k in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match='positive integer'):
            h.rank_scores(scores, graph, sources, k)
    scores[0, sources[0]] = 0
    with pytest.raises(ValueError, match='excluded'):
        h.rank_scores(scores, graph, sources, 16)


def test_partitioned_overfetch_completes_ties_and_keeps_empty_sources():
    h = harness()
    specs = [{'head': 'h0', 'source_label': 'Source0', 'candidates': 7},
             {'head': 'h1', 'source_label': 'Source1', 'candidates': 3},
             {'head': 'empty', 'source_label': 'Source2', 'candidates': 0}]

    class Source:
        def iter_candidates(self, cypher, parameters):
            assert cypher == h.PARTITIONED
            for req in parameters['requests']:
                # Adversarial cutoff ties: native output favors largest IDs.
                ids = list(reversed(range(specs[req['ordinal']]['candidates'])))[:req['limit']]
                for i in ids:
                    yield {'ordinal': req['ordinal'], 'a': f't{i}', 'b': req['head'], 'score': .5}

    output, counters = h.partitioned_request(Source(), specs, 1, k=2)
    assert output == [{'head': s['head'], 'recommendations': [] if not s['candidates'] else
                       [{'target': 't0', 'score': .5}, {'target': 't1', 'score': .5}]}
                      for s in specs]
    assert counters == {'rounds': 2, 'procedure_calls': 3, 'returned_pairs': 14, 'max_top_n': 7}


@pytest.mark.parametrize('failure', ('missing', 'duplicate', 'foreign', 'self', 'nonfinite'))
def test_partitioned_request_rejects_invalid_native_output(failure):
    h = harness()

    class Source:
        def iter_candidates(self, cypher, parameters):
            row = {'ordinal': 0, 'a': 'head', 'b': 'target', 'score': .5}
            if failure == 'missing':
                return iter(())
            if failure == 'duplicate':
                return iter((row, row))
            if failure == 'foreign':
                row['a'] = 'other'
            elif failure == 'self':
                row['b'] = 'head'
            elif failure == 'nonfinite':
                row['score'] = float('nan')
            return iter((row,))

    with pytest.raises(ValueError):
        h.partitioned_request(Source(), [{'head': 'head', 'source_label': 'Source', 'candidates': 1}], 1)


@pytest.mark.skipif(not os.getenv('ORBWEAVER_QUERY_GDS_TEST_URI'), reason='requires disposable GDS')
def test_live_native_topk_and_full_domain():
    from neo4j import GraphDatabase
    from orbweaver_query.neo4j import Neo4jSource

    h, native = harness(), harness('structural_neo4j')
    graph, sources = fixture()
    with GraphDatabase.driver(os.environ['ORBWEAVER_QUERY_GDS_TEST_URI'], auth=None) as driver:
        def query(cypher, **parameters):
            return [r.data() for r in driver.execute_query(cypher, parameters_=parameters)[0]]

        native.import_graph(driver, graph)
        query('UNWIND $ids AS id MATCH (n:Node {id:id}) SET n:Query',
              ids=[graph.node_ids[i] for i in sources])
        query('MATCH (n:Node) SET n.degree=COUNT { (n)-[:LINK]-() }')
        specs = h.prepare_source_specs(query, [graph.node_ids[i] for i in sources])
        query("CALL gds.graph.project('graph',$labels,{LINK:{orientation:'UNDIRECTED'}})",
              labels=['Node', 'Query', *[s['source_label'] for s in specs]])
        source = Neo4jSource(driver)
        params = {'heads': [graph.node_ids[i] for i in sources], 'k': 16,
                  'candidate_count': int(h.candidate_mask(graph, sources).sum()), 'threads': 1}
        assert [r['head'] for r in source.iter_candidates(h.HEADS, params)] == params['heads']
        for metric in ('resource_allocation', 'adamic_adar'):
            expected = h.rank_scores(h.structural_scores(graph, sources, metric), graph, sources, 16)
            for scalar in (True, False):
                assert list(source.iter_candidates(h.structural_query(metric, scalar=scalar), params)) == expected
        for threads in (1, 4):
            if threads == 4:
                query("CALL gds.model.drop('model')")
                query("CALL gds.beta.pipeline.drop('pipe')")
            params['threads'] = threads
            trained = h.fit_gds(query, {'dimension': 8, 'rich': True, 'negative_ratio': 1.0}, threads)
            assert trained[0]['configuration']['concurrency'] == threads
            scores = h.from_stream(source.iter_candidates(h.gds_query(full=True), params), graph, sources)
            expected = h.rank_scores(scores, graph, sources, 16)
            for _ in range(2):
                assert list(source.iter_candidates(h.gds_query(), params)) == expected
            actual, counters = h.partitioned_request(source, specs, threads)
            assert actual == expected
            assert counters['rounds'] >= 2  # Isolated roots force a full tie expansion.
