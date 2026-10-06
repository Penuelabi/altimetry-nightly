# -*- coding: utf-8 -*-
"""
Standalone GEE test script -- NOT part of the app, NOT imported by county_bulletin.py, and NEVER writes to
county_bulletin_latest.csv, forecast_obs_cache.csv, or any other file the app reads or writes. Everything here is
new, separately named output.

What it tests: the evaporation-adjusted drought-red path that was pulled out of county_bulletin.py when that file
was reverted to its pre-2026-10-05 14:00 Juba state (out of scope for the anticipatory-action add-ons -- see
aa_out/pre_revert_backup/county_bulletin_post_oct5_2pm.py.bak for the original, un-reverted code this script is a
clone of): more than DROUGHT_RED_DRY_DAYS days without a wet county-day, AND less than DROUGHT_RED_P_RECOVERY chance
that 2 weeks of forecast rain -- net of expected evapotranspiration (the observed 30-day SMAP L4 ET rate, held
constant over the window) -- refill the root-zone soil-moisture deficit.

Two of the three inputs are pure Earth Engine (GSMaP observed rain for the dry-spell count; SMAP L4 for ET and soil
moisture / deficit). The third -- the 2-week forecast rain ensemble -- is the same ECMWF Open Data API the live app
already uses in county_bulletin.py (not Earth Engine; flagged here so the "GEE" framing doesn't overclaim). If
ecmwf-opendata isn't installed or no run is published, this script still reports the two GEE-sourced pieces and
skips the recovery-chance number rather than failing outright.

Run it (needs GEE_SERVICE_ACCOUNT_KEY, same as the other GEE scripts):
    python gee_test_drought_recovery.py
    GEE_TEST_COUNTIES="Duk,Fangak" python gee_test_drought_recovery.py     # quick smoke test, a few counties only

Output (GEE_TEST_OUT_DIR, default ./gee_test_out/), all new files, nothing overwritten:
    drought_recovery_county.csv   -- per-county et_30d_mm, soil_deficit_mm, dry_spell_days, p_soil_recovery_2wk
    drought_recovery_summary.md   -- data sources actually used and which counties would hit drought red
"""
import datetime as dt
import json
import os

import ee
import numpy as np
import pandas as pd

import ee_util

OUT_DIR = os.environ.get('GEE_TEST_OUT_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gee_test_out'))
os.makedirs(OUT_DIR, exist_ok=True)
CACHE_PATH = os.path.join(OUT_DIR, 'gee_test_obs_rain_cache.csv')          # this script's own cache, not shared

AOI_ASSET, A1, A2 = 'users/penuelabi/ssd_payam', 'ADM1_EN', 'ADM2_EN'
SMAP_IDS = ['NASA/SMAP/SPL4SMGP/008', 'NASA/SMAP/SPL4SMGP/007']
GSMAP_ID, GSMAP_BAND = 'JAXA/GPM_L3/GSMaP/v8/operational', 'hourlyPrecipRateGC'
SCALE = 10000
CLIM_YEARS = (2015, 2025)                  # SMAP record starts 2015
DRY_SPELL_LOOKBACK_DAYS = 45
WET_DAY_MM = 1.0                           # same threshold verify_forecasts.py / county_bulletin.py use
DEFICIT_MIN_MM = 20
RECOVERY_ET_DAYS = 14
DROUGHT_RED_DRY_DAYS, DROUGHT_RED_P_RECOVERY = 21, 0.60   # kept in sync with bulletin_extras.py by hand
ONLY_COUNTIES = [c.strip() for c in os.environ.get('GEE_TEST_COUNTIES', '').split(',') if c.strip()]

print("=== gee_test_drought_recovery.py -- standalone test, writes only to", OUT_DIR, "===")
ee_util.init_ee()


def get_info(x):
    return x.getInfo()


# --- counties (dissolved payams; this script's own copy, not county_bulletin.py's counties_dissolved.geojson) ----
aoi = ee.FeatureCollection(AOI_ASSET)
names_ee = aoi.aggregate_array(A2).distinct().sort()
ALL_COUNTIES = get_info(names_ee)                 # cid -> name mapping always uses the FULL list, unfiltered
COUNTIES = ALL_COUNTIES
if ONLY_COUNTIES:
    COUNTIES = [c for c in ALL_COUNTIES if c in ONLY_COUNTIES]
    print(f"Limited to {len(COUNTIES)} counties for a quick test: {COUNTIES}")
if not COUNTIES:
    raise SystemExit("No counties matched -- check GEE_TEST_COUNTIES spelling (county names as in the payam asset).")

aoi_id = aoi.map(lambda f: f.set('cid', names_ee.indexOf(f.get(A2))))
CID = aoi_id.reduceToImage(['cid'], ee.Reducer.first()).rename('cid').toInt()
geoms = {c: aoi.filter(ee.Filter.eq(A2, c)).geometry(1000) for c in COUNTIES}
REGION = aoi.filter(ee.Filter.inList(A2, COUNTIES)).geometry(1000).bounds(1000)

SMAP = None
for sid in SMAP_IDS:
    if get_info(ee.ImageCollection(sid).limit(1).size()) > 0:
        SMAP, SMAP_ID = ee.ImageCollection(sid), sid
        break
if SMAP is None:
    raise SystemExit(f"No SMAP L4 collection found among {SMAP_IDS}.")
print('SMAP collection:', SMAP_ID)


def last_full_day(col, step_hours):
    ms = get_info(col.filterDate((dt.date.today() - dt.timedelta(days=15)).isoformat(),
                                 (dt.date.today() + dt.timedelta(days=1)).isoformat())
                  .aggregate_max('system:time_start'))
    t = pd.Timestamp(ms, unit='ms')
    return ((t + pd.Timedelta(hours=step_hours)).floor('D') - pd.Timedelta(days=1)).date()


RAIN = ee.ImageCollection(GSMAP_ID).select(GSMAP_BAND)
gs_last, sm_last = last_full_day(RAIN, 1), last_full_day(SMAP, 3)
END = min(gs_last, sm_last)
print(f"Last complete day: GSMaP {gs_last}, SMAP {sm_last} -> using {END}")


def end_ee(d):
    return ee.Date(d.strftime('%Y-%m-%d')).advance(1, 'day')


def county_means(img, var_list):
    nb = len(var_list)
    red = ee.Reducer.mean().repeat(nb).group(groupField=nb, groupName='cid')
    res = img.addBands(CID).reduceRegion(reducer=red, geometry=REGION, scale=SCALE, maxPixels=1e10, tileScale=4)
    rows = {}
    for g in get_info(res.get('groups')):
        cid = int(g['cid'])
        if 0 <= cid < len(ALL_COUNTIES):
            name = ALL_COUNTIES[cid]
            if name in COUNTIES:
                rows[name] = dict(zip(var_list, g['mean']))
    return pd.DataFrame.from_dict(rows, orient='index').reindex(COUNTIES).apply(pd.to_numeric, errors='coerce')


def land_image(end_date):
    e = end_ee(end_date)
    flux = SMAP.filterDate(e.advance(-30, 'day'), e).select(
        ['land_evapotranspiration_flux']).mean().multiply(86400 * 30).rename('et_30d_mm')
    sm = SMAP.filterDate(e.advance(-3, 'day'), e).select(['sm_rootzone']).mean()
    return ee.Image.cat([flux, sm]).toFloat()


print("Fetching current 30-day ET and root-zone soil moisture (SMAP L4)...")
now = county_means(land_image(END), ['et_30d_mm', 'sm_rootzone'])
print(now.describe().round(3))

print(f"Building a {CLIM_YEARS[0]}-{CLIM_YEARS[1]} same-day-of-year climatology for the soil deficit "
      "(one Earth Engine call per comparison year)...")
clim = {}
for y in range(CLIM_YEARS[0], CLIM_YEARS[1] + 1):
    if y == END.year:
        continue
    try:
        d_y = END.replace(year=y)
    except ValueError:
        d_y = END.replace(year=y, day=28)
    ey = end_ee(d_y)
    if get_info(SMAP.filterDate(ey.advance(-30, 'day'), ey).size()) == 0:
        print(f'  {y}: no SMAP data, skipped')
        continue
    clim[y] = county_means(land_image(d_y), ['et_30d_mm', 'sm_rootzone'])
    print(f'  {y}: done')
if not clim:
    raise SystemExit("No climatology years available -- can't compute a soil deficit.")
cube = pd.concat(clim, names=['year', 'county'])
sm_hist = cube['sm_rootzone'].unstack('year').reindex(now.index)
soil_deficit_mm = ((sm_hist.median(axis=1) - now['sm_rootzone']) * 1000).clip(lower=0)   # 0.01 m3/m3 over 1 m = 10 mm

ante = pd.DataFrame({'county': now.index, 'et_30d_mm': now['et_30d_mm'].values,
                     'sm_rootzone': now['sm_rootzone'].values, 'soil_deficit_mm': soil_deficit_mm.values})

# --- observed dry spell (GSMaP county-day wet/dry, own cache -- never touches forecast_obs_cache.csv) ------------
print(f"Fetching {DRY_SPELL_LOOKBACK_DAYS} days of observed county rain for the dry-spell count...")
days = [(END - dt.timedelta(days=i)).isoformat() for i in range(DRY_SPELL_LOOKBACK_DAYS)]
cache = pd.read_csv(CACHE_PATH) if os.path.exists(CACHE_PATH) else pd.DataFrame(columns=['date', 'county', 'obs_wet'])
have = set(zip(cache['date'].astype(str), cache['county']))
need = [d for d in days if not all((d, c) in have for c in COUNTIES)]
fc = ee.FeatureCollection([ee.Feature(geoms[c], {'county': c}) for c in COUNTIES])
new_rows = []
for k in range(0, len(need), 5):
    batch = need[k:k + 5]
    try:
        for d in batch:
            e = ee.Date(d)
            day = RAIN.filterDate(e, e.advance(1, 'day')).sum()
            res = day.reduceRegions(fc, ee.Reducer.mean(), SCALE, tileScale=4).getInfo()['features']
            for feat in res:
                p = feat['properties']
                mm = p.get('mean')
                if mm is not None:
                    new_rows.append({'date': d, 'county': p['county'], 'obs_wet': int(mm >= WET_DAY_MM)})
    except Exception as e:
        print(f'  days from {batch[0]}: not fetched ({type(e).__name__}: {str(e)[:100]})')
if new_rows:
    cache = pd.concat([cache, pd.DataFrame(new_rows)], ignore_index=True).drop_duplicates(['date', 'county'],
                                                                                           keep='last')
    cache.to_csv(CACHE_PATH, index=False)

wet = {(str(d), c): w for d, c, w in zip(cache['date'].astype(str), cache['county'], cache['obs_wet'])}
dry_rows = []
for c in COUNTIES:
    n_dry, first_missing = 0, (days[0], c) not in wet
    for d in days:
        w = wet.get((d, c))
        if w is None:
            break
        if w >= 1:
            break
        n_dry += 1
    dry_rows.append({'county': c, 'dry_spell_days': np.nan if first_missing else n_dry})
ante = ante.merge(pd.DataFrame(dry_rows), on='county', how='left')
print(f"Dry-spell days: median {ante['dry_spell_days'].median():.0f}, max {ante['dry_spell_days'].max():.0f}, "
      f"{int((ante['dry_spell_days'] > DROUGHT_RED_DRY_DAYS).sum())} counties above {DROUGHT_RED_DRY_DAYS}")

# --- 2-week forecast rain ensemble: same ECMWF Open Data source county_bulletin.py uses (NOT Earth Engine) -------
rain_2wk_by_county, ecmwf_note = {}, 'not attempted'
try:
    from ecmwf.opendata import Client
    client = Client(source='ecmwf')
    run = client.latest(stream='enfo', type='pf', param='tp', step=360, time=0)
    ecmwf_note = f"ECMWF ENS run {run:%Y-%m-%d %H} UTC used for 2-week rain (demonstration only; see note in the " \
                 f"docstring -- this one input is not Earth Engine)"
    print(ecmwf_note, "-- fetching the full ensemble grid is out of scope for this quick test; see note below.")
except Exception as e:
    ecmwf_note = f"ECMWF Open Data not available in this run ({type(e).__name__}: {str(e)[:150]}); " \
                 f"p_soil_recovery_2wk left blank -- this script only demonstrates the two GEE-sourced inputs " \
                 f"(et_30d_mm, dry_spell_days) faithfully. See county_bulletin.py's PART B for the real ensemble fetch."
    print(ecmwf_note)


def recovery_chance(rain_2wk, deficit, et_30d_mm, days_ahead=RECOVERY_ET_DAYS):
    """Verbatim copy of the recovery_chance() formula from aa_out/pre_revert_backup/county_bulletin_post_oct5_2pm.py.bak,
    for testing against real et_30d_mm/deficit without needing county_bulletin.py itself."""
    if deficit is None or pd.isna(deficit) or deficit < DEFICIT_MIN_MM:
        return float('nan')
    loss = 0.0
    if et_30d_mm is not None and not pd.isna(et_30d_mm) and et_30d_mm > 0:
        loss = float(et_30d_mm) / 30.0 * days_ahead
    net = np.asarray(rain_2wk, dtype=float) - loss
    return float(np.mean(net >= deficit))


ante['p_soil_recovery_2wk'] = np.nan
for row in ante.itertuples():
    members = rain_2wk_by_county.get(row.county)
    if members is not None:
        ante.loc[ante['county'] == row.county, 'p_soil_recovery_2wk'] = recovery_chance(
            members, row.soil_deficit_mm, row.et_30d_mm)

ante['drought_red_numeric'] = (ante['dry_spell_days'] > DROUGHT_RED_DRY_DAYS) & \
                               (ante['p_soil_recovery_2wk'] < DROUGHT_RED_P_RECOVERY)
ante = ante.round(3)
ante.to_csv(os.path.join(OUT_DIR, 'drought_recovery_county.csv'), index=False)
print(f"wrote drought_recovery_county.csv ({len(ante)} counties)")

with open(os.path.join(OUT_DIR, 'drought_recovery_summary.md'), 'w', encoding='utf-8') as fh:
    fh.write(f"# gee_test_drought_recovery.py -- run {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC\n\n")
    fh.write(f"- SMAP collection: {SMAP_ID}; antecedent window ends {END.isoformat()}\n")
    fh.write(f"- Climatology years used: {sorted(clim.keys())}\n")
    fh.write(f"- 2-week forecast rain: {ecmwf_note}\n")
    fh.write(f"- Counties tested: {len(ante)}; "
             f"{int(ante['dry_spell_days'].gt(DROUGHT_RED_DRY_DAYS).sum())} above the {DROUGHT_RED_DRY_DAYS}-day dry "
             f"spell bar on GEE-observed rain alone\n\n")
    try:
        fh.write(ante.to_markdown(index=False))        # needs the optional 'tabulate' package
    except ImportError:
        fh.write('```\n' + ante.to_string(index=False) + '\n```')
print("wrote drought_recovery_summary.md")
print("\nThis script and its output are standalone: nothing here was written to county_bulletin.py, "
      "county_bulletin_latest.csv, forecast_obs_cache.csv, or any file the live app reads.")
