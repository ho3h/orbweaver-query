"""Frozen development benchmark for exact bound-target inference and strong caches.

This measures runtime correctness and latency, not model quality. The movies and
collaboration coefficients are deterministic test weights, not learned models.
"""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time

ARMS = ('full', 'lru64k', 'lru16m', 'targeted', 'precomputed')
WORKLOADS = ('single', 'distinct128', 'interleaved256', 'clustered256',
             'many_targets256', 'hubs16', 'duplicates256')
THREADS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
           'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def freeze(run, prior_runs, collaboration):
    import numpy as np
    from orbweaver_query import GraphSnapshot, ExplicitPathModel

    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[2]
    shutil.copytree(package/'src/orbweaver_query', run/'source/orbweaver_query',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copyfile(package/'benchmarks/cache_reference.py', run/'cache_reference.py')
    shutil.copyfile(__file__, run/'targeted.py')
    shutil.copyfile(Path(__file__).with_name('ACCEPTANCE.md'), run/'ACCEPTANCE.md')
    graphs = {}
    for name, parent, graph_file, model_file in (
        ('wordnet', 'model-installed-v1', '71-graph.npz', '71-model.npz'),
        ('movies', 'public-movies-model-v1', 'graph.npz', 'test-model.npz'),
    ):
        source = prior_runs/parent
        for a, b in ((graph_file, f'{name}-graph.npz'), (model_file, f'{name}-model.npz')):
            shutil.copyfile(source/a, run/b)
        graph = GraphSnapshot.load(run/f'{name}-graph.npz')
        model = ExplicitPathModel.load(run/f'{name}-model.npz')
        graphs[name] = (graph, model)
    if sha(collaboration) != 'a254442cdf5d684712578b630c2e0d7543518ab154ef2341cabb607572ce7230':
        raise ValueError('Unexpected SNAP ca-GrQc checksum')
    pairs = sorted({tuple(sorted(map(int, line.split())))
                    for line in gzip.decompress(collaboration.read_bytes()).decode().splitlines()
                    if line and not line.startswith('#')})
    nodes = sorted({n for pair in pairs for n in pair})
    index = {n: i for i, n in enumerate(nodes)}
    graph = GraphSnapshot([(index[a], 0, index[b]) for a, b in pairs if a != b],
                          node_ids=[str(n) for n in nodes], relations=('coauthor',))
    model = ExplicitPathModel(np.random.default_rng(20260926).normal(size=(1, 16)),
                              relations=graph.relations)
    graph.save(run/'collaboration-graph.npz')
    model.save(run/'collaboration-model.npz')
    graphs['collaboration'] = graph, model
    inventory = {}
    for name, (graph, model) in graphs.items():
        rng = np.random.default_rng(2026092601)
        heads = rng.choice(np.flatnonzero(graph.degree), 128, replace=False)
        def row(head, ordinal):
            head = int(head)
            # Input-only candidate construction: one two-step random walk, with
            # every fourth endpoint drawn from the full domain (often unsupported).
            if ordinal % 4:
                first = int(rng.choice(graph.neighbors(head)))
                target = int(rng.choice(graph.neighbors(first)))
            else:
                target = int(rng.integers(len(graph.node_ids)))
            return dict(head=graph.node_ids[head], relation=graph.relations[ordinal % len(graph.relations)],
                        target=graph.node_ids[target], ordinal=ordinal)
        interleaved = [row(h, i) for i, h in enumerate(np.tile(heads[:32], 8))]
        clustered = sorted(interleaved, key=lambda x: x['head'])
        sets = {'single': [row(heads[0], 1)],
                'distinct128': [row(h, i) for i, h in enumerate(heads)],
                'interleaved256': interleaved, 'clustered256': clustered,
                'many_targets256': [row(heads[0], i) for i in range(256)],
                'hubs16': [row(h, i) for i, h in enumerate(np.argsort(-graph.degree, kind='stable')[:16])],
                'duplicates256': [row(heads[0], 1)]*256}
        write(run/f'{name}-queries.json', sets)
        inventory[name] = dict(nodes=len(graph.node_ids), edges=len(graph.triples()),
                               graph_id=graph.snapshot_id, model_id=model.model_id)
    jobs = [dict(graph=g, workload=w, arm=a, replicate=i)
            for g in graphs for w in WORKLOADS for a in ARMS for i in range(3)]
    random.Random(2026092601).shuffle(jobs)
    files = {str(p.relative_to(run)): sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    write(run/'manifest.json', dict(format='bound-target-development-v1', files=files,
        jobs=jobs, inventory=inventory, warmup=1, samples=3,
        collaboration_source='https://snap.stanford.edu/data/ca-GrQc.html',
        collaboration_sha256=sha(collaboration), quality_claim=False,
        precomputation='Oracle working set of requested sources and relations; full candidate output. '
                       'Warm lookup is a floor, not a free cold-start baseline.'))
    return dict(jobs=len(jobs), inventory=inventory, manifest_sha256=sha(run/'manifest.json'))


def checked(run):
    manifest = read(run/'manifest.json')
    for name, expected in manifest['files'].items():
        if sha(run/name) != expected:
            raise ValueError(f'Frozen file changed: {name}')
    return manifest


def worker(run, index):
    sys.path.insert(0, str(run/'source'))
    sys.path.insert(0, str(run))
    import numpy as np
    from types import MappingProxyType
    from orbweaver_query import GraphSnapshot, ExplicitPathModel, Session, score_bindings
    from orbweaver_query.bindings import BindingResult, ScoredBinding
    from cache_reference import lru_score_bindings

    manifest = checked(run)
    job = manifest['jobs'][index]
    graph = GraphSnapshot.load(run/f"{job['graph']}-graph.npz")
    model = ExplicitPathModel.load(run/f"{job['graph']}-model.npz")
    session = Session(graph, model)
    rows = read(run/f"{job['graph']}-queries.json")[job['workload']]
    prepared, prepare_seconds, prepared_bytes = {}, 0.0, 0
    if job['arm'] == 'precomputed':
        began = time.perf_counter()
        grouped = {}
        for row in rows:
            grouped.setdefault(row['head'], set()).add(row['relation'])
        for head, relations in grouped.items():
            features = model.expand(graph, graph.node_index(head), session.limits)
            for relation in relations:
                scores = model.score(features, graph.relation_index(relation))
                prepared[head, relation] = {graph.node_ids[int(n)]: float(s)
                                           for n, s in zip(features.candidates, scores)}
                prepared_bytes += features.candidates.nbytes + scores.nbytes
        prepare_seconds = time.perf_counter() - began
    samples, identity, numeric_max = [], None, 0
    for rep in range(manifest['warmup'] + manifest['samples']):
        before = time.perf_counter()
        arm = job['arm']
        if arm in ('full', 'targeted'):
            result = score_bindings(session, rows, execution=arm)
            work = [dict(p.__dict__) for p in result.profiles]
            numeric_max = max(p.peak_feature_bytes for p in result.profiles)
        elif arm.startswith('lru'):
            result, work = lru_score_bindings(session, rows,
                                max_numeric_bytes=64*1024 if arm == 'lru64k' else 16*2**20)
            numeric_max = work['peak_cached_numeric_bytes']
        else:
            output = []
            for row in rows:
                score = prepared[row['head'], row['relation']].get(row['target'])
                output.append(ScoredBinding(MappingProxyType(dict(row)), score,
                    'unsupported' if score is None else 'scored', graph.snapshot_id, model.model_id))
            result, work = BindingResult(tuple(output), ()), {'precomputed': True}
            numeric_max = prepared_bytes
        elapsed = time.perf_counter() - before
        payload = result.to_records()
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        if identity is None:
            identity = digest
        elif identity != digest:
            raise ValueError('Repeated execution changed output')
        if rep >= manifest['warmup']:
            samples.append(elapsed)
    import resource
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return dict(job=job, samples_seconds=samples, preparation_seconds=prepare_seconds,
                median_seconds=float(np.median(samples)), peak_rss_bytes=int(rss if sys.platform=='darwin' else rss*1024),
                retained_numeric_bytes=numeric_max, output=payload, output_sha256=identity, work=work)


def execute(run):
    manifest = checked(run)
    folder = run/'workers'
    folder.mkdir(exist_ok=True)
    for i, job in enumerate(manifest['jobs']):
        path = folder/f'{i:04d}.json'
        if path.exists():
            continue
        env = {**os.environ, **{k: '1' for k in THREADS}}
        process = subprocess.run([sys.executable, str(run/'targeted.py'), 'worker', str(run), '--index', str(i)],
                                 env=env, capture_output=True, text=True)
        if process.returncode:
            write(folder/f'{i:04d}-error.json', dict(job=job, stdout=process.stdout, stderr=process.stderr))
            raise RuntimeError(f'Worker {i} failed: {process.stderr}')
        write(path, json.loads(process.stdout))
        if i % 15 == 0:
            print(f'{i + 1}/{len(manifest["jobs"])} workers', flush=True)
    return dict(workers=len(manifest['jobs']))


def summarize(run):
    import numpy as np
    manifest = checked(run)
    records = [read(run/'workers'/f'{i:04d}.json') for i in range(len(manifest['jobs']))]
    outcomes, max_error = [], 0.0
    for graph in manifest['inventory']:
        for workload in WORKLOADS:
            selected = [r for r in records if r['job']['graph'] == graph and r['job']['workload'] == workload]
            reference = next(r['output'] for r in selected if r['job']['arm'] == 'full')
            arms = {}
            for arm in ARMS:
                rs = [r for r in selected if r['job']['arm'] == arm]
                for record in rs:
                    assert len(record['output']) == len(reference)
                    for a, b in zip(reference, record['output']):
                        a, b = dict(a), dict(b)
                        pa, pb = dict(a.pop('prediction')), dict(b.pop('prediction'))
                        va, vb = pa.pop('score'), pb.pop('score')
                        assert a == b and pa == pb
                        if va is None or vb is None:
                            assert va == vb
                        else:
                            np.testing.assert_allclose(va, vb, rtol=1e-12, atol=1e-12)
                            max_error = max(max_error, abs(va-vb))
                arms[arm] = dict(ms=float(np.median([r['median_seconds'] for r in rs]))*1000,
                    preparation_ms=float(np.median([r['preparation_seconds'] for r in rs]))*1000,
                    rss_mib=max(r['peak_rss_bytes'] for r in rs)/2**20,
                    numeric_bytes=max(r['retained_numeric_bytes'] for r in rs))
            baseline = min(arms[a]['ms'] for a in ('full', 'lru64k', 'lru16m'))
            outcomes.append(dict(graph=graph, workload=workload, arms=arms,
                strongest_ondemand_speedup=baseline/arms['targeted']['ms'],
                precompute_warm_speedup=arms['precomputed']['ms']/arms['targeted']['ms']))
    ratios = [x['strongest_ondemand_speedup'] for x in outcomes]
    report = dict(manifest_sha256=sha(run/'manifest.json'), checked_workers=len(records),
                  max_absolute_error=max_error, numerical_parity=True,
                  geometric_mean_ondemand_speedup=float(np.exp(np.mean(np.log(ratios)))),
                  outcomes=outcomes, environment=dict(python=sys.version, platform=platform.platform()),
                  gate_A_complete=False, reason='Development run only; update and multi-model workloads pending.')
    write(run/'results.json', report)
    return {k: v for k, v in report.items() if k != 'outcomes'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('freeze', 'execute', 'worker', 'summarize'))
    parser.add_argument('run', type=Path)
    parser.add_argument('--prior-runs', type=Path)
    parser.add_argument('--collaboration', type=Path)
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    run = args.run.resolve()
    if args.command == 'freeze':
        result = freeze(run, args.prior_runs.resolve(), args.collaboration.resolve())
    elif args.command == 'execute':
        result = execute(run)
    elif args.command == 'worker':
        result = worker(run, args.index)
    else:
        result = summarize(run)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
