"""Render all on-demand competitors; warm/ablation results remain in the full table."""

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

folder = Path(__file__).resolve().parent
report = json.loads((folder / 'analysis.json').read_text())
conditions = {x['workload']: x for x in report['conditions']}
order = ('single', 'basket_with_repeat', 'filtered_basket')
labels = ('Single film · 8 rows', 'Repeated basket · 36 rows', 'Filtered basket · 4 rows')
arms = ('native_cypher', 'manual_intersection', 'full_source_shared', 'plan')
names = ('Native Cypher', 'Manual intersection', 'Shared full expansion', 'Composed plan')
colors = ('#ca8a04', '#15803d', '#64748b', '#1d4ed8')
fig, axes = plt.subplots(1, 2, figsize=(12, 5.1))
for ax, metric, raw, title in zip(axes,
        ('request_ms', 'first_use_ms'),
        ('process_request_medians_ms', 'process_first_use_ms'),
        ('Repeated request, including JSON', 'Client first use, including export')):
    for j, (arm, label, color) in enumerate(zip(arms, names, colors)):
        values = [conditions[c]['arms'][arm][metric] for c in order]
        samples = [conditions[c]['arms'][arm][raw] for c in order]
        errors = [[v - min(s) for v, s in zip(values, samples)],
                  [max(s) - v for v, s in zip(values, samples)]]
        x = np.arange(3) + (j - 1.5) * .19
        if metric == 'request_ms':
            ax.bar(x, values, .18, label=label, color=color, yerr=errors,
                   capsize=2, error_kw={'linewidth': .8})
        else:
            ax.errorbar(x, values, yerr=errors, fmt='o', color=color,
                        capsize=3, markersize=5, linewidth=1)
    ax.set_xticks(np.arange(3), labels, fontsize=9)
    ax.set_ylabel('Milliseconds · lower is better')
    ax.set_title(title, fontsize=12, loc='left', pad=13)
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='y', alpha=.17)
    ax.set_axisbelow(True)
axes[1].set_yscale('log')
axes[1].set_ylabel('Milliseconds, log scale · lower is better')
axes[1].set_ylim(8, 1000)
axes[1].set_yticks([10, 20, 50, 100, 200, 500], ['10', '20', '50', '100', '200', '500'])
fig.suptitle('A complete graph-scoring workflow on one Mac', x=.055, ha='left', fontsize=18)
fig.legend(*axes[0].get_legend_handles_labels(), loc='upper center',
           bbox_to_anchor=(.51, .90), ncol=4, frameon=False, fontsize=9)
fig.text(.055, .035, '63 clients · median of 3 processes; whiskers show their range. '
         'Requested quiet window had substantial background activity.\n'
         'One small public movie graph; no general speedup or isolated latency claim.', fontsize=9)
fig.subplots_adjust(left=.065, right=.985, top=.76, bottom=.19, wspace=.22)
fig.savefig(folder / 'costs.svg')
fig.savefig(folder / 'costs.png', dpi=160)
