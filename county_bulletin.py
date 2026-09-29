# -*- coding: utf-8 -*-
"""
SOUTH SUDAN COUNTY HYDRO-CLIMATE BULLETIN (admin2) - Google Colab.

PART A  Antecedent conditions per county (Google Earth Engine)
        Rainfall           : GSMaP v8 operational, gauge-corrected (hours of latency), vs same window 2001-2025
        Soil / ET / runoff : NASA SMAP L4 (~3 days latency), vs same window 2015-2025
        7/15/30-day windows ending on the last complete day of both products; percentiles, medians,
        anomalies, root-zone z-score and class, and the root-zone soil water deficit in mm.
        (ERA5-Land was dropped: in 2026 it showed only 15-55% of the rainfall seen by GSMaP.)
PART B  Wet / dry spell outlook with certainty (ECMWF ENS open data, up to 51 members, 15 days)
PART C  Combined bulletin with graded advisory flags: Excel + CSV, and the GEE county asset.

Soil wetness is judged by the root-zone z-score (standard deviations from the 2015-2025 mean for the
same dates). With only ~10 comparison years, which include the exceptional flood years 2019-2022 and
2024, a z-score is steadier than a percentile.
"""

import os
import re
import sys
import time
import datetime
import subprocess

subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'ecmwf-opendata', 'cfgrib', 'eccodes',
                'xarray', 'geopandas', 'shapely', 'openpyxl'], check=False)

import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
from shapely.geometry import shape, mapping
import ee

# =========================================================================== #
# SETTINGS                                                                    #
# =========================================================================== #
PROJECT_ID = 'sudan-1575919084043'
AOI_ASSET = 'users/penuelabi/ssd_payam'
ADM2_FIELD = 'ADM2_EN'
ADM1_FIELD = 'ADM1_EN'
OUT_DIR = os.environ.get('BULLETIN_OUT_DIR', '/content/drive/MyDrive/colab_waterlevel/county_bulletin/')
TMP_DIR = os.environ.get('BULLETIN_TMP_DIR', '/content')
COUNTY_CACHE = os.path.join(OUT_DIR, 'counties_dissolved.geojson')

# --- Part A: antecedent conditions ---
RUN_ANTECEDENT = True
GSMAP_ID = 'JAXA/GPM_L3/GSMaP/v8/operational'
GSMAP_BAND = 'hourlyPrecipRateGC'                 # gauge-corrected; 'hourlyPrecipRate' = satellite only
SMAP_IDS = ['NASA/SMAP/SPL4SMGP/008', 'NASA/SMAP/SPL4SMGP/007']   # first one found is used
RAIN_CLIM_YEARS = (2001, 2025)                    # comparison years for rainfall
LAND_CLIM_YEARS = (2015, 2025)                    # comparison years for SMAP (record starts 2015)
WINDOWS = [7, 15, 30]
SCALE = 5000

# Soil classes from the root-zone z-score
Z_VERY_DRY = -1.5
Z_DRY = -0.75
Z_WET = 0.75
Z_VERY_WET = 1.5

# --- Part B: ensemble spell outlook ---
RUN_OUTLOOK = True
ENS_SOURCES = ['ecmwf', 'aws', 'azure']
BBOX = [23.0, 3.0, 36.5, 13.0]
WET_DAY_MM = 1.0                  # a grid cell with at least this much rain is wet
WET_AREA_FRACTION = 0.5           # a county day is wet if this share of its cells is wet
DRY_SPELL_DAYS = 7
WET_SPELL_DAYS = 3
HEAVY_7D_MM = 50.0
P_LIKELY_WET = 0.60
P_LIKELY_DRY = 0.25
LEAD_SKILL = [(5, 'good'), (10, 'moderate'), (15, 'low - tendency only')]

# --- Part C: advisory thresholds (agree these with extension / livestock partners) ---
ADV_HEAVY_P = 0.30                # heavy-rain probability for a watch
ADV_DRY_P = 0.60                  # dry-spell probability for a dry-spell flag
ADV_WETSPELL_P = 0.60             # wet-spell probability for wet-spell messages
ADV_WET_SOIL_Z = Z_WET            # soil counted as wet (waterlogging / flood watch)
ADV_DRY_SOIL_Z = Z_DRY            # soil counted as dry (dry-spell stress)
DEFICIT_Z = -1.0                  # soil counted as in deficit
DEFICIT_MIN_MM = 20               # smallest deficit (mm, top 1 m) worth flagging
RECOVERY_SEVERE = 0.25            # 2-week rain covers < 25% of the deficit -> severe
RECOVERY_MODERATE = 0.75          # 25-75% -> moderate; >= 75% -> easing

EXPORT_TO_GEE = True
COUNTY_ASSET = f'projects/{PROJECT_ID}/assets/altimetry/county_hydroclimate'

# =========================================================================== #
# SETUP                                                                       #
# =========================================================================== #
try:
    from google.colab import drive
    if not os.path.exists('/content/drive/MyDrive'):
        drive.mount('/content/drive')
except Exception:
    pass
os.makedirs(OUT_DIR, exist_ok=True)

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

TODAY = datetime.date.today()


def get_info(obj, tries=3):
    for k in range(tries):
        try:
            return obj.getInfo()
        except Exception as e:
            if k == tries - 1:
                raise
            print(f"  GEE request failed ({str(e)[:100]}); retrying")
            time.sleep(15)


def pclass(p):
    """Class from a percentile (used for rainfall, runoff, ET)."""
    if pd.isna(p):
        return 'no data'
    if p >= 90:
        return 'very wet'
    if p >= 67:
        return 'wet'
    if p >= 33:
        return 'near normal'
    if p >= 10:
        return 'dry'
    return 'very dry'


def zclass(z):
    """Class from a z-score (used for soil moisture)."""
    if pd.isna(z):
        return 'no data'
    if z <= Z_VERY_DRY:
        return 'very dry'
    if z <= Z_DRY:
        return 'dry'
    if z < Z_WET:
        return 'near normal'
    if z < Z_VERY_WET:
        return 'wet'
    return 'very wet'


# =========================================================================== #
# COUNTIES                                                                    #
# =========================================================================== #
print("=== COUNTIES ===")
aoi = ee.FeatureCollection(AOI_ASSET)
names_ee = aoi.aggregate_array(ADM2_FIELD).distinct().sort()
COUNTIES = get_info(names_ee)

counties = None
if os.path.exists(COUNTY_CACHE):
    counties = gpd.read_file(COUNTY_CACHE)
    if sorted(counties['county']) != sorted(COUNTIES):
        print("County list changed in the AOI asset; rebuilding the cache.")
        counties = None
if counties is None:
    print(f"Dissolving payams into {len(COUNTIES)} counties (first run only)...")
    fc = ee.FeatureCollection(names_ee.map(lambda n: ee.Feature(
        aoi.filter(ee.Filter.eq(ADM2_FIELD, n)).geometry(1000).dissolve(1000).simplify(1000),
        {'county': n, 'state': ee.Feature(aoi.filter(ee.Filter.eq(ADM2_FIELD, n)).first()).get(ADM1_FIELD)})))
    feats = get_info(fc)['features']
    counties = gpd.GeoDataFrame(
        {'county': [f['properties']['county'] for f in feats],
         'state': [f['properties'].get('state') for f in feats]},
        geometry=[shape(f['geometry']) for f in feats], crs=4326)
    counties.to_file(COUNTY_CACHE, driver='GeoJSON')
print(f"{len(counties)} counties in {counties['state'].nunique()} states")

# =========================================================================== #
# PART A - ANTECEDENT CONDITIONS (GSMaP rainfall + SMAP L4 soil/ET/runoff)    #
# =========================================================================== #
ante, ANTE_END, DATA_SOURCE, SMAP_ID = None, None, None, None
if RUN_ANTECEDENT:
    print("\n=== PART A: ANTECEDENT CONDITIONS (GSMaP + SMAP L4) ===")
    aoi_id = aoi.map(lambda f: f.set('cid', names_ee.indexOf(f.get(ADM2_FIELD))))
    CID = aoi_id.reduceToImage(['cid'], ee.Reducer.first()).rename('cid').toInt()
    REGION = aoi.geometry(1000).bounds(1000)

    RAIN = ee.ImageCollection(GSMAP_ID).select(GSMAP_BAND)
    SMAP = None
    for sid in SMAP_IDS:
        try:
            if get_info(ee.ImageCollection(sid).limit(1).size()) > 0:
                SMAP, SMAP_ID = ee.ImageCollection(sid), sid
                break
        except Exception:
            pass
    if SMAP is None:
        raise SystemExit(f"No SMAP L4 collection found among {SMAP_IDS}; check the Earth Engine catalog.")
    DATA_SOURCE = f"rain: GSMaP v8 {GSMAP_BAND}; soil/ET/runoff: {SMAP_ID.split('/')[-2]} v{SMAP_ID.split('/')[-1]}"
    print(f"Using {DATA_SOURCE}")

    SM_BANDS = ['sm_surface', 'sm_rootzone']
    FLUX_BANDS = ['land_evapotranspiration_flux', 'overland_runoff_flux', 'baseflow_flux']   # kg m-2 s-1 = mm/s
    RAIN_VARS = [f'rain_{d}d_mm' for d in WINDOWS]
    LAND_VARS = []
    for d in WINDOWS:
        LAND_VARS += [f'et_{d}d_mm', f'surf_runoff_{d}d_mm', f'runoff_{d}d_mm']
    LAND_VARS += ['sm_surface', 'sm_rootzone']

    def end_ee(end_date):
        return ee.Date(end_date.strftime('%Y-%m-%d')).advance(1, 'day')

    def rain_image(end_date):
        e = end_ee(end_date)
        return ee.Image.cat([RAIN.filterDate(e.advance(-d, 'day'), e).sum().rename(f'rain_{d}d_mm')
                             for d in WINDOWS]).toFloat()        # mm/h summed over hourly steps = mm

    def land_image(end_date):
        e = end_ee(end_date)
        bands = []
        for d in WINDOWS:
            # mean flux over the window x seconds in the window = total mm (robust to missing time steps)
            flux = SMAP.filterDate(e.advance(-d, 'day'), e).select(FLUX_BANDS).mean().multiply(86400 * d)
            bands += [flux.select('land_evapotranspiration_flux').rename(f'et_{d}d_mm'),
                      flux.select('overland_runoff_flux').rename(f'surf_runoff_{d}d_mm'),
                      flux.select('overland_runoff_flux').add(flux.select('baseflow_flux')).rename(f'runoff_{d}d_mm')]
        sm = SMAP.filterDate(e.advance(-3, 'day'), e).select(SM_BANDS).mean()
        bands += [sm.select('sm_surface'), sm.select('sm_rootzone')]
        return ee.Image.cat(bands).select(LAND_VARS).toFloat()

    def county_means(img, var_list):
        nb = len(var_list)
        red = ee.Reducer.mean().repeat(nb).group(groupField=nb, groupName='cid')
        res = img.addBands(CID).reduceRegion(reducer=red, geometry=REGION, scale=SCALE,
                                             maxPixels=1e10, tileScale=4)
        rows = {}
        for g in get_info(res.get('groups')):
            cid = int(g['cid'])
            if 0 <= cid < len(COUNTIES):
                rows[COUNTIES[cid]] = dict(zip(var_list, g['mean']))
        return pd.DataFrame.from_dict(rows, orient='index').reindex(COUNTIES).apply(pd.to_numeric, errors='coerce')

    def same_day(year, d):
        try:
            return d.replace(year=year)
        except ValueError:
            return d.replace(year=year, day=28)

    def last_full_day(col, step_hours):
        ms = get_info(col.filterDate((TODAY - datetime.timedelta(days=15)).isoformat(),
                                     (TODAY + datetime.timedelta(days=1)).isoformat())
                      .aggregate_max('system:time_start'))
        t = pd.Timestamp(ms, unit='ms')
        return ((t + pd.Timedelta(hours=step_hours)).floor('D') - pd.Timedelta(days=1)).date()

    gs_last, sm_last = last_full_day(RAIN, 1), last_full_day(SMAP, 3)
    ANTE_END = min(gs_last, sm_last)
    print(f"Last complete day: GSMaP {gs_last}, SMAP {sm_last} -> windows end on {ANTE_END}")

    e = end_ee(ANTE_END)
    n_gs = get_info(RAIN.filterDate(e.advance(-30, 'day'), e).size())
    n_sm = get_info(SMAP.filterDate(e.advance(-30, 'day'), e).size())
    print(f"30-day window: {n_gs}/720 GSMaP hours, {n_sm}/240 SMAP time steps")

    def frame(end_date, with_rain, with_land):
        parts = []
        if with_rain:
            parts.append(county_means(rain_image(end_date), RAIN_VARS))
        if with_land:
            parts.append(county_means(land_image(end_date), LAND_VARS))
        df = pd.concat(parts, axis=1)
        if with_rain and with_land:
            df['wb_30d_mm'] = df['rain_30d_mm'] - df['et_30d_mm'] - df['runoff_30d_mm']
        return df

    now = frame(ANTE_END, True, True)
    print(now[['rain_30d_mm', 'sm_rootzone', 'sm_surface', 'et_30d_mm', 'runoff_30d_mm']].describe().round(3))
    print("Sanity check: late-season 30-day ET is usually tens of mm to ~150 mm; root-zone soil ~0.1-0.45 m3/m3.")

    clim = {}
    for y in range(min(RAIN_CLIM_YEARS[0], LAND_CLIM_YEARS[0]), max(RAIN_CLIM_YEARS[1], LAND_CLIM_YEARS[1]) + 1):
        if y == ANTE_END.year:
            continue
        d_y = same_day(y, ANTE_END)
        ey = end_ee(d_y)
        use_rain = RAIN_CLIM_YEARS[0] <= y <= RAIN_CLIM_YEARS[1] and \
            get_info(RAIN.filterDate(ey.advance(-30, 'day'), ey).size()) > 0
        use_land = LAND_CLIM_YEARS[0] <= y <= LAND_CLIM_YEARS[1] and \
            get_info(SMAP.filterDate(ey.advance(-30, 'day'), ey).size()) > 0
        if not (use_rain or use_land):
            print(f"  {y}: no data, skipped")
            continue
        clim[y] = frame(d_y, use_rain, use_land)
        print(f"  comparison year {y} done ({'rain ' if use_rain else ''}{'land' if use_land else ''})")
    cube = pd.concat(clim, names=['year', 'county'])

    ante = now.copy()
    for v in RAIN_VARS + LAND_VARS + ['wb_30d_mm']:
        if v not in cube:
            continue
        hist = cube[v].unstack('year').reindex(now.index)
        x = now[v]
        n = hist.notna().sum(axis=1)
        below = hist.lt(x, axis=0).sum(axis=1)
        equal = hist.eq(x, axis=0).sum(axis=1)
        ante[f'{v}_pctile'] = (100 * (below + 0.5 * equal) / n.replace(0, np.nan)).where(x.notna())
        ante[f'{v}_median'] = hist.median(axis=1)
        ante[f'{v}_anom'] = x - hist.median(axis=1)
    for d in WINDOWS:
        mean_rain = cube[f'rain_{d}d_mm'].unstack('year').reindex(now.index).mean(axis=1)
        ante[f'rain_{d}d_pct_of_normal'] = 100 * now[f'rain_{d}d_mm'] / mean_rain.replace(0, np.nan)

    # Root-zone z-score and soil class (steadier than a percentile with ~10 comparison years)
    sm_hist = cube['sm_rootzone'].unstack('year').reindex(now.index)
    sm_sd = sm_hist.std(axis=1).replace(0, np.nan)
    ante['sm_rootzone_z'] = (now['sm_rootzone'] - sm_hist.mean(axis=1)) / sm_sd
    ante['sm_rootzone_nyears'] = sm_hist.notna().sum(axis=1)
    ante['soil_rootzone_class'] = ante['sm_rootzone_z'].map(zclass)
    ante['soil_surface_class'] = ante['sm_surface_pctile'].map(pclass)

    # Soil water below the seasonal median in the top 1 m (mm): 0.01 m3/m3 over 1 m = 10 mm of water
    ante['soil_deficit_mm'] = ((ante['sm_rootzone_median'] - ante['sm_rootzone']) * 1000).clip(lower=0)

    ante['rain_30d_class'] = ante['rain_30d_mm_pctile'].map(pclass)
    ante['runoff_30d_class'] = ante['runoff_30d_mm_pctile'].map(pclass)
    ante['et_30d_class'] = ante['et_30d_mm_pctile'].map(pclass)
    ante['antecedent_summary'] = [
        f"Root-zone soil {r.soil_rootzone_class} (z {r.sm_rootzone_z:+.1f}, "
        f"{r.soil_deficit_mm:.0f} mm below median); 30-day rain {r.rain_30d_mm:.0f} mm = "
        f"{r.rain_30d_pct_of_normal:.0f}% of normal; runoff {r.runoff_30d_class}; "
        f"ET {r.et_30d_mm:.0f} mm ({r.et_30d_class})"
        if pd.notna(r.sm_rootzone_z) else 'no data'
        for r in ante.itertuples()]
    ante.insert(0, 'data_source', DATA_SOURCE)
    ante.insert(0, 'data_end_date', ANTE_END.isoformat())
    ante = ante.rename_axis('county').reset_index()
    print("Root-zone soil classes (z-score): " +
          ', '.join(f"{k} {v}" for k, v in ante['soil_rootzone_class'].value_counts().items()))
    print("30-day rain classes:              " +
          ', '.join(f"{k} {v}" for k, v in ante['rain_30d_class'].value_counts().items()))

# =========================================================================== #
# PART B - WET / DRY SPELL OUTLOOK WITH CERTAINTY (ECMWF ENS)                 #
# =========================================================================== #
outlook, RUN_UTC, VALID = None, None, []
P_DRY = f'p_dry_spell_{DRY_SPELL_DAYS}d_in_15d'
P_WSP = f'p_wet_spell_{WET_SPELL_DAYS}d_week1'
P_HEAVY = f'p_heavy_{int(HEAVY_7D_MM)}mm_week1'
if RUN_OUTLOOK:
    print("\n=== PART B: SPELL OUTLOOK (ECMWF ENS) ===")
    try:
        from ecmwf.opendata import Client
        STEPS = list(range(24, 361, 24))                           # rainfall at step 0 is not published
        client, run = None, None
        for src in ENS_SOURCES:
            try:
                client = Client(source=src)
                run = client.latest(stream='enfo', type='pf', param='tp', step=360, time=0)
                print(f"Source: {src}")
                break
            except Exception as e:
                print(f"  source {src} unavailable ({str(e)[:80]})")
        if run is None:
            raise RuntimeError('no ENS source available')
        RUN_UTC = f"{run:%Y-%m-%d %H}"
        print(f"ENS run: {RUN_UTC} UTC")

        files = {}
        for typ in ('cf', 'pf'):                                   # control is optional
            target = os.path.join(TMP_DIR, f'ens_tp_{typ}.grib2')
            try:
                client.retrieve(date=run.strftime('%Y-%m-%d'), time=0, stream='enfo', type=typ,
                                param='tp', step=STEPS, target=target)
                files[typ] = target
            except Exception as e:
                print(f"  {typ} not available ({str(e)[:80]}); continuing without it")
        if 'pf' not in files:
            raise RuntimeError('perturbed members not available')

        def load(path):
            tp = xr.open_dataset(path, engine='cfgrib', backend_kwargs={'indexpath': ''})['tp']
            if 'number' not in tp.dims:
                n = int(tp.coords['number'].values) if 'number' in tp.coords else 0
                tp = tp.drop_vars('number', errors='ignore').expand_dims(number=[n])
            return tp

        tp = xr.concat([load(files[t]) for t in ('cf', 'pf') if t in files], dim='number')
        tp0 = xr.zeros_like(tp.isel(step=0)).assign_coords(step=np.timedelta64(0, 'h'))
        tp = xr.concat([tp0, tp], dim='step')                      # add the zero at step 0
        tp = tp.sortby('latitude', ascending=False)
        tp = tp.sel(latitude=slice(BBOX[3], BBOX[1]), longitude=slice(BBOX[0], BBOX[2]))
        daily = (tp.diff('step') * 1000).clip(min=0).transpose('number', 'step', 'latitude', 'longitude')
        N_DAYS = daily.sizes['step']
        VALID = [(run + datetime.timedelta(days=i)).date() for i in range(N_DAYS)]
        arr = daily.values
        print(f"{arr.shape[0]} members x {N_DAYS} days on a {arr.shape[2]} x {arr.shape[3]} grid")

        lats, lons = daily.latitude.values, daily.longitude.values
        LON, LAT = np.meshgrid(lons, lats)
        pts = gpd.GeoDataFrame({'iy': np.repeat(np.arange(len(lats)), len(lons)),
                                'ix': np.tile(np.arange(len(lons)), len(lats))},
                               geometry=gpd.points_from_xy(LON.ravel(), LAT.ravel()), crs=4326)
        joined = gpd.sjoin(pts, counties[['county', 'geometry']], predicate='within')
        cells = {c: (g.iy.to_numpy(), g.ix.to_numpy()) for c, g in joined.groupby('county')}
        for r in counties.itertuples():
            if r.county not in cells:
                cen = r.geometry.representative_point()
                cells[r.county] = (np.array([np.abs(lats - cen.y).argmin()]),
                                   np.array([np.abs(lons - cen.x).argmin()]))

        def longest_run(b):
            best = cur = 0
            for v in b:
                cur = cur + 1 if v else 0
                best = max(best, cur)
            return best

        def lead_skill(i):
            for limit, label in LEAD_SKILL:
                if i < limit:
                    return label
            return LEAD_SKILL[-1][1]

        def windows_text(p_wet):
            labels = ['likely wet' if p >= P_LIKELY_WET else 'likely dry' if p <= P_LIKELY_DRY else 'uncertain'
                      for p in p_wet]
            parts, i = [], 0
            while i < len(labels):
                j = i
                while j + 1 < len(labels) and labels[j + 1] == labels[i]:
                    j += 1
                agree = np.mean([max(p, 1 - p) for p in p_wet[i:j + 1]])
                conf = 'high' if agree >= 0.8 else 'medium' if agree >= 0.65 else 'low'
                if j >= 7 and conf == 'high':                      # beyond a week, cap confidence
                    conf = 'medium'
                span = f"{VALID[i]:%d %b}" if i == j else f"{VALID[i]:%d %b}-{VALID[j]:%d %b}"
                parts.append(f"{span}: {labels[i]}" + ('' if labels[i] == 'uncertain' else f" ({conf})"))
                i = j + 1
            return '; '.join(parts)

        rows, log = [], []
        for county, (iy, ix) in sorted(cells.items()):
            cellrain = arr[:, :, iy, ix]                          # members x days x cells
            r = cellrain.mean(axis=2)                             # county-mean rain (for totals)
            wet = (cellrain >= WET_DAY_MM).mean(axis=2) >= WET_AREA_FRACTION
            p_wet = wet.mean(axis=0)
            w1, w2 = r[:, :7].sum(axis=1), r[:, 7:14].sum(axis=1)
            m = len(r)
            rec = {
                'county': county, 'run_utc': RUN_UTC, 'n_members': m,
                'week1_rain_median_mm': np.median(w1), 'week1_rain_p20_mm': np.percentile(w1, 20),
                'week1_rain_p80_mm': np.percentile(w1, 80),
                'week2_rain_median_mm': np.median(w2), 'week2_rain_p20_mm': np.percentile(w2, 20),
                'week2_rain_p80_mm': np.percentile(w2, 80),
                P_DRY: np.mean([longest_run(~wet[k]) >= DRY_SPELL_DAYS for k in range(m)]),
                P_WSP: np.mean([longest_run(wet[k, :7]) >= WET_SPELL_DAYS for k in range(m)]),
                P_HEAVY: np.mean(w1 >= HEAVY_7D_MM),
                'spell_windows': windows_text(p_wet),
            }
            for i, p in enumerate(p_wet):
                rec[f'p_wet_{VALID[i]:%m%d}'] = p
                log.append({'run_utc': RUN_UTC, 'county': county, 'valid_date': VALID[i].isoformat(),
                            'lead_day': i + 1, 'p_wet': p, 'median_mm': np.median(r[:, i]),
                            'p20_mm': np.percentile(r[:, i], 20), 'p80_mm': np.percentile(r[:, i], 80),
                            'lead_skill': lead_skill(i)})
            rows.append(rec)
        outlook = pd.DataFrame(rows)

        log_path = os.path.join(OUT_DIR, 'forecast_log_ens.csv')   # for verification against observed rain
        log_df = pd.DataFrame(log)
        if os.path.exists(log_path):
            old = pd.read_csv(log_path)
            log_df = pd.concat([d for d in (old[old.run_utc != RUN_UTC], log_df) if len(d)], ignore_index=True)
        log_df.to_csv(log_path, index=False)
        print(f"Forecast log: {len(log_df)} rows -> {log_path}")
    except Exception as e:
        print(f"Spell outlook failed ({type(e).__name__}: {e}); the bulletin continues with antecedent data only.")
        outlook, RUN_UTC = None, None

# =========================================================================== #
# PART C - COMBINED BULLETIN + GRADED ADVISORY FLAGS                          #
# =========================================================================== #
print("\n=== PART C: BULLETIN ===")
bulletin = counties[['county', 'state']].copy()
if ante is not None:
    bulletin = bulletin.merge(ante, on='county', how='left')
if outlook is not None:
    bulletin = bulletin.merge(outlook, on='county', how='left')


def advisory(r):
    if ante is None or outlook is None or pd.isna(r.get('sm_rootzone_z')) or pd.isna(r.get(P_DRY)):
        return 'not available (needs both antecedent and outlook data)'
    z, soil_cls = r['sm_rootzone_z'], r['soil_rootzone_class']
    p_dry, p_heavy, p_wsp = r[P_DRY], r[P_HEAVY], r[P_WSP]
    w1, w2 = r['week1_rain_median_mm'], r['week2_rain_median_mm']
    deficit = r.get('soil_deficit_mm', np.nan)
    rain30 = r.get('rain_30d_pct_of_normal', np.nan)
    has_deficit = z <= DEFICIT_Z and pd.notna(deficit) and deficit >= DEFICIT_MIN_MM
    recovery = (w1 + w2) / deficit if has_deficit else np.nan    # share of the deficit the rain could refill
    flags = []

    # Heavy rain
    if p_heavy >= ADV_HEAVY_P and z >= ADV_WET_SOIL_Z:
        flags.append(f'FLOOD/WATERLOGGING WATCH: {p_heavy:.0%} chance of >= {HEAVY_7D_MM:.0f} mm in week 1 '
                     'on already wet soils; move livestock and stored produce off low ground')
    elif p_heavy >= ADV_HEAVY_P:
        flags.append(f'Heavy rain possible ({p_heavy:.0%} chance of >= {HEAVY_7D_MM:.0f} mm in week 1); '
                     'watch low-lying areas and roads')

    # Soil deficit, graded by how much of it the next 2 weeks of rain can refill
    if has_deficit:
        detail = (f'soil about {deficit:.0f} mm below median in the top metre (30-day rain {rain30:.0f}% of '
                  f'normal); ~{w1 + w2:.0f} mm expected over 2 weeks = {min(recovery, 9.99):.0%} of the deficit')
        if recovery < RECOVERY_SEVERE:
            flags.append('CROP/PASTURE STRESS (severe): ' + detail + '. Protect water sources, plan livestock '
                         'watering and grazing moves, favour short-cycle and drought-tolerant crops')
        elif recovery < RECOVERY_MODERATE:
            flags.append('Soil moisture deficit (moderate): ' + detail + '. Monitor crops and pasture; '
                         'delay new planting until soils recover')
        else:
            flags.append('Soil moisture deficit easing: ' + detail + '. Soils should recover if the rain arrives')

    # Dry spell
    if p_dry >= ADV_DRY_P and z <= ADV_DRY_SOIL_Z and not has_deficit:
        flags.append(f'CROP/PASTURE STRESS: {p_dry:.0%} chance of a {DRY_SPELL_DAYS}-day dry spell on dry soils')
    elif p_dry >= ADV_DRY_P:
        flags.append(f'Dry spell likely ({p_dry:.0%}): suitable for weeding, harvesting and drying; delay planting')
    elif p_dry >= 0.3 and z <= ADV_DRY_SOIL_Z:
        flags.append(f'Dry spell possible ({p_dry:.0%}) on dry soils: monitor crops and pasture')

    # Wet spell (only when it adds information beyond the deficit message)
    if p_wsp >= ADV_WETSPELL_P and not has_deficit:
        if z <= ADV_DRY_SOIL_Z:
            flags.append(f'Wet spell likely ({p_wsp:.0%}); soils should begin to recover')
        elif z < ADV_WET_SOIL_Z:
            flags.append(f'Wet spell likely ({p_wsp:.0%}) with moist soils: favourable for planting and top-dressing')
        else:
            flags.append(f'Wet spell likely ({p_wsp:.0%}) on saturated soils: waterlogging risk in low ground')

    if not flags:
        return f'No significant change expected: {soil_cls} soils, about {w1:.0f} mm of rain in week 1'
    return ' | '.join(flags)


bulletin['advisory_flags'] = bulletin.apply(advisory, axis=1)
bulletin = bulletin.sort_values(['state', 'county']).reset_index(drop=True)

KEY_COLS = ['state', 'county', 'data_end_date', 'data_source', 'soil_rootzone_class', 'sm_rootzone_z',
            'sm_rootzone_pctile', 'soil_deficit_mm', 'rain_30d_mm', 'rain_30d_pct_of_normal', 'rain_30d_class',
            'runoff_30d_class', 'et_30d_mm', 'wb_30d_mm', 'run_utc', 'n_members', 'week1_rain_median_mm',
            'week1_rain_p20_mm', 'week1_rain_p80_mm', 'week2_rain_median_mm', P_DRY, P_WSP, P_HEAVY,
            'spell_windows', 'advisory_flags']
key = bulletin[[c for c in KEY_COLS if c in bulletin.columns]]

notes = pd.DataFrame([
    ('rainfall source', f'GSMaP v8 operational, {GSMAP_BAND} (gauge-corrected), summed from hourly rates; '
                        f'percentiles vs the same window in {RAIN_CLIM_YEARS[0]}-{RAIN_CLIM_YEARS[1]}'),
    ('soil / ET / runoff source', f'NASA SMAP L4 ({SMAP_ID or "n/a"}): satellite soil moisture assimilated into '
                                 f'a land model; compared with the same window in {LAND_CLIM_YEARS[0]}-{LAND_CLIM_YEARS[1]}'),
    ('why not ERA5-Land', 'In 2026, ERA5-Land in Earth Engine showed only 15-55% of the rainfall seen by GSMaP, '
                          'which made soils appear record-dry everywhere.'),
    ('windows', f'{WINDOWS} days ending on data_end_date: the last day complete in both GSMaP and SMAP'),
    ('runoff_* / surf_runoff_*', 'SMAP L4 overland (+ baseflow) runoff generated locally (mm); NOT river flow'),
    ('et_*_mm', 'SMAP L4 land evapotranspiration (mm)'),
    ('wb_30d_mm', '30-day rain - ET - runoff (mm): positive = storage building up'),
    ('sm_surface / sm_rootzone', 'SMAP L4 soil moisture, 0-5 cm / 0-100 cm (m3/m3), mean of last 3 days'),
    ('sm_rootzone_z', 'Root-zone soil moisture minus the 2015-2025 mean for this date, in standard deviations'),
    ('soil_rootzone_class', f'From sm_rootzone_z: very dry <= {Z_VERY_DRY}, dry <= {Z_DRY}, near normal < {Z_WET}, '
                            f'wet < {Z_VERY_WET}, else very wet. The comparison years include the exceptional flood '
                            'years 2019-2022 and 2024, so "dry" means drier than a wet decade.'),
    ('soil_deficit_mm', 'Root-zone soil water below the median for this date, top 1 m (mm)'),
    ('rain / runoff / ET classes', 'From percentiles: very dry <10, dry 10-33, near normal 33-67, wet 67-90, very wet >=90'),
    ('Part B source', 'ECMWF ENS open data, 00 UTC run, control (if available) + 50 members, 15 days'),
    ('wet day', f'At least {WET_AREA_FRACTION:.0%} of the county\'s 0.25 deg cells get >= {WET_DAY_MM} mm in 24 h '
                '(00-24 UTC = 02:00-02:00 South Sudan time)'),
    ('p_dry_spell / p_wet_spell / p_heavy', 'Share of ensemble members showing the event'),
    ('spell_windows', 'Likely wet / likely dry / uncertain, with confidence from member agreement'),
    ('certainty caveat', 'Member agreement is not verified accuracy; forecast_log_ens.csv is kept for verification.'),
    ('advisory rules', f'Deficit when root-zone z <= {DEFICIT_Z} and >= {DEFICIT_MIN_MM} mm below median; graded by '
                       f'2-week expected rain / deficit: < {RECOVERY_SEVERE:.0%} severe (STRESS), < '
                       f'{RECOVERY_MODERATE:.0%} moderate, otherwise easing. Wet soil for watches: z >= {ADV_WET_SOIL_Z}. '
                       'Evaporation is ignored, so grading errs towards recovery. Thresholds are provisional.'),
], columns=['item', 'definition'])

stamp = (RUN_UTC[:10].replace('-', '') if RUN_UTC else (ANTE_END or TODAY).strftime('%Y%m%d'))
xlsx_path = os.path.join(OUT_DIR, f'county_bulletin_{stamp}.xlsx')
csv_path = os.path.join(OUT_DIR, f'county_bulletin_{stamp}.csv')
bulletin.to_csv(csv_path, index=False)
with pd.ExcelWriter(xlsx_path, engine='openpyxl') as xw:
    key.to_excel(xw, sheet_name='Bulletin', index=False)
    if ante is not None:
        ante.merge(counties[['county', 'state']], on='county', how='left') \
            .to_excel(xw, sheet_name='Antecedent_full', index=False)
    if outlook is not None:
        outlook.merge(counties[['county', 'state']], on='county', how='left') \
            .to_excel(xw, sheet_name='Outlook_daily_probs', index=False)
    notes.to_excel(xw, sheet_name='Notes', index=False)
# Fixed-name copies: a service account can update existing Drive files but cannot create new ones,
# so the automated run refreshes these "latest" files (dated copies are still written to OUT_DIR).
import shutil
shutil.copyfile(csv_path, os.path.join(OUT_DIR, 'county_bulletin_latest.csv'))
shutil.copyfile(xlsx_path, os.path.join(OUT_DIR, 'county_bulletin_latest.xlsx'))
print(f"-> {xlsx_path}\n-> {csv_path}\n-> county_bulletin_latest.(csv|xlsx)")

show = [c for c in ['state', 'county', 'soil_rootzone_class', 'sm_rootzone_z', 'soil_deficit_mm',
                    'rain_30d_pct_of_normal', 'week1_rain_median_mm'] if c in bulletin]
print(bulletin[show].round(1).to_string(index=False))

level = bulletin['advisory_flags'].str.extract(
    r'(STRESS \(severe\)|deficit \(moderate\)|deficit easing|WATCH|No significant|not available)')[0]
level = level.fillna('other (wet/dry spell or heavy-rain message)')
print("\nAdvisory levels:")
print(level.value_counts().rename_axis('level').to_string())

# =========================================================================== #
# COUNTY LAYER FOR THE GEE APP                                                #
# =========================================================================== #
if EXPORT_TO_GEE:
    def clean(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return v.item() if hasattr(v, 'item') else v

    geo = counties.set_index('county').geometry
    feats = []
    for rec in bulletin.to_dict('records'):
        props = {re.sub(r'[^0-9A-Za-z_]+', '_', k): clean(v) for k, v in rec.items()}
        props = {k: v for k, v in props.items() if v is not None}
        feats.append(ee.Feature(ee.Geometry(mapping(geo[rec['county']])), props))
    try:
        ee.data.deleteAsset(COUNTY_ASSET)
    except Exception:
        pass
    task = ee.batch.Export.table.toAsset(collection=ee.FeatureCollection(feats),
                                         description='county_hydroclimate', assetId=COUNTY_ASSET)
    task.start()
    print(f"Started export -> {COUNTY_ASSET} (check the Tasks tab in the Code Editor)")
    # wait for the export, then re-apply public read access (the delete + re-export reset it)
    while task.status()['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED'):
        time.sleep(15)
    _st = task.status()
    if _st['state'] == 'COMPLETED':
        make_public(COUNTY_ASSET)
    else:
        print(f"  county asset export {_st['state']}: {_st.get('error_message', '')}")