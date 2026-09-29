# -*- coding: utf-8 -*-
"""
Nightly: flood thresholds + river discharge outlook for every altimetry station.

Reads  merged_altimetry_stations.csv   (written by merge_dahiti_hydroweb.py in the same run)
Writes station_status.csv              (Drive) and the point table
       projects/<project>/assets/altimetry/station_status   (Earth Engine, public) for the app.

Optional pieces fail soft: without the river outlook the table still has the flood thresholds.
"""
import os
import sys
import tempfile

import pandas as pd

from station_thresholds import compute_thresholds

OUT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', '.')
WORK = os.environ.get('ALTIMETRY_WORK_DIR', tempfile.gettempdir())
MASTER = os.path.join(OUT_DIR, 'merged_altimetry_stations.csv')

if not os.path.exists(MASTER):
    sys.exit(f"{MASTER} not found; run merge_dahiti_hydroweb.py first")

print("=== STATION STATUS: flood thresholds + river outlook ===")
merged = pd.read_csv(MASTER, low_memory=False)
status = compute_thresholds(merged)
print(f"Thresholds for {len(status)} stations: "
      f"{status['thr_confidence'].value_counts().to_dict()}")
print(status['flood_status'].value_counts().to_string())

# river discharge outlook (optional)
try:
    import river_outlook
    rivers = status[status['type'].astype(str).str.lower().eq('river')]
    os.makedirs(WORK, exist_ok=True)
    outlook, msg = river_outlook.build(rivers[['station_uid', 'latitude', 'longitude']], WORK)
    print(msg)
    if len(outlook):
        status = status.merge(outlook, on='station_uid', how='left')
        print(outlook['river_alert'].value_counts().to_string())
except Exception as e:                                          # never break the nightly run
    print(f"river outlook unavailable: {type(e).__name__}: {str(e)[:200]}")

status['updated_utc'] = pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M')
csv_path = os.path.join(OUT_DIR, 'station_status.csv')
status.to_csv(csv_path, index=False)
print(f"-> {csv_path} ({len(status)} rows)")

# Earth Engine point table for the app
try:
    import ee
    import ee_util
    ee_util.init_ee()
    feats = []
    for rec in status.to_dict('records'):
        lat, lon = rec.get('latitude'), rec.get('longitude')
        if pd.isna(lat) or pd.isna(lon):
            continue
        props = {k: ee_util.clean(v) for k, v in rec.items() if k not in ('latitude', 'longitude')}
        props = {k: v for k, v in props.items() if v is not None}
        feats.append(ee.Feature(ee.Geometry.Point([float(lon), float(lat)]), props))
    ee_util.export_table(ee.FeatureCollection(feats), f'{ee_util.ASSET_FOLDER}/station_status',
                         'station_status')
except Exception as e:
    print(f"WARNING: station_status asset not updated ({type(e).__name__}: {str(e)[:200]})")
