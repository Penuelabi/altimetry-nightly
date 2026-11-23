# -*- coding: utf-8 -*-
"""
READ-ONLY test of the incremental GEE update filter against the real merged_observations asset.
Nothing is written. It checks that removal_filter() (taken from merge_dahiti_hydroweb.py) matches the rows it
should, using property names and types as they are stored in the asset.
"""
import json, os, sys
import ee
import pandas as pd

src = open('merge_dahiti_hydroweb.py').read()
PROJECT_ID = [l.split('=')[1].strip().strip("'\"") for l in src.splitlines() if l.startswith('PROJECT_ID')][0]
a, b = src.index('def removal_filter'), src.index('print("\\n=== STEP 1')
ns = {'ee': ee, 'pd': pd}
exec(src[a:b], ns)
removal_filter = ns['removal_filter']

key = os.environ['GEE_SERVICE_ACCOUNT_KEY'].strip()
txt = key if key.startswith('{') else open(key).read()
ee.Initialize(ee.ServiceAccountCredentials(json.loads(txt)['client_email'], key_data=txt), project=PROJECT_ID)
fc = ee.FeatureCollection(f'projects/{PROJECT_ID}/assets/altimetry/merged_observations')

total = fc.size().getInfo()
print('rows in merged_observations:', total)
sample = fc.limit(3).getInfo()['features']
p = sample[0]['properties']
print('sample properties:', {k: (type(p[k]).__name__, p[k]) for k in ('source', 'station_id', 'date') if k in p})
missing = [k for k in ('source', 'station_id', 'date') if k not in p]
if missing:
    print('FAIL: asset has no property', missing); sys.exit(1)


def rows_from(features):
    return pd.DataFrame([{k: f['properties'][k] for k in ('source', 'station_id', 'date')} for f in features])


ok = True
# 1) small: 3 rows
rows = rows_from(sample)
f = removal_filter(rows)
match = fc.filter(f).size().getInfo()
rest = fc.filter(ee.Filter.Not(f)).size().getInfo()
print(f'small:  matched {match} (>= {len(rows)} expected), remaining {rest}, match+remaining = {match + rest} vs total {total}')
ok &= match >= len(rows) and match + rest == total

# 2) realistic: the 300 most recent rows (many stations), like a night's back-filled rows
recent = fc.sort('system:time_start', False).limit(300).getInfo()['features']
rows = rows_from(recent)
f = removal_filter(rows)
n_st = rows[['source', 'station_id']].drop_duplicates().shape[0]
match = fc.filter(f).size().getInfo()
rest = fc.filter(ee.Filter.Not(f)).size().getInfo()
print(f'recent: {len(rows)} rows over {n_st} stations: matched {match}, remaining {rest}, sum {match + rest} vs total {total}')
ok &= match >= len(rows) and match + rest == total

# 3) replace simulation: remove then re-add the same rows -> same total
replaced = fc.filter(ee.Filter.Not(f)).merge(fc.filter(f)).size().getInfo()
print('remove + re-add gives', replaced, 'rows (must equal', total, ')')
ok &= replaced == total

# 4) a triple that does not exist matches nothing
none = removal_filter(pd.DataFrame([{'source': 'DAHITI', 'station_id': -1, 'date': '1900-01-01'}]))
n0 = fc.filter(none).size().getInfo()
print('non-existent triple matches', n0, '(must be 0)')
ok &= n0 == 0

print('\nRESULT:', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
