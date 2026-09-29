# -*- coding: utf-8 -*-
"""
River discharge outlook for the altimetry stations, from the GEOGLOWS ECMWF Streamflow model.

Each river station is snapped to the nearest GEOGLOWS river reach. From the latest 51-member
ensemble forecast (15 days) we take the current flow, the expected peak, and the share of
members that exceed the model's 2 / 5 / 10 / 25-year return-period flows. This sits next to the
observed altimetry level: the altimetry tells you what the river IS doing, the model tells you
what upstream rain is likely to make it do.

Data: GEOGLOWS v2 forecasts and return periods, open data on AWS (s3://geoglows-v2*), no key.
Everything here is optional: any failure returns an empty table and the nightly run carries on.

Needs: pip install geoglows   (brings xarray, zarr, s3fs, pyarrow)
"""
import datetime
import os

import numpy as np
import pandas as pd

FORECAST_BUCKET = 's3://geoglows-v2-forecasts'
RETURN_PERIODS_URI = 's3://geoglows-v2/retrospective/return-periods.zarr'
METADATA_URL = 'https://geoglows-v2.s3-us-west-2.amazonaws.com/tables/v2-model-table.parquet'
BBOX = (22.0, -3.0, 37.0, 14.0)         # lon_min, lat_min, lon_max, lat_max (Nile headwaters to the Sudd)
SNAP_MAX_KM = 15.0                      # stations further than this from any reach are skipped
RP_LIST = (2, 5, 10, 25)
TREND_PCT = 15.0                        # peak vs now beyond +/- this share = rising / falling


# --------------------------------------------------------------------------- #
# reach lookup                                                                #
# --------------------------------------------------------------------------- #
def load_metadata(cache_dir):
    """LINKNO, lat, lon (+ upstream area if present) for reaches inside BBOX."""
    import pyarrow.parquet as pq
    import requests
    path = os.path.join(cache_dir, 'v2-model-table.parquet')
    if not os.path.exists(path):
        with requests.get(METADATA_URL, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(path, 'wb') as fh:
                for chunk in r.iter_content(1 << 22):
                    fh.write(chunk)
    names = pq.read_schema(path).names
    area = next((c for c in names if c.lower() in ('uparea', 'usconarea', 'upstream_area', 'drainagearea',
                                                    'dscontarea', 'drainage_area')), None)
    cols = ['LINKNO', 'lat', 'lon'] + ([area] if area else [])
    m = pd.read_parquet(path, columns=cols)
    m = m[(m['lon'].between(BBOX[0], BBOX[2])) & (m['lat'].between(BBOX[1], BBOX[3]))].reset_index(drop=True)
    m = m.rename(columns={area: 'area'} if area else {})
    return m


def snap_stations(stations, meta):
    """Nearest reach per station (prefers the larger river among near-equal candidates)."""
    lat, lon = meta['lat'].to_numpy(), meta['lon'].to_numpy()
    area = meta['area'].to_numpy() if 'area' in meta.columns else None
    ids, dist_km = [], []
    for _, s in stations.iterrows():
        dlat = lat - s['latitude']
        dlon = (lon - s['longitude']) * np.cos(np.radians(s['latitude']))
        d = np.sqrt(dlat ** 2 + dlon ** 2) * 111.0
        i = int(np.argmin(d))
        if area is not None:
            near = np.where(d <= d[i] + 2.0)[0]            # within 2 km of the closest reach
            i = int(near[np.argmax(area[near])])
        ids.append(int(meta['LINKNO'].iloc[i]))
        dist_km.append(float(d[i]))
    out = stations.copy()
    out['river_id'] = ids
    out['snap_km'] = np.round(dist_km, 1)
    return out


# --------------------------------------------------------------------------- #
# data access                                                                 #
# --------------------------------------------------------------------------- #
def open_latest_forecast(xr, today=None, tries=5):
    today = today or datetime.datetime.utcnow().date()
    last_err = None
    for k in range(tries):
        day = today - datetime.timedelta(days=k)
        uri = f'{FORECAST_BUCKET}/{day:%Y%m%d}00.zarr'
        try:
            ds = xr.open_zarr(uri, zarr_format=2, storage_options={'anon': True})
            return ds, day
        except Exception as e:
            last_err = e
    raise RuntimeError(f'no GEOGLOWS forecast found in the last {tries} days ({last_err})')


def fetch(river_ids, chunk=100):
    """(forecast array [reach, member, time], times, return-period frame) for the given reaches."""
    import xarray as xr
    ids = sorted(set(int(i) for i in river_ids))
    ds, day = open_latest_forecast(xr)
    q_all, times = [], None
    for k in range(0, len(ids), chunk):
        part = ids[k:k + chunk]
        q = ds['Qout'].sel(rivid=part).transpose('rivid', 'ensemble', 'time').load()
        q_all.append(q.to_numpy())
        times = pd.to_datetime(q['time'].to_numpy())
    q_arr = np.concatenate(q_all, axis=0)
    members = ds['ensemble'].to_numpy()
    keep = np.array([int(m) <= 51 for m in members])       # member 52 is the high-resolution run
    q_arr = q_arr[:, keep, :]

    rp = xr.open_zarr(RETURN_PERIODS_URI, zarr_format=2, storage_options={'anon': True})
    rps = {}
    for dist in ('logpearson3', 'gumbel'):
        if dist in rp:
            frame = rp[dist].sel(river_id=ids).to_dataframe().reset_index() \
                .pivot(columns='river_id', index='return_period', values=dist)
            rps[dist] = frame
    return ids, q_arr, times, rps, day


# --------------------------------------------------------------------------- #
# metrics (pure, testable)                                                    #
# --------------------------------------------------------------------------- #
def summarise(ids, q_arr, times, rps):
    """One row per reach from forecast members [reach, member, time] and return-period flows."""
    rows = []
    for r, rid in enumerate(ids):
        q = q_arr[r]                                   # member x time
        if not np.isfinite(q).any():
            continue
        med = np.nanmedian(q, axis=0)
        now = float(med[0])
        pk_i = int(np.nanargmax(med))
        peak = float(med[pk_i])
        member_max = np.nanmax(q, axis=1)
        rec = {'river_id': rid,
               'forecast_start': pd.Timestamp(times[0]).strftime('%Y-%m-%d %H:%M'),
               'flow_now_m3s': round(now, 1),
               'peak_median_m3s': round(peak, 1),
               'peak_date': pd.Timestamp(times[pk_i]).strftime('%Y-%m-%d'),
               'peak_p80_m3s': round(float(np.nanpercentile(member_max, 80)), 1),
               'n_members': int(q.shape[0])}
        change = (peak - now) / now * 100 if now > 0 else np.nan
        rec['flow_trend'] = ('rising' if change > TREND_PCT else 'falling' if change < -TREND_PCT else 'steady') \
            if np.isfinite(change) else 'unknown'
        flows = None
        for dist in ('logpearson3', 'gumbel'):
            frame = rps.get(dist)
            if frame is not None and rid in frame.columns and frame[rid].notna().any():
                flows, rec['rp_method'] = frame[rid], dist
                break
        if flows is not None:
            for T in RP_LIST:
                if T in flows.index and np.isfinite(flows.loc[T]):
                    rec[f'rp{T}_m3s'] = round(float(flows.loc[T]), 1)
                    rec[f'p_exceed_{T}yr'] = round(float(np.mean(member_max >= flows.loc[T])), 2)
        rec['river_alert'] = river_alert(rec)
        rows.append(rec)
    return pd.DataFrame(rows)


def river_alert(rec):
    p5, p2 = rec.get('p_exceed_5yr'), rec.get('p_exceed_2yr')
    if p5 is not None and p5 >= 0.3:
        return 'High flood signal (5-yr flow likely)'
    if p2 is not None and p2 >= 0.5:
        return 'Elevated (2-yr flow likely)'
    if p2 is not None and p2 >= 0.2:
        return 'Watch (2-yr flow possible)'
    if p2 is None:
        return 'no return-period data'
    return 'Normal'


# --------------------------------------------------------------------------- #
# entry point                                                                 #
# --------------------------------------------------------------------------- #
def build(stations, cache_dir):
    """stations: DataFrame with station_uid, latitude, longitude (river stations only).
    Returns (table, message). Never raises."""
    try:
        st = stations.dropna(subset=['latitude', 'longitude']).copy()
        meta = load_metadata(cache_dir)
        st = snap_stations(st, meta)
        st = st[st['snap_km'] <= SNAP_MAX_KM]
        if st.empty:
            return pd.DataFrame(), 'no station within the snap distance of a GEOGLOWS reach'
        ids, q_arr, times, rps, day = fetch(st['river_id'])
        summ = summarise(ids, q_arr, times, rps)
        out = st[['station_uid', 'river_id', 'snap_km']].merge(summ, on='river_id', how='inner')
        return out, f'GEOGLOWS forecast {day:%Y-%m-%d} 00 UTC: {len(out)} stations on {out["river_id"].nunique()} reaches'
    except Exception as e:                                                    # optional product
        return pd.DataFrame(), f'river outlook skipped: {type(e).__name__}: {str(e)[:200]}'
