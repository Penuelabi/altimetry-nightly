# -*- coding: utf-8 -*-
"""
Verify the county rain outlook against the rain that actually fell.

forecast_log_ens.csv (kept by county_bulletin.py) holds, for every ensemble run, county and lead day:
p_wet (share of members with a wet county-day), median_mm, p20_mm, p80_mm. Here each forecast is
compared with GSMaP v8 (gauge-corrected) for the same UTC day, using the same wet-day definition as
the bulletin (at least WET_AREA_FRACTION of the county's 0.25 deg cells get >= WET_DAY_MM).

Writes to BULLETIN_OUT_DIR (all synced to Drive):
    forecast_verification.csv             per ECMWF cycle (00/12 UTC) and lead day: Brier score, Brier skill
                                          score vs the sample base rate, hit rate (POD), false-alarm ratio,
                                          CSI, accuracy, rain MAE/bias, coverage of the p20-p80 range
    forecast_reliability.csv              forecast probability bins vs how often the day was really wet
    forecast_verification_by_county.csv   Brier score and hit rate per county (leads 1-5 and 6-10)
    forecast_obs_cache.csv                observed county-day rain (so each day is fetched from Earth Engine once)

Method follows the WMO guidance for verifying probabilistic forecasts (Brier score, reliability diagram,
contingency-table scores). With a young log the numbers are noisy: read the "n" column first.
"""
import datetime
import os
import sys

import numpy as np
import pandas as pd

OUT_DIR = os.environ.get('BULLETIN_OUT_DIR', 'bulletin')
WET_DAY_MM = 1.0
WET_AREA_FRACTION = 0.5
P_THRESHOLD = 0.5                    # forecast counts as "wet" for the contingency scores
MIN_N_COUNTY = 30

LOG = os.path.join(OUT_DIR, 'forecast_log_ens.csv')
CACHE = os.path.join(OUT_DIR, 'forecast_obs_cache.csv')
GEOJSON = os.path.join(OUT_DIR, 'counties_dissolved.geojson')


# --------------------------------------------------------------------------- #
# scoring (pure functions)                                                    #
# --------------------------------------------------------------------------- #
def prepare(log, obs):
    """Join the forecast log to observed county-days."""
    f = log.drop_duplicates(['run_utc', 'county', 'valid_date']).copy()
    f['valid_date'] = pd.to_datetime(f['valid_date']).dt.strftime('%Y-%m-%d')
    o = obs.copy()
    o['date'] = pd.to_datetime(o['date']).dt.strftime('%Y-%m-%d')
    d = f.merge(o, left_on=['county', 'valid_date'], right_on=['county', 'date'], how='inner')
    d = d.dropna(subset=['p_wet', 'obs_wet', 'obs_mm'])
    d['run_hour'] = d['run_utc'].astype(str).str[-2:].astype(int)
    d['y'] = d['obs_wet'].astype(float)
    return d


def _contingency(p, y, thr=P_THRESHOLD):
    fc = p >= thr
    h = int((fc & (y == 1)).sum())
    m = int((~fc & (y == 1)).sum())
    fa = int((fc & (y == 0)).sum())
    cn = int((~fc & (y == 0)).sum())
    return h, m, fa, cn


def _scores(g):
    p, y = g['p_wet'].to_numpy(float), g['y'].to_numpy(float)
    base = y.mean()
    brier = float(np.mean((p - y) ** 2))
    ref = base * (1 - base)
    h, m, fa, cn = _contingency(p, y)
    return pd.Series({
        'n': len(g),
        'base_rate_wet': round(base, 3),
        'brier': round(brier, 4),
        'brier_skill_vs_base_rate': round(1 - brier / ref, 3) if ref > 0 else np.nan,
        'POD': round(h / (h + m), 3) if (h + m) else np.nan,
        'FAR': round(fa / (h + fa), 3) if (h + fa) else np.nan,
        'CSI': round(h / (h + m + fa), 3) if (h + m + fa) else np.nan,
        'accuracy': round((h + cn) / len(g), 3),
        'rain_MAE_mm': round(float(np.mean(np.abs(g['median_mm'] - g['obs_mm']))), 2),
        'rain_bias_mm': round(float(np.mean(g['median_mm'] - g['obs_mm'])), 2),
        'p20_p80_coverage': round(float(np.mean((g['obs_mm'] >= g['p20_mm']) & (g['obs_mm'] <= g['p80_mm']))), 3),
    })


def by_lead(d):
    rows = []
    for (rh, lead), g in d.groupby(['run_hour', 'lead_day']):
        s = _scores(g)
        s['run_hour_utc'], s['lead_day'] = rh, lead
        rows.append(s)
    out = pd.DataFrame(rows)
    for c in ('run_hour_utc', 'lead_day', 'n'):
        out[c] = out[c].astype(int)
    cols = ['run_hour_utc', 'lead_day'] + [c for c in out.columns if c not in ('run_hour_utc', 'lead_day')]
    return out[cols].sort_values(['run_hour_utc', 'lead_day']).reset_index(drop=True)


def reliability(d, bins=np.linspace(0, 1, 11)):
    d = d.copy()
    d['lead_group'] = pd.cut(d['lead_day'], [0, 5, 10, 15], labels=['day 1-5', 'day 6-10', 'day 11-15'])
    d['bin'] = pd.cut(d['p_wet'], bins, include_lowest=True)
    rows = []
    for (lg, b), g in d.groupby(['lead_group', 'bin'], observed=True):
        rows.append({'lead_group': lg, 'p_bin': str(b), 'n': len(g),
                     'mean_forecast_p': round(g['p_wet'].mean(), 3),
                     'observed_wet_freq': round(g['y'].mean(), 3)})
    return pd.DataFrame(rows)


def by_county(d):
    rows = []
    for lg, lo, hi in (('day 1-5', 1, 5), ('day 6-10', 6, 10)):
        sub = d[(d['lead_day'] >= lo) & (d['lead_day'] <= hi)]
        for county, g in sub.groupby('county'):
            if len(g) < MIN_N_COUNTY:
                continue
            s = _scores(g)
            rows.append({'lead_group': lg, 'county': county, 'n': int(s['n']), 'brier': s['brier'],
                         'brier_skill_vs_base_rate': s['brier_skill_vs_base_rate'],
                         'POD': s['POD'], 'FAR': s['FAR'], 'rain_bias_mm': s['rain_bias_mm']})
    return pd.DataFrame(rows)


def headline(lead_tbl):
    """One short line per lead group for the bulletin JSON/PDF."""
    if lead_tbl is None or lead_tbl.empty:
        return {}
    out = {}
    for lg, lo, hi in (('day 1-5', 1, 5), ('day 6-10', 6, 10), ('day 11-15', 11, 15)):
        g = lead_tbl[(lead_tbl['lead_day'] >= lo) & (lead_tbl['lead_day'] <= hi)]
        if g.empty or g['n'].sum() == 0:
            continue
        w = g['n']
        out[lg] = {'n': int(w.sum()),
                   'brier_skill': round(float(np.average(g['brier_skill_vs_base_rate'].fillna(0), weights=w)), 2),
                   'hit_rate': round(float(np.average(g['POD'].fillna(0), weights=w)), 2),
                   'false_alarm_ratio': round(float(np.average(g['FAR'].fillna(0), weights=w)), 2)}
    return out


# --------------------------------------------------------------------------- #
# observed rain from GSMaP (Earth Engine)                                     #
# --------------------------------------------------------------------------- #
def fetch_observed(dates, geojson_path):
    """County-day observed rain: obs_mm (county mean), obs_wet_frac, obs_wet. One row per county and date."""
    import json
    import ee
    import ee_util
    ee_util.init_ee()
    gj = json.load(open(geojson_path, encoding='utf-8'))
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f['geometry']), {'county': f['properties']['county']})
                               for f in gj['features']])
    rain = ee.ImageCollection('JAXA/GPM_L3/GSMaP/v8/operational').select('hourlyPrecipRateGC')
    grid = [0.25, 0, -180, 0, -0.25, 90]                      # the 0.25 deg ECMWF ENS grid
    proj = rain.first().projection()
    rows = []
    for d in dates:
        start = ee.Date(d)
        day = rain.filterDate(start, start.advance(1, 'day')).sum().setDefaultProjection(proj)
        coarse = day.reduceResolution(ee.Reducer.mean(), bestEffort=True, maxPixels=1024) \
            .reproject(crs='EPSG:4326', crsTransform=grid).rename('mm')
        img = coarse.addBands(coarse.gte(WET_DAY_MM).rename('wet'))
        res = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), crs='EPSG:4326', crsTransform=grid)
        for f in res.getInfo()['features']:
            p = f['properties']
            if p.get('mm') is None:
                continue
            rows.append({'date': d, 'county': p['county'], 'obs_mm': p['mm'], 'obs_wet_frac': p['wet']})
    out = pd.DataFrame(rows)
    if len(out):
        out['obs_wet'] = (out['obs_wet_frac'] >= WET_AREA_FRACTION).astype(int)
    return out


def last_complete_day():
    import ee
    rain = ee.ImageCollection('JAXA/GPM_L3/GSMaP/v8/operational')
    today = datetime.date.today()
    ms = rain.filterDate((today - datetime.timedelta(days=15)).isoformat(),
                         (today + datetime.timedelta(days=1)).isoformat()).aggregate_max('system:time_start').getInfo()
    t = pd.Timestamp(ms, unit='ms')
    return ((t + pd.Timedelta(hours=1)).floor('D') - pd.Timedelta(days=1)).date()


# --------------------------------------------------------------------------- #
def main():
    if not os.path.exists(LOG):
        sys.exit(f"{LOG} not found; nothing to verify yet")
    log = pd.read_csv(LOG)
    print(f"Forecast log: {len(log)} rows, runs {log['run_utc'].nunique()}, "
          f"valid dates {log['valid_date'].min()} .. {log['valid_date'].max()}")

    cache = pd.read_csv(CACHE) if os.path.exists(CACHE) and os.path.getsize(CACHE) > 5 else pd.DataFrame(
        columns=['date', 'county', 'obs_mm', 'obs_wet_frac', 'obs_wet'])
    need = sorted(set(pd.to_datetime(log['valid_date']).dt.strftime('%Y-%m-%d')) - set(cache['date'].astype(str)))
    if need:
        import ee_util
        ee_util.init_ee()
        last = last_complete_day().isoformat()
        need = [d for d in need if d <= last]
        print(f"Fetching observed GSMaP rain for {len(need)} new days (data complete to {last})")
        if need:
            new = fetch_observed(need, GEOJSON)
            cache = pd.concat([cache, new], ignore_index=True) if len(new) else cache
            cache.to_csv(CACHE, index=False)
    print(f"Observed county-days available: {len(cache)}")

    d = prepare(log, cache)
    if d.empty:
        print("No forecast has a complete observation yet; try again after a few days of data.")
        return
    lead = by_lead(d)
    lead.to_csv(os.path.join(OUT_DIR, 'forecast_verification.csv'), index=False)
    reliability(d).to_csv(os.path.join(OUT_DIR, 'forecast_reliability.csv'), index=False)
    by_county(d).to_csv(os.path.join(OUT_DIR, 'forecast_verification_by_county.csv'), index=False)
    print(f"Verified {len(d)} county-day forecasts")
    print(lead.groupby('run_hour_utc').apply(lambda g: g[['lead_day', 'n', 'brier_skill_vs_base_rate', 'POD', 'FAR',
                                                          'rain_bias_mm']].head(8)).to_string())


if __name__ == '__main__':
    main()
