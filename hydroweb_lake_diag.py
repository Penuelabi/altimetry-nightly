#!/usr/bin/env python3
"""READ-ONLY diagnosis: why might the HydroWeb website show newer lake data than the Drive files?
Prints dates/counts only. Downloads 3 files from the Drive folder; uploads nothing."""
import datetime as dt, os, re, sys
import pandas as pd
import drive_sync as ds

FOLDER = os.environ.get('CHECK_FOLDER_ID', '1EyYopiOghPmHyJyBuH8DCp9PJv1zvCzV').strip()
WORK, OUT = 'lakecheck_tmp', 'hydroweb_lake_check'
os.makedirs(OUT, exist_ok=True)
svc = ds.drive_service()
names = ['hydroweb_water_levels_raw.xlsx', 'merged_altimetry_stations.csv', 'nightly_run_log.txt']
ds.pull(svc, FOLDER, WORK, names, [])
L = [f"# HydroWeb lake diagnosis", f"Run {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC", ""]

st = pd.read_excel(os.path.join(WORK, 'hydroweb_water_levels_raw.xlsx'), sheet_name='Stations')
st['last_date'] = pd.to_datetime(st['last_date'], errors='coerce')
lk = st[st['type'] == 'lake'].sort_values('last_date', ascending=False)
L += ["## hydroweb_water_levels_raw.xlsx - Stations sheet, lakes (this is what the last HydroWeb download produced)", "",
      "| station_id | location | lat | lon | n | first | LAST |", "|---|---|---|---|---|---|---|"]
for _, r in lk.iterrows():
    L.append(f"| {r['station_id']} | {r['location']} | {r['latitude']:.2f} | {r['longitude']:.2f} | {r['n_measurements']} | {pd.to_datetime(r['first_date']):%Y-%m-%d} | **{r['last_date']:%Y-%m-%d}** |")
L.append(f"\nIs 1300000000016 (Lake Victoria in the merged file) in this sheet? {'YES' if (st['station_id'].astype(str) == '1300000000016').any() else 'NO'}")
rv = st[st['type'] == 'river']
L.append(f"Rivers in the sheet: {len(rv)}; newest river last_date {rv['last_date'].max():%Y-%m-%d}")

lvl = 'Water Surface Elevation - values(m)'
m = pd.read_csv(os.path.join(WORK, 'merged_altimetry_stations.csv'), usecols=lambda c: c in ('station_uid', 'date', lvl, 'location', 'type', 'source'), low_memory=False)
m['date'] = pd.to_datetime(m['date'], errors='coerce')
m['lvl'] = pd.to_numeric(m[lvl], errors='coerce')
g = m.dropna(subset=['date', 'lvl'])
last = g.groupby('station_uid')['date'].max()
recent = last[last >= '2026-09-28'].sort_values(ascending=False)
L += ["", "## Stations in merged_altimetry_stations.csv with an observation on/after 2026-09-28", ""]
for uid, d in recent.items():
    L.append(f"- {uid}: {d:%Y-%m-%d}")
L.append(f"\nVictoria hydroweb:1300000000016 last date in merged file: {last.get('hydroweb:1300000000016')}")
v = g[g['station_uid'] == 'hydroweb:1300000000016'].sort_values('date').tail(8)
L.append("Last 8 Victoria rows: " + "; ".join(f"{r.date:%Y-%m-%d}={r.lvl:.3f}" for r in v.itertuples()))
if 'type' in g.columns:
    L.append(f"Victoria type/source columns: {g[g['station_uid']=='hydroweb:1300000000016'][['type','source']].drop_duplicates().to_dict('records')}")

log = open(os.path.join(WORK, 'nightly_run_log.txt'), encoding='utf-8', errors='replace').read().splitlines()
pat = re.compile(r'hydroweb|HYDROWEB|py_hydroweb|bbox|Observations kept', re.I)
bad = re.compile(r'key|token|secret|password|authorization', re.I)
hits = [l[:220] for l in log if pat.search(l) and not bad.search(l)]
L += ["", f"## nightly_run_log.txt: {len(log)} lines; last 40 lines mentioning HydroWeb/bbox", ""]
L += ["    " + h for h in hits[-40:]]
dates = [l[:60] for l in log if re.search(r'20\d\d-\d\d-\d\d', l) and re.search(r'start|begin|run', l, re.I)]
L += ["", "Run-start style lines (last 6): " + " | ".join(dates[-6:])]
open(os.path.join(OUT, 'diag.md'), 'w').write("\n".join(L))
print("\n".join(L))
