# -*- coding: utf-8 -*-
"""
Weekly export of the current maximum flood extent to a CONSTANT asset name, shared so anyone can read it.

Method = the one the app uses for its same-season baseline (Sentinel-1 descending VV, 50 m focal median, open water VV < -18 dB,
flooded vegetation = VV rise >= 3 dB over the Feb-Mar dry-season median, terrain <= 15 m HAND), but the maximum over the last
EXTENT_DAYS days (default 12, i.e. at least one full Sentinel-1 repeat cycle) instead of a fixed late-September window.

Writes (1 = flooded, 0 = not) to FLOOD_EXTENT_ASSET (default projects/sudan-1575919084043/assets/maximum_flood_extent).
It exports to a staging asset first, then copies over the constant name, so the app never sees a gap.
"""
import datetime as dt
import os
import sys
import time

import ee

import ee_util

TARGET = os.environ.get('FLOOD_EXTENT_ASSET') or 'projects/sudan-1575919084043/assets/maximum_flood_extent'
DAYS = int(os.environ.get('EXTENT_DAYS') or '12')
WATER_VV_DB, FLOODVEG_RISE_DB, HAND_MAX_M, SPECKLE_M = -18, 3, 15, 50

ee_util.init_ee()
roi = ee.Geometry.Polygon([[[23.5, 12.5], [35.5, 12.5], [35.5, 3.0], [23.5, 3.0]]])
end = ee.Date(dt.datetime.utcnow().strftime('%Y-%m-%d')).advance(1, 'day')
start = end.advance(-DAYS, 'day')
year = dt.datetime.utcnow().year

s1 = (ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(roi).filter(ee.Filter.eq('instrumentMode', 'IW'))
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
      .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING')).select('VV'))
smooth = lambda i: i.focalMedian(SPECKLE_M, 'circle', 'meters')
wet = s1.filterDate(start, end)
dry = s1.filterDate(ee.Date.fromYMD(year, 2, 1), ee.Date.fromYMD(year, 4, 1))
n_wet = wet.size().getInfo()
if n_wet == 0:
    sys.exit(f'No Sentinel-1 scenes in the last {DAYS} days; nothing exported.')
print(f'{n_wet} Sentinel-1 scenes between the last {DAYS} days and today')
water = wet.map(lambda i: smooth(i).lt(WATER_VV_DB)).max()
rise = smooth(wet.max()).subtract(smooth(dry.median())).gte(FLOODVEG_RISE_DB)
water = ee.Image(ee.Algorithms.If(dry.size().gt(0), water.Or(rise), water))
lowland = ee.Image('MERIT/Hydro/v1_0_1').select('hnd').lte(HAND_MAX_M)
img = (water.And(lowland).unmask(0).rename('flooded').byte()
       .set({'window_start': start.format('YYYY-MM-dd'), 'window_end': end.advance(-1, 'day').format('YYYY-MM-dd'),
             'scenes': n_wet, 'method': 'Sentinel-1 descending VV, max over window, open water + flooded vegetation, HAND<=15 m',
             'updated_utc': dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}))


def run(target):
    stage = target + '_new'
    for a in (stage,):
        try:
            ee.data.deleteAsset(a)
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
