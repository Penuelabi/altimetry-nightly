"""ECMWF open-data (IFS) gap-fill for ERA5-Land soil moisture, runoff and 2 m temperature.

ERA5-Land reaches Earth Engine about 10 days late. For the days it has not published yet,
merge_dahiti_hydroweb.py normally uses the ERA5-Land day-of-year average. This module supplies
real recent values from the ECMWF IFS open data instead, adapted to ERA5-Land:

  VARIABLES (IFS open data -> ERA5-Land definition)
    2t   2 m temperature, K                 mean of the 4 step-0 fields (00/06/12/18 UTC)
    vsw  volumetric soil water, layer 1     mean of the 4 step-0 fields (0-7 cm, same layer as swvl1)
    ro   runoff, accumulated since the run  00 UTC run, step 24 = the UTC day's runoff (m)
    Evaporation is NOT in IFS open data, so total evaporation keeps the day-of-year average.

  ADAPTATION (IFS is not ERA5-Land): for days where both exist, a rolling 60-day comparison gives
    * temperature and soil moisture: an additive offset per station (median of ERA5-Land minus IFS)
    * runoff: a multiplicative ratio per station (sum ERA5-Land / sum IFS, limited to 0.1-10)
    A station with fewer than MIN_PAIR_DAYS paired days uses the all-station median; with no usable
    pairs at all, nothing is substituted and the day stays on the climatology average.

  AVAILABILITY: the ECMWF server keeps ~4 days of runs, the AWS mirror keeps longer. Every run
  appends the days it can reach to a cache file, so coverage builds up night by night.

Everything here is plain functions; Earth Engine calls stay in merge_dahiti_hydroweb.py.
"""
import os
import tempfile

import numpy as np
import pandas as pd

CYCLES = (0, 6, 12, 18)
SOURCES = ('aws', 'ecmwf')
LAT_RANGE, LON_RANGE = (-5.0, 17.0), (24.0, 38.0)        # sub-grid searched for the nearest cell
MIN_PAIR_DAYS = 10
ADAPT_WINDOW_DAYS = 60
RO_MIN_SUM_M = 0.002          # below this total (2 mm over the window) the runoff ratio is not fitted
RO_RATIO_LIMITS = (0.1, 10.0)
SW_LIMITS = (0.0, 0.6)
MISS_RETRY_DAYS = 5           # a day with no data is retried only while it is this recent
IFS_COLS = ['date', 'station_uid', 't2m_k', 'swvl1', 'ro_m', 'fetched_on']
VARS = ['t2m_k', 'swvl1', 'ro_m']
MISS_UID = '__none__'


# --- GRIB reading ---------------------------------------------------------------
_GRID_CACHE = {}


def _nearest_index(gid, lat, lon):
    """Flat grid index of the nearest cell for every station (regular lat/lon grid)."""
    import eccodes as ec
    key = (ec.codes_get(gid, 'Ni'), ec.codes_get(gid, 'Nj'),
           round(ec.codes_get(gid, 'latitudeOfFirstGridPointInDegrees'), 4),
           round(ec.codes_get(gid, 'longitudeOfFirstGridPointInDegrees'), 4))
    if key not in _GRID_CACHE:
        la = ec.codes_get_array(gid, 'latitudes')
        lo = ec.codes_get_array(gid, 'longitudes')
        lo = np.where(lo > 180, lo - 360, lo)
        sub = np.where((la >= LAT_RANGE[0]) & (la <= LAT_RANGE[1])
                       & (lo >= LON_RANGE[0]) & (lo <= LON_RANGE[1]))[0]
        _GRID_CACHE[key] = (sub, la[sub], lo[sub])
    sub, la, lo = _GRID_CACHE[key]
    dlat = lat[:, None] - la[None, :]
    dlon = (lon[:, None] - lo[None, :]) * np.cos(np.radians(lat[:, None]))
    return sub[np.argmin(dlat ** 2 + dlon ** 2, axis=1)]


def read_points(path, lat, lon):
    """{name: array over stations} for one GRIB file. name = shortName, soil layer 1 -> 'vsw1'."""
    import eccodes as ec
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    out, n_soil = {}, 0
    with open(path, 'rb') as f:
        while True:
            gid = ec.codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                name = ec.codes_get(gid, 'shortName')
                level = int(ec.codes_get(gid, 'level'))
                if name in ('vsw', 'swvl1'):
                    n_soil += 1
                    if name == 'vsw' and level > 1:
                        continue                     # only the top soil layer (0-7 cm)
                    if name == 'vsw' and level == 0 and n_soil > 1:
                        continue                     # level not encoded: layers run shallow -> deep
                    name = 'vsw1'
                ec.codes_set(gid, 'missingValue', 1e30)
                vals = ec.codes_get_values(gid)[_nearest_index(gid, lat, lon)].astype(float)
                vals[vals >= 1e29] = np.nan
                try:
                    units = ec.codes_get(gid, 'units')
                except Exception:
                    units = ''
                if name == 'ro' and 'kg' in units:      # kg m-2 -> m of water
                    vals = vals / 1000.0
                out[name] = vals
            finally:
                ec.codes_release(gid)
    return out


# --- Retrieval ------------------------------------------------------------------
def _retrieve(date, time_, step, params, workdir, sources):
    """Download one run's fields; returns a GRIB path or None."""
    from ecmwf.opendata import Client
    target = os.path.join(workdir, f"ifs_{date:%Y%m%d}_{time_:02d}_{step}.grib2")
    for src in sources:
        try:
            Client(source=src, model='ifs', resol='0p25').retrieve(
                date=int(f"{date:%Y%m%d}"), time=time_, step=step, type='fc',
                param=list(params), target=target)
            if os.path.exists(target) and os.path.getsize(target) > 0:
                return target
        except Exception:
            continue
    return None


def fetch_ifs_day(date, lat, lon, workdir=None, sources=SOURCES):
    """Daily IFS values at the stations for one UTC day, or None when the day is not complete."""
    workdir = workdir or tempfile.mkdtemp()
    t2m, sw = [], []
    for cyc in CYCLES:
        p = _retrieve(date, cyc, 0, ('2t', 'vsw'), workdir, sources)
        if p is None:
            return None                      # a daily mean from fewer than 4 times would be biased
        got = read_points(p, lat, lon)
        os.remove(p)
        if '2t' not in got or 'vsw1' not in got:
            return None
        t2m.append(got['2t'])
        sw.append(got['vsw1'])
    p = _retrieve(date, 0, 24, ('ro',), workdir, sources)
    ro = None
    if p is not None:
        got = read_points(p, lat, lon)
        os.remove(p)
        ro = got.get('ro')
    n = len(lat)
    return {'t2m_k': np.mean(t2m, axis=0), 'swvl1': np.mean(sw, axis=0),
            'ro_m': ro if ro is not None else np.full(n, np.nan)}


def load_cache(path):
    if os.path.exists(path):
        c = pd.read_csv(path, dtype={'date': str, 'station_uid': str})
        for col in IFS_COLS:
            if col not in c:
                c[col] = np.nan
        return c[IFS_COLS]
    return pd.DataFrame(columns=IFS_COLS)


def update_ifs_cache(stations, path, today, lookback_days=40, max_days=40, workdir=None,
                     sources=SOURCES, log=print):
    """Add the IFS days that can still be reached (newest first). Returns the cache DataFrame."""
    cache = load_cache(path)
    have_ok = set(cache.loc[cache.station_uid != MISS_UID, 'date'])
    miss = cache[cache.station_uid == MISS_UID].set_index('date')['fetched_on'].to_dict()
    lat, lon = stations['latitude'].to_numpy(float), stations['longitude'].to_numpy(float)
    uids = stations['station_uid'].to_numpy()
    new_rows, tried, got_days, dry = [], 0, 0, 0
    for k in range(1, lookback_days + 1):
        d = today - pd.Timedelta(days=k)
        ds = f"{d:%Y-%m-%d}"
        if ds in have_ok:
            continue
        if ds in miss and k > MISS_RETRY_DAYS:
            continue                          # old day already known to be gone
        if tried >= max_days or dry >= 4:
            break                             # 4 empty days in a row: older runs are no longer served
        tried += 1
        try:
            res = fetch_ifs_day(d, lat, lon, workdir, sources)
        except Exception as e:                # missing package / network: never stop the pipeline
            log(f"  IFS {ds}: {str(e)[:100]}")
            res = None
        if res is None:
            dry += 1
            new_rows.append(pd.DataFrame([{'date': ds, 'station_uid': MISS_UID, 't2m_k': np.nan,
                                           'swvl1': np.nan, 'ro_m': np.nan,
                                           'fetched_on': f"{today:%Y-%m-%d}"}]))
            continue
        dry = 0
        got_days += 1
        new_rows.append(pd.DataFrame({'date': ds, 'station_uid': uids, 't2m_k': res['t2m_k'],
                                      'swvl1': res['swvl1'], 'ro_m': res['ro_m'],
                                      'fetched_on': f"{today:%Y-%m-%d}"}))
    if new_rows:
        add = pd.concat(new_rows, ignore_index=True)
        done = set(add.loc[add.station_uid != MISS_UID, 'date'])
        drop = cache.station_uid.eq(MISS_UID) & cache.date.isin(set(add.date)) | cache.date.isin(done)
        cache = pd.concat([cache[~drop], add], ignore_index=True)
        cache.to_csv(path, index=False)
    log(f"ECMWF IFS cache: {got_days} new day(s) added, "
        f"{cache.loc[cache.station_uid != MISS_UID, 'date'].nunique()} day(s) in total")
    return cache


# --- Adaptation to ERA5-Land -----------------------------------------------------
def fit_adaptation(ifs, era5, today, window_days=ADAPT_WINDOW_DAYS, min_days=MIN_PAIR_DAYS):
    """Per-station offsets/ratios (row '*' = all-station fallback). None when there is too little overlap.

    ifs, era5: DataFrames with date, station_uid, t2m_k, swvl1, ro_m (era5 = ERA5-Land daily values).
    """
    a = ifs[ifs.station_uid != MISS_UID]
    p = a.merge(era5, on=['date', 'station_uid'], suffixes=('_ifs', '_era5'))
    p = p[pd.to_datetime(p.date) >= today - pd.Timedelta(days=window_days)]
    if p.empty or p.date.nunique() < min_days:
        return None
    rows = {}
    for var in VARS:
        x = p[[f'{var}_ifs', f'{var}_era5', 'station_uid', 'date']].dropna()
        if x.date.nunique() < min_days:
            continue
        if var == 'ro_m':
            g = x.groupby('station_uid').agg(i=(f'{var}_ifs', 'sum'), e=(f'{var}_era5', 'sum'),
                                             n=('date', 'nunique'))
            ok = (g.n >= min_days) & (g.i >= RO_MIN_SUM_M)
            st = (g.e / g.i.where(g.i > 0)).where(ok).clip(*RO_RATIO_LIMITS)
            tot_i, tot_e = x[f'{var}_ifs'].sum(), x[f'{var}_era5'].sum()
            dom = float(np.clip(tot_e / tot_i, *RO_RATIO_LIMITS)) if tot_i >= RO_MIN_SUM_M else 1.0
        else:
            d = (x[f'{var}_era5'] - x[f'{var}_ifs']).groupby(x.station_uid)
            g = pd.DataFrame({'m': d.median(), 'n': x.groupby('station_uid').date.nunique()})
            st = g.m.where(g.n >= min_days)
            dom = float((x[f'{var}_era5'] - x[f'{var}_ifs']).median())
        st = st.copy()
        st.loc['*'] = dom
        rows[var] = st
    if not rows:
        return None
    return pd.DataFrame(rows)


def adapt_ifs(ifs, adapt):
    """IFS daily values adapted to ERA5-Land. Variables without a fitted adaptation become NaN."""
    a = ifs[ifs.station_uid != MISS_UID].copy()
    for var in VARS:
        if adapt is None or var not in adapt:
            a[var] = np.nan
            continue
        par = a.station_uid.map(adapt[var]).fillna(adapt[var].loc['*'])
        if var == 'ro_m':
            a[var] = (a[var] * par).clip(lower=0)
        elif var == 'swvl1':
            a[var] = (a[var] + par).clip(*SW_LIMITS)
        else:
            a[var] = a[var] + par
    return a


# --- Fill the climate rows ---------------------------------------------------------
def apply_ifs_fill(c, adapted, doy_clim, window_days=15):
    """Swap the climatology contribution of missing ERA5-Land days for adapted IFS values.

    c        : climate rows with station_uid, date_key, era5_missing ('YYYY-MM-DD,...'), t2m_mean,
               swvl1_mean, ro_sum (these contain the day-of-year average for the missing days)
    adapted  : output of adapt_ifs
    doy_clim : DataFrame station_uid, doy, t2m, swvl1, ro  (the average that was used for the fill)
    Adds era5_days_ifs (days with at least one variable replaced).
    """
    c = c.copy()
    c['era5_days_ifs'] = 0.0
    if adapted is None or adapted.empty or doy_clim is None or doy_clim.empty:
        return c
    A = {(r.station_uid, r.date): (r.t2m_k, r.swvl1, r.ro_m) for r in adapted.itertuples()}
    C = {(r.station_uid, int(r.doy)): (r.t2m, r.swvl1, r.ro) for r in doy_clim.itertuples()}
    if 'era5_missing' not in c:
        return c
    sub = c[c['era5_missing'].fillna('').astype(str) != '']
    for i, row in sub.iterrows():
        miss = row['era5_missing']
        dt_t = dt_s = dt_r = 0.0
        n_days = 0
        for ds in miss.split(','):
            a = A.get((row.station_uid, ds))
            cl = C.get((row.station_uid, int(pd.Timestamp(ds).day_of_year)))
            if a is None or cl is None:
                continue
            used = False
            if np.isfinite(a[0]) and np.isfinite(cl[0]):
                dt_t += (a[0] - cl[0]) / window_days
                used = True
            if np.isfinite(a[1]) and np.isfinite(cl[1]):
                dt_s += (a[1] - cl[1]) / window_days
                used = True
            if np.isfinite(a[2]) and np.isfinite(cl[2]):
                dt_r += a[2] - cl[2]
                used = True
            n_days += int(used)
        if n_days:
            c.at[i, 't2m_mean'] = row.t2m_mean + dt_t
            c.at[i, 'swvl1_mean'] = row.swvl1_mean + dt_s
            c.at[i, 'ro_sum'] = max(row.ro_sum + dt_r, 0.0)
            c.at[i, 'era5_days_ifs'] = float(n_days)
    return c


# --- Self-test (no network) --------------------------------------------------------
def _selftest():
    import eccodes as ec
    tmp = tempfile.mkdtemp()
    lat = np.array([5.0, 8.1])
    lon = np.array([30.0, 31.3])
    # synthetic 0.25 degree GRIB with 2t, vsw level 1 and 2, ro (m)
    path = os.path.join(tmp, 't.grib2')
    with open(path, 'wb') as f:
        for name, level, base in (('2t', 0, 300.0), ('vsw', 1, 0.30), ('vsw', 2, 0.10), ('ro', 0, 0.004)):
            g = ec.codes_grib_new_from_samples('regular_ll_sfc_grib2')
            ec.codes_set(g, 'Ni', 1440)
            ec.codes_set(g, 'Nj', 721)
            ec.codes_set(g, 'latitudeOfFirstGridPointInDegrees', 90.0)
            ec.codes_set(g, 'latitudeOfLastGridPointInDegrees', -90.0)
            ec.codes_set(g, 'longitudeOfFirstGridPointInDegrees', 0.0)
            ec.codes_set(g, 'longitudeOfLastGridPointInDegrees', 359.75)
            ec.codes_set(g, 'iDirectionIncrementInDegrees', 0.25)
            ec.codes_set(g, 'jDirectionIncrementInDegrees', 0.25)
            ec.codes_set(g, 'shortName', name)
            if level:
                for k, v in (('typeOfFirstFixedSurface', 151), ('scaleFactorOfFirstFixedSurface', 0),
                             ('scaledValueOfFirstFixedSurface', level), ('typeOfSecondFixedSurface', 255)):
                    ec.codes_set(g, k, v)
            la = np.repeat(np.linspace(90, -90, 721), 1440)
            ec.codes_set_values(g, base + la / 1000.0)      # value encodes the latitude
            ec.codes_write(g, f)
            ec.codes_release(g)
    got = read_points(path, lat, lon)
    assert set(got) == {'2t', 'vsw1', 'ro'}, got.keys()
    assert abs(got['2t'][0] - (300.0 + 5.0 / 1000)) < 1e-3, got['2t']
    assert abs(got['vsw1'][1] - (0.30 + 8.0 / 1000)) < 2e-3, got['vsw1']       # level 1 only, not 2

    # adaptation: IFS is 2 K too cold, soil 0.05 too dry, runoff half of ERA5-Land
    today = pd.Timestamp('2026-10-27')
    days = [f"{(today - pd.Timedelta(days=k)):%Y-%m-%d}" for k in range(12, 32)]
    rng = np.random.default_rng(1)
    rows_i, rows_e = [], []
    for u in ('a', 'b'):
        for d in days:
            t, s, r = 295 + rng.normal(), 0.2 + rng.normal() * 0.01, abs(rng.normal()) * 0.004
            rows_i.append((d, u, t, s, r, ''))
            rows_e.append((d, u, t + 2, s + 0.05, r * 2))
    ifs = pd.DataFrame(rows_i, columns=IFS_COLS)
    era = pd.DataFrame(rows_e, columns=['date', 'station_uid', 't2m_k', 'swvl1', 'ro_m'])
    ad = fit_adaptation(ifs, era, today)
    assert abs(ad.loc['a', 't2m_k'] - 2) < 1e-6 and abs(ad.loc['*', 'swvl1'] - 0.05) < 1e-6
    assert abs(ad.loc['b', 'ro_m'] - 2) < 1e-6
    assert fit_adaptation(ifs.iloc[:5], era, today) is None
    # fill: window of 15 days, 3 missing days filled with climatology (t=290, sw=0.15, ro=0.001)
    missing = [f"{(today - pd.Timedelta(days=k)):%Y-%m-%d}" for k in (1, 2, 3)]
    new_i = pd.DataFrame([(d, 'a', 293.0, 0.25, 0.002, '') for d in missing], columns=IFS_COLS)
    adapted = adapt_ifs(pd.concat([ifs, new_i], ignore_index=True), ad)
    clim = pd.DataFrame([('a', pd.Timestamp(d).day_of_year, 290.0, 0.15, 0.001) for d in missing],
                        columns=['station_uid', 'doy', 't2m', 'swvl1', 'ro'])
    c = pd.DataFrame([{'station_uid': 'a', 'date_key': f"{today:%Y-%m-%d}",
                       'era5_missing': ','.join(missing), 't2m_mean': 290.0, 'swvl1_mean': 0.15,
                       'ro_sum': 0.015}])
    out = apply_ifs_fill(c, adapted, clim)
    assert out.era5_days_ifs.iloc[0] == 3
    assert abs(out.t2m_mean.iloc[0] - (290 + (293 + 2 - 290) * 3 / 15)) < 1e-6, out.t2m_mean
    assert abs(out.swvl1_mean.iloc[0] - (0.15 + (0.25 + 0.05 - 0.15) * 3 / 15)) < 1e-6
    assert out.ro_sum.iloc[0] > 0.015
    # a row without missing days is left alone
    c2 = c.assign(era5_missing='')
    assert apply_ifs_fill(c2, adapted, clim).era5_days_ifs.iloc[0] == 0
    print('ecmwf_gapfill selftest OK')


if __name__ == '__main__':
    _selftest()
