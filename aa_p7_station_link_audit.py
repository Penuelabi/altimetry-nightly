# -*- coding: utf-8 -*-
"""
AA ADD-ON 7: audit of the county -> river gauge link.

For every county this checks the gauge chosen by county_station_link.py against the real geometry:
  * distance from the gauge to the county polygon (0 = the gauge is inside the county), in km, in UTM 36N
  * the nearest gauges to the county polygon, with the age of their latest reading
  * whether a clearly closer and fresher gauge exists (a gauge on the river line next to the county)
Counties along the river line (Bor South, Duk, Twic East, ...) often get a "local" gauge that is
100+ km away although a gauge sits on the nearby river reach; those are flagged for review.

Nothing is changed in county_station_link.csv. The audit only reports; review the flagged rows and
change the link (or its confidence) deliberately.

Inputs  merged_altimetry_stations.csv, station_status.csv (ALTIMETRY_OUT_DIR)
        counties_dissolved.geojson (BULLETIN_OUT_DIR), county_station_link.csv (BULLETIN_OUT_DIR or repo root)
Outputs aa_out/p7_county_station_audit.csv, aa_out/p7_county_station_audit.md
Run     python aa_p7_station_link_audit.py            (--selftest uses made-up data)
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))
BUL_DIR = os.environ.get('BULLETIN_OUT_DIR', os.path.join(HERE, 'bulletin'))
ALT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', os.path.join(HERE, 'altdata'))
METRIC_CRS = 32636
FAR_KM = 100.0          # linked gauge farther than this from the county polygon = review
NEAR_KM = 10.0          # a gauge this close counts as "on the county"
GAIN_KM = 25.0          # an alternative must be at least this much closer to count as better
FRESH_DAYS = 30         # a "fresh" gauge has a reading this recent
NEAR_LIST = 3


def first_existing(*paths):
    return next((p for p in paths if p and os.path.exists(p)), None)


def norm(s):
    return ''.join(ch for ch in str(s).lower() if ch.isalnum())


def load_stations(alt_dir):
    df = pd.read_csv(os.path.join(alt_dir, 'merged_altimetry_stations.csv'), low_memory=False)
    df = df.dropna(subset=['latitude', 'longitude'])
    if 'type' in df.columns:
        df = df[~df['type'].astype(str).str.lower().eq('lake')]
    name_col = next((c for c in ('location/river_name', 'location', 'river_name', 'name', 'Target Name',
                                 'station_name') if c in df.columns), None)
    agg = {'latitude': ('latitude', 'median'), 'longitude': ('longitude', 'median')}
    if 'river_key' in df.columns:
        agg['river_key'] = ('river_key', 'first')
    if name_col:
        agg['station_name'] = (name_col, 'first')
    st = df.groupby('station_uid').agg(**agg).reset_index()
    for c in ('river_key', 'station_name'):
        if c not in st.columns:
            st[c] = ''
    st['river_key'] = st['river_key'].fillna('')
    st['station_name'] = st['station_name'].fillna(st['station_uid']).astype(str)
    sp = os.path.join(alt_dir, 'station_status.csv')
    if os.path.exists(sp):
        ss = pd.read_csv(sp)
        keep = [c for c in ('station_uid', 'last_date', 'last_level_m') if c in ss.columns]
        st = st.merge(ss[keep], on='station_uid', how='left')
    for c in ('last_date', 'last_level_m'):
        if c not in st.columns:
            st[c] = np.nan
    return st


def audit(stations, counties, link, today):
    import geopandas as gpd
    pts = gpd.GeoDataFrame(stations.copy(), geometry=gpd.points_from_xy(stations.longitude, stations.latitude),
                           crs=4326).to_crs(METRIC_CRS)
    pts['age_days'] = (today - pd.to_datetime(pts['last_date'], errors='coerce')).dt.days
    cty = counties.to_crs(METRIC_CRS)
    cty['key'] = cty['county'].map(norm)
    link = link.copy()
    link['key'] = link['county'].map(norm)
    lk = link.set_index('key')
    rows = []
    for c in cty.itertuples():
        d = pts.geometry.distance(c.geometry) / 1000.0
        cand = pts.assign(dist_km=d.values).sort_values('dist_km')
        near = cand.head(NEAR_LIST)
        row = {'county': c.county, 'state': getattr(c, 'state', '')}
        cur = None
        if c.key in lk.index:
            L = lk.loc[c.key]
            cur_uid = L['station_uid']
            m = cand[cand['station_uid'] == cur_uid]
            cur = m.iloc[0] if len(m) else None
            row.update(linked_station=L.get('station_name', cur_uid), linked_uid=cur_uid,
                       relation=L.get('relation', ''), confidence=L.get('confidence', ''),
                       link_csv_distance_km=L.get('distance_km', np.nan))
        else:
            row.update(linked_station='', linked_uid='', relation='', confidence='', link_csv_distance_km=np.nan)
        row['linked_to_polygon_km'] = round(float(cur['dist_km']), 1) if cur is not None else np.nan
        row['linked_inside_county'] = bool(cur is not None and cur['dist_km'] <= 0.5)
        row['linked_age_days'] = float(cur['age_days']) if cur is not None and pd.notna(cur['age_days']) else np.nan
        row['linked_river_key'] = cur['river_key'] if cur is not None else ''
        for i, n in enumerate(near.itertuples(), 1):
            row[f'near{i}_station'] = n.station_name
            row[f'near{i}_km'] = round(float(n.dist_km), 1)
            row[f'near{i}_age_days'] = float(n.age_days) if pd.notna(n.age_days) else np.nan
            row[f'near{i}_river_key'] = n.river_key
        # best alternative: the nearest gauge with a fresh reading
        fresh = cand[(cand['age_days'] <= FRESH_DAYS) & (cand['station_uid'] != row['linked_uid'])]
        alt = fresh.iloc[0] if len(fresh) else None
        row['alt_station'] = alt['station_name'] if alt is not None else ''
        row['alt_uid'] = alt['station_uid'] if alt is not None else ''
        row['alt_km'] = round(float(alt['dist_km']), 1) if alt is not None else np.nan
        row['alt_age_days'] = float(alt['age_days']) if alt is not None else np.nan
        row['alt_same_river'] = bool(alt is not None and cur is not None and alt['river_key'] != ''
                                     and alt['river_key'] == cur['river_key'])
        # verdict
        flags = []
        lk_km = row['linked_to_polygon_km']
        if cur is None:
            flags.append('no gauge linked')
        else:
            if lk_km > FAR_KM:
                flags.append(f'linked gauge {lk_km:.0f} km from the county')
            if pd.notna(row['linked_age_days']) and row['linked_age_days'] > FRESH_DAYS:
                flags.append(f"linked reading {row['linked_age_days']:.0f} days old")
            if pd.isna(row['linked_age_days']):
                flags.append('linked gauge has no reading date')
            if alt is not None and (lk_km - row['alt_km']) >= GAIN_KM:
                flags.append(f"closer fresh gauge {alt['station_name']} ({row['alt_km']:.0f} km)")
        row['flags'] = '; '.join(flags)
        if cur is None:
            row['verdict'] = 'NO LINK'
        elif lk_km <= NEAR_KM and not any('days old' in f for f in flags):
            row['verdict'] = 'OK (gauge on the county)'
        elif not flags:
            row['verdict'] = 'OK'
        elif any(f.startswith('closer fresh') for f in flags) or any('km from' in f for f in flags):
            row['verdict'] = 'REVIEW LINK'
        else:
            row['verdict'] = 'REVIEW DATA AGE'
        rows.append(row)
    return pd.DataFrame(rows)


def downgrade(conf, flags_text, lk_km, age):
    """One step down per problem: far from the county, or reading older than FRESH_DAYS (no reading = old)."""
    order = ['high', 'medium', 'low']
    c = str(conf).strip().lower()
    i = order.index(c) if c in order else 1
    if pd.notna(lk_km) and lk_km > FAR_KM:
        i += 1
    if pd.isna(age) or age > FRESH_DAYS:
        i += 1
    return order[min(i, 2)]


def options(df):
    """Primary (current link) + backup gauge per county, and the confidence after the checks."""
    o = pd.DataFrame({
        'county': df['county'], 'state': df['state'],
        'primary_station': df['linked_station'], 'primary_uid': df['linked_uid'],
        'primary_km': df['linked_to_polygon_km'], 'primary_age_days': df['linked_age_days'],
        'backup_station': df['alt_station'], 'backup_uid': df['alt_uid'],
        'backup_km': df['alt_km'], 'backup_age_days': df['alt_age_days'],
        'backup_same_river': df['alt_same_river'],
        'confidence_original': df['confidence'], 'verdict': df['verdict']})
    o['confidence_checked'] = [downgrade(c, f, k, a) for c, f, k, a in
                               zip(df['confidence'], df['flags'], df['linked_to_polygon_km'], df['linked_age_days'])]
    o['confidence_changed'] = o['confidence_checked'].ne(o['confidence_original'].astype(str).str.lower())
    o['use_backup'] = df['verdict'].eq('REVIEW LINK') & df['alt_uid'].ne('')
    return o


def gauge_county(stations, counties):
    """For every gauge: the county polygon it sits in (or the nearest one and the distance)."""
    import geopandas as gpd
    pts = gpd.GeoDataFrame(stations.copy(), geometry=gpd.points_from_xy(stations.longitude, stations.latitude),
                           crs=4326).to_crs(METRIC_CRS)
    cty = counties.to_crs(METRIC_CRS)
    rows = []
    for g in pts.itertuples():
        d = cty.geometry.distance(g.geometry) / 1000.0
        i = int(np.argmin(d.values))
        rows.append({'station_uid': g.station_uid, 'station_name': g.station_name,
                     'latitude': round(g.latitude, 4), 'longitude': round(g.longitude, 4),
                     'county': cty.iloc[i]['county'], 'state': cty.iloc[i]['state'],
                     'km_to_county': round(float(d.values[i]), 1),
                     'inside_county': bool(d.values[i] <= 0.5)})
    return pd.DataFrame(rows)


def write_md(df, path, today):
    n = len(df)
    vc = df['verdict'].value_counts().to_dict()
    L = [f'# County to gauge link audit ({today:%Y-%m-%d})', '',
         f'{n} counties checked. Distances are from the gauge to the county polygon (0 = gauge inside the county).', '',
         '| Verdict | Counties |', '| --- | --- |']
    L += [f'| {k} | {v} |' for k, v in vc.items()]
    rv = df[df['verdict'].str.startswith('REVIEW') | df['verdict'].eq('NO LINK')]
    if len(rv):
        L += ['', '## Counties to review', '',
              '| County | Linked gauge | km | Age (d) | Nearest fresh alternative | km | Flags |',
              '| --- | --- | --- | --- | --- | --- | --- |']
        for r in rv.sort_values('linked_to_polygon_km', ascending=False).itertuples():
            L.append(f"| {r.county} | {r.linked_station} | {r.linked_to_polygon_km} | {r.linked_age_days} | "
                     f"{r.alt_station} | {r.alt_km} | {r.flags} |")
    L += ['', 'Rules: review when the linked gauge is over 100 km from the county, its latest reading is over 30 '
              'days old, or a fresh gauge is at least 25 km closer. The link file is not changed by this audit.']
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L) + '\n')


def selftest():
    import geopandas as gpd
    from shapely.geometry import box
    import tempfile
    tmp = tempfile.mkdtemp()
    st = pd.DataFrame({'station_uid': ['a', 'b', 'c'], 'latitude': [7.0, 7.1, 9.5], 'longitude': [31.0, 31.0, 31.0],
                       'river_key': ['N|Nile', 'N|Nile', 'N|Other'], 'location/river_name': ['A', 'B', 'C'],
                       'date': ['2026-10-01'] * 3, 'Water Surface Elevation - values(m)': [400.0, 401.0, 402.0]})
    st.to_csv(os.path.join(tmp, 'merged_altimetry_stations.csv'), index=False)
    pd.DataFrame({'station_uid': ['a', 'b', 'c'], 'last_date': ['2026-10-01', '2026-10-05', '2026-06-01'],
                  'last_level_m': [400, 401, 402]}).to_csv(os.path.join(tmp, 'station_status.csv'), index=False)
    cty = gpd.GeoDataFrame({'county': ['X', 'Y'], 'state': ['S', 'S'],
                            'geometry': [box(30.9, 6.9, 31.1, 7.2), box(30.9, 8.0, 31.1, 8.1)]}, crs=4326)
    link = pd.DataFrame({'county': ['X', 'Y'], 'station_uid': ['a', 'c'], 'station_name': ['A', 'C'],
                         'relation': ['local', 'local'], 'confidence': ['high', 'high'], 'distance_km': [0, 100]})
    out = audit(load_stations(tmp), cty, link, pd.Timestamp('2026-10-09'))
    assert out.loc[out.county == 'X', 'verdict'].iloc[0].startswith('OK'), out
    assert out.loc[out.county == 'Y', 'verdict'].iloc[0] == 'REVIEW LINK', out
    op = options(out)
    assert op.loc[op.county == 'Y', 'confidence_checked'].iloc[0] == 'low', op
    assert op.loc[op.county == 'X', 'confidence_checked'].iloc[0] == 'high', op
    assert op.loc[op.county == 'Y', 'backup_uid'].iloc[0] == 'b', op
    print('selftest passed')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    import geopandas as gpd
    gj = first_existing(os.path.join(BUL_DIR, 'counties_dissolved.geojson'))
    lk = first_existing(os.path.join(BUL_DIR, 'county_station_link.csv'), os.path.join(HERE, 'county_station_link.csv'))
    if not gj or not lk or not os.path.exists(os.path.join(ALT_DIR, 'merged_altimetry_stations.csv')):
        sys.exit('inputs missing (counties_dissolved.geojson, county_station_link.csv or merged_altimetry_stations.csv)')
    cty = gpd.read_file(gj)
    if 'county' not in cty.columns:
        for alt in ('County', 'NAME', 'admin2Name', 'ADM2_EN'):
            if alt in cty.columns:
                cty = cty.rename(columns={alt: 'county'})
                break
    sc = next((c for c in ('state', 'State', 'admin1Name', 'ADM1_EN') if c in cty.columns), None)
    cty['state'] = cty[sc] if sc else ''
    cty = cty[['county', 'state', 'geometry']].set_crs(4326, allow_override=True)
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    df = audit(load_stations(ALT_DIR), cty, pd.read_csv(lk), today)
    os.makedirs(AA_OUT, exist_ok=True)
    df.to_csv(os.path.join(AA_OUT, 'p7_county_station_audit.csv'), index=False)
    write_md(df, os.path.join(AA_OUT, 'p7_county_station_audit.md'), today)
    stations = load_stations(ALT_DIR)
    gc = gauge_county(stations, cty)
    gc.to_csv(os.path.join(AA_OUT, 'p7_gauge_county.csv'), index=False)
    print(gc[gc.station_uid.eq('hydroweb:105860')].to_string())
    options(df).to_csv(os.path.join(AA_OUT, 'county_gauge_options.csv'), index=False)
    print(df['verdict'].value_counts().to_string())


if __name__ == '__main__':
    main()
