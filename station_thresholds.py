# -*- coding: utf-8 -*-
"""
Flood-level thresholds per altimetry station, and the latest status against them.

For every station the annual maximum water level is taken from the merged altimetry file
(QC-passed observations only) and a Gumbel distribution is fitted to give the levels expected
to be exceeded on average once in 2, 5 and 10 years. Stations with too short a record get
indicative percentile levels instead and are flagged as low confidence.

Caveat: altimetry samples a river every 10-35 days, so the observed annual maximum is usually
lower than the true peak. The thresholds are therefore "as seen by the satellite", not gauge
return periods. Use them to rank stations and to compare like with like over time.

Used by station_status.py (nightly run). Pure functions, no network.
"""
import numpy as np
import pandas as pd

LEVEL_COL = 'Water Surface Elevation - values(m)'
MIN_OBS_PER_YEAR = 6          # a year counts for the annual maximum only with this many passes
MIN_YEARS_GUMBEL = 8          # fewer annual maxima than this -> percentile fallback
MIN_MARGIN_M = 0.15           # exceeding the 2-yr level by less than this is within altimetry error -> 'Near', not 'Above'
MIN_SPREAD_M = 0.25           # 2-yr to 10-yr spread below this is within altimetry error -> low confidence
STALE_DAYS = 60               # latest pass older than this -> status "stale"
EULER = 0.5772156649


def gumbel_levels(annual_max, return_periods=(2, 5, 10)):
    """Return levels from annual maxima (method of moments)."""
    x = np.asarray(annual_max, dtype=float)
    beta = x.std(ddof=1) * np.sqrt(6) / np.pi
    mu = x.mean() - EULER * beta
    return {T: mu - beta * np.log(-np.log(1 - 1.0 / T)) for T in return_periods}


def _station_key(df):
    """Column identifying a station; builds station_uid ('dahiti:213') from source + station_id when absent."""
    if 'station_uid' not in df.columns and {'source', 'station_id'} <= set(df.columns):
        sid = pd.to_numeric(df['station_id'], errors='coerce')
        df['station_uid'] = (df['source'].astype(str).str.lower() + ':'
                             + sid.round().astype('Int64').astype(str)).where(sid.notna())
    return 'station_uid' if 'station_uid' in df.columns else 'station_id'


def compute_thresholds(df, today=None):
    """One row per station: thresholds + latest status. `df` is merged_altimetry_stations.csv."""
    today = pd.Timestamp(today or pd.Timestamp.utcnow().tz_localize(None)).normalize()
    d = df.copy()
    d['date'] = pd.to_datetime(d['date'], errors='coerce')
    d[LEVEL_COL] = pd.to_numeric(d[LEVEL_COL], errors='coerce')
    d = d.dropna(subset=['date', LEVEL_COL])
    key = _station_key(d)

    qc_ok = d['qc_status'].astype(str).str.lower().eq('ok') if 'qc_status' in d.columns else None
    use = d[qc_ok] if qc_ok is not None and qc_ok.mean() > 0.5 else d

    rows = []
    for uid, g in use.groupby(key):
        g = g.sort_values('date')
        yearly = g.groupby(g['date'].dt.year)[LEVEL_COL].agg(['max', 'count'])
        yearly = yearly[yearly['count'] >= MIN_OBS_PER_YEAR]
        n_years = len(yearly)
        lv = g[LEVEL_COL].to_numpy()
        if n_years >= MIN_YEARS_GUMBEL and yearly['max'].std(ddof=1) > 0:
            lev = gumbel_levels(yearly['max'])
            method = 'gumbel (annual maxima)'
            conf = 'medium' if n_years < 15 else 'high'
        elif len(lv) >= 20:
            lev = dict(zip((2, 5, 10), np.percentile(lv, (85, 95, 99))))
            method = 'percentile 85/95/99 (short record)'
            conf = 'low'
        else:
            continue
        # keep the levels ordered even when the fit is noisy
        l2, l5, l10 = sorted((lev[2], lev[5], lev[10]))
        if l10 - l2 < MIN_SPREAD_M:
            conf = 'low'
            method += '; 2-10 yr spread < %.2f m (within altimetry error)' % MIN_SPREAD_M
        last = g.iloc[-1]
        level = float(last[LEVEL_COL])
        age = int((today - last['date'].normalize()).days)
        if level >= l10:
            status = 'Above 10-yr level'
        elif level >= l5:
            status = 'Above 5-yr level'
        elif level >= l2 + MIN_MARGIN_M:
            status = 'Above 2-yr level'
        elif level >= l2:
            status = 'Near 2-yr level (within error)'
        else:
            status = 'Below 2-yr level'
        if age > STALE_DAYS:
            status_shown = f'Stale (last pass {age} d ago)'
        else:
            status_shown = status
        rec = {
            'station_uid': uid,
            'type': last.get('type'),
            'name': last.get('location/river_name'),
            'latitude': last.get('latitude'),
            'longitude': last.get('longitude'),
            'n_obs': int(len(g)),
            'n_years': int(n_years),
            'lvl_2yr_m': round(l2, 3), 'lvl_5yr_m': round(l5, 3), 'lvl_10yr_m': round(l10, 3),
            'thr_method': method, 'thr_confidence': conf,
            'last_date': last['date'].date().isoformat(),
            'days_since_obs': age,
            'last_level_m': round(level, 3),
            'vs_2yr_m': round(level - l2, 3),
            'flood_status': status_shown,
            'flood_status_raw': status,
        }
        for extra in ('level_class', 'seasonal_pctile', 'rate_m_per_day'):
            if extra in g.columns:
                v = last.get(extra)
                rec[extra] = None if pd.isna(v) else (round(float(v), 4) if extra != 'level_class' else v)
        rows.append(rec)
    return pd.DataFrame(rows)


if __name__ == '__main__':
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else 'merged_altimetry_stations.csv'
    out = compute_thresholds(pd.read_csv(src, low_memory=False))
    print(out['flood_status'].value_counts())
    out.to_csv('station_flood_thresholds.csv', index=False)
