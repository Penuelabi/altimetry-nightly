# -*- coding: utf-8 -*-
"""
Diagnostic (read-only): why is the current maximum flood extent so large, and how many buildings does each part of it flag?

Rebuilds the weekly flood map (export_flood_extent.py) for the SAME window as the published asset and splits it into its parts:
  water_any  = open water: any Sentinel-1 scene in the window with VV < -18 dB (after the 50 m median filter)
  rise_only  = "flooded vegetation" only: VV max in the window >= 3 dB above the Feb-Mar dry-season median, and NOT open water
  both are kept only where HAND <= 15 m (lowland)
and compares with more conservative versions (median instead of max over the window) and with JRC Global Surface Water max_extent
(every pixel ever seen as water 1984-2021) as a plausibility reference.

Writes to GEE_TEST_OUT_DIR (default flood_extent_check/): county_extent_parts.csv, buildings_parts.csv, summary.md.
Never exports or modifies any Earth Engine asset, never touches data/exposure_cache.json.
"""
import datetime as dt
import os

import ee
import pandas as pd

import ee_util

OUT = os.environ.get('GEE_TEST_OUT_DIR') or 'flood_extent_check'
ASSET = os.environ.get('FLOOD_EXTENT_ASSET') or 'projects/sudan-1575919084043/assets/maximum_flood_extent'
PAYAM = 'users/penuelabi/ssd_payam'
BUILD = 'projects/sat-io/open-datasets/VIDA_COMBINED/SSD'
BLD_COUNTIES = [c.strip() for c in (os.environ.get('BLD_COUNTIES') or
                'Rubkona,Bor South,Aweil East,Tonj North,Fangak,Pibor,Leer,Panyijiar').split(',') if c.strip()]
WATER_VV_DB, FLOODVEG_RISE_DB, HAND_MAX_M, SPECKLE_M = -18, 3, 15, 50
SCALE = 250                                   # m, for area sums (diagnostic, not the operational 30 m)

ee_util.init_ee()
os.makedirs(OUT, exist_ok=True)
info = ee.data.getAsset(ASSET)
props = info.get('properties', {})
ws, we = props.get('window_start'), props.get('window_end')
print('asset window', ws, '->', we, '| scenes', props.get('scenes'), '| updated', props.get('updated_utc'))
end = ee.Date(we).advance(1, 'day')
start = ee.Date(ws)
year = int(we[:4])

roi = ee.Geometry.Polygon([[[23.5, 12.5], [35.5, 12.5], [35.5, 3.0], [23.5, 3.0]]])
s1 = (ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(roi).filter(ee.Filter.eq('instrumentMode', 'IW'))
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
      .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING')).select('VV'))
smooth = lambda i: i.focalMedian(SPECKLE_M, 'circle', 'meters')
wet = s1.filterDate(start, end)
dry = s1.filterDate(ee.Date.fromYMD(year, 2, 1), ee.Date.fromYMD(year, 4, 1))
print('wet scenes', wet.size().getInfo(), '| dry scenes', dry.size().getInfo())
low = ee.Image('MERIT/Hydro/v1_0_1').select('hnd').lte(HAND_MAX_M)
dry_med = smooth(dry.median())

water_any = wet.map(lambda i: smooth(i).lt(WATER_VV_DB)).max().unmask(0)
rise_max = smooth(wet.max()).subtract(dry_med).gte(FLOODVEG_RISE_DB).unmask(0)
water_med = smooth(wet.median()).lt(WATER_VV_DB).unmask(0)
rise_med = smooth(wet.median()).subtract(dry_med).gte(FLOODVEG_RISE_DB).unmask(0)
jrc = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent').eq(1).unmask(0)
asset = ee.Image(ASSET).select(0).gt(0).unmask(0)
rebuilt = water_any.Or(rise_max).And(low)

parts = ee.Image.cat([
    asset.rename('asset'),
    rebuilt.rename('rebuilt'),
    water_any.And(low).rename('water_any'),
    rise_max.And(water_any.Not()).And(low).rename('rise_only'),
    water_med.And(low).rename('water_median'),
    water_med.Or(rise_med).And(low).rename('median_version'),
    asset.And(jrc).rename('asset_in_jrc'),
    low.rename('lowland'),
    ee.Image.constant(1).rename('total'),
]).multiply(ee.Image.pixelArea().divide(1e6))

payam = ee.FeatureCollection(PAYAM)
counties = payam.distinct('ADM2_EN').aggregate_array('ADM2_EN').getInfo()
rows = []
for i in range(0, len(counties), 10):
    names = counties[i:i + 10]
    fc = ee.FeatureCollection([ee.Feature(payam.filter(ee.Filter.eq('ADM2_EN', n)).geometry(), {'county': n}) for n in names])
    for attempt in range(3):
        try:
            res = parts.reduceRegions(fc, ee.Reducer.sum(), SCALE, tileScale=8).getInfo()['features']
            rows += [f['properties'] for f in res]
            break
        except Exception as e:
            print(f'  counties {i}: attempt {attempt + 1} failed: {str(e)[:150]}')
    print(f'counties {min(i + 10, len(counties))}/{len(counties)}', flush=True)
df = pd.DataFrame(rows)
for c in ['asset', 'rebuilt', 'water_any', 'rise_only', 'water_median', 'median_version', 'asset_in_jrc']:
    df[f'{c}_pct'] = 100 * df[c] / df['total']
df.round(1).sort_values('asset', ascending=False).to_csv(os.path.join(OUT, 'county_extent_parts.csv'), index=False)

# buildings: how many are flagged by the published map, by open water only, and by the rise rule only
bld = ee.FeatureCollection(BUILD)
img30 = ee.Image.cat([asset.rename('asset'), water_any.And(low).rename('water'),
                      rise_max.And(water_any.Not()).And(low).rename('rise_only'),
                      water_med.Or(rise_med).And(low).rename('median_version')]).reproject('EPSG:4326', None, 30)
brows = []
for n in BLD_COUNTIES:
    g = payam.filter(ee.Filter.eq('ADM2_EN', n)).geometry()
    b = bld.filterBounds(g)
    try:
        r = img30.reduceRegions(b, ee.Reducer.max(), 30, tileScale=16)
        out = {'county': n, 'buildings': b.size()}
        for band in ('asset', 'water', 'rise_only', 'median_version'):
            out[band] = r.filter(ee.Filter.gt(band, 0)).size()
        brows.append(ee.Dictionary(out).getInfo())
        print('buildings', brows[-1], flush=True)
    except Exception as e:
        print(f'  buildings {n} failed: {str(e)[:150]}')
bdf = pd.DataFrame(brows)
bdf.to_csv(os.path.join(OUT, 'buildings_parts.csv'), index=False)

tot = df[['asset', 'rebuilt', 'water_any', 'rise_only', 'water_median', 'median_version', 'asset_in_jrc', 'lowland', 'total']].sum()
with open(os.path.join(OUT, 'summary.md'), 'w') as fh:
    fh.write(f'# Flood extent check, run {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC\n\n')
    fh.write(f'Asset window {ws} to {we}, {props.get("scenes")} scenes, updated {props.get("updated_utc")}\n\n')
    fh.write('| part | km2 | % of country |\n|---|---|---|\n')
    for k in tot.index:
        fh.write(f'| {k} | {tot[k]:,.0f} | {100 * tot[k] / tot["total"]:.1f} |\n')
    if not bdf.empty:
        fh.write('\n' + bdf.to_markdown(index=False) + '\n')
print(open(os.path.join(OUT, 'summary.md')).read())
