"""Recompute resource-probe findings from frozen manifests and raw checkpoints."""

import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(root):
    cases = [('initial', 'grouped'), ('initial', 'separate'),
             ('retention/default', 'grouped'), ('retention/retained', 'grouped')]
    stages = ['projected', *[f'standalone-{i}' for i in range(1, 6)], 'fitted',
              *[f'prediction-{i}' for i in range(1, 6)]]
    if read(root/'initial/terminal.json') != [{'mode': m, 'returncode': 0} for m in ('grouped', 'separate')]:
        raise ValueError('Initial probe did not finish both conditions successfully')
    if read(root/'retention/terminal.json') != [
            {'condition': c, 'returncode': 0} for c in ('default', 'retained')]:
        raise ValueError('Retention probe did not finish both conditions successfully')
    reports, reference = [], None
    manifests = {}
    for location, mode in cases:
        run = root/location
        manifest = read(run/'manifest.json')
        if (manifest['format'] != 'orbweaver-gds-memory-probe-v1'
                or [manifest[k] for k in ('nodes', 'heads', 'requests', 'heap_megabytes')] != [96, 4, 5, 8192]
                or manifest['timing_claim'] is not False or manifest['confirmation_contents_read'] is not False):
            raise ValueError('Probe does not match the bounded resource protocol')
        for name, expected in manifest['files'].items():
            if digest(run/name) != expected:
                raise ValueError('Frozen source changed')
        manifests[location] = manifest
        child = run/mode
        result = read(child/'result.json')
        if (result['mode'] != mode or result['requests'] != 5 or result['repeated_outputs_equal'] is not True
                or (child/'failure.json').exists()
                or result['versions'] != {'neo4j': '2026.09.0', 'gds': '2026.09.0'}):
            raise ValueError('Missing or failed probe result')
        reservations, heap = [], []
        for i, stage in enumerate(stages):
            record = read(child/f'checkpoint-{i:02d}.json')
            if record['stage'] != stage or record['progress'] != [] or len(record['summary']) != 1:
                raise ValueError('Checkpoint missing or tasks remain active')
            summary = record['summary'][0]
            graph_records = [r for r in record['memory'] if r['entity'] == 'graph' and r['name'] == 'graph']
            task_records = [r for r in record['memory'] if r not in graph_records]
            if (len(graph_records) != 1 or graph_records[0]['memoryInBytes'] != summary['totalGraphsMemory']
                    or sum(r['memoryInBytes'] for r in task_records) != summary['totalTasksMemory']):
                raise ValueError('Reservation detail and summary disagree')
            reservations.append(summary['totalTasksMemory'])
            properties = record['jvm_heap'][0]['heap']['value']['properties']
            if properties['max'] != 8192*1024**2:
                raise ValueError('JVM heap limit differs')
            heap.append(properties['used'])
        for i in range(1, 6):
            request = read(child/f'request-{i:02d}.json')
            if reference is None:
                reference = request['output']
            if request['output'] != reference:
                raise ValueError('Repeated or independently fitted probe outputs differ')
        retention = manifest.get('gds_progress_retention_seconds', 0)
        if location.startswith('retention/'):
            settings = {r['name']: r['value'] for r in read(child/'settings.json')}
            if (settings['gds.progress_tracking_enabled'] != 'true'
                    or settings['gds.progress_tracking_retention_period'] != ('1m' if retention == 60 else '0s')):
                raise ValueError('Effective GDS task settings differ')
        reports.append({'condition': location+'/'+mode, 'retention_seconds': retention,
            'task_reservations_bytes': dict(zip(stages, reservations)),
            'standalone_reservation_deltas': [b-a for a, b in zip(reservations[:5], reservations[1:6])],
            'prediction_reservation_deltas': [b-a for a, b in zip(reservations[6:11], reservations[7:12])],
            'observed_heap_used_bytes': {'minimum': min(heap), 'maximum': max(heap)},
            'no_active_tasks_at_checkpoints': True, 'all_outputs_equal_reference': True})
    a, b = (dict(manifests['retention/'+key]) for key in ('default', 'retained'))
    if (a.pop('gds_progress_retention_seconds') != 0 or b.pop('gds_progress_retention_seconds') != 60 or a != b):
        raise ValueError('Fresh controls differ beyond their retention setting')
    zero = reports[0]['task_reservations_bytes']
    if any(report['task_reservations_bytes'] != zero for report in reports[1:3]):
        raise ValueError('Zero-retention resource reproductions differ')
    if any(reports[3]['task_reservations_bytes'].values()):
        raise ValueError('Reservations remain with deferred cleanup')
    return {'format': 'orbweaver-gds-memory-audit-v1', 'verified_conditions': 4, 'verified_request_outputs': 20,
            'conditions': reports, 'outputs_sha256': hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest(),
            'scope': '96-node resource reproduction; no application-quality, performance or full-graph stability claim'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root.resolve()), indent=2, sort_keys=True, allow_nan=False))
