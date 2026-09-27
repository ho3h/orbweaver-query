"""Render results.json with matplotlib 3.10.8; no new measurements."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

folder=Path(__file__).resolve().parent
results=json.loads((folder/'results.json').read_text())
rows=results['outcomes']
fig, axes=plt.subplots(1,2,figsize=(12,11),sharey=True,gridspec_kw={'width_ratios':[1.1,1]})
fig.subplots_adjust(left=.32,right=.95,top=.84,bottom=.16,wspace=.28)
y=list(range(len(rows)))
labels=[r['graph']+' / '+r['workload'] for r in rows]
ratios=[[r['strongest_ondemand_speedup'] for r in rows],
        [r['precompute_warm_speedup'] for r in rows]]
for axis, values, title in zip(axes,ratios,['Strongest on-demand control','Warm precomputed lookup']):
    for pos,value in zip(y,values):
        color='#126d81' if value>=1 else '#b04822'
        axis.plot([1,value],[pos,pos],color=color,alpha=.45,linewidth=1.5)
        axis.scatter(value,pos,color=color,s=30,zorder=3)
        axis.annotate(f'{value:.2f}×',(value,pos),xytext=(5,0),textcoords='offset points',fontsize=8,va='center')
    axis.axvline(1,color='#777777',linestyle='--',linewidth=1)
    axis.set_xscale('log')
    axis.set_title(title,fontsize=12,pad=15)
    axis.grid(axis='x',alpha=.16)
    axis.spines[['top','right','left']].set_visible(False)
    axis.tick_params(axis='y',length=0)
axes[0].set_yticks(y,labels,fontsize=9)
axes[0].invert_yaxis()
axes[0].set_xlim(.45,22)
axes[0].set_xticks([.5,1,2,4,8,16],['0.5','1','2','4','8','16'])
axes[1].set_xlim(.002,1.4)
axes[1].set_xticks([.01,.03,.1,.3,1],['0.01','0.03','0.1','0.3','1'])
fig.suptitle('Exact graph scoring on an M5 Max',x=.32,y=.965,ha='left',fontsize=20,fontweight='bold')
fig.text(.32,.907,'Installed wheel · 648 processes · JSON serialization included\nNormal mixed use; reused development workloads',fontsize=10,color='#444444')
fig.text(.08,.04,'Ratio = control latency / targeted latency. Above 1 favors targeted.\n2.59× on-demand geometric ratio; five >10% regressions. Warm lookup wins all 24.\nBackground CPU activity observed; this does not certify isolated latency or generalization.',fontsize=10,color='#333333',linespacing=1.6)
for suffix in ('svg','png'):
    fig.savefig(folder/f'speedups.{suffix}',dpi=150,metadata={'Creator':'Orbweaver Query benchmark renderer'} if suffix=='svg' else None)
