"""Prespecified v3 comparisons against the strongest control in each reuse regime.

Three process medians are resampled independently per arm and condition. These
intervals condition on the measured graphs, queries and tuning; they are not
confidence intervals for arbitrary new applications.
"""

import argparse
import json
from pathlib import Path

import numpy as np

COMPARISONS = {
    'ordered_vs_cold': ('ordered', ('separate', 'separate_ordered', 'pair_cold',
                                   'lru64k_cold', 'lru16m_cold')),
    'cached_cold_vs_cold': ('cached_cold', ('separate', 'separate_ordered', 'pair_cold',
                                         'lru64k_cold', 'lru16m_cold')),
    'cached_warm_vs_warm': ('cached_warm', ('pair_warm', 'lru16m_warm', 'precomputed')),
    'fusion_given_ordering': ('ordered', ('separate_ordered',)),
    'ordering_given_fusion': ('ordered', ('fused',)),
}
REQUEST_COUNTS = (None, 1, 10, 100, 1000)


def analyze(run):
    report = json.loads((run/'results.json').read_text())
    manifest = json.loads((run/'manifest.json').read_text())
    if not report['numerical_parity'] or report['verified_workers'] != len(manifest['jobs']):
        raise ValueError('Complete numerical verification is required before comparison')
    records = [json.loads((run/'workers'/f'{i:04d}.json').read_text())
               for i in range(len(manifest['jobs']))]
    result = {}
    for comparison, (candidate, baselines) in COMPARISONS.items():
        regimes = {}
        for requests in REQUEST_COUNTS:
            rng = np.random.default_rng(8107)
            ratios, regressions, conditions = [], [], []
            bootstrap_logs = np.zeros(10000)
            for outcome in report['outcomes']:
                condition = tuple(outcome[k] for k in ('dataset', 'workload', 'shape'))
                samples, point = {}, {}
                for arm in (candidate, *baselines):
                    matches = [r for r in records if r['job']['arm'] == arm and
                               tuple(r['job'][k] for k in ('dataset', 'workload', 'shape')) == condition]
                    if len(matches) != 3:
                        raise ValueError('Each arm/condition needs three process repetitions')
                    values = np.array([r['median_seconds'] + (0 if requests is None else
                        (r['calibration_seconds']+r['preparation_seconds'])/requests) for r in matches])
                    point[arm] = float(np.median(values))
                    samples[arm] = np.median(rng.choice(values, size=(10000, 3)), axis=1)
                strongest = min(baselines, key=lambda a: point[a])
                ratio = point[strongest]/point[candidate]
                ratios.append(ratio)
                bootstrap_best = np.min([samples[a] for a in baselines], axis=0)
                bootstrap_logs += np.log(bootstrap_best/samples[candidate])
                row = {'condition': condition, 'strongest_control': strongest,
                       'candidate_ms': point[candidate]*1000, 'control_ms': point[strongest]*1000,
                       'speedup': ratio}
                conditions.append(row)
                if point[candidate] > 1.1*point[strongest]:
                    regressions.append(row)
            regimes['steady_state' if requests is None else f'{requests}_requests'] = {
                'geometric_mean_speedup': float(np.exp(np.mean(np.log(ratios)))),
                'conditional_process_bootstrap_95_interval': np.quantile(
                    np.exp(bootstrap_logs/len(ratios)), [.025, .975]).tolist(),
                'regressions_over_ten_percent': regressions, 'conditions': conditions}
        result[comparison] = {'candidate': candidate, 'controls': list(baselines), 'regimes': regimes}
    return {'comparisons': result, 'bootstrap_samples': 10000, 'seed': 8107,
            'point_estimate': 'median of three per-process request-plus-amortized-setup values',
            'setup_scope': 'calibration and preparation; common graph/model load excluded',
            'limitations': 'Fixed development inputs, reused for implementation choices. Independent process resampling; no new-graph or confirmation inference.',
            'acceptance_gates_closed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = analyze(args.run)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: {r: v['geometric_mean_speedup'] for r, v in c['regimes'].items()}
                      for k, c in result['comparisons'].items()}))
