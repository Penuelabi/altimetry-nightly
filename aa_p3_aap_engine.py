# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 4 - PILLAR 3: ANTICIPATORY ACTION (plans, triggers and activation)
South Sudan Roadmap on Anticipatory Action 2025-2030, Outcome 3: a harmonised approach to design and deliver
anticipatory actions. Activities: standardised anticipatory action plans (AAPs) per hazard "with threshold, triggers,
forecast, anticipatory actions, beneficiary numbers, M&E framework and funding", and "joint activation of the AAPs
when the threshold is reached" (indicators: AAPs developed / validated / activated; trigger activation reports).

What it does
  Reads the plans the TWG-AA writes in two spreadsheets and checks them against the platform's latest data at every
  run (twice a day with the bulletin):
    aa_config/aap_plans.csv     one row per plan: county, hazard, readiness rule, activation rule, season, targets,
                                budget, funding source and release rule, lead agency, M&E reference, validation
    aa_config/aap_actions.csv   the pre-agreed actions per plan and stage, with lead, budget and deadline (days)
  Rules are short expressions over named values, for example
      river_level_m >= activation_level_m or (alert_level == 'red' and alert_hazard == 'flood / waterlogging')
  (python aa_p3_aap_engine.py --list-variables shows every name and today's values). Rules are parsed safely: only
  comparisons, and/or/not, numbers, text and arithmetic are allowed; a value that is missing or stale makes the
  condition 'not met' and is reported, so a dead gauge can never trigger a plan.
  Each plan moves normal -> readiness -> activated (once per season by default; confirmation over several distinct
  observations if you ask for it), stands down when readiness lapses, and closes at the end of its season.
  On every stage change it writes the activation log and, for an activation, a trigger activation report with the
  readings, thresholds, actions with due dates, targets, budget and the fund release rule.

Inputs   county_bulletin_latest.csv, county_station_link.csv, sudd_trigger_log.csv (BULLETIN_OUT_DIR);
         station_status.csv (ALTIMETRY_OUT_DIR); aa_out/aa_triggers.csv (aa_p2_trigger_scorecard.py);
         data/exposure_cache.json; aa_config/aap_plans.csv, aap_actions.csv (example drafts written on first run)
Outputs  aa_out/aap_status_latest.csv, aap_checklist_latest.csv/.md, aap_activation_log.csv, aap_state.json,
         aap_reports/<plan>_<date>_<stage>.md, aap_rule_variables.csv, indicator rows in aa_indicator_ledger.csv
Run:     python aa_p3_aap_engine.py   [--as-of 2026-10-05] [--dry-run] [--list-variables] [--selftest]
"""
import argparse
import ast
import datetime
import json
import operator
import os
import re

import numpy as np
import pandas as pd

# =========================================================================== #
# SETTINGS                                                                    #
# =========================================================================== #
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('AA_DATA_DIR', os.path.join(HERE, 'data'))
BUL_DIR = os.environ.get('BULLETIN_OUT_DIR', os.path.join(HERE, 'bulletin'))
ALT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', os.path.join(HERE, 'altdata'))
AA_CONFIG = os.environ.get('AA_CONFIG_DIR', os.path.join(HERE, 'aa_config'))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))

DEFAULTS = {'confirm_runs': 1,              # distinct observations the activation rule must hold for
            'max_data_age_days': 20,        # river readings older than this are ignored (passes are 10-35 days apart)
            'stand_down_runs': 4,           # consecutive runs without readiness before standing down
            'max_activations_per_season': 1,
            'season_start': '07-01', 'season_end': '01-31'}
EXAMPLE_PLANS = 6                           # draft plans written on the first run, highest-risk counties first
ALERT_RANK = {'green': 0, 'yellow': 1, 'orange': 2, 'red': 3}
RIVER_VARS = ('river_level_m', 'river_rate_m_per_day', 'river_pctile', 'river_rising', 'river_rise_m')
LEVEL_COL = 'Water Surface Elevation - values(m)'
DRY_MONTHS = (2, 3, 4, 5)                   # dry-season low for river_rise_m (as in aa_p2_trigger_scorecard.py)
EXAMPLE_NOTE = 'Example written by aa_p3_aap_engine.py'
ALIASES = {'abyeiadministrativearea': 'abyeiregion'}

VARIABLES = [
    ('alert_level', 'county bulletin', "impact-based alert: 'green', 'yellow', 'orange' or 'red'"),
    ('alert_rank', 'county bulletin', 'alert as a number: 0 green, 1 yellow, 2 orange, 3 red'),
    ('alert_stage', 'county bulletin', "the AA stage alert_level corresponds to: 'monitoring', 'warning', "
                                       "'readiness' or 'activation' -- readiness/activation line up with this "
                                       "engine's own plan stages ('readiness', 'activated')"),
    ('alert_hazard', 'county bulletin', "'flood / waterlogging' or 'drought / dry spell'"),
    ('p_heavy', 'county bulletin', 'chance of >= 50 mm of rain in week 1 (0-1, ECMWF ensemble)'),
    ('p_dry_spell', 'county bulletin', 'chance of a 7-day dry spell within 15 days (0-1)'),
    ('p_wet_spell', 'county bulletin', 'chance of a 3-day wet spell in week 1 (0-1)'),
    ('week1_rain_mm', 'county bulletin', 'median rain expected in week 1 (mm)'),
    ('week2_rain_mm', 'county bulletin', 'median rain expected in week 2 (mm)'),
    ('soil_z', 'county bulletin', 'root-zone soil moisture z-score (>= 0.75 wet, <= -0.75 dry)'),
    ('soil_deficit_mm', 'county bulletin', 'root-zone soil water below the seasonal median (mm)'),
    ('rain_30d_pct', 'county bulletin', 'last 30 days of rain as % of normal'),
    ('pop_total', 'county bulletin', 'county population (2025 estimate)'),
    ('pop_flood_prone', 'county bulletin', 'people on ground that has flooded before'),
    ('dry_spell_days', 'county bulletin', 'observed days since the last wet county-day (GSMaP)'),
    ('p_soil_recovery', 'county bulletin', 'chance that 2 weeks of rain refill the soil deficit (0-1, ECMWF ensemble)'),
    ('news_flood', 'county bulletin', 'True when news reported flooding or heavy rainfall in the county (last 21 '
                                      'days); supports a red alert but is not required for one'),
    ('news_drought', 'county bulletin', 'True when news reported drought or a dry spell in the county (last 21 '
                                        'days); supports a red alert but is not required for one'),
    ('river_level_m', 'station_status.csv', 'latest satellite water level at the county gauge (m)'),
    ('river_age_days', 'station_status.csv', 'days since that satellite pass'),
    ('river_rate_m_per_day', 'station_status.csv', 'rise (+) or fall (-) at the last pass (m per day)'),
    ('river_rising', 'station_status.csv', 'True when the rate is above zero'),
    ('river_pctile', 'station_status.csv', 'seasonal percentile of the last pass: how unusual for the time of year (0-100)'),
    ('river_rise_m', 'merged_altimetry_stations.csv', "rise since this year's dry-season low (February-May) at the gauge (m)"),
    ('lvl_2yr_m', 'station_status.csv', '2-year flood level at the gauge (m)'),
    ('lvl_5yr_m', 'station_status.csv', '5-year flood level (m)'),
    ('lvl_10yr_m', 'station_status.csv', '10-year flood level (m)'),
    ('readiness_level_m', 'aa_triggers.csv', 'readiness water level, when the county rule uses levels (else 2-year level - 0.25 m if the county has no aa_triggers.csv row)'),
    ('activation_level_m', 'aa_triggers.csv', 'activation water level, when the county rule uses levels (else the 2-year level)'),
    ('readiness_value', 'aa_triggers.csv', "readiness value of the county's trigger signal (units depend on trigger_family)"),
    ('activation_value', 'aa_triggers.csv', "activation value of the county's trigger signal"),
    ('regional_value', 'aa_triggers.csv', 'regional index needed together with the county signal (combined rules)'),
    ('sudd_upstream_pct', 'sudd_trigger_log.csv', 'experimental Sudd river trigger: upstream percentile (0-1)'),
    ('sudd_status', 'sudd_trigger_log.csv', "'normal', 'watch' or 'elevated'"),
    ('flooded_now_km2', 'exposure_cache.json', 'area flooded now (latest Sentinel-1 extent, km2)'),
    ('flooded_now_share', 'exposure_cache.json', 'share of the county flooded now (0-1)'),
    ('month', 'run date', 'month of the run, 1-12'),
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


def isnull(v):
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


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


def show(v, fmt='{:,.0f}'):
    """Readable cell: blank -> 'not set', numbers formatted."""
    if isnull(v) or str(v).strip() == '':
        return 'not set'
    x = pd.to_numeric(v, errors='coerce')
    return fmt.format(float(x)) if not isnull(x) else str(v)


def plain(v):
    """JSON/CSV-friendly scalar."""
    if isnull(v):
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return round(float(v), 4)
    return v


# =========================================================================== #
# SAFE RULES                                                                  #
# =========================================================================== #
_ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd, ast.Compare,
            ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq, ast.In, ast.NotIn, ast.Name, ast.Load, ast.Constant,
            ast.Tuple, ast.List, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div)
_CMP = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Eq: operator.eq,
        ast.NotEq: operator.ne, ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
KNOWN = {v[0] for v in VARIABLES}


def compile_rule(rule):
    """Parse a rule; raises ValueError naming the problem. Empty rule -> None (never met)."""
    s = '' if isnull(rule) else str(rule).strip()
    if not s:
        return None
    s = re.sub(r'\bAND\b', 'and', re.sub(r'\bOR\b', 'or', re.sub(r'\bNOT\b', 'not', s)))
    try:
        tree = ast.parse(s, mode='eval')
    except SyntaxError as e:
        raise ValueError(f'cannot read rule "{s}": {e.msg}')
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ValueError(f'"{type(node).__name__}" is not allowed in a rule: "{s}"')
    unknown = sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - KNOWN - {'True', 'False'})
    if unknown:
        raise ValueError(f"unknown name(s) {', '.join(unknown)} in \"{s}\" (see --list-variables)")
    return tree


def evaluate(tree, env, missing):
    """Three-valued evaluation: True, False, or None when a needed value is missing (names added to `missing`)."""
    if tree is None:
        return None

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            v = env.get(n.id)
            if isnull(v):
                missing.add(n.id)
                return None
            return v
        if isinstance(n, (ast.Tuple, ast.List)):
            return [ev(e) for e in n.elts]
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            if v is None:
                return None
            return (not v) if isinstance(n.op, ast.Not) else (-v if isinstance(n.op, ast.USub) else +v)
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            if a is None or b is None:
                return None
            try:
                return _BIN[type(n.op)](a, b)
            except (ZeroDivisionError, TypeError):
                return None
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            if isinstance(n.op, ast.And):
                if any(v is not None and not v for v in vals):
                    return False
                return None if any(v is None for v in vals) else True
            if any(v is not None and v for v in vals):
                return True
            return None if any(v is None for v in vals) else False
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = ev(comp)
                if left is None or right is None:
                    return None
                if isinstance(right, list):
                    right = [x for x in right if x is not None]
                try:
                    if not _CMP[type(op)](left, right):
                        return False
                except TypeError:
                    return None
                left = right
            return True
        raise ValueError(f'unsupported element {type(n).__name__}')

    out = ev(tree)
    return None if out is None else bool(out)


# =========================================================================== #
# SEASONS AND STAGES                                                          #
# =========================================================================== #
def mmdd(s, default):
    m = re.fullmatch(r'\s*(\d{1,2})-(\d{1,2})\s*', '' if isnull(s) else str(s))
    return (int(m.group(1)), int(m.group(2))) if m else mmdd(default, '07-01')


def season_of(day, start, end):
    """Season label (year the season opened) or None when `day` is outside the season window."""
    (sm, sd), (em, ed) = mmdd(start, DEFAULTS['season_start']), mmdd(end, DEFAULTS['season_end'])
    if (sm, sd) == (1, 1) and (em, ed) == (12, 31):
        return day.year
    if (em, ed) >= (sm, sd):
        return day.year if (sm, sd) <= (day.month, day.day) <= (em, ed) else None
    if (day.month, day.day) >= (sm, sd):
        return day.year
    if (day.month, day.day) <= (em, ed):
        return day.year - 1
    return None


def plan_env(env, plan):
    """Copy of the county values with stale river readings removed for this plan."""
    e = dict(env)
    age = e.get('river_age_days')
    if isnull(age) or age > plan['max_data_age_days']:
        for v in RIVER_VARS:
            e[v] = None
    return e


def step(plan, st, env, now):
    """One evaluation of one plan. Returns (new state, transitions, evaluation)."""
    st = dict(st or {})
    for k, v in (('stage', 'normal'), ('since', None), ('confirm', 0), ('quiet', 0), ('season', None),
                 ('activations', 0), ('last_sig', None), ('readiness_since', None)):
        st.setdefault(k, v)
    trans = []
    stamp = now.strftime('%Y-%m-%d %H:%M')

    def move(to, why):
        trans.append({'from_stage': st['stage'], 'to_stage': to, 'reason': why})
        st.update(stage=to, since=stamp, quiet=0)
        if to != 'readiness':                     # keep an activation count that is building up
            st['confirm'] = 0
        if to == 'readiness':
            st['readiness_since'] = stamp
        if to == 'activated' and not st.get('readiness_since'):
            st['readiness_since'] = stamp

    season = season_of(now.date(), plan['season_start'], plan['season_end'])
    if season is None:
        if st['stage'] in ('readiness', 'activated'):
            move('out of season', 'season closed')
        else:
            st.update(stage='out of season', confirm=0, quiet=0)
        return st, trans, {'readiness': None, 'activation': None, 'missing': [], 'in_season': False}
    if st['season'] != season:
        if st['stage'] in ('readiness', 'activated'):
            move('normal', f'new season {season}')
        st.update(season=season, activations=0, readiness_since=None)
    if st['stage'] == 'out of season':
        st.update(stage='normal', since=stamp)

    e = plan_env(env, plan)
    missing = set()
    r = evaluate(plan['_ready'], e, missing)
    a = evaluate(plan['_act'], e, missing)
    sig = env.get('_signature')
    if a is True and st['activations'] < plan['max_activations_per_season'] and st['stage'] != 'activated':
        if plan['confirm_runs'] <= 1 or sig != st.get('last_sig'):
            st['confirm'] += 1
            st['last_sig'] = sig
        if st['confirm'] >= plan['confirm_runs']:
            move('activated', 'activation rule met' + (f" on {plan['confirm_runs']} distinct observations"
                                                       if plan['confirm_runs'] > 1 else ''))
            st['activations'] += 1
    elif a is not True and st['stage'] != 'activated':
        st['confirm'] = 0
    if st['stage'] == 'normal' and r is True:
        move('readiness', 'readiness rule met')
    elif st['stage'] == 'readiness':
        if r is True or a is True:
            st['quiet'] = 0
        else:
            st['quiet'] += 1
            if st['quiet'] >= plan['stand_down_runs']:
                move('normal', f"readiness rule not met on {plan['stand_down_runs']} runs in a row (stood down)")
    return st, trans, {'readiness': r, 'activation': a, 'missing': sorted(missing), 'in_season': True}


# =========================================================================== #
# DATA -> VALUES PER COUNTY                                                   #
# =========================================================================== #
def num(v):
    v = pd.to_numeric(v, errors='coerce')
    return None if isnull(v) else float(v)


def build_values(as_of):
    """{county key: {name: value}} from the platform's latest outputs."""
    as_of = pd.Timestamp(as_of).tz_localize(None).normalize()
    vals, sources = {}, {}
    bul = read_csv(os.path.join(BUL_DIR, 'county_bulletin_latest.csv'))
    if bul is not None:
        sources['bulletin'] = 'county_bulletin_latest.csv'
        for r in bul.to_dict('records'):
            lvl = None if isnull(r.get('alert_level')) else str(r.get('alert_level')).lower()
            stage = None if isnull(r.get('alert_stage')) else str(r.get('alert_stage')).lower()
            vals.setdefault(ckey(r['county']), {}).update({
                'county': r['county'], 'state': r.get('state'), 'alert_level': lvl, 'alert_stage': stage,
                'alert_rank': ALERT_RANK.get(lvl), 'alert_hazard': None if isnull(r.get('alert_hazard')) else r.get('alert_hazard'),
                'p_heavy': num(r.get('p_heavy_50mm_week1')), 'p_dry_spell': num(r.get('p_dry_spell_7d_in_15d')),
                'p_wet_spell': num(r.get('p_wet_spell_3d_week1')), 'week1_rain_mm': num(r.get('week1_rain_median_mm')),
                'week2_rain_mm': num(r.get('week2_rain_median_mm')), 'soil_z': num(r.get('sm_rootzone_z')),
                'soil_deficit_mm': num(r.get('soil_deficit_mm')), 'rain_30d_pct': num(r.get('rain_30d_pct_of_normal')),
                'pop_total': num(r.get('pop_total')), 'pop_flood_prone': num(r.get('pop_flood_prone')),
                'dry_spell_days': num(r.get('dry_spell_days')), 'p_soil_recovery': num(r.get('p_soil_recovery_2wk')),
                'news_flood': not isnull(r.get('news_flood_report')) and str(r.get('news_flood_report')).strip() != '',
                'news_drought': not isnull(r.get('news_drought_report')) and str(r.get('news_drought_report')).strip() != '',
                '_bulletin': str(r.get('run_utc') or r.get('data_end_date') or '')})
    lpath = first_existing(os.path.join(BUL_DIR, 'county_station_link.csv'), os.path.join(HERE, 'county_station_link.csv'))
    link = read_csv(lpath)
    status = read_csv(os.path.join(ALT_DIR, 'station_status.csv'))
    trig = read_csv(os.path.join(AA_OUT, 'aa_triggers.csv'))
    st_by = status.set_index('station_uid').to_dict('index') if status is not None and 'station_uid' in status else {}
    rises = rise_now(as_of)
    if rises:
        sources['river rise'] = 'merged_altimetry_stations.csv'
    tr_by = {ckey(r['county']): r for r in trig.to_dict('records')} if trig is not None else {}
    if link is not None:
        sources['gauges'] = os.path.basename(lpath) + (' + station_status.csv' if st_by else '')
        for r in link.to_dict('records'):
            k = ckey(r['county'])
            uid = r.get('station_uid')
            if isnull(uid) or str(r.get('relation')) in ('none', 'nan'):
                continue
            s = st_by.get(uid, {})
            last_date = s.get('last_date', r.get('last_date'))
            d = pd.to_datetime(last_date, errors='coerce')
            rate = num(s.get('rate_m_per_day', r.get('rate_m_per_day')))
            l2 = num(s.get('lvl_2yr_m'))
            t = tr_by.get(k, {})
            v = vals.setdefault(k, {'county': r['county'], 'state': r.get('state')})
            v.update({'station_uid': uid, 'station_name': r.get('station_name'),
                      'river_level_m': num(s.get('last_level_m', r.get('last_level_m'))),
                      'river_obs_date': None if isnull(d) else d.date().isoformat(),
                      'river_age_days': None if isnull(d) else int((as_of - d.normalize()).days),
                      'river_rate_m_per_day': rate, 'river_rising': None if rate is None else rate > 0,
                      'river_pctile': num(s.get('seasonal_pctile', r.get('seasonal_pctile'))),
                      'lvl_2yr_m': l2, 'lvl_5yr_m': num(s.get('lvl_5yr_m')), 'lvl_10yr_m': num(s.get('lvl_10yr_m')),
                      'readiness_level_m': num(t.get('readiness_level_m')) if t else (None if l2 is None else l2 - 0.25),
                      'activation_level_m': num(t.get('activation_level_m')) if t else l2,
                      'readiness_value': num(t.get('readiness_value')) if t else None,
                      'activation_value': num(t.get('activation_value')) if t else None,
                      'regional_value': num(t.get('regional_value')) if t else None,
                      'river_rise_m': rises.get(uid, num(t.get('last_rise_m')) if t else None),
                      '_levels_from': 'aa_triggers.csv' if t else '2-year level (no aa_triggers.csv row)'})
    sud = read_csv(os.path.join(BUL_DIR, 'sudd_trigger_log.csv'))
    sudd = {}
    if sud is not None and len(sud):
        last = sud.sort_values('latest_month').iloc[-1]
        sudd = {'sudd_upstream_pct': num(last.get('upstream_pct')), 'sudd_status': last.get('status')}
        sources['sudd trigger'] = 'sudd_trigger_log.csv'
    nowmap = {}
    p = os.path.join(DATA_DIR, 'exposure_cache.json')
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8') as fh:
                ex = json.load(fh)
            for name, payams in (ex.get('payams_now') or {}).items():
                if isinstance(payams, dict):
                    a_now = sum(max(x.get('area_now_km2') or 0, 0) for x in payams.values())
                    a_tot = sum((x.get('area_km2') or 0) for x in (ex.get('payams', {}).get(name) or []))
                    nowmap[ckey(name)] = (a_now, a_now / a_tot if a_tot else None)
            sources['flood extent now'] = 'exposure_cache.json'
        except Exception as e:
            print(f"WARNING: exposure_cache.json not read: {e}")
    for k, v in vals.items():
        v.update(sudd)
        if k in nowmap:
            v['flooded_now_km2'], v['flooded_now_share'] = nowmap[k]
        v['month'] = int(as_of.month)
        v['_signature'] = f"{v.get('river_obs_date')}|{v.get('_bulletin')}"
    return vals, sources


def rise_now(as_of):
    """{station: latest level minus this year's dry-season (February-May) low}, from the merged altimetry file."""
    path = os.path.join(ALT_DIR, 'merged_altimetry_stations.csv')
    if not os.path.exists(path):
        return {}
    try:
        want = {'date', LEVEL_COL, 'station_uid', 'source', 'station_id', 'qc_status'}
        d = pd.read_csv(path, low_memory=False, usecols=lambda c: c in want)
        if 'station_uid' not in d.columns:
            sid = pd.to_numeric(d['station_id'], errors='coerce')
            d['station_uid'] = (d['source'].astype(str).str.lower() + ':' +
                                sid.round().astype('Int64').astype(str)).where(sid.notna())
        d['date'] = pd.to_datetime(d['date'], errors='coerce')
        d['level'] = pd.to_numeric(d[LEVEL_COL], errors='coerce')
        d = d.dropna(subset=['date', 'level', 'station_uid'])
        d = d[d['date'] <= pd.Timestamp(as_of)]
        if 'qc_status' in d.columns:
            ok = text(d['qc_status']).str.lower().eq('ok')
            if ok.mean() > 0.5:
                d = d[ok]
        out = {}
        for uid, g in d.sort_values('date').groupby('station_uid'):
            last = g.iloc[-1]
            dry = g[(g['date'].dt.year == last['date'].year) & g['date'].dt.month.isin(DRY_MONTHS)]
            if len(dry):
                out[uid] = float(last['level'] - dry['level'].min())
        return out
    except Exception as e:
        print(f"WARNING: river rise not computed ({type(e).__name__}: {e})")
        return {}


# =========================================================================== #
# PLANS                                                                       #
# =========================================================================== #
PLAN_COLS = ['plan_id', 'status', 'hazard', 'state', 'county', 'readiness_rule', 'activation_rule', 'confirm_runs',
             'max_data_age_days', 'stand_down_runs', 'max_activations_per_season', 'season_start', 'season_end',
             'lead_time_days', 'people_target', 'households_target', 'budget_usd', 'funding_source',
             'fund_release_rule', 'lead_agency', 'partners', 'mne_reference', 'validated_by', 'validated_date', 'notes']
ACTION_COLS = ['plan_id', 'stage', 'action_no', 'action', 'sector', 'lead', 'partners', 'beneficiaries', 'budget_usd',
               'deadline_days', 'status']
EXAMPLE_ACTIONS = [
    ('readiness', 'Verify the trigger reading with SSMS / MWRI; notify the state TWG-AA and the county commissioner',
     'coordination', 1),
    ('readiness', 'Issue the early warning through radio listening hubs, chiefs and community groups in local languages',
     'early warning', 2),
    ('readiness', 'Confirm beneficiary lists, payment and distribution channels; check pre-positioned stocks', 'logistics', 5),
    ('activation', 'Release pre-arranged funds according to the release rule', 'finance', 3),
    ('activation', 'Anticipatory cash transfers to targeted households', 'cash', 7),
    ('activation', 'Move livestock, seed and food stocks to high ground; support livestock vaccination', 'livelihoods', 7),
    ('activation', 'Distribute water treatment supplies and ORS; cholera prevention messages', 'WASH / health', 7),
    ('activation', 'Reinforce and patrol dykes with community groups', 'DRR', 5),
]


DEFAULT_RULES = ("river_level_m >= readiness_level_m or (alert_hazard == 'flood / waterlogging' and alert_rank >= 2)",
                 "river_level_m >= activation_level_m or (alert_hazard == 'flood / waterlogging' and "
                 "alert_level == 'red' and soil_z >= 0.75)")


def suggested_rules():
    """{county key: (readiness rule, activation rule)} from aa_triggers.csv (aa_p2_trigger_scorecard.py)."""
    trig = read_csv(os.path.join(AA_OUT, 'aa_triggers.csv'))
    if trig is None or 'suggested_readiness_rule' not in trig:
        return {}
    out = {}
    for r in trig.to_dict('records'):
        if not isnull(r.get('suggested_readiness_rule')) and not isnull(r.get('suggested_activation_rule')):
            out[ckey(r['county'])] = (str(r['suggested_readiness_rule']), str(r['suggested_activation_rule']))
    return out


def refresh_examples():
    """Untouched example plans follow the scorecard's latest suggested rules. Returns the plan ids changed.
    A plan stops being refreshed as soon as its status or notes are edited."""
    path = os.path.join(AA_CONFIG, 'aap_plans.csv')
    df = read_csv(path, dtype=str)
    sug = suggested_rules()
    if df is None or not sug:
        return set()
    changed = set()
    for i, r in df.iterrows():
        if str(r.get('status', '')).startswith('draft (example)') and str(r.get('notes', '')).startswith(EXAMPLE_NOTE):
            rr, ar = sug.get(ckey(r['county']), (None, None))
            if rr and (r.get('readiness_rule') != rr or r.get('activation_rule') != ar):
                df.at[i, 'readiness_rule'], df.at[i, 'activation_rule'] = rr, ar
                if not str(r.get('notes', '')).startswith(EXAMPLE_NOTE + '. Rules follow'):
                    df.at[i, 'notes'] = (EXAMPLE_NOTE + '. Rules follow aa_triggers.csv and are refreshed while the plan '
                                         'is an untouched example. ' + str(r.get('notes', ''))[len(EXAMPLE_NOTE) + 2:])
                changed.add(r['plan_id'])
    if changed:
        df.to_csv(path, index=False)
        print(f"Example plans now follow the latest suggested rules: {', '.join(sorted(changed))}")
    return changed


def write_examples():
    """Draft plans for the highest-risk linked counties, clearly marked as examples."""
    if os.path.exists(os.path.join(AA_CONFIG, 'aap_plans.csv')):
        return False
    os.makedirs(AA_CONFIG, exist_ok=True)
    trig = read_csv(os.path.join(AA_OUT, 'aa_triggers.csv'))
    risk = read_csv(os.path.join(AA_OUT, 'p1_county_risk_profile.csv'))
    scen = read_csv(os.path.join(DATA_DIR, 'flood_scenarios_2026_county.csv'))
    link = read_csv(first_existing(os.path.join(BUL_DIR, 'county_station_link.csv'),
                                   os.path.join(HERE, 'county_station_link.csv')))
    pool = trig if trig is not None else link
    if pool is None:
        pool = pd.DataFrame(columns=['county', 'state'])
    pool = pool[['county', 'state']].drop_duplicates('county').copy()
    pool['key'] = pool['county'].map(ckey)
    if risk is not None:
        rk = dict(zip(risk['county'].map(ckey), risk['risk_rank']))
        pool['order'] = pool['key'].map(rk)
    elif scen is not None:
        sc = dict(zip(scen['county'].map(ckey), -pd.to_numeric(scen['scenario2_planning'], errors='coerce')))
        pool['order'] = pool['key'].map(sc)
    else:
        pool['order'] = range(len(pool))
    pool = pool.sort_values('order').head(EXAMPLE_PLANS)
    people = dict(zip(scen['county'].map(ckey), scen['scenario2_planning'])) if scen is not None else {}
    suggested = suggested_rules()
    plans, acts = [], []
    for r in pool.itertuples():
        pid = 'AAP-FL-' + re.sub(r'[^A-Z0-9]+', '', str(r.county).upper())[:14]
        rr, ar = suggested.get(r.key, DEFAULT_RULES)
        plans.append({
            'plan_id': pid, 'status': 'draft (example) - not validated', 'hazard': 'riverine and flash flood',
            'state': r.state, 'county': r.county, 'readiness_rule': rr, 'activation_rule': ar,
            'confirm_runs': 1, 'max_data_age_days': DEFAULTS['max_data_age_days'],
            'stand_down_runs': DEFAULTS['stand_down_runs'], 'max_activations_per_season': 1,
            'season_start': DEFAULTS['season_start'], 'season_end': DEFAULTS['season_end'], 'lead_time_days': 30,
            'people_target': people.get(r.key, ''), 'households_target': '', 'budget_usd': '', 'funding_source': '',
            'fund_release_rule': 'e.g. pre-arranged release within 72 hours of activation', 'lead_agency': '',
            'partners': '', 'mne_reference': '', 'validated_by': '', 'validated_date': '',
            'notes': EXAMPLE_NOTE + '. Rules follow aa_triggers.csv and are refreshed while the plan is an '
                     'untouched example. people_target = planning scenario in data/flood_scenarios_2026_county.csv. '
                     'Replace rules, targets, budget and leads with the plan the TWG-AA validates.'})
        for i, (stage, action, sector, days) in enumerate(EXAMPLE_ACTIONS, start=1):
            acts.append({'plan_id': pid, 'stage': stage, 'action_no': i, 'action': action, 'sector': sector,
                         'lead': '', 'partners': '', 'beneficiaries': '', 'budget_usd': '', 'deadline_days': days,
                         'status': 'open'})
    pd.DataFrame(plans, columns=PLAN_COLS).to_csv(os.path.join(AA_CONFIG, 'aap_plans.csv'), index=False)
    if not os.path.exists(os.path.join(AA_CONFIG, 'aap_actions.csv')):
        pd.DataFrame(acts, columns=ACTION_COLS).to_csv(os.path.join(AA_CONFIG, 'aap_actions.csv'), index=False)
    print(f"Example plans written to {AA_CONFIG} for {', '.join(pool['county'])}: drafts to replace with the "
          'TWG-AA validated plans.')
    return True


def load_plans(path=None):
    path = path or os.path.join(AA_CONFIG, 'aap_plans.csv')
    df = read_csv(path)
    if df is None:
        return [], [f'{path} not found']
    plans, errors = [], []
    for r in df.to_dict('records'):
        if isnull(r.get('plan_id')) or isnull(r.get('county')):
            continue
        p = {c: r.get(c) for c in PLAN_COLS}
        for k in ('confirm_runs', 'max_data_age_days', 'stand_down_runs', 'max_activations_per_season'):
            v = pd.to_numeric(p.get(k), errors='coerce')
            p[k] = int(v) if not isnull(v) else DEFAULTS[k]
        for k in ('season_start', 'season_end'):
            p[k] = DEFAULTS[k] if isnull(p.get(k)) else str(p[k])
        p['status'] = '' if isnull(p.get('status')) else str(p['status'])
        p['key'] = ckey(p['county'])
        try:
            p['_ready'] = compile_rule(p.get('readiness_rule'))
            p['_act'] = compile_rule(p.get('activation_rule'))
        except ValueError as e:
            errors.append(f"{p['plan_id']}: {e}")
            continue
        plans.append(p)
    return plans, errors


def load_actions(path=None):
    df = read_csv(path or os.path.join(AA_CONFIG, 'aap_actions.csv'))
    return df if df is not None else pd.DataFrame(columns=ACTION_COLS)


# =========================================================================== #
# OUTPUTS                                                                     #
# =========================================================================== #
def checklist(plans, states, actions):
    rows = []
    for p in plans:
        st = states.get(p['plan_id'], {})
        stage = st.get('stage')
        if stage not in ('readiness', 'activated'):
            continue
        stages = ['readiness'] + (['activation'] if stage == 'activated' else [])
        a = actions[(actions['plan_id'] == p['plan_id']) & text(actions['stage']).str.lower().isin(stages)]
        for r in a.to_dict('records'):
            base = st.get('readiness_since') if str(r['stage']).lower() == 'readiness' else st.get('since')
            dd = pd.to_numeric(r.get('deadline_days'), errors='coerce')
            due = (pd.Timestamp(base) + pd.Timedelta(days=float(dd))).strftime('%Y-%m-%d') if base and not isnull(dd) else ''
            rows.append({'plan_id': p['plan_id'], 'county': p['county'], 'plan_stage': stage, 'action_stage': r['stage'],
                         'action_no': r.get('action_no'), 'action': r.get('action'), 'sector': r.get('sector'),
                         'lead': r.get('lead'), 'beneficiaries': r.get('beneficiaries'), 'budget_usd': r.get('budget_usd'),
                         'due': due, 'status': r.get('status')})
    return pd.DataFrame(rows)


def write_report(p, st, ev, env, actions, when, folder):
    os.makedirs(folder, exist_ok=True)
    stage = st['stage']
    path = os.path.join(folder, f"{p['plan_id']}_{when:%Y%m%d_%H%M}_{stage}.md")
    draft = not str(p.get('status', '')).lower().startswith('validated')
    keys = ['river_level_m', 'river_obs_date', 'river_age_days', 'readiness_level_m', 'activation_level_m',
            'lvl_2yr_m', 'alert_level', 'alert_hazard', 'p_heavy', 'soil_z', 'sudd_status', 'flooded_now_km2']
    lines = [f"# {'Activation' if stage == 'activated' else 'Readiness'} report - {p['plan_id']} ({p['county']}, "
             f"{p.get('state', '')})", '',
             f"Issued {when:%Y-%m-%d %H:%M} UTC by aa_p3_aap_engine.py (Roadmap on Anticipatory Action, Pillar 3).", '']
    if draft:
        lines += ['> **DRAFT PLAN - not validated by the TWG-AA.** Treat this as an exercise or advisory, not a '
                  'decision to release funds.', '']
    lines += [f"**Hazard:** {p.get('hazard', '')}  ", f"**Stage:** {stage} (season {st.get('season')})  ",
              f"**Rule met:** `{p.get('activation_rule') if stage == 'activated' else p.get('readiness_rule')}`", '',
              '## Readings at the time of the decision', '| Value | Reading |', '|---|---|']
    for k in keys:
        if not isnull(env.get(k)):
            lines.append(f"| {k} | {plain(env.get(k))} |")
    if ev.get('missing'):
        lines += ['', f"Missing or stale values (counted as not met): {', '.join(ev['missing'])}."]
    lines += ['', '## Targets and funding',
              f"- People targeted: {show(p.get('people_target'))}",
              f"- Households targeted: {show(p.get('households_target'))}",
              f"- Budget (USD): {show(p.get('budget_usd'))}; source: {show(p.get('funding_source'))}",
              f"- Fund release rule: {show(p.get('fund_release_rule'))}",
              f"- Lead agency: {show(p.get('lead_agency'))}; M&E: {show(p.get('mne_reference'))}", '',
              '## Actions now due']
    cl = checklist([p], {p['plan_id']: st}, actions)
    if len(cl):
        lines += ['| Stage | # | Action | Lead | Due | Status |', '|---|---|---|---|---|---|']
        for r in cl.itertuples():
            lines.append(f"| {r.action_stage} | {r.action_no} | {r.action} | {'' if isnull(r.lead) else r.lead} | "
                         f"{r.due} | {'' if isnull(r.status) else r.status} |")
    else:
        lines.append('No actions listed for this plan in aap_actions.csv.')
    lines += ['', '## Before acting', '- Confirm the reading with SSMS / MWRI (satellite levels can be noisy).',
              '- Record the TWG-AA decision, time of fund release and first action in the activation log.']
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return path


def run(as_of=None, dry_run=False):
    when = pd.Timestamp(as_of).to_pydatetime() if as_of else now_utc().replace(tzinfo=None)
    write_examples()
    refreshed = set() if dry_run else refresh_examples()
    plans, errors = load_plans()
    for e in errors:
        print(f"WARNING: plan skipped - {e}")
    actions = load_actions()
    values, sources = build_values(when)
    state_path = os.path.join(AA_OUT, 'aap_state.json')
    states = {}
    if os.path.exists(state_path):
        with open(state_path, encoding='utf-8') as fh:
            states = json.load(fh)
    rows, log_rows, reports = [], [], []
    for p in plans:
        env = values.get(p['key'], {})
        if not env:
            print(f"WARNING: {p['plan_id']}: no data for county '{p['county']}' (check the name)")
        sig = f"{p.get('readiness_rule')} || {p.get('activation_rule')}"
        st0 = states.get(p['plan_id'])
        validated = str(p.get('status', '')).lower().startswith('validated')
        reset = []
        if st0 is not None and not validated and (p['plan_id'] in refreshed or st0.get('rules') not in (None, sig)):
            if st0.get('stage') in ('readiness', 'activated'):
                reset = [{'from_stage': st0.get('stage'), 'to_stage': 'normal',
                          'reason': 'plan rules changed: draft plan restarted'}]
            st0 = None
        st, trans, ev = step(p, st0, env, when)
        trans = reset + trans
        st['rules'] = sig
        states[p['plan_id']] = st
        for t in trans:
            rep = ''
            if t['to_stage'] in ('readiness', 'activated') and not dry_run:
                rep = write_report(p, st, ev, env, actions, when, os.path.join(AA_OUT, 'aap_reports'))
                reports.append(rep)
            log_rows.append({'time_utc': when.strftime('%Y-%m-%d %H:%M'), 'plan_id': p['plan_id'], 'county': p['county'],
                             'state': p.get('state'), 'hazard': p.get('hazard'), 'plan_status': p.get('status'),
                             **t, 'river_level_m': plain(env.get('river_level_m')),
                             'river_obs_date': env.get('river_obs_date'),
                             'readiness_level_m': plain(env.get('readiness_level_m')),
                             'activation_level_m': plain(env.get('activation_level_m')),
                             'alert_level': env.get('alert_level'), 'alert_hazard': env.get('alert_hazard'),
                             'p_heavy': plain(env.get('p_heavy')), 'report': os.path.basename(rep) if rep else ''})
        rows.append({'plan_id': p['plan_id'], 'county': p['county'], 'state': p.get('state'), 'hazard': p.get('hazard'),
                     'plan_status': p.get('status'), 'stage': st['stage'], 'stage_since': st.get('since'),
                     'season': st.get('season'), 'activations_this_season': st.get('activations'),
                     'readiness_now': ev['readiness'], 'activation_now': ev['activation'],
                     'missing_or_stale': ', '.join(ev['missing']),
                     **{k: plain(env.get(k)) for k in ('river_level_m', 'river_obs_date', 'river_age_days',
                                                       'readiness_level_m', 'activation_level_m', 'alert_level',
                                                       'alert_hazard', 'p_heavy', 'soil_z')},
                     'people_target': p.get('people_target'), 'budget_usd': p.get('budget_usd'),
                     'lead_agency': p.get('lead_agency'), 'evaluated_utc': when.strftime('%Y-%m-%d %H:%M')})
    status = pd.DataFrame(rows)
    cl = checklist(plans, states, actions)
    if not dry_run:
        os.makedirs(AA_OUT, exist_ok=True)
        with open(state_path, 'w', encoding='utf-8') as fh:
            json.dump(states, fh, indent=1, default=str)
        status.to_csv(os.path.join(AA_OUT, 'aap_status_latest.csv'), index=False)
        cl.to_csv(os.path.join(AA_OUT, 'aap_checklist_latest.csv'), index=False)
        write_checklist_md(status, cl, when, os.path.join(AA_OUT, 'aap_checklist_latest.md'))
        if log_rows:
            lp = os.path.join(AA_OUT, 'aap_activation_log.csv')
            old = read_csv(lp)
            new = pd.DataFrame(log_rows)
            (new if old is None else pd.concat([old.astype(object), new.astype(object)], ignore_index=True)).to_csv(lp, index=False)
        write_variables(values)
        n_valid = sum(1 for p in plans if str(p.get('status', '')).lower().startswith('validated'))
        ind = [dict(pillar='3', activity='Develop standardised AAPs for multi-hazard',
                    indicator='Anticipatory action plans developed', value=len(plans), kind='snapshot', unit='plans',
                    verification='aa_config/aap_plans.csv'),
               dict(pillar='3', activity='Develop standardised AAPs for multi-hazard',
                    indicator='Anticipatory action plans validated', value=n_valid, kind='snapshot', unit='plans',
                    verification='aa_config/aap_plans.csv (status, validated_by, validated_date)'),
               dict(pillar='3', activity='Joint activation of the AAPs when the threshold is reached',
                    indicator='Plans in readiness or activated now',
                    value=int(status['stage'].isin(['readiness', 'activated']).sum()) if len(status) else 0,
                    kind='snapshot', unit='plans', verification='aap_status_latest.csv')]
        for r in log_rows:
            if r['to_stage'] == 'activated':
                valid = str(r.get('plan_status') or '').lower().startswith('validated')
                ind.append(dict(pillar='3', activity='Joint activation of the AAPs when the threshold is reached',
                                indicator='AAPs activated' if valid else
                                'Draft-plan activation levels reached (not counted as activations)',
                                value=1, kind='event', unit='activations', verification=r['report'],
                                note=f"{r['plan_id']} ({r['plan_status']})"))
            elif r['to_stage'] == 'readiness':
                ind.append(dict(pillar='3', activity='Joint activation of the AAPs when the threshold is reached',
                                indicator='Readiness stages reached', value=1, kind='event', unit='plans',
                                verification=r['report'], note=r['plan_id']))
        log_indicators(ind, 'aa_p3_aap_engine.py')
    return status, pd.DataFrame(log_rows), cl, reports, sources, errors


def write_checklist_md(status, cl, when, path):
    lines = [f"# Anticipatory action plans - status {when:%Y-%m-%d %H:%M} UTC", '']
    if status.empty:
        lines.append('No plans loaded.')
    else:
        lines += ['| Plan | County | Stage | Since | River level / readiness / activation (m) | Alert | Missing or stale |',
                  '|---|---|---|---|---|---|---|']
        for r in status.itertuples():
            lv = '/'.join('' if isnull(x) else f'{x:.2f}' for x in (r.river_level_m, r.readiness_level_m,
                                                                     r.activation_level_m))
            lines.append(f"| {r.plan_id} | {r.county} | **{r.stage}** | {'' if isnull(r.stage_since) else r.stage_since} | {lv} | "
                         f"{'' if isnull(r.alert_level) else r.alert_level} | {r.missing_or_stale} |")
    if len(cl):
        lines += ['', '## Actions due', '| Plan | Stage | # | Action | Lead | Due | Status |', '|---|---|---|---|---|---|---|']
        for r in cl.sort_values(['due', 'plan_id']).itertuples():
            lines.append(f"| {r.plan_id} | {r.action_stage} | {r.action_no} | {r.action} | "
                         f"{'' if isnull(r.lead) else r.lead} | {r.due} | {'' if isnull(r.status) else r.status} |")
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')


def write_variables(values):
    ex = next((v for v in values.values() if v.get('river_level_m') is not None), next(iter(values.values()), {}))
    pd.DataFrame([{'name': n, 'source': s, 'meaning': m, 'example_county': ex.get('county'),
                   'example_value': plain(ex.get(n))} for n, s, m in VARIABLES]).to_csv(
        os.path.join(AA_OUT, 'aap_rule_variables.csv'), index=False)


def main():
    ap = argparse.ArgumentParser(description='Pillar 3 anticipatory action plan engine')
    ap.add_argument('--as-of', help='evaluate as of this date/time (UTC), e.g. 2026-10-05 or 2026-10-05T09:30')
    ap.add_argument('--dry-run', action='store_true', help='evaluate and print only; write nothing')
    ap.add_argument('--list-variables', action='store_true', help='print the names a rule can use, with values now')
    ap.add_argument('--selftest', action='store_true', help='check rules and stage changes on synthetic data and exit')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.list_variables:
        values, _ = build_values(a.as_of or now_utc().date())
        ex = next((v for v in values.values() if v.get('river_level_m') is not None), {})
        print(pd.DataFrame([{'name': n, 'source': s, 'meaning': m, f"value ({ex.get('county', '-')})": plain(ex.get(n))}
                            for n, s, m in VARIABLES]).to_string(index=False))
        return
    print('=== AA ADD-ON 4 (PILLAR 3): ANTICIPATORY ACTION PLAN ENGINE ===')
    status, log, cl, reports, sources, errors = run(a.as_of, a.dry_run)
    print('Data used: ' + '; '.join(f'{k}: {v}' for k, v in sources.items()))
    if len(status):
        print(status[['plan_id', 'county', 'stage', 'readiness_now', 'activation_now', 'river_level_m',
                      'readiness_level_m', 'activation_level_m', 'alert_level', 'missing_or_stale']].to_string(index=False))
    for r in log.to_dict('records'):
        print(f"STAGE CHANGE {r['plan_id']}: {r['from_stage']} -> {r['to_stage']} ({r['reason']})")
    if a.dry_run:
        print('(dry run: nothing written)')
    else:
        for f in ('aap_status_latest.csv', 'aap_checklist_latest.md', 'aap_activation_log.csv', 'aap_state.json'):
            if os.path.exists(os.path.join(AA_OUT, f)):
                print('->', os.path.join(AA_OUT, f))
        for rp in reports:
            print('->', rp)


def selftest():
    for bad in ("__import__('os').system('ls')", "river_level_m.real", "open('x')", "unknown_value > 3"):
        try:
            compile_rule(bad)
            raise AssertionError(f'unsafe or unknown rule accepted: {bad}')
        except ValueError:
            pass
    t = compile_rule("river_level_m >= activation_level_m OR (alert_level == 'red' AND p_heavy >= 0.3)")
    miss = set()
    assert evaluate(t, {'river_level_m': 5.0, 'activation_level_m': 4.0}, miss) is True
    assert evaluate(t, {'alert_level': 'red', 'p_heavy': 0.1}, set()) is None            # river missing, rain branch False
    assert evaluate(t, {'alert_level': 'green', 'river_level_m': 1.0, 'activation_level_m': 4.0}, set()) is False
    assert evaluate(compile_rule("alert_level in ('orange', 'red')"), {'alert_level': 'red'}, set()) is True
    assert season_of(datetime.date(2026, 1, 15), '07-01', '01-31') == 2025
    assert season_of(datetime.date(2026, 3, 1), '07-01', '01-31') is None
    plan = {'plan_id': 'T', 'county': 'X', 'season_start': '07-01', 'season_end': '01-31', 'confirm_runs': 2,
            'max_data_age_days': 20, 'stand_down_runs': 2, 'max_activations_per_season': 1,
            '_ready': compile_rule('river_level_m >= readiness_level_m'),
            '_act': compile_rule('river_level_m >= activation_level_m')}
    base = {'readiness_level_m': 10.0, 'activation_level_m': 11.0, 'river_age_days': 3}
    seq = [('2026-08-01', 9.0, 'a'), ('2026-08-02', 10.2, 'b'), ('2026-08-03', 11.3, 'c'), ('2026-08-04', 11.3, 'c'),
           ('2026-08-05', 11.4, 'd'), ('2026-08-20', 12.0, 'e'), ('2026-09-01', 9.0, 'f'), ('2027-02-10', 9.0, 'g'),
           ('2027-07-05', 11.5, 'h'), ('2027-07-06', 11.6, 'i')]
    st, stages = None, []
    for day, lvl, sig in seq:
        st, tr, ev = step(plan, st, {**base, 'river_level_m': lvl, '_signature': sig}, pd.Timestamp(day).to_pydatetime())
        stages.append(st['stage'])
    assert stages == ['normal', 'readiness', 'readiness', 'readiness', 'activated', 'activated', 'activated',
                      'out of season', 'readiness', 'activated'], stages
    stale = {**base, 'river_level_m': 50.0, 'river_age_days': 40, '_signature': 'z'}
    st2, tr2, ev2 = step(plan, None, stale, pd.Timestamp('2026-08-01').to_pydatetime())
    assert st2['stage'] == 'normal' and 'river_level_m' in ev2['missing'], 'a stale reading must not trigger'
    print('selftest passed: unsafe rules rejected, three-valued logic, seasons, confirmation on distinct '
          'observations, once per season, stale data ignored')


if __name__ == '__main__':
    main()
