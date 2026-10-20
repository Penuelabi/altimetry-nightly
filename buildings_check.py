# -*- coding: utf-8 -*-
"""
Buildings sanity test for ONE payam (default: Juba Town). Compares four ways of counting buildings from
GOOGLE/Research/open-buildings-temporal/v1 (building_fractional_count) so we can see which one gives a believable number.
Runs in GitHub Actions with the service account (workflow buildings-check.yml). Input PAYAM_NAME tests another payam.
"""
import ee

PROJECT = 'sudan-1575919084043'
PAYAM_NAME = 'Juba Town'
import json, os
key = os.environ['GEE_SERVICE_ACCOUNT_KEY'].strip()
txt = key if key.startswith('{') else open(key).read()
ee.Initialize(ee.ServiceAccountCredentials(json.loads(txt)['client_email'], key_data=txt), project=PROJECT)
PAYAM_NAME = os.environ.get('PAYAM_NAME') or PAYAM_NAME

payam = ee.FeatureCollection('users/penuelabi/ssd_payam').filter(ee.Filter.eq('ADM3_EN', PAYAM_NAME))
geom = payam.geometry()
print('payam area km2 (geometry):', round(geom.area(1).divide(1e6).getInfo(), 1))

col = ee.ImageCollection('GOOGLE/Research/open-buildings-temporal/v1').filterBounds(geom)
t = col.aggregate_max('system:time_start')
tiles = col.filter(ee.Filter.eq('system:time_start', t))
print('year:', ee.Date(t).format('YYYY-MM-dd').getInfo(), '| tiles:', tiles.size().getInfo())
band = 'building_fractional_count'

# per-tile projection (native 4 m UTM grid of the first tile) and band range
p0 = ee.Image(tiles.first()).select(band).projection()
print('tile projection:', p0.crs().getInfo(), '| nominal scale m:', p0.nominalScale().getInfo())

mos = tiles.mosaic().select(band).unmask(0)


def total(img, scale, label, tile_scale=16):
    try:
        v = img.reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e11, tileScale=tile_scale).get(band).getInfo()
        print(f'{label:55s} -> {v}')
    except Exception as e:
        print(f'{label:55s} -> FAILED: {str(e)[:120]}')


# A: direct sum on the native tile projection (the reference value; may be slow or time out for big payams)
total(mos.setDefaultProjection(p0), 4, 'A) direct sum, native 4 m grid')
# B: direct sum, coarser scale (resamples nearest; should be roughly A * (4/scale)^2 only if values are not additive)
total(mos.setDefaultProjection(p0), 30, 'B) direct sum at 30 m (nearest, NOT additive)')
# C: what the script does now (reduceResolution + EPSG:4326 4 m default projection)
bC = mos.setDefaultProjection(ee.Projection('EPSG:4326').atScale(4)).reduceResolution(ee.Reducer.sum(), True, 4096).reproject('EPSG:4326', None, 100)
total(bC, 100, 'C) current script: reduceResolution(sum) -> 100 m')
# D: same but using the tile's own projection as the default projection
bD = mos.setDefaultProjection(p0).reduceResolution(ee.Reducer.sum(), True, 4096).reproject('EPSG:4326', None, 100)
total(bD, 100, 'D) reduceResolution(sum) with native tile projection')
# E: mean-based check: mean per 4 m pixel x number of 4 m pixels in the polygon
mean = mos.setDefaultProjection(p0).reduceRegion(ee.Reducer.mean(), geom, 4, maxPixels=1e11, tileScale=16).get(band)
npix = geom.area(1).divide(16)
try:
    print('E) mean x (area/16 m2)                                  ->', ee.Number(mean).multiply(npix).getInfo())
except Exception as e:
    print('E) FAILED', str(e)[:120])
print('\nExpected for Juba Town: tens of thousands of buildings. Report which of A-E is in that range.')
