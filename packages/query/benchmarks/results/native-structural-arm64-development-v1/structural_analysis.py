"""Descriptive native request comparisons; resample whole database repetitions."""

import argparse
import json
from pathlib import Path

import numpy as np


def analyze(run):
    report = json.loads((run/'results.json').read_text())
    workers = [json.loads(p.read_text()) for p in sorted((run/'workers').glob('[0-9][0-9][0-9][0-9].json'))]
    if len(workers) != 9 or not report['numerical_parity']:
        raise ValueError('Nine verified database workers are required')
    comparisons = {}
    for candidate, controls in (
        ('local_cold', ('gds_native', 'cypher_fused', 'cypher_selective')),
        ('local_warm', ('gds_native', 'cypher_fused', 'cypher_selective', 'precomputed')),
    ):
        regimes = {}
        for requests in (None, 1, 10, 100, 1000):
            rng = np.random.default_rng(8310)
            indices = {d: rng.integers(3, size=(10000, 3)) for d in
                       ('collaboration', 'friendship', 'communication')}
            ratios, conditions, logs = [], [], np.zeros(10000)
            for outcome in report['outcomes']:
                dataset, workload, filtered = (outcome[k] for k in ('dataset', 'workload', 'filtered'))
                ws = sorted((w for w in workers if w['job']['dataset'] == dataset), key=lambda w: w['job']['replicate'])
                medians, sampled = {}, {}
                for arm in (candidate, *controls):
                    values = []
                    for w in ws:
                        record, = [r for r in w['records'] if (r['workload'], r['filtered'], r['arm']) == (workload, filtered, arm)]
                        setup = record['preparation_seconds']
                        if arm in ('local_cold', 'local_warm', 'precomputed'):
                            setup += w['setup']['evidence_export_seconds']
                        values.append(record['median_seconds']+(0 if requests is None else setup/requests))
                    medians[arm] = float(np.median(values))
                    sampled[arm] = np.median(np.array(values)[indices[dataset]], axis=1)
                strongest = min(controls, key=lambda a: medians[a])
                ratio = medians[strongest]/medians[candidate]
                ratios.append(ratio)
                logs += np.log(np.min([sampled[a] for a in controls], axis=0)/sampled[candidate])
                conditions.append({'dataset': dataset, 'workload': workload, 'filtered': filtered,
                    'strongest_control': strongest, 'candidate_ms': 1000*medians[candidate],
                    'control_ms': 1000*medians[strongest], 'speedup': ratio})
            regimes['steady_state' if requests is None else f'{requests}_requests'] = {
                'geometric_mean_speedup': float(np.exp(np.mean(np.log(ratios)))),
                'conditional_database_bootstrap_95_interval': np.quantile(np.exp(logs/24), [.025, .975]).tolist(),
                'conditions': conditions,
                'regressions_over_ten_percent': [c for c in conditions if c['candidate_ms'] > 1.1*c['control_ms']]}
        comparisons[candidate] = {'controls': list(controls), 'regimes': regimes}
    return {'comparisons': comparisons, 'bootstrap_samples': 10000, 'seed': 8310,
            'method': 'Paired whole-database resampling within each graph; retain the same sampled repetitions across arms and conditions; recompute strongest control each draw.',
            'analysis_status': 'Descriptive analysis after collection, on the protocol-defined arms and workloads; not a confirmatory significance test.',
            'limitations': 'Only three independent database repetitions per graph; fixed development graphs/queries. Export and preparation charged; shared import/startup excluded. No per-arm peak-memory claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = analyze(args.run)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({c: {r: {'ratio': v['geometric_mean_speedup'],
        'interval': v['conditional_database_bootstrap_95_interval']} for r, v in d['regimes'].items()}
        for c, d in result['comparisons'].items()}))
