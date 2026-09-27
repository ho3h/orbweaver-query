"""Identify global topN queue overhead using exact native per-source requests."""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import gds_quality
import gds_ranking as ranking
from structural_neo4j import checked, import_graph, read, runtime_identity, sha, write


DATASETS = ('collaboration', 'friendship', 'communication')


def freeze(run, reference, dataset='friendship', threads=1):
    if dataset not in DATASETS or type(threads) is not int or threads not in (1, 4):
        raise ValueError('Requires a declared graph family and one/four threads')
    original = checked(reference)
    previous_index = next((i for i, job in enumerate(original['jobs'])
        if job['dataset'] == dataset and job['threads'] == threads
        and (reference/f'workers/{i:04d}.json').is_file()), None)
    if previous_index is not None:
        previous = read(reference/f'workers/{previous_index:04d}.json')
        if previous['manifest_sha256'] != sha(reference/'manifest.json'):
            raise ValueError('Prior worker belongs to another manifest')
        if sha(reference/f'workers/{previous_index:04d}-scores.npz') != previous['full_scores_sha256']:
            raise ValueError('Prior raw scores changed')
    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[2]
    shutil.copytree(package/'src/orbweaver_query', run/'source/orbweaver_query',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('gds_queue_diagnostic.py', 'gds_quality.py', 'gds_ranking.py',
                 'structural_neo4j.py', 'GDS_QUEUE_DIAGNOSTIC.md', 'GDS_QUEUE_GENERALIZATION.md'):
        shutil.copyfile(Path(__file__).with_name(name), run/name)
    shutil.copyfile(package/'tools/disposable_neo4j.py', run/'disposable_neo4j.py')
    shutil.copyfile(reference/f'{dataset}-outer.npz', run/'graph.npz')
    shutil.copyfile(reference/f'{dataset}-development.npz', run/'development.npz')
    if previous_index is not None:
        shutil.copyfile(reference/f'workers/{previous_index:04d}.json', run/'previous-worker.json')
        shutil.copyfile(reference/f'workers/{previous_index:04d}-scores.npz', run/'previous-scores.npz')
    config_name = original['gds_selection'][dataset]
    write(run/'manifest.json', {'format': 'orbweaver-gds-queue-diagnostic-v2',
        'files': {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file()},
        'runtime_identity': original['runtime_identity'], 'reference_manifest_sha256': sha(reference/'manifest.json'),
        'dataset': dataset, 'threads': threads, 'previous_worker_index': previous_index,
        'gds_config_name': config_name, 'gds_config': gds_quality.GDS_CONFIGS[config_name], 'k': 16,
        'arms': ['global', 'partitioned'], 'warmup': 1, 'samples': 3, 'order_seed': 7620,
        'heap_megabytes': 8192, 'neo4j_version': '2026.09.0', 'gds_version': '2026.09.0',
        'confirmation_contents_read': False, 'timing_scope': 'single-process descriptive diagnostic'})
    return {'manifest_sha256': sha(run/'manifest.json')}


def worker(run, neo4j_home, java, gds_jar):
    sys.path.insert(0, str(run/'source'))
    sys.path.insert(0, str(run))
    import numpy as np
    from disposable_neo4j import disposable_database
    from neo4j import GraphDatabase
    from orbweaver_query import GraphSnapshot
    from orbweaver_query.neo4j import Neo4jSource

    manifest = checked(run)
    if runtime_identity(neo4j_home, java, gds_jar) != manifest['runtime_identity']:
        raise ValueError('Native runtime differs')
    threads = manifest['threads']
    if any(os.environ.get(key) != str(threads) for key in gds_quality.THREADS):
        raise ValueError('Numeric-library ceilings differ from the frozen condition')
    graph = GraphSnapshot.load(run/'graph.npz')
    with np.load(run/'development.npz', allow_pickle=False) as file:
        sources, positives = file['sources'], file['positives']
    heads = [graph.node_ids[i] for i in sources]
    candidate_mask = ranking.candidate_mask(graph, sources)
    capacity = int(candidate_mask.sum())
    unique = capacity-int(candidate_mask[:, sources].sum())//2
    copy_lower_bound = 24*(unique*capacity-unique*(unique+1)//2)
    setup, records = {}, []

    def phase(name, begin):
        setup[name] = time.perf_counter()-begin
        print(name, round(setup[name], 3), file=sys.stderr, flush=True)

    begin = time.perf_counter()
    with (disposable_database(neo4j_home, java, gds_jar=gds_jar,
            heap_megabytes=manifest['heap_megabytes'], entrypoint='org.neo4j.server.Neo4jCommunity',
            transaction_timeout='900s') as uri, GraphDatabase.driver(uri, auth=None) as driver):
        phase('database_start', begin)

        def query(cypher, **parameters):
            return [r.data() for r in driver.execute_query(cypher, parameters_=parameters)[0]]

        versions = query('CALL dbms.components() YIELD versions '
                         'RETURN versions[0] AS neo4j,gds.version() AS gds')[0]
        if versions != {key: manifest[key+'_version'] for key in ('neo4j', 'gds')}:
            raise ValueError('Database versions differ')
        begin = time.perf_counter()
        import_graph(driver, graph)
        phase('import', begin)
        begin = time.perf_counter()
        query('UNWIND $heads AS id MATCH (n:Node {id:id}) SET n:Query', heads=heads)
        specs = ranking.prepare_source_specs(query, heads)
        query("CALL gds.graph.project('graph',$labels,{LINK:{orientation:'UNDIRECTED'}})",
              labels=['Node', 'Query', *[s['source_label'] for s in specs]])
        phase('labels_and_projection', begin)
        begin = time.perf_counter()
        trained = ranking.fit_gds(query, manifest['gds_config'], threads)
        phase('fit', begin)
        source = Neo4jSource(driver, fetch_size=1000)
        params = {'heads': heads, 'k': manifest['k'], 'threads': threads, 'candidate_count': capacity}
        begin = time.perf_counter()
        scores = ranking.from_stream(source.iter_candidates(ranking.gds_query(full=True), params), graph, sources)
        expected = ranking.rank_scores(scores, graph, sources, manifest['k'])
        phase('full_score_audit', begin)
        previous_max_error = None
        if (run/'previous-scores.npz').exists():
            with np.load(run/'previous-scores.npz', allow_pickle=False) as file:
                prior = file['gds']
            if not np.array_equal(np.isfinite(scores), np.isfinite(prior)):
                raise ValueError('Prior and current candidate coverage differ')
            previous_max_error = float(np.max(np.abs(scores[candidate_mask]-prior[candidate_mask])))
        np.savez_compressed(run/'scores.npz', scores=scores)
        order = list(manifest['arms'])
        random.Random(manifest['order_seed']).shuffle(order)
        for arm in order:
            samples, counters = [], []
            for repeat in range(manifest['warmup']+manifest['samples']):
                begin = time.perf_counter()
                if arm == 'global':
                    output = list(source.iter_candidates(ranking.gds_query(), params))
                    count = {'procedure_calls': 1, 'max_top_n': capacity}
                else:
                    output, count = ranking.partitioned_request(source, specs, threads, manifest['k'])
                json.dumps(output, sort_keys=True, allow_nan=False)
                elapsed = time.perf_counter()-begin
                if output != expected:
                    write(run/'mismatch.json', {'arm': arm, 'repeat': repeat, 'expected': expected, 'actual': output})
                    raise ValueError('Native request differs from the complete-score reference')
                if repeat >= manifest['warmup']:
                    samples.append(elapsed)
                    counters.append(count)
                print(arm, repeat, round(elapsed, 3), count, file=sys.stderr, flush=True)
            records.append({'arm': arm, 'samples_seconds': samples, 'counters': counters, 'output': output})
    quality = gds_quality.evaluate(scores, candidate_mask, sources, positives)
    predictions = {(graph.node_index(row['head']), graph.node_index(r['target']))
                   for row in expected for r in row['recommendations']}
    report = {'format': manifest['format'], 'manifest_sha256': sha(run/'manifest.json'),
        'dataset': manifest.get('dataset', 'friendship'), 'threads': threads,
        'raw_score_quality': quality,
        'deterministic_id_recall16': sum((int(a), int(b)) in predictions for a, b in positives)/len(positives),
        'setup_seconds': setup, 'records': records, 'model_training': trained,
        'candidate_count': capacity, 'unique_undirected_predictions': unique,
        'global_queue_logical_copy_bytes_lower_bound': copy_lower_bound,
        'lower_bound_scope': 'source-derived logical array-copy bytes, not measured DRAM traffic or elapsed-time attribution',
        'previous_model_max_absolute_score_difference': previous_max_error,
        'all_outputs_match_complete_score_reference': True, 'full_scores_sha256': sha(run/'scores.npz'),
        'single_process_diagnostic': True, 'confirmation_contents_read': False}
    write(run/'results.json', report)
    return {'all_outputs_match_complete_score_reference': True,
            'median_seconds': {r['arm']: float(np.median(r['samples_seconds'])) for r in records},
            'previous_model_max_absolute_score_difference': previous_max_error}


def freeze_suite(run, reference):
    run.mkdir(parents=True, exist_ok=False)
    jobs = [{'dataset': d, 'threads': t, 'directory': f'{d}-t{t}'} for d in DATASETS for t in (1, 4)]
    random.Random(7621).shuffle(jobs)
    shutil.copyfile(Path(__file__), run/'gds_queue_diagnostic.py')
    for name in ('gds_quality.py', 'gds_ranking.py', 'structural_neo4j.py', 'GDS_QUEUE_GENERALIZATION.md'):
        shutil.copyfile(Path(__file__).with_name(name), run/name)
    for job in jobs:
        freeze(run/job['directory'], reference, job['dataset'], job['threads'])
        job['manifest_sha256'] = sha(run/job['directory']/'manifest.json')
    write(run/'suite.json', {'format': 'orbweaver-gds-queue-suite-v1', 'jobs': jobs,
        'files': {p.name: sha(p) for p in sorted(run.iterdir()) if p.is_file()},
        'confirmation_contents_read': False, 'one_process_per_condition': True})
    return {'conditions': len(jobs), 'suite_sha256': sha(run/'suite.json')}


def checked_suite(run):
    suite = read(run/'suite.json')
    for name, checksum in suite['files'].items():
        if sha(run/name) != checksum:
            raise ValueError('Frozen suite source changed')
    jobs = suite['jobs']
    if len(jobs) != 6 or {(j['dataset'], j['threads']) for j in jobs} != {
            (d, t) for d in DATASETS for t in (1, 4)}:
        raise ValueError('Suite does not contain all six declared conditions')
    for job in jobs:
        if job['directory'] != f"{job['dataset']}-t{job['threads']}":
            raise ValueError('Invalid condition directory')
        child = checked(run/job['directory'])
        if (sha(run/job['directory']/'manifest.json') != job['manifest_sha256']
                or (child['dataset'], child['threads']) != (job['dataset'], job['threads'])):
            raise ValueError('Frozen condition identity changed')
    return suite


def run_suite(run, neo4j_home, java, gds_jar):
    suite = checked_suite(run)
    failed = []
    for job in suite['jobs']:
        child = run/job['directory']
        if (child/'results.json').exists() or (child/'worker-error.json').exists():
            raise FileExistsError('Do not overwrite or silently restart a condition')
        print('START', job['directory'], flush=True)
        env = {**os.environ, **dict.fromkeys(gds_quality.THREADS, str(job['threads']))}
        with (child/'console.txt').open('x') as log:
            result = subprocess.run([sys.executable, str(child/'gds_queue_diagnostic.py'),
                'worker', str(child), '--neo4j-home', str(neo4j_home), '--java', str(java),
                '--gds-jar', str(gds_jar)], env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            write(child/'worker-error.json', {'job': job, 'returncode': result.returncode})
            failed.append(job['directory'])
        print('FINISH', job['directory'], result.returncode, flush=True)
    if failed:
        raise RuntimeError(f'Failed conditions retained: {failed}')
    return {'completed_conditions': len(suite['jobs'])}


def summarize_suite(run):
    import numpy as np

    suite = checked_suite(run)
    sys.path.insert(0, str(run/suite['jobs'][0]['directory']/'source'))
    from orbweaver_query import GraphSnapshot

    cases = []
    for job in suite['jobs']:
        child = run/job['directory']
        if (child/'worker-error.json').exists():
            raise ValueError('A failed condition cannot supply a suite summary')
        result = read(child/'results.json')
        if (result['manifest_sha256'] != job['manifest_sha256']
                or (result['dataset'], result['threads']) != (job['dataset'], job['threads'])
                or result['full_scores_sha256'] != sha(child/'scores.npz')
                or result['all_outputs_match_complete_score_reference'] is not True):
            raise ValueError('Invalid condition result')
        graph = GraphSnapshot.load(child/'graph.npz')
        with np.load(child/'development.npz', allow_pickle=False) as file:
            sources, positives = file['sources'], file['positives']
        with np.load(child/'scores.npz', allow_pickle=False) as file:
            scores = file['scores']
        mask = ranking.candidate_mask(graph, sources)
        if not np.array_equal(np.isfinite(scores), mask):
            raise ValueError('Raw scores do not cover exactly the complete candidate domain')
        expected = ranking.rank_scores(scores, graph, sources, 16)
        predicted = {(graph.node_index(row['head']), graph.node_index(r['target']))
                     for row in expected for r in row['recommendations']}
        recall = sum((int(a), int(b)) in predicted for a, b in positives)/len(positives)
        if result['deterministic_id_recall16'] != recall:
            raise ValueError('Stable-ID recall does not reproduce')
        if result['raw_score_quality'] != gds_quality.evaluate(scores, mask, sources, positives):
            raise ValueError('Quality does not reproduce from scores')
        records = result['records']
        if len(records) != 2 or {r['arm'] for r in records} != {'global', 'partitioned'}:
            raise ValueError('Missing condition arm')
        for record in records:
            samples = record['samples_seconds']
            if (record['output'] != expected or len(samples) != 3 or len(record['counters']) != 3
                    or any(type(s) not in (int, float) or not np.isfinite(s) or s <= 0 for s in samples)):
                raise ValueError('Condition output or samples do not validate')
        medians = {r['arm']: float(np.median(r['samples_seconds'])) for r in records}
        cases.append({'dataset': job['dataset'], 'threads': job['threads'], 'median_seconds': medians,
            'global_over_partitioned': medians['global']/medians['partitioned'],
            'raw_score_quality': result['raw_score_quality']['metrics'],
            'deterministic_id_recall16': result['deterministic_id_recall16'],
            'selected_classifier': result['model_training'][0]['modelInfo']['bestParameters'],
            'setup_seconds': result['setup_seconds'],
            'partitioned_counters': next(r['counters'] for r in records if r['arm'] == 'partitioned')})
    report = {'format': suite['format'], 'suite_sha256': sha(run/'suite.json'),
              'verified_conditions': 6, 'conditions': cases, 'confirmation_contents_read': False,
              'scope': 'one process per graph/thread condition; descriptive native baseline check'}
    write(run/'summary.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'worker', 'freeze-suite', 'run-suite', 'summarize-suite'))
    parser.add_argument('run', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--dataset', choices=DATASETS, default='friendship')
    parser.add_argument('--threads', type=int, choices=(1, 4), default=1)
    for name in ('neo4j-home', 'java', 'gds-jar'):
        parser.add_argument('--'+name, type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    if args.command == 'freeze':
        result = freeze(run, args.reference, args.dataset, args.threads)
    elif args.command == 'freeze-suite':
        result = freeze_suite(run, args.reference)
    elif args.command == 'run-suite':
        result = run_suite(run, args.neo4j_home, args.java, args.gds_jar)
    elif args.command == 'summarize-suite':
        result = summarize_suite(run)
    else:
        result = worker(run, args.neo4j_home, args.java, args.gds_jar)
    print(json.dumps(result, allow_nan=False))
