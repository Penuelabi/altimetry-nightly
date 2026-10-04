# -*- coding: utf-8 -*-
"""Write the Lake Victoria water-level series (DAHITI 2 and Hydroweb 1300000000016) from
merged_altimetry_stations.csv to data/lake_victoria_levels.csv, and print May and Aug-Sep means by year.
Used for the Nile pulse countdown and for checking the lake against earlier years."""
import os
import sys

import pandas as pd

OUT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', 'altdata')
MERGED = os.path.join(OUT_DIR, 'merged_altimetry_stations.csv')
LEVEL_COL = 'Water Surface Elevation - values(m)'
UIDS = ['dahiti:2', 'hydroweb:1300000000016']
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'lake_victoria_levels.csv')

if not os.path.exists(MERGED):
    sys.exit(f'{MERGED} not found')
hdr = pd.read_csv(MERGED, nrows=0).columns
if 'station_uid' not in hdr:
    sys.exit('merged file has no station_uid column: ' + ', '.join(hdr[:20]))
df = pd.read_csv(MERGED, usecols=['station_uid', 'date', LEVEL_COL], low_memory=False)
df['date'] = pd.to_datetime(df['date'], errors='coerce')
df['level_m'] = pd.to_numeric(df[LEVEL_COL], errors='coerce')
d = df[df['station_uid'].astype(str).isin(UIDS)].dropna(subset=['date', 'level_m']).sort_values(['station_uid', 'date'])
os.makedirs(os.path.dirname(DEST), exist_ok=True)
d[['station_uid', 'date', 'level_m']].to_csv(DEST, index=False, date_format='%Y-%m-%d')
print(f'{len(d)} rows -> {DEST}')
d['y'], d['m'] = d['date'].dt.year, d['date'].dt.month
for uid, g in d.groupby('station_uid'):
    print(uid, g['date'].min().date(), 'to', g['date'].max().date())
    print('  May mean:', g[g.m == 5].groupby('y')['level_m'].mean().round(3).loc[2019:].to_dict())
    print('  Aug-Sep mean:', g[g.m.isin([8, 9])].groupby('y')['level_m'].mean().round(3).loc[2019:].to_dict())
