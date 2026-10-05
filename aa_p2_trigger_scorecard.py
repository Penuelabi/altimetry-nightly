# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 2 - PILLAR 2: TRIGGER AND EARLY WARNING SYSTEMS (thresholds and triggers)
South Sudan Roadmap on Anticipatory Action 2025-2030, Outcome 2: capacity to provide impact-based forecasting and
early warning; activity b "technical guidance and tools for the design of triggers, thresholds ... and data
requirements" and the indicator "hazards with defined thresholds".

What it does
  Tests five kinds of river signal as flood triggers against recorded flood impacts, and proposes a readiness rule
  and an activation rule for every county:
    level      water level at the county gauge at or above a level (percentiles of the gauge's record; 2-, 5- and
               10-year levels from station_status.csv)
    seasonal   how unusual the level is for the time of year: the seasonal percentile the nightly pipeline gives each
               pass (same +/-30 days in other years of 2016-2025)
    rise       rise since the dry-season low (February-May) at or above the gauge's usual seasonal rise
               (its median, 75th or 90th percentile)
    regional   the Sudd regional upstream index that the bulletin logs as the Sudd river trigger (sudd_trigger.py),
               rebuilt for past months with flood_trigger_analysis.py; the previous month's value is used
    combined   a county signal AND the regional index (tested for activation)
  Only gauges upstream of or inside the county with medium- or high-confidence thresholds are used. Counties without
  such a gauge get the regional rule (if they are Sudd counties) or the bulletin's flood alert.
  Impact record: flood displacement (IOM DTM, by month) OR being listed in a flood assessment (2021, 2022, 2024,
  2025). When displacement gives an onset month, the signal must come no later than 15 days after it began (else
  it is 'late', counted as a miss); assessment-only events count at any time in the season (July-January).
  Activation: best CSI among rules with FAR <= 50% (else best TSS among rules catching >= 30% on time).
  Readiness: a lower rule of the same kind that catches at least 60% on time and as many as activation; best TSS.

  Altimetry samples rivers every 10-35 days, the impact records are incomplete and the sample is small: the output is
  a PROPOSAL for validation with SSMS, MWRI and the national TWG-AA, never an automatic trigger.

Inputs   merged_altimetry_stations.csv, station_status.csv (ALTIMETRY_OUT_DIR); county_station_link.csv,
         counties_dissolved.geojson (BULLETIN_OUT_DIR, link also at the repository root);
         data/flood_displacement_county_month.csv, data/flood_affected_county_year.csv;
         flood_trigger_analysis.py + geopandas for the regional index (skipped with a note if missing)
Outputs  aa_out/aa_triggers.csv (read by aa_p3_aap_engine.py: values and suggested rules per county),
         p2_trigger_skill_season.csv, p2_trigger_track_record.csv, p2_trigger_design_note.md,
         p2_trigger_hydrographs.png, indicator rows in aa_indicator_ledger.csv
Run:     python aa_p2_trigger_scorecard.py            python aa_p2_trigger_scorecard.py --selftest
"""
import argparse
import datetime
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
ALT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', os.path.join(HERE, 'altdata'))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))

LEVEL_COL = 'Water Surface Elevation - values(m)'
SEASON_MONTHS = (7, 8, 9, 10, 11, 12, 1)      # a season runs July-January (January belongs to the previous July)
DRY_MONTHS = (2, 3, 4, 5)                     # dry-season low for the 'rise' signal
ON_TIME_DAYS = 15                             # signal up to 15 days after the first displacement month began = on time
GAUGE_RELATIONS = ('upstream', 'local')       # gauges used for county triggers
GAUGE_CONFIDENCE = ('medium', 'high')         # threshold confidence required
READINESS_MIN_POD = 0.60
ACTIVATION_MAX_FAR = 0.50
ACTIVATION_MIN_POD = 0.30                     # fallback: never propose an activation rule that catches less than this
GAP = {'level': 0.25, 'rise': 0.25, 'seasonal': 10.0, 'regional': 0.10}   # readiness this far below activation
                                              # when no lower rule of the same kind qualifies (m, m, pctile, index)
MIN_PASSES = 3                                # passes in a season for it to be scored
DISPLACEMENT_COLS = ['flood', 'natural disaster (unspecified)']
MIN_OBS_PER_YEAR, MIN_YEARS_GUMBEL, EULER = 6, 8, 0.5772156649     # same rules as station_thresholds.py
LEVEL_PCTL = (60, 70, 80, 90, 95)
RP_TYPES = [('2yr-0.50m', 'lvl_2yr_m', -0.50), ('2yr-0.25m', 'lvl_2yr_m', -0.25), ('2yr', 'lvl_2yr_m', 0.0),
            ('2yr+0.25m', 'lvl_2yr_m', 0.25), ('5yr', 'lvl_5yr_m', 0.0), ('10yr', 'lvl_10yr_m', 0.0)]
SEASONAL_PCTL = (70, 80, 85, 90, 95)
RISE_PCTL = (50, 75, 90)
REGIONAL = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
COMBO_REGIONAL = (0.55, 0.60, 0.70)
COMBO_TOP = 3                                 # best county rules (by TSS) combined with the regional index
STALE_DAYS = 45
N_PLOTS = 6
ALIASES = {'abyeiadministrativearea': 'abyeiregion'}
SURFACE, INK, INK2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
LINE, READY_C, ACT_C, IMPACT_C = '#2a78d6', '#52514e', '#0b0b0b', '#d03b3b'
VAR = {'level': 'river_level_m', 'seasonal': 'river_pctile', 'rise': 'river_rise_m', 'regional': 'sudd_upstream_pct'}
FLOOD_ALERT_READY = "(alert_hazard == 'flood / waterlogging' and alert_rank >= 2)"
FLOOD_ALERT_ACT = "(alert_hazard == 'flood / waterlogging' and alert_level == 'red')"


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


def first_existing(*paths):
    for p in paths:
        if p and os.path.exists(p) and os.path.getsize(p) > 2:
            return p
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


def season_of_date(d):
    return d.year if d.month >= 7 else d.year - 1


# =========================================================================== #
# DATA                                                                        #
# =========================================================================== #
def load_merged(path):
    want = {'date', LEVEL_COL, 'station_uid', 'source', 'station_id', 'qc_status', 'seasonal_pctile', 'latitude',
            'longitude'}
    return pd.read_csv(path, low_memory=False, usecols=lambda c: c in want)


def levels_from(merged):
    d = merged.copy()
    if 'station_uid' not in d.columns:
        sid = pd.to_numeric(d['station_id'], errors='coerce')
        d['station_uid'] = (d['source'].astype(str).str.lower() + ':' +
                            sid.round().astype('Int64').astype(str)).where(sid.notna())
    d['date'] = pd.to_datetime(d['date'], errors='coerce')
    d['level'] = pd.to_numeric(d[LEVEL_COL], errors='coerce')
    d['spct'] = pd.to_numeric(d['seasonal_pctile'], errors='coerce') if 'seasonal_pctile' in d else np.nan
    d = d.dropna(subset=['date', 'level', 'station_uid'])
    if 'qc_status' in d.columns:
        ok = text(d['qc_status']).str.lower().eq('ok')
        if ok.mean() > 0.5:
            d = d[ok]
    return d[['station_uid', 'date', 'level', 'spct']].sort_values(['station_uid', 'date']).reset_index(drop=True)


def gumbel(annual_max, T):
    x = np.asarray(annual_max, float)
    beta = x.std(ddof=1) * np.sqrt(6) / np.pi
    return x.mean() - EULER * beta - beta * np.log(-np.log(1 - 1.0 / T))


def dry_lows(levels):
    """(station, year) -> lowest level in February-May."""
    d = levels[levels['date'].dt.month.isin(DRY_MONTHS)]
    return d.groupby(['station_uid', d['date'].dt.year])['level'].min().to_dict()


def season_tables(levels):
    """(station, season) -> flood-season passes (date, level, spct) sorted by date."""
    d = levels[levels['date'].dt.month.isin(SEASON_MONTHS)].copy()
    d['season'] = np.where(d['date'].dt.month >= 7, d['date'].dt.year, d['date'].dt.year - 1)
    return {k: g[['date', 'level', 'spct']].reset_index(drop=True) for k, g in d.groupby(['station_uid', 'season'])}


def station_table(levels, status, seasons, lows):
    """Per station: 2/5/10-year levels (station_status.csv, else the same Gumbel rules), record percentiles, the
    usual seasonal rise above the dry-season low, and the latest pass."""
    known = {}
    if status is not None and 'station_uid' in status:
        for r in status.to_dict('records'):
            if pd.notna(r.get('lvl_2yr_m')):
                known[r['station_uid']] = {'lvl_2yr_m': r['lvl_2yr_m'], 'lvl_5yr_m': r.get('lvl_5yr_m'),
                                           'lvl_10yr_m': r.get('lvl_10yr_m'), 'thr_confidence': r.get('thr_confidence'),
                                           'n_years': r.get('n_years'), 'thr_source': 'station_status.csv'}
    rises_by = {}
    for (u, s), sg in seasons.items():
        if (u, s) in lows and len(sg) >= MIN_PASSES:
            rises_by.setdefault(u, []).append(sg['level'].max() - lows[(u, s)])
    rows = []
    for uid, g in levels.groupby('station_uid'):
        rec = dict(known.get(uid, {}))
        if not rec:
            yearly = g.groupby(g['date'].dt.year)['level'].agg(['max', 'count'])
            yearly = yearly[yearly['count'] >= MIN_OBS_PER_YEAR]
            if len(yearly) >= MIN_YEARS_GUMBEL and yearly['max'].std(ddof=1) > 0:
                lv = sorted(gumbel(yearly['max'], T) for T in (2, 5, 10))
                conf = 'medium' if len(yearly) < 15 else 'high'
            elif len(g) >= 20:
                lv, conf = list(np.percentile(g['level'], (85, 95, 99))), 'low'
            else:
                continue
            rec = {'lvl_2yr_m': lv[0], 'lvl_5yr_m': lv[1], 'lvl_10yr_m': lv[2], 'thr_confidence': conf,
                   'n_years': len(yearly), 'thr_source': 'computed here (no station_status.csv row)'}
        rec['station_uid'] = uid
        for p in LEVEL_PCTL:
            rec[f'P{p}'] = float(np.percentile(g['level'], p))
        rises = rises_by.get(uid, [])
        for q in RISE_PCTL:
            rec[f'R{q}'] = float(np.percentile(rises, q)) if len(rises) >= 3 else np.nan
        last = g.iloc[-1]
        low = lows.get((uid, last['date'].year))
        rec.update({'record_start': g['date'].min().date().isoformat(), 'last_date': last['date'].date().isoformat(),
                    'last_level_m': float(last['level']),
                    'last_spct': float(last['spct']) if pd.notna(last['spct']) else np.nan,
                    'last_rise_m': float(last['level'] - low) if low is not None else np.nan})
        rows.append(rec)
    out = pd.DataFrame(rows)
    for name, base, off in RP_TYPES:
        out[name] = pd.to_numeric(out[base], errors='coerce') + off
    return out.set_index('station_uid')


def regional_index(merged, disp):
    """Monthly Sudd regional upstream index, built as sudd_trigger.py does (mean, over the counties with recorded
    flood displacement, of the monthly-maximum level percentile at their 3 nearest upstream gauges).
    Returns (Series indexed by month or None, note)."""
    gj = first_existing(os.path.join(BUL_DIR, 'counties_dissolved.geojson'))
    if not gj:
        return None, 'skipped: counties_dissolved.geojson not found'
    try:
        sys.path.insert(0, HERE)
        import geopandas as gpd
        import flood_trigger_analysis as fta
    except Exception as e:
        return None, f'skipped ({type(e).__name__}: {e})'
    flood_counties = sorted(disp.loc[pd.to_numeric(disp['flood'], errors='coerce') > 0, 'county'].unique())
    counties = gpd.read_file(gj)
    counties = counties[counties['county'].isin(flood_counties)].reset_index(drop=True)
    st = fta.station_table(merged)
    ml = fta.monthly_levels(st)
    if ml.empty or counties.empty:
        return None, 'skipped: no stations or Sudd counties'
    assign = fta.assign_stations(counties, ml)
    months = pd.period_range(pd.Period(st['date'].min(), 'M'), pd.Period(st['date'].max(), 'M'), freq='M')
    lf = fta.level_features(assign, ml, months)
    if 'lvl_upstream' not in lf:
        return None, 'skipped: no upstream gauges'
    reg = lf.groupby('ym')['lvl_upstream'].mean()
    reg.index = pd.PeriodIndex(reg.index, freq='M')
    n_up = assign[assign['group'] == 'upstream']['station_uid'].nunique()
    return reg.dropna(), f'{len(counties)} Sudd counties with recorded flood displacement, {n_up} upstream gauges'


def impacts(disp, affected):
    """(county key, season) -> {'onset': first displacement month or None, 'displacement', 'listed'}; years covered."""
    ev = {}
    d = disp.copy()
    cols = [c for c in DISPLACEMENT_COLS if c in d.columns]
    d['n'] = d[cols].apply(pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
    for r in d[d['n'] > 0].itertuples():
        t = pd.Timestamp(year=int(r.year), month=int(r.month), day=1)
        e = ev.setdefault((ckey(r.county), season_of_date(t)), {'onset': None, 'displacement': False, 'listed': False})
        e['displacement'] = True
        e['onset'] = t if e['onset'] is None else min(e['onset'], t)
    years = list(disp['year'])
    if affected is not None and len(affected):
        a = affected[pd.to_numeric(affected['affected'], errors='coerce') > 0]
        for r in a.itertuples():
            m = pd.to_numeric(getattr(r, 'month', np.nan), errors='coerce')
            season = int(r.year) if pd.isna(m) or m >= 7 else int(r.year) - 1
            ev.setdefault((ckey(r.county), season), {'onset': None, 'displacement': False, 'listed': False})['listed'] = True
        years += list(affected['year'])
    return ev, int(min(years)), int(max(years))


# =========================================================================== #
# CANDIDATES AND SCORING                                                      #
# =========================================================================== #
def candidates(thr, have_regional):
    """[{name, family, order, ...}]; order ranks a family's rules from lowest to highest."""
    c = []
    for p in LEVEL_PCTL:
        c.append({'name': f'P{p}', 'family': 'level', 'col': f'P{p}',
                  'order': float((thr[f'P{p}'] - thr['lvl_2yr_m']).median())})
    for name, base, off in RP_TYPES:
        c.append({'name': name, 'family': 'level', 'col': name, 'order': float((thr[name] - thr['lvl_2yr_m']).median())})
    for p in SEASONAL_PCTL:
        c.append({'name': f'S{p}', 'family': 'seasonal', 'order': float(p), 'value': float(p)})
    for q in RISE_PCTL:
        c.append({'name': f'R{q}', 'family': 'rise', 'order': float(q), 'col': f'R{q}'})
    if have_regional:
        for x in REGIONAL:
            c.append({'name': f'U{int(round(x * 100))}', 'family': 'regional', 'order': x, 'value': x})
    return c


def county_condition(g, cand, st, low):
    """Boolean array over a season's passes for a county rule."""
    if cand['family'] == 'level':
        t = st.get(cand['col'])
        return g['level'].to_numpy() >= t if pd.notna(t) else np.zeros(len(g), bool)
    if cand['family'] == 'seasonal':
        return (g['spct'] >= cand['value']).to_numpy()
    if cand['family'] == 'rise':
        t = st.get(cand['col'])
        if low is None or pd.isna(low) or pd.isna(t):
            return np.zeros(len(g), bool)
        return (g['level'] - low).to_numpy() >= t
    return np.zeros(len(g), bool)


def first_fired(cand, g, st, low, reg, season):
    if cand['family'] == 'regional':
        if reg is None:
            return None
        for m in pd.period_range(pd.Period(year=season, month=6, freq='M'), pd.Period(year=season, month=12, freq='M')):
            v = reg.get(m)
            if v is not None and pd.notna(v) and v >= cand['value']:
                return (m + 1).start_time                        # the month's value is known when it ends
        return None
    if g is None or g.empty:
        return None
    cond = county_condition(g, cand.get('county', cand), st, low)
    if 'county' in cand:                                         # combined: county rule AND previous month's regional
        prev = [reg.get(pd.Period(d, 'M') - 1, np.nan) if reg is not None else np.nan for d in g['date']]
        cond = cond & (np.asarray(prev, float) >= cand['value'])
    return g['date'].iloc[int(cond.argmax())] if cond.any() else None


def outcome(fired, ev, definition):
    tol = pd.Timedelta(days=ON_TIME_DAYS)
    if definition == 'displacement':
        is_event = ev is not None and ev['displacement']
    else:
        is_event = ev is not None and (ev['displacement'] or ev['listed'])
    onset = ev['onset'] if ev else None
    if is_event:
        if fired is None:
            return 'miss', np.nan
        if onset is None:
            return 'hit', np.nan
        return ('hit', float((onset - fired).days)) if fired <= onset + tol else ('late', np.nan)
    return ('false alarm' if fired is not None else 'correct negative'), np.nan


def scores(o):
    h, l, m, f, c = (int((o == k).sum()) for k in ('hit', 'late', 'miss', 'false alarm', 'correct negative'))
    ev = h + l + m
    fired = h + l + f
    pod = h / ev if ev else np.nan
    far = f / fired if fired else np.nan
    csi = h / (ev + f) if ev + f else np.nan
    pofd = f / (f + c) if f + c else np.nan
    tss = pod - pofd if pd.notna(pod) and pd.notna(pofd) else np.nan
    return {'events': ev, 'hits': h, 'late': l, 'misses': m, 'false_alarms': f, 'correct_negatives': c,
            'POD': pod, 'FAR': far, 'CSI': csi, 'TSS': tss}


def evaluate(cands, panel, thr, seasons, lows, reg, ev):
    """First-fired date and outcome for every candidate and county-season."""
    rows = []
    for r in panel.itertuples():
        g = seasons.get((r.station_uid, r.season))
        st = thr.loc[r.station_uid].to_dict() if r.station_uid in thr.index else {}
        low = lows.get((r.station_uid, r.season))
        e = ev.get((r.key, r.season))
        for cand in cands:
            fd = first_fired(cand, g, st, low, reg, r.season)
            o1, lead1 = outcome(fd, e, 'displacement or listed')
            o2, lead2 = outcome(fd, e, 'displacement')
            rows.append((r.key, r.county, r.station_uid, r.season, cand['name'], cand['family'], fd, o1, lead1, o2, lead2))
    return pd.DataFrame(rows, columns=['key', 'county', 'station_uid', 'season', 'candidate', 'family', 'fired',
                                       'outcome', 'lead_days', 'outcome_displacement', 'lead_days_displacement'])


def skill(long):
    out = []
    for (name, fam), g in long.groupby(['candidate', 'family'], sort=False):
        for definition, col, lcol in (('displacement or listed in a flood assessment', 'outcome', 'lead_days'),
                                      ('flood displacement only', 'outcome_displacement', 'lead_days_displacement')):
            s = scores(g[col])
            leads = g.loc[g[col] == 'hit', lcol].dropna()
            out.append({'impact_definition': definition, 'candidate': name, 'family': fam, 'county_seasons': len(g),
                        **s, 'median_lead_days': float(leads.median()) if len(leads) else np.nan})
    return pd.DataFrame(out)


def choose(sk, cands):
    """Activation first (the funding decision), then a lower readiness rule of the same kind."""
    s = sk[sk['impact_definition'].str.startswith('displacement or')].set_index('candidate')
    s = s[s['events'] > 0]
    if s.empty:
        return None, None, 'no impact records to test against'
    byname = {c['name']: c for c in cands}
    good = s[s['FAR'] <= ACTIVATION_MAX_FAR]
    if len(good) and good['CSI'].notna().any():
        act = good.sort_values(['CSI', 'TSS'], ascending=False).index[0]
        why = f'best CSI among rules with FAR <= {ACTIVATION_MAX_FAR:.0%}'
    else:
        pool = s[s['POD'] >= ACTIVATION_MIN_POD]
        pool = pool if len(pool) else s
        act = pool.sort_values(['TSS', 'CSI'], ascending=False).index[0]
        why = (f'no rule kept FAR <= {ACTIVATION_MAX_FAR:.0%}; best TSS among rules catching at least '
               f'{ACTIVATION_MIN_POD:.0%} on time')
    ca = byname[act]
    base = ca.get('county', ca)
    lower = [n for n, c in byname.items() if c['family'] == base['family'] and 'county' not in c and n in s.index and
             (c['order'] < base['order'] or ('county' in ca and n == base['name']))]
    need = max(READINESS_MIN_POD, float(s.loc[act, 'POD']) if pd.notna(s.loc[act, 'POD']) else 0.0)
    ok = [n for n in lower if s.loc[n, 'POD'] >= need and pd.notna(s.loc[n, 'TSS'])]
    if ok:
        best = max(s.loc[n, 'TSS'] for n in ok)
        ready = max((n for n in ok if s.loc[n, 'TSS'] == best), key=lambda n: byname[n]['order'])
    elif lower:
        ready = max(lower, key=lambda n: (s.loc[n, 'POD'], byname[n]['order']))
    else:
        ready = base['name'] if base['name'] in s.index else act
    if ready == base['name'] and 'county' not in ca:
        why += f"; no lower rule of this kind qualifies, so readiness = activation minus {GAP[base['family']]:g}"
    return ready, act, why


# =========================================================================== #
# RULES PER COUNTY                                                            #
# =========================================================================== #
def value_for(cand, st):
    if cand['family'] in ('level', 'rise'):
        v = st.get(cand['col'])
        return float(v) if v is not None and pd.notna(v) else np.nan
    return float(cand['value'])


def county_rules(lk, thr, cands, ready, act, reg, sudd_keys, today, reg_pair=None):
    byname = {c['name']: c for c in cands}
    cr, ca = byname.get(ready), byname.get(act)
    rr_name, ra_name = reg_pair or ('U55', 'U70')
    reg_now = float(reg.iloc[-1]) if reg is not None and len(reg) else np.nan
    regional_only = ca is not None and ca['family'] == 'regional'
    rows = []
    for r in lk.itertuples():
        st = thr.loc[r.station_uid].to_dict() if r.station_uid in thr.index else {}
        gauge_ok = bool(st) and r.relation in GAUGE_RELATIONS and str(st.get('thr_confidence')) in GAUGE_CONFIDENCE
        rec = {'county': r.county, 'state': getattr(r, 'state', ''), 'station_uid': r.station_uid,
               'station_name': getattr(r, 'station_name', ''), 'relation': r.relation,
               'link_confidence': getattr(r, 'confidence', ''), 'thr_confidence': st.get('thr_confidence'),
               'gauge_used': gauge_ok}
        note = ''
        if ca is not None and gauge_ok and not regional_only:
            base = ca.get('county', ca)
            fam = base['family']
            rv, av = value_for(cr, st), value_for(base, st)
            if pd.notna(rv) and pd.notna(av):
                if cr['name'] == base['name'] and 'county' not in ca:
                    rv, note = av - GAP[fam], f'readiness {GAP[fam]:g} below activation (no lower rule qualified)'
                elif fam in ('level', 'rise') and av < rv + GAP[fam]:
                    av, note = rv + GAP[fam], f'activation set {GAP[fam]:g} m above readiness'
            act_rule = f"{VAR[fam]} >= activation_value" + (' and sudd_upstream_pct >= regional_value' if 'county' in ca else '')
            rec.update({'trigger_family': fam + (' + regional' if 'county' in ca else ''),
                        'readiness_rule_name': cr['name'], 'activation_rule_name': act,
                        'readiness_value': round(rv, 3) if pd.notna(rv) else np.nan,
                        'activation_value': round(av, 3) if pd.notna(av) else np.nan,
                        'regional_value': ca['value'] if 'county' in ca else np.nan,
                        'suggested_readiness_rule': f"{VAR[fam]} >= readiness_value or {FLOOD_ALERT_READY}",
                        'suggested_activation_rule': f"({act_rule}) or {FLOOD_ALERT_ACT}"})
            if cr['name'] == base['name'] and 'county' not in ca:
                rec['readiness_rule_name'] = f"{cr['name']}-{GAP[fam]:g}"
            now_val = {'level': st.get('last_level_m'), 'seasonal': st.get('last_spct'), 'rise': st.get('last_rise_m')}[fam]
        elif reg is not None and (r.key in sudd_keys or regional_only):
            rn, an = (ready, act) if regional_only else (rr_name, ra_name)
            rv, av = byname[rn]['value'], byname[an]['value']
            if rn == an:
                rv = av - GAP['regional']
            rec.update({'trigger_family': 'regional', 'readiness_rule_name': rn if rn != an else f'{an}-{GAP["regional"]:g}',
                        'activation_rule_name': an, 'readiness_value': round(rv, 3),
                        'activation_value': av, 'regional_value': np.nan,
                        'suggested_readiness_rule': f'sudd_upstream_pct >= readiness_value or {FLOOD_ALERT_READY}',
                        'suggested_activation_rule': f'sudd_upstream_pct >= activation_value or {FLOOD_ALERT_ACT}'})
            note = 'regional rule chosen' if regional_only else 'no reliable county gauge: regional index used'
            now_val, fam = reg_now, 'regional'
        else:
            rec.update({'trigger_family': 'bulletin flood alert', 'readiness_rule_name': 'flood alert orange or red',
                        'activation_rule_name': 'flood alert red', 'readiness_value': np.nan,
                        'activation_value': np.nan, 'regional_value': np.nan,
                        'suggested_readiness_rule': FLOOD_ALERT_READY, 'suggested_activation_rule': FLOOD_ALERT_ACT})
            note = 'no reliable county gauge and not a Sudd county: bulletin flood alert only'
            now_val, fam = np.nan, None
        lvl = rec['trigger_family'].startswith('level')
        rec['readiness_level_m'] = rec['readiness_value'] if lvl else np.nan
        rec['activation_level_m'] = rec['activation_value'] if lvl else np.nan
        age = (today - pd.Timestamp(st['last_date'])).days if st.get('last_date') else np.nan
        if fam is None or now_val is None or pd.isna(now_val):
            state = 'n/a'
        elif fam != 'regional' and pd.notna(age) and age > STALE_DAYS:
            state = 'stale'
        else:
            reg_ok = pd.isna(rec['regional_value']) or (pd.notna(reg_now) and reg_now >= rec['regional_value'])
            state = 'activation' if pd.notna(rec['activation_value']) and now_val >= rec['activation_value'] and reg_ok \
                else 'readiness' if pd.notna(rec['readiness_value']) and now_val >= rec['readiness_value'] else 'below'
        rec.update({'lvl_2yr_m': st.get('lvl_2yr_m'), 'lvl_5yr_m': st.get('lvl_5yr_m'), 'lvl_10yr_m': st.get('lvl_10yr_m'),
                    'last_date': st.get('last_date'), 'last_level_m': st.get('last_level_m'),
                    'last_seasonal_pctile': st.get('last_spct'), 'last_rise_m': st.get('last_rise_m'),
                    'regional_now': reg_now, 'days_since_obs': age, 'current_state': state, 'note': note,
                    'status': 'proposed - validate with SSMS/MWRI and TWG-AA', 'validated_by': '', 'validated_date': ''})
        rows.append(rec)
    return pd.DataFrame(rows)


# =========================================================================== #
# OUTPUTS                                                                     #
# =========================================================================== #
def _plt():
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        return plt
    except Exception as e:
        print(f"Chart skipped: matplotlib not available ({e}). Add 'matplotlib' to requirements-bulletin.txt.")
        return None


def plot_signals(trig, levels, lows, ev, reg, out_png, years=6):
    """The signal each county's rule uses, its readiness and activation values, and the impact seasons."""
    plt = _plt()
    if plt is None or trig.empty:
        return None
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    rows = trig[trig['gauge_used'].astype(bool) & ~trig['trigger_family'].isin(['regional', 'bulletin flood alert'])]
    rows = rows.head(N_PLOTS - 1)
    if reg is not None and trig['trigger_family'].eq('regional').any():
        rows = pd.concat([rows, trig[trig['trigger_family'].eq('regional')].head(1)])
    if rows.empty:
        return None
    n = len(rows)
    fig, axes = plt.subplots(n, 1, figsize=(10, 2.15 * n + 0.9), dpi=140, sharex=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    t0 = levels['date'].max() - pd.DateOffset(years=years)
    for ax, r in zip(axes[:, 0], rows.itertuples()):
        ax.set_facecolor(SURFACE)
        fam = r.trigger_family.split(' ')[0]
        g = levels[(levels['station_uid'] == r.station_uid) & (levels['date'] >= t0)]
        if fam == 'regional':
            s = reg[reg.index.to_timestamp() >= t0]
            x, y, ylab = s.index.to_timestamp(), s.values, 'index (0-1)'
            title = 'Sudd regional upstream index (used by counties without a reliable gauge)'
        else:
            if fam == 'seasonal':
                x, y, ylab = g['date'], g['spct'], 'seasonal pctile'
            elif fam == 'rise':
                lo = [lows.get((r.station_uid, d.year), np.nan) for d in g['date']]
                x, y, ylab = g['date'], g['level'].to_numpy() - np.asarray(lo, float), 'rise (m)'
            else:
                x, y, ylab = g['date'], g['level'], 'level (m)'
            extra = f" + regional >= {r.regional_value:.2f}" if pd.notna(r.regional_value) else ''
            title = f"{r.county} ({r.state}) - {fam}{extra}; gauge {r.station_name or r.station_uid}, {r.relation}"
            key = ckey(r.county)
            for (k, s_), e in ev.items():
                if k != key or pd.Timestamp(year=s_, month=7, day=1) < t0:
                    continue
                if e['onset'] is not None:
                    ax.axvspan(e['onset'], e['onset'] + pd.offsets.MonthEnd(0), color=IMPACT_C, alpha=0.16, lw=0)
                elif e['listed']:
                    ax.axvspan(pd.Timestamp(year=s_, month=7, day=1), pd.Timestamp(year=s_ + 1, month=1, day=31),
                               color=IMPACT_C, alpha=0.05, lw=0)
        ax.plot(x, y, color=LINE, lw=1.5, marker='o', ms=2.2)
        for v, c, ls, lab in ((r.readiness_value, READY_C, '--', 'readiness'),
                              (r.activation_value, ACT_C, '-.', 'activation')):
            if pd.notna(v):
                ax.axhline(v, color=c, lw=1.1, ls=ls)
                ax.text(1.003, v, lab, transform=ax.get_yaxis_transform(), fontsize=7, color=c, va='center')
        ax.set_title(title, fontsize=9, color=INK, loc='left')
        ax.grid(axis='y', color=GRID, lw=0.6)
        for sp in ('top', 'right'):
            ax.spines[sp].set_visible(False)
        ax.tick_params(colors=INK2, labelsize=7)
        ax.set_ylabel(ylab, color=INK2, fontsize=8)
    handles = [Line2D([], [], color=LINE, lw=1.5, marker='o', ms=3, label='signal the rule uses'),
               Line2D([], [], color=READY_C, ls='--', label='readiness'),
               Line2D([], [], color=ACT_C, ls='-.', label='activation'),
               Patch(color=IMPACT_C, alpha=0.3, label='displacement month (pale band: listed in that season\'s assessment)')]
    fig.legend(handles=handles, loc='upper left', ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.01, 1.0))
    fig.tight_layout(rect=(0, 0, 0.97, 1 - 0.75 / (2.15 * n + 0.9)))
    fig.savefig(out_png, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)
    return out_png


def md_table(df, cols, fmt=None):
    fmt = fmt or {}
    lines = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    for r in df[cols].itertuples(index=False):
        cells = [fmt[c].format(v) if c in fmt and pd.notna(v) else ('' if isinstance(v, float) and np.isnan(v) else str(v))
                 for c, v in zip(cols, r)]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return lines


def write_note(path, R, trig):
    ready, act, why, sk = R['ready'], R['act'], R['why'], R['skill']
    pct = {'POD': '{:.0%}', 'FAR': '{:.0%}', 'CSI': '{:.2f}', 'TSS': '{:.2f}', 'median_lead_days': '{:.0f}'}
    lines = ['# River triggers - design note (proposal for validation)', '',
             f"Generated {now_utc():%Y-%m-%d %H:%M} UTC by aa_p2_trigger_scorecard.py (Roadmap on Anticipatory Action, "
             'Pillar 2: Trigger and Early Warning Systems).', '', '## Proposed rule']
    if act is None:
        lines += ['No rule could be scored: ' + why]
    else:
        main = sk[sk['impact_definition'].str.startswith('displacement or')]
        lines += [f"- **Activation: {act}** ({why}).",
                  f"- **Readiness: {ready}** (a lower rule of the same kind that catches at least {READINESS_MIN_POD:.0%} "
                  'of flood seasons on time and as many as activation; best TSS).',
                  '- Names: P = percentile of the gauge record; 2yr/5yr/10yr = return levels; S = seasonal percentile '
                  '(how unusual for the time of year); R = rise since the dry-season low against the gauge\'s usual rise; '
                  'U = Sudd regional upstream index x100; A+U = both.',
                  '- Counties without a reliable gauge use the regional rule if they are Sudd counties'
                  + (f" (readiness {R['reg_pair'][0]}, activation {R['reg_pair'][1]})" if R.get('reg_pair') else '')
                  + ', otherwise the bulletin flood alert. Each county\'s values and suggested plan rules are in '
                  'aa_triggers.csv.']
        weak = main[main['candidate'].isin([ready, act]) & ~(main['TSS'] > 0)]['candidate'].tolist()
        if weak:
            lines += ['', f"> **Warning:** {', '.join(weak)} shows no skill over chance in this record (TSS <= 0). Treat "
                      'it as a placeholder until SSMS/MWRI and the TWG-AA agree a rule from local knowledge.']
        lines += ['', '## Evidence',
                  f"{R['n_events']} county-seasons with a recorded flood impact, seasons {R['years'][0]}-{R['years'][1]} "
                  f"(July-January); {len(R['panel'])} county-seasons scored at {R['panel']['county'].nunique()} counties "
                  f"with a reliable gauge. Regional index: {R['reg_note']}.", '',
                  '### Every rule (impact = displacement or listed in a flood assessment; used for the choice)']
        lines += md_table(main.sort_values(['family', 'TSS'], ascending=[True, False]),
                          ['family', 'candidate', 'county_seasons', 'events', 'hits', 'late', 'misses', 'false_alarms',
                           'POD', 'FAR', 'CSI', 'TSS', 'median_lead_days'], pct)
        disp = sk[sk['impact_definition'].str.startswith('flood displacement') & sk['candidate'].isin([ready, act])]
        lines += ['', '### The chosen rules, impact = flood displacement only']
        lines += md_table(disp, ['candidate', 'events', 'hits', 'late', 'misses', 'false_alarms', 'POD', 'FAR', 'CSI',
                                 'TSS', 'median_lead_days'], pct)
    if len(trig):
        lines += ['', '## Counties', 'Rule used: ' + ', '.join(f'{k} {v}' for k, v in trig['trigger_family'].value_counts().items()) + '.']
        near = trig[trig['current_state'].isin(['activation', 'readiness'])]
        names = [f"{r.county} ({r.current_state})" for r in near.itertuples()]
        lines += [f"At or above a proposed value now: {len(names)}" + (': ' + ', '.join(names[:25]) if names else '.')]
    lines += ['', '## How to read and validate',
              '- POD: share of flood seasons caught on time. FAR: share of the seasons a rule fired with no impact recorded. '
              'CSI and TSS combine both; higher is better. Late = fired after displacement had begun (counted as a miss).',
              '- Small samples: one or two seasons can swing the numbers. Prefer rules that also make physical sense.',
              '- Satellite passes are 10-35 days apart; displacement and assessment records miss floods nobody counted.',
              '- Confirm per county with SSMS / MWRI and the state TWG-AA; record the decision in aa_triggers.csv '
              '(validated_by, validated_date) before using the values in an anticipatory action plan.']
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return path


# =========================================================================== #
# MAIN                                                                        #
# =========================================================================== #
def run(merged, status, link, disp, affected, reg=None, reg_note='not built', today=None):
    today = pd.Timestamp(today or now_utc().date())
    levels = levels_from(merged)
    seasons = season_tables(levels)
    lows = dry_lows(levels)
    thr = station_table(levels, status, seasons, lows)
    ev, y0, y1 = impacts(disp, affected)
    lk = link.copy()
    lk['key'] = lk['county'].map(ckey)
    lk = lk[text(lk['station_uid']).ne('')]
    use = lk[lk['station_uid'].isin(thr.index) & lk['relation'].isin(GAUGE_RELATIONS)]
    use = use[use['station_uid'].map(lambda u: str(thr.loc[u, 'thr_confidence']) in GAUGE_CONFIDENCE)]
    panel = pd.DataFrame([{'key': r.key, 'county': r.county, 'station_uid': r.station_uid, 'season': s}
                          for r in use.itertuples() for s in range(y0, y1 + 1)
                          if len(seasons.get((r.station_uid, s), [])) >= MIN_PASSES],
                         columns=['key', 'county', 'station_uid', 'season'])
    cands = candidates(thr, reg is not None)
    long, sk, ready, act, why = pd.DataFrame(), pd.DataFrame(), None, None, 'no county-seasons with a reliable gauge'
    if len(panel):
        long = evaluate(cands, panel, thr, seasons, lows, reg, ev)
        sk = skill(long)
        if reg is not None:                                  # the best county rules AND the regional index
            top = sk[sk['impact_definition'].str.startswith('displacement or') &
                     ~sk['family'].isin(['regional'])].sort_values('TSS', ascending=False)['candidate'].head(COMBO_TOP)
            byname = {c['name']: c for c in cands}
            combos = [{'name': f"{t}+U{int(round(x * 100))}", 'family': byname[t]['family'] + '+regional',
                       'order': byname[t]['order'], 'value': x, 'county': byname[t]} for t in top for x in COMBO_REGIONAL]
            long = pd.concat([long, evaluate(combos, panel, thr, seasons, lows, reg, ev)], ignore_index=True)
            cands = cands + combos
            sk = skill(long)
        ready, act, why = choose(sk, cands)
    reg_pair = None
    if reg is not None and len(sk) and (sk['family'] == 'regional').any():
        rp = choose(sk[sk['family'] == 'regional'], cands)
        reg_pair = rp[:2] if rp[1] else None
    sudd_keys = {ckey(c) for c in disp.loc[pd.to_numeric(disp['flood'], errors='coerce') > 0, 'county']}
    trig = county_rules(lk, thr, cands, ready, act, reg, sudd_keys, today, reg_pair)
    track = pd.DataFrame()
    if len(long) and act:
        t = long[long['candidate'].isin([ready, act])].pivot_table(
            index=['county', 'station_uid', 'season'], columns='candidate', values='fired', aggfunc='first').reset_index()
        t = t.rename(columns={ready: 'readiness_first_signal', act: 'activation_first_signal'})
        o = long[long['candidate'] == act][['county', 'season', 'outcome', 'lead_days']].rename(
            columns={'outcome': 'activation_outcome', 'lead_days': 'activation_lead_days'})
        track = t.merge(o, on=['county', 'season'], how='left')
        e = pd.DataFrame([{'county_key': k, 'season': s, 'flood_displacement': v['displacement'],
                           'first_displacement_month': v['onset'].strftime('%Y-%m') if v['onset'] is not None else '',
                           'listed_in_assessment': v['listed']} for (k, s), v in ev.items()],
                         columns=['county_key', 'season', 'flood_displacement', 'first_displacement_month',
                                  'listed_in_assessment'])
        track['county_key'] = track['county'].map(ckey)
        track = track.merge(e, on=['county_key', 'season'], how='left').drop(columns='county_key')
        track['season'] = track['season'].map(lambda s: f'{s}-{str(s + 1)[-2:]}')
        summ = long[long['candidate'] == act].groupby('county')['outcome'].value_counts().unstack(fill_value=0)
        for c in ('hit', 'late', 'miss', 'false alarm'):
            col = summ[c] if c in summ.columns else pd.Series(dtype=int)
            trig[f"seasons_{c.replace(' ', '_')}"] = trig['county'].map(col).fillna(0).astype(int)
    n_events = sum(1 for v in ev.values() if v['displacement'] or v['listed'])
    return {'trig': trig, 'track': track, 'skill': sk, 'ready': ready, 'act': act, 'why': why, 'reg_pair': reg_pair,
            'levels': levels,
            'lows': lows, 'ev': ev, 'reg': reg, 'reg_note': reg_note, 'years': (y0, y1), 'n_events': n_events,
            'panel': panel}


def main():
    print('=== AA ADD-ON 2 (PILLAR 2): RIVER TRIGGER SCORECARD ===')
    os.makedirs(AA_OUT, exist_ok=True)
    mpath = os.path.join(ALT_DIR, 'merged_altimetry_stations.csv')
    if not os.path.exists(mpath):
        sys.exit(f"{mpath} not found: run drive_sync.py pull (or set ALTIMETRY_OUT_DIR)")
    lpath = first_existing(os.path.join(BUL_DIR, 'county_station_link.csv'), os.path.join(HERE, 'county_station_link.csv'))
    if not lpath:
        sys.exit('county_station_link.csv not found (BULLETIN_OUT_DIR or repository root)')
    disp = read_csv(os.path.join(DATA_DIR, 'flood_displacement_county_month.csv'))
    if disp is None:
        sys.exit('data/flood_displacement_county_month.csv is needed to score the triggers')
    merged = load_merged(mpath)
    status = read_csv(os.path.join(ALT_DIR, 'station_status.csv'))
    link = read_csv(lpath)
    affected = read_csv(os.path.join(DATA_DIR, 'flood_affected_county_year.csv'))
    try:
        reg, reg_note = regional_index(merged, disp)
    except Exception as e:
        reg, reg_note = None, f'skipped ({type(e).__name__}: {str(e)[:150]})'
    print(f"Regional index: {reg_note}")
    R = run(merged, status, link, disp, affected, reg, reg_note)
    trig, sk, ready, act = R['trig'], R['skill'], R['ready'], R['act']
    print(f"{R['levels']['station_uid'].nunique()} stations; {len(R['panel'])} county-seasons scored at "
          f"{R['panel']['county'].nunique() if len(R['panel']) else 0} counties with a reliable gauge")
    risk = read_csv(os.path.join(AA_OUT, 'p1_county_risk_profile.csv'))
    if risk is not None and len(trig):
        trig = trig.merge(risk[['county', 'risk_rank', 'risk_class']], on='county', how='left')
        trig = trig.sort_values(['risk_rank', 'county'], na_position='last')
    out = {k: os.path.join(AA_OUT, v) for k, v in {
        'trig': 'aa_triggers.csv', 'ss': 'p2_trigger_skill_season.csv', 'tr': 'p2_trigger_track_record.csv',
        'note': 'p2_trigger_design_note.md', 'png': 'p2_trigger_hydrographs.png'}.items()}
    old = read_csv(out['trig'])
    if old is not None and 'validated_by' in old and len(trig):     # keep validation records already entered
        keep_cols = [c for c in ('county', 'validated_by', 'validated_date', 'trigger_family', 'readiness_value',
                                 'activation_value', 'regional_value', 'readiness_level_m', 'activation_level_m',
                                 'suggested_readiness_rule', 'suggested_activation_rule') if c in old.columns]
        keep = old[text(old['validated_by']).ne('')][keep_cols].set_index('county')
        if len(keep):
            trig = trig.set_index('county')
            idx = keep.index.intersection(trig.index)
            for c in keep.columns:
                trig[c] = trig[c].astype(object) if c in trig.columns else None
                trig.loc[idx, c] = keep.loc[idx, c]
            trig.loc[idx, 'status'] = 'validated (values kept as entered)'
            trig = trig.reset_index()
            print(f"Kept {len(idx)} validated county rules")
    trig.to_csv(out['trig'], index=False)
    if len(sk):
        sk.round(3).to_csv(out['ss'], index=False)
    R['track'].to_csv(out['tr'], index=False)
    write_note(out['note'], R, trig)
    png = plot_signals(trig, R['levels'], R['lows'], R['ev'], R['reg'], out['png'])
    stale = os.path.join(AA_OUT, 'p2_trigger_skill_monthly.csv')       # from the first version of this scorecard
    if os.path.exists(stale):
        os.remove(stale)

    hazards = {'riverine flood (river signal)'}
    bul = read_csv(os.path.join(BUL_DIR, 'county_bulletin_latest.csv'))
    if bul is not None and 'alert_hazard' in bul:
        hazards |= {h for h in text(bul['alert_hazard']).unique() if h and h != 'n/a'}
    main_sk = sk[sk['impact_definition'].str.startswith('displacement or')].set_index('candidate') if len(sk) else pd.DataFrame()
    note = ''
    if act and ready in main_sk.index and act in main_sk.index:
        note = (f"readiness {ready} POD {main_sk.loc[ready, 'POD']:.0%} FAR {main_sk.loc[ready, 'FAR']:.0%}; activation "
                f"{act} POD {main_sk.loc[act, 'POD']:.0%} FAR {main_sk.loc[act, 'FAR']:.0%}")
    log_indicators([
        dict(pillar='2', activity='Develop technical guidance and tools for triggers and thresholds',
             indicator='Hazards with defined thresholds and data requirements', value=len(hazards), kind='snapshot',
             unit='hazards', verification='p2_trigger_design_note.md; county bulletin advisory rules',
             note='; '.join(sorted(hazards))),
        dict(pillar='2', activity='Develop technical guidance and tools for triggers and thresholds',
             indicator='Counties with proposed river trigger levels',
             value=int((~trig['trigger_family'].eq('bulletin flood alert')).sum()) if len(trig) else 0,
             kind='snapshot', unit='counties', verification='aa_triggers.csv'),
        dict(pillar='2', activity='Develop technical guidance and tools for triggers and thresholds',
             indicator='Counties with validated river trigger levels',
             value=int(text(trig['validated_by']).ne('').sum()) if len(trig) else 0, kind='snapshot',
             unit='counties', verification='aa_triggers.csv (validated_by, validated_date)'),
        dict(pillar='2', activity='Map hazards, vulnerabilities and impacts to inform IbF and AA protocols',
             indicator='Trigger skill evaluations against recorded impacts', value=1, kind='event', unit='evaluations',
             verification='p2_trigger_skill_season.csv; p2_trigger_track_record.csv', note=note),
    ], 'aa_p2_trigger_scorecard.py')

    print(f"Proposed: readiness = {ready}, activation = {act} ({R['why']})")
    if R.get('reg_pair'):
        print(f"Counties without a reliable gauge (Sudd): readiness {R['reg_pair'][0]}, activation {R['reg_pair'][1]}")
    for c in dict.fromkeys((ready, act)):
        if c in main_sk.index:
            r = main_sk.loc[c]
            print(f"  {c:>12}: POD {r['POD']:.0%}  FAR {r['FAR']:.0%}  CSI {r['CSI']:.2f}  TSS {r['TSS']:.2f}  "
                  f"({int(r['hits'])} on time, {int(r['late'])} late, {int(r['misses'])} missed, "
                  f"{int(r['false_alarms'])} false alarms)")
            if not r['TSS'] > 0:
                print(f"  WARNING: {c} shows no skill over chance in this record (TSS {r['TSS']:.2f}); validate locally.")
    if len(trig):
        print('Counties by rule: ' + ', '.join(f'{k} {v}' for k, v in trig['trigger_family'].value_counts().items()))
        print('Counties now: ' + ', '.join(f'{k} {v}' for k, v in trig['current_state'].value_counts().items()))
    for k in ('trig', 'ss', 'tr', 'note'):
        print('->', out[k])
    if png:
        print('->', png)


def selftest():
    rng = np.random.default_rng(3)
    days = pd.date_range('2016-01-05', '2025-12-31', freq='11D')
    flood_years = {2020, 2022, 2024}
    rows = []
    for uid, base in (('dahiti:1', 400.0), ('dahiti:2', 380.0)):
        for d in days:
            trend = 0.5 if d.year >= 2019 else 0.0           # persistent high water from 2019, as in the Sudd
            seas = 1.2 * np.exp(-((d.dayofyear - 260) / 45.0) ** 2)
            boost = 0.6 if d.year in flood_years and 200 < d.dayofyear < 340 else 0.0
            rows.append({'station_uid': uid, 'date': d, 'level': base + trend + seas + boost + rng.normal(0, 0.04)})
    m = pd.DataFrame(rows)
    doy, yr = m['date'].dt.dayofyear.to_numpy(), m['date'].dt.year.to_numpy()
    spct = np.full(len(m), np.nan)
    for uid in m['station_uid'].unique():                    # seasonal percentile, as merge_dahiti_hydroweb.py does
        i = np.where(m['station_uid'].to_numpy() == uid)[0]
        dd = np.abs(doy[i][:, None] - doy[i][None, :])
        dd = np.minimum(dd, 365 - dd)
        w = m['level'].to_numpy()[i]
        mask = (dd <= 30) & (yr[i][:, None] != yr[i][None, :])
        for a, row in enumerate(mask):
            v = w[row]
            spct[i[a]] = 100 * (np.sum(v < w[a]) + 0.5 * np.sum(v == w[a])) / len(v) if len(v) else np.nan
    merged = pd.DataFrame({'station_uid': m['station_uid'], 'date': m['date'].dt.date.astype(str),
                           LEVEL_COL: m['level'], 'qc_status': 'ok', 'seasonal_pctile': spct})
    status = pd.DataFrame({'station_uid': ['dahiti:1', 'dahiti:2'], 'lvl_2yr_m': [401.0, 381.0],
                           'lvl_5yr_m': [401.5, 381.5], 'lvl_10yr_m': [401.8, 381.8],
                           'thr_confidence': ['medium', 'medium'], 'n_years': [10, 10]})
    link = pd.DataFrame({'county': ['A', 'B', 'C'], 'state': ['S'] * 3, 'station_uid': ['dahiti:1', 'dahiti:2', 'dahiti:2'],
                         'station_name': ['g1', 'g2', 'g2'], 'relation': ['local', 'upstream', 'downstream'],
                         'confidence': ['high'] * 3})
    disp = pd.DataFrame([{'county': c, 'year': y, 'month': 10, 'flood': 1000, 'natural disaster (unspecified)': 0}
                         for c in ('A', 'B') for y in sorted(flood_years)])
    affected = pd.DataFrame({'year': [2021], 'month': [np.nan], 'county': ['Z'], 'affected': [10]})
    R = run(merged, status, link, disp, affected, today=pd.Timestamp('2026-01-10'))
    sk = R['skill'][R['skill']['impact_definition'].str.startswith('displacement or')].set_index('candidate')
    assert sk.loc['S90', 'TSS'] > sk.loc['2yr-0.50m', 'TSS'], 'seasonal anomaly must beat a level crossed every season'
    t = R['trig'].set_index('county')
    assert t.loc['C', 'trigger_family'] == 'bulletin flood alert' and not t.loc['C', 'gauge_used'], 'downstream excluded'
    assert t.loc['A', 'suggested_activation_rule'].startswith('(river_'), t.loc['A', 'suggested_activation_rule']
    o = scores(pd.Series(['hit', 'late', 'miss', 'false alarm', 'correct negative', 'correct negative']))
    assert abs(o['POD'] - 1 / 3) < 1e-9 and abs(o['FAR'] - 1 / 3) < 1e-9
    e = {'onset': pd.Timestamp('2024-10-01'), 'displacement': True, 'listed': False}
    assert outcome(pd.Timestamp('2024-10-20'), e, 'displacement')[0] == 'late'
    assert outcome(pd.Timestamp('2024-10-10'), e, 'displacement')[0] == 'hit'
    assert outcome(pd.Timestamp('2024-12-01'), {'onset': None, 'displacement': False, 'listed': True},
                   'displacement or listed')[0] == 'hit'
    reg = pd.Series(0.4, index=pd.period_range('2016-01', '2025-12', freq='M'))
    for y in flood_years:
        reg[pd.Period(f'{y}-08', 'M')] = 0.8
    R2 = run(merged, status, link, disp, affected, reg=reg, today=pd.Timestamp('2026-01-10'))
    assert any('+U' in c for c in R2['skill']['candidate']), 'combined rules must be scored with a regional index'
    print(f"selftest passed: seasonal beats level under persistent high water (chosen {R['ready']} / {R['act']}), "
          f"downstream gauge excluded, timing rules, combined rules scored (chosen {R2['ready']} / {R2['act']})")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Pillar 2 river trigger scorecard')
    ap.add_argument('--selftest', action='store_true', help='check the scoring on synthetic data and exit')
    a = ap.parse_args()
    selftest() if a.selftest else main()
