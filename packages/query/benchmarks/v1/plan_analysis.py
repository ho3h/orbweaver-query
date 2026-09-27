"""Descriptive process-bootstrap analysis for the frozen composed-plan campaign."""

import argparse
import json
from pathlib import Path

import numpy as np


def analyze(run):
    report = json.loads((run/'results.json').read_text())
    records = [json.loads(p.read_text()) for p in sorted((run/'workers').glob('[0-9]*.json'))]
    rng = np.random.default_rng(8106)
    log_ratios = np.zeros(10000)
    ratios, regressions = [], []
    for outcome in report['outcomes']:
        condition = tuple(outcome[k] for k in ('dataset','workload','shape'))
        arms = outcome['arms']
        baseline = min(arms[a]['ms'] for a in ('lru64k_cold','lru16m_cold'))
        ratios.append(baseline/arms['ordered']['ms'])
        if arms['ordered']['ms']>1.1*baseline:
            regressions.append({'condition':condition,'ordered_ms':arms['ordered']['ms'],'baseline_ms':baseline})
        sampled = {}
        for arm in ('ordered','lru64k_cold','lru16m_cold'):
            values = [r['median_seconds'] for r in records if r['job']['arm']==arm and
                      tuple(r['job'][k] for k in ('dataset','workload','shape'))==condition]
            if len(values)!=3:
                raise ValueError('Expected three process repetitions per arm and condition')
            sampled[arm] = np.median(rng.choice(values,size=(10000,3)),axis=1)
        log_ratios += np.log(np.minimum(sampled['lru64k_cold'],sampled['lru16m_cold'])/sampled['ordered'])
    return {'geometric_mean_cold_control_speedup':float(np.exp(np.mean(np.log(ratios)))),
            'conditional_process_bootstrap_95_interval':np.quantile(np.exp(log_ratios/len(ratios)),[.025,.975]).tolist(),
            'method':'10,000 independent resamples of three process medians per arm, seed 8106; fixed workloads and configurations; calibration excluded from this ratio',
            'limitations':'Exploratory development only. This interval does not represent new graphs, query distributions, model choices or confirmation. Warm controls are separate regimes.',
            'regressions_over_ten_percent':regressions,
            'conditions_where_warm_pair_cache_is_fastest':sum(
                x['arms']['pair_warm']['ms']==min(a['ms'] for a in x['arms'].values()) for x in report['outcomes']),
            'conditions':len(ratios)}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    result = analyze(args.run)
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print(json.dumps(result))
