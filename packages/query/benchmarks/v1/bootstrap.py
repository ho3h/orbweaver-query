"""Exploratory timing uncertainty conditional on the frozen development workloads."""

import argparse
import hashlib
import json
from pathlib import Path


def analyze(run, draws=5000):
    import numpy as np
    report = json.loads((run/'results.json').read_text())
    workers = [json.loads(p.read_text()) for p in sorted((run/'workers').glob('*.json'))]
    rng = np.random.default_rng(20260926)
    distributions, conditions = [], []
    for outcome in report['outcomes']:
        selected = [r for r in workers if r['job']['graph'] == outcome['graph']
                    and r['job']['workload'] == outcome['workload']]
        arms = {}
        for arm in ('full','lru64k','lru16m','lru_guarded','full_guarded','targeted'):
            values = np.array([r['median_seconds'] for r in selected if r['job']['arm'] == arm])
            arms[arm] = np.median(rng.choice(values, (draws, len(values)), replace=True), axis=1)
        strongest = np.min([v for k, v in arms.items() if k != 'targeted'], axis=0)
        ratios = strongest / arms['targeted']
        distributions.append(ratios)
        conditions.append({'graph': outcome['graph'],'workload': outcome['workload'],
                               'ratio_interval_95': np.quantile(ratios,[.025,.975]).tolist()})
    aggregate = np.exp(np.mean(np.log(distributions),axis=0))
    output = {'results_sha256': hashlib.sha256((run/'results.json').read_bytes()).hexdigest(),
        'draws': draws,'seed': 20260926,'conditions': conditions,
        'aggregate_ratio_interval_95': np.quantile(aggregate,[.025,.975]).tolist(),
        'interpretation': 'Exploratory resampling of three fresh-process medians per arm, '
        'conditional on this fixed workload mix. Not a confirmation test or uncertainty '
        'over new machines/graphs. Minimum baseline reselected within each draw.'}
    with (run/'bootstrap.json').open('x') as stream:
        json.dump(output,stream,indent=2)
        stream.write('\n')
    return output['aggregate_ratio_interval_95']


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    print(analyze(parser.parse_args().run))
