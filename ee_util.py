# -*- coding: utf-8 -*-
"""Small Earth Engine helpers shared by the newer scripts (station_status.py, verify_forecasts.py)."""
import json
import os
import time

import ee

PROJECT_ID = 'sudan-1575919084043'
ASSET_FOLDER = f'projects/{PROJECT_ID}/assets/altimetry'


def init_ee():
    """Initialise Earth Engine with the service-account key from GEE_SERVICE_ACCOUNT_KEY (or your own login)."""
    key = os.environ.get('GEE_SERVICE_ACCOUNT_KEY', '').strip()
    if key:
        text = key if key.startswith('{') else open(key, encoding='utf-8').read()
        ee.Initialize(ee.ServiceAccountCredentials(json.loads(text)['client_email'], key_data=text),
                      project=PROJECT_ID)
    else:
        try:
            ee.Initialize(project=PROJECT_ID)
        except Exception:
            ee.Authenticate()
            ee.Initialize(project=PROJECT_ID)


def make_public(asset_id):
    """'Anyone can read' on an asset (a re-export creates a fresh, private asset)."""
    try:
        ee.data.setAssetAcl(asset_id, {'all_users_can_read': True})
        print(f"  shared publicly (anyone can read): {asset_id}")
        return True
    except Exception as e1:
        try:
            pol = ee.data.getIamPolicy(asset_id)
            viewers = [b for b in pol.get('bindings', []) if b.get('role') == 'roles/earthengine.viewer']
            members = sorted(set(sum([b.get('members', []) for b in viewers], []) + ['allUsers']))
            pol['bindings'] = [b for b in pol.get('bindings', []) if b.get('role') != 'roles/earthengine.viewer'] \
                + [{'role': 'roles/earthengine.viewer', 'members': members}]
            ee.data.setIamPolicy(asset_id, {'policy': pol})
            print(f"  shared publicly (anyone can read): {asset_id}")
            return True
        except Exception as e2:
            print(f"  WARNING: could not share {asset_id} publicly ({str(e1)[:100]} | {str(e2)[:100]}). "
                  "Give the service account the 'Earth Engine Resource Admin' role, or share it by hand.")
            return False


def export_table(fc, asset_id, description, public=True, poll=15):
    """Replace a table asset with `fc`, wait for the export, then re-share it. True on success."""
    try:
        ee.data.deleteAsset(asset_id)
    except Exception:
        pass
    task = ee.batch.Export.table.toAsset(collection=fc, description=description[:100], assetId=asset_id)
    task.start()
    print(f"Started export -> {asset_id}")
    while task.status()['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED'):
        time.sleep(poll)
    st = task.status()
    if st['state'] != 'COMPLETED':
        print(f"  export {st['state']}: {st.get('error_message', '')}")
        return False
    if public:
        make_public(asset_id)
    return True


def clean(v):
    """Python/numpy/NaN value -> something Earth Engine accepts, or None to drop it."""
    import numpy as np
    import pandas as pd
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (float, np.floating)):
        return float(v) if np.isfinite(v) else None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v
