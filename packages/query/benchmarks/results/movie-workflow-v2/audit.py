"""Reconstruct this fixed study from retained records, using only the standard library."""

import hashlib
import json
import math
import statistics
import tarfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def equivalent(actual, expected):
    assert len(actual) == len(expected)
    for a, b in zip(actual, expected):
        a, b = dict(a), dict(b)
        for name in ('shared_cast', 'affinity'):
            x, y = dict(a.pop(name)), dict(b.pop(name))
            sx, sy = x.pop('score'), y.pop('score')
            assert x == y and math.isclose(sx, sy, rel_tol=1e-12, abs_tol=1e-12)
        assert a == b


def audit(folder):
    path = folder / 'evidence.tar.gz'
    with tarfile.open(path) as archive:
        payloads = {}
        for member in archive:
            assert member.isfile() and not member.name.startswith('/')
            assert '..' not in Path(member.name).parts and member.name not in payloads
            payloads[member.name] = archive.extractfile(member).read()
    def read(name):
        return json.loads(payloads[name])

    manifest = read('manifest.json')
    assert digest(payloads['manifest.json']) == '14e36defbafcd71e549aae278daa2913c90ee8684520cdf17de3e9039fc244ee'
    for name, value in manifest['files'].items():
        if name == 'movies.cypher':
            assert value == '7be04aba2193790e0051308e6aa8550236e651cae652ea7da44b7dc01f4c4e69'
            continue  # Original upstream source is downloaded on demand, not redistributed.
        assert digest(payloads[name]) == value, name
    expected, published = read('expected.json'), read('results.json')
    assert published == json.loads((folder / 'results.json').read_text())
    records = []
    assert len(manifest['jobs']) == 63
    for index, job in enumerate(manifest['jobs']):
        r = read(f'workers/{index:03d}.json')
        assert r['job'] == job and len(r['samples']) == 7
        equivalent(r['output'], expected[job['workload']]['records'])
        assert digest(json.dumps(r['output'], sort_keys=True, allow_nan=False).encode()) == r['output_sha256']
        for sample in [r['first'], *r['samples']]:
            assert all(math.isfinite(x) and x >= 0 for x in sample.values())
            assert math.isclose(sample['total_seconds'], sum(sample[k] for k in
                ('query_transfer_seconds', 'local_materialize_seconds', 'json_seconds')), abs_tol=1e-9)
        assert statistics.median(s['total_seconds'] for s in r['samples']) == r['median_seconds']
        setup = sum(r[k] for k in ('connection_seconds', 'snapshot_export_seconds', 'preparation_seconds'))
        assert r['first_use_seconds'] + 1e-9 >= setup + r['first']['total_seconds']
        assert r['subprocess_wall_seconds'] >= r['first_use_seconds']
        records.append(r)
    assert not any(name.startswith('workers/') and name.endswith('-error.json') for name in payloads)
    conditions = []
    for condition in published['conditions']:
        name = condition['workload']
        arms = {}
        for arm, reported in condition['arms'].items():
            selected = sorted((r for r in records if r['job']['arm'] == arm
                and r['job']['workload'] == name), key=lambda r: r['job']['replicate'])
            assert [r['job']['replicate'] for r in selected] == [0, 1, 2]
            request = [r['median_seconds'] * 1000 for r in selected]
            first = [r['first_use_seconds'] * 1000 for r in selected]
            assert math.isclose(statistics.median(request), reported['request_ms'], abs_tol=1e-12)
            assert math.isclose(statistics.median(first), reported['first_use_ms'], abs_tol=1e-12)
            arms[arm] = {**reported, 'process_request_medians_ms': request, 'process_first_use_ms': first}
        best = min(('native_cypher', 'manual_intersection', 'full_source_shared'),
                   key=lambda arm: arms[arm]['request_ms'])
        ratio = arms[best]['request_ms'] / arms['plan']['request_ms']
        assert best == condition['strongest_ondemand'] and ratio == condition['plan_speedup']
        conditions.append({**condition, 'arms': arms})
    cpu = [r[t]['aggregate_process_cpu_percent'] for r in records
           for t in ('activity_before', 'activity_after')]
    return {
        'verified': True, 'archive_sha256': digest(path.read_bytes()),
        'manifest_sha256': digest(payloads['manifest.json']),
        'archive_files': len(payloads), 'checked_clients': len(records),
        'measured_calls': len(records) * 8, 'new_measurements': False,
        'campaign': read('workers/campaign.json'), 'conditions': conditions,
        'host_context': {
            'requested_label': 'quiet-window',
            'observed': 'substantial background activity; not an isolated latency measurement',
            'aggregate_process_cpu_percent_min_median_max': [min(cpu), statistics.median(cpu), max(cpu)],
            'aggregate_cpu_definition': 'Summed per-process CPU percentages; 100% is approximately one logical CPU, not the whole Mac.',
        },
        'total_subprocess_wall_seconds': sum(r['subprocess_wall_seconds'] for r in records),
        'release_gate_complete': False,
    }


if __name__ == '__main__':
    print(json.dumps(audit(Path(__file__).resolve().parent), indent=2, sort_keys=True, allow_nan=False))
