"""Step 4 — the headline chart. Reads results/quarterly_vh_db.csv."""
import pandas as pd, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
ROOT=__import__('pathlib').Path(__file__).resolve().parents[1]
Q=pd.read_csv(ROOT/'results'/'quarterly_vh_db.csv',index_col=0)
lab={'T1_ntt_fdc__v1':'T1  NTT FDC campus  (treatment)','C1_hkex_dc__v1':'C1  HKEX data centre  (control)',
     'P1_vacant__v1':'P1  vacant lot  (placebo)','C2b_amc__v2':'C2b  Advanced Manufacturing Centre  (build 2018-2022)',
     'X1_build_slab__v1':'X1  works lot, structure  (positive control)','X2_build_site__v1':'X2  works lot, whole site  (positive control)'}
col={'T1_ntt_fdc__v1':'#20808D','C1_hkex_dc__v1':'#1B474D','P1_vacant__v1':'#848456',
     'C2b_amc__v2':'#A84B2F','X1_build_slab__v1':'#DA7101','X2_build_site__v1':'#944454'}
ls={'T1_ntt_fdc__v1':'-','C1_hkex_dc__v1':'--','P1_vacant__v1':':','C2b_amc__v2':'-','X1_build_slab__v1':'-','X2_build_site__v1':'-'}
x=np.arange(len(Q.index))
fig,ax=plt.subplots(figsize=(13.5,7.2),dpi=170)
fig.patch.set_facecolor('#F7F6F2'); ax.set_facecolor('#F7F6F2')
for c in ['T1_ntt_fdc__v1','C1_hkex_dc__v1','P1_vacant__v1','C2b_amc__v2','X1_build_slab__v1','X2_build_site__v1']:
    ax.plot(x,Q[c].values,color=col[c],ls=ls[c],lw=2.1 if c.startswith(('C2b','X')) else 1.5,
            label=lab[c],alpha=1.0 if c.startswith(('C2b','X','T1')) else .8)
for qn,txt,cc,yy in [('2017Q1','works-lot onset 2017Q1  (both orbits)','#DA7101',3.6),
                     ('2018Q2','AMC onset 2018Q2  (both orbits)','#A84B2F',2.2)]:
    i=list(Q.index).index(qn); ax.axvline(i,color=cc,lw=1,ls='--',alpha=.55)
    ax.annotate(txt,xy=(i,yy),xytext=(i+0.5,yy),fontsize=9,color=cc,va='center')
ax.set_ylim(-17,4.6); ax.set_xlim(-0.5,len(x)-0.5)
tick=[i for i,q in enumerate(Q.index) if q.endswith('Q1')]
ax.set_xticks(tick); ax.set_xticklabels([Q.index[i][:4] for i in tick],fontsize=9.5)
ax.yaxis.set_major_locator(MultipleLocator(2.5))
ax.tick_params(labelsize=9.5,colors='#28251D')
ax.set_ylabel('VH  γ⁰  quarterly mean (dB)',fontsize=10.5,color='#28251D')
ax.set_title('Construction is visible; an operating data centre is flat',fontsize=15.5,color='#28251D',pad=30,loc='left',weight='bold')
ax.text(0,1.018,'Sentinel-1 RTC, VH, ascending orbits 11 + 113, 608 S1A scenes, 2015-06 to 2026-06 · Tseung Kwan O InnoPark',
        transform=ax.transAxes,fontsize=9.5,color='#7A7974')
for s in ('top','right'): ax.spines[s].set_visible(False)
for s in ('bottom','left'): ax.spines[s].set_color('#D4D1CA')
ax.grid(axis='y',color='#D4D1CA',lw=.6,alpha=.6); ax.set_axisbelow(True)
ax.legend(fontsize=9,frameon=False,loc='lower right',ncol=2,columnspacing=1.4,labelcolor='#28251D')
fig.tight_layout(); out=ROOT/'results'/'tko_vh_quarterly.png'
fig.savefig(out,facecolor=fig.get_facecolor())
print('wrote',out)
