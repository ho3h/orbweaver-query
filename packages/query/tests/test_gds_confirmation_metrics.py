"""Independent closed-form fixtures for the unopened confirmation evaluation."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def metrics():
    path = Path(__file__).resolve().parents[1]/'benchmarks/v1/gds_confirmation_metrics.py'
    spec = importlib.util.spec_from_file_location('confirmation_metrics_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def empty_graph(metrics, n=70):
    ids, sources = [f'n{i}' for i in range(n)], np.array([0])
    adjacency, mask = metrics.graph_domain(ids, np.empty((0, 3), dtype=np.int64), sources)
    scores = metrics.common_neighbors(adjacency, sources, mask)
    return ids, sources, mask, scores


def test_common_neighbors_counts_walks_and_preserves_zero_candidates(metrics):
    edges = [(0, 1), (0, 2), (1, 3), (2, 3), (2, 4)]
    triples = np.array([(h, 0, t) for a, b in edges for h, t in ((a, b), (b, a))])
    sources = np.array([0, 5])
    adjacency, mask = metrics.graph_domain([str(i) for i in range(6)], triples, sources)
    scores = metrics.common_neighbors(adjacency, sources, mask)
    np.testing.assert_array_equal(scores[0, [3, 4, 5]], [2., 1., 0.])
    np.testing.assert_array_equal(scores[1, :5], np.zeros(5))
    assert np.isnan(scores[0, :3]).all() and np.isnan(scores[1, 5])
    metrics.validate_scores(scores, mask, complete=True)


@pytest.mark.parametrize('bad', ('directed', 'duplicate', 'self', 'relation', 'index', 'source'))
def test_graph_domain_rejects_mismatched_evidence(metrics, bad):
    triples, sources = np.array([[0, 0, 1], [1, 0, 0]]), np.array([0])
    if bad == 'directed':
        triples = triples[:1]
    elif bad == 'duplicate':
        triples = np.vstack([triples, triples[:1]])
    elif bad == 'self':
        triples = np.array([[0, 0, 0]])
    elif bad == 'relation':
        triples[:, 1] = 1
    elif bad == 'index':
        triples[0, 2] = 2
    elif bad == 'source':
        sources = np.array([0, 0])
    with pytest.raises(ValueError):
        metrics.graph_domain(['a', 'b'], triples, sources)


def test_large_tie_has_expected_recall_but_different_actual_answers(metrics):
    ids, sources, mask, scores = empty_graph(metrics)
    result = metrics.assess(scores, mask, sources, np.array([[0, 1], [0, 69]]), ids)
    assert result['raw']['metrics'] == pytest.approx(
        {'recall16': 16/69, 'recall64': 64/69, 'reciprocal_rank': 1/35, 'supported': 1})
    assert result['rounded']['metrics'] == result['raw']['metrics']
    assert result['deterministic_id_recall16'] == .5
    assert result['source_positive_counts'] == [2]
    assert metrics.source_totals(result, sources)[0] == pytest.approx(32/69)
    assert result['output'][0]['recommendations'][1]['target'] == 'n10'


def test_rounding_and_unsupported_predictions_cannot_improve_primary_quality(metrics):
    ids, sources, mask, scores = empty_graph(metrics)
    scores[0, 69] = 1e-13
    result = metrics.assess(scores, mask, sources, np.array([[0, 69]]), ids)
    assert result['raw']['metrics']['recall16'] == 1
    assert result['rounded']['metrics']['recall16'] == pytest.approx(16/69)
    assert result['deterministic_id_recall16'] == 0
    scores[0, 69] = np.nan
    missed = metrics.assess(scores, mask, sources, np.array([[0, 69]]), ids)
    assert missed['raw']['metrics'] == dict.fromkeys(metrics.METRICS, 0.)
    assert missed['raw']['outcomes'][0]['rank'] is None
    assert missed['deterministic_id_recall16'] == 0
    with pytest.raises(ValueError, match='Incomplete'):
        metrics.validate_scores(scores, mask, complete=True)


def test_empty_denominator_is_unevaluable_and_invalid_positives_fail(metrics):
    ids, sources, mask, scores = empty_graph(metrics)
    empty = metrics.assess(scores, mask, sources, np.empty((0, 2), dtype=np.int64), ids)
    assert not empty['raw']['evaluable']
    assert empty['raw']['metrics'] == dict.fromkeys(metrics.METRICS)
    assert empty['deterministic_id_recall16'] is None
    for positives in ([[0, 0]], [[1, 2]], [[0, 70]], [[0, 1], [0, 1]]):
        with pytest.raises(ValueError):
            metrics.assess(scores, mask, sources, np.array(positives), ids)
    scores[0, 1] = np.inf
    with pytest.raises(ValueError, match='Invalid score'):
        metrics.validate_scores(scores, mask)


def bootstrap_inputs(metrics, rates=(.6, .4, .2, .6, .6)):
    counts = {d: np.arange(64) % 3 for d in metrics.DATASETS}
    totals = {d: np.broadcast_to(counts[d][None, None, :, None]*np.array(rates),
                                 (2, 3, 64, 5)).copy() for d in metrics.DATASETS}
    return totals, counts


def test_paired_bootstrap_keeps_identical_controls_exactly_equal(metrics):
    totals, counts = bootstrap_inputs(metrics)
    report = metrics.paired_bootstrap(totals, counts, draws=257)
    assert report['status'] == 'evaluated' and len(report['comparisons']) == 40
    assert report['configuration']['simultaneous_tail_probability'] == .05/80
    assert report['exclusions']['retained_draws'] == 257
    for row in report['comparisons']:
        expected = {'gds': .2, 'common_neighbors': .4,
                    'resource_allocation': 0., 'adamic_adar': 0.}[row['control']]
        assert row['difference'] == pytest.approx(expected)
        assert row['simultaneous_95'] == pytest.approx([expected, expected])
        assert row['supported_improvement'] == bool(expected)
        assert not row['supported_loss']
    assert all(v['original_quality_conditions_met'] for v in report['quality_rule'].values())
    assert report == metrics.paired_bootstrap(totals, counts, draws=257)


def test_process_repetitions_are_averaged_before_resampling(metrics):
    totals, counts = bootstrap_inputs(metrics, rates=(.4, .4, .4, .4, .4))
    for name in metrics.DATASETS:
        for repetition, rate in enumerate((.2, .4, .6)):
            totals[name][:, repetition, :, 0] = counts[name]*rate
    report = metrics.paired_bootstrap(totals, counts, draws=101)
    for row in report['comparisons']:
        assert row['difference'] == pytest.approx(0., abs=1e-15)
        assert row['simultaneous_95'] == pytest.approx([0., 0.], abs=1e-15)
        assert not row['supported_loss'] and not row['supported_improvement']


def test_nonconstant_paired_intervals_and_both_pools_match_scalar_reference(metrics):
    totals, counts = bootstrap_inputs(metrics)
    for d, name in enumerate(metrics.DATASETS):
        counts[name] += d
        for t in range(2):
            for r in range(3):
                for s in range(64):
                    for method in range(5):
                        totals[name][t, r, s, method] = (
                            counts[name][s]*((s+3*r+2*t+7*method+5*d) % 13)/13)
    draws, seed = 19, 851
    report = metrics.paired_bootstrap(totals, counts, draws=draws, seed=seed)
    rng = np.random.default_rng(seed)
    indices = {name: rng.integers(0, 64, size=(draws, 64)).tolist() for name in metrics.DATASETS}

    def reference(view, t, c, draw):
        numerators, denominators = [], []
        for name in metrics.DATASETS:
            selected = range(64) if draw is None else indices[name][draw]
            denominator = sum(int(counts[name][s]) for s in selected)
            numerator = sum(float(totals[name][t, r, s, 0]-totals[name][t, r, s, c])
                            for r in range(3) for s in selected)/3
            numerators.append(numerator)
            denominators.append(denominator)
        ratios = [n/d for n, d in zip(numerators, denominators)]
        if view in metrics.DATASETS:
            return ratios[metrics.DATASETS.index(view)]
        if view == 'equal_application':
            return sum(ratios)/3
        return sum(numerators)/sum(denominators)

    for row in report['comparisons']:
        t, c = metrics.THREADS.index(row['threads']), metrics.METHODS.index(row['control'])
        values = [reference(row['view'], t, c, draw) for draw in range(draws)]
        assert row['difference'] == pytest.approx(reference(row['view'], t, c, None), abs=1e-15)
        assert row['percentile_95'] == pytest.approx(np.quantile(values, [.025, .975]), abs=1e-15)
        tail = .05/80
        assert row['simultaneous_95'] == pytest.approx(np.quantile(values, [tail, 1-tail]), abs=1e-15)


def test_zero_positive_sources_remain_in_resampling_and_are_counted(metrics):
    totals, counts = bootstrap_inputs(metrics)
    for name in metrics.DATASETS:
        counts[name][1:] = 0
        counts[name][0] = 1
        totals[name][:] = 0
        totals[name][:, :, 0, :] = .5
    report = metrics.paired_bootstrap(totals, counts, draws=301)
    exclusions = report['exclusions']
    assert all(n > 0 for n in exclusions['by_application'].values())
    assert 0 < exclusions['retained_draws'] < 301
    assert exclusions['retained_draws']+exclusions['any_application'] == 301
    assert all(row['simultaneous_95'] == [0., 0.] for row in report['comparisons'])
    counts['friendship'][:] = 0
    totals['friendship'][:] = 0
    empty = metrics.paired_bootstrap(totals, counts, draws=301)
    assert empty['status'] == 'unevaluable' and empty['quality_rule'] is None
    assert empty['empty_positive_applications'] == ['friendship']


def test_point_boundary_is_distinct_from_strict_noninferiority(metrics):
    totals, counts = bootstrap_inputs(metrics, rates=(.49, .5, .5, .5, .5))
    report = metrics.paired_bootstrap(totals, counts, draws=101)
    for rule in report['quality_rule'].values():
        assert rule['point_estimates_within_one_point_on_every_application']
        assert rule['statistically_supported_pooled_loss']
        assert not rule['one_point_noninferiority_all_views']
        assert not rule['original_quality_conditions_met']


def test_bootstrap_rejects_missing_families_and_hidden_denominator_changes(metrics):
    totals, counts = bootstrap_inputs(metrics)
    with pytest.raises(ValueError, match='three graph'):
        metrics.paired_bootstrap({k: v for k, v in totals.items() if k != 'friendship'}, counts)
    totals['friendship'][0, 0, 0, 0] = 1  # Source zero has no positives.
    with pytest.raises(ValueError, match='contributions'):
        metrics.paired_bootstrap(totals, counts, draws=101)
