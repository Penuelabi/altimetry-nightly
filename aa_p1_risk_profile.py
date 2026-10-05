# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 1 - PILLAR 1: RISK KNOWLEDGE
South Sudan Roadmap on Anticipatory Action 2025-2030, Outcome 1: improved understanding of risk at community
level, so that triggers and thresholds are risk-informed.

What it does
  Builds a county flood-risk profile for all 79 counties from data the platform already produces, so no new
  Earth Engine run is needed, and ranks counties INFORM-style (each indicator scaled 0-10 across counties, log
  scale for counts; indicators averaged within a dimension; dimensions combined by an offset geometric mean).
    Hazard          impact history: share of the 2021-2025 flood assessments that listed the county, mean % of
                    people affected, flood displacement 2020-2025 per 1,000 people and years with displacement (DTM)
    Exposure        people and cropland on flood-prone ground (county bulletin exposure layer); share of county
                    area, schools and health facilities at risk, road km at risk (data/exposure_cache.json);
                    people in settlements reported flooded in Sept 2025
    Vulnerability   v_* columns you add in aa_config/county_vulnerability.csv (more = more vulnerable), e.g. IPC phase
    Lack of coping  c_* columns you add there (more = more coping capacity; inverted here)
  Without vulnerability columns the score is hazard & exposure only; the notes and the ledger flag that gap.
  (Displacement is impact history, not vulnerability: a county with no DTM record is not shown as invulnerable.)
  Scores are RELATIVE: they rank counties within South Sudan, they are not probabilities of loss.

Roadmap activities supported (section 5.2.1)
  - assess risk profiles for hazards                      -> p1_county_risk_profile.csv
  - exposure and coping analysis by livelihood zone       -> p1_zone_profile.csv (FEWS NET zones if you add them)
  - vulnerability indicators for multi-hazards            -> vulnerability dimension + aa_config/county_vulnerability.csv
  - detailed risk maps to inform AA interventions         -> p1_risk_map.png + validation checklist in the notes
  - risk information into the information management system -> p1_county_risk_profile_hxl.csv (HXL tags, HDX-ready)

Inputs (repository data/ unless noted; all optional except the population file)
  ssd_county_population_2025.csv, flood_affected_county_year.csv, flood_displacement_county_month.csv,
  flood_settlements_sept2025.csv, exposure_cache.json
  county_bulletin_latest.csv (or county_exposure_cache.csv), counties_dissolved.geojson     BULLETIN_OUT_DIR
  county_vulnerability.csv, county_livelihood_zones.csv (templates are written on the first run)   AA_CONFIG_DIR
Outputs (AA_OUT_DIR, default ./aa_out)
  p1_county_risk_profile.csv, p1_county_risk_profile_hxl.csv, p1_zone_profile.csv, p1_risk_map.png,
  p1_risk_profile_notes.md, and indicator rows appended to aa_indicator_ledger.csv

Run:  python aa_p1_risk_profile.py            python aa_p1_risk_profile.py --selftest
"""
import argparse
import datetime
import json
import os
import re
import sys

import numpy as np
import pandas as pd

# =========================================================================== #
# SETTINGS                                                                    #
# =========================================================================== #
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('AA_DATA_DIR', os.path.join(HERE, 'data'))
BUL_DIR = os.environ.get('BULLETIN_OUT_DIR', os.path.join(HERE, 'bulletin'))
AA_CONFIG = os.environ.get('AA_CONFIG_DIR', os.path.join(HERE, 'aa_config'))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))

# Displacement causes counted as flood displacement. In South Sudan most "natural disaster (unspecified)"
# displacement is flooding; remove it here to use the 'flood' column only.
DISPLACEMENT_COLS = ['flood', 'natural disaster (unspecified)']
FLOODED_SETTLEMENT_SOURCES = ['Other Flooded Settlements']      # 'High Ground' sites are refuges, not losses
CAP_PCTILE = 95             # values above this percentile score 10 (keeps one extreme county from flattening the rest)
CLASS_BREAKS = [(6.5, 'Very high'), (5.0, 'High'), (3.5, 'Medium'), (2.0, 'Low'), (0.0, 'Very low')]
LOW_DATA_SHARE = 0.6        # county flagged 'low data' when fewer than 60% of indicators are available
TOP_LABELS = 12             # counties named on the map

# name, dimension, scale ('log' for counts, 'lin' for shares), meaning, source
INDICATORS = [
    ('flood_years_share', 'hazard', 'lin', 'Share of the flood assessments (2021-2025) that listed the county',
     'data/flood_affected_county_year.csv'),
    ('affected_pct_mean', 'hazard', 'lin', 'Mean share of the 2025 population affected per assessment (%)',
     'data/flood_affected_county_year.csv'),
    ('pop_flood_prone', 'exposure', 'log', 'People living on ground mapped as water or flooded before',
     'county bulletin exposure layer (JRC GSW + Global Flood Database, WorldPop shares)'),
    ('flood_prone_share', 'exposure', 'lin', 'Share of the population on flood-prone ground',
     'county bulletin exposure layer'),
    ('cropland_km2', 'exposure', 'log', 'Cropland area (km2)', 'ESA WorldCover 2021 via the county bulletin'),
    ('area_risk_share', 'exposure', 'lin', 'Share of county area at risk (Sentinel-1 baseline + current extent)',
     'data/exposure_cache.json'),
    ('facilities_risk_share', 'exposure', 'lin', 'Share of schools and health facilities at risk',
     'data/exposure_cache.json'),
    ('roads_risk_km', 'exposure', 'log', 'Road length at risk (km)', 'data/exposure_cache.json (GRIP4 roads)'),
    ('flooded_settlement_pop', 'exposure', 'log', 'People in settlements reported flooded, Sept 2025',
     'data/flood_settlements_sept2025.csv'),
    ('displaced_per_1000', 'hazard', 'log', 'Flood displacement 2020-2025 per 1,000 people (impact history)',
     'data/flood_displacement_county_month.csv (IOM DTM)'),
    ('displacement_years', 'hazard', 'lin', 'Years with flood displacement recorded, 2020-2025 (impact history)',
     'data/flood_displacement_county_month.csv (IOM DTM)'),
]

HXL = {'state': '#adm1+name', 'county': '#adm2+name', 'pcode': '#adm2+code', 'pop_total': '#population+total',
       'pop_flood_prone': '#population+flood_prone', 'risk_score': '#indicator+risk_score+num',
       'risk_class': '#indicator+risk_class', 'risk_rank': '#indicator+risk_rank+num',
       'hazard': '#indicator+hazard+num', 'exposure': '#indicator+exposure+num',
       'hazard_exposure': '#indicator+hazard_exposure+num', 'vulnerability': '#indicator+vulnerability+num',
       'lack_of_coping': '#indicator+lack_of_coping+num', 'data_completeness': '#indicator+completeness+num',
       'flooded_now_km2': '#indicator+flooded_now_km2+num', 'generated_utc': '#date+generated'}

# chart colours: one-hue ordinal ramp (light to dark) for the five risk classes, neutral ink for text
CLASS_COLORS = {'Very low': '#86b6ef', 'Low': '#5598e7', 'Medium': '#2a78d6', 'High': '#1c5cab', 'Very high': '#0d366b'}
SURFACE, INK, INK2, NODATA = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
ALIASES = {'abyeiadministrativearea': 'abyeiregion'}


# =========================================================================== #
# SMALL HELPERS (each add-on is standalone, so these are repeated per file)   #
# =========================================================================== #
def ckey(name):
    """County name key that survives case, spaces, hyphens and slashes ('Kajo-Keji' == 'Kajo-keji')."""
    k = re.sub(r'[^a-z0-9]+', '', str(name).lower())
    return ALIASES.get(k, k)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def text(series):
    """Strings with blanks as '' (pandas 2 and 3 treat missing values in astype(str) differently)."""
    return series.astype(object).where(series.notna(), '').astype(str).str.strip().replace({'nan': '', 'None': ''})


def read_csv(path, **kw):
    if path and os.path.exists(path) and os.path.getsize(path) > 2:
        try:
            return pd.read_csv(path, **kw)
        except Exception as e:
            print(f"WARNING: could not read {path}: {e}")
    return None


def first_existing(*paths):
    for p in paths:
        if p and os.path.exists(p) and os.path.getsize(p) > 2:
            return p
    return None


def log_indicators(rows, script):
    """Append roadmap indicator values to AA_OUT/aa_indicator_ledger.csv (read by aa_p5_indicator_tracker.py).
    kind 'snapshot' = state at run time (one kept per indicator per day); 'event' = happened in this run (summed)."""
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
    day = text(df['run_utc']).str[:10]
    dup = pd.DataFrame({'d': day, 's': df['script'], 'i': df['indicator']}).duplicated(keep='last')
    df = df[~(df['kind'].eq('snapshot') & dup)]
    df.to_csv(path, index=False)
    return path


def write_template(path, df, note):
    """Write an editable template once; never overwrite the user's version."""
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Template written: {path} ({note})")
    return True


# =========================================================================== #
# INPUTS                                                                      #
# =========================================================================== #
def load_inputs():
    d = {}
    d['pop'] = read_csv(os.path.join(DATA_DIR, 'ssd_county_population_2025.csv'))
    if d['pop'] is None:
        sys.exit(f"Population file not found in {DATA_DIR}: ssd_county_population_2025.csv is required")
    d['affected'] = read_csv(os.path.join(DATA_DIR, 'flood_affected_county_year.csv'))
    d['displacement'] = read_csv(os.path.join(DATA_DIR, 'flood_displacement_county_month.csv'))
    d['settlements'] = read_csv(os.path.join(DATA_DIR, 'flood_settlements_sept2025.csv'))
    d['exposure_json'] = None
    p = os.path.join(DATA_DIR, 'exposure_cache.json')
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8') as fh:
                d['exposure_json'] = json.load(fh)
        except Exception as e:
            print(f"WARNING: exposure_cache.json not read: {e}")
    src = first_existing(os.path.join(BUL_DIR, 'county_bulletin_latest.csv'),
                         os.path.join(BUL_DIR, 'county_exposure_cache.csv'))
    d['bulletin'] = read_csv(src) if src else None
    d['bulletin_src'] = src
    d['vuln'] = read_csv(os.path.join(AA_CONFIG, 'county_vulnerability.csv'))
    d['zones'] = read_csv(os.path.join(AA_CONFIG, 'county_livelihood_zones.csv'))
    d['geojson'] = first_existing(os.path.join(BUL_DIR, 'counties_dissolved.geojson'))
    return d


def write_templates(pop):
    base = pop[['state', 'county']].copy()
    v = base.copy()
    for c in ('v_ipc_phase', 'v_idp_share_pct', 'v_female_headed_hh_pct', 'c_health_facilities_per_10k',
              'c_market_access_score'):
        v[c] = np.nan
    write_template(os.path.join(AA_CONFIG, 'county_vulnerability.csv'), v,
                   'fill any v_* (more = more vulnerable) or c_* (more = more coping capacity) columns; '
                   'blank columns are ignored; add or rename columns freely, keeping the v_/c_ prefix')
    z = base.copy()
    z['livelihood_zone'] = ''
    z['share'] = 1.0
    write_template(os.path.join(AA_CONFIG, 'county_livelihood_zones.csv'), z,
                   'FEWS NET livelihood zone per county; repeat a county on several rows with share < 1 if it '
                   'spans zones (shares of one county should add to 1)')


# =========================================================================== #
# INDICATORS                                                                  #
# =========================================================================== #
def county_frame(pop):
    df = pop.copy()
    df['key'] = df['county'].map(ckey)
    df = df.rename(columns={'pop_2025': 'pop_2025'})
    return df[['key', 'state', 'county'] + [c for c in ('pcode', 'pop_2025') if c in df.columns]]


def hazard_indicators(base, affected):
    out = pd.DataFrame({'key': base['key']})
    if affected is None or affected.empty:
        return out.assign(flood_years_share=np.nan, affected_pct_mean=np.nan, assessments_listed=np.nan)
    a = affected.copy()
    a['key'] = a['county'].map(ckey)
    years = sorted(a['year'].dropna().unique())
    a['affected'] = pd.to_numeric(a['affected'], errors='coerce')
    a['pct'] = pd.to_numeric(a.get('pct_of_pop2025'), errors='coerce')
    per = a[a['affected'] > 0].groupby('key').agg(n_years=('year', 'nunique'), pct_sum=('pct', 'sum'))
    out = out.merge(per, left_on='key', right_index=True, how='left')
    out['assessments_listed'] = out['n_years'].fillna(0).astype(int)
    out['flood_years_share'] = out['assessments_listed'] / max(len(years), 1)
    out['affected_pct_mean'] = out['pct_sum'].fillna(0) / max(len(years), 1)    # not listed = 0 in that year
    return out.drop(columns=['n_years', 'pct_sum'])


def exposure_indicators(base, bulletin, ex_json, settlements):
    out = pd.DataFrame({'key': base['key']})
    if bulletin is not None and 'county' in bulletin:
        b = bulletin.copy()
        b['key'] = b['county'].map(ckey)
        keep = [c for c in ('pop_total', 'pop_flood_prone', 'cropland_km2') if c in b.columns]
        out = out.merge(b[['key'] + keep].drop_duplicates('key'), on='key', how='left')
    for c in ('pop_total', 'pop_flood_prone', 'cropland_km2'):
        if c not in out:
            out[c] = np.nan
    out['flood_prone_share'] = out['pop_flood_prone'] / out['pop_total'].where(out['pop_total'] > 0)

    rows = []
    if ex_json:
        pay, cty, now = ex_json.get('payams') or {}, ex_json.get('county') or {}, ex_json.get('payams_now') or {}
        for name in set(pay) | set(cty):
            plist = pay.get(name) or []
            area = sum((p.get('area_km2') or 0) for p in plist)
            area_r = sum((p.get('area_risk_km2') or 0) for p in plist)
            roads_r = sum((p.get('roads_risk_km') or 0) for p in plist)
            c = cty.get(name) or {}
            fac = (c.get('schools') or 0) + (c.get('health') or 0)
            fac_r = (c.get('schools_risk') or 0) + (c.get('health_risk') or 0)
            nowd = now.get(name) or {}
            area_now = sum(max(v.get('area_now_km2') or 0, 0) for v in nowd.values()) if isinstance(nowd, dict) else np.nan
            fac_now = sum(max(v.get('schools_now') or 0, 0) + max(v.get('health_now') or 0, 0)
                          for v in nowd.values()) if isinstance(nowd, dict) else np.nan
            rows.append({'key': ckey(name), 'area_km2': area or np.nan,
                         'area_risk_share': area_r / area if area > 0 else np.nan,
                         'facilities_total': fac, 'facilities_at_risk': fac_r,
                         'facilities_risk_share': fac_r / fac if fac > 0 else np.nan,
                         'roads_risk_km': roads_r if plist else np.nan,
                         'flooded_now_km2': area_now if nowd else np.nan,
                         'facilities_flooded_now': fac_now if nowd else np.nan})
    ex = pd.DataFrame(rows) if rows else pd.DataFrame(columns=['key'])
    out = out.merge(ex, on='key', how='left')
    for c in ('area_km2', 'area_risk_share', 'facilities_risk_share', 'roads_risk_km', 'flooded_now_km2',
              'facilities_at_risk', 'facilities_flooded_now'):
        if c not in out:
            out[c] = np.nan
    out['flooded_now_share'] = out['flooded_now_km2'] / out['area_km2']

    if settlements is not None and not settlements.empty:
        s = settlements.copy()
        s['key'] = s['county'].map(ckey)
        s['population'] = pd.to_numeric(s['population'], errors='coerce').fillna(0)
        flooded = s[s['source'].isin(FLOODED_SETTLEMENT_SOURCES)].groupby('key')['population'].sum()
        refuges = s[text(s['source']).str.startswith('High Ground')].groupby('key').size()
        out['flooded_settlement_pop'] = out['key'].map(flooded).fillna(0)
        out['high_ground_sites'] = out['key'].map(refuges).fillna(0).astype(int)
    else:
        out['flooded_settlement_pop'] = np.nan
        out['high_ground_sites'] = np.nan
    return out


def vulnerability_indicators(base, displacement, pop_col):
    out = pd.DataFrame({'key': base['key']})
    if displacement is None or displacement.empty:
        return out.assign(displaced_total=np.nan, displaced_per_1000=np.nan, displacement_years=np.nan)
    d = displacement.copy()
    d['key'] = d['county'].map(ckey)
    cols = [c for c in DISPLACEMENT_COLS if c in d.columns]
    d['n'] = d[cols].apply(pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
    agg = d[d['n'] > 0].groupby('key').agg(displaced_total=('n', 'sum'), displacement_years=('year', 'nunique'))
    out = out.merge(agg, left_on='key', right_index=True, how='left')
    out['displaced_total'] = out['displaced_total'].fillna(0)
    out['displacement_years'] = out['displacement_years'].fillna(0)
    out['displaced_per_1000'] = 1000 * out['displaced_total'] / pop_col.where(pop_col > 0).to_numpy()
    return out


def user_indicators(base, vuln):
    """v_* / c_* columns from aa_config/county_vulnerability.csv (blank columns ignored)."""
    if vuln is None or 'county' not in vuln:
        return pd.DataFrame({'key': base['key']}), [], []
    v = vuln.copy()
    v['key'] = v['county'].map(ckey)
    vcols = [c for c in v.columns if c.startswith('v_') and pd.to_numeric(v[c], errors='coerce').notna().any()]
    ccols = [c for c in v.columns if c.startswith('c_') and pd.to_numeric(v[c], errors='coerce').notna().any()]
    v = v[['key'] + vcols + ccols].drop_duplicates('key')
    for c in vcols + ccols:
        v[c] = pd.to_numeric(v[c], errors='coerce')
    return pd.DataFrame({'key': base['key']}).merge(v, on='key', how='left'), vcols, ccols


# =========================================================================== #
# INDEX                                                                       #
# =========================================================================== #
def scale_0_10(s, how='lin'):
    """Min-max to 0-10 across counties; values above the CAP_PCTILE percentile score 10. NaN stays NaN."""
    x = pd.to_numeric(s, errors='coerce').astype(float)
    if how == 'log':
        x = np.log10(x.clip(lower=0) + 1)
    valid = x.dropna()
    if len(valid) == 0:
        return x
    lo = valid.min()
    hi = np.percentile(valid, CAP_PCTILE) if len(valid) >= 5 else valid.max()
    if not np.isfinite(hi) or hi <= lo:
        hi = valid.max()
    if hi <= lo:
        return x.where(x.isna(), 0.0)
    return (10 * (x.clip(upper=hi) - lo) / (hi - lo)).clip(0, 10)


def offset_geomean(frame):
    """Geometric mean of 0-10 dimension scores, offset by 1 so one empty dimension does not zero the risk:
    ((d1+1)(d2+1)...)^(1/n) - 1. Stays on 0-10; equals the plain value when all dimensions agree."""
    logs = np.log(frame.astype(float) + 1)
    return np.exp(logs.mean(axis=1, skipna=True)) - 1


def risk_class(v):
    if pd.isna(v):
        return 'no data'
    for edge, name in CLASS_BREAKS:
        if v >= edge:
            return name
    return CLASS_BREAKS[-1][1]


def build_profile(pop, affected=None, displacement=None, settlements=None, ex_json=None, bulletin=None, vuln=None):
    base = county_frame(pop)
    h = hazard_indicators(base, affected)
    e = exposure_indicators(base, bulletin, ex_json, settlements)
    popn = e['pop_total'].where(e['pop_total'].notna(), base['pop_2025'] if 'pop_2025' in base else np.nan)
    e['pop_total'] = popn
    vul = vulnerability_indicators(base, displacement, popn)
    u, vcols, ccols = user_indicators(base, vuln)
    df = base.merge(h, on='key').merge(e, on='key').merge(vul, on='key').merge(u, on='key')

    spec = [(n, dim, how) for n, dim, how, *_ in INDICATORS] + \
           [(c, 'vulnerability', 'lin') for c in vcols] + [(c, 'coping', 'lin') for c in ccols]
    used = []
    for name, dim, how in spec:
        if name not in df or df[name].notna().sum() == 0:
            continue
        sc = scale_0_10(df[name], how)
        if dim == 'coping':                      # more capacity -> less risk
            sc = 10 - sc
        df[f's_{name}'] = sc.round(2)
        used.append((name, dim))
    dims = {}
    for dim in ('hazard', 'exposure', 'vulnerability', 'coping'):
        cols = [f's_{n}' for n, d in used if d == dim]
        if cols:
            dims[dim] = df[cols].mean(axis=1, skipna=True)
    df['hazard'] = dims.get('hazard', pd.Series(np.nan, index=df.index)).round(2)
    df['exposure'] = dims.get('exposure', pd.Series(np.nan, index=df.index)).round(2)
    df['hazard_exposure'] = df[['hazard', 'exposure']].mean(axis=1, skipna=True).round(2)
    df['vulnerability'] = dims.get('vulnerability', pd.Series(np.nan, index=df.index)).round(2)
    df['lack_of_coping'] = dims.get('coping', pd.Series(np.nan, index=df.index)).round(2)
    dim_cols = ['hazard_exposure'] + [c for c in ('vulnerability', 'lack_of_coping') if df[c].notna().any()]
    df['risk_score'] = offset_geomean(df[dim_cols]).round(2)
    df.loc[df[dim_cols].isna().all(axis=1), 'risk_score'] = np.nan
    df['risk_class'] = df['risk_score'].map(risk_class)
    df['risk_rank'] = df['risk_score'].rank(ascending=False, method='min').astype('Int64')
    n_ind = max(len(used), 1)
    df['data_completeness'] = (df[[f's_{n}' for n, _ in used]].notna().sum(axis=1) / n_ind).round(2)
    df['data_flag'] = np.where(df['data_completeness'] < LOW_DATA_SHARE, 'low data', '')
    df['generated_utc'] = now_utc().strftime('%Y-%m-%d %H:%M')
    df = df.sort_values(['risk_score', 'county'], ascending=[False, True]).reset_index(drop=True)
    return df, used, dim_cols


def zone_profile(profile, zones):
    """Population-weighted risk and summed exposure by livelihood zone (or by state when no zone file)."""
    p = profile.copy()
    if zones is not None and {'county', 'livelihood_zone'} <= set(zones.columns) and \
            text(zones['livelihood_zone']).ne('').any():
        z = zones.copy()
        z['livelihood_zone'] = text(z['livelihood_zone'])
        z = z[z['livelihood_zone'].ne('')]
        z['key'] = z['county'].map(ckey)
        z['share'] = pd.to_numeric(z.get('share', 1.0), errors='coerce').fillna(1.0)
        m = z[['key', 'livelihood_zone', 'share']].merge(p, on='key', how='inner')
        m = m.rename(columns={'livelihood_zone': 'zone'})
        zone_type = 'livelihood zone'
    else:
        m = p.assign(zone=p['state'], share=1.0)
        zone_type = 'state (add aa_config/county_livelihood_zones.csv for livelihood zones)'
    m['w_pop'] = m['pop_total'].fillna(0) * m['share']
    rows = []
    for zone, g in m.groupby('zone'):
        w = g['w_pop'].where(g['risk_score'].notna(), 0)
        risk = float((g['risk_score'].fillna(0) * w).sum() / w.sum()) if w.sum() > 0 else np.nan
        top = g.sort_values('risk_score', ascending=False)['county'].head(3).tolist()
        rows.append({'zone_type': zone_type, 'zone': zone, 'n_counties': g['county'].nunique(),
                     'population': round(float(g['w_pop'].sum())),
                     'pop_flood_prone': round(float((g['pop_flood_prone'].fillna(0) * g['share']).sum())),
                     'cropland_km2': round(float((g['cropland_km2'].fillna(0) * g['share']).sum()), 1),
                     'displaced_2020_2025': round(float((g['displaced_total'].fillna(0) * g['share']).sum())),
                     'risk_score_pop_weighted': round(risk, 2) if pd.notna(risk) else np.nan,
                     'risk_class': risk_class(risk),
                     'counties_very_high_or_high': int(g['risk_class'].isin(['Very high', 'High']).sum()),
                     'highest_risk_counties': ', '.join(top)})
    return pd.DataFrame(rows).sort_values('risk_score_pop_weighted', ascending=False).reset_index(drop=True)


# =========================================================================== #
# OUTPUTS                                                                     #
# =========================================================================== #
def write_hxl(profile, path):
    cols = [c for c in HXL if c in profile.columns]
    out = profile[cols].copy()
    tags = pd.DataFrame([[HXL[c] for c in cols]], columns=cols)
    pd.concat([tags, out.astype(object)], ignore_index=True).to_csv(path, index=False)
    return path


def _plt():
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        return plt
    except Exception as e:
        print(f"Chart skipped: matplotlib not available ({e}). Add 'matplotlib' to requirements-bulletin.txt.")
        return None


def _polys(geom):
    t, c = geom.get('type'), geom.get('coordinates') or []
    if t == 'Polygon':
        return [c]
    if t == 'MultiPolygon':
        return list(c)
    if t == 'GeometryCollection':
        return sum((_polys(g) for g in geom.get('geometries', [])), [])
    return []


def _ring_centroid(ring):
    a = np.asarray(ring, dtype=float)
    x, y = a[:, 0], a[:, 1]
    cross = x[:-1] * y[1:] - x[1:] * y[:-1]
    area = cross.sum() / 2
    if abs(area) < 1e-12:
        return x.mean(), y.mean(), 0.0
    return ((x[:-1] + x[1:]) * cross).sum() / (6 * area), ((y[:-1] + y[1:]) * cross).sum() / (6 * area), abs(area)


def plot_map(profile, geojson_path, out_png):
    plt = _plt()
    if plt is None:
        return None
    from matplotlib.patches import Patch, Polygon
    look = profile.set_index('key')
    fig, ax = plt.subplots(figsize=(9.5, 8.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    if geojson_path:
        with open(geojson_path, encoding='utf-8') as fh:
            gj = json.load(fh)
        labels = []
        for f in gj.get('features', []):
            name = (f.get('properties') or {}).get('county')
            k = ckey(name)
            cls = look['risk_class'].get(k, 'no data') if k in look.index else 'no data'
            col = CLASS_COLORS.get(cls, NODATA)
            best = None
            for poly in _polys(f.get('geometry') or {}):
                if not poly:
                    continue
                ax.add_patch(Polygon(np.asarray(poly[0])[:, :2], closed=True, facecolor=col, edgecolor=SURFACE,
                                     linewidth=0.6))
                cx, cy, ar = _ring_centroid(poly[0])
                if best is None or ar > best[2]:
                    best = (cx, cy, ar)
            if best and k in look.index and pd.notna(look['risk_rank'].get(k)) and int(look['risk_rank'][k]) <= TOP_LABELS:
                labels.append((best[0], best[1], int(look['risk_rank'][k]), name))
        ax.autoscale_view()
        ax.set_aspect(1 / np.cos(np.radians(7.5)))
        for x, y, rk, _ in labels:                     # rank numbers on the map, names in a list beside it
            ax.annotate(str(rk), (x, y), fontsize=6.5, color=INK, ha='center', va='center', fontweight='bold',
                        bbox=dict(boxstyle='circle,pad=0.18', fc=SURFACE, ec=INK2, lw=0.4, alpha=0.95))
        if labels:
            st = dict(zip(profile['county'], profile['state']))
            ranked = '\n'.join(f"{rk:>2}. {nm} ({st.get(nm, '')})" for _, _, rk, nm in sorted(labels, key=lambda t: t[2]))
            ax.text(1.02, 0.34, 'Highest-ranked counties\n' + ranked, transform=ax.transAxes, fontsize=7.5,
                    color=INK, va='top', ha='left', linespacing=1.45)
        ax.set_axis_off()
        title = 'Relative flood risk by county'
    else:
        top = profile.dropna(subset=['risk_score']).head(25).iloc[::-1]
        ax.barh(top['county'], top['risk_score'], color=[CLASS_COLORS.get(c, NODATA) for c in top['risk_class']],
                height=0.7)
        ax.set_xlim(0, 10)
        ax.set_xlabel('Risk score (0-10, relative)', color=INK2)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        ax.tick_params(colors=INK2, labelsize=8)
        ax.grid(axis='x', color=NODATA, linewidth=0.6)
        ax.set_axisbelow(True)
        title = 'Relative flood risk: 25 highest-ranked counties (no county boundaries found for a map)'
    counts = profile['risk_class'].value_counts()
    handles = [Patch(facecolor=CLASS_COLORS[c], label=f"{c} ({int(counts.get(c, 0))})") for c, _ in
               [(n, e) for e, n in CLASS_BREAKS]]
    if counts.get('no data', 0):
        handles.append(Patch(facecolor=NODATA, label=f"no data ({int(counts['no data'])})"))
    where = dict(loc='center left', bbox_to_anchor=(1.0, 0.5)) if geojson_path else dict(loc='lower right')
    leg = ax.legend(handles=handles, title='Risk class (counties)', frameon=False, fontsize=8, title_fontsize=8,
                    **where)
    for t in leg.get_texts():
        t.set_color(INK)
    fig.suptitle(title, x=0.02, ha='left', fontsize=12, color=INK)
    fig.text(0.02, 0.935, 'INFORM-style index (hazard & exposure x vulnerability), 0-10, ranks counties within South '
             'Sudan. Draft for validation with state partners.', fontsize=8, color=INK2)
    fig.savefig(out_png, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)
    return out_png


def write_notes(profile, used, dim_cols, zones_df, path, sources):
    rank = profile.dropna(subset=['risk_score'])
    lines = [
        '# County flood risk profile - method notes',
        '',
        f"Generated {now_utc():%Y-%m-%d %H:%M} UTC by aa_p1_risk_profile.py (Roadmap on Anticipatory Action, "
        "Pillar 1: Risk Knowledge).",
        '',
        '## What the score means',
        'Each indicator is scaled 0-10 across the counties (log scale for counts; values above the '
        f"{CAP_PCTILE}th percentile score 10). Indicators are averaged within a dimension; hazard and exposure "
        'form one dimension, as in INFORM. Dimensions are combined by a geometric mean offset by 1 '
        '(((d1+1)(d2+1)...)^(1/n) - 1), so a county needs both hazard/exposure and vulnerability to rank high, '
        'but one empty dimension does not erase the score.',
        f"Dimensions used this run: {', '.join(dim_cols)}." + (
            '' if len(dim_cols) > 1 else ' No vulnerability or coping columns were filled in '
            'aa_config/county_vulnerability.csv, so this run ranks hazard (impact history) and exposure only. '
            'Adding agreed vulnerability indicators (e.g. IPC phase, IDP share) completes the index.'),
        '',
        'The scores RANK counties within South Sudan; they are not probabilities of loss, and they are only as good '
        'as the records behind them (assessment coverage, DTM coverage, satellite exposure layers).',
        '',
        '## Indicators',
        '| Indicator | Dimension | Scale | Meaning | Source |',
        '|---|---|---|---|---|',
    ]
    meta = {n: (dim, how, mean, src) for n, dim, how, mean, src in INDICATORS}
    for n, dim in used:
        dimn, how, mean, src = meta.get(n, (dim, 'lin', 'user indicator (aa_config/county_vulnerability.csv)',
                                            'aa_config/county_vulnerability.csv'))
        lines.append(f"| {n} | {dim} | {how} | {mean} | {src} |")
    lines += ['', '## Classes', ', '.join(f"{name} >= {edge}" for edge, name in CLASS_BREAKS[:-1]) +
              f", otherwise {CLASS_BREAKS[-1][1]}.", '',
              '## Ten highest-ranked counties', '| Rank | County | State | Score | Class | People on flood-prone ground | '
              'Displaced 2020-2025 | Completeness |', '|---|---|---|---|---|---|---|---|']
    for r in rank.head(10).itertuples():
        pfp = '' if pd.isna(r.pop_flood_prone) else f"{r.pop_flood_prone:,.0f}"
        lines.append(f"| {r.risk_rank} | {r.county} | {r.state} | {r.risk_score:.1f} | {r.risk_class} | {pfp} | "
                     f"{r.displaced_total:,.0f} | {r.data_completeness:.0%} |")
    low = profile[profile['data_flag'] == 'low data']['county'].tolist()
    lines += ['', f"Counties flagged 'low data' (< {LOW_DATA_SHARE:.0%} of indicators): "
              f"{', '.join(low) if low else 'none'}.", '',
              '## Validation checklist (state TWG-AA / partners)',
              '- Does the ranking match local knowledge of where floods hurt most? Note disagreements per county.',
              '- Are the flood assessments and DTM records complete for these counties, or missing because no one '
              'assessed them?',
              '- Add vulnerability (v_*) and coping (c_*) indicators agreed with partners, e.g. IPC phase, IDP share, '
              'health facilities per 10,000 people, market access.',
              '- Add FEWS NET livelihood zones (aa_config/county_livelihood_zones.csv) for the zone profile.',
              '- Record the validation (date, who, changes) before the profile is used to target anticipatory action.',
              '', '## Inputs used']
    lines += [f"- {k}: {v}" for k, v in sources.items()]
    if zones_df is not None and len(zones_df):
        lines += ['', f"Zone profile: {zones_df['zone_type'].iloc[0]} ({len(zones_df)} zones), see p1_zone_profile.csv."]
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return path


# =========================================================================== #
# MAIN                                                                        #
# =========================================================================== #
def main():
    print('=== AA ADD-ON 1 (PILLAR 1): COUNTY FLOOD RISK PROFILE ===')
    os.makedirs(AA_OUT, exist_ok=True)
    d = load_inputs()
    write_templates(d['pop'])
    profile, used, dim_cols = build_profile(d['pop'], d['affected'], d['displacement'], d['settlements'],
                                            d['exposure_json'], d['bulletin'], d['vuln'])
    if d['bulletin'] is None:
        print('WARNING: no county_bulletin_latest.csv / county_exposure_cache.csv: people and cropland on flood-prone '
              'ground are left out this run.')
    zones = zone_profile(profile, d['zones'])

    p_csv = os.path.join(AA_OUT, 'p1_county_risk_profile.csv')
    front = ['risk_rank', 'state', 'county', 'pcode', 'risk_score', 'risk_class', 'hazard_exposure', 'hazard',
             'exposure', 'vulnerability', 'lack_of_coping', 'data_completeness', 'data_flag', 'pop_total',
             'pop_flood_prone', 'flood_prone_share', 'cropland_km2', 'assessments_listed', 'affected_pct_mean',
             'displaced_total', 'displaced_per_1000', 'displacement_years', 'area_risk_share',
             'facilities_at_risk', 'facilities_risk_share', 'roads_risk_km', 'flooded_settlement_pop',
             'high_ground_sites', 'flooded_now_km2', 'flooded_now_share', 'facilities_flooded_now']
    cols = [c for c in front if c in profile.columns] + \
           [c for c in profile.columns if c not in front and c != 'key']
    profile[cols].to_csv(p_csv, index=False)
    hxl = write_hxl(profile, os.path.join(AA_OUT, 'p1_county_risk_profile_hxl.csv'))
    z_csv = os.path.join(AA_OUT, 'p1_zone_profile.csv')
    zones.to_csv(z_csv, index=False)
    png = plot_map(profile, d['geojson'], os.path.join(AA_OUT, 'p1_risk_map.png'))
    sources = {'population': 'data/ssd_county_population_2025.csv',
               'bulletin exposure': d['bulletin_src'] or 'not found',
               'exposure cache': 'data/exposure_cache.json' if d['exposure_json'] else 'not found',
               'flood assessments': 'data/flood_affected_county_year.csv' if d['affected'] is not None else 'not found',
               'displacement': 'data/flood_displacement_county_month.csv' if d['displacement'] is not None else 'not found',
               'settlements': 'data/flood_settlements_sept2025.csv' if d['settlements'] is not None else 'not found',
               'county boundaries': d['geojson'] or 'not found (bar chart instead of map)'}
    notes = write_notes(profile, used, dim_cols, zones, os.path.join(AA_OUT, 'p1_risk_profile_notes.md'), sources)

    n_scored = int(profile['risk_score'].notna().sum())
    n_vuln = sum(1 for _, dim in used if dim in ('vulnerability', 'coping'))
    zone_is_lz = len(zones) and zones['zone_type'].iloc[0] == 'livelihood zone'
    log_indicators([
        dict(pillar='1', activity='Assess risk profiles for hazards',
             indicator='Counties with a flood risk profile', value=n_scored, kind='snapshot', unit='counties',
             verification=os.path.basename(p_csv)),
        dict(pillar='1', activity='Exposure and coping analysis for livelihood zones',
             indicator='Livelihood zones with exposure analysis', value=len(zones) if zone_is_lz else 0,
             kind='snapshot', unit='zones', verification=os.path.basename(z_csv),
             note='' if zone_is_lz else 'state profile only; livelihood zone file not filled'),
        dict(pillar='1', activity='Identify and validate vulnerability indicators',
             indicator='Vulnerability and coping indicators in use', value=n_vuln, kind='snapshot',
             unit='indicators', verification=os.path.basename(notes)),
        dict(pillar='1', activity='Develop and validate risk maps',
             indicator='Risk maps produced', value=1 if png else 0, kind='event', unit='maps',
             verification='p1_risk_map.png' if png else ''),
        dict(pillar='1', activity='Integrate risk information into the information management system',
             indicator='Risk datasets exported in HXL for the IMS', value=1, kind='event', unit='datasets',
             verification=os.path.basename(hxl)),
    ], 'aa_p1_risk_profile.py')

    show = profile.dropna(subset=['risk_score'])[['risk_rank', 'county', 'state', 'risk_score', 'risk_class',
                                                   'data_completeness']].head(15)
    print(show.to_string(index=False))
    print('Risk classes: ' + ', '.join(f"{k} {v}" for k, v in profile['risk_class'].value_counts().items()))
    for p in (p_csv, hxl, z_csv, png, notes):
        if p:
            print('->', p)


def selftest():
    rng = np.random.default_rng(1)
    n = 12
    names = [f'County {i}' for i in range(n)]
    pop = pd.DataFrame({'state': ['S1'] * 6 + ['S2'] * 6, 'county': names, 'pcode': [f'SS{i:04d}' for i in range(n)],
                        'pop_2025': rng.integers(50_000, 400_000, n)})
    affected = pd.DataFrame({'year': [2021, 2022, 2024, 2025, 2021, 2024], 'county': [names[0]] * 4 + [names[1]] * 2,
                             'affected': [50_000, 60_000, 70_000, 80_000, 5_000, 4_000],
                             'pct_of_pop2025': [30, 35, 40, 45, 2, 1]})
    disp = pd.DataFrame({'county': [names[0], names[0], names[1]], 'year': [2020, 2022, 2021], 'month': [8, 9, 10],
                         'flood': [20_000, 15_000, 500], 'natural disaster (unspecified)': [0, 0, 0]})
    bulletin = pd.DataFrame({'county': names, 'pop_total': pop['pop_2025'],
                             'pop_flood_prone': [300_000] + list(rng.integers(0, 20_000, n - 1)),
                             'cropland_km2': rng.uniform(5, 300, n)})
    vuln = pd.DataFrame({'county': names, 'v_ipc_phase': [5] + [2] * (n - 1), 'c_health': [0.1] + [3.0] * (n - 1)})
    prof, used, dims = build_profile(pop, affected, disp, None, None, bulletin, vuln)
    assert prof['risk_score'].between(0, 10).all(), 'scores outside 0-10'
    assert prof.iloc[0]['county'] == names[0], 'the county high on every indicator must rank first'
    assert set(prof['risk_class']) <= {n for _, n in CLASS_BREAKS}, 'unexpected class'
    assert set(dims) == {'hazard_exposure', 'vulnerability', 'lack_of_coping'}
    g = offset_geomean(pd.DataFrame({'a': [10.0, 0.0, 4.0], 'b': [10.0, 0.0, 4.0]}))
    assert np.allclose(g, [10, 0, 4]), 'geometric mean must equal the value when dimensions agree'
    s = scale_0_10(pd.Series([0, 1, 2, 3, 1000.0]), 'lin')
    assert s.max() == 10 and s.min() == 0
    z = zone_profile(prof, None)
    assert set(z['zone']) == {'S1', 'S2'}
    print('selftest passed: scores bounded, ordering, classes, geometric mean, scaling, zone profile')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--selftest', action='store_true', help='check the index maths on synthetic data and exit')
    a = ap.parse_args()
    selftest() if a.selftest else main()
