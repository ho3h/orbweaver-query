"""Check production backends and plans against frozen independent sparse scores."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from orbweaver_query import ExplicitPathModel, GraphSnapshot, NeighborhoodModel, QueryPlan


def verify(run):
    reports = {}
    for dataset in ('collaboration', 'friendship', 'communication'):
        graph = GraphSnapshot.load(run/f'{dataset}-outer.npz')
        path = ExplicitPathModel.load(run/f'{dataset}-path-model.npz')
        with np.load(run/f'{dataset}-development.npz', allow_pickle=False) as data:
            sources = data['sources']
        models = {'path':path, **{m:NeighborhoodModel(relations=graph.relations, metric=m)
                                 for m in NeighborhoodModel.metrics}}
        expected = {}
        for name in models:
            with np.load(run/f'{dataset}-{name}-scores.npz', allow_pickle=False) as data:
                expected[name] = data['scores']
        counts, errors = {}, {}
        rng = np.random.default_rng(8102)
        rows = []
        for i, head in enumerate(sources):
            h = int(head)
            for name, model in models.items():
                if name == 'path':
                    continue
                features = model.expand(graph, h, QueryPlan(graph).limits)
                actual = model.score(features, 0)
                reference = expected[name][i, features.candidates]
                np.testing.assert_allclose(actual, reference, atol=1e-12, rtol=1e-12)
                counts[name] = counts.get(name, 0)+len(actual)
                errors[name] = max(errors.get(name, 0.), float(np.max(np.abs(actual-reference), initial=0)))
            for target in rng.choice(len(graph.node_ids), 16, replace=False):
                rows.append({'head':graph.node_ids[h], 'relation':'LINK',
                             'target':graph.node_ids[int(target)], 'source_row':i})
        rows.extend(rows[:17])  # Repeated observations remain repeated rows.
        rows.append({'head':None, 'relation':'LINK', 'target':None, 'source_row':-1})
        plan = QueryPlan(graph)
        for name, model in models.items():
            plan = plan.predict(name, model)
        results = [plan.run(rows, fused=fused) for fused in (False, True)]
        for result in results:
            assert len(result.rows) == len(rows)
            for actual, original in zip(result.rows, rows):
                assert all(actual[key] == value for key, value in original.items())
                for name, model in models.items():
                    prediction = actual[name]
                    assert prediction.snapshot_id == graph.snapshot_id
                    assert prediction.model_id == model.model_id
                    if original['head'] is None:
                        assert prediction.score is None and prediction.status == 'null_input'
                        continue
                    head, target = graph.node_index(original['head']), graph.node_index(original['target'])
                    reference = expected[name][original['source_row'], target]
                    excluded = head == target or target in graph.neighbors(head)
                    if excluded or not np.isfinite(reference):
                        assert prediction.score is None and prediction.status == 'unsupported'
                    else:
                        assert prediction.status == 'scored'
                        np.testing.assert_allclose(prediction.score, reference, atol=1e-12, rtol=1e-12)
        reports[dataset] = {'graph':graph.snapshot_id, 'models':{k:v.model_id for k,v in models.items()},
                            'full_candidate_checks':counts, 'maximum_absolute_errors':errors,
                            'composed_rows_per_strategy':len(rows),
                            'separate_expansions':results[0].report()['expansions'],
                            'fused_expansions':results[1].report()['expansions']}
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    package = Path(__file__).resolve().parents[2]
    files = [*sorted((package/'src/orbweaver_query').glob('*.py')), Path(__file__)]
    receipt = {'source_sha256':{str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in files}, 'datasets':verify(args.run)}
    with args.output.open('x') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps(receipt['datasets'], sort_keys=True))
