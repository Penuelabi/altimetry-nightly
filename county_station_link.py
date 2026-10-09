# -*- coding: utf-8 -*-
"""
Link every county to the most relevant altimetry gauge (DAHITI / Hydroweb),
even when the nearest station is far away, so each county page can show a river
water-level reading.

Selection order (hydrologically first, distance only as a tie-break):
  1. UPSTREAM gauge   - the gauge's basin lies inside the county's upstream
                        catchment, so a rise there forewarns the county.
  2. DOWNSTREAM gauge - the county drains into the gauge (county basin is in the
                        gauge's upstream catchment).
  3. SAME-RIVER gauge - same river_key (BASIN|RIVER) but not directly up/down.
  4. NEAREST off-basin - last resort, flagged "indicative", so no county is blank.

"Upstream / downstream" use the HydroBASINS level-6 NEXT_DOWN network - the same
tracing build_catchments() in merge_dahiti_hydroweb.py uses. Station upstream
sets are reused from cache_station_catchments.csv when present; county upstream
sets are cached in cache_county_catchments.csv. If Earth Engine is unavailable,
the module falls back to nearest-by-distance with latitude-based position.

Inputs  : merged_altimetry_stations.csv, station_status.csv   (ALTIMETRY_OUT_DIR)
          counties_dissolved.geojson                          (BULLETIN_OUT_DIR)
Output  : county_station_link.csv                             (BULLETIN_OUT_DIR)
          columns: county, state, station_uid, station_name, river, relation,
                   confidence, distance_km, last_date, last_level_m, flood_status,
                   seasonal_pctile, rate_m_per_day
"""
import os
import sys

import numpy as np
import pandas as pd

LEVEL_COL = 'Water Surface Elevation - values(m)'
HYBAS_LEVEL = 6
CATCHMENT_BBOX = [21.0, -12.0, 42.0, 24.5]           # Nile basin incl. Lake Victoria basin to the south
METRIC_CRS = 32636                                   # UTM 36N - metres over South Sudan
LOCAL_BAND_DEG = 0.15                                # fallback only: |dlat| below this = "local"

ALT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', '.')
BUL_DIR = os.environ.get('BULLETIN_OUT_DIR', '.')
STATION_CATCH_CACHE = os.path.join(ALT_DIR, 'cache_station_catchments.csv')
COUNTY_CATCH_CACHE = os.path.join(ALT_DIR, 'cache_county_catchments.csv')

OUT_COLS = ['county', 'state', 'station_uid', 'station_name', 'river', 'relation',
            'confidence', 'distance_km', 'last_date', 'last_level_m', 'flood_status',
            'seasonal_pctile', 'rate_m_per_day']

CONFIDENCE = {'upstream': 'high', 'local': 'high', 'downstream': 'high',
              'same-river': 'medium', 'nearest': 'indicative'}
RELATION_RANK = {'upstream': 0, 'local': 1, 'downstream': 2, 'same-river': 3, 'nearest': 4}


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #
def _river_name(river_key):
    """'BASIN|RIVER' -> 'River' (title case); blank when unknown."""
    if not isinstance(river_key, str) or '|' not in river_key:
        return ''
    riv = river_key.split('|', 1)[1].strip()
    return riv.title() if riv else ''


def load_stations():
    """One row per river gauge: uid, name, lat, lon, river_key, + latest reading.
    Tolerant of optional columns (river_key / location / type may be absent in the CSV)."""
    master = os.path.join(ALT_DIR, 'merged_altimetry_stations.csv')
    df = pd.read_csv(master, low_memory=False)
    print('county_station_link: merged columns ->', list(df.columns)[:40])
    df = df.dropna(subset=['latitude', 'longitude'])
    if 'type' in df.columns:
        df = df[~df['type'].astype(str).str.lower().eq('lake')]
    if 'date' in df.columns:
        df = df.sort_values('date')
    agg = {'latitude': ('latitude', 'median'), 'longitude': ('longitude', 'median')}
    if 'river_key' in df.columns:
        agg['river_key'] = ('river_key', 'first')
    name_col = next((c for c in ('location/river_name', 'location', 'river_name', 'name',
                                 'Target Name', 'station_name') if c in df.columns), None)
    if name_col:
        agg['station_name'] = (name_col, 'first')
    st = df.groupby('station_uid').agg(**agg).reset_index()
    if 'river_key' not in st.columns:
        st['river_key'] = ''
    if 'station_name' not in st.columns:
        st['station_name'] = st['station_uid']
    st['river_key'] = st['river_key'].fillna('')
    st['station_name'] = st['station_name'].fillna(st['station_uid']).astype(str).str.strip()
    # river label: from river_key (BASIN|RIVER) when present, else the station's own name/river text
    st['river'] = st['river_key'].map(_river_name)
    st.loc[st['river'].eq(''), 'river'] = st['station_name']

    status_path = os.path.join(ALT_DIR, 'station_status.csv')
    if os.path.exists(status_path):
        ss = pd.read_csv(status_path)
        keep = [c for c in ('station_uid', 'last_date', 'last_level_m', 'flood_status',
                            'seasonal_pctile', 'rate_m_per_day') if c in ss.columns]
        st = st.merge(ss[keep], on='station_uid', how='left')
    for c in ('last_date', 'last_level_m', 'flood_status', 'seasonal_pctile', 'rate_m_per_day'):
        if c not in st.columns:
            st[c] = np.nan
    return st


def load_counties():
    import geopandas as gpd
    path = os.path.join(BUL_DIR, 'counties_dissolved.geojson')
    gdf = gpd.read_file(path)
    if 'county' not in gdf.columns:
        for alt in ('County', 'NAME', 'admin2Name', 'ADM2_EN'):
            if alt in gdf.columns:
                gdf = gdf.rename(columns={alt: 'county'})
                break
    state_col = next((c for c in ('state', 'State', 'admin1Name', 'ADM1_EN') if c in gdf.columns), None)
    gdf['state'] = gdf[state_col] if state_col else ''
    return gdf[['county', 'state', 'geometry']].set_crs(4326, allow_override=True)


# --------------------------------------------------------------------------- #
# HydroBASINS upstream sets (station + county) via Earth Engine
# --------------------------------------------------------------------------- #
def _children_map(hb):
    """HYBAS_ID -> list of basins that flow directly into it (from NEXT_DOWN)."""
    pairs = hb.reduceColumns(__import__('ee').Reducer.toList(2), ['HYBAS_ID', 'NEXT_DOWN']).get('list').getInfo()
    children = {}
    for hid, nd in pairs:
        children.setdefault(int(nd), []).append(int(hid))
    return children


def _trace_up(start, children):
    """All basins upstream of (and including) `start`."""
    seen, stack = {int(start)}, [int(start)]
    while stack:
        cur = stack.pop()
        for ch in children.get(cur, []):
            if ch not in seen:
                seen.add(ch)
                stack.append(ch)
    return seen


def _point_basins(ee, hb, feats):
    """[{id, lon, lat}] -> {id: HYBAS_ID} via point-in-basin join."""
    pts = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([float(f['lon']), float(f['lat'])]), {'id': f['id']}) for f in feats])
    joined = ee.Join.saveFirst('basin').apply(
        pts, hb, ee.Filter.intersects(leftField='.geo', rightField='.geo'))
    hits = joined.map(lambda f: ee.Feature(None, {
        'id': f.get('id'), 'hybas': ee.Feature(f.get('basin')).get('HYBAS_ID')})).getInfo()['features']
    return {h['properties']['id']: int(h['properties']['hybas']) for h in hits
            if h['properties'].get('hybas') is not None}


def build_catchment_sets(stations, counties):
    """
    Return (station_up, station_base, county_up, county_base):
      *_up   : id -> set of upstream HYBAS_IDs (incl. own basin)
      *_base : id -> own HYBAS_ID
    Uses caches where possible; computes the rest in Earth Engine. Returns None on failure.
    """
    import ee
    from ee_util import init_ee
    try:
        init_ee()
        hb = (ee.FeatureCollection(f'WWF/HydroSHEDS/v1/Basins/hybas_{HYBAS_LEVEL}')
              .filterBounds(ee.Geometry.Rectangle(CATCHMENT_BBOX)))
        children = _children_map(hb)
    except Exception as e:
        print(f"county_station_link: Earth Engine / HydroBASINS unavailable ({type(e).__name__}: {e}); "
              "using distance-only fallback.")
        return None

    # stations: reuse cached upstream sets; trace basin for each from the smallest cached basin is not
    # possible, so (re)derive base basins for all stations and reuse cached upstream sets by uid.
    station_up, station_base = {}, {}
    cache = pd.read_csv(STATION_CATCH_CACHE, dtype={'hybas_ids': str}) if os.path.exists(STATION_CATCH_CACHE) else None
    if cache is not None:
        for r in cache.itertuples():
            ids = [int(x) for x in str(r.hybas_ids).split(';') if x]
            if ids:
                station_up[r.station_uid] = set(ids)

    st_feats = [{'id': r.station_uid, 'lon': r.longitude, 'lat': r.latitude} for r in stations.itertuples()]
    station_base = _point_basins(ee, hb, st_feats)
    # any station without a cached upstream set: trace it now
    for uid, base in station_base.items():
        if uid not in station_up:
            station_up[uid] = _trace_up(base, children)

    # counties: cache by name
    county_up, county_base = {}, {}
    ccache = pd.read_csv(COUNTY_CATCH_CACHE, dtype={'hybas_ids': str}) if os.path.exists(COUNTY_CATCH_CACHE) else None
    if ccache is not None:
        for r in ccache.itertuples():
            ids = [int(x) for x in str(r.hybas_ids).split(';') if x]
            if ids:
                county_up[r.county] = set(ids)
            county_base[r.county] = int(r.hybas_id) if not pd.isna(r.hybas_id) else None

    reps = counties.copy()
    reps['rep'] = reps.geometry.representative_point()
    todo = [{'id': r.county, 'lon': r.rep.x, 'lat': r.rep.y}
            for r in reps.itertuples() if r.county not in county_base]
    if todo:
        new_base = _point_basins(ee, hb, todo)
        rows = []
        for cty, base in new_base.items():
            county_base[cty] = base
            county_up[cty] = _trace_up(base, children)
            rows.append({'county': cty, 'hybas_id': base, 'hybas_ids': ';'.join(map(str, sorted(county_up[cty])))})
        if rows:
            allrows = (ccache.to_dict('records') if ccache is not None else []) + rows
            pd.DataFrame(allrows).drop_duplicates('county', keep='last').to_csv(COUNTY_CATCH_CACHE, index=False)
            print(f"county_station_link: traced {len(rows)} new county catchments -> {COUNTY_CATCH_CACHE}")
    return station_up, station_base, county_up, county_base


# --------------------------------------------------------------------------- #
# matching
# --------------------------------------------------------------------------- #
def _distances_km(counties, stations):
    """DataFrame county x station of min polygon-to-point distance in km."""
    import geopandas as gpd
    pts = gpd.GeoDataFrame(stations[['station_uid']],
                           geometry=gpd.points_from_xy(stations['longitude'], stations['latitude']),
                           crs=4326).to_crs(METRIC_CRS)
    cty = counties.to_crs(METRIC_CRS)
    out = {}
    for c in cty.itertuples():
        d = pts.geometry.distance(c.geometry) / 1000.0
        out[c.county] = dict(zip(pts['station_uid'].values, np.round(d.values, 1)))
    return out


def _network_relation(county, uid, sets):
    """upstream / downstream / None from the HydroBASINS network (None if not connected)."""
    station_up, station_base, county_up, county_base = sets
    s_base = station_base.get(uid)
    c_base = county_base.get(county)
    if s_base is None or c_base is None or s_base == c_base:
        return 'local' if (s_base is not None and s_base == c_base) else None
    if s_base in county_up.get(county, set()):
        return 'upstream'
    if c_base in station_up.get(uid, set()):
        return 'downstream'
    return None


def apply_overrides(out, stations):
    """Audited overrides (aa_config/county_station_override.csv): county -> gauge, from the p7 audit.
    The network ranking prefers an 'upstream' gauge even when it is 100+ km from the county; an override
    pins a gauge that sits on or next to the county. Missing gauges in this run are skipped."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'aa_config', 'county_station_override.csv')
    if not os.path.exists(path):
        return out
    ov = pd.read_csv(path)
    st = stations.set_index('station_uid')
    out = out.copy()
    n = 0
    for r in ov.itertuples():
        if r.station_uid not in st.index:
            continue
        m = out['county'].astype(str).str.lower() == str(r.county).lower()
        if not m.any():
            continue
        s = st.loc[r.station_uid]
        for col, val in (('station_uid', r.station_uid), ('station_name', s['station_name']), ('river', s['river']),
                         ('relation', 'audit-override'), ('confidence', 'medium'),
                         ('distance_km', r.distance_km), ('last_date', s['last_date']),
                         ('last_level_m', s['last_level_m']), ('flood_status', s['flood_status']),
                         ('seasonal_pctile', s['seasonal_pctile']), ('rate_m_per_day', s['rate_m_per_day'])):
            out.loc[m, col] = val
        n += 1
    print(f"county_station_link: applied {n} audited gauge overrides")
    return out


def match(stations, counties, sets):
    dist = _distances_km(counties, stations)
    rows = []
    for c in counties.itertuples():
        county = c.county
        dmap = dist.get(county, {})
        scored = []          # (relation, distance_km, station_row)
        on_net_rivers = set()
        for s in stations.itertuples():
            dk = dmap.get(s.station_uid)
            if dk is None:
                continue
            rel = _network_relation(county, s.station_uid, sets) if sets is not None else None
            if rel in ('upstream', 'downstream', 'local'):
                if isinstance(s.river_key, str) and s.river_key.strip():
                    on_net_rivers.add(s.river_key)
            scored.append([rel, dk, s])
        if not scored:
            rows.append(dict(county=county, state=getattr(c, 'state', ''), station_uid=None,
                             station_name='no gauge', river='', relation='none', confidence='none',
                             distance_km=np.nan, last_date=None, last_level_m=np.nan,
                             flood_status=None, seasonal_pctile=np.nan, rate_m_per_day=np.nan))
            continue
        # fill in same-river / nearest for stations the network did not connect
        cands = []
        for rel, dk, s in scored:
            if rel is None:
                rel = 'same-river' if (isinstance(s.river_key, str) and s.river_key in on_net_rivers) else 'nearest'
            cands.append((RELATION_RANK[rel], dk, rel, s))
        cands.sort(key=lambda t: (t[0], t[1]))
        _, dk, rel, s = cands[0]
        rows.append(dict(
            county=county, state=getattr(c, 'state', ''), station_uid=s.station_uid,
            station_name=s.station_name, river=s.river, relation=rel, confidence=CONFIDENCE[rel],
            distance_km=dk, last_date=s.last_date, last_level_m=s.last_level_m,
            flood_status=s.flood_status, seasonal_pctile=s.seasonal_pctile, rate_m_per_day=s.rate_m_per_day))
    return pd.DataFrame(rows, columns=OUT_COLS)


# --------------------------------------------------------------------------- #
def export_link_asset(out, counties):
    """Publish the county->gauge link as a public Earth Engine table asset for the GEE app popup."""
    import ee
    from ee_util import ASSET_FOLDER, export_table
    reps = counties.to_crs(4326).copy()
    reps['geometry'] = reps.geometry.representative_point()
    cen = {r.county: (float(r.geometry.x), float(r.geometry.y)) for r in reps.itertuples()}
    feats = []
    for r in out.to_dict('records'):
        if not r.get('station_uid'):
            continue
        props = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()}
        xy = cen.get(r['county'])
        feats.append(ee.Feature(ee.Geometry.Point(list(xy)) if xy else None, props))
    if not feats:
        return
    asset_id = f"{ASSET_FOLDER}/county_gauge_link"
    if export_table(ee.FeatureCollection(feats), asset_id, 'county to gauge link', public=True):
        print(f"county_station_link: exported EE asset {asset_id} ({len(feats)} counties)")


def build():
    stations = load_stations()
    counties = load_counties()
    print(f"county_station_link: {len(stations)} river gauges, {len(counties)} counties")
    try:
        sets = build_catchment_sets(stations, counties)
    except Exception as e:
        print(f"county_station_link: catchment step failed ({type(e).__name__}: {e}); distance-only fallback.")
        sets = None
    out = apply_overrides(match(stations, counties, sets), stations)
    path = os.path.join(BUL_DIR, 'county_station_link.csv')
    out.to_csv(path, index=False)
    tier = out['relation'].value_counts().to_dict()
    print(f"county_station_link: wrote {path}  ({tier})")
    if sets is not None:                      # EE is up -> publish the app asset
        try:
            export_link_asset(out, counties)
        except Exception as e:
            print(f"county_station_link: EE asset export skipped ({type(e).__name__}: {e})")
    return out, path


def apply_only():
    """Re-apply the audited overrides to the existing link file (no Earth Engine needed)."""
    here = os.path.dirname(os.path.abspath(__file__))
    src = next((p for p in (os.path.join(BUL_DIR, 'county_station_link.csv'),
                            os.path.join(here, 'county_station_link.csv')) if os.path.exists(p)), None)
    if not src:
        print('county_station_link: no link file to patch')
        return
    out = apply_overrides(pd.read_csv(src), load_stations())
    out.to_csv(os.path.join(BUL_DIR, 'county_station_link.csv'), index=False)
    print(f"county_station_link: patched link file written ({src} -> {BUL_DIR})")


if __name__ == '__main__':
    if '--apply-only' in sys.argv:
        try:
            apply_only()
        except Exception as e:
            print(f"WARNING: override step failed ({type(e).__name__}: {e})")
        sys.exit(0)
    try:
        build()
    except Exception as e:
        print(f"WARNING: county_station_link failed ({type(e).__name__}: {e})")
        sys.exit(0)
