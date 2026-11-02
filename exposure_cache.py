# -*- coding: utf-8 -*-
"""
Earth Engine job behind the "infrastructure at risk" and "25 km exposure" sections of the county report pages.
Same definitions as the GEE app (gee.js): at risk = flooded now OR flooded in >= 15% of the same-season Sentinel-1 baseline years.

Writes data/exposure_cache.json:
  payams   {county: [ {payam, area_km2, area_risk_km2, schools, schools_risk, health, health_risk, buildings, buildings_risk,
                       roads_km, roads_risk_km} ]}
  county   {county: {schools, schools_risk, health, health_risk}}
  payams_pop {county: {payam: {pcode, pop, pop_risk, pop_now}}}   GHSL GHS-POP 2020 inside each payam and inside the at-risk / flooded-now area
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

# --- 1c. population per payam (GHSL GHS-POP 2020), with the payam code the Abuk app looks payams up by ----------------------
# Whole country, incremental like the flooded-now table. Adds c['payams_pop'] = {county: {payam: {pcode, pop, pop_risk, pop_now}}};
# every existing key is left as it was, so the county report and the other readers of this file are not affected.
# The WorldPop 100 m layer for South Sudan is smoothed (largest cell in Juba Town is 0.7 people), which left the towns at a few
# hundred people. GHSL GHS-POP R2023A keeps the urban peaks, so a cache built with another source is recomputed once.
POP_SOURCE = 'GHSL GHS-POP R2023A, 100 m, 2020'
c = load()
pop_stale = c.get('pop_source') != POP_SOURCE
if c.get('payams_complete') and (not c.get('pop_complete') or REFRESH or pop_stale) and left() > 900:
    ghs = ee.ImageCollection('JRC/GHSL/P2023A/GHS_POP').filter(ee.Filter.eq('system:index', '2020')).first().select('population_count')
    ghs_proj = ghs.projection()
    K_PCODE = next((k for k in keys if k.lower() in ('adm3_pcode', 'adm3_pcod', 'pcode3', 'pcode')), None)
    has_now = flooded is not None and risk_basis.startswith('Sentinel-1 same-season baseline +')
    popimg = ghs.rename('pop').addBands(ghs.multiply(risk).rename('pop_risk'))
    if has_now:
        popimg = popimg.addBands(ghs.multiply(flooded).rename('pop_now'))
    n = payam.size().getInfo()
    lst = payam.toList(n)
    done = {} if (REFRESH or pop_stale) else (c.get('payams_pop') or {})
    meta = payam.reduceColumns(ee.Reducer.toList(2), [A2, A3]).get('list').getInfo()
    todo = [i for i, (cn, pn) in enumerate(meta) if pn not in (done.get(cn) or {})]
    print(f'population: {len(meta) - len(todo)} payams already done, {len(todo)} to do; payam code field: {K_PCODE}')
    prow = []
    for i in range(0, len(todo), CHUNK):
        if left() < 600:
            print('budget used up during the population table; it will continue on the next run'); break
        sub = ee.FeatureCollection([lst.get(j) for j in todo[i:i + CHUNK]])

        def popf(f):
            s = popimg.reduceRegion(ee.Reducer.sum(), f.geometry(), crs=ghs_proj, maxPixels=1e10, tileScale=8)
            props = {'payam': f.get(A3), 'county': f.get(A2), 'pop': s.get('pop'), 'pop_risk': s.get('pop_risk')}
            if has_now:
                props['pop_now'] = s.get('pop_now')
            if K_PCODE:
                props['pcode'] = f.get(K_PCODE)
            return ee.Feature(None, props)
        for attempt in range(2):
            try:
                prow += [r['properties'] for r in sub.map(popf).getInfo()['features']]
                break
            except Exception as e:
                print(f'  population payams {i}-{i + CHUNK} attempt {attempt + 1} failed: {str(e)[:200]}')
        print(f'population payams {min(i + CHUNK, len(todo))}/{len(todo)}', flush=True)
    if prow:
        by = {k: dict(v) for k, v in done.items()}
        for r in prow:
            by.setdefault(r['county'], {})[r['payam']] = {k: (round(v) if isinstance(v, float) else v) for k, v in r.items()
                                                          if k not in ('county', 'payam') and v is not None}
        c['payams_pop'] = by
        c['pop_source'] = POP_SOURCE
        c['pop_complete'] = sum(len(v) for v in by.values()) >= 0.98 * n
        save(c)
        print('population table saved:', len(prow), 'payams')

# --- 1d. 2025 population (project asset, 40 m) and facilities by "Facility subtype" per payam -------------------------------
# Adds c['payams_new'] = {county: {payam: {pcode, pop25, pop25_risk, pop25_now, fac_t, fac_r, fac_n}}}; fac_* map each facility subtype to
# the number of facilities in the payam (t), inside the at-risk area (r) and inside the current flood extent (n). Incremental like 1c.
POP25 = 'projects/ee-penuelabi/assets/SSD_2025q2_populacehealthdataorg'
FACILITIES = 'projects/ee-penuelabi/assets/SSD_Facilities'
SUBTYPE = 'Facility subtype'
NEW_SOURCE = 'SSD_2025q2_populacehealthdataorg (40 m, April 2025); SSD_Facilities by Facility subtype'
c = load()
if c.get('payams_complete') and (not c.get('new_complete') or c.get('new_source') != NEW_SOURCE or REFRESH) and left() > 900:
    K_PCODE = next((k for k in keys if k.lower() in ('adm3_pcode', 'adm3_pcod', 'pcode3', 'pcode')), None)
    has_now = flooded is not None and risk_basis.startswith('Sentinel-1 same-season baseline +')
    p25 = ee.Image(POP25).select(0)
    p25_proj = p25.projection()
    p25img = p25.rename('pop25').addBands(p25.multiply(risk).rename('pop25_risk'))
    fac = ee.FeatureCollection(FACILITIES).select([SUBTYPE])
    if has_now:
        p25img = p25img.addBands(p25.multiply(flooded).rename('pop25_now'))
        flood30 = flooded.reproject('EPSG:4326', None, 30)
    n = payam.size().getInfo()
    lst = payam.toList(n)
    stale = c.get('new_source') != NEW_SOURCE
    done = {} if (REFRESH or stale) else (c.get('payams_new') or {})
    meta = payam.reduceColumns(ee.Reducer.toList(2), [A2, A3]).get('list').getInfo()
    by = {k: dict(v) for k, v in done.items()}
    CHUNK_NEW = int(os.environ.get('EXPOSURE_CHUNK_NEW', '4'))  # each payam runs three facility aggregations; 20 at once is "too many concurrent aggregations"

    def newf(f):
        g = f.geometry()
        s = p25img.reduceRegion(ee.Reducer.sum(), g, crs=p25_proj, maxPixels=1e10, tileScale=8)
        fs = risk30.reduceRegions(fac.filterBounds(g), ee.Reducer.max().setOutputs(['r']), 30, tileScale=4)
        if has_now:
            fs = flood30.reduceRegions(fs, ee.Reducer.max().setOutputs(['n']), 30, tileScale=4)
        props = {'payam': f.get(A3), 'county': f.get(A2), 'pop25': s.get('pop25'), 'pop25_risk': s.get('pop25_risk'),
                 'fac_t': fs.aggregate_histogram(SUBTYPE),
                 'fac_r': fs.filter(ee.Filter.gt('r', 0)).aggregate_histogram(SUBTYPE)}
        if has_now:
            props['pop25_now'] = s.get('pop25_now')
            props['fac_n'] = fs.filter(ee.Filter.gt('n', 0)).aggregate_histogram(SUBTYPE)
        if K_PCODE:
            props['pcode'] = f.get(K_PCODE)
        return ee.Feature(None, props)

    saved = 0
    for sweep in range(3):  # payams that failed are tried again once the load has dropped
        todo = [i for i, (cn, pn) in enumerate(meta) if pn not in (by.get(cn) or {})]
        print(f'2025 population and facilities, pass {sweep + 1}: {len(meta) - len(todo)} payams done, {len(todo)} to do')
        if not todo or left() < 600:
            break
        got_any = False
        for i in range(0, len(todo), CHUNK_NEW):
            if left() < 600:
                print('budget used up during the 2025 table; it will continue on the next run'); break
            sub = ee.FeatureCollection([lst.get(j) for j in todo[i:i + CHUNK_NEW]])
            for attempt in range(3):
                try:
                    for r in [x['properties'] for x in sub.map(newf).getInfo()['features']]:
                        by.setdefault(r['county'], {})[r['payam']] = {k: (round(v) if isinstance(v, float) else v) for k, v in r.items()
                                                                      if k not in ('county', 'payam') and v is not None}
                        saved += 1
                    got_any = True
                    break
                except Exception as e:
                    print(f'  2025 payams {i}-{i + CHUNK_NEW} attempt {attempt + 1} failed: {str(e)[:120]}')
                    time.sleep(15 * (attempt + 1))
            if (i // CHUNK_NEW) % 10 == 9:
                print(f'2025 payams {min(i + CHUNK_NEW, len(todo))}/{len(todo)}', flush=True)
                c['payams_new'], c['new_source'] = by, NEW_SOURCE
                c['new_complete'] = sum(len(v) for v in by.values()) >= 0.98 * n
                save(c)
        if not got_any:
            break
    if saved:
        c['payams_new'] = by
        c['new_source'] = NEW_SOURCE
        c['new_complete'] = sum(len(v) for v in by.values()) >= 0.98 * n
        save(c)
        print('2025 table saved:', saved, 'payams;', sum(len(v) for v in by.values()), 'of', n, 'in the table')

# --- 1e. which river stations are upstream of, in, or downstream of each payam and county (HydroBASINS network) ----------------
# Writes station_relation.csv (place, pcode, county, station_uid, relation, distance_km) for the REL_NEAREST stations nearest to each
# payam and county that sit on its river network; the Abuk app reads it to say "upstream of / mid-stream in / downstream of".
# Same rule as county_station_link.py: station basin inside the place's upstream catchment = upstream, the place's basin inside the
# station's upstream catchment = downstream, same level-6 basin = local (mid-stream).
REL_OUT = os.path.join(os.environ.get('EXPOSURE_OUT_DIR', os.path.join(HERE, 'exposure_out')), 'station_relation.csv')
HYBAS_LEVEL, REL_NEAREST = 6, 12


def station_relations():
    import math
    ssp = os.path.join(ALT, 'station_status.csv')
    if not os.path.exists(ssp):
        print('station relations skipped: station_status.csv not found'); return
    stt = pd.read_csv(ssp)
    stt = stt[stt['type'].astype(str).str.lower().eq('river')].dropna(subset=['latitude', 'longitude']).drop_duplicates('station_uid')
    k_pcode = next((k for k in keys if k.lower() in ('adm3_pcode', 'adm3_pcod', 'pcode3', 'pcode')), None)
    hb = (ee.FeatureCollection(f'WWF/HydroSHEDS/v1/Basins/hybas_{HYBAS_LEVEL}')
          .filterBounds(ee.Geometry.Rectangle([21.0, -12.0, 42.0, 24.5])))
    children = {}
    for hid, nd in hb.reduceColumns(ee.Reducer.toList(2), ['HYBAS_ID', 'NEXT_DOWN']).get('list').getInfo():
        children.setdefault(int(nd), []).append(int(hid))

    def trace(start):
        seen, stack = {int(start)}, [int(start)]
        while stack:
            for ch in children.get(stack.pop(), []):
                if ch not in seen:
                    seen.add(ch); stack.append(ch)
        return seen

    def basins(feats):
        out = {}
        for i in range(0, len(feats), 300):
            pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(f['lon']), float(f['lat'])]), {'id': f['id']}) for f in feats[i:i + 300]])
            joined = ee.Join.saveFirst('basin').apply(pts, hb, ee.Filter.intersects(leftField='.geo', rightField='.geo'))
            for h in joined.map(lambda f: ee.Feature(None, {'id': f.get('id'), 'hybas': ee.Feature(f.get('basin')).get('HYBAS_ID')})).getInfo()['features']:
                if h['properties'].get('hybas') is not None:
                    out[h['properties']['id']] = int(h['properties']['hybas'])
        return out

    sb = basins([{'id': r.station_uid, 'lon': r.longitude, 'lat': r.latitude} for r in stt.itertuples()])
    sup = {}
    cp = os.path.join(ALT, 'cache_station_catchments.csv')
    if os.path.exists(cp):
        for r in pd.read_csv(cp, dtype={'hybas_ids': str}).itertuples():
            ids = {int(x) for x in str(r.hybas_ids).split(';') if x}
            if ids:
                sup[r.station_uid] = ids
    for uid, b in sb.items():
        sup.setdefault(uid, trace(b))

    cen = payam.map(lambda f: ee.Feature(f.geometry().centroid(100), {'pcode': f.get(k_pcode) if k_pcode else f.get(A3), 'county': f.get(A2)})).getInfo()['features']
    places = [{'kind': 'payam', 'pcode': f['properties']['pcode'], 'county': f['properties']['county'], 'lon': f['geometry']['coordinates'][0], 'lat': f['geometry']['coordinates'][1]} for f in cen]
    by_county = {}
    for pl in places:
        by_county.setdefault(pl['county'], []).append(pl)
    for cty, lst in by_county.items():  # the county point is the payam centre closest to the average of its payam centres, so it lies inside the county
        mx, my = sum(p['lon'] for p in lst) / len(lst), sum(p['lat'] for p in lst) / len(lst)
        best = min(lst, key=lambda p: (p['lon'] - mx) ** 2 + (p['lat'] - my) ** 2)
        places.append({'kind': 'county', 'pcode': str(best['pcode'])[:6], 'county': cty, 'lon': best['lon'], 'lat': best['lat']})  # ADM2 code, e.g. SS0305
    for i, pl in enumerate(places):
        pl['id'] = str(i)
    pb = basins(places)

    def km(a, b, c, d):
        p1, p2, dl = math.radians(b), math.radians(d), math.radians(c - a)
        return 6371 * 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))

    rows = []
    for pl in places:
        base = pb.get(pl['id'])
        if base is None:
            continue
        up = trace(base)
        near = sorted(stt.itertuples(), key=lambda r: km(pl['lon'], pl['lat'], r.longitude, r.latitude))[:REL_NEAREST]
        for r in near:
            sbase = sb.get(r.station_uid)
            if sbase is None:
                continue
            rel = 'local' if sbase == base else 'upstream' if sbase in up else 'downstream' if base in sup.get(r.station_uid, set()) else None
            if rel:
                rows.append({'place': pl['kind'], 'pcode': pl['pcode'], 'county': pl['county'], 'station_uid': r.station_uid,
                             'relation': rel, 'distance_km': round(km(pl['lon'], pl['lat'], r.longitude, r.latitude), 1)})
    os.makedirs(os.path.dirname(REL_OUT), exist_ok=True)
    pd.DataFrame(rows, columns=['place', 'pcode', 'county', 'station_uid', 'relation', 'distance_km']).to_csv(REL_OUT, index=False)
    print(f'station relations: {len(rows)} links for {len(places)} places and {len(sb)} river stations -> {REL_OUT}',
          pd.Series([r['relation'] for r in rows]).value_counts().to_dict())


try:
    station_relations()
except Exception:
    print('station relations failed (the app then shows no upstream / downstream label):')
    traceback.print_exc()

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
