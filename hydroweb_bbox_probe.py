#!/usr/bin/env python3
"""READ-ONLY probe: what does HydroWeb return for the proposed bbox, and which basin is each station in?
Downloads the two HydroWeb collections for BBOX into a temp folder, lists station, basin, river, lat/lon,
last date. Writes hydroweb_lake_check/bbox_stations.csv/.md. Changes nothing else."""
import glob, os, subprocess, sys, zipfile
import pandas as pd

BBOX = [23.9, -1.8, 36.4, 12.9]
KEY = (os.environ.get('HYDROWEB_API_KEY') or '').strip()
OUT, TMP = 'hydroweb_lake_check', 'bbox_probe_tmp'
os.makedirs(OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True)
if not KEY:
    sys.exit('HYDROWEB_API_KEY not set')
try:
    import py_hydroweb
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'py-hydroweb'], check=False)
    import py_hydroweb
client = py_hydroweb.Client(api_key=KEY)
rows = []
for coll in ['HYDROWEB_RIVERS_OPE', 'HYDROWEB_LAKES_OPE']:
    cwd = os.getcwd(); os.chdir(TMP)
    try:
        b = py_hydroweb.DownloadBasket(f'probe_{coll.lower()}')
        b.add_collection(coll, bbox=BBOX)
        z = os.path.abspath(f'{coll}.zip')
        p = client.submit_and_download_zip(b, zip_filename=z, output_folder=os.getcwd())
        p = p if (p and os.path.isabs(p)) else z
    finally:
        os.chdir(cwd)
    d = os.path.join(TMP, coll); os.makedirs(d, exist_ok=True)
    with zipfile.ZipFile(p) as zf: zf.extractall(d)
    for f in sorted(glob.glob(os.path.join(d, '**', '*.txt'), recursive=True)):
        txt = open(f, encoding='utf-8', errors='replace').read().splitlines()
        if coll.startswith('HYDROWEB_RIVERS'):
            m = {}
            for l in txt:
                if not l.startswith('#'): break
                if '::' in l:
                    k, v = l[1:].split('::', 1); m[k.strip()] = v.strip()
            data = [l.split()[0] for l in txt if l and not l.startswith('#')]
            rows.append(dict(type='river', id=m.get('ID'), basin=m.get('BASIN'), river=m.get('RIVER'),
                             lat=m.get('REFERENCE LATITUDE'), lon=m.get('REFERENCE LONGITUDE'),
                             n=len(data), last=data[-1] if data else None))
        else:
            h = {}
            for part in txt[0].split(';'):
                if '=' in part:
                    k, v = part.split('=', 1); h[k.strip()] = v.strip()
            data = [l.split(';')[1].strip() for l in txt[1:] if l.strip() and not l.startswith('#') and l.count(';') >= 6]
            rows.append(dict(type='lake', id=h.get('id'), basin=h.get('basin') or h.get('country'), river=h.get('lake'),
                             lat=h.get('lat'), lon=h.get('lon'), n=len(data), last=data[-1] if data else None))
df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUT, 'bbox_stations.csv'), index=False)
L = [f'# HydroWeb stations in bbox {BBOX}', '', f'{(df.type=="river").sum()} river, {(df.type=="lake").sum()} lake stations', '',
     '## Count by type and basin', '', df.groupby(['type', 'basin'], dropna=False).size().to_string(), '',
     '## Lakes', '', df[df.type == 'lake'].to_string(index=False)]
open(os.path.join(OUT, 'bbox_stations.md'), 'w').write('\n'.join(L))
print('\n'.join(L[:40]))
