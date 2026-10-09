# -*- coding: utf-8 -*-
"""Publish the anticipatory-action add-on results as an Earth Engine table asset.

The GEE Code Editor cannot read files from GitHub, so this is how the add-on outputs reach a Code Editor script
(gee_code_editor_aa_addons_test.js): one public table asset, one feature per county, rebuilt on every run.

  python aa_p6_gee_publish.py             # build the payload and replace the asset
  python aa_p6_gee_publish.py --dry-run   # build the payload, write aa_out/aa_gee_payload.json, touch nothing in EE

Reads (never changes): aa_out/p1_county_risk_profile.csv, aa_triggers.csv, aap_status_latest.csv,
aap_checklist_latest.csv, p5_indicator_report_<latest>.csv and aa_config/aap_plans.csv.
Writes: projects/<PROJECT>/assets/altimetry/aa_county_status  (same folder as county_hydroclimate and county_gauge_link)

Each county feature has a few flat properties (county, state, risk_class, risk_score, trigger_family, plan_stage,
plan_status) and three JSON strings (risk_json, trig_json, plan_json) that the viewer unpacks.
One extra feature, county = '__meta__', carries generated_utc and the indicator table (indicators_json).
"""
import glob
import json
import math
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))
CFG = os.environ.get('AA_CONFIG_DIR', os.path.join(HERE, 'aa_config'))
ASSET_NAME = 'aa_county_status'

RISK_COLS = ['risk_rank', 'state', 'pcode', 'risk_score', 'risk_class', 'hazard_exposure', 'hazard', 'exposure',
             'vulnerability', 'lack_of_coping', 'data_completeness', 'data_flag', 'pop_total', 'pop_flood_prone',
             'displaced_total', 'flooded_settlement_pop', 'facilities_risk_share']
TRIG_COLS = ['station_name', 'station_uid', 'relation', 'link_confidence', 'thr_confidence', 'trigger_family',
             'readiness_rule_name', 'activation_rule_name', 'readiness_value', 'activation_value', 'regional_value',
             'readiness_level_m', 'activation_level_m', 'lvl_2yr_m', 'last_date', 'last_level_m',
             'last_seasonal_pctile', 'last_rise_m', 'days_since_obs', 'current_state', 'note', 'status',
             'validated_by', 'seasons_hit', 'seasons_late', 'seasons_miss', 'seasons_false_alarm']
PLAN_COLS = ['plan_id', 'hazard', 'plan_status', 'stage', 'stage_since', 'activations_this_season', 'readiness_now',
             'activation_now', 'missing_or_stale', 'river_level_m', 'river_obs_date', 'river_age_days', 'alert_level',
             'alert_hazard', 'p_heavy', 'people_target', 'budget_usd', 'lead_agency', 'evaluated_utc']
PLAN_CFG_COLS = ['readiness_rule', 'activation_rule', 'confirm_runs', 'max_data_age_days', 'season_start', 'season_end',
                 'fund_release_rule', 'validated_by']
ACTION_COLS = ['plan_stage', 'action_stage', 'action_no', 'action', 'sector', 'due', 'status']


def clean(v):
    if v is None:
        return None
    if hasattr(v, 'item'):
        v = v.item()
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else round(v, 4)
    return v


def pick(row, cols):
    return {c: clean(row[c]) for c in cols if c in row.index}


def read(name, folder=OUT):
    path = os.path.join(folder, name)
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def build_payload():
    """-> {'counties': {name: {risk, trig, plan}}, 'indicators': [...], 'generated': str, 'indicators_prepared': str}"""
    risk, trig = read('p1_county_risk_profile.csv'), read('aa_triggers.csv')
    status, checks = read('aap_status_latest.csv'), read('aap_checklist_latest.csv')
    plans = read('aap_plans.csv', CFG)
    ind_files = sorted(glob.glob(os.path.join(OUT, 'p5_indicator_report_20*.csv')))
    ind = pd.read_csv(ind_files[-1]) if ind_files else pd.DataFrame()

    counties = {}
    for _, r in risk.iterrows():
        counties.setdefault(r['county'], {})['risk'] = pick(r, RISK_COLS)
    for _, r in trig.iterrows():
        counties.setdefault(r['county'], {})['trig'] = pick(r, TRIG_COLS)
    for _, r in status.iterrows():
        q = pick(r, PLAN_COLS)
        if len(plans) and 'plan_id' in plans:
            cfg = plans[plans.plan_id == r['plan_id']]
            if len(cfg):
                q.update(pick(cfg.iloc[0], PLAN_CFG_COLS))
        q['actions'] = ([pick(a, ACTION_COLS) for _, a in checks[checks.plan_id == r['plan_id']].iterrows()]
                        if len(checks) else [])
        counties.setdefault(r['county'], {})['plan'] = q
    generated = str(status['evaluated_utc'].max()) if len(status) and 'evaluated_utc' in status else ''
    prepared = ''
    if ind_files:
        base = os.path.basename(ind_files[-1])
        md = os.path.join(OUT, base.replace('.csv', '.md'))
        if os.path.exists(md):
            for line in open(md, encoding='utf-8'):
                if line.startswith('Prepared '):
                    prepared = line.split()[1]
                    break
    indicators = ([pick(r, ['pillar', 'indicator', 'year_to_date', 'target']) for _, r in ind.iterrows()]
                  if len(ind) else [])
    return {'counties': counties, 'indicators': indicators, 'generated': generated, 'indicators_prepared': prepared}


def to_features(payload, ee):
    feats = []
    for name, d in payload['counties'].items():
        rk, tg, pl = d.get('risk') or {}, d.get('trig') or {}, d.get('plan') or {}
        props = {'county': name, 'state': rk.get('state') or '', 'generated_utc': payload['generated'],
                 'risk_class': rk.get('risk_class') or '', 'risk_score': rk.get('risk_score'),
                 'trigger_family': tg.get('trigger_family') or '', 'plan_stage': pl.get('stage') or '',
                 'plan_status': pl.get('plan_status') or '',
                 'risk_json': json.dumps(rk, ensure_ascii=False), 'trig_json': json.dumps(tg, ensure_ascii=False),
                 'plan_json': json.dumps(pl, ensure_ascii=False)}
        feats.append(ee.Feature(None, {k: v for k, v in props.items() if v is not None}))
    feats.append(ee.Feature(None, {'county': '__meta__', 'generated_utc': payload['generated'],
                                   'indicators_prepared': payload['indicators_prepared'],
                                   'indicators_json': json.dumps(payload['indicators'], ensure_ascii=False)}))
    return feats


def publish(payload):
    import ee
    from ee_util import ASSET_FOLDER, export_table, init_ee
    init_ee()
    asset_id = f'{ASSET_FOLDER}/{ASSET_NAME}'
    ok = export_table(ee.FeatureCollection(to_features(payload, ee)), asset_id, 'aa county status', public=True)
    print(f'aa_p6_gee_publish: {"exported" if ok else "FAILED"} {asset_id} ({len(payload["counties"])} counties)')
    return ok


def main():
    payload = build_payload()
    if not payload['counties']:
        print('aa_p6_gee_publish: no add-on outputs found in', OUT, '- nothing to publish')
        return 1
    n = lambda k: sum(1 for d in payload['counties'].values() if d.get(k))
    print(f'aa_p6_gee_publish: {len(payload["counties"])} counties (risk {n("risk")}, trigger {n("trig")}, '
          f'plan {n("plan")}); generated {payload["generated"]}')
    if '--dry-run' in sys.argv or '--selftest' in sys.argv:
        path = os.path.join(OUT, 'aa_gee_payload.json')
        json.dump(payload, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        print('dry run: wrote', path, '- Earth Engine not touched')
        return 0
    return 0 if publish(payload) else 1


if __name__ == '__main__':
    sys.exit(main())
