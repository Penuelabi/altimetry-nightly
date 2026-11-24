# -*- coding: utf-8 -*-
"""
Weekly export of the current maximum flood extent to a CONSTANT asset name, shared so anyone can read it.

Method v6, masked upland version (calibrated against the VIIRS monthly flood maps, Jun-Oct 2019-2025;
CSI about 0.29 against 0.14 for the old rule):
  - Sentinel-1 GRD, ASCENDING and DESCENDING passes, VV and VH, 50 m focal median
  - open water: VV < -18 dB in any scene of the window (everywhere)
  - flooded vegetation: VV rise >= 4 dB AND (VV - VH) rise >= 1 dB against a FIXED dry-season reference
    (median Feb-Mar 2017-2019 per orbit pass, asset DRY_REF_ASSET). A same-year dry reference misses floods that
    persist through the dry season (2019-2022 Sudd); the VV/VH check removes vegetation green-up false alarms.
  - upland states (Central/Eastern/Western Equatoria, Western Bahr el Ghazal): flooded vegetation is kept ONLY inside
    the water mask = JRC max_extent buffered 1 km OR Sentinel-1 open water in at least one 15-26 September window
    2017-2025. The mask is read from the 'water_mask' band of the v6 baseline asset (BASELINE_ASSET); if that asset
    cannot be read, the JRC 1 km buffer alone is used. This cut upland false-alarm area by 65-85 % in the calibration.
  - terrain: HAND <= 5 m; JRC permanent water (occurrence >= 75 %) removed unless KEEP_PERMANENT_WATER=1
  - maximum over the last EXTENT_DAYS days (default 12, at least one Sentinel-1 repeat cycle)

Writes (1 = flooded, 0 = not flooded or no image) to FLOOD_EXTENT_ASSET
(default projects/sudan-1575919084043/assets/maximum_flood_extent) and a second band 'covered' (1 = imaged in the window),
so "no image" is never read as "not flooded".
It exports to a staging asset first, then copies over the constant name, so the app never sees a gap.
"""
import datetime as dt
import os
import sys
import time

import ee

import ee_util

TARGET = os.environ.get('FLOOD_EXTENT_ASSET') or 'projects/sudan-1575919084043/assets/maximum_flood_extent'
DRY_REF_ASSET = os.environ.get('DRY_REF_ASSET') or 'projects/sudan-1575919084043/assets/s1_dry_ref_FebMar_2017_2019c'
BASELINE_ASSET = os.environ.get('BASELINE_ASSET') or 'projects/sudan-1575919084043/assets/flood_baseline_s1v6_0915_0926_2017_2025'
ADMIN_ASSET = os.environ.get('ADMIN_ASSET') or 'users/penuelabi/ssd_payam'
DAYS = int(os.environ.get('EXTENT_DAYS') or '12')
KEEP_PERMANENT_WATER = os.environ.get('KEEP_PERMANENT_WATER', '0') == '1'
WATER_VV_DB, FLOODVEG_RISE_DB, RATIO_RISE_DB = -18, 4, 1
UPLAND_STATES = ['Central Equatoria', 'Eastern Equatoria', 'Western Equatoria', 'Western Bahr el Ghazal']
HAND_MAX_M, SPECKLE_M, PERM_WATER_OCC, MASK_BUFFER_M = 5, 50, 75, 1000
PASSES = [('ASCENDING', 'asc'), ('DESCENDING', 'desc')]

ee_util.init_ee()
roi = ee.Geometry.Polygon([[[23.5, 12.5], [35.5, 12.5], [35.5, 3.0], [23.5, 3.0]]])
end = ee.Date(dt.datetime.utcnow().strftime('%Y-%m-%d')).advance(1, 'day')
start = end.advance(-DAYS, 'day')

s1 = (ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(roi).filter(ee.Filter.eq('instrumentMode', 'IW'))
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
      .select(['VV', 'VH']))
dref = ee.Image(DRY_REF_ASSET)
smooth = lambda i: i.focalMedian(SPECKLE_M, 'circle', 'meters')

# upland states and the water mask that limits flooded vegetation there
upland = (ee.Image(0).paint(ee.FeatureCollection(ADMIN_ASSET).filter(ee.Filter.inList('ADM1_EN', UPLAND_STATES)), 1)
          .rename('upland'))
jrc_buf = (ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent').unmask(0).eq(1)
           .focalMax(MASK_BUFFER_M, 'circle', 'meters'))
try:
    ee.data.getAsset(BASELINE_ASSET)
    water_mask = ee.Image(BASELINE_ASSET).select('water_mask').unmask(0).gt(0)
    mask_source = 'v6 baseline water_mask (JRC max_extent +1 km OR S1 open water in a 15-26 Sep window 2017-2025)'
except Exception as e:
    print('baseline water_mask not readable, using JRC max_extent +1 km only:', str(e)[:150])
    water_mask = jrc_buf
    mask_source = 'JRC max_extent +1 km (baseline asset not readable)'
veg_allowed = upland.Not().Or(water_mask)

n_wet = s1.filterDate(start, end).size().getInfo()
if n_wet == 0:
    sys.exit(f'No Sentinel-1 scenes in the last {DAYS} days; nothing exported.')
print(f'{n_wet} Sentinel-1 scenes (both passes) in the last {DAYS} days')
print('upland mask:', mask_source)

flooded_parts, cover_parts = [], []
for pass_name, tag in PASSES:
    wet = s1.filter(ee.Filter.eq('orbitProperties_pass', pass_name)).filterDate(start, end)
    if wet.size().getInfo() == 0:
        continue
    d_vv, d_vh = smooth(dref.select(f'{tag}_VV')), smooth(dref.select(f'{tag}_VH'))
    w_vv, w_vh = smooth(wet.select('VV').max()), smooth(wet.select('VH').max())
    water = wet.select('VV').map(lambda i: smooth(i).lt(WATER_VV_DB)).max()
    veg = (w_vv.subtract(d_vv).gte(FLOODVEG_RISE_DB)
           .And(w_vv.subtract(w_vh).subtract(d_vv.subtract(d_vh)).gte(RATIO_RISE_DB))
           .And(veg_allowed))
    flooded_parts.append(water.unmask(0).Or(veg.unmask(0)).toByte())
    cover_parts.append(wet.select('VV').map(lambda i: i.mask().gt(0)).max().And(d_vv.mask()).unmask(0).toByte())

lowland = ee.Image('MERIT/Hydro/v1_0_1').select('hnd').lte(HAND_MAX_M)
flooded = ee.ImageCollection(flooded_parts).max().And(lowland)
if not KEEP_PERMANENT_WATER:
    perm = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').unmask(0).gte(PERM_WATER_OCC)
    flooded = flooded.And(perm.Not())
covered = ee.ImageCollection(cover_parts).max()

img = (ee.Image.cat([flooded.unmask(0).rename('flooded'), covered.rename('covered')]).byte()
       .set({'window_start': start.format('YYYY-MM-dd'), 'window_end': end.advance(-1, 'day').format('YYYY-MM-dd'),
             'scenes': n_wet,
             'method': (f'v6 masked: Sentinel-1 asc+desc, max over window; open water VV<{WATER_VV_DB} dB + flooded veg '
                        f'(VV rise>={FLOODVEG_RISE_DB} dB AND VV-VH rise>={RATIO_RISE_DB} dB) vs fixed Feb-Mar 2017-2019 '
                        f'dry reference; upland states: flooded veg only inside {mask_source}; HAND<={HAND_MAX_M} m; '
                        + ('permanent water kept' if KEEP_PERMANENT_WATER else 'JRC permanent water removed')),
             'updated_utc': dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}))


def run(target):
    stage = target + '_new'
    try:
        ee.data.deleteAsset(stage)
    except Exception:
        pass
    task = ee.batch.Export.image.toAsset(image=img.clip(roi), description='maximum_flood_extent', assetId=stage, region=roi,
                                         scale=30, maxPixels=1e13, pyramidingPolicy={'.default': 'max'})
    task.start()
    print('export started ->', stage, flush=True)
    while task.status()['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED'):
        time.sleep(30)
    st = task.status()
    if st['state'] != 'COMPLETED':
        raise RuntimeError(f"export {st['state']}: {st.get('error_message', '')}")
    ee.data.copyAsset(stage, target, True)           # overwrite: the constant name never disappears
    try:
        ee.data.deleteAsset(stage)
    except Exception:
        pass
    ee_util.make_public(target)
    print('updated and shared:', target)


run(TARGET)
