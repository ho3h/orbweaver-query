"""Frozen matched top-16 application requests against native Neo4j/GDS."""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import gds_application_archive as archive
import gds_quality
import gds_ranking as ranking
from structural_neo4j import checked, export_graph, import_graph, read, runtime_identity, sha, write

DATASETS = ('collaboration', 'friendship', 'communication')
GDS_SELECTION = {'collaboration': 'negatives16', 'friendship': 'baseline', 'communication': 'baseline'}
LOCAL_SELECTION = {'collaboration': 'resource_allocation', 'friendship': 'resource_allocation',
                   'communication': 'path'}
ARMS = ('local', 'manual', 'native_ra_scalar', 'native_ra_fused', 'native_aa_fused',
        'gds', 'cached_local', 'cached_gds')


def freeze(run, inputs, selection, neo4j_home, java, gds_jar):
    runtime = runtime_identity(neo4j_home, java, gds_jar)
    original = read(inputs/'manifest.json')
    choices = read(selection)
    for dataset in DATASETS:
        selected = choices['datasets'][dataset]
        if (selected['best_completed_gds'] != 'gds_'+GDS_SELECTION[dataset]
                or selected['best_orbweaver'] != LOCAL_SELECTION[dataset]):
            raise ValueError('Selection differs from the completed development grid')
    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[2]
    shutil.copytree(package/'src/orbweaver_query', run/'source/orbweaver_query',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('gds_application.py', 'gds_application_archive.py', 'gds_ranking.py', 'gds_quality.py',
                 'structural_neo4j.py', 'GDS_APPLICATION_PROTOCOL.md'):
        shutil.copyfile(Path(__file__).with_name(name), run/name)
    shutil.copyfile(package/'tools/disposable_neo4j.py', run/'disposable_neo4j.py')
    shutil.copyfile(selection, run/'development-selection.json')
    for dataset in DATASETS:
        suffixes = ('outer.npz', 'development.npz')
        if dataset == 'communication':
            suffixes += ('evidence.npz', 'fit.npz')
        for suffix in suffixes:
            name = f'{dataset}-{suffix}'
            if sha(inputs/name) != original['files'][name]:
                raise ValueError(f'Changed original input: {name}')
            shutil.copyfile(inputs/name, run/name)
    jobs = [{'dataset': d, 'threads': t, 'replicate': r}
            for d in DATASETS for t in (1, 4) for r in range(3)]
    random.Random(7610).shuffle(jobs)
    write(run/'manifest.json', {'format': 'orbweaver-gds-application-v2', 'jobs': jobs,
        'files': {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file()},
        'runtime_identity': runtime, 'gds_selection': GDS_SELECTION, 'local_selection': LOCAL_SELECTION,
        'input_manifest_sha256': sha(inputs/'manifest.json'), 'selection_sha256': sha(selection),
        'arms': ARMS, 'k': 16, 'ranking_precision': ranking.PRECISION, 'warmup': 1, 'samples': 3,
        'condition_seed': 7611, 'heap_megabytes': 8192, 'transaction_timeout_seconds': 900,
        'neo4j_version': '2026.09.0', 'gds_version': '2026.09.0', 'fetch_size': 1000,
        'gds_request_strategy': 'singleton_adaptive_topk', 'gds_progress_retention_seconds': 60,
        'confirmation_contents_read': False})
    return {'workers': len(jobs), 'manifest_sha256': sha(run/'manifest.json')}


def fit_path(run, dataset, graph):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from orbweaver_query import ExplicitPathModel, GraphSnapshot
    from orbweaver_query.datasets import positives_by_query
    from orbweaver_query.training import prepare_examples

    evidence = GraphSnapshot.load(run/f'{dataset}-evidence.npz')
    with np.load(run/f'{dataset}-fit.npz', allow_pickle=False) as file:
        fitting = file['triples']
    examples, x, audit = prepare_examples(evidence, fitting, positives_by_query(graph.triples()), seed=71)
    estimator = LogisticRegression(C=10, solver='liblinear', max_iter=2000, tol=1e-6,
                                   random_state=0, fit_intercept=False)
    estimator.fit(x, examples['labels'], sample_weight=1/np.bincount(examples['groups'])[examples['groups']])
    return ExplicitPathModel(estimator.coef_, relations=graph.relations), audit


def manual_scores(graph, sources, model, method):
    import numpy as np
    from orbweaver_query import Limits

    if method != 'path':
        return ranking.structural_scores(graph, sources, method)
    scores = np.full((len(sources), len(graph.node_ids)), np.nan)
    for i, h in enumerate(sources):
        features = model.expand(graph, int(h), Limits())
        scores[i, features.candidates] = model.score(features, 0)
    return scores


def output_recall(output, graph, positives):
    pairs = {(graph.node_index(row['head']), graph.node_index(r['target']))
             for row in output for r in row['recommendations']}
    return sum((int(h), int(t)) in pairs for h, t in positives)/len(positives)


def quality(scores, output, graph, sources, positives):
    import numpy as np

    candidates = ranking.candidate_mask(graph, sources)
    rounded = np.array([[round(float(v), ranking.PRECISION) for v in row] for row in scores])
    return {'raw': gds_quality.evaluate(scores, candidates, sources, positives),
            'rounded': gds_quality.evaluate(rounded, candidates, sources, positives),
            'deterministic_id_recall16': output_recall(output, graph, positives)}


def worker(run, index, neo4j_home, java, gds_jar):
    sys.path.insert(0, str(run/'source'))
    sys.path.insert(0, str(run))
    import numpy as np
    from disposable_neo4j import disposable_database
    from neo4j import GraphDatabase
    from orbweaver_query import GraphSnapshot, NeighborhoodModel
    from orbweaver_query.neo4j import Neo4jSource

    manifest = checked(run)
    archive.validate_manifest(manifest)
    if manifest['format'] != 'orbweaver-gds-application-v2':
        raise ValueError('Use the frozen original runner for historical application runs')
    if runtime_identity(neo4j_home, java, gds_jar) != manifest['runtime_identity']:
        raise ValueError('Runtime differs from the frozen campaign')
    job = manifest['jobs'][index]
    dataset, threads = job['dataset'], job['threads']
    if any(os.environ.get(k) != str(threads) for k in gds_quality.THREADS):
        raise ValueError('Numeric-library thread ceilings differ from the frozen worker')
    graph = GraphSnapshot.load(run/f'{dataset}-outer.npz')
    with np.load(run/f'{dataset}-development.npz', allow_pickle=False) as file:
        sources, positives = file['sources'], file['positives']
    method = manifest['local_selection'][dataset]
    config = gds_quality.GDS_CONFIGS[manifest['gds_selection'][dataset]]
    setup, records, diagnostics = {}, [], {}

    def phase(name, start):
        setup[name] = time.perf_counter()-start
        print(f'{index}/{dataset}/{threads}: {name} {setup[name]:.3f}s', file=sys.stderr, flush=True)

    begin = time.perf_counter()
    if method == 'path':
        model, diagnostics['local_fit'] = fit_path(run, dataset, graph)
        model.save(run/'workers'/f'{index:04d}-model.npz')
    else:
        model = NeighborhoodModel(relations=graph.relations, metric=method)
    phase('local_fit', begin)
    begin = time.perf_counter()
    with (disposable_database(neo4j_home, java, gds_jar=gds_jar,
            heap_megabytes=manifest['heap_megabytes'], entrypoint='org.neo4j.server.Neo4jCommunity',
            transaction_timeout=f"{manifest['transaction_timeout_seconds']}s",
            gds_progress_retention_seconds=manifest['gds_progress_retention_seconds']) as uri,
          GraphDatabase.driver(uri, auth=None) as driver):
        phase('database_start', begin)

        def query(cypher, **parameters):
            return [r.data() for r in driver.execute_query(cypher, parameters_=parameters)[0]]

        versions = query('CALL dbms.components() YIELD versions '
                         'RETURN versions[0] AS neo4j,gds.version() AS gds')[0]
        if versions != {k: manifest[k+'_version'] for k in ('neo4j', 'gds')}:
            raise ValueError('Database/plugin version differs')
        diagnostics['gds_settings'] = {r['name']: r['value'] for r in query(
            "SHOW SETTINGS YIELD name,value WHERE name IN "
            "['gds.progress_tracking_enabled','gds.progress_tracking_retention_period'] RETURN name,value")}
        if diagnostics['gds_settings'] != archive.GDS_SETTINGS:
            raise ValueError('Effective GDS task retention differs from the protocol')
        diagnostics['gds_checkpoints'], diagnostics['gds_requests'] = [], []
        write(run/'workers'/f'{index:04d}-native-settings.json', diagnostics['gds_settings'])

        def checkpoint(stage):
            # Always outside request/setup timers. Persist before enforcing the guard.
            record = {'stage': stage, 'memory': query('CALL gds.memory.list()'),
                      'summary': query('CALL gds.memory.summary()'),
                      'progress': query('CALL gds.listProgress()')}
            diagnostics['gds_checkpoints'].append(record)
            write(run/'workers'/f'{index:04d}-native-{stage}.json', record)
            archive.validate_checkpoint(record)

        def retain_request(stage, output, counters):
            record = {'stage': stage, 'output': output, 'counters': counters}
            diagnostics['gds_requests'].append(record)
            write(run/'workers'/f'{index:04d}-request-{stage}.json', record)
            checkpoint(stage)

        begin = time.perf_counter()
        import_graph(driver, graph)
        phase('import', begin)
        source = Neo4jSource(driver, fetch_size=manifest['fetch_size'])
        begin = time.perf_counter()
        exported = export_graph(source)
        phase('evidence_export', begin)
        if exported.snapshot_id != graph.snapshot_id:
            raise ValueError('Exported evidence differs')
        heads = [graph.node_ids[i] for i in sources]
        if len(heads) != 64:
            raise ValueError('Application campaign requires the original 64 development sources')
        begin = time.perf_counter()
        query('UNWIND $heads AS id MATCH (n:Node {id:id}) SET n:Query', heads=heads)
        specs = ranking.prepare_source_specs(query, heads)
        phase('gds_source_preparation', begin)
        diagnostics['gds_source_specs'] = specs
        begin = time.perf_counter()
        query("CALL gds.graph.project('graph',$labels,{LINK:{orientation:'UNDIRECTED'}})",
              labels=['Node', 'Query', *[s['source_label'] for s in specs]])
        phase('gds_projection', begin)
        checkpoint('projected')
        begin = time.perf_counter()
        query('MATCH (n:Node) SET n.degree=COUNT { (n)-[:LINK]-() }')
        phase('native_degrees', begin)
        begin = time.perf_counter()
        diagnostics['gds_fit'] = ranking.fit_gds(query, config, threads)
        phase('gds_fit', begin)
        checkpoint('fitted')
        params = {'heads': heads, 'k': manifest['k'], 'threads': threads,
                  'candidate_count': int(ranking.candidate_mask(graph, sources).sum())}
        begin = time.perf_counter()
        raw = {'gds': ranking.from_stream(source.iter_candidates(ranking.gds_query(full=True), params),
                                           graph, sources),
               'resource_allocation': ranking.structural_scores(graph, sources, 'resource_allocation'),
               'adamic_adar': ranking.structural_scores(graph, sources, 'adamic_adar'),
               'local': manual_scores(graph, sources, model, method)}
        phase('untimed_full_score_audit', begin)
        checkpoint('full-score-reference')
        references = {name: ranking.rank_scores(values, graph, sources, manifest['k'])
                      for name, values in raw.items()}
        np.savez_compressed(run/'workers'/f'{index:04d}-scores.npz', **raw)
        qualities = {name: quality(raw[name], references[name], graph, sources, positives) for name in raw}
        cache = {}

        def request(arm):
            if arm.startswith('native_'):
                metric = 'adamic_adar' if arm == 'native_aa_fused' else 'resource_allocation'
                return list(source.iter_candidates(ranking.structural_query(metric,
                    scalar=arm == 'native_ra_scalar'), params)), None
            if arm == 'gds':
                return ranking.partitioned_request(source, specs, threads, manifest['k'])
            read_heads = [row['head'] for row in source.iter_candidates(ranking.HEADS, params)]
            if read_heads != heads:
                raise ValueError('Native source selection differs')
            if arm.startswith('cached_'):
                return [cache[arm][head] for head in read_heads], None
            scores = (ranking.local_scores(exported, sources, model) if arm == 'local'
                      else manual_scores(exported, sources, model, method))
            return ranking.rank_scores(scores, exported, sources, manifest['k']), None

        # Build each warm answer cache through a real request; do not use audit outputs.
        for arm in ('local', 'gds'):
            begin = time.perf_counter()
            output, counters = request(arm)
            json.dumps(output, sort_keys=True, allow_nan=False)
            phase('cache_'+arm, begin)
            if output != references[arm]:
                raise ValueError(f'Cache construction differs from full-score reference: {arm}')
            cache['cached_'+arm] = {row['head']: row for row in output}
            if arm == 'gds':
                retain_request('cache-gds', output, counters)
        order = list(manifest['arms'])
        random.Random(manifest['condition_seed']+index).shuffle(order)
        for arm in order:
            reference_name = ('gds' if arm in ('gds', 'cached_gds') else
                'adamic_adar' if arm == 'native_aa_fused' else
                'resource_allocation' if arm.startswith('native_') else 'local')
            samples = []
            for repeat in range(manifest['warmup']+manifest['samples']):
                begin = time.perf_counter()
                output, counters = request(arm)
                json.dumps(output, sort_keys=True, allow_nan=False)
                elapsed = time.perf_counter()-begin
                if output != references[reference_name]:
                    raise ValueError(f'Recommendations differ from full-score reference: {arm}')
                if repeat >= manifest['warmup']:
                    samples.append(elapsed)
                if arm == 'gds':
                    retain_request(f'gds-{repeat}', output, counters)
            records.append({'arm': arm, 'samples_seconds': samples, 'output': output,
                            'quality_reference': reference_name})
            print(f'{index}/{dataset}/{threads}: {arm} complete', file=sys.stderr, flush=True)
    import resource
    scale = 1 if sys.platform == 'darwin' else 1024
    return {'job': job, 'manifest_sha256': sha(run/'manifest.json'), 'records': records,
            'setup_seconds': setup, 'quality': qualities, 'diagnostics': diagnostics,
            'candidate_count': params['candidate_count'], 'snapshot_id': graph.snapshot_id,
            'model_id': model.model_id, 'all_request_references_match': True,
            'full_scores_sha256': sha(run/'workers'/f'{index:04d}-scores.npz'),
            'peak_python_rss_bytes': scale*resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'peak_java_rss_bytes': scale*resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            'memory_scope': 'whole worker, not per-arm', 'python': sys.version}


def execute(run, neo4j_home, java, gds_jar):
    manifest = checked(run)
    folder = run/'workers'
    folder.mkdir(exist_ok=True)
    for index, job in enumerate(manifest['jobs']):
        output, error = folder/f'{index:04d}.json', folder/f'{index:04d}-error.json'
        if output.exists():
            continue
        if error.exists():
            raise ValueError('Preserve failed campaign; freeze a new run')
        command = [sys.executable, str(run/'gds_application.py'), 'worker', str(run),
                   '--index', str(index), '--neo4j-home', str(neo4j_home), '--java', str(java),
                   '--gds-jar', str(gds_jar)]
        with (folder/f'{index:04d}-console.txt').open('x') as log:
            result = subprocess.run(command, env={**os.environ,
                **{key: str(job['threads']) for key in gds_quality.THREADS}},
                stdout=subprocess.PIPE, stderr=log, text=True, check=False)
        if result.returncode:
            write(error, {'job': job, 'returncode': result.returncode, 'stdout': result.stdout})
            raise RuntimeError(f'Worker {index} failed; console and error retained')
        write(output, json.loads(result.stdout))
        print(f'{index+1}/{len(manifest["jobs"])} workers', flush=True)
    return {'workers': len(manifest['jobs'])}


def summarize(run):
    """Rebuild answers/quality from retained scores before accepting any timing."""
    sys.path.insert(0, str(run/'source'))
    import numpy as np
    from orbweaver_query import GraphSnapshot

    manifest = checked(run)
    archive.validate_manifest(manifest)
    if list((run/'workers').glob('*-error.json')):
        raise ValueError('A failed campaign cannot be summarized as successful')
    workers = []
    for index, job in enumerate(manifest['jobs']):
        worker_result = read(run/'workers'/f'{index:04d}.json')
        archive.validate_worker(manifest, sha(run/'manifest.json'), index, worker_result)
        if (worker_result['job'] != job
                or worker_result['manifest_sha256'] != sha(run/'manifest.json')
                or not worker_result['all_request_references_match']):
            raise ValueError('Worker identity/validation differs')
        path = run/'workers'/f'{index:04d}-scores.npz'
        if sha(path) != worker_result['full_scores_sha256']:
            raise ValueError('Raw scores changed')
        graph = GraphSnapshot.load(run/f'{job["dataset"]}-outer.npz')
        with np.load(run/f'{job["dataset"]}-development.npz', allow_pickle=False) as file:
            sources, positives = file['sources'], file['positives']
        if manifest['format'] == 'orbweaver-gds-application-v2':
            specs = worker_result['diagnostics']['gds_source_specs']
            mask = ranking.candidate_mask(graph, sources)
            expected = [{'ordinal': i, 'head': graph.node_ids[h], 'candidates': int(mask[i].sum()),
                         'source_label': f'OrbRankSource_{i}'} for i, h in enumerate(sources)]
            if specs != expected:
                raise ValueError('Native prepared domains differ from immutable graph')
        with np.load(path, allow_pickle=False) as file:
            raw = {key: file[key] for key in file.files}
        if set(raw) != {'gds', 'local', 'resource_allocation', 'adamic_adar'}:
            raise ValueError('Missing score reference')
        references = {key: ranking.rank_scores(scores, graph, sources, manifest['k'])
                      for key, scores in raw.items()}
        for key, scores in raw.items():
            if quality(scores, references[key], graph, sources, positives) != worker_result['quality'][key]:
                raise ValueError('Retained quality differs from raw scores')
        if (len(worker_result['records']) != len(ARMS)
                or {r['arm'] for r in worker_result['records']} != set(ARMS)):
            raise ValueError('Missing/duplicate request conditions')
        for record in worker_result['records']:
            samples = record['samples_seconds']
            if (len(samples) != manifest['samples'] or not np.isfinite(samples).all()
                    or min(samples) <= 0 or record['output'] != references[record['quality_reference']]):
                raise ValueError('Invalid request measurements or output')
        workers.append(worker_result)
    outcomes = []
    for dataset in DATASETS:
        for threads in (1, 4):
            ws = [w for w in workers if w['job']['dataset'] == dataset and w['job']['threads'] == threads]
            for arm in ARMS:
                medians, setups, raw_quality, rounded_quality, id_quality = [], [], [], [], []
                for w in ws:
                    record, = [r for r in w['records'] if r['arm'] == arm]
                    q = w['quality'][record['quality_reference']]
                    raw_quality.append(q['raw']['metrics']['recall16'])
                    rounded_quality.append(q['rounded']['metrics']['recall16'])
                    id_quality.append(q['deterministic_id_recall16'])
                    medians.append(float(np.median(record['samples_seconds'])))
                    s = w['setup_seconds']
                    if arm in ('local', 'manual', 'cached_local'):
                        cost = s['evidence_export']+s['local_fit']
                    elif arm in ('gds', 'cached_gds'):
                        cost = s['gds_projection']+s['gds_fit']+s.get('gds_source_preparation', 0.)
                    else:
                        cost = s['native_degrees'] if arm.endswith('_fused') else 0.
                    if arm.startswith('cached_'):
                        cost += s['cache_'+arm.removeprefix('cached_')]
                    setups.append(cost)
                outcomes.append({'dataset': dataset, 'threads': threads, 'arm': arm,
                    'process_medians_ms': [1000*v for v in medians],
                    'request_median_ms': 1000*float(np.median(medians)),
                    'setup_seconds': setups, 'raw_recall16': raw_quality,
                    'rounded_recall16': rounded_quality, 'deterministic_id_recall16': id_quality,
                    'amortized_ms': {str(n): 1000*float(np.median(np.array(medians)+np.array(setups)/n))
                                     for n in (1, 10, 100, 1000)}})
    report = {'format': manifest['format'], 'manifest_sha256': sha(run/'manifest.json'),
        'verified_workers': len(workers), 'per_arm_reference_match': True, 'outcomes': outcomes,
        'interpretation': 'Development quality/cost observations; algorithms differ. No cross-algorithm numerical-parity or release-gate claim.',
        'confirmation_contents_read': False}
    write(run/'results.json', report)
    return {'verified_workers': len(workers), 'outcomes': len(outcomes),
            'per_arm_reference_match': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'worker', 'execute', 'summarize'))
    parser.add_argument('run', type=Path)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--index', type=int)
    for name in ('neo4j-home', 'java', 'gds-jar'):
        parser.add_argument('--'+name, type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    runtime = (args.neo4j_home, args.java, args.gds_jar)
    if args.command == 'freeze':
        report = freeze(run, args.inputs, args.selection, *runtime)
    elif args.command == 'worker':
        report = worker(run, args.index, *runtime)
    elif args.command == 'summarize':
        report = summarize(run)
    else:
        report = execute(run, *runtime)
    print(json.dumps(report, allow_nan=False))
