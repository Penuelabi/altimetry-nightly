# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 5 - PILLAR 3: ANTICIPATORY ACTION (simulation exercises)
South Sudan Roadmap on Anticipatory Action 2025-2030, Pillar 3: "joint simulation exercises on the agreed activation
mechanisms to establish the level of community preparedness for different hazards" (indicator: number of simulation
exercises conducted; verification: simulation reports).

What it does
  Replays a past flood season through an anticipatory action plan, using the plan engine's own rules and stage logic
  (it imports aa_p3_aap_engine.py, so keep the two files together), and builds a ready-to-run exercise pack.
    replay   python aa_p3_simulation.py --plan AAP-FL-AYOD --season 2024
             What would the plan have done in the 2024 season, and was it in time for the recorded displacement?
    drill    python aa_p3_simulation.py --plan AAP-FL-AYOD --season 2024 --shift-m 0.6
                    --inject "2024-08-20: alert_level=red; alert_hazard=flood / waterlogging"
             Raises the river by 0.6 m and adds a red bulletin alert from 20 August, so the plan surely activates.
    review   python aa_p3_simulation.py --all --season 2020-2025
             Every plan in every season: hit / late / miss / false alarm, with lead times (no packs written).
  River readings come from merged_altimetry_stations.csv as they were on each day (last pass on or before that day);
  bulletin values (alert level, rain outlook, soil) are not archived, so they are empty unless injected.
  The pack: timeline.csv, exercise_pack.md (scenario, timeline, injects with expected responses, actions with due
  dates, discussion questions), evaluation.csv (blank sheet for facilitators: timeliness, communication, gaps;
  the indicator tracker counts an exercise as conducted once 'conducted_date' is filled), hydrograph.png.

Inputs   aa_config/aap_plans.csv, aap_actions.csv, simulation_injects.csv (template written on first run);
         merged_altimetry_stations.csv (ALTIMETRY_OUT_DIR); data/flood_displacement_county_month.csv
Outputs  aa_out/simulations/SIM-<plan>-<season>-<stamp>/..., aa_out/simulations/p3_retrospective_<seasons>.csv
Run:     python aa_p3_simulation.py --plan PLAN_ID --season YEAR [--shift-m M] [--inject "DATE: name=value; ..."]
         python aa_p3_simulation.py --all --season 2020-2025          python aa_p3_simulation.py --selftest
"""
import argparse
import datetime
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aa_p3_aap_engine as eng      # noqa: E402  (same folder: the engine's rules are what is being exercised)

# =========================================================================== #
# SETTINGS                                                                    #
# =========================================================================== #
DATA_DIR, ALT_DIR, AA_CONFIG, AA_OUT = eng.DATA_DIR, eng.ALT_DIR, eng.AA_CONFIG, eng.AA_OUT
LEVEL_COL = 'Water Surface Elevation - values(m)'
STEP_DAYS = 2                    # the plan is evaluated every 2 days through the season
ON_TIME_DAYS = 15                # activation up to 15 days after the first displacement month began = on time
DISPLACEMENT_COLS = ['flood', 'natural disaster (unspecified)']
SURFACE, INK, INK2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
LINE, READY_BG, ACT_BG, IMPACT_C = '#2a78d6', '#fab219', '#ec835a', '#d03b3b'

INJECT_TEMPLATE = [
    ('readiness', 0, 'Readiness notice from the platform: river at the readiness level', 'State TWG-AA chair',
     'Confirm the reading with SSMS / MWRI within 24 hours; inform the county commissioner'),
    ('readiness', 1, 'The radio listening hub in the main payam reports the station is off-air',
     'Communication focal point', 'Switch to chiefs, church networks or SMS; log which channel reached whom'),
    ('activation', 0, 'Activation notice: the activation level is reached', 'Fund holder and TWG-AA',
     'Decide and release funds within the time set in the release rule; record the time'),
    ('activation', 1, 'The main road to the distribution site is cut by water', 'Logistics lead',
     'Use the alternative route, boats or pre-positioned stock; update the timeline'),
    ('activation', 2, 'A rumour that the warning is false spreads in the community', 'Community engagement lead',
     'Answer through trusted leaders and the radio hub within a day'),
    ('activation', 3, 'The beneficiary list misses female-headed households and people with disabilities',
     'Protection / gender focal point', 'Verify and add them before transfers; note the fix for the plan'),
]
EVAL_ROWS = [
    ('meta', 'conducted_date', '', 'YYYY-MM-DD; the exercise counts as conducted once this is filled'),
    ('meta', 'location', '', ''), ('meta', 'facilitator', '', ''),
    ('meta', 'participants_total', '', ''), ('meta', 'participants_women', '', ''), ('meta', 'participants_youth', '', ''),
    ('meta', 'organisations', '', 'list'), ('meta', 'communities_represented', '', ''),
    ('timeliness', 'hours from trigger notice to TWG-AA decision', '<= 24', ''),
    ('timeliness', 'hours from activation to fund release', 'per release rule', ''),
    ('timeliness', 'days from activation to first assistance delivered', '<= action deadline', ''),
    ('timeliness', 'readiness actions done by their deadline (%)', '100', ''),
    ('timeliness', 'activation actions done by their deadline (%)', '100', ''),
    ('communication', 'radio hubs / community groups confirming receipt (%)', '100', ''),
    ('communication', 'languages used', 'all needed locally', ''),
    ('communication', 'community members who understood the message (%)', '>= 80', 'from a short check after the drill'),
    ('gaps', 'problems found', '', ''), ('gaps', 'changes to the plan agreed', '', ''),
    ('gaps', 'follow-up actions (owner, date)', '', ''),
]


# =========================================================================== #
# DATA                                                                        #
# =========================================================================== #
def load_levels():
    path = os.path.join(ALT_DIR, 'merged_altimetry_stations.csv')
    if not os.path.exists(path):
        sys.exit(f"{path} not found: run drive_sync.py pull (or set ALTIMETRY_OUT_DIR)")
    want = {'date', LEVEL_COL, 'station_uid', 'source', 'station_id', 'qc_status'}
    d = pd.read_csv(path, low_memory=False, usecols=lambda c: c in want)
    if 'station_uid' not in d.columns:
        sid = pd.to_numeric(d['station_id'], errors='coerce')
        d['station_uid'] = (d['source'].astype(str).str.lower() + ':' +
                            sid.round().astype('Int64').astype(str)).where(sid.notna())
    d['date'] = pd.to_datetime(d['date'], errors='coerce')
    d['level'] = pd.to_numeric(d[LEVEL_COL], errors='coerce')
    d = d.dropna(subset=['date', 'level', 'station_uid'])
    if 'qc_status' in d.columns:
        ok = eng.text(d['qc_status']).str.lower().eq('ok')
        if ok.mean() > 0.5:
            d = d[ok]
    return d[['station_uid', 'date', 'level']].sort_values(['station_uid', 'date'])


def displacement_months(county):
    disp = eng.read_csv(os.path.join(DATA_DIR, 'flood_displacement_county_month.csv'))
    if disp is None:
        return []
    d = disp[disp['county'].map(eng.ckey) == eng.ckey(county)].copy()
    cols = [c for c in DISPLACEMENT_COLS if c in d.columns]
    d['n'] = d[cols].apply(pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
    d = d[d['n'] > 0]
    return sorted(pd.Period(year=int(y), month=int(m), freq='M') for y, m in zip(d['year'], d['month']))


def parse_injects(items):
    """['2024-08-20: alert_level=red; p_heavy=0.4'] -> [(Timestamp, {name: value})]"""
    out = []
    for it in items or []:
        m = re.fullmatch(r'\s*(\d{4}-\d{2}-\d{2})\s*:\s*(.+)', it)
        if not m:
            sys.exit(f'cannot read --inject "{it}"; use "YYYY-MM-DD: name=value; name=value"')
        vals = {}
        for pair in m.group(2).split(';'):
            if '=' not in pair:
                continue
            k, v = (x.strip() for x in pair.split('=', 1))
            if k not in eng.KNOWN:
                sys.exit(f'unknown name "{k}" in --inject (see aa_p3_aap_engine.py --list-variables)')
            x = pd.to_numeric(v, errors='coerce')
            vals[k] = float(x) if not eng.isnull(x) else (v.lower() if k == 'alert_level' else v)
        if 'alert_level' in vals:
            vals['alert_rank'] = eng.ALERT_RANK.get(vals['alert_level'])
        out.append((pd.Timestamp(m.group(1)), vals))
    return sorted(out, key=lambda t: t[0])


def river_at(g, day, shift):
    past = g[g['date'] <= day]
    if past.empty:
        return {}
    last = past.iloc[-1]
    rate = None
    if len(past) > 1:
        prev = past.iloc[-2]
        dd = (last['date'] - prev['date']).days
        rate = (last['level'] - prev['level']) / dd if dd > 0 else None
    return {'river_level_m': float(last['level']) + shift, 'river_obs_date': last['date'].date().isoformat(),
            'river_age_days': int((day - last['date']).days), 'river_rate_m_per_day': rate,
            'river_rising': None if rate is None else rate > 0, '_signature': last['date'].date().isoformat()}


def season_window(plan, season):
    (sm, sd), (em, ed) = eng.mmdd(plan['season_start'], '07-01'), eng.mmdd(plan['season_end'], '01-31')
    start = pd.Timestamp(year=season, month=sm, day=sd)
    end = pd.Timestamp(year=season + (1 if (em, ed) < (sm, sd) else 0), month=em, day=ed)
    return start, end


# =========================================================================== #
# SIMULATION                                                                  #
# =========================================================================== #
def simulate(plan, season, levels, values_now, shift=0.0, injects=None):
    """Day-by-day replay of one season. Returns (timeline, transitions, summary)."""
    env0 = values_now.get(plan['key'], {})
    uid = env0.get('station_uid')
    keep = {k: env0.get(k) for k in ('readiness_level_m', 'activation_level_m', 'lvl_2yr_m', 'lvl_5yr_m', 'lvl_10yr_m',
                                     'county', 'state', 'station_uid', 'station_name')}
    g = levels[levels['station_uid'] == uid] if uid else levels.iloc[0:0]
    start, end = season_window(plan, season)
    st, rows, trans = None, [], []
    injects = injects or []
    for day in pd.date_range(start, end, freq=f'{STEP_DAYS}D'):
        env = dict(keep, month=int(day.month))
        for d0, vals in injects:
            if day >= d0:
                env.update(vals)
        env.update(river_at(g, day, shift))
        env['_signature'] = f"{env.get('_signature')}|{sum(day >= d0 for d0, _ in injects)}"
        st, tr, ev = eng.step(plan, st, env, day.to_pydatetime())
        for t in tr:
            trans.append({'date': day.date().isoformat(), **t})
        rows.append({'date': day.date().isoformat(), 'river_level_m': env.get('river_level_m'),
                     'river_obs_date': env.get('river_obs_date'), 'river_age_days': env.get('river_age_days'),
                     'readiness_level_m': env.get('readiness_level_m'), 'activation_level_m': env.get('activation_level_m'),
                     'alert_level': env.get('alert_level'), 'readiness_rule': ev['readiness'],
                     'activation_rule': ev['activation'], 'stage': st['stage'], 'missing': ', '.join(ev['missing'])})
    tl = pd.DataFrame(rows)
    months = [m for m in displacement_months(plan['county']) if (m.year if m.month >= 7 else m.year - 1) == season]
    first = months[0].start_time if months else None
    t_ready = next((pd.Timestamp(t['date']) for t in trans if t['to_stage'] == 'readiness'), None)
    t_act = next((pd.Timestamp(t['date']) for t in trans if t['to_stage'] == 'activated'), None)
    if first is not None:
        if t_act is not None and t_act <= first + pd.Timedelta(days=ON_TIME_DAYS):
            outcome = 'hit (on time)'
        elif t_act is not None:
            outcome = 'late'
        else:
            outcome = 'miss'
    else:
        outcome = 'false alarm' if t_act is not None else 'correct negative'
    summary = {'plan_id': plan['plan_id'], 'county': plan['county'], 'season': season,
               'station_uid': uid, 'shift_m': shift, 'injects': len(injects),
               'readiness_date': '' if t_ready is None else t_ready.date().isoformat(),
               'activation_date': '' if t_act is None else t_act.date().isoformat(),
               'displacement_months': ', '.join(str(m) for m in months),
               'lead_days_activation': (first - t_act).days if first is not None and t_act is not None else np.nan,
               'lead_days_readiness': (first - t_ready).days if first is not None and t_ready is not None else np.nan,
               'outcome': outcome, 'river_data_points': int(tl['river_level_m'].notna().sum()) if len(tl) else 0}
    return tl, pd.DataFrame(trans), summary


# =========================================================================== #
# PACK                                                                        #
# =========================================================================== #
def injects_table():
    path = os.path.join(AA_CONFIG, 'simulation_injects.csv')
    if not os.path.exists(path):
        os.makedirs(AA_CONFIG, exist_ok=True)
        pd.DataFrame(INJECT_TEMPLATE, columns=['relative_to', 'day_offset', 'inject', 'to', 'expected_response']).to_csv(
            path, index=False)
        print(f"Template written: {path} (edit the exercise injects freely)")
    return eng.read_csv(path)


def _plt():
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        return plt
    except Exception as e:
        print(f"Chart skipped: matplotlib not available ({e}).")
        return None


def plot(tl, levels, plan, summary, start, end, out_png, shift):
    plt = _plt()
    if plt is None or tl.empty:
        return None
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    uid = summary['station_uid']
    g = levels[(levels['station_uid'] == uid) & (levels['date'] >= start - pd.Timedelta(days=45)) &
               (levels['date'] <= end + pd.Timedelta(days=15))]
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=140)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    t = tl.assign(date=pd.to_datetime(tl['date']))
    for stage, col, alpha in (('readiness', READY_BG, 0.22), ('activated', ACT_BG, 0.28)):
        on = t['stage'].eq(stage).to_numpy()
        i = 0
        while i < len(on):
            if on[i]:
                j = i
                while j + 1 < len(on) and on[j + 1]:
                    j += 1
                ax.axvspan(t['date'].iloc[i], t['date'].iloc[j] + pd.Timedelta(days=STEP_DAYS), color=col,
                           alpha=alpha, lw=0)
                i = j + 1
            else:
                i += 1
    for m in str(summary['displacement_months']).split(', '):
        if m:
            p = pd.Period(m, 'M')
            ax.axvspan(p.start_time, p.end_time, ymin=0, ymax=0.06, color=IMPACT_C, alpha=0.9, lw=0)
    ax.plot(g['date'], g['level'] + shift, color=LINE, lw=1.8, marker='o', ms=3)
    rl, al = tl['readiness_level_m'].dropna(), tl['activation_level_m'].dropna()
    if len(rl):
        ax.axhline(rl.iloc[0], color=INK2, ls='--', lw=1.1)
        ax.text(1.003, rl.iloc[0], 'readiness', transform=ax.get_yaxis_transform(), fontsize=7, color=INK2, va='center')
    if len(al):
        ax.axhline(al.iloc[0], color=INK, ls='-.', lw=1.1)
        ax.text(1.003, al.iloc[0], 'activation', transform=ax.get_yaxis_transform(), fontsize=7, color=INK, va='center')
    ax.grid(axis='y', color=GRID, lw=0.6)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.set_ylabel('water level (m)', color=INK2, fontsize=8)
    lab = f"{plan['plan_id']} - {plan['county']}, season {summary['season']}"
    if shift:
        lab += f" (drill: river raised {shift:+.2f} m)"
    ax.set_title(lab + f" - outcome: {summary['outcome']}", loc='left', fontsize=10, color=INK)
    handles = [Line2D([], [], color=LINE, lw=1.8, marker='o', ms=3, label='water level at the gauge'),
               Patch(color=READY_BG, alpha=0.4, label='plan in readiness'),
               Patch(color=ACT_BG, alpha=0.5, label='plan activated'),
               Patch(color=IMPACT_C, label='month with flood displacement')]
    ax.legend(handles=handles, loc='upper left', frameon=False, fontsize=7.5, ncol=2)
    fig.savefig(out_png, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)
    return out_png


def write_pack(folder, plan, tl, trans, summary, actions, injects, shift, inject_args, png):
    t_ready = pd.Timestamp(summary['readiness_date']) if summary['readiness_date'] else None
    t_act = pd.Timestamp(summary['activation_date']) if summary['activation_date'] else None
    draft = not str(plan.get('status', '')).lower().startswith('validated')
    lines = [f"# Simulation exercise - {plan['plan_id']} ({plan['county']}), season {summary['season']}", '',
             f"Prepared {eng.now_utc():%Y-%m-%d %H:%M} UTC by aa_p3_simulation.py (Roadmap on Anticipatory Action, "
             'Pillar 3: joint simulation exercises).', '']
    if draft:
        lines += ['> The plan is a **draft** (not validated). The exercise tests the draft before the TWG-AA adopts it.', '']
    scen = (f"a replay of the {summary['season']} season with the river as the satellites saw it" if not shift and not
            inject_args else f"a drill built on the {summary['season']} season" +
            (f", river raised by {shift:+.2f} m" if shift else '') +
            (f", with injected values: {'; '.join(inject_args)}" if inject_args else ''))
    lines += ['## Scenario', f"This exercise uses {scen}. Gauge: {summary['station_uid']}.",
              f"- Readiness reached: {summary['readiness_date'] or 'never'}",
              f"- Activation reached: {summary['activation_date'] or 'never'}",
              f"- Flood displacement recorded: {summary['displacement_months'] or 'none in this season'}",
              f"- Outcome: **{summary['outcome']}**" +
              (f" (activation {summary['lead_days_activation']:.0f} days before the first displacement month)"
               if pd.notna(summary['lead_days_activation']) else ''), '']
    if png:
        lines += [f"![hydrograph]({os.path.basename(png)})", '']
    lines += ['## Stage changes', '| Date | From | To | Why |', '|---|---|---|---|']
    for t in trans.to_dict('records') if len(trans) else []:
        lines.append(f"| {t['date']} | {t['from_stage']} | {t['to_stage']} | {t['reason']} |")
    if not len(trans):
        lines.append('| - | - | - | the plan never left normal: discuss whether the trigger is too high |')
    lines += ['', '## Injects (hand these out at the times shown)', '| When | Inject | To | Expected response |',
              '|---|---|---|---|']
    for r in injects.to_dict('records') if injects is not None else []:
        base = t_ready if str(r['relative_to']).lower() == 'readiness' else t_act
        when = (base + pd.Timedelta(days=float(r['day_offset']))).date().isoformat() if base is not None else \
            f"{r['relative_to']} +{r['day_offset']} d (not reached: play it as a what-if)"
        lines.append(f"| {when} | {r['inject']} | {r['to']} | {r['expected_response']} |")
    lines += ['', '## Pre-agreed actions and their due dates', '| Stage | # | Action | Lead | Due |', '|---|---|---|---|---|']
    a = actions[actions['plan_id'] == plan['plan_id']] if len(actions) else actions
    for r in a.to_dict('records'):
        base = t_ready if str(r['stage']).lower() == 'readiness' else t_act
        dd = pd.to_numeric(r.get('deadline_days'), errors='coerce')
        due = (base + pd.Timedelta(days=float(dd))).date().isoformat() if base is not None and not eng.isnull(dd) else '-'
        lines.append(f"| {r['stage']} | {r.get('action_no')} | {r.get('action')} | "
                     f"{'' if eng.isnull(r.get('lead')) else r.get('lead')} | {due} |")
    lines += ['', '## Discussion questions',
              '- Was the readiness notice early enough to prepare? What did each organisation do with it?',
              '- Who decided to activate, how long did it take, and was the fund release rule followed?',
              '- Which communities did the warning not reach, and in which language would it have worked?',
              '- Were women, youth, people with disabilities and the elderly reached by the targeting and the warning?',
              '- What should change in the plan: levels, actions, deadlines, leads, budget?', '',
              '## Evaluation', 'Fill evaluation.csv during and after the exercise. The roadmap indicator '
              '"simulation exercises conducted" counts this exercise once conducted_date is filled.']
    path = os.path.join(folder, 'exercise_pack.md')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    pd.DataFrame(EVAL_ROWS, columns=['section', 'item', 'target', 'notes']).assign(observed='')[
        ['section', 'item', 'target', 'observed', 'notes']].to_csv(os.path.join(folder, 'evaluation.csv'), index=False)
    tl.to_csv(os.path.join(folder, 'timeline.csv'), index=False)
    return path


def seasons_arg(s):
    m = re.fullmatch(r'(\d{4})(?:-(\d{4}))?', s.strip())
    if not m:
        sys.exit('--season must be a year (2024) or a range (2020-2025)')
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    return list(range(a, b + 1))


def main():
    ap = argparse.ArgumentParser(description='Pillar 3 simulation exercises')
    ap.add_argument('--plan', help='plan_id from aa_config/aap_plans.csv')
    ap.add_argument('--all', action='store_true', help='every plan (review table only, no packs)')
    ap.add_argument('--season', default=str(datetime.date.today().year - 1), help='year the season starts, or a range')
    ap.add_argument('--shift-m', type=float, default=0.0, help='drill: add this many metres to the river levels')
    ap.add_argument('--inject', action='append', help='"YYYY-MM-DD: name=value; name=value" (repeatable)')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.plan and not a.all:
        ap.error('give --plan PLAN_ID or --all')
    print('=== AA ADD-ON 5 (PILLAR 3): SIMULATION EXERCISES ===')
    plans, errors = eng.load_plans()
    for e in errors:
        print(f"WARNING: plan skipped - {e}")
    if not plans:
        sys.exit('No plans: run aa_p3_aap_engine.py first (it writes example plans) or fill aa_config/aap_plans.csv')
    if a.plan:
        plans = [p for p in plans if p['plan_id'] == a.plan]
        if not plans:
            sys.exit(f'plan {a.plan} not found in aa_config/aap_plans.csv')
    levels = load_levels()
    values_now, _ = eng.build_values(eng.now_utc().replace(tzinfo=None))
    injects = parse_injects(a.inject)
    seasons = seasons_arg(a.season)
    out_dir = os.path.join(AA_OUT, 'simulations')
    os.makedirs(out_dir, exist_ok=True)

    if a.all or len(seasons) > 1:
        rows = []
        for p in plans:
            for s in seasons:
                _, _, summ = simulate(p, s, levels, values_now, a.shift_m, injects)
                rows.append(summ)
        rev = pd.DataFrame(rows)
        path = os.path.join(out_dir, f'p3_retrospective_{seasons[0]}_{seasons[-1]}.csv')
        rev.to_csv(path, index=False)
        print(rev[['plan_id', 'county', 'season', 'readiness_date', 'activation_date', 'displacement_months',
                   'lead_days_activation', 'outcome']].to_string(index=False))
        print('Outcomes: ' + ', '.join(f'{k} {v}' for k, v in rev['outcome'].value_counts().items()))
        print('->', path)
        eng.log_indicators([dict(pillar='3', activity='Joint simulation exercises on the agreed activation mechanisms',
                                 indicator='Retrospective plan tests (plan-seasons replayed)', value=len(rev),
                                 kind='event', unit='plan-seasons', verification=os.path.basename(path))],
                           'aa_p3_simulation.py')
        return

    p, s = plans[0], seasons[0]
    tl, trans, summ = simulate(p, s, levels, values_now, a.shift_m, injects)
    stamp = eng.now_utc().strftime('%Y%m%d_%H%M')
    folder = os.path.join(out_dir, f"SIM-{p['plan_id']}-{s}-{stamp}")
    os.makedirs(folder, exist_ok=True)
    start, end = season_window(p, s)
    png = plot(tl, levels, p, summ, start, end, os.path.join(folder, 'hydrograph.png'), a.shift_m)
    pack = write_pack(folder, p, tl, trans, summ, eng.load_actions(), injects_table(), a.shift_m, a.inject or [], png)
    eng.log_indicators([dict(pillar='3', activity='Joint simulation exercises on the agreed activation mechanisms',
                             indicator='Simulation exercise packs prepared', value=1, kind='event', unit='packs',
                             verification=os.path.relpath(pack, AA_OUT), note=f"{p['plan_id']} {s}: {summ['outcome']}")],
                       'aa_p3_simulation.py')
    print(f"{p['plan_id']} season {s}: readiness {summ['readiness_date'] or 'never'}, activation "
          f"{summ['activation_date'] or 'never'}, displacement {summ['displacement_months'] or 'none'} -> {summ['outcome']}")
    print('->', folder)


def selftest():
    plan = {'plan_id': 'T', 'county': 'Nowhere', 'key': 'nowhere', 'season_start': '07-01', 'season_end': '01-31',
            'confirm_runs': 1, 'max_data_age_days': 20, 'stand_down_runs': 3, 'max_activations_per_season': 1,
            'status': 'draft', '_ready': eng.compile_rule('river_level_m >= readiness_level_m'),
            '_act': eng.compile_rule("river_level_m >= activation_level_m or alert_level == 'red'")}
    days = pd.date_range('2024-05-01', '2025-02-28', freq='10D')
    lv = 10 + 1.5 * np.exp(-((days.dayofyear - 255) / 40.0) ** 2)
    levels = pd.DataFrame({'station_uid': 'x:1', 'date': days, 'level': lv})
    values = {'nowhere': {'station_uid': 'x:1', 'readiness_level_m': 10.8, 'activation_level_m': 11.3}}
    tl, trans, summ = simulate(plan, 2024, levels, values)
    assert summ['readiness_date'] and summ['activation_date'] and summ['readiness_date'] < summ['activation_date']
    _, _, low = simulate(plan, 2024, levels, values, shift=-2.0)
    assert not low['activation_date'], 'lowered river must not activate'
    _, _, inj = simulate(plan, 2024, levels, values, shift=-2.0, injects=parse_injects(['2024-09-01: alert_level=red']))
    assert inj['activation_date'] >= '2024-09-01', 'an injected red alert must activate from its date'
    print('selftest passed: replay reaches readiness before activation, lowered river stays quiet, injects work')


if __name__ == '__main__':
    main()
