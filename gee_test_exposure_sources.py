# -*- coding: utf-8 -*-
"""
Standalone GEE test script -- NOT part of the app, NOT imported by county_bulletin.py or exposure_cache.py, and NEVER
writes to data/exposure_cache.json or any other file the app reads. Everything here is new, separately named output.

What it tests: the two exposure sources that were pulled out of exposure_cache.py when that file was reverted to its
pre-2026-10-05 14:00 Juba state (the change was out of scope for the anticipatory-action add-ons -- see
aa_out/pre_revert_backup/exposure_cache_post_oct5_2pm.py.bak for the original, un-reverted code this script is a
clone of) --

  1. JRC GHS-OBAT 2020 buildings (projects/sat-io/open-datasets/JRC/GHS-OBAT/...), falling back to VIDA combined
     buildings (projects/sat-io/open-datasets/VIDA_COMBINED/SSD) if the service account can't read it.
  2. GHSL built-up surface, 2020 (JRC/GHSL/P2023A/GHS_BUILT_S/2020), for settlement extent.

...aggregated to COUNTY level (not payam) and checked against the 50% severe-exposure bar
(bulletin_extras.FLOOD_COUNTY_SHARE_SEVERE) used for the flood red/activation rule, alongside the schools/health
counts the live bulletin_extras.py already aggregates at county level today.

Run it (needs GEE_SERVICE_ACCOUNT_KEY, same as the other GEE scripts):
    python gee_test_exposure_sources.py
    GEE_TEST_COUNTIES="Duk,Fangak" python gee_test_exposure_sources.py     # quick smoke test, a few counties only

Output (GEE_TEST_OUT_DIR, default ./gee_test_out/), all new files, nothing overwritten:
    exposure_sources_payam.csv   -- per-payam figures, same shape as exposure_cache.json's payam rows
    exposure_sources_county.csv  -- per-county totals, shares, and a severe_flood_exposure flag/reasons column
    exposure_sources_summary.md  -- what asset was actually used (GHS-OBAT vs VIDA; GHSL available y/n) and counts
"""
import datetime as dt
import os

import ee
import pandas as pd

import ee_util

OUT_DIR = os.environ.get('GEE_TEST_OUT_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gee_test_out'))
os.makedirs(OUT_DIR, exist_ok=True)

PAYAM = 'users/penuelabi/ssd_payam'
SCHOOLS = 'projects/ee-penuelabi/assets/SDD_Schools'
HEALTH = 'projects/ee-penuelabi/assets/SSD_Health'
BUILD_GHSOBAT = 'projects/sat-io/open-datasets/JRC/GHS-OBAT/GHS_OBAT_GPKG_SSD_E2020_R2024A_V1_0'
BUILD_VIDA = 'projects/sat-io/open-datasets/VIDA_COMBINED/SSD'
GHSL_BUILT_S = 'JRC/GHSL/P2023A/GHS_BUILT_S/2020'
FLOOD_EXTENT_ASSET = os.environ.get('FLOOD_EXTENT_ASSET') or 'projects/sudan-1575919084043/assets/maximum_flood_extent'
BASELINE_ASSET = 'projects/wajaras-remote-s-1565857510402/assets/flood_baseline_s1_0915_0926_2017_2025'
FREQ_RARE, MIN_FLOOD_YEARS = 0.15, 3
A1, A2, A3 = 'ADM1_EN', 'ADM2_EN', 'ADM3_EN'
FLOOD_COUNTY_SHARE_SEVERE = 0.50          # matches bulletin_extras.py -- kept in sync by hand, not imported
CHUNK = int(os.environ.get('GEE_TEST_CHUNK', '20'))
ONLY_COUNTIES = [c.strip() for c in os.environ.get('GEE_TEST_COUNTIES', '').split(',') if c.strip()]

print("=== gee_test_exposure_sources.py -- standalone test, writes only to", OUT_DIR, "===")
ee_util.init_ee()

payam = ee.FeatureCollection(PAYAM)
if ONLY_COUNTIES:
    payam = payam.filter(ee.Filter.inList(A2, ONLY_COUNTIES))
    print(f"Limited to {len(ONLY_COUNTIES)} counties for a quick test: {ONLY_COUNTIES}")
n = payam.size().getInfo()
if n == 0:
    raise SystemExit("No payams matched -- check GEE_TEST_COUNTIES spelling (county names as in the payam asset).")
print(f"{n} payams selected")

# --- flood-risk raster: same definition as exposure_cache.py / the GEE app ---------------------------------------
risk_basis = 'Sentinel-1 same-season baseline + current extent'
try:
    ee.data.getAsset(BASELINE_ASSET)
    base = ee.Image(BASELINE_ASSET)
    freq = base.select('freq').unmask(0)
    has_base = base.select('n_years').unmask(0).gte(MIN_FLOOD_YEARS)
    try:
        ee.data.getAsset(FLOOD_EXTENT_ASSET)
        flooded = ee.Image(FLOOD_EXTENT_ASSET).select(0).gt(0).unmask(0)
    except Exception:
        flooded = ee.Image.constant(0)
        risk_basis = 'Sentinel-1 same-season baseline'
    risk = flooded.max(freq.gte(FREQ_RARE).And(has_base)).rename('risk')
except Exception as e:
    print('baseline asset not readable, falling back to JRC surface water + Global Flood DB:', str(e)[:150])
    gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent').eq(1).unmask(0)
    gfd = ee.ImageCollection('GLOBAL_FLOOD_DB/MODIS_EVENTS/V1').select('flooded').sum().gt(0).unmask(0)
    risk = gsw.max(gfd).rename('risk')
    risk_basis = 'JRC surface water + Global Flood DB (baseline asset not accessible)'
print('risk basis:', risk_basis)
risk30 = risk.reproject('EPSG:4326', None, 30)

# --- the two sources under test -----------------------------------------------------------------------------------
try:
    ee.data.getAsset(BUILD_GHSOBAT)
    bld = ee.FeatureCollection(BUILD_GHSOBAT)
    buildings_basis = 'JRC GHS-OBAT 2020 (sat-io)'
except Exception as e:
    print('GHS-OBAT not readable by the service account, falling back to VIDA combined buildings:', str(e)[:150])
    bld = ee.FeatureCollection(BUILD_VIDA)
    buildings_basis = 'VIDA combined buildings (sat-io) -- GHS-OBAT not accessible'
print('buildings basis:', buildings_basis)

try:
    ghsl_bu = ee.Image(GHSL_BUILT_S).select('built_surface').divide(1e6)      # m2/cell -> km2
    have_ghsl = True
    print('settlement extent: GHSL built-up surface 2020 -- OK')
except Exception as e:
    ghsl_bu, have_ghsl = None, False
    print('GHSL built-up surface not available:', str(e)[:150])

area = ee.Image.pixelArea().divide(1e6)
schools, health = ee.FeatureCollection(SCHOOLS), ee.FeatureCollection(HEALTH)
schools_r = risk30.reduceRegions(schools, ee.Reducer.max(), 30, tileScale=4)
health_r = risk30.reduceRegions(health, ee.Reducer.max(), 30, tileScale=4)


def cnt(fc_r, g):
    s = fc_r.filterBounds(g)
    return s.size(), s.filter(ee.Filter.gt('max', 0)).size()


# --- per-payam pass (mirrors exposure_cache.py's payam loop, output-only) -----------------------------------------
lst = payam.toList(n)
rows = []
for i in range(0, n, CHUNK):
    sub = ee.FeatureCollection(lst.slice(i, i + CHUNK))

    def per(f):
        g = f.geometry()
        bands = area.rename('a').addBands(area.multiply(risk).rename('ar'))
        if have_ghsl:
            bands = bands.addBands(ghsl_bu.rename('bu')).addBands(ghsl_bu.multiply(risk).rename('bur'))
        a = bands.reduceRegion(ee.Reducer.sum(), g, 100, maxPixels=1e10, tileScale=8)
        st, sr = cnt(schools_r, g)
        ht, hr = cnt(health_r, g)
        props = {'payam': f.get(A3), 'county': f.get(A2), 'state': f.get(A1),
                 'area_km2': a.get('a'), 'area_risk_km2': a.get('ar'),
                 'schools': st, 'schools_risk': sr, 'health': ht, 'health_risk': hr}
        if have_ghsl:
            props['built_km2'] = a.get('bu')
            props['built_risk_km2'] = a.get('bur')
        b = bld.filterBounds(g)
        nb = b.size()
        props['buildings'] = nb
        props['buildings_risk'] = ee.Number(ee.Algorithms.If(
            nb.lt(40000), risk30.reduceRegions(b, ee.Reducer.max(), 30, tileScale=8)
            .filter(ee.Filter.gt('max', 0)).size(), -1))
        return ee.Feature(None, props)

    got = False
    for attempt in range(2):
        try:
            res = sub.map(per).getInfo()['features']
            rows += [r['properties'] for r in res]
            got = True
            break
        except Exception as e:
            print(f'  payams {i}-{i + CHUNK} attempt {attempt + 1} failed: {str(e)[:200]}')
    print(f'payams {min(i + CHUNK, n)}/{n} done' + ('' if got else ' (FAILED, skipped)'), flush=True)

if not rows:
    raise SystemExit("No payam rows computed -- nothing written. Check the errors above.")

payam_df = pd.DataFrame(rows)
for c in payam_df.columns:
    if c not in ('payam', 'county', 'state'):
        payam_df[c] = pd.to_numeric(payam_df[c], errors='coerce').round(2)
payam_df.to_csv(os.path.join(OUT_DIR, 'exposure_sources_payam.csv'), index=False)
print(f"wrote exposure_sources_payam.csv ({len(payam_df)} payams)")

# --- county-level aggregation + the 50% severe-exposure check -----------------------------------------------------
sum_cols = [c for c in ('buildings', 'buildings_risk', 'schools', 'schools_risk', 'health', 'health_risk',
                        'built_km2', 'built_risk_km2') if c in payam_df.columns]
county_df = payam_df.groupby('county')[sum_cols].sum(min_count=1).reset_index()


def share(row, total_col, risk_col):
    t, r = row.get(total_col), row.get(risk_col)
    if t and t > 0 and pd.notna(r) and r >= 0:
        return r / t
    return float('nan')


def severe_reasons(row):
    why = []
    for total_col, risk_col, label in (('buildings', 'buildings_risk', 'buildings'),
                                        ('schools', 'schools_risk', 'schools'),
                                        ('health', 'health_risk', 'health facilities'),
                                        ('built_km2', 'built_risk_km2', 'built-up (settlement) area')):
        s = share(row, total_col, risk_col)
        if pd.notna(s) and s >= FLOOD_COUNTY_SHARE_SEVERE:
            why.append(f"{s:.0%} of {label}")
    return why


county_df['buildings_share'] = county_df.apply(lambda r: share(r, 'buildings', 'buildings_risk'), axis=1)
county_df['schools_share'] = county_df.apply(lambda r: share(r, 'schools', 'schools_risk'), axis=1)
county_df['health_share'] = county_df.apply(lambda r: share(r, 'health', 'health_risk'), axis=1)
if 'built_km2' in county_df.columns:
    county_df['settlement_share'] = county_df.apply(lambda r: share(r, 'built_km2', 'built_risk_km2'), axis=1)
county_df['severe_flood_exposure_reasons'] = county_df.apply(lambda r: '; '.join(severe_reasons(r)), axis=1)
county_df['severe_flood_exposure'] = county_df['severe_flood_exposure_reasons'] != ''
county_df = county_df.round(4)
county_df.to_csv(os.path.join(OUT_DIR, 'exposure_sources_county.csv'), index=False)
print(f"wrote exposure_sources_county.csv ({len(county_df)} counties, "
      f"{int(county_df['severe_flood_exposure'].sum())} at/above the {FLOOD_COUNTY_SHARE_SEVERE:.0%} county bar)")

with open(os.path.join(OUT_DIR, 'exposure_sources_summary.md'), 'w', encoding='utf-8') as fh:
    fh.write(f"# gee_test_exposure_sources.py -- run {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC\n\n")
    fh.write(f"- Buildings source actually used: **{buildings_basis}**\n")
    fh.write(f"- Settlement extent (GHSL built-up surface): **{'available' if have_ghsl else 'NOT available'}**\n")
    fh.write(f"- Flood-risk basis: {risk_basis}\n")
    fh.write(f"- Payams tested: {len(payam_df)}; counties: {len(county_df)}\n")
    fh.write(f"- Counties at/above the {FLOOD_COUNTY_SHARE_SEVERE:.0%} county-level severe bar: "
             f"{int(county_df['severe_flood_exposure'].sum())}\n\n")
    severe = county_df[county_df['severe_flood_exposure']][['county', 'severe_flood_exposure_reasons']]
    if len(severe):
        fh.write("| County | Why |\n|---|---|\n")
        for r in severe.itertuples():
            fh.write(f"| {r.county} | {r.severe_flood_exposure_reasons} |\n")
    else:
        fh.write("No county reached the severe bar in this test run.\n")
print("wrote exposure_sources_summary.md")
print("\nThis script and its output are standalone: nothing here was written to data/exposure_cache.json, "
      "exposure_cache.py, county_bulletin.py, or any file the live app reads.")
