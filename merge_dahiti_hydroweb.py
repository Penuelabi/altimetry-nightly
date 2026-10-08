# -*- coding: utf-8 -*-
"""
DAHITI + Hydroweb.next satellite altimetry - incremental update in four steps.

STEP 1  Check the merged station observations already saved
        (merged_altimetry_stations.csv): stations, observation count, last date.
STEP 2  Download observations from the DAHITI and Hydroweb.next APIs
        - DAHITI: DAHITI_SEED_FILE is merged into dahiti_water_levels_raw.xlsx, then
          every station's FULL series is downloaded from the API and compared with
          the seed file (report -> dahiti_seed_check.csv). Anything the seed file is
          missing is added from the API.
        - Hydroweb: rivers + lakes zips for the bbox (py_hydroweb)
          -> HYDROWEB_RIVERS_OPE.zip / HYDROWEB_LAKES_OPE.zip -> hydroweb_water_levels_raw.xlsx
        Everything is capped at END_DATE (today's date, set when the run starts).
STEP 3  Merge, keep only observations not merged yet, and for those:
          * minimum / maximum / average as of each pass, ANCHORED TO station_lookup.xlsx
            where the station is listed (lower min, higher max, count-weighted average),
            deviation from average, difference from previous
          * SEASONAL BASELINE: each pass vs the same station's passes within
            +/- SEASON_HALF_WINDOW days of the same day of year in other years of
            REF_YEARS (leave-one-year-out) -> median, MAD, percentile, robust z,
            level_class; classes need MIN_BASE_YEARS years and MIN_BASE_OBS passes
          * QC FLAGS: jump (robust rate-of-change test), neighbour confirmation
            (upstream / downstream stations within +/- NEIGHBOUR_WINDOW_DAYS),
            long gap, high uncertainty -> qc_status. No interpolation of levels.
          * 15-day antecedent CHIRPS rainfall + ERA5-Land soil moisture,
            evapotranspiration, 2 m temperature, runoff (GEE, local buffer), gap-filled:
              rainfall : CHIRPS -> ERA5-Land precipitation -> CHIRPS day-of-year climatology
              ERA5-Land: ERA5-Land -> ERA5-Land day-of-year climatology
          * rows already in the merged file with blank climate are back-filled;
            derived columns (min / max / average, seasonal baseline, QC) are added or
            refreshed in saved rows
          * SRTM elevation (new stations only), up/downstream links,
            Lag Days over the last 12 observations
        -> merged_altimetry_stations.csv / .xlsx
STEP 4  Upload to GEE - ONLY THE NEW OBSERVATIONS leave Colab:
          * new rows are exported as small temporary parts, merged INSIDE Earth Engine
            with the current merged_observations table, and the result is renamed
            to projects/<PROJECT_ID>/assets/altimetry/merged_observations
          * the previous table is kept as merged_observations_old (one run back)
          * stations layer + upstream catchment of every station (HydroBASINS)
            -> station_catchments
        If saved rows were changed (back-fill / new columns) the asset is rebuilt.

Run in Google Colab. API keys come ONLY from Colab secrets (key icon, left panel)
named DAHITI_API_KEY and HYDROWEB_API_KEY, or from environment variables of the same names.
Station IDs are written as "source:id" (station_uid and the link columns, e.g.
"dahiti:213", "hydroweb:12345") because DAHITI and Hydroweb IDs can collide.
"""

import os
import re
import sys
import math
import glob
import time
import shutil
import zipfile
import datetime
import subprocess
from io import StringIO

import numpy as np
import pandas as pd
import requests
import ee

# =========================================================================== #
# 1. CONFIGURATION                                                            #
# =========================================================================== #
PROJECT_ID = 'sudan-1575919084043'

OUT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', '/content/drive/MyDrive/colab_waterlevel/')
WORK_DIR = os.environ.get('ALTIMETRY_WORK_DIR', '/content/hydroweb_extract')
OUTPUT_BASENAME = 'merged_altimetry_stations'

# --- Last observation date kept (both sources): today's date, taken at run time ---
END_DATE = datetime.date.today().strftime('%Y-%m-%d')

# --- Download switches: set False to reuse what is already on Drive ---------
DOWNLOAD_DAHITI = True
DOWNLOAD_HYDROWEB = True
VERIFY_SEED_WITH_API = True

# --- Raw downloads (kept on Drive, updated each run) ------------------------
DAHITI_RAW_XLSX = os.path.join(OUT_DIR, 'dahiti_water_levels_raw.xlsx')
DAHITI_SEED_FILE = os.path.join(OUT_DIR, 'dahiti_water_levels_raw.xlsx')
#DAHITI_SEED_FILE = os.path.join(OUT_DIR, 'combined_water_levels_analyzed_20260929_085307.xlsx')
SEED_CHECK_CSV = os.path.join(OUT_DIR, 'dahiti_seed_check.csv')
DAHITI_PAUSE_S = 3
DAHITI_MAX_RETRIES = 4
DAHITI_MAX_WAIT_S = 120
DAHITI_STOP_AFTER_429 = 3
RIVERS_ZIP = os.path.join(OUT_DIR, 'Theia_Hydroweb_Operational_Rivers.zip')
LAKES_ZIP = os.path.join(OUT_DIR, 'HYDROWEB_LAKES_OPE.zip')
HYDROWEB_RAW_XLSX = os.path.join(OUT_DIR, 'hydroweb_water_levels_raw.xlsx')

# --- Station lookup: long-term min / max / average water level per station ---
# Recognised ID columns : station_uid ("dahiti:213"), or source + station_id, or DAHITI-ID.
# Recognised value cols : minimum/min, maximum/max, average/mean, optional n_obs/count.
# Stations not in the lookup keep plain running values. Leave the file out to disable.
STATION_LOOKUP_XLSX = os.path.join(OUT_DIR, 'station_lookup.xlsx')

# --- GEE caches so reruns only fetch what is new ----------------------------
CLIMATE_CACHE = os.path.join(OUT_DIR, 'cache_climate_15d_v2.csv')
ELEV_CACHE = os.path.join(OUT_DIR, 'cache_elevation.csv')
CATCHMENT_CACHE = os.path.join(OUT_DIR, 'cache_station_catchments.csv')

START_YEAR = 2016
WINDOW_DAYS = 15
BUFFER_M = {'river': 5000, 'lake': 20000}
ELEV_BUFFER_M = 1000
RETRY_RECENT_DAYS = 60
CLIMATE_RETRY_DAYS = 7
CLIM_REF_YEARS = (2016, 2025)

UPDATE_MASTER_CLIMATE = True
REFRESH_GAPFILLED_DAYS = 60

HYDROWEB_BBOX = [25.9, -3.8, 36.4, 15.9]

# --- Seasonal baseline for level classification -------------------------------
REF_YEARS = (2016, 2025)      # fixed reference period
SEASON_HALF_WINDOW = 30       # +/- days around the same day of year
MIN_BASE_YEARS = 2            # minimum distinct baseline years for a class
MIN_BASE_OBS = 6             # minimum baseline passes for a class
PCT_CLASSES = [(90, 'Unusually high'), (67, 'Above normal'), (33, 'Near normal'),
               (10, 'Below normal'), (-1, 'Unusually low')]

# --- Quality flags between passes ---------------------------------------------
JUMP_MAD_K = 5.0              # rate of change more than K robust SDs from the station's own rates
JUMP_MIN_M = 0.5              # ...and at least this change (m)
HIGH_UNC_M = 0.5              # uncertainty above this (m) is flagged
NEIGHBOUR_WINDOW_DAYS = 10    # a jump is confirmed if an up/downstream station moves the same way
NEIGHBOUR_MIN_M = 0.25        # ...by at least this much within +/- this many days

# Onset-lag settings
MAX_LAG_DAYS = 60
MAX_GAP_DAYS = 45             # no interpolation across longer gaps; also the gap flag threshold
LAG_WINDOW_OBS = 12
LAG_MIN_OVERLAP_DAYS = 60
MIN_R = 0.3

MANUAL_LINKS = []

# --- Upstream catchments ------------------------------------------------------
BUILD_CATCHMENTS = True
HYBAS_LEVEL = 6
CATCHMENT_BBOX = [13.0, -3.0, 36.0, 23.5]   # Nile basin; catchments are cut at this box

# --- STAGE 4: upload results to Earth Engine assets --------------------------
UPLOAD_TO_GEE = True
ASSET_FOLDER = f'projects/{PROJECT_ID}/assets/altimetry'
ROWS_PER_PART = 3000

MASTER_CSV = os.path.join(OUT_DIR, f'{OUTPUT_BASENAME}.csv')
MASTER_XLSX = os.path.join(OUT_DIR, f'{OUTPUT_BASENAME}.xlsx')
GEE_LEDGER = os.path.join(OUT_DIR, 'gee_uploaded_keys.csv')
REBUILD_OUTPUTS = False

# Derived columns whose changes in ALREADY SAVED rows do not trigger a rewrite of the master
# files or a full GEE rebuild. neighbour_confirmed can change later when a neighbouring
# station gets a new pass; qc_status text is built from it.
REBUILD_IGNORE_COLS = {'neighbour_confirmed', 'qc_status'}

# False = small changes to derived values of already saved rows never trigger a rewrite or a
# full GEE rebuild (only a NEW column or a climate back-fill does). Old rows keep their saved values.
REBUILD_ON_DERIVED_CHANGES = False


# --- API keys: Colab secrets or environment variables only (never in the file) ---
def _secret(name):
    try:
        from google.colab import userdata
        value = userdata.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(name, '')


HYDROWEB_API_KEY = (_secret('HYDROWEB_API_KEY') or '').strip()
DAHITI_API_KEY = (_secret('DAHITI_API_KEY') or '').strip()

URL_LIST = 'https://dahiti.dgfi.tum.de/api/v2/list-targets/'
URL_DOWNLOAD = 'https://dahiti.dgfi.tum.de/api/v2/download-water-level/'
DAHITI_LIST_ARGS = {'api_key': DAHITI_API_KEY, 'min_lon': 23.2, 'max_lon': 36.1,
                    'min_lat': -1.8, 'max_lat': 12.8}

DAHITI_IDS = [
    85, 213, 2686, 2687, 2688, 3246, 3247, 3764, 5959,
    8313, 11635, 11683, 11750, 11815, 11900, 15192, 15710, 16098,
    16099, 16985, 18043, 18741, 18743, 19747, 19749, 23333, 23334,
    23336, 23337, 23338, 23341, 23353, 23354, 23357, 23358, 23359, 34869, 38468,
    39376, 12258, 17741, 16686, 16323, 14196, 10179, 2, 2264, 11761, 12138, 12178,
    15556, 15557, 16846, 17743, 17749, 17750, 17752, 17753, 17754,
    38453, 38456, 967, 23344, 23343, 23342, 19752, 19751,
]

DAHITI_ORDER = """id\tafter\n2\t38471\n38471\t16846\n16846\t38456\n38456\t2264\n2264\t38454\n38454\t38455\n38455\t38453\n38453\t213\n213\t16099\n16099\t15192\n15192\t16098\n85\t16098\n16098\t967\n967\t15556\n15556\t11761\n11761\t17753\n17753\t17754\n17754\t3246\n3246\t17752\n3247\t17752\n17752\t17750\n17750\t17749\n17749\t15557\n2686\t39376\n39376\t2687\n23344\t23343\n23343\t19749\n19749\t23342\n23342\t23341\n23341\t23338\n18741\t23338\n2687\t2688\n2688\t23338\n23338\t23337\n23337\t23336\n23336\t15557\n15557\t17743\n19752\t17743\n12138\t19752\n17743\t19751\n19751\t12178\n12178\t10179\n10179\t14196\n14196\t16323\n16323\t16686\n16686\t17741\n17741\t12258\n23359\t23358\n23358\t23357\n23357\t18743\n18743\t18043\n18043\t11815\n11815\t10179\n23354\t23353\n23353\t3764\n3764\t19747\n19747\t23359\n11683\t19747\n23333\t11683\n23334\t23333\n11635\t23334\n11750\t11635"""

RAW_COLS = ['source', 'station_id', 'type', 'location', 'latitude', 'longitude',
            'river_key', 'date_dt', 'wse', 'uncertainty']
DAHITI_RAW_COLS = ['DAHITI-ID', 'Target Name', 'Target Type', 'Longitude', 'Latitude',
                   'date [yyyy-mm-dd]', 'water level', 'wse_u']
DDATE = 'date [yyyy-mm-dd]'

CLIMATE_COLS_OUT = ['last_15_days_Rainfall_mm', 'last_15_days_Soil_Moisture',
                    'last_15_days_Evapotranspiration', 'last_15_days_Temp_C', 'last_15_days_runoff']
GAPFILL_COLS = ['rain_days_gapfilled', 'era5_days_gapfilled']
LEVEL_STAT_COLS = ['minimium', 'maxmium', 'average', 'deviation from average']
SEASONAL_COLS = ['seasonal_median_m', 'seasonal_mad_m', 'seasonal_pctile', 'seasonal_z',
                 'base_n_obs', 'base_n_years', 'level_class']
QC_COLS = ['days_since_prev', 'rate_m_per_day', 'jump_flag', 'neighbour_confirmed',
           'gap_flag', 'high_uncertainty_flag', 'qc_status']
DERIVED_COLS = LEVEL_STAT_COLS + SEASONAL_COLS + QC_COLS
TEXT_COLS = {'level_class', 'qc_status'}

# =========================================================================== #
# 2. SETUP                                                                    #
# =========================================================================== #
try:
    from google.colab import drive
    if not os.path.exists('/content/drive/MyDrive'):
        drive.mount('/content/drive')
except Exception:
    pass
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(WORK_DIR, exist_ok=True)

import json as _json
_SA_KEY = os.environ.get('GEE_SERVICE_ACCOUNT_KEY', '').strip()
if _SA_KEY:
    _key_text = _SA_KEY if _SA_KEY.startswith('{') else open(_SA_KEY, encoding='utf-8').read()
    ee.Initialize(ee.ServiceAccountCredentials(_json.loads(_key_text)['client_email'], key_data=_key_text),
                  project=PROJECT_ID)
else:
    try:
        ee.Initialize(project=PROJECT_ID)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=PROJECT_ID)

RUN_STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
TODAY = pd.Timestamp.today().normalize()
END_TS = (pd.Timestamp(END_DATE) if END_DATE else TODAY).normalize()
END_EXCL = END_TS + pd.Timedelta(days=1)
print(f"Observations kept up to and including {END_TS:%Y-%m-%d}")


def parse_dt(date_s, time_s):
    """Hydroweb date + time -> datetime, ISO format first, then a slower fallback for odd rows."""
    txt = (date_s.astype(str) + ' ' + time_s.fillna('').astype(str)).str.strip()
    out = pd.to_datetime(txt, format='ISO8601', errors='coerce')
    bad = out.isna() & txt.ne('')
    if bad.any():
        out[bad] = pd.to_datetime(txt[bad], format='mixed', errors='coerce')
    return out


def empty_raw():
    return pd.DataFrame(columns=RAW_COLS)


# =========================================================================== #
# DOWNLOAD FUNCTIONS - DAHITI                                                 #
# =========================================================================== #
def dahiti_type(name, raw_type=''):
    text = (str(raw_type or '') + ' ' + str(name or '')).lower()
    return 'lake' if any(k in text for k in ('lake', 'reservoir', 'wetland', 'swamp')) else 'river'


def clean_dahiti(frames):
    """Combine DAHITI frames, one row per station per day (later frames win), capped at END_DATE."""
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return pd.DataFrame(columns=DAHITI_RAW_COLS)
    d = pd.concat([f.reindex(columns=DAHITI_RAW_COLS) for f in frames], ignore_index=True)
    d[DDATE] = pd.to_datetime(d[DDATE], errors='coerce')
    d['water level'] = pd.to_numeric(d['water level'], errors='coerce')
    d['DAHITI-ID'] = pd.to_numeric(d['DAHITI-ID'], errors='coerce')
    d = d.dropna(subset=['DAHITI-ID', DDATE, 'water level'])
    d['DAHITI-ID'] = d['DAHITI-ID'].astype(int)
    d = d[d['DAHITI-ID'].isin(DAHITI_IDS) & (d[DDATE] < END_EXCL)].copy()
    d['_day'] = d[DDATE].dt.normalize()
    d = (d.drop_duplicates(['DAHITI-ID', '_day'], keep='last')
          .sort_values(['DAHITI-ID', DDATE]).drop(columns='_day').reset_index(drop=True))
    return d[DAHITI_RAW_COLS]


def load_seed():
    """Read DAHITI_SEED_FILE (or the newest combined_water_levels_analyzed*.xlsx). Read only."""
    path = None
    if DAHITI_SEED_FILE and os.path.exists(DAHITI_SEED_FILE):
        path = DAHITI_SEED_FILE
    else:
        if DAHITI_SEED_FILE:
            print(f"DAHITI_SEED_FILE not found ({DAHITI_SEED_FILE}); looking for the newest old file instead.")
        old = sorted(glob.glob(os.path.join(OUT_DIR, 'combined_water_levels_analyzed*.xlsx')),
                     key=os.path.getmtime)
        path = old[-1] if old else None
    if path is None:
        print("No seed file found.")
        return pd.DataFrame(columns=DAHITI_RAW_COLS)
    try:
        d = pd.read_excel(path)
    except Exception as e:
        print(f"Could not read {os.path.basename(path)}: {e}")
        return pd.DataFrame(columns=DAHITI_RAW_COLS)
    d = d.rename(columns={'datetime': DDATE, 'date': DDATE, 'date_time': DDATE, 'wse': 'water level'})
    d = d.loc[:, ~d.columns.duplicated()]
    need = ['DAHITI-ID', 'Target Name', 'Longitude', 'Latitude', DDATE, 'water level']
    if not all(c in d.columns for c in need):
        print(f"{os.path.basename(path)} is missing expected columns "
              f"({[c for c in need if c not in d.columns]}); not used.")
        return pd.DataFrame(columns=DAHITI_RAW_COLS)
    if 'wse_u' not in d:
        d['wse_u'] = np.nan
    d['Target Type'] = d['Target Name'].map(dahiti_type)
    d = clean_dahiti([d])
    print(f"Seed file {os.path.basename(path)}: {len(d)} rows for "
          f"{d['DAHITI-ID'].nunique()} stations, last date "
          f"{d[DDATE].max():%Y-%m-%d}" if len(d) else f"Seed file {os.path.basename(path)}: no usable rows")
    return d


def dahiti_post(url, payload, timeout=60):
    """POST to the DAHITI API, backing off on HTTP 429 / 5xx / network errors."""
    wait = 15
    status = 'no response'
    for attempt in range(DAHITI_MAX_RETRIES + 1):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
        except Exception as e:
            status = f'request failed: {e}'
        else:
            if r.status_code == 200:
                return r, 'ok'
            status = f'HTTP {r.status_code}'
            if r.status_code not in (429, 500, 502, 503, 504):
                return r, status
            ra = r.headers.get('Retry-After', '')
            if ra.strip().isdigit():
                wait = int(ra.strip())
        if attempt == DAHITI_MAX_RETRIES:
            break
        w = min(wait, DAHITI_MAX_WAIT_S)
        print(f"    {status}, waiting {w} s (retry {attempt + 1}/{DAHITI_MAX_RETRIES})")
        time.sleep(w)
        wait = min(wait * 2, DAHITI_MAX_WAIT_S)
    return None, status


REPORT_COLS = ['DAHITI-ID', 'Target Name', 'seed_obs', 'seed_last', 'api_obs', 'api_last',
               'missing_in_seed', 'first_missing', 'only_in_seed', 'max_abs_wse_diff_m',
               'check', 'checked_on', 'this_run']


def download_dahiti():
    global DAHITI_RAW_XLSX
    print("\n--- DAHITI ---")
    if DAHITI_SEED_FILE and os.path.abspath(DAHITI_RAW_XLSX) == os.path.abspath(DAHITI_SEED_FILE):
        DAHITI_RAW_XLSX = os.path.join(OUT_DIR, 'dahiti_water_levels_raw.xlsx')
        print("DAHITI_RAW_XLSX pointed at the seed file; saving raw data to "
              f"{os.path.basename(DAHITI_RAW_XLSX)} instead so the seed file isn't overwritten.")

    saved = pd.DataFrame(columns=DAHITI_RAW_COLS)
    if os.path.exists(DAHITI_RAW_XLSX):
        saved = clean_dahiti([pd.read_excel(DAHITI_RAW_XLSX)])
        print(f"Raw file {os.path.basename(DAHITI_RAW_XLSX)}: {len(saved)} rows for "
              f"{saved['DAHITI-ID'].nunique()} stations")

    seed = load_seed()
    base = clean_dahiti([seed, saved])
    print(f"Raw file after merging the seed file: {len(base)} rows "
          f"(+{len(base) - len(saved)} from the seed file)")
    if len(base):
        base.to_excel(DAHITI_RAW_XLSX, index=False)

    if not DOWNLOAD_DAHITI:
        print("DOWNLOAD_DAHITI = False -> using saved data only (seed file NOT checked against the API).")
        return base
    if not DAHITI_API_KEY:
        print("No DAHITI_API_KEY secret found -> using saved data only (seed file NOT checked against the API).")
        return base

    meta = {}
    for sid, grp in base.groupby('DAHITI-ID'):
        last = grp.iloc[-1]
        meta[int(sid)] = {
            'name': last['Target Name'],
            'type': last.get('Target Type') or dahiti_type(last['Target Name']),
            'lon': float(last['Longitude']), 'lat': float(last['Latitude'])}
    no_meta = [sid for sid in DAHITI_IDS if sid not in meta]
    if no_meta:
        r, st = dahiti_post(URL_LIST, DAHITI_LIST_ARGS, timeout=120)
        if r is not None and r.status_code == 403:
            print("DAHITI rejected the API key (HTTP 403). Server said: "
                  f"{r.text.strip()[:300]}\n"
                  "-> Check the key (no spaces/quotes) or get a new one from your DAHITI account. "
                  "Continuing with saved data only.")
            return base
        if st == 'ok':
            try:
                for t in r.json().get('data', []):
                    if t.get('dahiti_id') in no_meta:
                        meta[t['dahiti_id']] = {
                            'name': t.get('target_name'),
                            'type': dahiti_type(t.get('target_name'), t.get('type') or t.get('target_type')),
                            'lon': float(t['longitude']), 'lat': float(t['latitude'])}
            except Exception as e:
                print(f"list-targets reply could not be read ({e}).")
        else:
            print(f"list-targets failed ({st}).")
        print(f"Metadata: {len(meta)}/{len(DAHITI_IDS)} stations "
              f"({len(no_meta)} needed from the API)")
    else:
        print(f"Metadata for all {len(DAHITI_IDS)} stations already saved - list-targets not needed.")
    time.sleep(DAHITI_PAUSE_S)

    last_by_id = base.groupby('DAHITI-ID')[DDATE].max().to_dict() if len(base) else {}
    for sid in DAHITI_IDS:
        merged_last = MASTER_LAST.get(f'dahiti:{sid}')
        if merged_last is not None and (sid not in last_by_id or pd.isna(last_by_id[sid])
                                        or merged_last > last_by_id[sid]):
            last_by_id[sid] = merged_last

    seed_series = {int(sid): g.groupby(g[DDATE].dt.normalize())['water level'].mean()
                   for sid, g in seed.groupby('DAHITI-ID')} if len(seed) else {}

    prev = {}
    if os.path.exists(SEED_CHECK_CSV):
        try:
            pr = pd.read_csv(SEED_CHECK_CSV)
            if 'check' in pr:
                for rec in pr.to_dict('records'):
                    if isinstance(rec.get('check'), str) and not rec['check'].startswith('not checked'):
                        prev[int(rec['DAHITI-ID'])] = rec
        except Exception as e:
            print(f"Previous check report unreadable ({e}); checking all stations again.")
    to_check = [sid for sid in DAHITI_IDS if VERIFY_SEED_WITH_API and sid not in prev]
    print(f"Seed check: {len(DAHITI_IDS) - len(to_check)} stations checked on earlier runs, "
          f"{len(to_check)} to check now (full series); the rest fetch new dates only.")

    today = pd.Timestamp.today().strftime('%Y-%m-%d')
    frames, report = [], []
    streak_429, stopped = 0, False
    for sid in DAHITI_IDS:
        s = seed_series.get(sid, pd.Series(dtype=float))
        full = sid in to_check
        rep = dict(prev.get(sid, {}))
        rep.update({'DAHITI-ID': sid, 'Target Name': (meta.get(sid) or {}).get('name'),
                    'seed_obs': len(s),
                    'seed_last': s.index.max().strftime('%Y-%m-%d') if len(s) else None})
        m = meta.get(sid)
        if m is None:
            rep.update({'check': 'not checked: no metadata', 'this_run': 'skipped'})
            report.append(rep)
            print(f"  {sid}: no metadata, skipped")
            continue
        if stopped:
            rep.setdefault('check', 'not checked: rate limited')
            rep['this_run'] = 'skipped (rate limited)'
            report.append(rep)
            continue

        args = {'api_key': DAHITI_API_KEY, 'dahiti_id': sid, 'format': 'csv'}
        last = last_by_id.get(sid)
        if not full and last is not None and pd.notna(last):
            args['start_date'] = (last + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        r, st = dahiti_post(URL_DOWNLOAD, args)
        time.sleep(DAHITI_PAUSE_S)
        if st != 'ok':
            streak_429 = streak_429 + 1 if st == 'HTTP 429' else 0
            if full:
                rep['check'] = f'not checked: {st}'
            rep['this_run'] = st
            report.append(rep)
            print(f"  {sid}: {st}")
            if streak_429 >= DAHITI_STOP_AFTER_429:
                stopped = True
                print(f"  DAHITI kept answering HTTP 429 for {streak_429} stations in a row -> "
                      "stopping API requests for this run. Saved data are used; wait a while "
                      "(an hour or more) and rerun to check the remaining stations.")
            continue
        streak_429 = 0
        try:
            d = pd.read_csv(StringIO(r.text), sep=';')
        except Exception:
            d = pd.DataFrame()
        if d.empty or 'datetime' not in d:
            api = pd.DataFrame(columns=DAHITI_RAW_COLS)
        else:
            api = pd.DataFrame({
                'DAHITI-ID': sid, 'Target Name': m['name'], 'Target Type': m['type'],
                'Longitude': m['lon'], 'Latitude': m['lat'],
                DDATE: pd.to_datetime(d['datetime'], errors='coerce'),
                'water level': pd.to_numeric(d['wse'], errors='coerce'),
                'wse_u': pd.to_numeric(d['wse_u'], errors='coerce') if 'wse_u' in d else np.nan,
            })
            api = clean_dahiti([api])
        frames.append(api)

        if full:
            a = (api.groupby(api[DDATE].dt.normalize())['water level'].mean()
                 if len(api) else pd.Series(dtype=float))
            missing = a.index.difference(s.index)
            common = a.index.intersection(s.index)
            rep.update({
                'api_obs': len(a),
                'api_last': a.index.max().strftime('%Y-%m-%d') if len(a) else None,
                'missing_in_seed': len(missing),
                'first_missing': missing.min().strftime('%Y-%m-%d') if len(missing) else None,
                'only_in_seed': len(s.index.difference(a.index)),
                'max_abs_wse_diff_m': float((a[common] - s[common]).abs().max()) if len(common) else np.nan,
                'checked_on': today,
            })
            if not len(a):
                rep['check'] = 'API returned no data'
            elif not len(s):
                rep['check'] = 'not in seed file - all dates added from API'
            elif len(missing):
                rep['check'] = f'{len(missing)} dates missing in seed - added from API'
            else:
                rep['check'] = 'complete'
            rep['this_run'] = 'full series checked'
            print(f"  {sid}: API {len(a)} obs to {rep['api_last']}, seed {len(s)} -> {rep['check']}")
        else:
            rep['this_run'] = f'+{len(api)} new rows'
            if len(api):
                rep['api_last'] = max(str(rep.get('api_last') or ''), api[DDATE].max().strftime('%Y-%m-%d'))
            print(f"  {sid}: +{len(api)} rows")
        report.append(rep)

    out = clean_dahiti([base] + frames)
    if len(out):
        out.to_excel(DAHITI_RAW_XLSX, index=False)
    print(f"DAHITI saved: {out['DAHITI-ID'].nunique()} stations, {len(out)} rows "
          f"(+{len(out) - len(base)} vs seed/raw), last date {out[DDATE].max():%Y-%m-%d} "
          f"-> {DAHITI_RAW_XLSX}")

    rep = pd.DataFrame(report).reindex(columns=REPORT_COLS)
    rep.to_csv(SEED_CHECK_CSV, index=False)
    if VERIFY_SEED_WITH_API and len(rep):
        chk = rep['check'].fillna('not checked')
        n_done = int((~chk.str.startswith('not checked')).sum())
        n_ok = int((chk == 'complete').sum())
        print(f"\nSeed file check: {n_done}/{len(rep)} stations checked "
              f"({n_ok} complete, {n_done - n_ok} with dates added or no API data), "
              f"{len(rep) - n_done} not checked yet -> {SEED_CHECK_CSV}")
        show = rep[(chk != 'complete') & ~chk.str.startswith('not checked')]
        if len(show):
            print(show[['DAHITI-ID', 'seed_obs', 'api_obs', 'seed_last', 'api_last', 'check']]
                  .to_string(index=False))
        if n_done < len(rep):
            print("Rerun later to check the remaining stations; checked ones are not downloaded in full again.")
    return out


def dahiti_to_raw(d):
    if d.empty:
        return empty_raw()
    types = d['Target Type'] if 'Target Type' in d else pd.Series(np.nan, index=d.index)
    types = types.fillna(d['Target Name'].map(dahiti_type))
    return pd.DataFrame({
        'source': 'DAHITI', 'station_id': d['DAHITI-ID'].astype(int), 'type': types,
        'location': d['Target Name'], 'latitude': d['Latitude'].astype(float),
        'longitude': d['Longitude'].astype(float), 'river_key': None,
        'date_dt': pd.to_datetime(d[DDATE], errors='coerce'),
        'wse': pd.to_numeric(d['water level'], errors='coerce'),
        'uncertainty': pd.to_numeric(d['wse_u'], errors='coerce'),
    })


# =========================================================================== #
# DOWNLOAD FUNCTIONS - HYDROWEB.NEXT (rivers + lakes)                         #
# =========================================================================== #
def download_hydroweb():
    print("\n--- Hydroweb.next (rivers + lakes) ---")
    if not DOWNLOAD_HYDROWEB:
        print("DOWNLOAD_HYDROWEB = False -> using the zips already on Drive.")
        return
    if not HYDROWEB_API_KEY:
        print("No HYDROWEB_API_KEY secret found -> using the zips already on Drive.")
        return
    try:
        import py_hydroweb
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'py-hydroweb'], check=False)
        import py_hydroweb

    client = py_hydroweb.Client(api_key=HYDROWEB_API_KEY)
    dl_dir = os.path.join(WORK_DIR, 'hydroweb_download')
    os.makedirs(dl_dir, exist_ok=True)
    old_cwd = os.getcwd()
    for collection, target in [('HYDROWEB_RIVERS_OPE', RIVERS_ZIP), ('HYDROWEB_LAKES_OPE', LAKES_ZIP)]:
        print(f"Requesting {collection} for bbox {HYDROWEB_BBOX} ...")
        local_zip = os.path.join(dl_dir, f"{collection}_{RUN_STAMP}.zip")
        try:
            os.chdir(dl_dir)
            basket = py_hydroweb.DownloadBasket(f"{collection.lower()}_{RUN_STAMP}")
            basket.add_collection(collection, bbox=HYDROWEB_BBOX)
            path = client.submit_and_download_zip(basket, zip_filename=local_zip, output_folder=dl_dir)
            if path is None:
                print("  Hydroweb could not prepare this download (see message above); "
                      "keeping previous zip if present.")
                continue
            path = path if os.path.isabs(path) else os.path.join(dl_dir, path)
            if not os.path.exists(path):
                path = local_zip
            shutil.copy(path, target)
            print(f"  saved -> {target} ({os.path.getsize(target) / 1e6:.1f} MB)")
        except Exception as e:
            print(f"  {collection} download failed ({e}); keeping previous zip if present.")
        finally:
            os.chdir(old_cwd)


RIVER_COLS = [
    'date', 'time', 'water_surface_elevation', 'uncertainty', 'sep',
    'lon', 'lat', 'ellipsoidal_height', 'geoid_ondulation', 'distance_km',
    'satellite', 'mission', 'ground_track', 'cycle', 'retracking', 'gdr_version',
]


def extract(zip_path, sub):
    out = os.path.join(WORK_DIR, sub)
    if not os.path.exists(zip_path):
        print(f"  {os.path.basename(zip_path)} not found, skipping {sub}")
        return []
    shutil.rmtree(out, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
    files = sorted(glob.glob(os.path.join(out, '**', '*.txt'), recursive=True))
    print(f"  {sub}: {len(files)} station files")
    return files


def load_hydroweb_rivers():
    frames = []
    for path in extract(RIVERS_ZIP, 'rivers'):
        m = {}
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                if not line.startswith('#'):
                    break
                if '::' in line:
                    k, v = line[1:].split('::', 1)
                    m[k.strip()] = v.strip()
        if 'ID' not in m:
            continue
        d = pd.read_csv(path, comment='#', sep=r'\s+', header=None,
                        names=RIVER_COLS, dtype={'date': str, 'time': str})
        river = (m.get('RIVER') or '').replace('-', ' ').title()
        km = m.get('REFERENCE DISTANCE (km)')
        frames.append(pd.DataFrame({
            'source': 'Hydroweb', 'station_id': int(m['ID']), 'type': 'river',
            'location': f"{river} km {km}" if km else river,
            'latitude': float(m['REFERENCE LATITUDE']),
            'longitude': float(m['REFERENCE LONGITUDE']),
            'river_key': f"{m.get('BASIN', '')}|{m.get('RIVER', '')}".upper().replace('-', ' '),
            'date_dt': parse_dt(d['date'], d['time']),
            'wse': pd.to_numeric(d['water_surface_elevation'], errors='coerce'),
            'uncertainty': pd.to_numeric(d['uncertainty'], errors='coerce'),
        }))
    return pd.concat(frames, ignore_index=True) if frames else empty_raw()


def load_hydroweb_lakes():
    frames = []
    for path in extract(LAKES_ZIP, 'lakes'):
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        if not lines:
            continue
        h = {}
        for part in lines[0].strip().split(';'):
            if '=' in part:
                k, v = part.split('=', 1)
                h[k.strip()] = v.strip()
        if 'id' not in h:
            continue
        recs = []
        for l in lines[1:]:
            if not l.strip() or l.strip().startswith('#'):
                continue
            parts = [p.strip() for p in l.split(';')]
            if len(parts) >= 7:
                recs.append((parts + [''])[:8])
        if not recs:
            continue
        d = pd.DataFrame(recs, columns=['decimal_year', 'date', 'time', 'height_m',
                                        'stdev_m', 'area_km2', 'volume_km3', 'mission'])
        d['date'] = d['date'].str.replace('/', '-')
        name = h.get('lake', '').replace('-', ' ').title()
        frames.append(pd.DataFrame({
            'source': 'Hydroweb', 'station_id': int(h['id']), 'type': 'lake',
            'location': f"{name} Lake",
            'latitude': float(h.get('lat', 'nan')), 'longitude': float(h.get('lon', 'nan')),
            'river_key': None,
            'date_dt': parse_dt(d['date'], d['time']),
            'wse': pd.to_numeric(d['height_m'], errors='coerce'),
            'uncertainty': pd.to_numeric(d['stdev_m'], errors='coerce'),
        }))
    return pd.concat(frames, ignore_index=True) if frames else empty_raw()


def load_hydroweb():
    rivers, lakes = load_hydroweb_rivers(), load_hydroweb_lakes()
    hw = pd.concat([rivers, lakes], ignore_index=True)
    if hw.empty:
        print("Hydroweb: no data.")
        return hw
    mn_lon, mn_lat, mx_lon, mx_lat = HYDROWEB_BBOX
    hw = hw[hw.longitude.between(mn_lon, mx_lon) & hw.latitude.between(mn_lat, mx_lat)
            & (hw.date_dt < END_EXCL)]

    with pd.ExcelWriter(HYDROWEB_RAW_XLSX, engine='openpyxl') as xw:
        stations_hw = (hw.groupby(['type', 'station_id'])
                         .agg(location=('location', 'first'), latitude=('latitude', 'first'),
                              longitude=('longitude', 'first'), n_measurements=('wse', 'size'),
                              first_date=('date_dt', 'min'), last_date=('date_dt', 'max'))
                         .reset_index())
        stations_hw.to_excel(xw, sheet_name='Stations', index=False)
        for t, sheet in [('river', 'All_Rivers'), ('lake', 'All_Lakes')]:
            hw[hw.type == t].drop(columns=['river_key']).to_excel(xw, sheet_name=sheet, index=False)
    print(f"Hydroweb saved: {(hw.type == 'river').groupby(hw.station_id).any().sum()} river + "
          f"{(hw.type == 'lake').groupby(hw.station_id).any().sum()} lake stations, "
          f"{len(hw)} rows, last date {hw.date_dt.max():%Y-%m-%d} -> {HYDROWEB_RAW_XLSX}")
    return hw


# =========================================================================== #
# STATION LOOKUP (long-term min / max / average per station)                  #
# =========================================================================== #
def load_station_lookup(path):
    """Read the station lookup -> index station_uid, columns lookup_min / lookup_max / lookup_avg / lookup_n."""
    if not os.path.exists(path):
        print(f"No station lookup at {path}; running min / max / average only.")
        return None
    try:
        lk = pd.read_excel(path)
    except Exception as e:
        print(f"Station lookup could not be read ({type(e).__name__}: {e}); not used.")
        return None
    if lk.empty:
        print("Station lookup is empty; not used.")
        return None
    cols = {str(c).lower().strip(): c for c in lk.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    uid_col = pick('station_uid', 'uid')
    src_col = pick('source')
    dahiti_col = pick('dahiti-id', 'dahiti_id', 'dahiti id')
    sid_col = pick('station_id', 'station id', 'id')
    if uid_col:
        uid = lk[uid_col].astype(str).str.strip().str.lower()
    elif src_col and (sid_col or dahiti_col):
        sid = pd.to_numeric(lk[sid_col or dahiti_col], errors='coerce')
        uid = lk[src_col].astype(str).str.strip().str.lower() + ':' + sid.astype('Int64').astype(str)
    elif dahiti_col:
        uid = 'dahiti:' + pd.to_numeric(lk[dahiti_col], errors='coerce').astype('Int64').astype(str)
    else:
        print(f"Station lookup: no usable ID column in {list(lk.columns)} "
              "(need station_uid, source + station_id, or DAHITI-ID); not used.")
        return None

    fields = {
        'lookup_min': pick('minimum', 'minimium', 'min', 'min_wse', 'min_level', 'minimum_m'),
        'lookup_max': pick('maximum', 'maxmium', 'maximium', 'max', 'max_wse', 'max_level', 'maximum_m'),
        'lookup_avg': pick('average', 'mean', 'avg', 'mean_wse', 'average_m', 'mean_level'),
        'lookup_n': pick('n_obs', 'count', 'n', 'observations', 'n_observations'),
    }
    out = pd.DataFrame({'station_uid': uid})
    for name, col in fields.items():
        out[name] = pd.to_numeric(lk[col], errors='coerce') if col else np.nan
    out = out[out.station_uid.notna() & ~out.station_uid.str.endswith(':<na>')
              & ~out.station_uid.isin(['nan', 'none', ''])]
    out = out.drop_duplicates('station_uid', keep='last').set_index('station_uid')

    found = [f"{k} <- '{v}'" for k, v in fields.items() if v]
    print(f"Station lookup: {len(out)} stations; columns used: {', '.join(found) or 'none'}")
    if not any(fields[k] for k in ('lookup_min', 'lookup_max', 'lookup_avg')):
        print("  No min / max / average columns recognised; lookup not used.")
        return None
    bad = out[(out.lookup_min > out.lookup_max)]
    if len(bad):
        print(f"  WARNING: minimum > maximum for {len(bad)} stations: {', '.join(bad.index[:10])}")
    return out


# =========================================================================== #
# STEP 1 - CHECK MERGED STATION OBSERVATIONS                                  #
# =========================================================================== #
WSE_COL = 'Water Surface Elevation - values(m)'


def obs_key(frame):
    """One key per observation (output-table columns): source | station | date | level (mm)."""
    return (frame['source'].astype(str) + '|'
            + pd.to_numeric(frame['station_id']).astype(int).astype(str) + '|'
            + frame['date'].astype(str) + '|'
            + pd.to_numeric(frame[WSE_COL]).round(3).map('{:.3f}'.format))


print("\n=== STEP 1: CHECK MERGED STATION OBSERVATIONS ===")
if REBUILD_OUTPUTS:
    for p in (MASTER_CSV, MASTER_XLSX, GEE_LEDGER):
        if os.path.exists(p):
            os.remove(p)
    print("REBUILD_OUTPUTS = True -> master files and GEE ledger removed; rebuilding all rows.")

MASTER_LAST = {}
master_hist = None
if os.path.exists(MASTER_CSV):
    master_hist = pd.read_csv(MASTER_CSV, usecols=['source', 'station_id', 'type', 'location/river_name',
                                                   'latitude', 'longitude', 'date', WSE_COL,
                                                   'uncertainty (m)'])
    old_keys = set(obs_key(master_hist))
    master_hist['station_uid'] = (master_hist['source'].str.lower() + ':'
                                  + master_hist['station_id'].astype(int).astype(str))
    MASTER_LAST = pd.to_datetime(master_hist['date']).groupby(master_hist['station_uid']).max().to_dict()
    summary = master_hist.groupby('source').agg(stations=('station_uid', 'nunique'),
                                                observations=('date', 'size'),
                                                first_date=('date', 'min'), last_date=('date', 'max'))
    print(f"{os.path.basename(MASTER_CSV)}: {len(master_hist)} observations already merged")
    print(summary.to_string())
else:
    old_keys = set()
    print("No merged file yet -> every downloaded observation counts as new.")

# =========================================================================== #
# STEP 2 - DOWNLOAD OBSERVATIONS FROM THE DAHITI + HYDROWEB APIs               #
# =========================================================================== #
print("\n=== STEP 2: DOWNLOAD OBSERVATIONS (DAHITI + Hydroweb APIs) ===")
dahiti_raw = download_dahiti()
download_hydroweb()
hydroweb_raw = load_hydroweb()

# =========================================================================== #
# STEP 3 - MERGE, LOOKUP, BASELINE + QC, THEN GEE CLIMATE + ELEVATION          #
# =========================================================================== #
print("\n=== STEP 3: MERGE + LOOKUP + BASELINE + QC + GEE CLIMATE ===")
raw = pd.concat([dahiti_to_raw(dahiti_raw), hydroweb_raw], ignore_index=True)

if master_hist is not None and len(master_hist):
    hist = pd.DataFrame({
        'source': master_hist['source'], 'station_id': master_hist['station_id'].astype(int),
        'type': master_hist['type'], 'location': master_hist['location/river_name'],
        'latitude': master_hist['latitude'], 'longitude': master_hist['longitude'], 'river_key': None,
        'date_dt': pd.to_datetime(master_hist['date']), 'wse': master_hist[WSE_COL],
        'uncertainty': master_hist['uncertainty (m)']})
    raw = pd.concat([hist, raw], ignore_index=True)

raw['date_dt'] = pd.to_datetime(raw['date_dt'], errors='coerce')
for col in ['wse', 'uncertainty', 'latitude', 'longitude']:
    raw[col] = pd.to_numeric(raw[col], errors='coerce')
raw = raw.dropna(subset=['date_dt', 'wse', 'latitude', 'longitude'])
raw = raw[(raw.date_dt.dt.year >= START_YEAR) & (raw.date_dt < END_EXCL)].copy()
raw['station_id'] = raw['station_id'].astype(int)
raw['station_uid'] = raw['source'].str.lower() + ':' + raw['station_id'].astype(str)
raw['river_key'] = raw.groupby('station_uid')['river_key'].transform('first')
raw['_day'] = raw['date_dt'].dt.normalize()
raw = raw.drop_duplicates(['station_uid', '_day'], keep='first').drop(columns='_day')
df = raw.sort_values(['station_uid', 'date_dt']).reset_index(drop=True)

if df.empty:
    raise SystemExit("No data from either source - nothing to merge.")

df['day_dt'] = df['date_dt'].dt.normalize()
df['date_key'] = df['day_dt'].dt.strftime('%Y-%m-%d')
df['obs_key'] = obs_key(pd.DataFrame({'source': df['source'], 'station_id': df['station_id'],
                                      'date': df['date_key'], WSE_COL: df['wse']}))
is_new = ~df['obs_key'].isin(old_keys)
new_by_source = df.loc[is_new].groupby('source')['obs_key'].size().to_dict()
print(f"New observations not yet merged: {int(is_new.sum())} {new_by_source if new_by_source else ''}")
print(f"Latest observation date: {df['day_dt'].max():%Y-%m-%d} (cap {END_TS:%Y-%m-%d})")

# --- 3a. Station statistics, "as of" each observation (anchored to the lookup) ---
station_lookup = load_station_lookup(STATION_LOOKUP_XLSX)

g = df.groupby('station_uid')['wse']
run_min = g.cummin()
run_max = g.cummax()
run_n = df.groupby('station_uid').cumcount() + 1
run_sum = g.cumsum()
running_avg = run_sum / run_n

if station_lookup is not None:
    lk_min = df['station_uid'].map(station_lookup['lookup_min'])
    lk_max = df['station_uid'].map(station_lookup['lookup_max'])
    lk_avg = df['station_uid'].map(station_lookup['lookup_avg'])
    lk_n = df['station_uid'].map(station_lookup['lookup_n'])

    df['minimium'] = np.fmin(run_min, lk_min)          # NaN in the lookup -> running value kept
    df['maxmium'] = np.fmax(run_max, lk_max)

    blended = (lk_avg * lk_n + run_sum) / (lk_n + run_n)  # lookup average weighted by its count
    df['average'] = np.where(lk_avg.notna() & lk_n.gt(0), blended,
                             np.where(lk_avg.notna(), lk_avg, running_avg))

    matched = df['station_uid'].isin(station_lookup.index)
    print(f"  Lookup applied to {df.loc[matched, 'station_uid'].nunique()} of "
          f"{df['station_uid'].nunique()} stations")
    unmatched = sorted(set(station_lookup.index) - set(df['station_uid']))
    if unmatched:
        print(f"  Lookup stations with no observations: {', '.join(unmatched[:10])}"
              f"{' ...' if len(unmatched) > 10 else ''}")
else:
    df['minimium'] = run_min
    df['maxmium'] = run_max
    df['average'] = running_avg

df['deviation from average'] = df['wse'] - df['average']
df['difference from previous'] = g.diff().fillna(0.0)

stations = (df.groupby('station_uid')
              .agg(source=('source', 'first'), station_id=('station_id', 'first'),
                   type=('type', 'first'), location=('location', 'first'),
                   latitude=('latitude', 'first'), longitude=('longitude', 'first'),
                   river_key=('river_key', 'first'), mean_wse=('wse', 'mean'),
                   n_obs=('wse', 'size'), first_date=('date_key', 'min'),
                   last_date=('date_key', 'max'))
              .reset_index())
latest_stats = df.groupby('station_uid')[['minimium', 'maxmium', 'average']].last()
stations = stations.merge(latest_stats.rename(columns={'minimium': 'min_wse', 'maxmium': 'max_wse',
                                                       'average': 'average_wse'}),
                          left_on='station_uid', right_index=True, how='left')
stations['in_lookup'] = (stations.station_uid.isin(station_lookup.index).astype(int)
                         if station_lookup is not None else 0)
present = set(stations.station_uid)
print(f"Merged: {len(stations)} stations, {len(df)} observations")

# --- 3b. Upstream / downstream links -----------------------------------------
raw_links = {}
order = pd.read_csv(StringIO(DAHITI_ORDER), sep='\t').dropna()
for _, r in order.iterrows():
    raw_links[f"dahiti:{int(r['id'])}"] = f"dahiti:{int(r['after'])}"

hw_riv = stations[(stations.source == 'Hydroweb') & (stations.type == 'river')]
for _, grp in hw_riv.groupby('river_key'):
    uids = grp.sort_values('mean_wse', ascending=False).station_uid.tolist()
    for up, dn in zip(uids[:-1], uids[1:]):
        raw_links.setdefault(up, dn)

for up, dn in MANUAL_LINKS:
    raw_links[up] = dn


def resolve_down(uid):
    """Follow the chain past stations that have no data (e.g. 38471, 38454)."""
    seen, nxt = {uid}, raw_links.get(uid)
    while nxt is not None and nxt not in present and nxt not in seen:
        seen.add(nxt)
        nxt = raw_links.get(nxt)
    return nxt if nxt in present else None


after_map = {u: resolve_down(u) for u in present}
after_map = {u: d for u, d in after_map.items() if d is not None}
before_map = {}
for up, dn in after_map.items():
    before_map.setdefault(dn, []).append(up)

stations['Station After_this_station'] = stations.station_uid.map(after_map)
stations['Station Before_this_Station'] = stations.station_uid.map(
    lambda u: ', '.join(sorted(before_map[u])) if u in before_map else None)

# --- 3c. Seasonal baseline and level class ------------------------------------
print(f"Seasonal baseline: +/-{SEASON_HALF_WINDOW} days, reference {REF_YEARS[0]}-{REF_YEARS[1]}, "
      f"leave-one-year-out, min {MIN_BASE_YEARS} years / {MIN_BASE_OBS} passes")


def seasonal_baseline(frame):
    cols = ['seasonal_median_m', 'seasonal_mad_m', 'seasonal_pctile', 'seasonal_z',
            'base_n_obs', 'base_n_years']
    out = pd.DataFrame(np.nan, index=frame.index, columns=cols)
    for uid, grp in frame.groupby('station_uid'):
        doy = grp['day_dt'].dt.dayofyear.to_numpy()
        yr = grp['day_dt'].dt.year.to_numpy()
        w = grp['wse'].to_numpy(float)
        in_ref = (yr >= REF_YEARS[0]) & (yr <= REF_YEARS[1])
        d = np.abs(doy[:, None] - doy[None, :])
        d = np.minimum(d, 365 - d)
        m = (d <= SEASON_HALF_WINDOW) & in_ref[None, :] & (yr[:, None] != yr[None, :])
        for i, idx in enumerate(grp.index):
            vals = w[m[i]]
            n_years = len(np.unique(yr[m[i]]))
            out.at[idx, 'base_n_obs'] = len(vals)
            out.at[idx, 'base_n_years'] = n_years
            if len(vals) < MIN_BASE_OBS or n_years < MIN_BASE_YEARS:
                continue
            med = float(np.median(vals))
            mad = 1.4826 * float(np.median(np.abs(vals - med)))
            out.at[idx, 'seasonal_median_m'] = med
            out.at[idx, 'seasonal_mad_m'] = mad
            out.at[idx, 'seasonal_pctile'] = 100.0 * (np.sum(vals < w[i]) + 0.5 * np.sum(vals == w[i])) / len(vals)
            out.at[idx, 'seasonal_z'] = (w[i] - med) / mad if mad > 0 else np.nan
    return out


def level_class(p):
    if pd.isna(p):
        return 'Insufficient record'
    for thr, name in PCT_CLASSES:
        if p >= thr:
            return name
    return 'Unusually low'


df = df.join(seasonal_baseline(df))
df['level_class'] = df['seasonal_pctile'].map(level_class)
print("  Level classes (all rows): " + ', '.join(f"{k} {v}" for k, v in df['level_class'].value_counts().items()))

# --- 3d. Quality flags between passes ------------------------------------------
df['days_since_prev'] = df.groupby('station_uid')['day_dt'].diff().dt.days
df['rate_m_per_day'] = df['difference from previous'] / df['days_since_prev'].where(df['days_since_prev'] > 0)
in_ref = df['day_dt'].dt.year.between(REF_YEARS[0], REF_YEARS[1])
ref_rate = df['rate_m_per_day'].where(in_ref).groupby(df['station_uid'])
full_rate = df['rate_m_per_day'].groupby(df['station_uid'])
mad_fn = lambda s: 1.4826 * (s - s.median()).abs().median()
r_med = ref_rate.transform('median').fillna(full_rate.transform('median'))
r_mad = ref_rate.transform(mad_fn).fillna(full_rate.transform(mad_fn))
df['jump_flag'] = (((df['rate_m_per_day'] - r_med).abs() > JUMP_MAD_K * r_mad)
                   & (df['difference from previous'].abs() >= JUMP_MIN_M)).astype(int)
df['gap_flag'] = (df['days_since_prev'] > MAX_GAP_DAYS).astype(int)
df['high_uncertainty_flag'] = (df['uncertainty'] > HIGH_UNC_M).astype(int)


def neighbour_confirm(frame):
    """1 = an up/downstream station moved the same way within the window, 0 = none did,
    NaN = no jump or no linked neighbour with data."""
    res = pd.Series(np.nan, index=frame.index)
    flagged = frame.index[frame['jump_flag'] == 1]
    if not len(flagged):
        return res
    by_uid = {u: grp[['day_dt', 'difference from previous']] for u, grp in frame.groupby('station_uid')}
    win = pd.Timedelta(days=NEIGHBOUR_WINDOW_DAYS)
    for i in flagged:
        u = frame.at[i, 'station_uid']
        day = frame.at[i, 'day_dt']
        sign = np.sign(frame.at[i, 'difference from previous'])
        nbrs = ([after_map[u]] if u in after_map else []) + before_map.get(u, [])
        checked = False
        for n in nbrs:
            grp = by_uid.get(n)
            if grp is None:
                continue
            near = grp[(grp['day_dt'] - day).abs() <= win]
            if not len(near):
                continue
            checked = True
            chg = near['difference from previous']
            if ((np.sign(chg) == sign) & (chg.abs() >= NEIGHBOUR_MIN_M)).any():
                res.at[i] = 1
                break
        if checked and pd.isna(res.at[i]):
            res.at[i] = 0
    return res


df['neighbour_confirmed'] = neighbour_confirm(df)


def qc_text(r):
    parts = []
    if r.jump_flag == 1:
        if r.neighbour_confirmed == 1:
            parts.append('jump confirmed by neighbour')
        elif r.neighbour_confirmed == 0:
            parts.append('jump unconfirmed')
        else:
            parts.append('jump (no neighbour to check)')
    if r.gap_flag == 1:
        parts.append(f'gap > {MAX_GAP_DAYS} days')
    if r.high_uncertainty_flag == 1:
        parts.append(f'uncertainty > {HIGH_UNC_M} m')
    return '; '.join(parts) if parts else 'ok'


df['qc_status'] = [qc_text(r) for r in
                   df[['jump_flag', 'neighbour_confirmed', 'gap_flag', 'high_uncertainty_flag']].itertuples()]
print(f"  QC: {int(df['jump_flag'].sum())} jumps "
      f"({int((df['neighbour_confirmed'] == 1).sum())} confirmed by a neighbour), "
      f"{int(df['gap_flag'].sum())} long gaps, {int(df['high_uncertainty_flag'].sum())} high-uncertainty passes")

# --- 3e. Onset lag over the last 12 observations -------------------------------
print(f"Computing onset lags (rolling window of the last {LAG_WINDOW_OBS} observations)...")
_daily_cache = {}


def daily_change(uid):
    """Daily water level, linearly interpolated between passes (not across gaps > MAX_GAP_DAYS).
    Used ONLY for travel-time estimation, never shown as data."""
    if uid in _daily_cache:
        return _daily_cache[uid]
    s = df.loc[df.station_uid == uid].groupby('day_dt')['wse'].mean()
    if len(s) < 3:
        _daily_cache[uid] = None
        return None
    idx = pd.date_range(s.index.min(), s.index.max(), freq='D')
    obs = pd.Series(s.index, index=s.index).reindex(idx)
    gap = (obs.bfill() - obs.ffill()).dt.days
    full = s.reindex(idx).interpolate(method='time', limit_area='inside')
    full[gap > MAX_GAP_DAYS] = np.nan
    _daily_cache[uid] = full
    return full


def best_lag(up_vals, dn_vals, s, e):
    y = dn_vals[s:e + 1]
    best_L, best_r = np.nan, -np.inf
    for L in range(MAX_LAG_DAYS + 1):
        x = up_vals[s - L:e + 1 - L]
        m = np.isfinite(x) & np.isfinite(y)
        if m.sum() < LAG_MIN_OVERLAP_DAYS:
            continue
        xs, ys = x[m] - x[m].mean(), y[m] - y[m].mean()
        if xs.std() == 0 or ys.std() == 0:
            continue
        r = np.corrcoef(xs, ys)[0, 1]
        if np.isfinite(r) and r > best_r:
            best_L, best_r = L, r
    if not np.isfinite(best_r):
        return np.nan, np.nan
    return (best_L if best_r >= MIN_R else np.nan), best_r


need_lag = is_new
df['Lag Days'] = np.nan
df['lag_r'] = np.nan
for up, grp in df[need_lag].groupby('station_uid'):
    dn = after_map.get(up)
    su, sd = daily_change(up), (daily_change(dn) if dn else None)
    if su is None or sd is None:
        continue
    start = min(su.index.min(), sd.index.min()) - pd.Timedelta(days=MAX_LAG_DAYS)
    grid = pd.date_range(start, max(su.index.max(), sd.index.max()), freq='D')
    up_vals, dn_vals = su.reindex(grid).to_numpy(), sd.reindex(grid).to_numpy()
    pos = pd.Series(np.arange(len(grid)), index=grid)
    obs_days = np.sort(df.loc[df.station_uid == up, 'day_dt'].unique())
    for i, day in grp['day_dt'].items():
        k = np.searchsorted(obs_days, np.datetime64(day), side='right')
        if k < LAG_WINDOW_OBS:
            continue
        s, e = pos[pd.Timestamp(obs_days[k - LAG_WINDOW_OBS])], pos[day]
        df.at[i, 'Lag Days'], df.at[i, 'lag_r'] = best_lag(up_vals, dn_vals, s, e)

all_lags = df.loc[need_lag, ['station_uid', 'Lag Days']]
if os.path.exists(MASTER_CSV):
    saved = pd.read_csv(MASTER_CSV, usecols=['source', 'station_id', 'Lag Days'])
    saved['station_uid'] = saved['source'].str.lower() + ':' + saved['station_id'].astype(int).astype(str)
    all_lags = pd.concat([saved[['station_uid', 'Lag Days']], all_lags], ignore_index=True)
stations['median_lag_days'] = stations.station_uid.map(all_lags.groupby('station_uid')['Lag Days'].median())
print(f"  Lag Days computed for {int(need_lag.sum())} new rows; "
      f"{int(df.loc[need_lag, 'Lag Days'].notna().sum())} with an accepted lag")

# --- 3f. Elevation (SRTM, once per station, cached) --------------------------
elev_cols = ['Elevation_Min', 'Elevation_Mean', 'Elevation_Max']
elev = (pd.read_csv(ELEV_CACHE) if os.path.exists(ELEV_CACHE)
        else pd.DataFrame(columns=['station_uid'] + elev_cols))
todo = stations[~stations.station_uid.isin(elev.station_uid)]
if len(todo):
    print(f"Fetching SRTM elevation for {len(todo)} stations...")
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([float(r.longitude), float(r.latitude)]).buffer(ELEV_BUFFER_M),
                   {'uid': r.station_uid}) for r in todo.itertuples()])
    red = (ee.Reducer.min().combine(ee.Reducer.mean(), '', True)
           .combine(ee.Reducer.max(), '', True))
    res = (ee.Image('USGS/SRTMGL1_003').select('elevation')
           .reduceRegions(collection=fc, reducer=red, scale=30).getInfo())
    new = pd.DataFrame([f['properties'] for f in res['features']]).rename(
        columns={'uid': 'station_uid', 'min': 'Elevation_Min',
                 'mean': 'Elevation_Mean', 'max': 'Elevation_Max'})
    elev = pd.concat([elev, new[['station_uid'] + elev_cols]], ignore_index=True)
    elev.to_csv(ELEV_CACHE, index=False)
stations = stations.merge(elev, on='station_uid', how='left')

# --- 3g. 15-day antecedent hydro-climate, gap-filled (CHIRPS + ERA5-Land) ----
CHIRPS = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').select(['precipitation'], ['rain'])
ERA5 = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
ERA5_IN = ['temperature_2m', 'volumetric_soil_water_layer_1', 'total_evaporation_sum', 'runoff_sum']
ERA5_OUT = ['t2m', 'swvl1', 'evap', 'ro']
REF_START = ee.Date.fromYMD(CLIM_REF_YEARS[0], 1, 1)
REF_END = ee.Date.fromYMD(CLIM_REF_YEARS[1] + 1, 1, 1)
DATES_PER_CALL = 20


def last_available(col):
    recent = col.filterDate((TODAY - pd.Timedelta(days=400)).strftime('%Y-%m-%d'),
                            (TODAY + pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
    ms = recent.aggregate_max('system:time_start').getInfo()
    return pd.Timestamp(ms, unit='ms').normalize() if ms else pd.Timestamp('1900-01-01')


_clim_cache = {}


def doy_climatology(doy):
    """(CHIRPS rain, ERA5-Land bands) mean for one day of year over CLIM_REF_YEARS."""
    if doy not in _clim_cache:
        f = ee.Filter.calendarRange(doy, doy, 'day_of_year')
        _clim_cache[doy] = (
            CHIRPS.filterDate(REF_START, REF_END).filter(f).mean().rename('rain'),
            ERA5.filterDate(REF_START, REF_END).filter(f).select(ERA5_IN, ERA5_OUT).mean())
    return _clim_cache[doy]


def window_image(date_key):
    """15-day antecedent image for one observation date + (days CHIRPS, days ERA5 observed)."""
    day = pd.Timestamp(date_key).normalize()
    days = [day - pd.Timedelta(days=k) for k in range(WINDOW_DAYS - 1, -1, -1)]
    n_ch = sum(d <= CHIRPS_LAST for d in days)
    n_er = sum(d <= ERA5_LAST for d in days)
    start, end = days[0].strftime('%Y-%m-%d'), (day + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    if n_ch == WINDOW_DAYS and n_er == WINDOW_DAYS:
        er = ERA5.filterDate(start, end)
        img = ee.Image.cat([
            CHIRPS.filterDate(start, end).sum().rename('rain_sum'),
            er.select(ERA5_IN[:2], ['t2m_mean', 'swvl1_mean']).mean(),
            er.select(ERA5_IN[2:], ['evap_sum', 'ro_sum']).sum(),
        ])
        return img.toFloat(), n_ch, n_er
    imgs = []
    for d in days:
        d0, d1 = d.strftime('%Y-%m-%d'), (d + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        doy = int(d.dayofyear)
        if d <= ERA5_LAST:
            er_day = ee.Image(ERA5.filterDate(d0, d1).first())
            era = er_day.select(ERA5_IN, ERA5_OUT)
        else:
            era = doy_climatology(doy)[1]
        if d <= CHIRPS_LAST:
            rain = ee.Image(CHIRPS.filterDate(d0, d1).first()).rename('rain')
        elif d <= ERA5_LAST:
            rain = er_day.select(['total_precipitation_sum'], ['rain']).multiply(1000)
        else:
            rain = doy_climatology(doy)[0]
        imgs.append(rain.addBands(era).toFloat())
    col = ee.ImageCollection.fromImages(imgs)
    img = ee.Image.cat([
        col.select('rain').sum().rename('rain_sum'),
        col.select(['t2m', 'swvl1']).mean().rename(['t2m_mean', 'swvl1_mean']),
        col.select(['evap', 'ro']).sum().rename(['evap_sum', 'ro_sum']),
    ])
    return img.toFloat(), n_ch, n_er


def fetch_dates(groups):
    """groups: list of (date_key, rows). Returns a DataFrame, splitting the request on failure."""
    fcs = []
    for date_key, rows in groups:
        img, n_ch, n_er = window_image(date_key)
        pts = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([float(r.longitude), float(r.latitude)])
                       .buffer(BUFFER_M.get(r.type, 5000), 100),
                       {'uid': r.station_uid, 'date': date_key, 'n_chirps': n_ch, 'n_era5': n_er})
            for r in rows.itertuples()])
        red = img.reduceRegions(collection=pts, reducer=ee.Reducer.mean(), scale=5000, tileScale=4)
        fcs.append(red.map(lambda f: ee.Feature(None, f.toDictionary())))
    err = ''
    for attempt in range(2):
        try:
            res = ee.FeatureCollection(fcs).flatten().getInfo()['features']
            return pd.DataFrame([f['properties'] for f in res])
        except Exception as e:
            err = str(e)
            if 'memory' in err.lower() or 'too many' in err.lower() or 'timed out' in err.lower():
                break
            print(f"    request failed ({err[:120]}); retrying")
            time.sleep(10)
    n_rows = sum(len(r) for _, r in groups)
    if len(groups) > 1:
        h = len(groups) // 2
        print(f"    splitting {len(groups)} dates into {h} + {len(groups) - h}")
        return pd.concat([fetch_dates(groups[:h]), fetch_dates(groups[h:])], ignore_index=True)
    if n_rows > 1:
        date_key, rows = groups[0]
        h = n_rows // 2
        print(f"    {date_key}: splitting {n_rows} stations into {h} + {n_rows - h}")
        return pd.concat([fetch_dates([(date_key, rows.iloc[:h])]),
                          fetch_dates([(date_key, rows.iloc[h:])])], ignore_index=True)
    print(f"    {groups[0][0]} / {groups[0][1].station_uid.iloc[0]}: failed ({err[:120]}); retried next run")
    return pd.DataFrame()


clim_cols = ['station_uid', 'date_key', 'rain_sum', 't2m_mean', 'swvl1_mean',
             'evap_sum', 'ro_sum', 'n_chirps', 'n_era5', 'complete', 'fetched_on']
VAL_COLS = ['rain_sum', 't2m_mean', 'swvl1_mean', 'evap_sum', 'ro_sum']
clim = (pd.read_csv(CLIMATE_CACHE) if os.path.exists(CLIMATE_CACHE)
        else pd.DataFrame(columns=clim_cols))
for c in clim_cols:
    if c not in clim:
        clim[c] = np.nan

req_cols = ['station_uid', 'type', 'latitude', 'longitude', 'date_key']
requests_ = [df.loc[is_new, req_cols]]

master_full, master_sel, refresh_keys = None, None, set()
if os.path.exists(MASTER_CSV):
    master_full = pd.read_csv(MASTER_CSV)
    master_full['station_uid'] = (master_full['source'].str.lower() + ':'
                                  + master_full['station_id'].astype(int).astype(str))
    master_full['date'] = master_full['date'].astype(str)
    for c in CLIMATE_COLS_OUT:
        if c not in master_full:
            master_full[c] = np.nan
    if UPDATE_MASTER_CLIMATE:
        master_sel = master_full[CLIMATE_COLS_OUT].isna().any(axis=1)
        if REFRESH_GAPFILLED_DAYS and all(c in master_full for c in GAPFILL_COLS):
            gf = master_full[GAPFILL_COLS].fillna(0).sum(axis=1) > 0
            rec = pd.to_datetime(master_full['date']) >= TODAY - pd.Timedelta(days=REFRESH_GAPFILLED_DAYS)
            refresh = gf & rec
            refresh_keys = set(master_full.loc[refresh, 'station_uid'] + '|' + master_full.loc[refresh, 'date'])
            master_sel = master_sel | refresh
        if master_sel.any():
            print(f"Saved rows needing climate: {int(master_sel.sum())}")
            requests_.append(master_full.loc[master_sel, ['station_uid', 'type', 'latitude',
                                                          'longitude', 'date']]
                             .rename(columns={'date': 'date_key'}))

need = (pd.concat(requests_, ignore_index=True)
        .drop_duplicates(['station_uid', 'date_key'])
        .merge(clim[['station_uid', 'date_key', 'complete', 'fetched_on']],
               on=['station_uid', 'date_key'], how='left'))
cutoff = TODAY - pd.Timedelta(days=RETRY_RECENT_DAYS)
is_recent = pd.to_datetime(need.date_key) >= cutoff
not_cached = need.complete.isna()
incomplete = need.complete.astype(str).eq('False')
stale = ((need.station_uid + '|' + need.date_key).isin(refresh_keys)
         & (need.fetched_on.astype(str) != TODAY.strftime('%Y-%m-%d')))
fetched_on = pd.to_datetime(need.fetched_on, errors='coerce')
retry_old = fetched_on.isna() | (fetched_on <= TODAY - pd.Timedelta(days=CLIMATE_RETRY_DAYS))
todo = need[not_cached | (incomplete & (is_recent | retry_old)) | stale]
print(f"Climate requests: {len(need)} station-dates checked, {len(todo)} to fetch "
      f"({int(not_cached.sum())} never fetched, {int((incomplete & (is_recent | retry_old)).sum())} "
      f"retried blanks, {int(stale.sum())} gap-filled refreshes)")

if len(todo):
    CHIRPS_LAST, ERA5_LAST = last_available(CHIRPS), last_available(ERA5)
    print(f"Latest data in GEE: CHIRPS {CHIRPS_LAST:%Y-%m-%d}, ERA5-Land {ERA5_LAST:%Y-%m-%d} "
          "(later days are gap-filled)")
    groups = [(k, grp) for k, grp in todo.groupby('date_key')]
    calls = [groups[i:i + DATES_PER_CALL] for i in range(0, len(groups), DATES_PER_CALL)]
    print(f"Fetching 15-day climate for {len(todo)} station-dates "
          f"({len(groups)} dates, {len(calls)} requests)...")
    for b, chunk in enumerate(calls):
        new = fetch_dates(chunk)
        if new.empty:
            print(f"  request {b + 1}/{len(calls)}: nothing returned")
            continue
        new = new.rename(columns={'uid': 'station_uid', 'date': 'date_key'})
        for c in clim_cols:
            if c not in new:
                new[c] = np.nan
        new['complete'] = new[VAL_COLS].notna().all(axis=1)
        new['fetched_on'] = TODAY.strftime('%Y-%m-%d')
        keys = set(zip(new.station_uid, new.date_key))
        keep = [k not in keys for k in zip(clim.station_uid, clim.date_key)]
        clim = pd.concat([clim[keep], new[clim_cols]], ignore_index=True)
        clim.to_csv(CLIMATE_CACHE, index=False)
        print(f"  request {b + 1}/{len(calls)} done ({len(new)} station-dates)")

c = clim.copy()
for col in VAL_COLS + ['n_chirps', 'n_era5']:
    c[col] = pd.to_numeric(c[col], errors='coerce')
c['last_15_days_Rainfall_mm'] = c.rain_sum
c['last_15_days_Soil_Moisture'] = c.swvl1_mean
c['last_15_days_Evapotranspiration'] = -c.evap_sum * 1000
c['last_15_days_Temp_C'] = c.t2m_mean - 273.15
c['last_15_days_runoff'] = c.ro_sum * 1000
c['rain_days_gapfilled'] = (WINDOW_DAYS - c.n_chirps).clip(lower=0)
c['era5_days_gapfilled'] = (WINDOW_DAYS - c.n_era5).clip(lower=0)
clim_out = (c[['station_uid', 'date_key'] + CLIMATE_COLS_OUT + GAPFILL_COLS]
            .drop_duplicates(['station_uid', 'date_key'], keep='last'))
df = df.merge(clim_out, on=['station_uid', 'date_key'], how='left')

# --- 3h. Final table + export ------------------------------------------------
df = df.merge(stations[['station_uid'] + elev_cols
                       + ['Station After_this_station', 'Station Before_this_Station']],
              on='station_uid', how='left')

final = pd.DataFrame({
    'source': df['source'],
    'station_id': df['station_id'],
    'station_uid': df['station_uid'],
    'type': df['type'],
    'location/river_name': df['location'],
    'latitude': df['latitude'],
    'longitude': df['longitude'],
    'year': df['date_dt'].dt.year,
    'month': df['date_dt'].dt.month,
    'day': df['date_dt'].dt.day,
    'date': df['date_key'],
    'Water Surface Elevation - values(m)': df['wse'],
    'uncertainty (m)': df['uncertainty'],
    'minimium': df['minimium'],
    'maxmium': df['maxmium'],
    'average': df['average'],
    'deviation from average': df['deviation from average'],
    'difference from previous': df['difference from previous'],
    'seasonal_median_m': df['seasonal_median_m'],
    'seasonal_mad_m': df['seasonal_mad_m'],
    'seasonal_pctile': df['seasonal_pctile'],
    'seasonal_z': df['seasonal_z'],
    'base_n_obs': df['base_n_obs'],
    'base_n_years': df['base_n_years'],
    'level_class': df['level_class'],
    'days_since_prev': df['days_since_prev'],
    'rate_m_per_day': df['rate_m_per_day'],
    'jump_flag': df['jump_flag'],
    'neighbour_confirmed': df['neighbour_confirmed'],
    'gap_flag': df['gap_flag'],
    'high_uncertainty_flag': df['high_uncertainty_flag'],
    'qc_status': df['qc_status'],
    'last_15_days_Rainfall_mm': df['last_15_days_Rainfall_mm'],
    'last_15_days_Soil_Moisture': df['last_15_days_Soil_Moisture'],
    'last_15_days_Evapotranspiration': df['last_15_days_Evapotranspiration'],
    'last_15_days_Temp_C': df['last_15_days_Temp_C'],
    'last_15_days_runoff': df['last_15_days_runoff'],
    'rain_days_gapfilled': df['rain_days_gapfilled'],
    'era5_days_gapfilled': df['era5_days_gapfilled'],
    'Elevation_Max': df['Elevation_Max'],
    'Elevation_Mean': df['Elevation_Mean'],
    'Elevation_Min': df['Elevation_Min'],
    'Station After_this_station': df['Station After_this_station'],
    'Station Before_this_Station': df['Station Before_this_Station'],
    'Lag Days': df['Lag Days'],
}).sort_values(['source', 'type', 'station_id', 'date']).reset_index(drop=True)

notes = pd.DataFrame([
    ('station_uid', 'Unique station key "source:id". Use this (not station_id) to match stations: '
                    'DAHITI and Hydroweb IDs can collide.'),
    ('station links', "IDs written as source:id. DAHITI links from the manual order table; "
                      "Hydroweb river stations chained along the same river by mean level "
                      "(higher = upstream); MANUAL_LINKS override both."),
    ('minimium / maxmium / average', "As of each observation: running values from the station's first pass, "
                                     f"anchored to {os.path.basename(STATION_LOOKUP_XLSX)} where the station "
                                     "is listed (min = lower of lookup and running minimum; max = higher of "
                                     "the two; average = lookup average weighted by its count and blended with "
                                     "the running average, or the fixed lookup average if no count is given)."),
    ('deviation from average', 'Level minus the average above (m). Use seasonal_* and level_class for status.'),
    ('seasonal_median_m / seasonal_mad_m',
     f"Median and robust SD (1.4826 x MAD) of the station's passes within +/-{SEASON_HALF_WINDOW} days of "
     f"the same day of year in other years of {REF_YEARS[0]}-{REF_YEARS[1]} (own year left out). "
     "Fixed reference period, so values do not drift as new data arrive."),
    ('seasonal_pctile', 'Percentile of this pass within that seasonal baseline (0-100).'),
    ('seasonal_z', '(level - seasonal median) / robust SD.'),
    ('base_n_obs / base_n_years', 'Passes and distinct years in the seasonal baseline.'),
    ('level_class', f"Unusually high >= 90th percentile; Above normal 67-90; Near normal 33-67; "
                    f"Below normal 10-33; Unusually low < 10. 'Insufficient record' if fewer than "
                    f"{MIN_BASE_YEARS} baseline years or {MIN_BASE_OBS} baseline passes."),
    ('days_since_prev / rate_m_per_day', 'Days since the previous pass and change per day (m/day). '
                                         'Levels are never interpolated between passes in the product.'),
    ('jump_flag', f"1 if the rate of change is more than {JUMP_MAD_K} robust SDs from the station's own "
                  f"{REF_YEARS[0]}-{REF_YEARS[1]} rates AND the change is at least {JUMP_MIN_M} m."),
    ('neighbour_confirmed', f"For jumps: 1 if a linked upstream/downstream station changed the same way "
                            f"by >= {NEIGHBOUR_MIN_M} m within +/-{NEIGHBOUR_WINDOW_DAYS} days, 0 if not, "
                            "blank if no neighbour could be checked."),
    ('gap_flag', f'1 if more than {MAX_GAP_DAYS} days since the previous pass.'),
    ('high_uncertainty_flag', f'1 if the reported uncertainty exceeds {HIGH_UNC_M} m.'),
    ('qc_status', 'Plain-language summary of the flags above ("ok" if none).'),
    ('last_15_days_*', f"{WINDOW_DAYS} days ending on and including the observation date; "
                       f"buffer {BUFFER_M['river']} m (river) / {BUFFER_M['lake']} m (lake) around the "
                       "station - LOCAL conditions, not the upstream catchment. "
                       "Days not yet published are gap-filled (see *_gapfilled)."),
    ('last_15_days_Rainfall_mm', 'CHIRPS daily, summed (mm). Missing CHIRPS days: ERA5-Land '
                                 'total_precipitation_sum, else CHIRPS day-of-year mean '
                                 f'{CLIM_REF_YEARS[0]}-{CLIM_REF_YEARS[1]}.'),
    ('last_15_days_Soil_Moisture', 'ERA5-Land volumetric_soil_water_layer_1, mean (m3/m3, 0-7 cm)'),
    ('last_15_days_Evapotranspiration', 'ERA5-Land total_evaporation_sum, summed, sign flipped (mm)'),
    ('last_15_days_Temp_C', 'ERA5-Land temperature_2m, mean (deg C)'),
    ('last_15_days_runoff', 'ERA5-Land runoff_sum, summed (mm)'),
    ('rain_days_gapfilled', 'Days of the 15-day window without CHIRPS data (filled as above). 0 = all observed.'),
    ('era5_days_gapfilled', 'Days of the 15-day window without ERA5-Land data, filled with the ERA5-Land '
                            f'day-of-year mean {CLIM_REF_YEARS[0]}-{CLIM_REF_YEARS[1]}. 0 = all observed.'),
    ('Elevation_*', f'SRTM 30 m within {ELEV_BUFFER_M} m of the station (m)'),
    ('Lag Days', f"Days (0-{MAX_LAG_DAYS}) by which the downstream station's daily water level "
                 f"best follows this station's, over the window covered by this station's last "
                 f"{LAG_WINDOW_OBS} observations (data up to this date only). Daily levels are "
                 f"interpolated for this calculation only, never across gaps > {MAX_GAP_DAYS} days. "
                 f"Blank if fewer than {LAG_WINDOW_OBS} observations, no downstream station, too little "
                 f"overlap or correlation below {MIN_R}."),
    ('difference from previous', 'Change from the previous observation at the same station (m)'),
    ('Stations sheet: min_wse / max_wse / average_wse / in_lookup',
     'Latest minimum, maximum and average per station (lookup-anchored); in_lookup = 1 if listed in the lookup.'),
    ('station_catchments (GEE asset)', f'Upstream area of each station traced through HydroBASINS level '
                                       f'{HYBAS_LEVEL} (NEXT_DOWN), cut at {CATCHMENT_BBOX}.'),
], columns=['column', 'definition'])


def to_py(v):
    return v.item() if hasattr(v, 'item') else v


def save_xlsx_safely(write_fn):
    """Write the workbook locally first, then copy it over the Drive copy."""
    tmp = os.path.join(WORK_DIR,
                       f'_tmp_{OUTPUT_BASENAME}_{RUN_STAMP}.xlsx')
    write_fn(tmp)
    shutil.copy(tmp, MASTER_XLSX)
    os.remove(tmp)


def write_full_xlsx(frame):
    if len(frame) > 1_048_575:
        print(f"WARNING: {len(frame)} rows is more than one Excel sheet holds; "
              "the CSV is complete, the XLSX 'Merged' sheet is cut off.")

    def w(path):
        with pd.ExcelWriter(path, engine='openpyxl') as xw:
            frame.head(1_048_575).to_excel(xw, sheet_name='Merged', index=False)
            stations.drop(columns=['river_key']).to_excel(xw, sheet_name='Stations', index=False)
            notes.to_excel(xw, sheet_name='Column_notes', index=False)
    save_xlsx_safely(w)


cached = set(clim.station_uid.astype(str) + '|' + clim.date_key.astype(str))
fetched = (final['station_uid'] + '|' + final['date']).isin(cached)
recent_row = pd.to_datetime(final['date']) >= cutoff
incomplete_row = final[CLIMATE_COLS_OUT].isna().any(axis=1)
hold = incomplete_row & (recent_row | ~fetched)
ready = final[~hold]
held_back = int((hold & ~obs_key(final).isin(old_keys)).sum())

# --- Update saved rows (new columns, back-filled climate, derived columns) ----
master_changed, n_backfilled, n_derived = False, 0, 0
if master_full is not None:
    file_cols = pd.read_csv(MASTER_CSV, nrows=0).columns
    if any(col not in file_cols for col in final.columns):
        master_changed = True            # new columns (e.g. station_uid, seasonal_*, QC) -> rewrite
    for col in GAPFILL_COLS:
        if col not in master_full:
            master_full[col] = np.where(master_full[CLIMATE_COLS_OUT].notna().all(axis=1), 0.0, np.nan)
            master_changed = True
    if master_sel is not None and master_sel.any():
        co = clim_out.set_index(clim_out.station_uid + '|' + clim_out.date_key)
        mk = master_full['station_uid'] + '|' + master_full['date']
        nv = {col: mk.map(co[col]) for col in CLIMATE_COLS_OUT + GAPFILL_COLS}
        ok = master_sel & pd.concat([nv[col] for col in CLIMATE_COLS_OUT], axis=1).notna().all(axis=1)
        diff = pd.Series(False, index=master_full.index)
        for col in CLIMATE_COLS_OUT + GAPFILL_COLS:
            old = pd.to_numeric(master_full[col], errors='coerce')
            new_v = pd.to_numeric(nv[col], errors='coerce')
            same = (old.round(6) == new_v.round(6)) | (old.isna() & new_v.isna())
            diff |= ok & ~same
        for col in CLIMATE_COLS_OUT + GAPFILL_COLS:
            master_full.loc[diff, col] = nv[col][diff]
        n_backfilled = int(diff.sum())
        master_changed = master_changed or n_backfilled > 0

    # Derived columns (lookup-anchored min / max / average, seasonal baseline, QC)
    dmap = final.assign(_k=final['station_uid'] + '|' + final['date']).drop_duplicates('_k').set_index('_k')
    mk = master_full['station_uid'] + '|' + master_full['date']
    for col in DERIVED_COLS:
        new_v = mk.map(dmap[col])
        if col not in master_full:
            master_full[col] = new_v
            master_changed = True
            continue
        old = master_full[col]
        if col in TEXT_COLS:
            same = (old.astype(str) == new_v.astype(str)) | (old.isna() & new_v.isna())
        else:
            o = pd.to_numeric(old, errors='coerce')
            n = pd.to_numeric(new_v, errors='coerce')
            same = (o.round(6) == n.round(6)) | (o.isna() & n.isna())
        if (~same).any():
            master_full[col] = new_v
            if REBUILD_ON_DERIVED_CHANGES and col not in REBUILD_IGNORE_COLS:
                n_derived += int((~same).sum())
                master_changed = True

out_cols = list(final.columns)
if master_full is not None:
    out_cols += [col for col in master_full.columns if col not in out_cols]
new_rows = ready[~obs_key(ready).isin(old_keys)].reindex(columns=out_cols)

if master_full is None:
    new_rows.to_csv(MASTER_CSV, index=False)
    write_full_xlsx(new_rows)
elif master_changed:
    everything = pd.concat([master_full.reindex(columns=out_cols), new_rows], ignore_index=True)
    everything.to_csv(MASTER_CSV, index=False)
    write_full_xlsx(everything)
    if os.path.exists(GEE_LEDGER):
        os.remove(GEE_LEDGER)
    print(f"Saved rows updated ({n_backfilled} with new or changed climate values, "
          f"{n_derived} derived values changed or added); master files rewritten, GEE asset will be rebuilt.")
else:
    header = pd.read_csv(MASTER_CSV, nrows=0).columns.tolist()
    if len(new_rows):
        new_rows.reindex(columns=header).to_csv(MASTER_CSV, mode='a', header=False, index=False)
    appended = False
    if os.path.exists(MASTER_XLSX):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(MASTER_XLSX)
            ws = wb['Merged']
            xhdr = [cell.value for cell in ws[1]]
            for row in new_rows.reindex(columns=xhdr).itertuples(index=False):
                ws.append([None if pd.isna(v) else to_py(v) for v in row])
            for name in ['Stations', 'Lags_by_year', 'Column_notes']:
                if name in wb.sheetnames:
                    del wb[name]

            def w(path):
                wb.save(path)
                with pd.ExcelWriter(path, engine='openpyxl', mode='a') as xw:
                    stations.drop(columns=['river_key']).to_excel(xw, sheet_name='Stations', index=False)
                    notes.to_excel(xw, sheet_name='Column_notes', index=False)
            save_xlsx_safely(w)
            appended = True
        except Exception as e:
            print(f"{os.path.basename(MASTER_XLSX)} could not be opened ({type(e).__name__}: {e}); "
                  "rebuilding it from the CSV.")
    if not appended:
        write_full_xlsx(pd.read_csv(MASTER_CSV))
        print(f"Rebuilt {os.path.basename(MASTER_XLSX)} from {os.path.basename(MASTER_CSV)}")

still_blank = (master_full[CLIMATE_COLS_OUT].isna().any(axis=1).sum()
               if master_full is not None else 0) + int(new_rows[CLIMATE_COLS_OUT].isna().any(axis=1).sum())
if still_blank:
    print(f"Rows still without complete climate: {int(still_blank)} "
          f"(retried after {CLIMATE_RETRY_DAYS} days; see cache_climate_15d_v2.csv)")
print("\nDone.")
print(final.groupby(['source', 'type'])['station_id'].nunique().rename('stations'))
print(final.groupby('source')['date'].max().rename('latest date'))
print(f"New observations appended: {len(new_rows)}  "
      f"(already saved: {len(old_keys)}, held back because GEE gave no climate: {held_back})")
gf_new = new_rows[GAPFILL_COLS].fillna(0).sum(axis=1).gt(0).sum() if len(new_rows) else 0
print(f"New rows with gap-filled climate days: {int(gf_new)}")
latest_status = final.sort_values('date').groupby('station_uid').tail(1)['level_class'].value_counts()
print("Latest status per station: " + ', '.join(f"{k} {v}" for k, v in latest_status.items()))
print(f"-> {MASTER_XLSX}\n-> {MASTER_CSV}")


# =========================================================================== #
# STEP 4 - UPLOAD TO EARTH ENGINE (observations, stations, catchments)        #
# =========================================================================== #
def gee_name(col):
    return re.sub(r'[^0-9A-Za-z_]+', '_', str(col)).strip('_')


def df_to_fc(frame, date_col=None):
    feats = []
    for rec in frame.to_dict('records'):
        props = {gee_name(k): to_py(v) for k, v in rec.items() if pd.notna(v)}
        if date_col and pd.notna(rec.get(date_col)):
            props['system:time_start'] = int(pd.Timestamp(rec[date_col]).value // 10**6)
        geom = ee.Geometry.Point([float(rec['longitude']), float(rec['latitude'])])
        feats.append(ee.Feature(geom, props))
    return ee.FeatureCollection(feats)


def asset_exists(asset_id):
    try:
        ee.data.getAsset(asset_id)
        return True
    except ee.EEException:
        return False


def make_public(asset_id):
    """Give 'Anyone can read' on an asset (an export/rename creates a fresh asset with a private ACL)."""
    try:
        ee.data.setAssetAcl(asset_id, {'all_users_can_read': True})
        print(f"  shared publicly (anyone can read): {asset_id}")
        return True
    except Exception as e1:
        try:
            pol = ee.data.getIamPolicy(asset_id)
            bindings = [b for b in pol.get('bindings', []) if b.get('role') != 'roles/earthengine.viewer'
                        or 'allUsers' not in b.get('members', [])]
            viewers = [b for b in pol.get('bindings', []) if b.get('role') == 'roles/earthengine.viewer']
            members = sorted(set(sum([b.get('members', []) for b in viewers], []) + ['allUsers']))
            bindings = [b for b in pol.get('bindings', []) if b.get('role') != 'roles/earthengine.viewer']
            bindings.append({'role': 'roles/earthengine.viewer', 'members': members})
            pol['bindings'] = bindings
            ee.data.setIamPolicy(asset_id, {'policy': pol})
            print(f"  shared publicly (anyone can read): {asset_id}")
            return True
        except Exception as e2:
            print(f"  WARNING: could not share {asset_id} publicly ({str(e1)[:120]} | {str(e2)[:120]}). "
                  f"Give the service account the 'Earth Engine Resource Admin' role, or share it by hand.")
            return False


def start_export(fc, asset_id, desc):
    if asset_exists(asset_id):
        ee.data.deleteAsset(asset_id)
    task = ee.batch.Export.table.toAsset(collection=fc, description=gee_name(desc)[:100],
                                         assetId=asset_id)
    task.start()
    return task


def wait_for(tasks, poll=30):
    done = ('COMPLETED', 'FAILED', 'CANCELLED')
    while True:
        states = [t.status()['state'] for t in tasks]
        if all(s in done for s in states):
            for t, s in zip(tasks, states):
                if s != 'COMPLETED':
                    print(f"  {t.status().get('description')}: {s} "
                          f"{t.status().get('error_message', '')}")
            return states
        print(f"  waiting: {sum(s == 'COMPLETED' for s in states)}/{len(tasks)} tasks done")
        time.sleep(poll)


def build_catchments():
    """Trace each station's upstream area through HydroBASINS and export station_catchments."""
    asset_id = f'{ASSET_FOLDER}/station_catchments'
    cols = ['station_uid', 'hybas_ids', 'n_basins']
    cache = (pd.read_csv(CATCHMENT_CACHE, dtype={'hybas_ids': str}) if os.path.exists(CATCHMENT_CACHE)
             else pd.DataFrame(columns=cols))
    todo_st = stations[~stations.station_uid.isin(cache.station_uid)]
    if todo_st.empty and asset_exists(asset_id):
        print("Station catchments: up to date.")
        return None
    hb = (ee.FeatureCollection(f'WWF/HydroSHEDS/v1/Basins/hybas_{HYBAS_LEVEL}')
          .filterBounds(ee.Geometry.Rectangle(CATCHMENT_BBOX)))
    if len(todo_st):
        print(f"Tracing upstream catchments for {len(todo_st)} stations (HydroBASINS level {HYBAS_LEVEL})...")
        pairs = hb.reduceColumns(ee.Reducer.toList(2), ['HYBAS_ID', 'NEXT_DOWN']).get('list').getInfo()
        children = {}
        for hid, nd in pairs:
            children.setdefault(int(nd), []).append(int(hid))
        pts = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([float(r.longitude), float(r.latitude)]), {'uid': r.station_uid})
            for r in todo_st.itertuples()])
        joined = ee.Join.saveFirst('basin').apply(
            pts, hb, ee.Filter.intersects(leftField='.geo', rightField='.geo'))
        hits = joined.map(lambda f: ee.Feature(None, {
            'uid': f.get('uid'), 'hybas': ee.Feature(f.get('basin')).get('HYBAS_ID')})).getInfo()['features']
        rows = []
        for h in hits:
            start = int(h['properties']['hybas'])
            seen, stack = {start}, [start]
            while stack:
                cur = stack.pop()
                for child in children.get(cur, []):
                    if child not in seen:
                        seen.add(child)
                        stack.append(child)
            rows.append({'station_uid': h['properties']['uid'],
                         'hybas_ids': ';'.join(str(x) for x in sorted(seen)), 'n_basins': len(seen)})
        missing = set(todo_st.station_uid) - {r['station_uid'] for r in rows}
        if missing:
            print(f"  {len(missing)} stations fall outside HydroBASINS coverage in the box: "
                  f"{', '.join(sorted(missing)[:10])}{' ...' if len(missing) > 10 else ''}")
        cache = pd.concat([cache, pd.DataFrame(rows, columns=cols)], ignore_index=True)
        cache.to_csv(CATCHMENT_CACHE, index=False)
    feats = []
    for r in cache[cache.station_uid.isin(stations.station_uid)].itertuples():
        ids = [int(x) for x in str(r.hybas_ids).split(';') if x]
        geom = hb.filter(ee.Filter.inList('HYBAS_ID', ids)).geometry(500).dissolve(500)
        feats.append(ee.Feature(geom, {'station_uid': r.station_uid, 'n_basins': len(ids),
                                       'hybas_level': HYBAS_LEVEL})
                     .set('area_km2', geom.area(1000).divide(1e6)))
    if not feats:
        return None
    task = start_export(ee.FeatureCollection(feats), asset_id, 'station_catchments')
    print(f"Started station_catchments export ({len(feats)} catchments; runs in the background)")
    return task


if UPLOAD_TO_GEE:
    print("\n=== STEP 4: UPLOAD TO GEE (new observations only) ===")
    if not asset_exists(ASSET_FOLDER):
        ee.data.createAsset({'type': 'FOLDER'}, ASSET_FOLDER)
        print(f"Created folder {ASSET_FOLDER}")

    target = f'{ASSET_FOLDER}/merged_observations'
    backup = f'{target}_old'

    if BUILD_CATCHMENTS:
        try:
            build_catchments()
        except Exception as e:
            print(f"Catchment build failed ({type(e).__name__}: {e}); continuing without it.")

    st_task = start_export(df_to_fc(stations.drop(columns=['river_key'])),
                           f'{ASSET_FOLDER}/stations', 'altimetry_stations')
    print(f"Started stations export ({len(stations)} points)")

    master = pd.read_csv(MASTER_CSV)
    master_keys = obs_key(master)

    if os.path.exists(GEE_LEDGER) and asset_exists(target):
        done_keys, rebuild = set(pd.read_csv(GEE_LEDGER)['key']), False
    else:
        done_keys, rebuild = set(), True       # first run, or saved rows were changed

    pending = master if rebuild else master[~master_keys.isin(done_keys)]
    print(f"Observations to upload: {len(pending)}"
          + (" (full rebuild)" if rebuild else " (new only)"))

    if pending.empty:
        wait_for([st_task])
        print("Nothing new for GEE; stations layer refreshed.")
    else:
        # 1. upload ONLY the new rows as temporary parts
        n_parts = math.ceil(len(pending) / ROWS_PER_PART)
        part_ids, tasks = [], []
        for i in range(n_parts):
            chunk = pending.iloc[i * ROWS_PER_PART:(i + 1) * ROWS_PER_PART]
            pid = f'{ASSET_FOLDER}/merged_obs_part_{i:03d}'
            tasks.append(start_export(df_to_fc(chunk, date_col='date'), pid, f'merged_obs_part_{i:03d}'))
            part_ids.append(pid)
        print(f"Started {n_parts} observation export(s) of up to {ROWS_PER_PART} rows")
        states = wait_for(tasks + [st_task])
        if states[-1] == 'COMPLETED':
            make_public(f'{ASSET_FOLDER}/stations')

        if all(s == 'COMPLETED' for s in states[:-1]):
            # 2. merge INSIDE GEE: current merged_observations + new parts
            new_fc = ee.FeatureCollection([ee.FeatureCollection(p) for p in part_ids]).flatten()
            combined = new_fc if rebuild else ee.FeatureCollection(target).merge(new_fc)
            staging = f'{target}_{RUN_STAMP}'
            t = start_export(combined, staging, 'merged_observations')

            if wait_for([t])[0] == 'COMPLETED':
                # 3. swap: current table -> _old (backup), staging -> merged_observations
                if asset_exists(target):
                    if asset_exists(backup):
                        ee.data.deleteAsset(backup)
                    ee.data.renameAsset(target, backup)
                ee.data.renameAsset(staging, target)
                make_public(target)
                for p in part_ids:
                    ee.data.deleteAsset(p)
                uploaded = set(master_keys) if rebuild else done_keys | set(obs_key(pending))
                pd.DataFrame({'key': sorted(uploaded)}).to_csv(GEE_LEDGER, index=False)
                print(f"Done -> {target} (+{len(pending)} observations, {len(uploaded)} in total). "
                      f"Previous version kept as {backup}.")
            else:
                if asset_exists(staging):
                    ee.data.deleteAsset(staging)
                print("Merge failed; merged_observations is unchanged and the rows retry next run.")
        else:
            for p in part_ids:
                if asset_exists(p):
                    ee.data.deleteAsset(p)
            print("Some uploads failed; merged_observations is unchanged and the rows retry next run.")
