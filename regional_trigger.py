"""Sudd-wide trigger test from flood_trigger_features.csv (output of flood_trigger_analysis.py).
Monthly: any county with flood displacement vs mean river level percentile (Jul-Jan), lags 0-2 months."""
import sys, numpy as np, pandas as pd
from flood_trigger_analysis import auc, best_threshold
p = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else 'flood_trigger_features.csv')
p['ym'] = pd.PeriodIndex(p.ym, freq='M')
cols = {b: b + '__L0' for b in ['lvl_upstream', 'lvl_local', 'lvl_downstream']}
R = p.groupby('ym').agg(n=('y', 'sum'), **{k: (v, 'mean') for k, v in cols.items()}).reset_index().sort_values('ym')
R['y'] = R.n > 0; R['mo'] = R.ym.dt.month
rows = []
for k in cols:
    for L in (0, 1, 2):
        s = R.assign(x=R[k].shift(L)); s = s[s.mo.isin([7, 8, 9, 10, 11, 12, 1])]
        t = best_threshold(s.y.values, s.x.values) or {}
        rows.append(dict(predictor=k, lag_months=L, AUC=round(auc(s.y.values, s.x.values), 2),
                         **{a: (round(t[a], 2) if a in t else None) for a in ['threshold', 'POD', 'FAR', 'hits', 'misses', 'false_alarms']}))
print(pd.DataFrame(rows).to_string(index=False))
