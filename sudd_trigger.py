# -*- coding: utf-8 -*-
"""
Experimental Sudd-wide river trigger (from flood_trigger_analysis.py / regional_trigger.py, 2020-2025).

Regional upstream level = mean, over counties that have recorded flood displacement, of the monthly maximum level
percentile (of each station's own record) at the 3 nearest upstream stations. In the 2020-2025 test a level above
about the 55th percentile one month ahead flagged 4 of 6 flood onsets with no false alarms, and above the 70th
percentile was the best one-month-ahead threshold for flood months in general. Six onsets is a tiny sample: this is
an experiment to be scored in 2026, not a validated warning. Every run is logged to sudd_trigger_log.csv.
"""
import os
import numpy as np
import pandas as pd

WATCH, ELEVATED = 0.55, 0.70
LOG = 'sudd_trigger_log.csv'


def status(v):
    if v is None or pd.isna(v):
        return 'no data'
    return 'elevated' if v >= ELEVATED else ('watch' if v >= WATCH else 'normal')


def compute(merged_csv, counties_geojson, displacement_csv, today=None):
    import geopandas as gpd
    import flood_trigger_analysis as fta
    today = pd.Timestamp(today or pd.Timestamp.now('UTC').tz_localize(None))
    disp = pd.read_csv(displacement_csv)
    flood_counties = sorted(disp.loc[disp.flood > 0, 'county'].unique())
    counties = gpd.read_file(counties_geojson)
    counties = counties[counties.county.isin(flood_counties)].reset_index(drop=True)
    st = fta.station_table(pd.read_csv(merged_csv, low_memory=False))
    ml = fta.monthly_levels(st)
    assign = fta.assign_stations(counties, ml)
    this = pd.Period(today, 'M')
    months = pd.period_range(this - 3, this, freq='M')
    lf = fta.level_features(assign, ml, months)
    out = {}
    for k in ('upstream', 'local', 'downstream'):
        col = f'lvl_{k}'
        out[k] = lf.groupby('ym')[col].mean().reindex(months) if col in lf else pd.Series(np.nan, index=months)
    df = pd.DataFrame(out)
    df.index.name = 'month'
    last = df['upstream'].last_valid_index()
    prev = df['upstream'].dropna().index[-2] if df['upstream'].notna().sum() > 1 else None
    res = {'as_of': str(today.date()), 'latest_month': str(last) if last is not None else None,
           'upstream_pct': None if last is None else float(df.loc[last, 'upstream']),
           'local_pct': None if last is None or pd.isna(df.loc[last, 'local']) else float(df.loc[last, 'local']),
           'downstream_pct': None if last is None or pd.isna(df.loc[last, 'downstream']) else float(df.loc[last, 'downstream']),
           'previous_month': str(prev) if prev is not None else None,
           'previous_upstream_pct': None if prev is None else float(df.loc[prev, 'upstream']),
           'watch_at': WATCH, 'elevated_at': ELEVATED,
           'n_counties': int(counties.shape[0]), 'n_upstream_stations': int(assign[assign.group == 'upstream'].station_uid.nunique()),
           'experimental': True}
    res['status'] = status(res['upstream_pct'])
    res['text'] = trigger_text(res)
    return res, df


def trigger_text(r):
    if r['upstream_pct'] is None:
        return 'Sudd river trigger (experimental): no recent upstream altimetry passes.'
    s = (f"Sudd river trigger (experimental): upstream levels at the {r['upstream_pct'] * 100:.0f}th percentile of their "
         f"record in {r['latest_month']} -> {r['status'].upper()} "
         f"(watch from {WATCH * 100:.0f}th, elevated from {ELEVATED * 100:.0f}th). ")
    if r['status'] == 'normal':
        return s + 'No flood-displacement signal expected next month from the river.'
    return s + 'In 2020-2025 such levels often preceded flood displacement in the Sudd counties within about a month.'


def append_log(res, out_dir):
    path = os.path.join(out_dir, LOG)
    row = {k: res.get(k) for k in ('latest_month', 'as_of', 'upstream_pct', 'local_pct', 'downstream_pct', 'status')}
    old = None
    if os.path.exists(path) and os.path.getsize(path) > 20:
        try:
            old = pd.read_csv(path)
        except Exception:
            old = None
    new = pd.DataFrame([row])
    log = new if old is None else pd.concat([old[old.latest_month != row['latest_month']], new], ignore_index=True)
    log.sort_values('latest_month').to_csv(path, index=False)
    return path
