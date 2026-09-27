"""Freeze and evaluate held-out GDS quality only after complete application replay."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

import gds_application_archive as archive
import gds_confirmation_metrics as metrics

INPUT_MANIFEST = '0d5bf2f247943e66aa0f05ceb50eb710ef94d16f83655a0fdd2d6c9e6a2defac'
APPLICATION_MANIFEST = '8d7cf9d8cdf429c190782559e045873953e35cc16dc46df469b125b9b020aba1'
SELECTION = '0061cf0e47e0d49c46692a014555c9be1caa4ef9fc5475ff87ff66d52d19c05e'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def graph_context(application, dataset):
    with np.load(application/f'{dataset}-outer.npz', allow_pickle=False) as data:
        ids, triples = data['node_ids'].tolist(), data['triples']
        if data['relations'].tolist() != ['LINK']:
            raise ValueError('The frozen application is an undirected LINK task')
    with np.load(application/f'{dataset}-development.npz', allow_pickle=False) as data:
        sources, positives = data['sources'], data['positives']
    adjacency, mask = metrics.graph_domain(ids, triples, sources)
    if len(sources) != 64:
        raise ValueError('The original 64 sources are required')
    metrics.validate_positives(positives, sources, mask)
    return {'ids': ids, 'sources': sources, 'development': positives,
            'adjacency': adjacency, 'mask': mask}


def score_arrays(application, index, context):
    with np.load(application/'workers'/f'{index:04d}-scores.npz', allow_pickle=False) as data:
        if set(data.files) != {'local', 'gds', 'resource_allocation', 'adamic_adar'}:
            raise ValueError('All original score matrices are required')
        scores = {key: data[key] for key in data.files}
    for name, values in scores.items():
        metrics.validate_scores(values, context['mask'], complete=name != 'local',
                                probability=name == 'gds')
    return scores


def small_reference_check():
    """Untimed, label-free prerequisite for the added common-neighbor control."""
    pairs = [(0, 1), (0, 2), (1, 3), (2, 3), (2, 4)]
    triples = np.array([(h, 0, t) for a, b in pairs for h, t in ((a, b), (b, a))])
    sources = np.array([0, 5])
    adjacency, mask = metrics.graph_domain([str(i) for i in range(6)], triples, sources)
    scores = metrics.common_neighbors(adjacency, sources, mask)
    if (not np.array_equal(scores[0, [3, 4, 5]], [2., 1., 0.])
            or not np.array_equal(scores[1, :5], np.zeros(5))):
        raise ValueError('Common-neighbor walk counts differ from the manual fixture')
    ids, sources = [f'n{i}' for i in range(70)], np.array([0])
    adjacency, mask = metrics.graph_domain(ids, np.empty((0, 3), dtype=np.int64), sources)
    result = metrics.assess(metrics.common_neighbors(adjacency, sources, mask), mask, sources,
                            np.array([[0, 1], [0, 69]]), ids)
    if (result['raw']['metrics']['recall16'] != 16/69
            or result['deterministic_id_recall16'] != .5):
        raise ValueError('Uniform-tie and deterministic-ID quality were conflated')
    return {'common_neighbor_manual_fixture': True, 'closed_form_tie_fixture': True}


def audit_application(application):
    """Independently reconstruct each original answer and development metric."""
    if sha(application/'manifest.json') != APPLICATION_MANIFEST:
        raise ValueError('Use the declared v2 application campaign, not a substituted run')
    manifest = archive.read(application/'manifest.json')
    archive.validate_manifest(manifest)
    if (manifest['input_manifest_sha256'] != INPUT_MANIFEST
            or manifest['selection_sha256'] != SELECTION
            or sha(application/'development-selection.json') != SELECTION):
        raise ValueError('Development inputs or model selection changed')
    contexts = {d: graph_context(application, d) for d in metrics.DATASETS}
    workers = []
    for index, job in enumerate(manifest['jobs']):
        path = application/'workers'/f'{index:04d}.json'
        worker = archive.read(path)
        archive.validate_worker(manifest, APPLICATION_MANIFEST, index, worker)
        if sha(application/'workers'/f'{index:04d}-scores.npz') != worker['full_scores_sha256']:
            raise ValueError('Retained score matrix changed')
        context = contexts[job['dataset']]
        scores = score_arrays(application, index, context)
        if job['dataset'] != 'communication':
            metrics.validate_scores(scores['local'], context['mask'], complete=True)
        for name, values in scores.items():
            assessment = metrics.assess(values, context['mask'], context['sources'],
                                        context['development'], context['ids'])
            prior = worker['quality'][name]
            for mode in ('raw', 'rounded'):
                if any(assessment[mode][k] != prior[mode][k]
                       for k in ('metrics', 'positive_queries', 'outcomes')):
                    raise ValueError('Independent development quality reconstruction differs')
            if assessment['deterministic_id_recall16'] != prior['deterministic_id_recall16']:
                raise ValueError('Independent deterministic quality differs')
            for record in worker['records']:
                if record['quality_reference'] == name and record['output'] != assessment['output']:
                    raise ValueError('Saved request differs from independent ranking')
        workers.append({'job': job, 'worker_sha256': sha(path),
                        'score_sha256': worker['full_scores_sha256'],
                        'local_model_id': worker['model_id'],
                        'gds_training_record_sha256': hashlib.sha256(json.dumps(
                            worker['diagnostics']['gds_fit'], sort_keys=True,
                            allow_nan=False).encode()).hexdigest()})
    return contexts, workers


def freeze(run, application_archive, inputs):
    """Never parse a confirmation array during preparation."""
    if run.exists():
        raise ValueError('Preserve previous attempts; use a fresh confirmation directory')
    verified = archive.verify(application_archive)
    if verified['status'] != 'complete' or verified['verified_workers'] != 18:
        raise ValueError('Confirmation requires every application worker to complete')
    if sha(inputs/'manifest.json') != INPUT_MANIFEST:
        raise ValueError('Original split manifest changed')
    original = archive.read(inputs/'manifest.json')
    fixture = small_reference_check()
    with tempfile.TemporaryDirectory(prefix='orbweaver-confirmation-replay-') as temporary:
        replay = Path(temporary)/'application'
        runner = archive.restore(application_archive, replay)
        command = subprocess.run([sys.executable, runner, 'summarize', str(replay)],
                                 text=True, capture_output=True, check=False)
        if command.returncode:
            raise RuntimeError('Application replay failed before label access: '+command.stderr)
        if (replay/'results.json').read_bytes() != (replay/'recorded-results.json').read_bytes():
            raise ValueError('Rebuilt application results are not byte-identical')
        contexts, workers = audit_application(replay)
        for dataset in metrics.DATASETS:
            for suffix in ('outer.npz', 'development.npz'):
                name = f'{dataset}-{suffix}'
                if sha(replay/name) != original['files'][name]:
                    raise ValueError('Application graph or sources differ from original split')
        run.mkdir(parents=True)
        shutil.copytree(replay, run/'application', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        (run/'application-replay-console.txt').write_text(command.stdout+command.stderr)
        for name in ('gds_confirmation.py', 'gds_confirmation_metrics.py',
                     'gds_application_archive.py', 'GDS_CONFIRMATION_PROTOCOL.md'):
            shutil.copyfile(Path(__file__).with_name(name), run/name)
        shutil.copyfile(inputs/'manifest.json', run/'original-input-manifest.json')
        shutil.copyfile(application_archive/'ARCHIVE.json', run/'application-archive-receipt.json')
        (run/'sealed').mkdir()
        (run/'structural').mkdir()
        for dataset, context in contexts.items():
            values = metrics.common_neighbors(context['adjacency'], context['sources'], context['mask'])
            np.savez_compressed(run/'structural'/f'{dataset}.npz', scores=values)
            name = f'{dataset}-confirmation-sealed.npz'
            # Byte identity only; interpretation of labels occurs in evaluate().
            if sha(inputs/name) != original['files'][name]:
                raise ValueError('Sealed confirmation bytes changed')
            shutil.copyfile(inputs/name, run/'sealed'/name)
        write(run/'manifest.json', {'format': 'orbweaver-gds-confirmation-v1',
            'confirmation_evaluation_permitted': True, 'confirmation_labels_parsed_at_freeze': False,
            'application_manifest_sha256': APPLICATION_MANIFEST, 'input_manifest_sha256': INPUT_MANIFEST,
            'selection_sha256': SELECTION, 'application_archive_sha256': sha(application_archive/'evidence.tar.gz'),
            'application_results_sha256': sha(replay/'results.json'),
            'prerequisites': {'application_archive': verified, 'byte_identical_replay': True,
                              'independent_worker_reconstructions': len(workers), 'small_fixture': fixture},
            'workers': workers, 'source_ids': {d: [c['ids'][h] for h in c['sources']]
                                             for d, c in contexts.items()},
            'bootstrap_draws': 100_000, 'bootstrap_seed': 20260928,
            'numpy_version': np.__version__, 'python_version': sys.version,
            'files': {p.relative_to(run).as_posix(): sha(p) for p in sorted(run.rglob('*')) if p.is_file()}})
    return {'manifest_sha256': sha(run/'manifest.json'), 'confirmation_labels_parsed': False}


def checked(run):
    manifest = archive.read(run/'manifest.json')
    if (manifest['format'] != 'orbweaver-gds-confirmation-v1'
            or manifest['confirmation_evaluation_permitted'] is not True
            or manifest['confirmation_labels_parsed_at_freeze'] is not False
            or manifest['application_manifest_sha256'] != APPLICATION_MANIFEST
            or manifest['input_manifest_sha256'] != INPUT_MANIFEST
            or manifest['selection_sha256'] != SELECTION
            or (manifest['bootstrap_draws'], manifest['bootstrap_seed']) != (100_000, 20260928)
            or manifest['numpy_version'] != np.__version__):
        raise ValueError('Confirmation identity or declared evaluation parameters differ')
    required = {'gds_confirmation.py', 'gds_confirmation_metrics.py', 'gds_application_archive.py',
                'GDS_CONFIRMATION_PROTOCOL.md', 'original-input-manifest.json',
                'application/manifest.json', 'application/results.json', 'application-archive-receipt.json'}
    required.update(f'sealed/{d}-confirmation-sealed.npz' for d in metrics.DATASETS)
    required.update(f'structural/{d}.npz' for d in metrics.DATASETS)
    if not required <= set(manifest['files']):
        raise ValueError('Frozen confirmation manifest is missing required artifacts')
    proof = manifest['prerequisites']
    if (proof['application_archive']['status'] != 'complete'
            or proof['application_archive']['verified_workers'] != 18
            or proof['byte_identical_replay'] is not True
            or proof['independent_worker_reconstructions'] != 18
            or proof['small_fixture'] != {
                'common_neighbor_manual_fixture': True, 'closed_form_tie_fixture': True}):
        raise ValueError('Confirmation prerequisites are incomplete')
    for name, expected in manifest['files'].items():
        if sha(run/archive.relative(name)) != expected:
            raise ValueError(f'Frozen confirmation input changed: {name}')
    for name, path in (('gds_confirmation.py', Path(__file__)),
                       ('gds_confirmation_metrics.py', Path(metrics.__file__)),
                       ('gds_application_archive.py', Path(archive.__file__))):
        if sha(path) != manifest['files'][name]:
            raise ValueError('Use the frozen evaluator and numerical implementation')
    if (sha(run/'original-input-manifest.json') != INPUT_MANIFEST
            or sha(run/'application/manifest.json') != APPLICATION_MANIFEST
            or sha(run/'application/results.json') != manifest['application_results_sha256']):
        raise ValueError('Original split or verified application identity changed')
    receipt = archive.read(run/'application-archive-receipt.json')
    if (receipt['archive_sha256'] != manifest['application_archive_sha256']
            or receipt['format'] != 'orbweaver-gds-application-archive-v1'
            or receipt['verified_workers'] != 18
            or any(manifest['files'].get('application/'+name) != expected
                   for name, expected in receipt['files'].items())):
        raise ValueError('Confirmation inputs do not preserve the verified application archive')
    return manifest


def held_out_queries(pairs, context, expected_count):
    pairs = metrics.integer_array(pairs, columns=2)
    ids, sources, adjacency = context['ids'], context['sources'], context['adjacency']
    canonical = [(int(a), int(b)) for a, b in pairs]
    if (len(canonical) != expected_count or len(set(canonical)) != len(canonical)
            or any(not 0 <= a < b < len(ids) for a, b in canonical)):
        raise ValueError('Invalid, duplicate or incomplete canonical confirmation pairs')
    development = {tuple(sorted(map(int, row))) for row in context['development']}
    if any(b in adjacency[a] or (a, b) in development for a, b in canonical):
        raise ValueError('Confirmation overlaps training or retained development positives')
    selected = set(map(int, sources))
    result = np.array([(h, t) for a, b in canonical for h, t in ((a, b), (b, a))
                       if h in selected], dtype=np.int64).reshape(-1, 2)
    metrics.validate_positives(result, sources, context['mask'])
    return result


def evaluate(run):
    manifest = checked(run)
    for name in ('results.json', 'EVALUATION_STARTED.json', 'error.json'):
        if (run/name).exists():
            raise ValueError('Preserve the prior confirmation attempt; do not silently repeat it')
    contexts, workers = audit_application(run/'application')
    if workers != manifest['workers']:
        raise ValueError('Frozen prediction identities changed')
    if {d: [c['ids'][h] for h in c['sources']] for d, c in contexts.items()} != manifest['source_ids']:
        raise ValueError('Frozen source identities changed')
    write(run/'EVALUATION_STARTED.json', {'manifest_sha256': sha(run/'manifest.json'),
        'purpose': 'One held-out evaluation of the preregistered frozen predictions'})
    try:
        result = evaluate_labels(run, manifest, contexts)
        write(run/'results.json', result)
    except Exception as exc:
        write(run/'error.json', {'manifest_sha256': sha(run/'manifest.json'),
            'error_type': type(exc).__name__, 'message': str(exc),
            'confirmation_may_have_been_opened': True})
        raise
    return {'workers': len(result['workers']), 'status': result['paired_analysis']['status'],
            'results_sha256': sha(run/'results.json'), 'release_gate_closed': False}


def evaluate_labels(run, manifest, contexts):
    original = archive.read(run/'original-input-manifest.json')
    queries, counts, structural = {}, {}, {}
    for dataset, context in contexts.items():
        with np.load(run/'sealed'/f'{dataset}-confirmation-sealed.npz', allow_pickle=False) as data:
            if data.files != ['pairs']:
                raise ValueError('Unexpected confirmation file schema')
            queries[dataset] = held_out_queries(data['pairs'], context,
                                               original['inventory'][dataset]['confirmation'])
        with np.load(run/'structural'/f'{dataset}.npz', allow_pickle=False) as data:
            structural[dataset] = data['scores']
        metrics.validate_scores(structural[dataset], context['mask'], complete=True)
    totals = {d: np.full((2, 3, 64, 5), np.nan) for d in metrics.DATASETS}
    workers = []
    (run/'workers').mkdir()
    for index, frozen in enumerate(manifest['workers']):
        job = frozen['job']
        dataset, threads, replicate = job['dataset'], job['threads'], job['replicate']
        context = contexts[dataset]
        values = score_arrays(run/'application', index, context)
        values['common_neighbors'] = structural[dataset]
        assessments = {}
        for column, name in enumerate(metrics.METHODS):
            assessment = metrics.assess(values[name], context['mask'], context['sources'],
                                        queries[dataset], context['ids'])
            if dataset in counts and counts[dataset] != assessment['source_positive_counts']:
                raise ValueError('Methods use different held-out denominators')
            counts[dataset] = assessment['source_positive_counts']
            totals[dataset][metrics.THREADS.index(threads), replicate, :, column] = metrics.source_totals(
                assessment, context['sources'])
            assessments[name] = assessment
        worker = {'job': job, 'frozen_prediction_identity': frozen, 'methods': assessments}
        write(run/'workers'/f'{index:04d}.json', worker)
        workers.append(worker)
    analysis = metrics.paired_bootstrap(totals, counts, draws=manifest['bootstrap_draws'],
                                        seed=manifest['bootstrap_seed'])
    return {'format': manifest['format'], 'manifest_sha256': sha(run/'manifest.json'),
            'confirmation_labels_parsed': True, 'workers': workers,
            'mean_quality': summarize_workers(workers),
            'source_positive_counts': counts, 'paired_analysis': analysis,
            'application_results_sha256': manifest['application_results_sha256'],
            'cost_scope': 'Reuse the separately verified fixed-source development application costs; common neighbors is an untimed quality control. No new confirmation timing or per-arm memory claim.',
            'release_gate_closed': False}


def summarize_workers(workers):
    """Retain absolute quality as well as paired differences, without choosing a run."""
    summary = []
    for dataset in metrics.DATASETS:
        for threads in metrics.THREADS:
            selected = [w for w in workers if w['job']['dataset'] == dataset
                        and w['job']['threads'] == threads]
            if len(selected) != 3 or {w['job']['replicate'] for w in selected} != {0, 1, 2}:
                raise ValueError('Every original process repetition is required')
            denominators = {a['raw']['positive_queries']
                            for w in selected for a in w['methods'].values()}
            if len(denominators) != 1:
                raise ValueError('Process or method positive denominators differ')
            denominator = denominators.pop()

            def mean(values):
                if not denominator:
                    if any(v is not None for v in values):
                        raise ValueError('Empty quality denominator has a numeric metric')
                    return None
                if any(v is None or not np.isfinite(v) for v in values):
                    raise ValueError('Invalid metric for a nonempty positive denominator')
                return float(np.mean(values))

            methods = {}
            for name in metrics.METHODS:
                records = [w['methods'][name] for w in selected]
                methods[name] = {
                    mode: {key: mean([r[mode]['metrics'][key] for r in records])
                           for key in metrics.METRICS} for mode in ('raw', 'rounded')}
                methods[name]['deterministic_id_recall16'] = mean(
                    [r['deterministic_id_recall16'] for r in records])
            control_scores = {name: methods[name]['raw']['recall16'] for name in metrics.METHODS[1:]}
            best = max(control_scores.values()) if denominator else None
            strongest = [name for name, value in control_scores.items()
                         if denominator and abs(value-best) <= metrics.METRIC_EPSILON]
            summary.append({'dataset': dataset, 'threads': threads, 'positive_queries': denominator,
                'aggregation': 'Arithmetic mean of three process metrics; not an ensemble',
                'methods': methods, 'strongest_control_methods': strongest,
                'strongest_control_raw_recall16': best,
                'local_minus_strongest_raw_recall16':
                    methods['local']['raw']['recall16']-best if denominator else None})
    return summary


def replay(run):
    """Recompute an existing result in isolation; never replace that result."""
    manifest = checked(run)
    if (run/'error.json').exists() or not (run/'results.json').exists():
        raise ValueError('Numerical replay requires a successful retained evaluation')
    with tempfile.TemporaryDirectory(prefix='orbweaver-confirmation-audit-') as temporary:
        restored = Path(temporary)
        for name in (*manifest['files'], 'manifest.json'):
            target = restored/archive.relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(run/name, target)
        evaluate(restored)
        if (restored/'results.json').read_bytes() != (run/'results.json').read_bytes():
            raise ValueError('Held-out quality or uncertainty does not reproduce byte for byte')
        expected = {f'{i:04d}.json' for i in range(18)}
        if {p.name for p in (run/'workers').iterdir()} != expected:
            raise ValueError('Missing or unexpected confirmation worker records')
        for name in expected:
            if (restored/'workers'/name).read_bytes() != (run/'workers'/name).read_bytes():
                raise ValueError('Held-out per-worker outcomes changed')
    return {'byte_identical_result': True, 'verified_workers': 18,
            'results_sha256': sha(run/'results.json'), 'release_gate_closed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'evaluate', 'replay'))
    parser.add_argument('run', type=Path)
    parser.add_argument('--application-archive', type=Path)
    parser.add_argument('--inputs', type=Path)
    args = parser.parse_args()
    if args.command == 'freeze':
        result = freeze(args.run.resolve(), args.application_archive, args.inputs)
    elif args.command == 'replay':
        result = replay(args.run.resolve())
    else:
        result = evaluate(args.run.resolve())
    print(json.dumps(result, allow_nan=False))
