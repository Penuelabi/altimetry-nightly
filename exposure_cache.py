# -*- coding: utf-8 -*-
"""
Earth Engine job behind the "infrastructure at risk" and "25 km exposure" sections of the county report pages.
Same definitions as the GEE app (gee.js): at risk = flooded now OR flooded in >= 15% of the same-season Sentinel-1 baseline years.

Writes data/exposure_cache.json:
  payams   {county: [ {payam, area_km2, area_risk_km2, schools, schools_risk, health, health_risk, buildings, buildings_risk,
                       roads_km, roads_risk_km} ]}
  county   {county: {schools, schools_risk, health, health_risk}}
  stations {station_uid: {county, payam, pop, pop_risk, schools, schools_risk, health, health_risk, buildings, buildings_risk,
                          counties, payams: [ {payam, county, pop, pop_risk, bld, sch, sch_r, hl, hl_r} ]}}

Incremental: stations already in the cache are skipped (set EXPOSURE_REFRESH=1 to recompute everything), the file is saved after
every step, and the run stops cleanly when EXPOSURE_BUDGET_MIN minutes are used, so a re-run continues where it stopped.
Every layer is optional: a failure is logged and that figure stays empty. Needs GEE_SERVICE_ACCOUNT_KEY.
"""
import datetime as dt
import json
import os
import sys
import time
import traceback

import ee
import pandas as pd

import ee_util

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'data', 'exposure_cache.json')
ALT = os.environ.get('ALTIMETRY_OUT_DIR', os.path.join(HERE, 'altdata'))
BUDGET_S = float(os.environ.get('EXPOSURE_BUDGET_MIN', '300')) * 60
REFRESH = os.environ.get('EXPOSURE_REFRESH') == '1'
CHUNK = int(os.environ.get('EXPOSURE_CHUNK', '20'))
T0 = time.time()

PAYAM = 'users/penuelabi/ssd_payam'
SCHOOLS = 'projects/ee-penuelabi/assets/SDD_Schools'
HEALTH = 'projects/ee-penuelabi/assets/SSD_Health'
ROADS = 'projects/sat-io/open-datasets/GRIP4/Africa'
BUILD_A = 'projects/sat-io/open-datasets/VIDA_COMBINED/SSD'
FLOOD_EXTENT_ASSET = os.environ.get('FLOOD_EXTENT_ASSET') or 'projects/sudan-1575919084043/assets/maximum_flood_extent'
BASELINE_ASSET = 'projects/wajaras-remote-s-1565857510402/assets/flood_baseline_s1_0915_0926_2017_2025'
FREQ_RARE, MIN_FLOOD_YEARS, BUF_M = 0.15, 3, 25000
A2, A3, A1 = 'ADM2_EN', 'ADM3_EN', 'ADM1_EN'


def left():
    return BUDGET_S - (time.time() - T0)


def load():
    if os.path.exists(CACHE) and not REFRESH:
        try:
            return json.load(open(CACHE, encoding='utf-8'))
        except Exception:
            pass
    return {'payams': {}, 'county': {}, 'stations': {}}


def save(c):
    c['generated_utc'] = dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, 'w', encoding='utf-8') as fh:
        json.dump(c, fh, ensure_ascii=False, separators=(',', ':'))


ee_util.init_ee()
payam = ee.FeatureCollection(PAYAM)
keys = payam.first().propertyNames().getInfo()
print('payam properties:', keys)
for k in (A1, A2, A3):
    if k not in keys:
        sys.exit(f'payam asset has no field {k}: {keys}')

# --- risk image (same definition as the app) -------------------------------------------------------------------
risk_basis = 'Sentinel-1 same-season baseline + current extent'
flooded = None
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
    print('baseline asset not readable by the service account, using JRC surface water + Global Flood DB:', str(e)[:150])
    gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent').eq(1).unmask(0)
    gfd = ee.ImageCollection('GLOBAL_FLOOD_DB/MODIS_EVENTS/V1').select('flooded').sum().gt(0).unmask(0)
    risk = gsw.max(gfd).rename('risk')
    risk_basis = 'JRC surface water + Global Flood DB (baseline asset not accessible)'
print('risk basis:', risk_basis)
risk30 = risk.reproject('EPSG:4326', None, 30)

schools, health = ee.FeatureCollection(SCHOOLS), ee.FeatureCollection(HEALTH)
schools_r = risk30.reduceRegions(schools, ee.Reducer.max(), 30, tileScale=4)
health_r = risk30.reduceRegions(health, ee.Reducer.max(), 30, tileScale=4)
bld = ee.FeatureCollection(BUILD_A)
wp = (ee.ImageCollection('WorldPop/GP/100m/pop').filter(ee.Filter.date('2020-01-01', '2020-12-31'))
      .mosaic().select('population'))
area = ee.Image.pixelArea().divide(1e6)


def cnt(fc_r, g):
    s = fc_r.filterBounds(g)
    return s.size(), s.filter(ee.Filter.gt('max', 0)).size()


# --- 1. payam table ----------------------------------------------------------------------------------------------
c = load()
if not c.get('payams_complete') or REFRESH:
    n = payam.size().getInfo()
    lst = payam.toList(n)
    rows = []
    road_img = None
    try:
        rd = ee.FeatureCollection(ROADS).filterBounds(payam.geometry())
        road_img = ee.Image().byte().paint(rd, 1, 1).unmask(0).reproject('EPSG:4326', None, 100)
    except Exception as e:
        print('roads unavailable:', str(e)[:120])
    for i in range(0, n, CHUNK):
        if left() < 600:
            print('budget used up during the payam table; it will continue on the next run'); break
        sub = ee.FeatureCollection(lst.slice(i, i + CHUNK))

        def per(f):
            g = f.geometry()
            a = area.rename('a').addBands(area.multiply(risk).rename('ar')).reduceRegion(
                ee.Reducer.sum(), g, 100, maxPixels=1e10, tileScale=8)
            st, sr = cnt(schools_r, g)
            ht, hr = cnt(health_r, g)
            props = {'payam': f.get(A3), 'county': f.get(A2), 'state': f.get(A1),
                     'area_km2': a.get('a'), 'area_risk_km2': a.get('ar'),
                     'schools': st, 'schools_risk': sr, 'health': ht, 'health_risk': hr}
            b = bld.filterBounds(g)
            nb = b.size()
            props['buildings'] = nb
            props['buildings_risk'] = ee.Number(ee.Algorithms.If(
                nb.lt(40000), risk30.reduceRegions(b, ee.Reducer.max(), 30, tileScale=8).filter(ee.Filter.gt('max', 0)).size(), -1))
            if road_img is not None:
                r = road_img.addBands(road_img.multiply(risk.reproject('EPSG:4326', None, 100)).rename('rr')).reduceRegion(
                    ee.Reducer.sum(), g, 100, maxPixels=1e10, tileScale=8)
                props['roads_km'] = ee.Number(r.get('constant')).multiply(0.1)
                props['roads_risk_km'] = ee.Number(r.get('rr')).multiply(0.1)
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
        print(f'payams {min(i + CHUNK, n)}/{n}', flush=True)
    if rows:
        by = {}
        for r in rows:
            by.setdefault(r['county'], []).append({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()
                                                   if k not in ('county', 'state')})
        c['payams'] = by
        c['county'] = {k: {m: sum((p.get(m) or 0) for p in v if (p.get(m) or 0) >= 0) for m in ('schools', 'schools_risk', 'health', 'health_risk')}
                       for k, v in by.items()}
        c['risk_basis'] = risk_basis
        c['payams_complete'] = len(rows) >= 0.98 * n
        save(c)
        print('payam table saved:', len(rows), 'payams')

# --- 1b. flooded-now table (current maximum flood extent only) ------------------------------------------------------
c = load()
if flooded is not None and risk_basis.startswith('Sentinel-1 same-season baseline +') and (not c.get('now_complete') or REFRESH) \
        and c.get('payams_complete') and left() > 900:
    nowi = flooded.rename('now')
    now30 = nowi.reproject('EPSG:4326', None, 30)
    schools_n = now30.reduceRegions(schools, ee.Reducer.max(), 30, tileScale=4)
    health_n = now30.reduceRegions(health, ee.Reducer.max(), 30, tileScale=4)
    n = payam.size().getInfo()
    lst = payam.toList(n)
    done = {} if REFRESH else (c.get('payams_now') or {})
    meta = payam.reduceColumns(ee.Reducer.toList(2), [A2, A3]).get('list').getInfo()
    todo = [i for i, (cn, pn) in enumerate(meta) if pn not in (done.get(cn) or {})]
    print(f'flooded-now: {len(meta) - len(todo)} payams already done, {len(todo)} to do')
    nrows = []
    road_now = None
    try:
        rd = ee.FeatureCollection(ROADS).filterBounds(payam.geometry())
        road_now = ee.Image().byte().paint(rd, 1, 1).unmask(0).reproject('EPSG:4326', None, 100)
    except Exception as e:
        print('roads unavailable (now):', str(e)[:120])
    for i in range(0, len(todo), CHUNK):
        if left() < 600:
            print('budget used up during the flooded-now table; it will continue on the next run'); break
        sub = ee.FeatureCollection([lst.get(j) for j in todo[i:i + CHUNK]])

        def pern(f):
            g = f.geometry()
            a = area.multiply(nowi).rename('an').reduceRegion(ee.Reducer.sum(), g, 100, maxPixels=1e10, tileScale=8)
            props = {'payam': f.get(A3), 'county': f.get(A2),
                     'area_now_km2': a.get('an'),
                     'schools_now': cnt(schools_n, g)[1], 'health_now': cnt(health_n, g)[1]}
            b = bld.filterBounds(g)
            props['buildings_now'] = ee.Number(ee.Algorithms.If(
                b.size().lt(40000), now30.reduceRegions(b, ee.Reducer.max(), 30, tileScale=8).filter(ee.Filter.gt('max', 0)).size(), -1))
            if road_now is not None:
                r = road_now.multiply(nowi.reproject('EPSG:4326', None, 100)).rename('rn').reduceRegion(
                    ee.Reducer.sum(), g, 100, maxPixels=1e10, tileScale=8)
                props['roads_now_km'] = ee.Number(r.get('rn')).multiply(0.1)
            return ee.Feature(None, props)
        for attempt in range(2):
            try:
                nrows += [r['properties'] for r in sub.map(pern).getInfo()['features']]
                break
            except Exception as e:
                print(f'  now payams {i}-{i + CHUNK} attempt {attempt + 1} failed: {str(e)[:200]}')
        print(f'flooded-now payams {min(i + CHUNK, len(todo))}/{len(todo)}', flush=True)
    if nrows:
        by = {k: dict(v) for k, v in done.items()}
        for r in nrows:
            by.setdefault(r['county'], {})[r['payam']] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()
                                                          if k not in ('county', 'payam')}
        c['payams_now'] = by
        c['now_complete'] = sum(len(v) for v in by.values()) >= 0.98 * n
        save(c)
        print('flooded-now table saved:', len(nrows), 'payams')

# --- 2. station exposure (25 km) -----------------------------------------------------------------------------------
ss = os.path.join(ALT, 'station_status.csv')
if not os.path.exists(ss):
    print('station_status.csv not found; station exposure skipped')
    sys.exit(0)
st = pd.read_csv(ss)
st = st[st['type'].astype(str).str.lower().eq('river')].dropna(subset=['latitude', 'longitude'])
age = (pd.Timestamp.utcnow().tz_localize(None).normalize() - pd.to_datetime(st['last_date'], errors='coerce')).dt.days
st = st[age <= 120]
todo = [r for r in st.to_dict('records') if r['station_uid'] not in c['stations']]
print(f'{len(st)} active river stations, {len(todo)} still to compute')
for rec in todo:
    if left() < 420:
        print('time budget used up; re-run to continue'); break
    uid = rec['station_uid']
    try:
        pt = ee.Geometry.Point([float(rec['longitude']), float(rec['latitude'])])
        buf = pt.buffer(BUF_M)
        here = payam.filterBounds(pt)
        b = bld.filterBounds(buf)
        nb = b.size()

        def prow(pf):
            pg = pf.geometry().intersection(buf, 200)
            p = wp.rename('p').reduceRegion(ee.Reducer.sum(), pg, 100, maxPixels=1e9, tileScale=4).get('p')
            pr = wp.multiply(risk).rename('p').reduceRegion(ee.Reducer.sum(), pg, 100, maxPixels=1e9, tileScale=4).get('p')
            s_t, s_r = cnt(schools_r, pg)
            h_t, h_r = cnt(health_r, pg)
            return ee.Feature(None, {'payam': pf.get(A3), 'county': pf.get(A2), 'pop': p, 'pop_risk': pr,
                                     'bld': b.filterBounds(pg).size(), 'sch': s_t, 'sch_r': s_r, 'hl': h_t, 'hl_r': h_r})
        d = ee.Dictionary({
            'county': ee.Algorithms.If(here.size().gt(0), ee.Feature(here.first()).get(A2), None),
            'payam': ee.Algorithms.If(here.size().gt(0), ee.Feature(here.first()).get(A3), None),
            'pop': wp.reduceRegion(ee.Reducer.sum(), buf, 100, maxPixels=1e9).get('population'),
            'pop_risk': wp.multiply(risk).reduceRegion(ee.Reducer.sum(), buf, 100, maxPixels=1e9, tileScale=4).get('population'),
            'schools': schools_r.filterBounds(buf).size(),
            'schools_risk': schools_r.filterBounds(buf).filter(ee.Filter.gt('max', 0)).size(),
            'health': health_r.filterBounds(buf).size(),
            'health_risk': health_r.filterBounds(buf).filter(ee.Filter.gt('max', 0)).size(),
            'buildings': nb,
            'buildings_risk': ee.Algorithms.If(nb.lt(40000), risk30.reduceRegions(b, ee.Reducer.max(), 30, tileScale=8)
                                               .filter(ee.Filter.gt('max', 0)).size(), -1),
            'counties': payam.filterBounds(buf).aggregate_array(A2).distinct().sort(),
            'payams': payam.filterBounds(buf).limit(16).map(prow).toList(16).map(lambda x: ee.Feature(x).toDictionary()),
        }).getInfo()
        d['payams'] = sorted(d.get('payams') or [], key=lambda r: -(r.get('pop') or 0))
        for k in ('pop', 'pop_risk'):
            d[k] = round(d[k]) if d.get(k) is not None else None
        c['stations'][uid] = d
        save(c)
        print(f"{uid}: {d.get('county')} pop {d.get('pop')} ({len(c['stations'])} stations done)", flush=True)
    except Exception as e:
        print(f'  {uid} failed: {str(e)[:200]}')
save(c)
print('done:', len(c['stations']), 'stations,', sum(len(v) for v in c['payams'].values()), 'payams in the cache')
