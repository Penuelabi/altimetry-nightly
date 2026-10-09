# -*- coding: utf-8 -*-
"""Ask Hydroweb.next for Lake Victoria in several ways and report which one returns a file.
Each attempt gets its own folder under OUT; every zip is listed, and any file with 'victoria' in its name
is copied to OUT/victoria_found/. Needs HYDROWEB_API_KEY. Writes nothing to the repo."""
import os
import shutil
import sys
import zipfile

import py_hydroweb

KEY = os.environ.get('HYDROWEB_API_KEY')
if not KEY:
    sys.exit('HYDROWEB_API_KEY is not set')
OUT = os.path.abspath(os.environ.get('OUT', 'hydroweb_victoria_out'))
os.makedirs(os.path.join(OUT, 'victoria_found'), exist_ok=True)

ATTEMPTS = [
    ('A_ope_bbox_victoria', 'HYDROWEB_LAKES_OPE', dict(bbox=[31.5, -3.2, 34.9, 0.6])),
    ('B_ope_point_in_lake', 'HYDROWEB_LAKES_OPE', dict(bbox=[32.9, -1.1, 33.1, -0.9])),
    ('C_ope_toponym', 'HYDROWEB_LAKES_OPE', dict(intersects_refs=['HYDROWEB_LAKES_OPE.L_victoria'])),
    ('D_research_bbox_victoria', 'HYDROWEB_LAKES_RESEARCH', dict(bbox=[31.5, -3.2, 34.9, 0.6])),
    ('E_ope_bbox_nile_lakes', 'HYDROWEB_LAKES_OPE', dict(bbox=[29.0, -4.0, 36.5, 4.0])),
]

client = py_hydroweb.Client(api_key=KEY)
found = False
for name, collection, kw in ATTEMPTS:
    folder = os.path.join(OUT, name)
    os.makedirs(folder, exist_ok=True)
    print(f'\n=== {name}: {collection} {kw}', flush=True)
    try:
        basket = py_hydroweb.DownloadBasket(name.lower())
        basket.add_collection(collection, **kw)
        path = client.submit_and_download_zip(basket, zip_filename=os.path.join(folder, name + '.zip'),
                                              output_folder=folder)
    except Exception as e:
        print(f'  failed: {type(e).__name__}: {e}')
        continue
    if not path or not os.path.exists(path):
        print('  no zip returned')
        continue
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        print(f'  {len(names)} files: {sorted(os.path.basename(n) for n in names)}')
        for n in names:
            if 'victoria' in n.lower():
                found = True
                z.extract(n, os.path.join(OUT, 'victoria_found'))
                with z.open(n) as fh:
                    print('  VICTORIA FILE:', n)
                    print('   ', fh.readline().decode('utf-8', 'replace').strip()[:300])

print('\nRESULT:', 'Lake Victoria returned by Hydroweb' if found else 'Lake Victoria NOT returned by any attempt')
