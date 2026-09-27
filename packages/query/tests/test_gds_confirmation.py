"""Confirmation access boundaries and synthetic split checks, without real labels."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def confirmation(monkeypatch):
    folder = Path(__file__).resolve().parents[1]/'benchmarks/v1'
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location('confirmation_runner_test', folder/'gds_confirmation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def context(confirmation):
    ids, sources = [str(i) for i in range(6)], np.array([0, 3])
    adjacency, mask = confirmation.metrics.graph_domain(ids, np.array([[0, 0, 1], [1, 0, 0]]), sources)
    return {'ids': ids, 'sources': sources, 'adjacency': adjacency, 'mask': mask,
            'development': np.array([[0, 2]])}


def test_confirmation_retains_both_queried_directions_and_full_denominator(confirmation, context):
    pairs = np.array([[0, 3], [0, 4], [3, 4], [4, 5]])
    actual = confirmation.held_out_queries(pairs, context, 4)
    np.testing.assert_array_equal(actual, [[0, 3], [3, 0], [0, 4], [3, 4]])


@pytest.mark.parametrize('pairs,count', [([[0, 1]], 1), ([[0, 2]], 1), ([[3, 3]], 1),
    ([[3, 0]], 1), ([[0, 6]], 1), ([[0, 4], [0, 4]], 2), ([[0, 4]], 2)])
def test_confirmation_rejects_overlap_reversal_duplicates_and_missing_labels(
        confirmation, context, pairs, count):
    with pytest.raises(ValueError):
        confirmation.held_out_queries(np.array(pairs), context, count)


def test_added_control_passes_explicit_manual_fixture(confirmation):
    assert confirmation.small_reference_check() == {
        'common_neighbor_manual_fixture': True, 'closed_form_tie_fixture': True}


def test_incomplete_application_cannot_reach_any_label_reader(confirmation, monkeypatch, tmp_path):
    monkeypatch.setattr(confirmation.archive, 'verify', lambda _: {
        'status': 'interrupted; no aggregate timing claim', 'verified_workers': 4})

    def unexpected(*args, **kwargs):
        raise AssertionError('No NumPy file reader should be reached')

    monkeypatch.setattr(confirmation.np, 'load', unexpected)
    with pytest.raises(ValueError, match='every application worker'):
        confirmation.freeze(tmp_path/'run', tmp_path/'archive', tmp_path/'inputs')
    assert not (tmp_path/'run').exists()


@pytest.mark.parametrize('marker', ('results.json', 'EVALUATION_STARTED.json', 'error.json'))
def test_repeat_or_failed_confirmation_is_not_silently_reopened(
        confirmation, monkeypatch, tmp_path, marker):
    monkeypatch.setattr(confirmation, 'checked', lambda _: {})
    (tmp_path/marker).write_text('{}\n')

    def unexpected(*args, **kwargs):
        raise AssertionError('No application or label reader should be reached')

    monkeypatch.setattr(confirmation, 'audit_application', unexpected)
    with pytest.raises(ValueError, match='prior confirmation attempt'):
        confirmation.evaluate(tmp_path)


def quality_workers(module, *, empty=False):
    workers = []
    for dataset in module.metrics.DATASETS:
        for threads in module.metrics.THREADS:
            for repeat in range(3):
                methods = {}
                for method, score in zip(module.metrics.METHODS, (.1+.1*repeat, .25, .3, .15, .2)):
                    value = None if empty else score
                    methods[method] = {mode: {'metrics': dict.fromkeys(module.metrics.METRICS, value),
                        'positive_queries': 0 if empty else 10} for mode in ('raw', 'rounded')}
                    methods[method]['deterministic_id_recall16'] = value
                workers.append({'job': {'dataset': dataset, 'threads': threads, 'replicate': repeat},
                                'methods': methods})
    return workers


def test_absolute_quality_uses_all_repetitions_and_retains_strongest_control(confirmation):
    workers = quality_workers(confirmation)
    rows = confirmation.summarize_workers(workers)
    assert len(rows) == 6
    for row in rows:
        assert row['methods']['local']['raw']['recall16'] == pytest.approx(.2)
        assert row['methods']['local']['deterministic_id_recall16'] == pytest.approx(.2)
        assert row['strongest_control_methods'] == ['common_neighbors']
        assert row['local_minus_strongest_raw_recall16'] == pytest.approx(-.1)
    with pytest.raises(ValueError, match='every|Every'):
        confirmation.summarize_workers(workers[:-1])


def test_unevaluable_absolute_quality_is_never_reported_as_perfect(confirmation):
    rows = confirmation.summarize_workers(quality_workers(confirmation, empty=True))
    assert all(r['positive_queries'] == 0 and r['strongest_control_methods'] == []
               and r['local_minus_strongest_raw_recall16'] is None for r in rows)


def test_full_synthetic_evaluation_preserves_all_workers_and_paired_labels(confirmation, tmp_path):
    """Exercise file assembly and analysis without touching actual held-out data."""
    module = confirmation
    for name in ('sealed', 'structural', 'application/workers'):
        (tmp_path/name).mkdir(parents=True)
    module.write(tmp_path/'manifest.json', {'synthetic_fixture': True})
    module.write(tmp_path/'original-input-manifest.json', {
        'inventory': {d: {'confirmation': 2} for d in module.metrics.DATASETS}})
    ids, sources = [f'n{i}' for i in range(70)], np.arange(64)
    adjacency, mask = module.metrics.graph_domain(
        ids, np.empty((0, 3), dtype=np.int64), sources)
    scores = module.metrics.common_neighbors(adjacency, sources, mask)
    contexts = {d: {'ids': ids, 'sources': sources, 'adjacency': adjacency, 'mask': mask,
                   'development': np.empty((0, 2), dtype=np.int64)} for d in module.metrics.DATASETS}
    # First pair contributes both directions; second contributes only source 0.
    for dataset in module.metrics.DATASETS:
        np.savez_compressed(tmp_path/'sealed'/f'{dataset}-confirmation-sealed.npz',
                            pairs=np.array([[0, 1], [0, 69]]))
        np.savez_compressed(tmp_path/'structural'/f'{dataset}.npz', scores=scores)
    frozen = []
    for dataset in module.metrics.DATASETS:
        for threads in module.metrics.THREADS:
            for replicate in range(3):
                index = len(frozen)
                frozen.append({'job': {'dataset': dataset, 'threads': threads,
                                       'replicate': replicate}})
                np.savez_compressed(tmp_path/'application/workers'/f'{index:04d}-scores.npz',
                    **{name: scores for name in ('local', 'gds', 'resource_allocation', 'adamic_adar')})
    manifest = {'format': 'synthetic-confirmation', 'workers': frozen,
                'bootstrap_draws': 17, 'bootstrap_seed': 20260928,
                'application_results_sha256': 'synthetic-application'}
    result = module.evaluate_labels(tmp_path, manifest, contexts)
    assert result['confirmation_labels_parsed'] and not result['release_gate_closed']
    assert len(result['workers']) == 18 and len(result['mean_quality']) == 6
    assert len(list((tmp_path/'workers').glob('*.json'))) == 18
    for worker in result['workers']:
        for assessment in worker['methods'].values():
            assert assessment['raw']['positive_queries'] == 3
            assert assessment['raw']['metrics']['recall16'] == pytest.approx(16/69)
            assert assessment['deterministic_id_recall16'] == pytest.approx(2/3)
            assert assessment['source_positive_counts'] == [2, 1]+[0]*62
            assert len(assessment['output']) == 64
    for row in result['paired_analysis']['comparisons']:
        assert row['difference'] == 0 and row['simultaneous_95'] == [0, 0]
    assert len(result['paired_analysis']['comparisons']) == 40
    # The final artifact must be serializable without nonfinite sentinels.
    module.write(tmp_path/'results.json', result)
    assert module.archive.read(tmp_path/'results.json') == result


def test_evaluation_failure_retains_access_marker_and_cannot_reopen(
        confirmation, monkeypatch, tmp_path):
    module = confirmation
    module.write(tmp_path/'manifest.json', {'synthetic_fixture': True})
    monkeypatch.setattr(module, 'checked', lambda _: {'workers': [], 'source_ids': {}})
    monkeypatch.setattr(module, 'audit_application', lambda _: ({}, []))
    accesses = []

    def fail_after_access(*args):
        accesses.append(True)
        raise ValueError('Synthetic failure after label access')

    monkeypatch.setattr(module, 'evaluate_labels', fail_after_access)
    with pytest.raises(ValueError, match='Synthetic failure'):
        module.evaluate(tmp_path)
    assert (tmp_path/'EVALUATION_STARTED.json').is_file()
    assert not (tmp_path/'results.json').exists()
    assert module.archive.read(tmp_path/'error.json')['confirmation_may_have_been_opened']
    with pytest.raises(ValueError, match='prior confirmation attempt'):
        module.evaluate(tmp_path)
    assert accesses == [True]
