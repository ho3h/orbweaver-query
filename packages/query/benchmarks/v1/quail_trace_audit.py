"""Attribute captured elapsed intervals without treating GPU idle time as causality."""

import argparse
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path


def merged(intervals):
    result = []
    for left, right in sorted(intervals):
        if result and left <= result[-1][1]:
            result[-1] = (result[-1][0], max(right, result[-1][1]))
        else:
            result.append((left, right))
    return result


def length(intervals):
    return sum(right-left for left, right in merged(intervals))


def overlap(first, second):
    first, second = merged(first), merged(second)
    i, j, total = 0, 0, 0.
    while i < len(first) and j < len(second):
        a, b = first[i]
        c, d = second[j]
        total += max(0., min(b, d)-max(a, c))
        if b <= d:
            i += 1
        else:
            j += 1
    return total


def events(path, start_ns, end_ns):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as file:
        trace = json.load(file)
    base = trace['baseTimeNanoseconds']
    if type(base) is not int:
        raise ValueError('Trace must record its epoch time base')
    left, right = (start_ns-base)/1000, (end_ns-base)/1000
    for event in trace['traceEvents']:
        if event.get('ph') != 'X':
            continue
        begin, duration = event['ts'], event['dur']
        if (type(begin) not in (int, float) or type(duration) not in (int, float)
                or not math.isfinite(begin) or not math.isfinite(duration) or duration < 0):
            raise ValueError('Invalid complete trace event')
        a, b = max(left, begin), min(right, begin+duration)
        if b > a:
            yield event, ((a-left)/1e6, (b-left)/1e6)


def analyze(root):
    if (root/'failure.json').exists():
        raise ValueError('A failed capture cannot establish a complete profile')
    record = json.loads((root/'profile.json').read_text())
    if record['timing_claim'] is not False or record['all_reference_decisions_match'] is not True:
        raise ValueError('Capture must preserve the reference and disclaim comparative timing')
    start, end = record['start_unix_ns'], record['end_unix_ns']
    if type(start) is not int or type(end) is not int or end <= start:
        raise ValueError('Invalid profile boundaries')
    duration = (end-start)/1e9
    if abs(duration-record['instrumented_graph_seconds']) > max(.05, duration*.001):
        raise ValueError('Trace clock disagrees with instrumented duration')
    driver = list(events(root/record['driver_trace'], start, end))
    graph = [(e, span) for e, span in driver if e.get('name') == 'orbweaver.graph']
    if len(graph) != 1 or str(graph[0][0]['pid']) != str(record['driver_pid']):
        raise ValueError('Missing or inconsistent driver graph boundary')
    if record['arm'] == 'vllm':
        if len(record['worker_traces']) != 1 or len(record['workers']) != 1:
            raise ValueError('Require one captured vLLM worker')
        model_events = list(events(root/record['worker_traces'][0], start, end))
    elif record['arm'] == 'quail' and not record['worker_traces']:
        model_events = driver
    else:
        raise ValueError('Unsupported capture layout')
    gpu = merged(span for event, span in model_events
                 if event.get('cat') in ('kernel', 'gpu_memcpy', 'gpu_memset'))
    if not gpu:
        raise ValueError('No model-process GPU activity in the declared interval')
    scopes = defaultdict(list)
    for event, span in model_events:
        name = event.get('name', '')
        if name.startswith('orbweaver.scheduler.'):
            if str(event['pid']) != str(record['workers'][0]['pid']):
                raise ValueError('Scheduler trace belongs to an unexpected process')
            scopes[name].append(span)
    if record['arm'] == 'vllm' and 'orbweaver.scheduler.schedule' not in scopes:
        raise ValueError('Worker trace is missing scheduler instrumentation')
    active = length(gpu)
    return {'arm': record['arm'], 'captured_seconds': duration, 'gpu_active_union_seconds': active,
        'no_gpu_activity_seconds': duration-active, 'gpu_active_fraction': active/duration,
        'scheduler_scopes': {name: {'elapsed_union_seconds': length(spans),
            'overlap_gpu_active_seconds': overlap(spans, gpu),
            'overlap_no_gpu_activity_seconds': length(spans)-overlap(spans, gpu)}
            for name, spans in sorted(scopes.items())},
        'timing_claim': False,
        'scope': 'instrumented graph interval; activity is not MFU and overlap does not establish causality'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.capture), indent=2, sort_keys=True, allow_nan=False))
