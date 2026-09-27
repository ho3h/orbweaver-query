"""All runtime comparison arms must return the same filtered, serialized rows."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from test_execution import fixture
from test_plan import assert_records

from orbweaver_query import ExplicitPathModel, GraphSnapshot


def test_composed_benchmark_controls_preserve_complete_outputs(tmp_path):
    folder = Path(__file__).resolve().parents[1]/'benchmarks/v1'
    spec = importlib.util.spec_from_file_location('plan_runtime_test',folder/'plan_runtime.py')
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    shutil.copyfile(folder/'plan_reference.py',tmp_path/'plan_reference.py')
    edges, source, fitted = fixture(4,n=20,r=1)
    graph = GraphSnapshot(edges,node_ids=source.node_ids,relations=('LINK',))
    model = ExplicitPathModel(fitted.coefficient,relations=graph.relations)
    graph.save(tmp_path/'collaboration-outer.npz')
    model.save(tmp_path/'collaboration-path-model.npz')
    rows = [{'head':f'n{h}','relation':'LINK','target':f'n{t}','ordinal':i}
            for i,(h,t) in enumerate((h,t) for h in range(5) for t in range(20))]
    rows += [rows[5], {'head':None,'relation':'LINK','target':None,'ordinal':-1}]
    (tmp_path/'collaboration-queries.json').write_text(json.dumps({'distinct128':rows,'calibration':rows[:40]}))
    jobs = [{'dataset':'collaboration','shape':shape,'workload':'distinct128','arm':arm,'replicate':0}
            for shape in benchmark.SHAPES for arm in benchmark.ARMS]
    (tmp_path/'manifest.json').write_text(json.dumps({'files':{},'jobs':jobs,'warmup':1,'samples':1}))
    path_before = sys.path.copy()
    try:
        results = [benchmark.worker(tmp_path,i) for i in range(len(jobs))]
    finally:
        sys.path[:] = path_before
        sys.modules.pop('plan_reference',None)
    for shape in benchmark.SHAPES:
        selected = [r for r in results if r['job']['shape']==shape]
        expected = selected[0]['output']
        assert expected
        for result in selected:
            assert_records(result['output'],expected)
            assert np.isfinite(result['samples_seconds']).all()
            assert result['samples_seconds'][0]>0
            assert result['calibration_seconds']>=0 and result['preparation_seconds']>=0
        assert next(r for r in selected if r['job']['arm']=='pair_warm')['work']['pair_cache']['hits']>0
        warm = next(r for r in selected if r['job']['arm']=='precomputed')
        assert warm['cache']['evictions']==0 and warm['cache']['feature_hits']>0
    assert len(results[0]['output'])==len(rows)
    assert len(results[len(benchmark.ARMS)]['output'])<len(rows)
