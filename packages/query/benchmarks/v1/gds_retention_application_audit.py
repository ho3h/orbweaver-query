"""Replay full-graph resource checks using saved scores and raw graph edges.

No database or scoring implementation is imported. The audit reconstructs the
candidate domain, rankings and development metrics independently of the worker.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_files(root, files):
    for name, expected in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.as_posix() != name:
            raise ValueError('Unsafe frozen path')
        if digest(root/name) != expected:
            raise ValueError(f'Frozen input changed: {name}')


def reference(run):
    import numpy as np

    with np.load(run/'graph.npz', allow_pickle=False) as graph:
        ids, triples = graph['node_ids'], graph['triples']
    with np.load(run/'development.npz', allow_pickle=False) as data:
        sources, positives = data['sources'], data['positives']
    if len(ids) != 5242 or len(sources) != 64 or len(set(sources)) != 64 or len(positives) != 46:
        raise ValueError('Original collaboration development domain differs')
    adjacency = [set() for _ in ids]
    for head, _, target in triples:
        adjacency[head].add(int(target))
        adjacency[target].add(int(head))
    mask = np.ones((len(sources), len(ids)), dtype=bool)
    for row, head in enumerate(sources):
        mask[row, [int(head), *adjacency[head]]] = False
    with np.load(run/'grouped/scores.npz', allow_pickle=False) as data:
        scores = data['scores']
    with np.load(run/'previous-scores.npz', allow_pickle=False) as data:
        previous = data['scores']
    for values in (scores, previous):
        if (values.shape != mask.shape or not np.array_equal(np.isfinite(values), mask)
                or np.any((values[mask] < 0) | (values[mask] > 1))):
            raise ValueError('Incomplete or invalid candidate probabilities')
    outputs = []
    for row, head in enumerate(sources):
        values = sorted(((-round(float(scores[row, target]), 12), str(ids[target]))
                         for target in np.flatnonzero(mask[row])))[:16]
        outputs.append({'head': str(ids[head]), 'recommendations': [
            {'target': target, 'score': -score} for score, target in values]})
    source_rows = {int(head): row for row, head in enumerate(sources)}
    ordered = [np.sort(scores[row, mask[row]]) for row in range(len(sources))]
    outcomes = []
    for head, target in positives:
        head, target = int(head), int(target)
        row = source_rows[head]
        if not mask[row, target]:
            raise ValueError('Development positive outside the candidate domain')
        value = scores[row, target]
        left, right = np.searchsorted(ordered[row], value, side='left'), np.searchsorted(
            ordered[row], value, side='right')
        tied, greater = int(right-left), len(ordered[row])-int(right)
        rank = 1+greater+(tied-1)/2
        outcomes.append({'head': head, 'target': target, 'supported': True, 'rank': rank,
                         'recall16': min(1., max(0., (16-greater)/tied)),
                         'recall64': min(1., max(0., (64-greater)/tied)),
                         'reciprocal_rank': 1/rank})
    quality = {'outcomes': outcomes, 'positive_queries': len(outcomes), 'metrics': {
        key: float(np.mean([row[key] for row in outcomes]))
        for key in ('recall16', 'recall64', 'reciprocal_rank', 'supported')}}
    return {'output': outputs, 'candidate_count': int(mask.sum()), 'raw_quality': quality,
            'prior_max_absolute_score_difference': float(np.max(np.abs(scores[mask]-previous[mask])))}


def summarize(root):
    suite = read(root/'suite.json')
    cases = [('collaboration-t1', 1), ('collaboration-t4', 4)]
    if (suite['format'] != 'orbweaver-gds-retention-application-suite-v1'
            or [(c['directory'], c['threads']) for c in suite['conditions']] != cases
            or suite['timing_claim'] is not False or suite['confirmation_contents_read'] is not False):
        raise ValueError('Unexpected application diagnostic suite')
    if read(root/'terminal.json') != [{'condition': name, 'returncode': 0} for name, _ in cases]:
        raise ValueError('Both declared processes must terminate successfully')
    reports = []
    stages = ['projected', 'fitted', 'full-score-reference',
              *[f'prediction-{i}' for i in range(1, 6)], 'after-retention-expiry']
    for case in suite['conditions']:
        run = root/case['directory']
        if digest(run/'manifest.json') != case['manifest_sha256']:
            raise ValueError('Condition manifest changed')
        manifest = read(run/'manifest.json')
        if (manifest['format'] != 'orbweaver-gds-retention-application-v1'
                or manifest['dataset'] != 'collaboration' or manifest['threads'] != case['threads']
                or [manifest[k] for k in ('requests', 'heap_megabytes', 'gds_progress_retention_seconds',
                                         'cleanup_wait_seconds')] != [5, 8192, 60, 65]
                or manifest['modes'] != ['grouped'] or manifest['timing_claim'] is not False
                or manifest['confirmation_contents_read'] is not False):
            raise ValueError('Condition does not follow the resource protocol')
        frozen_files(run, manifest['files'])
        previous = read(run/'previous-manifest.json')
        failure = read(run/'previous-worker-error.json')
        if (digest(run/'previous-manifest.json') != manifest['previous_manifest_sha256']
                or digest(run/'previous-scores.npz') != manifest['previous_score_sha256']
                or manifest['gds_config'] != previous['gds_config']
                or manifest['runtime_identity'] != previous['runtime_identity']
                or manifest['native_runtime'] != previous['runtime_identity']['architecture']
                or manifest['threads'] != previous['threads']):
            raise ValueError('Configuration differs from the original failed condition')
        if (failure['returncode'] != 1 or failure['job']['directory'] != case['directory']
                or failure['job']['manifest_sha256'] != manifest['previous_manifest_sha256']):
            raise ValueError('Previous failure provenance differs')
        for name, checksum in previous['files'].items():
            if name.startswith('source/') or name in ('graph.npz', 'development.npz', 'gds_ranking.py',
                                                       'gds_quality.py', 'structural_neo4j.py'):
                if manifest['files'].get(name) != checksum:
                    raise ValueError('Original application inputs or model implementation changed')
        child = run/'grouped'
        result = read(child/'result.json')
        if (result['mode'] != 'grouped' or result['requests'] != 5 or result['threads'] != case['threads']
                or result['repeated_outputs_equal'] is not True or result['full_score_reference_checked'] is not True
                or result['versions'] != {'neo4j': '2026.09.0', 'gds': '2026.09.0'}
                or (child/'failure.json').exists() or not (run/'console.txt').is_file()):
            raise ValueError('Missing or conflicting condition outcome')
        settings = {r['name']: r['value'] for r in read(child/'settings.json')}
        if settings != {'gds.progress_tracking_enabled': 'true', 'gds.progress_tracking_retention_period': '1m'}:
            raise ValueError('Effective GDS retention settings differ')
        training = read(child/'model-training.json')
        if len(training) != 1:
            raise ValueError('Expected one completed native model fit')
        trained = training[0]
        if (trained['configuration']['concurrency'] != case['threads']
                or trained['configuration']['randomSeed'] != 71
                or len(trained['modelSelectionStats']['modelCandidates']) != 2):
            raise ValueError('Native model selection contract differs')
        steps = {r['name']: r['config'] for r in trained['modelInfo']['nodePropertySteps']}
        if (set(steps) != {'gds.fastRP.mutate', 'gds.degree.mutate'}
                or steps['gds.fastRP.mutate']['embeddingDimension'] != 256
                or any(r['concurrency'] != case['threads'] for r in steps.values())):
            raise ValueError('Native feature pipeline differs')
        expected = reference(run)
        if read(child/'full-score-reference.json') != expected:
            raise ValueError('Full-score ranking, quality or prior difference does not reproduce')
        names = {p.name for p in child.glob('request-*.json')}
        if names != {f'request-{i:02d}.json' for i in range(1, 6)}:
            raise ValueError('Missing or unexpected repeated request')
        counters = []
        for i in range(1, 6):
            request = read(child/f'request-{i:02d}.json')
            if request['output'] != expected['output']:
                raise ValueError('Repeated native output differs from independently ranked full scores')
            count = request['counters']
            if (set(count) != {'rounds', 'procedure_calls', 'returned_pairs', 'max_top_n'}
                    or any(type(v) is not int or v <= 0 for v in count.values())
                    or count['procedure_calls'] < 64 or count['max_top_n'] > 5241):
                raise ValueError('Invalid adaptive-request counters')
            counters.append(count)
        if {p.name for p in child.glob('checkpoint-*.json')} != {
                f'checkpoint-{i:02d}.json' for i in range(len(stages))}:
            raise ValueError('Missing or unexpected resource checkpoint')
        heaps, completed = [], []
        for i, stage in enumerate(stages):
            record = read(child/f'checkpoint-{i:02d}.json')
            if (record['stage'] != stage or record['progress'] != [] or len(record['summary']) != 1
                    or record['summary'][0]['totalTasksMemory'] != 0):
                raise ValueError('Active work or unreleased reservations at checkpoint')
            graphs = [r for r in record['memory'] if r['entity'] == 'graph' and r['name'] == 'graph']
            tasks = [r for r in record['memory'] if r not in graphs]
            if (len(graphs) != 1 or graphs[0]['memoryInBytes'] != record['summary'][0]['totalGraphsMemory']
                    or any(r['memoryInBytes'] for r in tasks)):
                raise ValueError('Memory summary and detailed reservations disagree')
            properties = record['jvm_heap'][0]['heap']['value']['properties']
            if properties['max'] != 8192*1024**2 or not 0 <= properties['used'] <= properties['max']:
                raise ValueError('Unexpected JVM heap limit or observation')
            heaps.append(properties['used'])
            count = record['completed_task_count']
            if type(count) is not int or count < 0:
                raise ValueError('Invalid completed task count')
            completed.append(count)
        if completed[-1] != 0:
            raise ValueError('Completed task records did not expire')
        reports.append({'condition': case['directory'], 'threads': case['threads'],
            'selected_method': trained['modelInfo']['bestParameters']['methodName'],
            'candidate_count': expected['candidate_count'], 'positive_queries': expected['raw_quality']['positive_queries'],
            'quality_metrics': expected['raw_quality']['metrics'], 'recomputed_request_outputs': 5,
            'scores_sha256': digest(child/'scores.npz'), 'model_training_sha256': digest(child/'model-training.json'),
            'output_sha256': hashlib.sha256(json.dumps(expected['output'], sort_keys=True).encode()).hexdigest(),
            'prior_max_absolute_score_difference': expected['prior_max_absolute_score_difference'],
            'request_counters': counters, 'zero_task_reservations_at_all_checkpoints': True,
            'no_active_tasks_at_all_checkpoints': True, 'completed_tasks_by_stage': dict(zip(stages, completed)),
            'observed_heap_used_bytes': {'minimum': min(heaps), 'maximum': max(heaps)}})
    return {'format': 'orbweaver-gds-retention-application-audit-v1', 'suite_sha256': digest(root/'suite.json'),
        'verified_conditions': 2, 'verified_request_outputs': 10, 'conditions': reports,
        'cross_condition_outputs_equal': reports[0]['output_sha256'] == reports[1]['output_sha256'],
        'timing_claim': False, 'confirmation_contents_read': False,
        'scope': 'bounded original-workload resource/correctness check; no timing or long-running stability claim'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root.resolve()), indent=2, sort_keys=True, allow_nan=False))
