# -*- coding: utf-8 -*-
"""Probe: can the service account read the schools / health / roads assets, and what fields do they have?"""
import json, os
import ee
key = os.environ['GEE_SERVICE_ACCOUNT_KEY'].strip()
txt = key if key.startswith('{') else open(key).read()
ee.Initialize(ee.ServiceAccountCredentials(json.loads(txt)['client_email'], key_data=txt), project='sudan-1575919084043')
for a in ['projects/ee-penuelabi/assets/SDD_Schools', 'users/penuelabi/ssd_payam', 'projects/ee-penuelabi/assets/SSD_Health']:
    try:
        info = ee.data.getAsset(a)
        print('OK', a, info.get('type'))
        if info.get('type') == 'TABLE':
            fc = ee.FeatureCollection(a)
            print('  count', fc.size().getInfo()); print('  first', json.dumps(fc.first().getInfo())[:700])
        else:
            fc = ee.FeatureCollection(a); print('  first', json.dumps(fc.first().getInfo())[:700])
    except Exception as e:
        print('FAIL', a, str(e)[:200])
for a in ['projects/sat-io/open-datasets/shared/administrative/ssd_adm3', 'projects/sudan-1575919084043/assets/altimetry/county_hydroclimate']:
    try: print('OK', a, ee.FeatureCollection(a).size().getInfo())
    except Exception as e: print('FAIL', a, str(e)[:120])
