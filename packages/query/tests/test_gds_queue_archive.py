"""Archives must preserve failure accounting rather than manufacture completeness."""

import importlib
import json
from pathlib import Path

import pytest


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True)+'\n')


@pytest.fixture
def archive_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'benchmarks/v1'))
    return importlib.import_module('gds_queue_archive')


def make_suite(run, module, failed=False):
    run.mkdir()
    (run/'frozen.py').write_text('# source\n')
    jobs, cases = [], []
    for dataset in ('collaboration', 'friendship', 'communication'):
        for threads in (1, 4):
            child = run/f'{dataset}-t{threads}'
            child.mkdir()
            (child/'scores.npz').write_bytes(b'envelope fixture, not numerical evidence')
            (child/'console.txt').write_text('terminal worker\n')
            manifest = {'format': 'orbweaver-gds-queue-diagnostic-v2', 'files': {},
                        'dataset': dataset, 'threads': threads, 'k': 16, 'warmup': 1, 'samples': 3}
            write(child/'manifest.json', manifest)
            job = {'dataset': dataset, 'threads': threads, 'directory': child.name,
                   'manifest_sha256': module.digest((child/'manifest.json').read_bytes())}
            jobs.append(job)
            if failed and len(jobs) == 1:
                write(child/'worker-error.json', {'job': job, 'returncode': 1})
                continue
            result = {**{k: manifest[k] for k in ('format', 'dataset', 'threads')},
                      'manifest_sha256': job['manifest_sha256'],
                      'full_scores_sha256': module.digest((child/'scores.npz').read_bytes()),
                      'all_outputs_match_complete_score_reference': True,
                      'single_process_diagnostic': True, 'confirmation_contents_read': False,
                      'records': [{'arm': arm, 'samples_seconds': samples, 'counters': [{}, {}, {}],
                                   'output': []} for arm, samples in
                                  [('global', [4, 5, 6]), ('partitioned', [1, 2, 3])]],
                      'raw_score_quality': {'metrics': {'recall': 0.5}}, 'deterministic_id_recall16': 0.5,
                      'setup_seconds': {'fit': 1},
                      'model_training': [{'modelInfo': {'bestParameters': {'method': 'LogisticRegression'}}}]}
            write(child/'results.json', result)
            cases.append({'dataset': dataset, 'threads': threads,
                          'median_seconds': {'global': 5, 'partitioned': 2}, 'global_over_partitioned': 2.5,
                          'raw_score_quality': result['raw_score_quality']['metrics'],
                          'deterministic_id_recall16': 0.5, 'setup_seconds': result['setup_seconds'],
                          'selected_classifier': result['model_training'][0]['modelInfo']['bestParameters'],
                          'partitioned_counters': [{}, {}, {}]})
    suite = {'format': 'orbweaver-gds-queue-suite-v1', 'jobs': jobs,
             'files': {'frozen.py': module.digest((run/'frozen.py').read_bytes())},
             'confirmation_contents_read': False, 'one_process_per_condition': True}
    write(run/'suite.json', suite)
    identity = module.digest((run/'suite.json').read_bytes())
    if failed:
        write(run/'ATTEMPT.json', {'format': 'orbweaver-gds-queue-failed-attempt-v1',
              'suite_sha256': identity, 'aggregate_timing_claim': False, 'confirmation_contents_read': False,
              'completed_conditions': [j['directory'] for j in jobs[1:]],
              'failed_conditions': [jobs[0]['directory']], 'unattempted_conditions': []})
    else:
        write(run/'summary.json', {'format': suite['format'], 'suite_sha256': identity,
              'verified_conditions': 6, 'conditions': cases, 'confirmation_contents_read': False})


@pytest.mark.parametrize('failed', [False, True])
def test_suite_roundtrip_keeps_failure_status_and_requires_numerical_replay(tmp_path, archive_module, failed):
    run, archive, restored = (tmp_path/name for name in ('run', 'archive', 'restored'))
    make_suite(run, archive_module, failed)
    checked = archive_module.pack(run, archive, suite=True, failed=failed)
    assert 'numerical replay remains separate' in checked['scope']
    assert archive_module.restore(archive, restored) == checked
    if failed:
        assert checked['failed_conditions'] == ['collaboration-t1']
        assert len(checked['completed_conditions']) == 5
        assert (restored/'collaboration-t1/worker-error.json').exists()
        assert not (restored/'summary.json').exists()
    else:
        assert checked['verified_conditions'] == 6
        assert (restored/'recorded-summary.json').exists()
        assert not (restored/'summary.json').exists()


@pytest.mark.parametrize('corruption', ['missing_terminal', 'two_terminals', 'misidentified_error', 'false_summary'])
def test_failed_suite_cannot_hide_incomplete_or_conflicting_outcomes(tmp_path, archive_module, corruption):
    run, archive = tmp_path/'run', tmp_path/'archive'
    make_suite(run, archive_module, failed=True)
    child = run/'collaboration-t1'
    if corruption == 'missing_terminal':
        (child/'worker-error.json').unlink()
    elif corruption == 'two_terminals':
        write(child/'results.json', {})
    elif corruption == 'misidentified_error':
        error = archive_module.read(child/'worker-error.json')
        error['job']['threads'] = 4
        write(child/'worker-error.json', error)
    else:
        write(run/'summary.json', {'verified_conditions': 6})
    with pytest.raises(ValueError):
        archive_module.pack(run, archive, suite=True, failed=True)
    assert not archive.exists()


@pytest.mark.parametrize('corruption', ['source', 'timing', 'error'])
def test_complete_suite_rejects_changed_source_summary_or_failed_case(tmp_path, archive_module, corruption):
    run, archive = tmp_path/'run', tmp_path/'archive'
    make_suite(run, archive_module)
    if corruption == 'source':
        (run/'frozen.py').write_text('# changed\n')
    elif corruption == 'timing':
        summary = archive_module.read(run/'summary.json')
        summary['conditions'][0]['global_over_partitioned'] = 100
        write(run/'summary.json', summary)
    else:
        write(run/'collaboration-t1/worker-error.json', {'returncode': 1})
    with pytest.raises(ValueError):
        archive_module.pack(run, archive, suite=True)
    assert not archive.exists()
