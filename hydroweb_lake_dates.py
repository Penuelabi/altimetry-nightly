#!/usr/bin/env python3
"""READ-ONLY check: last observation date of every lake in HYDROWEB_LAKES_OPE.zip on the Drive folder,
and of the HydroWeb lake stations inside merged_altimetry_stations.csv. Downloads two files, uploads nothing.
Writes hydroweb_lake_check/lake_dates.md and .csv (dates, counts, heights only)."""
import csv, datetime as dt, io, os, sys, zipfile
import pandas as pd
import drive_sync as ds

FOLDER = os.environ.get('CHECK_FOLDER_ID', '1EyYopiOghPmHyJyBuH8DCp9PJv1zvCzV').strip()
WORK = 'lakecheck_tmp'
OUT = 'hydroweb_lake_check'
os.makedirs(OUT, exist_ok=True)
svc = ds.drive_service()
remote = ds.folder_files(svc, FOLDER)
need = ['HYDROWEB_LAKES_OPE.zip', 'merged_altimetry_stations.csv', 'hydroweb_water_levels_raw.xlsx']
missing = [n for n in need if n not in remote]
if missing:
    sys.exit(f"Not found in folder {FOLDER}: {missing}. Found {len(remote)} files.")
lines = [f"# HydroWeb lake last-data check", f"Run {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC; Drive folder {FOLDER}", ""]
lines.append("## Drive file timestamps (when the file was last written, NOT the last observation)")
for n in need:
    lines.append(f"- {n}: modified {remote[n]['modifiedTime']}, {int(remote[n].get('size', 0)) / 1e6:.1f} MB")
ds.pull(svc, FOLDER, WORK, need[:2], [])

rows = []
with zipfile.ZipFile(os.path.join(WORK, 'HYDROWEB_LAKES_OPE.zip')) as z:
    for name in sorted(n for n in z.namelist() if n.lower().endswith('.txt')):
        txt = z.read(name).decode('utf-8', 'replace').splitlines()
        if not txt:
            continue
        h = {}
        for part in txt[0].strip().split(';'):
            if '=' in part:
                k, v = part.split('=', 1); h[k.strip()] = v.strip()
        recs = []
        for l in txt[1:]:
            if not l.strip() or l.strip().startswith('#'):
                continue
            p = [x.strip() for x in l.split(';')]
            if len(p) >= 7:
                recs.append((p + [''] * 8)[:8])
        d = pd.DataFrame(recs, columns=['decimal_year', 'date', 'time', 'height_m', 'stdev_m', 'area_km2', 'volume_km3', 'mission'])
        d['dt'] = pd.to_datetime(d['date'].str.replace('/', '-') + ' ' + d['time'], errors='coerce')
        d['h'] = pd.to_numeric(d['height_m'], errors='coerce')
        d = d.dropna(subset=['dt']).sort_values('dt')
        last = d.iloc[-1] if len(d) else None
        last_valid = d.dropna(subset=['h'])
        rows.append({'file': os.path.basename(name), 'lake': h.get('lake', ''), 'id': h.get('id', ''),
                     'lat': h.get('lat', ''), 'lon': h.get('lon', ''), 'observations': len(d),
                     'first_date': f"{d['dt'].min():%Y-%m-%d}" if len(d) else '', 'last_date': f"{d['dt'].max():%Y-%m-%d}" if len(d) else '',
                     'last_height_m': f"{last_valid.iloc[-1]['h']:.3f}" if len(last_valid) else '',
                     'last_height_date': f"{last_valid.iloc[-1]['dt']:%Y-%m-%d}" if len(last_valid) else '',
                     'last_mission': last['mission'] if last is not None else ''})
lines += ["", "## Lakes inside HYDROWEB_LAKES_OPE.zip (raw HydroWeb files)", "",
          "| Lake | HydroWeb id | Obs | First | LAST DATE | Last height (m) | Mission |", "|---|---|---|---|---|---|---|"]
for r in rows:
    lines.append(f"| {r['lake']} | {r['id']} | {r['observations']} | {r['first_date']} | **{r['last_date']}** | {r['last_height_m']} ({r['last_height_date']}) | {r['last_mission']} |")
pd.DataFrame(rows).to_csv(os.path.join(OUT, 'lake_dates.csv'), index=False)

lvl = 'Water Surface Elevation - values(m)'
m = pd.read_csv(os.path.join(WORK, 'merged_altimetry_stations.csv'), usecols=lambda c: c in ('station_uid', 'date', lvl, 'location', 'type', 'source'), low_memory=False)
m['date'] = pd.to_datetime(m['date'], errors='coerce')
m['lvl'] = pd.to_numeric(m.get(lvl), errors='coerce')
hw = m[m['station_uid'].astype(str).str.startswith('hydroweb:')]
lake_ids = {f"hydroweb:{r['id']}" for r in rows}
sel = hw[hw['station_uid'].isin(lake_ids | {'hydroweb:1300000000016'})]
lines += ["", "## Same lakes as they appear in merged_altimetry_stations.csv (what the pipeline and bulletin use)", "",
          "| station_uid | Name in file | Obs with a level | First | LAST DATE with a level |", "|---|---|---|---|---|"]
for uid, g in sel.dropna(subset=['date', 'lvl']).groupby('station_uid'):
    nm = g['location'].dropna().iloc[0] if 'location' in g and g['location'].notna().any() else ''
    lines.append(f"| {uid} | {nm} | {len(g)} | {g['date'].min():%Y-%m-%d} | **{g['date'].max():%Y-%m-%d}** |")
notin = sorted(lake_ids - set(sel['station_uid'].unique()))
if notin:
    lines += ["", f"Lake ids in the zip but absent from the merged file: {notin}"]
lines += ["", f"Newest HydroWeb observation of any kind in the merged file: {hw.dropna(subset=['date', 'lvl'])['date'].max():%Y-%m-%d}",
          f"Newest observation of any source in the merged file: {m.dropna(subset=['date', 'lvl'])['date'].max():%Y-%m-%d}"]
open(os.path.join(OUT, 'lake_dates.md'), 'w').write("\n".join(lines))
print("\n".join(lines))
