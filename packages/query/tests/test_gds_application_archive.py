"""Integrity, completeness and safe restoration for recommendation evidence."""

import importlib.util
import copy
import io
import json
import tarfile
from pathlib import Path

import pytest


@pytest.fixture
def archive_module():
    path = Path(__file__).resolve().parents[1]/'benchmarks/v1/gds_application_archive.py'
    spec = importlib.util.spec_from_file_location('gds_archive_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, data):
    path.write_text(json.dumps(data, sort_keys=True)+'\n')


@pytest.fixture
def run(tmp_path, archive_module):
    """Tiny synthetic envelope; tests integrity, not numerical prediction quality."""
    root = tmp_path/'run'
    root.mkdir()
    (root/'workers').mkdir()
    runner = root/'gds_application.py'
    runner.write_text('# Synthetic archive fixture, never executed.\n')
    jobs = [{'dataset': d, 'threads': t, 'replicate': r}
            for d in archive_module.DATASETS for t in (1, 4) for r in range(3)]
    manifest = {'format': 'orbweaver-gds-application-v1', 'jobs': jobs,
                'files': {'gds_application.py': archive_module.digest(runner.read_bytes())},
                'arms': list(archive_module.REFERENCES), 'k': 16, 'samples': 3,
                'warmup': 1, 'ranking_precision': 12}
    write(root/'manifest.json', manifest)
    manifest_hash = archive_module.digest((root/'manifest.json').read_bytes())
    for index, job in enumerate(jobs):
        score = root/'workers'/f'{index:04d}-scores.npz'
        score.write_bytes(b'synthetic score-file bytes')
        records = [{'arm': arm, 'quality_reference': ref, 'output': [],
                    'samples_seconds': [.01, .02, .03]}
                   for arm, ref in archive_module.REFERENCES.items()]
        write(root/'workers'/f'{index:04d}.json', {'job': job, 'manifest_sha256': manifest_hash,
            'all_request_references_match': True, 'records': records,
            'full_scores_sha256': archive_module.digest(score.read_bytes())})
    write(root/'results.json', {'format': manifest['format'], 'verified_workers': 18,
        'per_arm_reference_match': True, 'manifest_sha256': manifest_hash,
        'outcomes': [{'dataset': d, 'threads': t, 'arm': a}
                     for d in archive_module.DATASETS for t in (1, 4) for a in manifest['arms']]})
    return root


def test_round_trip_preserves_bytes_and_keeps_summary_for_recomputation(tmp_path, run, archive_module):
    archive, restored = tmp_path/'archive', tmp_path/'restored'
    assert archive_module.pack(run, archive)['verified_workers'] == 18
    archive_module.restore(archive, restored)
    assert not (restored/'results.json').exists()
    assert (restored/'recorded-results.json').read_bytes() == (run/'results.json').read_bytes()
    for source in run.rglob('*'):
        if source.is_file() and source.name != 'results.json':
            assert (restored/source.relative_to(run)).read_bytes() == source.read_bytes()


@pytest.mark.parametrize('mutation', ('missing_arm', 'failed', 'bad_sample', 'wrong_reference',
                                     'changed_output', 'changed_scores', 'missing_outcome'))
def test_incomplete_or_changed_evidence_cannot_be_packed(tmp_path, run, archive_module, mutation):
    path = run/'workers/0000.json'
    worker = archive_module.read(path)
    if mutation == 'missing_arm':
        worker['records'].pop()
    elif mutation == 'failed':
        worker['all_request_references_match'] = False
    elif mutation == 'bad_sample':
        worker['records'][0]['samples_seconds'][0] = float('nan')
    elif mutation == 'wrong_reference':
        worker['records'][0]['quality_reference'] = 'gds'
    elif mutation == 'changed_output':
        worker['records'][0]['output'] = [{'head': 'changed'}]
    elif mutation == 'changed_scores':
        (run/'workers/0000-scores.npz').write_bytes(b'changed')
    else:
        summary = archive_module.read(run/'results.json')
        summary['outcomes'].pop()
        write(run/'results.json', summary)
    write(path, worker)
    with pytest.raises(ValueError):
        archive_module.pack(run, tmp_path/'archive')
    assert not (tmp_path/'archive').exists()


@pytest.mark.parametrize('name', ('../outside', '/outside', 'C:/outside', 'x/../outside',
                                 'x//outside', 'x/./outside', '.', 'recorded-results.json'))
def test_unsafe_archive_is_rejected_before_restore(tmp_path, archive_module, name):
    archive = tmp_path/'archive'
    archive.mkdir()
    raw = b'untrusted archive content'
    with tarfile.open(archive/'evidence.tar.gz', 'w:gz') as tar:
        member = tarfile.TarInfo(name)
        member.size = len(raw)
        tar.addfile(member, io.BytesIO(raw))
    write(archive/'ARCHIVE.json', {'format': 'orbweaver-gds-application-archive-v1',
        'verified_workers': 18, 'files': {name: archive_module.digest(raw)},
        'archive_sha256': archive_module.digest((archive/'evidence.tar.gz').read_bytes())})
    with pytest.raises(ValueError):
        archive_module.restore(archive, tmp_path/'restored')
    assert not (tmp_path/'restored').exists()


def test_corrupt_archive_payload_is_detected(tmp_path, run, archive_module):
    archive = tmp_path/'archive'
    archive_module.pack(run, archive)
    with (archive/'evidence.tar.gz').open('ab') as stream:
        stream.write(b'corruption')
    with pytest.raises(ValueError, match='checksum'):
        archive_module.verify(archive)


def interrupt_fixture(run, module):
    manifest = module.read(run/'manifest.json')
    (run/'results.json').unlink()
    for i in range(4, 18):
        (run/'workers'/f'{i:04d}.json').unlink()
        if i > 4:
            (run/'workers'/f'{i:04d}-scores.npz').unlink()
    write(run/'CANCELLATION.json', {
        'manifest_sha256': module.digest((run/'manifest.json').read_bytes()),
        'completed_workers': [0, 1, 2, 3], 'interrupted_worker': 4,
        'unattempted_workers': list(range(5, 18)), 'aggregate_timing_claim': False})
    write(run/'workers/0004-error.json', {'job': manifest['jobs'][4],
        'intentional_interruption': True, 'returncode': 130})


def test_interrupted_attempt_is_preserved_without_claiming_completion(tmp_path, run, archive_module):
    interrupt_fixture(run, archive_module)
    archive = tmp_path/'archive'
    result = archive_module.pack(run, archive, interrupted=True)
    assert result['verified_workers'] == 4
    assert result['status'].startswith('interrupted')
    archive_module.restore(archive, tmp_path/'restored')
    assert (tmp_path/'restored/CANCELLATION.json').read_bytes() == (run/'CANCELLATION.json').read_bytes()
    assert (tmp_path/'restored/workers/0004-scores.npz').exists()
    receipt = archive_module.read(archive/'ARCHIVE.json')
    receipt['format'] = 'orbweaver-gds-application-archive-v1'
    write(archive/'ARCHIVE.json', receipt)
    with pytest.raises(ValueError, match='format or worker count'):
        archive_module.verify(archive)


def test_unattempted_outputs_cannot_be_hidden_in_an_interrupted_archive(tmp_path, run, archive_module):
    interrupt_fixture(run, archive_module)
    (run/'workers/0008-console.txt').write_text('This job was actually attempted.')
    with pytest.raises(ValueError, match='unattempted worker'):
        archive_module.pack(run, tmp_path/'archive', interrupted=True)


@pytest.fixture
def run_v2(run, archive_module):
    manifest = archive_module.read(run/'manifest.json')
    manifest.update(format='orbweaver-gds-application-v2',
                    gds_request_strategy='singleton_adaptive_topk',
                    gds_progress_retention_seconds=60, confirmation_contents_read=False)
    write(run/'manifest.json', manifest)
    checksum = archive_module.digest((run/'manifest.json').read_bytes())
    specs = [{'ordinal': i, 'head': f'h{i}', 'source_label': f'OrbRankSource_{i}', 'candidates': 100}
             for i in range(64)]
    output = [{'head': s['head'], 'recommendations': []} for s in specs]
    for index in range(18):
        path = run/'workers'/f'{index:04d}.json'
        worker = archive_module.read(path)
        worker.update(manifest_sha256=checksum, candidate_count=6400,
                      setup_seconds={'gds_source_preparation': .1})
        for record in worker['records']:
            if record['quality_reference'] == 'gds':
                record['output'] = output
        worker['diagnostics'] = {
            'gds_settings': archive_module.GDS_SETTINGS, 'gds_source_specs': specs,
            'gds_requests': [{'stage': stage, 'output': output,
                'counters': {'rounds': 1, 'procedure_calls': 64,
                             'returned_pairs': 2048, 'max_top_n': 32}}
                for stage in archive_module.GDS_REQUEST_STAGES],
            'gds_checkpoints': [{'stage': stage, 'progress': [],
                'summary': [{'totalTasksMemory': 0, 'totalGraphsMemory': 1000}],
                'memory': [{'entity': 'graph', 'name': 'graph', 'memoryInBytes': 1000}]}
                for stage in archive_module.GDS_CHECKPOINT_STAGES]}
        write(path, worker)
    results = archive_module.read(run/'results.json')
    results.update(format=manifest['format'], manifest_sha256=checksum)
    write(run/'results.json', results)
    return run


def test_v2_round_trip_preserves_native_evidence(tmp_path, run_v2, archive_module):
    archive = tmp_path/'archive'
    assert archive_module.pack(run_v2, archive)['verified_workers'] == 18
    archive_module.restore(archive, tmp_path/'restored')
    for index in range(18):
        name = f'workers/{index:04d}.json'
        assert (tmp_path/'restored'/name).read_bytes() == (run_v2/name).read_bytes()


@pytest.mark.parametrize('mutation', ('setting', 'cost', 'missing_request', 'changed_warmup',
    'counter', 'counter_type', 'counter_bound', 'missing_checkpoint', 'active_task',
    'reservation', 'detailed_reservation', 'graph_memory', 'domain', 'source_order'))
def test_v2_rejects_hidden_native_work_or_unverified_requests(run_v2, archive_module, mutation):
    manifest = archive_module.read(run_v2/'manifest.json')
    worker = archive_module.read(run_v2/'workers/0000.json')
    original = copy.deepcopy(worker)
    d = worker['diagnostics']
    if mutation == 'setting':
        d['gds_settings']['gds.progress_tracking_retention_period'] = '0s'
    elif mutation == 'cost':
        worker['setup_seconds']['gds_source_preparation'] = 0
    elif mutation == 'missing_request':
        d['gds_requests'].pop(1)
    elif mutation == 'changed_warmup':
        d['gds_requests'][1]['output'].pop()
    elif mutation.startswith('counter'):
        d['gds_requests'][1]['counters']['procedure_calls'] = {
            'counter': 0, 'counter_type': True, 'counter_bound': 100000}[mutation]
    elif mutation == 'missing_checkpoint':
        d['gds_checkpoints'].pop()
    elif mutation == 'active_task':
        d['gds_checkpoints'][-1]['progress'] = [{'task': 'unfinished'}]
    elif mutation == 'reservation':
        d['gds_checkpoints'][-1]['summary'][0]['totalTasksMemory'] = 1
    elif mutation == 'detailed_reservation':
        d['gds_checkpoints'][-1]['memory'].append(
            {'entity': 'task', 'name': 'unfinished', 'memoryInBytes': 1})
    elif mutation == 'graph_memory':
        d['gds_checkpoints'][-1]['summary'][0]['totalGraphsMemory'] = 1001
    elif mutation == 'domain':
        d['gds_source_specs'][0]['candidates'] = 99
    elif mutation == 'source_order':
        d['gds_source_specs'].reverse()
    with pytest.raises(ValueError):
        archive_module.validate_worker(manifest, worker['manifest_sha256'], 0, worker)
    archive_module.validate_worker(manifest, original['manifest_sha256'], 0, original)
