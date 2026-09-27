"""Check attribution against explicit overlapping multi-process timelines."""

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1]/'benchmarks/v1/quail_trace_audit.py'
spec = importlib.util.spec_from_file_location('trace_audit', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def event(name, category, begin, duration, pid=7):
    return {'ph': 'X', 'name': name, 'cat': category, 'ts': begin*1e6,
            'dur': duration*1e6, 'pid': pid, 'tid': 1}


def trace(path, base, events):
    with gzip.open(path, 'wt') as file:
        json.dump({'baseTimeNanoseconds': base, 'traceEvents': events}, file)


@pytest.fixture
def captured(tmp_path):
    record = {'arm': 'vllm', 'timing_claim': False, 'all_reference_decisions_match': True,
              'start_unix_ns': 1_000_000_000, 'end_unix_ns': 11_000_000_000,
              'instrumented_graph_seconds': 10, 'driver_trace': 'driver.json.gz',
              'driver_pid': 1, 'worker_traces': ['worker.json.gz'], 'workers': [{'pid': 7}]}
    (tmp_path/'profile.json').write_text(json.dumps(record))
    trace(tmp_path/'driver.json.gz', 1_000_000_000, [
        event('orbweaver.graph', 'user_annotation', 0, 10, pid=1),
        event('unrelated driver kernel', 'kernel', 0, 10, pid=1)])
    # Worker timestamps have a different base. Events use absolute seconds here;
    # the query window is [1, 11]. Concurrent kernels overlap rather than add.
    trace(tmp_path/'worker.json.gz', 0, [
        event('clipped kernel', 'kernel', .5, 2),
        event('kernel a', 'kernel', 3, 3),
        event('kernel b', 'kernel', 5, 3),
        event('copy', 'gpu_memcpy', 9, 1),
        event('later work', 'kernel', 11, 5),
        event('orbweaver.scheduler.schedule', 'user_annotation', 2, 2),
        event('orbweaver.scheduler.schedule', 'user_annotation', 8, 2)])
    return tmp_path


def test_clips_aligns_merges_and_ignores_driver_gpu_activity(captured):
    result = audit.analyze(captured)
    assert result['gpu_active_union_seconds'] == pytest.approx(7.5)
    assert result['no_gpu_activity_seconds'] == pytest.approx(2.5)
    assert result['gpu_active_fraction'] == pytest.approx(.75)
    assert result['scheduler_scopes']['orbweaver.scheduler.schedule'] == {
        'elapsed_union_seconds': 4, 'overlap_gpu_active_seconds': 2.5,
        'overlap_no_gpu_activity_seconds': 1.5}
    assert result['timing_claim'] is False


@pytest.mark.parametrize('change', ['absent_gpu', 'absent_scheduler', 'wrong_scheduler_pid', 'negative_duration'])
def test_rejects_incomplete_or_inconsistent_worker_trace(captured, change):
    path = captured/'worker.json.gz'
    with gzip.open(path, 'rt') as file:
        data = json.load(file)
    events = data['traceEvents']
    if change == 'absent_gpu':
        events = [e for e in events if e['cat'] == 'user_annotation']
    elif change == 'absent_scheduler':
        events = [e for e in events if e['cat'] != 'user_annotation']
    elif change == 'wrong_scheduler_pid':
        events[-1]['pid'] = 8
    else:
        events[0]['dur'] = -1
    trace(path, 0, events)
    with pytest.raises(ValueError):
        audit.analyze(captured)


def test_rejects_failed_capture_or_unverified_answers(captured):
    (captured/'failure.json').write_text('{}')
    with pytest.raises(ValueError, match='failed capture'):
        audit.analyze(captured)
    (captured/'failure.json').unlink()
    path = captured/'profile.json'
    data = json.loads(path.read_text())
    data['all_reference_decisions_match'] = False
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='preserve the reference'):
        audit.analyze(captured)


def test_quail_uses_same_process_trace(captured):
    path = captured/'profile.json'
    data = json.loads(path.read_text())
    data.update(arm='quail', worker_traces=[], workers=[])
    path.write_text(json.dumps(data))
    result = audit.analyze(captured)
    assert result['gpu_active_union_seconds'] == 10
    assert result['scheduler_scopes'] == {}
