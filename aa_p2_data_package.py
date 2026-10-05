# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 3 - PILLAR 2: TRIGGER AND EARLY WARNING SYSTEMS (data repository)
South Sudan Roadmap on Anticipatory Action 2025-2030, Pillar 2 activity d: "a centralized repository for data and
information management to support multi-hazard IbF, EW and trigger-threshold development", indicator "number of
datasets uploaded and validated" (verification: SSMS database records). Also serves Pillar 1's "integration of risk
information into the existing Information Management System".

What it does
  Collects the platform's latest tables (county bulletin, station thresholds, county-gauge link, risk profile,
  proposed triggers, AAP status, forecast verification), checks each one, and writes ONE dated, documented package
  that SSMS, MHADM or an HDX/IMS focal point can load without asking how it was made:
    - every table as CSV plus an HXL-tagged copy (humanitarian exchange language, HDX-ready)
    - datapackage.json (Frictionless Data standard): fields, types, keys, SHA-256 checksums, sources, licence,
      and the validation result of every check
    - README.txt in plain language
  Checks: file readable and not empty, required columns, unique keys, probabilities within 0-1, allowed categories,
  value ranges, ordered thresholds (2-yr <= 5-yr <= 10-yr; readiness <= activation), freshness, and complete county
  coverage against data/ssd_county_population_2025.csv. A table that FAILS a check is left out of the package and
  listed in the manifest; warnings are kept and reported.

Outputs  aa_out/repository/aa_data_package_<UTC stamp>.zip, aa_out/aa_data_package_latest.zip (fixed name for Drive),
         aa_out/aa_data_package_latest.json (the manifest), indicator rows in aa_indicator_ledger.csv
Run:     python aa_p2_data_package.py           python aa_p2_data_package.py --selftest
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile

import pandas as pd

# =========================================================================== #
# SETTINGS                                                                    #
# =========================================================================== #
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('AA_DATA_DIR', os.path.join(HERE, 'data'))
BUL_DIR = os.environ.get('BULLETIN_OUT_DIR', os.path.join(HERE, 'bulletin'))
ALT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', os.path.join(HERE, 'altdata'))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))
PUBLISHER = os.environ.get('AA_PUBLISHER', 'South Sudan Climate Monitor (hydro-climate platform)')
KEEP_PACKAGES = 10                     # dated zips kept in aa_out/repository
ALIASES = {'abyeiadministrativearea': 'abyeiregion'}

DATASETS = [
    dict(id='county-bulletin', where=('BUL',), file='county_bulletin_latest.csv',
         title='County hydro-climate bulletin: antecedent rain and soil, 15-day ensemble outlook, impact-based alert',
         key='county', required=['county', 'state', 'alert_level'],
         probs=['p_heavy_50mm_week1', 'p_dry_spell_7d_in_15d', 'p_wet_spell_3d_week1'],
         cats={'alert_level': ['green', 'yellow', 'orange', 'red', 'n/a']}, date_col='data_end_date', max_age_days=7,
         all_counties=True),
    dict(id='station-status', where=('ALT',), file='station_status.csv',
         title='Satellite altimetry stations: 2-, 5- and 10-year flood levels and latest status',
         key='station_uid', required=['station_uid', 'lvl_2yr_m', 'lvl_5yr_m', 'lvl_10yr_m', 'last_level_m', 'last_date'],
         date_col='updated_utc', max_age_days=3, ordered=[('lvl_2yr_m', 'lvl_5yr_m'), ('lvl_5yr_m', 'lvl_10yr_m')]),
    dict(id='county-gauge-link', where=('BUL', 'ROOT'), file='county_station_link.csv',
         title='County to river gauge link (upstream / local / downstream)', key='county',
         required=['county', 'station_uid', 'relation'], all_counties=True),
    dict(id='county-flood-risk-profile', where=('AA',), file='p1_county_risk_profile.csv',
         title='County flood risk profile (INFORM-style, relative 0-10)', key='county',
         required=['county', 'risk_score', 'risk_class'], ranges={'risk_score': (0, 10)}, all_counties=True),
    dict(id='aa-river-triggers', where=('AA',), file='aa_triggers.csv',
         title='Proposed readiness and activation trigger rules per county (river level, seasonal anomaly, rise, '
               'Sudd regional index or bulletin alert; for validation)', key='county',
         required=['county', 'trigger_family', 'readiness_value', 'activation_value', 'suggested_activation_rule'],
         ordered=[('readiness_value', 'activation_value'), ('readiness_level_m', 'activation_level_m')]),
    dict(id='aap-status', where=('AA',), file='aap_status_latest.csv',
         title='Anticipatory action plan status (normal / readiness / activated)', key='plan_id',
         required=['plan_id', 'county', 'stage'], cats={'stage': ['normal', 'readiness', 'activated', 'out of season']}),
    dict(id='forecast-verification', where=('BUL',), file='forecast_verification.csv',
         title='Verification of the ensemble rain outlook against observed rain', required=[]),
]
HXL = {'state': '#adm1+name', 'county': '#adm2+name', 'pcode': '#adm2+code', 'station_uid': '#site+code',
       'station_name': '#site+name', 'name': '#site+name', 'latitude': '#geo+lat', 'longitude': '#geo+lon',
       'alert_level': '#severity+alert', 'alert_hazard': '#crisis+type', 'pop_total': '#population+total',
       'pop_flood_prone': '#population+flood_prone', 'risk_score': '#indicator+risk_score+num',
       'risk_class': '#indicator+risk_class', 'last_level_m': '#indicator+water_level_m+num',
       'lvl_2yr_m': '#indicator+level_2yr_m+num', 'lvl_5yr_m': '#indicator+level_5yr_m+num',
       'lvl_10yr_m': '#indicator+level_10yr_m+num', 'readiness_level_m': '#indicator+readiness_level_m+num',
       'activation_level_m': '#indicator+activation_level_m+num', 'plan_id': '#activity+code', 'stage': '#status',
       'readiness_value': '#indicator+readiness_value+num', 'activation_value': '#indicator+activation_value+num',
       'trigger_family': '#indicator+trigger_type',
       'data_end_date': '#date+data_end', 'last_date': '#date+observed', 'updated_utc': '#date+updated',
       'week1_rain_median_mm': '#indicator+rain_week1_mm+num', 'p_heavy_50mm_week1': '#indicator+p_heavy+num',
       'p_dry_spell_7d_in_15d': '#indicator+p_dry_spell+num'}
SOURCES = [
    'Rainfall: GSMaP v8 (JAXA), gauge-corrected, via Google Earth Engine',
    'Soil moisture, evapotranspiration, runoff: NASA SMAP Level-4 (SPL4SMGP)',
    'Forecast: ECMWF IFS ensemble open data, CC BY 4.0',
    'River levels: DAHITI (DGFI-TUM) and Hydroweb.Next (Theia / CNES, LEGOS) satellite altimetry',
    'Population: 2025 county estimates; WorldPop 2020 shares (CC BY 4.0); cropland: ESA WorldCover 2021 (CC BY 4.0)',
    'Flood-prone ground: JRC Global Surface Water; Global Flood Database; Sentinel-1 flood extent (Copernicus)',
    'Displacement: IOM Displacement Tracking Matrix records compiled in data/flood_displacement_county_month.csv',
]


# =========================================================================== #
# SMALL HELPERS (repeated in each add-on so every file runs on its own)       #
# =========================================================================== #
def ckey(name):
    k = re.sub(r'[^a-z0-9]+', '', str(name).lower())
    return ALIASES.get(k, k)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def text(series):
    return series.astype(object).where(series.notna(), '').astype(str).str.strip().replace({'nan': '', 'None': ''})


def read_csv(path, **kw):
    if path and os.path.exists(path) and os.path.getsize(path) > 2:
        try:
            return pd.read_csv(path, **kw)
        except Exception as e:
            print(f"WARNING: could not read {path}: {e}")
    return None


def log_indicators(rows, script):
    if not rows:
        return None
    os.makedirs(AA_OUT, exist_ok=True)
    path = os.path.join(AA_OUT, 'aa_indicator_ledger.csv')
    cols = ['run_utc', 'script', 'pillar', 'activity', 'indicator', 'value', 'kind', 'unit', 'verification', 'note']
    new = pd.DataFrame(rows)
    new['run_utc'] = now_utc().strftime('%Y-%m-%d %H:%M')
    new['script'] = script
    for c in cols:
        if c not in new:
            new[c] = ''
    old = read_csv(path)
    df = new[cols] if old is None else pd.concat([old.astype(object), new[cols].astype(object)], ignore_index=True)
    dup = pd.DataFrame({'d': text(df['run_utc']).str[:10], 's': df['script'], 'i': df['indicator']}).duplicated(keep='last')
    df = df[~(df['kind'].eq('snapshot') & dup)]
    df.to_csv(path, index=False)
    return path


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# =========================================================================== #
# CHECKS                                                                      #
# =========================================================================== #
def locate(spec):
    for w in spec['where']:
        base = {'BUL': BUL_DIR, 'ALT': ALT_DIR, 'AA': AA_OUT, 'ROOT': HERE}[w]
        p = os.path.join(base, spec['file'])
        if os.path.exists(p) and os.path.getsize(p) > 2:
            return p
    return None


def validate(df, spec, county_keys, today):
    """List of (check, status, detail); status is pass / warn / fail."""
    out = []
    if df is None or df.empty:
        return [('readable and not empty', 'fail', 'no rows')]
    out.append(('readable and not empty', 'pass', f'{len(df)} rows, {df.shape[1]} columns'))
    miss = [c for c in spec.get('required', []) if c not in df.columns]
    out.append(('required columns', 'fail' if miss else 'pass', f"missing: {', '.join(miss)}" if miss else
                ', '.join(spec.get('required', [])) or 'none required'))
    key = spec.get('key')
    if key and key in df.columns:
        dup = int(df[key].duplicated().sum())
        out.append((f'unique {key}', 'fail' if dup else 'pass', f'{dup} duplicates' if dup else 'unique'))
    for c in spec.get('probs', []):
        if c in df.columns:
            v = pd.to_numeric(df[c], errors='coerce')
            bad = int(((v < 0) | (v > 1)).sum())
            out.append((f'{c} within 0-1', 'fail' if bad else 'pass', f'{bad} out of range' if bad else
                        f'{int(v.notna().sum())} values'))
    for c, allowed in spec.get('cats', {}).items():
        if c in df.columns:
            vals = set(text(df[c])) - {''}
            odd = sorted(vals - set(allowed))
            out.append((f'{c} categories', 'warn' if odd else 'pass', f"unexpected: {', '.join(odd)}" if odd else
                        ', '.join(sorted(vals))))
    for c, (lo, hi) in spec.get('ranges', {}).items():
        if c in df.columns:
            v = pd.to_numeric(df[c], errors='coerce')
            bad = int(((v < lo) | (v > hi)).sum())
            out.append((f'{c} within {lo}-{hi}', 'fail' if bad else 'pass', f'{bad} out of range' if bad else 'ok'))
    for a, b in spec.get('ordered', []):
        if a in df.columns and b in df.columns:
            va, vb = pd.to_numeric(df[a], errors='coerce'), pd.to_numeric(df[b], errors='coerce')
            bad = int((va > vb).sum())
            out.append((f'{a} <= {b}', 'warn' if bad else 'pass', f'{bad} rows reversed' if bad else 'ok'))
    dc = spec.get('date_col')
    if dc and dc in df.columns:
        d = pd.to_datetime(df[dc], errors='coerce').max()
        if pd.isna(d):
            out.append((f'{dc} freshness', 'warn', 'no readable date'))
        else:
            age = (today - d.normalize()).days
            lim = spec.get('max_age_days', 7)
            out.append((f'{dc} freshness', 'warn' if age > lim else 'pass', f'latest {d.date()} ({age} days old, '
                        f'limit {lim})'))
    if spec.get('all_counties') and county_keys and 'county' in df.columns:
        have = set(df['county'].map(ckey))
        missing, extra = county_keys - have, have - county_keys
        st = 'warn' if missing or extra else 'pass'
        out.append(('county coverage', st, f'{len(have & county_keys)}/{len(county_keys)} counties' +
                    (f'; missing {len(missing)}' if missing else '') + (f'; unknown names {len(extra)}' if extra else '')))
    return out


def overall(checks):
    sts = [c[1] for c in checks]
    return 'fail' if 'fail' in sts else 'warn' if 'warn' in sts else 'pass'


def field_type(s):
    if pd.api.types.is_bool_dtype(s):
        return 'boolean'
    if pd.api.types.is_integer_dtype(s):
        return 'integer'
    if pd.api.types.is_numeric_dtype(s):
        return 'number'
    t = text(s)
    nonblank = t[t.ne('')]
    if len(nonblank) and pd.to_datetime(nonblank, errors='coerce', format='mixed').notna().mean() > 0.95 and \
            nonblank.str.match(r'^\d{4}-\d{2}-\d{2}').mean() > 0.95:
        return 'date' if nonblank.str.len().max() <= 10 else 'datetime'
    return 'string'


def hxl_copy(df, path):
    tags = [HXL.get(c, '') for c in df.columns]
    pd.concat([pd.DataFrame([tags], columns=df.columns), df.astype(object)], ignore_index=True).to_csv(path, index=False)


# =========================================================================== #
# PACKAGE                                                                     #
# =========================================================================== #
def build_package(today=None):
    today = pd.Timestamp(today or now_utc().date())
    stamp = now_utc().strftime('%Y%m%d_%H%M')
    pop = read_csv(os.path.join(DATA_DIR, 'ssd_county_population_2025.csv'))
    county_keys = set(pop['county'].map(ckey)) if pop is not None else set()
    work = tempfile.mkdtemp(prefix='aa_pkg_')
    resources, report = [], []
    for spec in DATASETS:
        path = locate(spec)
        if not path:
            report.append({'dataset': spec['id'], 'status': 'not found', 'detail': spec['file']})
            continue
        df = read_csv(path, low_memory=False)
        checks = validate(df, spec, county_keys, today)
        status = overall(checks)
        report.append({'dataset': spec['id'], 'status': status,
                       'detail': '; '.join(f'{c}: {d}' for c, s, d in checks if s != 'pass') or 'all checks passed'})
        res = {'name': spec['id'], 'title': spec['title'], 'source_file': spec['file'],
               'validation': {'status': status, 'checks': [{'check': c, 'status': s, 'detail': d}
                                                           for c, s, d in checks]}}
        if status == 'fail':
            res['included'] = False
            resources.append(res)
            continue
        out = os.path.join(work, spec['file'])
        df.to_csv(out, index=False)
        hx = os.path.join(work, spec['file'].replace('.csv', '_hxl.csv'))
        hxl_copy(df, hx)
        res.update({'included': True, 'path': spec['file'], 'hxl_path': os.path.basename(hx), 'format': 'csv',
                    'mediatype': 'text/csv', 'encoding': 'utf-8', 'bytes': os.path.getsize(out),
                    'hash': 'sha256:' + sha256(out), 'rows': int(len(df)),
                    'schema': {'fields': [{'name': c, 'type': field_type(df[c]), **({'hxl': HXL[c]} if c in HXL else {})}
                                          for c in df.columns],
                               **({'primaryKey': spec['key']} if spec.get('key') in df.columns else {})}})
        resources.append(res)
    included = [r for r in resources if r.get('included')]
    manifest = {
        'profile': 'tabular-data-package',
        'name': f'south-sudan-hydroclimate-aa-{stamp.lower()}',
        'title': 'South Sudan hydro-climate and anticipatory action data package',
        'version': stamp,
        'created': now_utc().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'description': 'County hydro-climate bulletin, altimetry flood thresholds, county-gauge links, county flood '
                       'risk profile, proposed river triggers and anticipatory action plan status, checked and '
                       'documented for the national early warning repository (SSRAA 2025-2030, Pillar 2, activity d). '
                       'Decision support, not an official warning.',
        'publisher': PUBLISHER,
        'licenses': [{'name': 'CC-BY-4.0', 'path': 'https://creativecommons.org/licenses/by/4.0/',
                      'title': 'Creative Commons Attribution 4.0 (attribute the sources below)'}],
        'sources': [{'title': s} for s in SOURCES],
        'keywords': ['South Sudan', 'anticipatory action', 'early warning', 'flood', 'drought', 'altimetry', 'HXL'],
        'roadmap': {'document': 'South Sudan Roadmap on Anticipatory Action 2025-2030',
                    'pillar': '2 - Trigger and Early Warning Systems',
                    'activity': 'Centralized repository for multi-hazard IbF, EW and trigger-threshold data',
                    'indicator': 'Number of datasets uploaded and validated'},
        'validation_summary': report,
        'resources': resources,
    }
    with open(os.path.join(work, 'datapackage.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    readme = ['SOUTH SUDAN HYDRO-CLIMATE AND ANTICIPATORY ACTION DATA PACKAGE', f'Version {stamp} (UTC)', '',
              manifest['description'], '', 'TABLES (each with an HXL-tagged copy, *_hxl.csv):']
    for r in included:
        readme.append(f"  {r['path']:<32} {r['rows']:>5} rows  {r['title']}  [{r['validation']['status']}]")
    left = [r for r in resources if not r.get('included')]
    if left:
        readme += ['', 'LEFT OUT (failed a check):'] + [f"  {r['source_file']}: " + '; '.join(
            c['check'] + ' - ' + c['detail'] for c in r['validation']['checks'] if c['status'] == 'fail') for r in left]
    readme += ['', 'datapackage.json lists every field, type, HXL tag, checksum and check result.', '',
               'SOURCES (attribute when reusing):'] + [f'  - {s}' for s in SOURCES] + [
               '', f'Publisher: {PUBLISHER}. Licence: CC BY 4.0. Alert levels and triggers are decision support for '
               'SSMS, MHADM and the TWG-AA; official warnings come from SSMS.']
    with open(os.path.join(work, 'README.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(readme) + '\n')

    repo_dir = os.path.join(AA_OUT, 'repository')
    os.makedirs(repo_dir, exist_ok=True)
    zpath = os.path.join(repo_dir, f'aa_data_package_{stamp}.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(work)):
            z.write(os.path.join(work, f), arcname=f)
    shutil.copyfile(zpath, os.path.join(AA_OUT, 'aa_data_package_latest.zip'))
    shutil.copyfile(os.path.join(work, 'datapackage.json'), os.path.join(AA_OUT, 'aa_data_package_latest.json'))
    shutil.rmtree(work, ignore_errors=True)
    old = sorted(f for f in os.listdir(repo_dir) if re.fullmatch(r'aa_data_package_\d{8}_\d{4}\.zip', f))
    for f in old[:-KEEP_PACKAGES]:
        os.remove(os.path.join(repo_dir, f))
    return zpath, manifest, report


def main():
    print('=== AA ADD-ON 3 (PILLAR 2): VALIDATED DATA PACKAGE FOR THE EW REPOSITORY ===')
    zpath, manifest, report = build_package()
    rep = pd.DataFrame(report)
    print(rep.to_string(index=False, max_colwidth=110))
    ok = int(rep['status'].isin(['pass', 'warn']).sum())
    fails = rep[rep['status'] == 'fail']['dataset'].tolist()
    log_indicators([
        dict(pillar='2', activity='Centralized repository for multi-hazard IbF, EW and trigger-threshold data',
             indicator='Datasets packaged and validated for the repository', value=ok, kind='event', unit='datasets',
             verification=os.path.basename(zpath), note='uploaded once shared with SSMS'),
        dict(pillar='2', activity='Centralized repository for multi-hazard IbF, EW and trigger-threshold data',
             indicator='Datasets failing validation', value=len(fails), kind='snapshot', unit='datasets',
             verification='aa_data_package_latest.json', note=', '.join(fails)),
        dict(pillar='1', activity='Integrate risk information into the information management system',
             indicator='Risk and trigger datasets in HXL for the IMS',
             value=int(rep[rep['dataset'].isin(['county-flood-risk-profile', 'aa-river-triggers'])]['status']
                       .isin(['pass', 'warn']).sum()), kind='snapshot', unit='datasets',
             verification=os.path.basename(zpath)),
    ], 'aa_p2_data_package.py')
    print(f"{ok} datasets packaged" + (f"; left out after a failed check: {', '.join(fails)}" if fails else ''))
    print('->', zpath)
    print('->', os.path.join(AA_OUT, 'aa_data_package_latest.zip'))


def selftest():
    global BUL_DIR, ALT_DIR, AA_OUT, DATA_DIR, HERE
    tmp = tempfile.mkdtemp(prefix='aa_pkg_test_')
    BUL_DIR = ALT_DIR = AA_OUT = DATA_DIR = HERE = tmp
    pd.DataFrame({'state': ['S'] * 3, 'county': ['A', 'B', 'C'], 'pop_2025': [1, 2, 3]}).to_csv(
        os.path.join(tmp, 'ssd_county_population_2025.csv'), index=False)
    pd.DataFrame({'county': ['A', 'B', 'C'], 'state': ['S'] * 3, 'alert_level': ['green', 'red', 'purple'],
                  'p_heavy_50mm_week1': [0.1, 0.5, 0.9], 'data_end_date': [str(datetime.date.today())] * 3}).to_csv(
        os.path.join(tmp, 'county_bulletin_latest.csv'), index=False)
    pd.DataFrame({'county': ['A', 'B', 'C'], 'risk_score': [1.0, 11.0, 5.0], 'risk_class': ['Low'] * 3}).to_csv(
        os.path.join(tmp, 'p1_county_risk_profile.csv'), index=False)
    zpath, man, rep = build_package()
    st = {r['dataset']: r['status'] for r in rep}
    assert st['county-bulletin'] == 'warn', st                 # 'purple' is not an alert level -> warning, kept
    assert st['county-flood-risk-profile'] == 'fail', st       # score 11 is outside 0-10 -> left out
    with zipfile.ZipFile(zpath) as z:
        names = set(z.namelist())
    assert {'datapackage.json', 'README.txt', 'county_bulletin_latest.csv', 'county_bulletin_latest_hxl.csv'} <= names
    assert 'p1_county_risk_profile.csv' not in names
    res = [r for r in man['resources'] if r['name'] == 'county-bulletin'][0]
    with zipfile.ZipFile(zpath) as z:
        assert hashlib.sha256(z.read('county_bulletin_latest.csv')).hexdigest() == res['hash'][7:]
    shutil.rmtree(tmp, ignore_errors=True)
    print('selftest passed: warnings kept, failures left out, checksums match, HXL copies written')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Pillar 2 validated data package')
    ap.add_argument('--selftest', action='store_true', help='check validation and packaging on synthetic data and exit')
    a = ap.parse_args()
    selftest() if a.selftest else main()
