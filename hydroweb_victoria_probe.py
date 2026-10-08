#!/usr/bin/env python3
"""READ-ONLY: find how to get L_victoria (HYDROWEB_LAKES_OPE) through py_hydroweb. Downloads only."""
import inspect, os, subprocess, sys, zipfile
KEY = (os.environ.get('HYDROWEB_API_KEY') or '').strip()
OUT, TMP = 'hydroweb_lake_check', 'victoria_probe_tmp'
os.makedirs(OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True)
try:
    import py_hydroweb
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'py-hydroweb'], check=False)
    import py_hydroweb
L = ['# Victoria probe', '']
try:
    L.append('DownloadBasket.add_collection signature: ' + str(inspect.signature(py_hydroweb.DownloadBasket.add_collection)))
    L.append((inspect.getdoc(py_hydroweb.DownloadBasket.add_collection) or '')[:1500])
except Exception as e:
    L.append(f'inspect failed: {e}')
client = py_hydroweb.Client(api_key=KEY)
tests = [('intersects Point 33.0,-1.0', dict(intersects={'type': 'Point', 'coordinates': [33.0, -1.0]})),
         ('intersects Polygon small', dict(intersects={'type': 'Polygon', 'coordinates': [[[32.9, -1.1], [33.1, -1.1], [33.1, -0.9], [32.9, -0.9], [32.9, -1.1]]]})),
         ('bbox whole east Africa', dict(bbox=[20.0, -12.0, 42.0, 15.0])),
         ('bbox 31.5-35 x -3.2-0.6', dict(bbox=[31.5, -3.2, 35.0, 0.6])),
         ('query id contains victoria', dict(query={'id': {'contains': 'victoria'}})),
         ('query lake eq L_victoria', dict(query={'lake': {'eq': 'victoria'}}))]
for label, kw in tests:
    cwd = os.getcwd(); os.chdir(TMP)
    try:
        b = py_hydroweb.DownloadBasket('vic_' + str(abs(hash(label)) % 10**6))
        b.add_collection('HYDROWEB_LAKES_OPE', **kw)
        z = os.path.abspath('vic.zip')
        p = client.submit_and_download_zip(b, zip_filename=z, output_folder=os.getcwd())
        zp = p if (p and os.path.isabs(p)) else z
        names = [n.split('/')[-1] for n in zipfile.ZipFile(zp).namelist() if n.endswith('.txt')] if p else []
        L.append(f'- {label}: {len(names)} lakes: {names}')
        if any('victoria' in n.lower() for n in names):
            zf = zipfile.ZipFile(zp)
            n = [x for x in zf.namelist() if 'victoria' in x.lower()][0]
            t = zf.read(n).decode('utf-8', 'replace').splitlines()
            L.append(f'  VICTORIA FOUND ({n}); header: {t[0][:300]}')
            L.append('  last 3 lines: ' + ' | '.join(x[:80] for x in t[-3:]))
    except Exception as e:
        L.append(f'- {label}: {type(e).__name__}: {str(e)[:200]}')
    finally:
        os.chdir(cwd)
open(os.path.join(OUT, 'victoria_probe.md'), 'w').write('\n'.join(L))
print('\n'.join(L))
