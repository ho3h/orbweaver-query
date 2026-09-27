"""Frozen multi-model execution experiment with strong shared caches."""

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

DATASETS = ('collaboration', 'friendship', 'communication')
WORKLOADS = ('distinct128', 'interleaved256', 'many_targets256', 'hubs128')
SHAPES = ('structural', 'mixed_filter')
ARMS = ('separate', 'fused', 'ordered', 'lru64k_cold', 'lru16m_cold',
        'lru16m_warm', 'precomputed', 'pair_warm')
THREADS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
           'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def checked(run):
    manifest = read(run/'manifest.json')
    for name, digest in manifest['files'].items():
        if sha(run/name) != digest:
            raise ValueError(f'Frozen file changed: {name}')
    return manifest


def freeze(run, quality):
    import numpy as np

    from orbweaver_query import ExplicitPathModel, GraphSnapshot

    run.mkdir(parents=True, exist_ok=False)
    package = Path(__file__).resolve().parents[2]
    shutil.copytree(package/'src/orbweaver_query', run/'source/orbweaver_query',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for filename in ('plan_runtime.py','plan_reference.py','PLAN_RUNTIME_PROTOCOL.md'):
        shutil.copyfile(Path(__file__).with_name(filename),run/filename)
    inventory = {}
    for name in DATASETS:
        for suffix in ('outer.npz','path-model.npz'):
            shutil.copyfile(quality/f'{name}-{suffix}',run/f'{name}-{suffix}')
        graph = GraphSnapshot.load(run/f'{name}-outer.npz')
        model = ExplicitPathModel.load(run/f'{name}-path-model.npz')
        def row(head, ordinal, rng, graph=graph):
            head = int(head)
            if ordinal % 4 and graph.degree[head]:
                intermediate = int(rng.choice(graph.neighbors(head)))
                target = int(rng.choice(graph.neighbors(intermediate)))
            else:
                target = int(rng.integers(len(graph.node_ids)))
            return {'head':graph.node_ids[head], 'relation':'LINK', 'target':graph.node_ids[target],
                    'ordinal':ordinal}
        rng = np.random.default_rng(8103)
        heads = rng.choice(np.flatnonzero(graph.degree),128,replace=False)
        patterns = {'distinct128':heads, 'interleaved256':np.tile(heads[:16],16),
                    'many_targets256':np.repeat(heads[0],256),
                    'hubs128':np.tile(np.argsort(-graph.degree,kind='stable')[:8],16)}
        queries = {k:[*[row(h,i,rng) for i,h in enumerate(values)],
                       {'head':None,'relation':'LINK','target':None,'ordinal':-1}]
                   for k,values in patterns.items()}
        rng = np.random.default_rng(8104)
        queries['calibration'] = [row(h,i,rng) for i,h in enumerate(
            rng.choice(np.flatnonzero(graph.degree),64,replace=False))]
        write(run/f'{name}-queries.json',queries)
        inventory[name] = {'snapshot_id':graph.snapshot_id,'path_model_id':model.model_id,
                           'nodes':len(graph.node_ids),'directed_edges':len(graph.triples())}
    jobs = [{'dataset':d,'workload':w,'shape':s,'arm':a,'replicate':r}
            for d in DATASETS for w in WORKLOADS for s in SHAPES for a in ARMS for r in range(3)]
    random.Random(8105).shuffle(jobs)
    files = {str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    write(run/'manifest.json',{'format':'orbweaver-plan-development-v1','files':files,'jobs':jobs,
                              'inventory':inventory,'warmup':1,'samples':3,'quality_claim':False})
    return {'jobs':len(jobs),'manifest_sha256':sha(run/'manifest.json')}


def worker(run, index):
    sys.path.insert(0,str(run/'source'))
    sys.path.insert(0,str(run))
    import resource

    import numpy as np
    from plan_reference import CachedModel, SharedFeatureLRU

    from orbweaver_query import (
        BindingCache,
        ExplicitPathModel,
        GraphSnapshot,
        NeighborhoodModel,
        QueryPlan,
        Session,
        score_bindings,
    )

    manifest = checked(run)
    job = manifest['jobs'][index]
    dataset, arm = job['dataset'], job['arm']
    graph = GraphSnapshot.load(run/f'{dataset}-outer.npz')
    path = ExplicitPathModel.load(run/f'{dataset}-path-model.npz')
    queries = read(run/f'{dataset}-queries.json')
    rows = queries[job['workload']]
    models = {} if job['shape']=='structural' else {'path':path}
    models.update({m:NeighborhoodModel(relations=graph.relations,metric=m)
                   for m in ('resource_allocation','adamic_adar','common_neighbors')})
    thresholds = {} if job['shape']=='structural' else {'resource_allocation':.2}
    columns = ('head','relation','target','ordinal',*models)
    cache = None
    if arm.startswith('lru') or arm=='precomputed':
        cache = SharedFeatureLRU(64*1024 if arm=='lru64k_cold' else 2**30 if arm=='precomputed' else 16*2**20)
    plan = QueryPlan(graph)
    for name, model in models.items():
        plan = plan.predict(name,model if cache is None else CachedModel(model,cache))
        if name in thresholds:
            plan = plan.where_score(name,thresholds[name])
    plan = plan.project(*columns)
    statistics, calibration_seconds = None, 0.
    if arm not in ('separate','fused','pair_warm'):
        before = time.perf_counter()
        statistics = plan.calibrate(queries['calibration'])
        calibration_seconds = time.perf_counter()-before
    if cache is not None:
        cache.clear()
    pair_cache = BindingCache(max_entries=2*len(rows)*len(models)) if arm=='pair_warm' else None
    before = time.perf_counter()
    if arm=='precomputed':
        sources = sorted({graph.node_index(r['head']) for r in rows if r['head'] is not None})
        for head in sources:
            for model in models.values():
                features = cache.features(model,graph,head,plan.limits)
                cache.score(model,features,0)
        if cache.evictions:
            raise ValueError('Oracle working set exceeds its declared budget')
    elif arm=='lru16m_warm':
        plan.run(rows,statistics=statistics)
    elif arm=='pair_warm':
        for model in models.values():
            score_bindings(Session(graph,model),rows,cache=pair_cache)
    preparation_seconds = time.perf_counter()-before if arm in ('precomputed','lru16m_warm','pair_warm') else 0.
    samples, identity = [], None
    for repeat in range(manifest['warmup']+manifest['samples']):
        if arm.endswith('_cold'):
            cache.clear()
        before = time.perf_counter()
        if arm=='pair_warm':
            payload = rows
            # With every pair cached, evaluate the only selective operator first.
            order = sorted(models,key=lambda name:name not in thresholds)
            for name in order:
                result = score_bindings(Session(graph,models[name]),payload,cache=pair_cache)
                if name in thresholds:
                    result = result.where_score(thresholds[name])
                payload = result.to_records(prediction_column=name)
            payload = [{k:r[k] for k in columns} for r in payload]
        else:
            result = plan.run(rows,fused=arm!='separate',statistics=statistics)
            payload = result.to_records()
        encoded = json.dumps(payload,sort_keys=True,allow_nan=False).encode()
        elapsed = time.perf_counter()-before
        work = {'pair_cache':pair_cache.info().__dict__} if arm=='pair_warm' else result.report()
        digest = hashlib.sha256(encoded).hexdigest()
        if identity is not None and identity!=digest:
            raise ValueError('Repeated execution changed outputs')
        identity = digest
        if repeat>=manifest['warmup']:
            samples.append(elapsed)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'job':job,'samples_seconds':samples,'median_seconds':float(np.median(samples)),
            'calibration_seconds':calibration_seconds,'preparation_seconds':preparation_seconds,
            'peak_rss_bytes':int(rss if sys.platform=='darwin' else rss*1024),
            'cache':None if cache is None else cache.info(),'work':work,'output':payload,
            'output_sha256':identity,'environment':{'python':sys.version,'platform':platform.platform()}}


def execute(run):
    manifest = checked(run)
    folder = run/'workers'
    folder.mkdir(exist_ok=True)
    for index,job in enumerate(manifest['jobs']):
        output = folder/f'{index:04d}.json'
        if output.exists():
            continue
        error = folder/f'{index:04d}-error.json'
        if error.exists():
            raise ValueError('Failed attempt already exists; preserve it and freeze a fresh campaign')
        env = {**os.environ,**{key:'1' for key in THREADS}}
        result = subprocess.run([sys.executable,str(run/'plan_runtime.py'),'worker',str(run),'--index',str(index)],
                                 env=env,capture_output=True,text=True,check=False)
        if result.returncode:
            write(error,{'job':job,'stdout':result.stdout,'stderr':result.stderr})
            raise RuntimeError(f'Worker {index} failed: {result.stderr}')
        write(output,json.loads(result.stdout))
        if index%12==0:
            print(f'{index+1}/{len(manifest["jobs"])} workers',flush=True)
    return {'workers':len(manifest['jobs'])}


def summarize(run):
    import numpy as np

    manifest = checked(run)
    workers = [read(run/'workers'/f'{i:04d}.json') for i in range(len(manifest['jobs']))]
    for record, job in zip(workers, manifest['jobs']):
        assert record['job'] == job
    outcomes, error = [], 0.
    for dataset in DATASETS:
        for workload in WORKLOADS:
            for shape in SHAPES:
                records = [r for r in workers if (r['job']['dataset'],r['job']['workload'],r['job']['shape'])
                           == (dataset,workload,shape)]
                reference = next(r['output'] for r in records if r['job']['arm']=='lru16m_cold')
                for record in records:
                    assert len(record['output'])==len(reference)
                    for actual,expected in zip(record['output'],reference):
                        assert actual.keys()==expected.keys()
                        for key,value in actual.items():
                            if not isinstance(value,dict):
                                assert value==expected[key]
                                continue
                            a,b = dict(value),dict(expected[key])
                            x,y = a.pop('score'),b.pop('score')
                            assert a==b
                            if x is None or y is None:
                                assert x==y
                            else:
                                np.testing.assert_allclose(x,y,atol=1e-12,rtol=1e-12)
                                error = max(error,abs(x-y))
                arms = {}
                for arm in ARMS:
                    rs = [r for r in records if r['job']['arm']==arm]
                    latency = float(np.median([r['median_seconds'] for r in rs]))
                    setup = float(np.median([r['calibration_seconds']+r['preparation_seconds'] for r in rs]))
                    arms[arm] = {'ms':1000*latency,'calibration_ms':1000*float(np.median([r['calibration_seconds'] for r in rs])),
                        'preparation_ms':1000*float(np.median([r['preparation_seconds'] for r in rs])),
                        'peak_rss_mib':max(r['peak_rss_bytes'] for r in rs)/2**20,
                        'amortized_ms':{str(n):1000*(latency+setup/n) for n in (1,10,100,1000)}}
                outcomes.append({'dataset':dataset,'workload':workload,'shape':shape,'output_rows':len(reference),'arms':arms})
    result = {'manifest_sha256':sha(run/'manifest.json'),'verified_workers':len(workers),
              'max_absolute_error':error,'numerical_parity':True,'outcomes':outcomes,'gate_A_complete':False}
    write(run/'results.json',result)
    return {k:v for k,v in result.items() if k!='outcomes'}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('freeze','execute','worker','summarize'))
    parser.add_argument('run',type=Path)
    parser.add_argument('--quality-run',type=Path)
    parser.add_argument('--index',type=int)
    args = parser.parse_args()
    root = args.run.resolve()
    if args.command=='freeze':
        report = freeze(root,args.quality_run)
    elif args.command=='execute':
        report = execute(root)
    elif args.command=='worker':
        report = worker(root,args.index)
    else:
        report = summarize(root)
    print(json.dumps(report,allow_nan=False))
