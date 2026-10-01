# -*- coding: utf-8 -*-
"""
Infrastructure on flood-prone ground by payam (512 payam polygons): settled area, buildings, schools, health
facilities (counts only) and road length. Flood-prone ground = JRC surface water (max extent) U Global Flood DB.
Output: infra_exposure_payam.csv (+ .json by county) in INFRA_OUT_DIR. Needs GEE_SERVICE_ACCOUNT_KEY.
Each layer is optional: a failure is logged and its columns stay empty.
"""
import json, os, re, sys, traceback
import ee
import pandas as pd

OUT = os.environ.get('INFRA_OUT_DIR', 'infra_out')
os.makedirs(OUT, exist_ok=True)
PAYAM = 'users/penuelabi/ssd_payam'
SCHOOLS = 'projects/ee-penuelabi/assets/SDD_Schools'
HEALTH = 'projects/ee-penuelabi/assets/SSD_Health'
ROADS = 'projects/sat-io/open-datasets/GRIP4/Africa'
BUILDINGS = 'GOOGLE/Research/open-buildings-temporal/v1'
CHUNK = int(os.environ.get('INFRA_CHUNK', '40'))

key = os.environ['GEE_SERVICE_ACCOUNT_KEY'].strip()
txt = key if key.startswith('{') else open(key).read()
ee.Initialize(ee.ServiceAccountCredentials(json.loads(txt)['client_email'], key_data=txt), project='sudan-1575919084043')

payam = ee.FeatureCollection(PAYAM)
keys = payam.first().propertyNames().getInfo()
print('payam properties:', keys)


def pick(*pats):
    for p in pats:
        for k in keys:
            if re.fullmatch(p, k, re.I):
                return k
    return None


K_PAYAM = pick('adm3_en', r'payam.*', r'adm3.*name.*', 'name', r'.*payam.*')
K_PCODE = pick('adm3_pcode', r'.*pcode3.*', r'adm3_.*code')
K_COUNTY = pick('adm2_en', r'county.*', r'adm2.*name.*')
K_STATE = pick('adm1_en', r'state.*', r'adm1.*name.*')
print('using', dict(payam=K_PAYAM, pcode=K_PCODE, county=K_COUNTY, state=K_STATE))

gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent').eq(1).unmask(0)
gfd = ee.ImageCollection('GLOBAL_FLOOD_DB/MODIS_EVENTS/V1').select('flooded').sum().gt(0).unmask(0)
fp = gsw.max(gfd).rename('fp')
fp_geo = fp.reproject('EPSG:4326', None, 250)
SCALE = 250


def with_fp(fc):
    return fp_geo.reduceRegions(fc, ee.Reducer.max(), SCALE, tileScale=4)


def count_points(fc_id, label):
    pts = ee.FeatureCollection(fc_id)
    pts = with_fp(pts)

    def per(f):
        g = f.geometry()
        inside = pts.filterBounds(g)
        return f.set({label + '_total': inside.size(), label + '_at_risk': inside.filter(ee.Filter.gt('max', 0)).size()})
    return per


def area_stats(f):
    g = f.geometry()
    a = ee.Image.pixelArea().divide(1e6)
    r = a.addBands(a.multiply(fp).rename('fpa')).reduceRegion(ee.Reducer.sum(), g, 500, maxPixels=1e10, tileScale=8)
    return f.set({'area_km2': r.get('area'), 'flood_prone_km2': r.get('fpa')})


# settled area (GHSL built-up surface m2 per 100 m cell, 2020)
try:
    bu = ee.Image('JRC/GHSL/P2023A/GHS_BUILT_S/2020').select('built_surface').divide(1e6)

    def built(f):
        g = f.geometry()
        r = bu.addBands(bu.multiply(fp_geo).rename('b_risk')).reduceRegion(ee.Reducer.sum(), g, 100, maxPixels=1e10, tileScale=8)
        return f.set({'built_km2': r.get('built_surface'), 'built_at_risk_km2': r.get('b_risk')})
except Exception:
    built = None

# roads: rasterise GRIP4 (any class), 100 m cells ~ 0.1 km each
try:
    rd = ee.FeatureCollection(ROADS).filterBounds(payam.geometry())
    road_img = ee.Image().byte().paint(rd, 1, 1).unmask(0).reproject('EPSG:4326', None, 100)

    def roads(f):
        g = f.geometry()
        r = road_img.addBands(road_img.multiply(fp_geo.reproject('EPSG:4326', None, 100)).rename('r_risk')).reduceRegion(
            ee.Reducer.sum(), g, 100, maxPixels=1e10, tileScale=8)
        return f.set({'road_km_total': ee.Number(r.get('constant')).multiply(0.1),
                      'road_km_at_risk': ee.Number(r.get('r_risk')).multiply(0.1)})
except Exception:
    roads = None

# buildings: open-buildings temporal, latest year, fractional count summed at 4 m then aggregated
try:
    b = ee.ImageCollection(BUILDINGS).sort('system:time_start', False).first().select('building_fractional_count')
    b100 = b.reduceResolution(ee.Reducer.sum(), True, 4096).reproject('EPSG:4326', None, 100)

    def bld(f):
        g = f.geometry()
        r = b100.addBands(b100.multiply(fp_geo.reproject('EPSG:4326', None, 100)).rename('b_risk')).reduceRegion(
            ee.Reducer.sum(), g, 100, maxPixels=1e10, tileScale=16)
        return f.set({'buildings_total': r.get('building_fractional_count'), 'buildings_at_risk': r.get('b_risk')})
except Exception:
    bld = None

layers = [('area', area_stats)]
if built: layers.append(('built', built))
if roads: layers.append(('roads', roads))
if bld: layers.append(('buildings', bld))
layers.append(('schools', count_points(SCHOOLS, 'schools')))
layers.append(('health', count_points(HEALTH, 'health')))

n = payam.size().getInfo()
lst = payam.toList(n)
base = []
for i in range(0, n, CHUNK):
    sub = ee.FeatureCollection(lst.slice(i, i + CHUNK))
    sub = sub.map(lambda f: ee.Feature(None, {k: f.get(k) for k in [K_PAYAM, K_PCODE, K_COUNTY, K_STATE] if k}).setGeometry(f.geometry()))
    rows = None
    for name, fn in layers:
        try:
            res = sub.map(fn).select(['.*'], None, False).getInfo()['features']
            part = pd.DataFrame([r['properties'] for r in res])
            rows = part if rows is None else rows.join(part.drop(columns=[c for c in part.columns if c in rows.columns]))
        except Exception as e:
            print(f'  layer {name} failed on chunk {i}: {str(e)[:160]}')
    if rows is not None:
        base.append(rows)
    print(f'chunk {i}-{min(i + CHUNK, n)} done', flush=True)

df = pd.concat(base, ignore_index=True)
ren = {K_PAYAM: 'payam', K_PCODE: 'payam_pcode', K_COUNTY: 'county', K_STATE: 'state'}
df = df.rename(columns={k: v for k, v in ren.items() if k})
for c in df.columns:
    if c.endswith(('_km2', '_km', '_total', '_risk')) or c in ('area_km2',):
        df[c] = pd.to_numeric(df[c], errors='coerce').round(2)
df.to_csv(os.path.join(OUT, 'infra_exposure_payam.csv'), index=False)
print(df.describe(include='all').T.head(30).to_string())
if 'county' in df.columns:
    num = [c for c in df.columns if c not in ('payam', 'payam_pcode', 'county', 'state')]
    df.groupby('county')[num].sum().round(1).to_csv(os.path.join(OUT, 'infra_exposure_county.csv'))
