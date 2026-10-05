# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 6 - PILLAR 5: COORDINATION AND LEGAL FRAMEWORK (briefs and dissemination)
South Sudan Roadmap on Anticipatory Action 2025-2030, Outcome 5: institutional coordination at national, state and
local level for inclusive early warning, anticipatory action and climate services. Activities: coordination platforms
at subnational level linked to the national TWG-AA, regular updates on operations, community groups / radio listening
hubs that disseminate early warnings, and SOPs. Also serves Pillar 2 activity f (translating warnings into local
languages through trained intermediaries).

What it does, at every bulletin run
  - a national TWG-AA situation brief and one brief per state that has something to act on: counties by alert level,
    river gauges at their readiness / activation levels, anticipatory action plans in readiness or activated with
    the actions due this week, data freshness, and the decisions the group needs to take
  - SMS-length messages (<= 160 characters) and radio scripts for each county with an alert, in every language whose
    template has been translated AND validated (aa_config/message_templates.csv); English otherwise, and the missing
    translations are listed so intermediaries know what to translate
  - a distribution plan per coordination group (aa_config/recipient_groups.csv: groups and channels, no personal
    contacts), appended to aa_out/dissemination_log.csv as 'prepared'; mark rows 'sent' when you send them
  - templates for the feedback log (what communities heard, understood and did) and the TWG-AA meetings log
  Nothing is sent automatically, and community messages about a plan are only drafted for VALIDATED plans, so no one
  is promised help that a draft plan cannot deliver. Everything is labelled for SSMS / MHADM validation before release.

Inputs   county_bulletin_latest.csv (BULLETIN_OUT_DIR); aa_out/aap_status_latest.csv, aap_checklist_latest.csv,
         aa_triggers.csv; aa_config/message_templates.csv, recipient_groups.csv (templates written on the first run)
Outputs  aa_out/dissemination/<stamp>/ and .../latest/: brief_national.md, brief_<state>.md, messages.csv,
         radio_scripts.md, distribution_plan.csv; aa_out/dissemination_log.csv; aa_config/feedback_log.csv and
         meetings_log.csv (templates); indicator rows in aa_indicator_ledger.csv
Run:     python aa_p5_dissemination.py        python aa_p5_dissemination.py --selftest
"""
import argparse
import datetime
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd

# =========================================================================== #
# SETTINGS                                                                    #
# =========================================================================== #
HERE = os.path.dirname(os.path.abspath(__file__))
BUL_DIR = os.environ.get('BULLETIN_OUT_DIR', os.path.join(HERE, 'bulletin'))
AA_CONFIG = os.environ.get('AA_CONFIG_DIR', os.path.join(HERE, 'aa_config'))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))
SOURCE = os.environ.get('AA_SOURCE_NAME', 'SS Climate Monitor (advisory)')
SOURCE_SHORT = os.environ.get('AA_SOURCE_SHORT', 'SSCM advisory')      # used when an SMS would pass 160 characters
MIN_ALERT = 'yellow'               # counties at or above this level get messages
SMS_MAX = 160
KEEP_RUNS = 30                     # dated dissemination folders kept
ACTIONS_DUE_DAYS = 7               # actions due within this many days appear in the briefs
LANGUAGES = [('en', 'English'), ('pga', 'Juba Arabic'), ('din', 'Dinka (Thuongjang)'), ('nus', 'Nuer (Thok Naath)'),
             ('shk', 'Shilluk (Dhok Cøllø)'), ('bfa', 'Bari')]
ALERT_RANK = {'green': 0, 'yellow': 1, 'orange': 2, 'red': 3}
ALIASES = {'abyeiadministrativearea': 'abyeiregion'}
DISCLAIMER = ('Decision support from the hydro-climate platform (satellite rain, soil, river levels and the ECMWF '
              'ensemble). Official warnings are issued by SSMS; plans are activated by the TWG-AA.')

EN_TEMPLATES = {
    ('flood_red', 'sms'): '{LEVEL} FLOOD ALERT {county}: flooding likely this week. Move people, animals and food to '
                          'high ground now. Follow radio and chiefs. {source}',
    ('flood_orange', 'sms'): '{LEVEL} flood alert {county}: flooding possible this week. Keep food, seed and papers '
                             'high and dry; plan where animals go. {source}',
    ('flood_yellow', 'sms'): 'Flood watch {county}: wet days ahead. Clear drains, watch the river, follow radio '
                             'updates. {source}',
    ('drought_red', 'sms'): '{LEVEL} DRY-SPELL ALERT {county}: little rain for 1-2 weeks. Save water, plan grazing '
                            'moves, do not plant now. {source}',
    ('drought_orange', 'sms'): '{LEVEL} dry-spell alert {county}: dry days ahead. Save water and protect crops and '
                               'pasture. {source}',
    ('drought_yellow', 'sms'): 'Dry-spell watch {county}: rain may stop for some days. Delay planting, save water. '
                               '{source}',
    ('river_high', 'sms'): 'River warning {county}: the river is high and may rise. Keep boats ready, move animals '
                           'near high ground. {source}',
    ('aap_readiness', 'sms'): 'Early action alert {county}: flood plan in READINESS. Get ready to move to high ground '
                              'if leaders advise. {source}',
    ('aap_activated', 'sms'): 'EARLY ACTION {county}: flood plan ACTIVATED. Support starts before the flood. Follow '
                              'chiefs and radio. {source}',
    ('flood', 'radio'): 'Good day, listeners in {county}. This is a {level} flood message for {county}, {state}. '
                        '{why} Over the coming days, please: move children, the elderly and people with disabilities '
                        'to high ground first; keep food, seed and important papers high and dry; move animals early '
                        'and keep boats ready; and use safe water to avoid cholera. Listen again tomorrow at the same '
                        'time and follow your chief and local authorities. Message prepared by {source}.',
    ('drought', 'radio'): 'Good day, listeners in {county}. This is a {level} dry-spell message for {county}, {state}. '
                          '{why} Over the coming days, please: save water and protect water points; plan grazing '
                          'moves early and peacefully; delay new planting until rain returns; and check on the elderly '
                          'and the sick in the heat. Listen again tomorrow. Message prepared by {source}.',
    ('river', 'radio'): 'Good day, listeners in {county}. The river gauge serving {county} shows a high water level. '
                        'Water can rise further in the coming weeks. Please keep boats ready, move animals and stored '
                        'food near high ground, and follow your chief and local authorities. Message prepared by '
                        '{source}.',
}


# =========================================================================== #
# SMALL HELPERS (repeated in each add-on so every file runs on its own)       #
# =========================================================================== #
def ckey(name):
    k = re.sub(r'[^a-z0-9]+', '', str(name).lower())
    return ALIASES.get(k, k)


def slug(s):
    return re.sub(r'[^a-z0-9]+', '_', str(s).lower()).strip('_')


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def text(series):
    return series.astype(object).where(series.notna(), '').astype(str).str.strip().replace({'nan': '', 'None': ''})


def blank(v):
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() in ('', 'nan', 'None')


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


def write_template(path, df, note):
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Template written: {path} ({note})")
    return True


# =========================================================================== #
# TEMPLATES                                                                   #
# =========================================================================== #
def ensure_templates(states):
    rows = []
    for (situation, channel), txt in EN_TEMPLATES.items():
        for code, name in LANGUAGES:
            rows.append({'situation': situation, 'channel': channel, 'language': code, 'language_name': name,
                         'text': txt if code == 'en' else '', 'validated_by': 'platform (English master)' if code == 'en' else '',
                         'validated_date': '', 'notes': '' if code == 'en' else
                         'translate from the English text with native-speaker intermediaries; fill validated_by when checked'})
    write_template(os.path.join(AA_CONFIG, 'message_templates.csv'), pd.DataFrame(rows),
                   'translate the empty rows; a language is used once text and validated_by are filled; '
                   'placeholders in {braces} must stay as they are')
    g = [{'group_id': 'NTWG-AA', 'group_name': 'National Technical Working Group on Anticipatory Action',
          'level': 'national', 'state': '', 'county': '', 'channel': 'email', 'languages': 'en', 'min_alert': 'yellow',
          'active': 'yes', 'members': '', 'notes': 'chaired by MHADM'}]
    for s in sorted(states):
        g.append({'group_id': f'TWG-{slug(s)[:20].upper()}', 'group_name': f'{s} state TWG-AA', 'level': 'state',
                  'state': s, 'county': '', 'channel': 'email', 'languages': 'en', 'min_alert': 'yellow',
                  'active': 'no', 'members': '', 'notes': 'set active=yes once the state group is established'})
    g.append({'group_id': 'HUB-EXAMPLE', 'group_name': 'Example radio listening hub (replace)', 'level': 'community',
              'state': '', 'county': '', 'channel': 'radio_hub', 'languages': 'en', 'min_alert': 'yellow',
              'active': 'no', 'members': '', 'notes': 'one row per hub: fill state, county, languages (e.g. en;din)'})
    write_template(os.path.join(AA_CONFIG, 'recipient_groups.csv'), pd.DataFrame(g),
                   'coordination groups and channels; keep personal contacts out of this file')
    write_template(os.path.join(AA_CONFIG, 'feedback_log.csv'), pd.DataFrame(columns=[
        'date', 'state', 'county', 'payam', 'group_id', 'channel', 'language', 'message_situation', 'heard_warning',
        'understood', 'action_taken', 'comments', 'recorded_by']), 'what communities heard, understood and did')
    write_template(os.path.join(AA_CONFIG, 'meetings_log.csv'), pd.DataFrame(columns=[
        'date', 'level', 'state', 'county', 'group_id', 'attendees_total', 'attendees_women', 'agenda', 'decisions',
        'minutes_reference']), 'one row per TWG-AA meeting (national, state or county)')


def load_templates():
    t = read_csv(os.path.join(AA_CONFIG, 'message_templates.csv'))
    if t is None:
        return {}, set()
    t = t.copy()
    t['ok'] = text(t['text']).ne('') & text(t['validated_by']).ne('')
    usable = {(r.situation, r.channel, r.language): r.text for r in t[t['ok']].itertuples()}
    langs = set(t[t['ok']]['language'])
    return usable, langs


# =========================================================================== #
# CONTENT                                                                     #
# =========================================================================== #
def county_items(bul, plans, trig):
    """One record per county with the situations that apply, in order of urgency."""
    items = []
    pl = plans.groupby(plans['county'].map(ckey)) if plans is not None and len(plans) else None
    tr = {ckey(r['county']): r for r in trig.to_dict('records')} if trig is not None else {}
    for r in bul.to_dict('records'):
        k = ckey(r['county'])
        lvl = str(r.get('alert_level') or '').lower()
        rank = ALERT_RANK.get(lvl, 0)
        hz = str(r.get('alert_hazard') or '')
        sits, notes = [], []
        if pl is not None and k in pl.groups:
            g = pl.get_group(k)
            for p in g.to_dict('records'):
                validated = str(p.get('plan_status', '')).lower().startswith('validated')
                if p.get('stage') in ('activated', 'readiness'):
                    if validated:
                        sits.append('aap_' + p['stage'])
                    else:
                        notes.append(f"{p['plan_id']} {p['stage']} (draft plan: no community message)")
        if rank >= ALERT_RANK[MIN_ALERT]:
            sits.append(('flood_' if 'flood' in hz else 'drought_') + lvl)
        t = tr.get(k)
        if t and t.get('current_state') in ('readiness', 'activation') and not any(s.startswith('aap_') for s in sits):
            sits.append('river_high')
        if sits or notes:
            items.append({'key': k, 'county': r['county'], 'state': r.get('state'), 'level': lvl, 'rank': rank,
                          'hazard': hz, 'situations': sits, 'plan_notes': notes, 'row': r, 'trigger': t})
    return sorted(items, key=lambda i: (-max([3 if s.startswith('aap_act') else 2 if s.startswith('aap_') else 0
                                             for s in i['situations']] + [i['rank']]), i['state'] or '', i['county']))


def why_sentence(r):
    bits = []
    p = r.get('p_heavy_50mm_week1')
    if p is not None and not blank(p) and float(p) >= 0.2:
        bits.append(f"There is a {float(p):.0%} chance of more than 50 millimetres of rain in the next week")
    w = r.get('week1_rain_median_mm')
    if w is not None and not blank(w):
        bits.append(f"about {float(w):.0f} millimetres of rain are expected this week")
    z = r.get('sm_rootzone_z')
    if z is not None and not blank(z) and float(z) >= 0.75:
        bits.append('the ground is already wet')
    d = r.get('p_dry_spell_7d_in_15d')
    if d is not None and not blank(d) and float(d) >= 0.5:
        bits.append(f"there is a {float(d):.0%} chance of a week without rain")
    if not bits:
        return ''
    joined = bits[0] if len(bits) == 1 else (' and '.join(bits) if len(bits) == 2 else
                                             ', '.join(bits[:-1]) + ', and ' + bits[-1])
    return joined[0].upper() + joined[1:] + '.'


def fill(tmpl, it, source=None):
    r = it['row']
    return tmpl.format(county=it['county'], state=it['state'] or '', level=it['level'] or '',
                       LEVEL=(it['level'] or '').upper(), source=source or SOURCE, why=why_sentence(r),
                       hazard=it['hazard']).replace('  ', ' ').strip()


def build_messages(items, usable):
    msgs, missing = [], set()
    for it in items:
        sms_sits = it['situations'][:1]                 # one SMS per county: the most urgent situation
        radio = {'flood' if any(s.startswith('flood') or s.startswith('aap') for s in it['situations']) else
                 'drought' if any(s.startswith('drought') for s in it['situations']) else 'river'}
        for code, name in LANGUAGES:
            for s in sms_sits:
                tm = usable.get((s, 'sms', code))
                if tm is None:
                    missing.add((s, 'sms', code))
                    continue
                txt = fill(tm, it)
                if len(txt) > SMS_MAX:
                    txt = fill(tm, it, SOURCE_SHORT)
                msgs.append({'state': it['state'], 'county': it['county'], 'situation': s, 'channel': 'sms',
                             'language': code, 'language_name': name, 'text': txt, 'chars': len(txt),
                             'sms_parts': int(np.ceil(len(txt) / SMS_MAX)) if len(txt) > SMS_MAX else 1,
                             'status': 'draft - validate with SSMS / MHADM before release'})
            for s in radio:
                tm = usable.get((s, 'radio', code))
                if tm is None:
                    missing.add((s, 'radio', code))
                    continue
                txt = fill(tm, it)
                msgs.append({'state': it['state'], 'county': it['county'], 'situation': s, 'channel': 'radio',
                             'language': code, 'language_name': name, 'text': txt, 'chars': len(txt),
                             'sms_parts': '', 'status': 'draft - validate with SSMS / MHADM before release'})
    return pd.DataFrame(msgs), missing


def fmt_num(v, f='{:,.0f}'):
    return '' if blank(v) else f.format(float(v))


def brief(scope, items, bul, plans, checklist, trig, when, missing_langs, state=None):
    sub = bul if state is None else bul[bul['state'] == state]
    its = [i for i in items if state is None or i['state'] == state]
    counts = text(sub['alert_level']).str.lower().value_counts()
    data_end = text(bul.get('data_end_date', pd.Series(dtype=object))).max() if 'data_end_date' in bul else ''
    run = text(bul.get('run_utc', pd.Series(dtype=object))).max() if 'run_utc' in bul else ''
    lines = [f"# {scope} - anticipatory action situation brief", '',
             f"Prepared {when:%Y-%m-%d %H:%M} UTC for the {'national' if state is None else state + ' state'} TWG-AA. "
             f"Rain and soil data to {data_end or 'n/a'}; ECMWF run {run or 'n/a'} UTC.", '',
             f"> {DISCLAIMER}", '', '## Summary',
             f"- Counties by alert level: red {int(counts.get('red', 0))}, orange {int(counts.get('orange', 0))}, "
             f"yellow {int(counts.get('yellow', 0))}, green {int(counts.get('green', 0))}."]
    act = plans[(plans['stage'].isin(['readiness', 'activated']))] if plans is not None and len(plans) else pd.DataFrame()
    if state is not None and len(act):
        act = act[act['state'] == state]
    if len(act):
        val = text(act['plan_status']).str.lower().str.startswith('validated')
        lines.append(f"- Validated plans in readiness: {int(((act['stage'] == 'readiness') & val).sum())}; "
                     f"activated: {int(((act['stage'] == 'activated') & val).sum())}.")
        if (~val).any():
            lines.append(f"- Draft plans whose rules are met: {int((~val).sum())} (for review, not activations).")
    else:
        lines.append('- No anticipatory action plan is in readiness or activated.')
    if trig is not None and len(trig):
        tsub = trig if state is None else trig[trig['state'] == state]
        hi = tsub[tsub['current_state'].isin(['readiness', 'activation'])]
        lines.append(f"- River gauges at a proposed trigger level: {len(hi)} counties "
                     f"({int((hi['current_state'] == 'activation').sum())} at activation level).")
    lines += ['', '## Counties with an alert', '| County | State | Level | Hazard | Week-1 rain (mm) | '
              'Heavy-rain chance | People on flood-prone ground |', '|---|---|---|---|---|---|---|']
    shown = 0
    for i in its:
        if i['rank'] >= ALERT_RANK[MIN_ALERT]:
            r = i['row']
            ph = r.get('p_heavy_50mm_week1')
            lines.append(f"| {i['county']} | {i['state']} | **{i['level'].upper()}** | {i['hazard']} | "
                         f"{fmt_num(r.get('week1_rain_median_mm'))} | {'' if blank(ph) else f'{float(ph):.0%}'} | "
                         f"{fmt_num(r.get('pop_flood_prone'))} |")
            shown += 1
    if not shown:
        lines.append('| none | | | | | | |')
    if len(act):
        lines += ['', '## Anticipatory action plans', '| Plan | County | Stage | Since | Plan status | River / readiness / '
                  'activation (m) |', '|---|---|---|---|---|---|']
        for r in act.itertuples():
            lv = '/'.join('' if blank(x) else f'{float(x):.2f}' for x in (r.river_level_m, r.readiness_level_m,
                                                                          r.activation_level_m))
            lines.append(f"| {r.plan_id} | {r.county} | **{r.stage}** | {r.stage_since} | {r.plan_status} | {lv} |")
        if checklist is not None and len(checklist):
            cl = checklist[checklist['plan_id'].isin(act['plan_id'])].copy()
            cl['due_d'] = pd.to_datetime(cl['due'], errors='coerce')
            cl = cl[cl['due_d'] <= pd.Timestamp(when.date()) + pd.Timedelta(days=ACTIONS_DUE_DAYS)]
            if len(cl):
                lines += ['', f"### Actions due within {ACTIONS_DUE_DAYS} days", '| Plan | Action | Lead | Due | Status |',
                          '|---|---|---|---|---|']
                for r in cl.sort_values('due_d').itertuples():
                    lines.append(f"| {r.plan_id} | {r.action} | {'' if blank(r.lead) else r.lead} | {r.due} | "
                                 f"{'' if blank(r.status) else r.status} |")
    notes = [n for i in its for n in i['plan_notes']]
    if trig is not None and len(trig):
        tsub = trig if state is None else trig[trig['state'] == state]
        stale = tsub[tsub['current_state'] == 'stale']
        if len(stale):
            notes.append(f"{len(stale)} county gauges have no satellite pass in the last weeks: "
                         + ', '.join(stale['county'].head(8)) + ('...' if len(stale) > 8 else ''))
    lines += ['', '## Decisions for the group']
    dec = []
    for r in act.itertuples() if len(act) else []:
        if str(r.plan_status).lower().startswith('validated'):
            dec.append(f"- {r.plan_id}: confirm the {r.stage} decision, record it in the activation log"
                       + (' and the fund release time' if r.stage == 'activated' else '') + '.')
        else:
            dec.append(f"- {r.plan_id} (draft plan): its {'activation' if r.stage == 'activated' else 'readiness'} "
                       'rule is met. Review the plan and its trigger; this is not an activation.')
    if shown:
        dec.append(f"- Agree the warning for the {shown} counties with an alert and the channels (radio hubs, chiefs, SMS).")
    if missing_langs:
        dec.append('- Ask intermediaries to translate and validate templates for: ' + ', '.join(sorted(missing_langs)) + '.')
    lines += dec or ['- No decisions needed: routine monitoring.']
    if notes:
        lines += ['', '## Notes'] + [f'- {n}' for n in notes]
    return '\n'.join(lines) + '\n'


def distribution(groups, items, briefs, msgs, when):
    rows = []
    if groups is None:
        return pd.DataFrame()
    g = groups[text(groups['active']).str.lower().isin(['yes', 'y', 'true', '1'])]
    for r in g.to_dict('records'):
        lvl = str(r.get('level', '')).lower()
        langs = [x.strip() for x in str(r.get('languages') or 'en').split(';') if x.strip()]
        min_rank = ALERT_RANK.get(str(r.get('min_alert') or MIN_ALERT).lower(), 1)
        if lvl == 'national' and 'national' in briefs:
            rows.append({'item': os.path.basename(briefs['national']), 'scope': 'national', 'language': 'en'})
        elif lvl == 'state' and r.get('state') in briefs:
            rows.append({'item': os.path.basename(briefs[r['state']]), 'scope': r['state'], 'language': 'en'})
        elif lvl in ('county', 'community'):
            for it in items:
                if (blank(r.get('county')) or ckey(r['county']) == it['key']) and \
                        (blank(r.get('state')) or r['state'] == it['state']) and \
                        (it['rank'] >= min_rank or any(s.startswith('aap_') for s in it['situations'])):
                    ch = 'radio' if r.get('channel') == 'radio_hub' else 'sms'
                    m = msgs[(msgs['county'] == it['county']) & (msgs['channel'] == ch)] if len(msgs) else msgs
                    use = [l for l in langs if l in set(m['language'])] or (['en'] if len(m) else [])
                    for l in use:
                        rows.append({'item': f"{ch} message, {it['county']}", 'scope': it['county'], 'language': l})
        for x in rows:
            x.setdefault('group_id', r['group_id'])
            x.setdefault('group_name', r.get('group_name'))
            x.setdefault('channel', r.get('channel'))
    out = pd.DataFrame(rows)
    if len(out):
        out.insert(0, 'prepared_utc', when.strftime('%Y-%m-%d %H:%M'))
        out['status'] = 'prepared'
        out['sent_utc'] = ''
        out['sent_by'] = ''
        out['receipt_confirmed'] = ''
    return out


# =========================================================================== #
# MAIN                                                                        #
# =========================================================================== #
def run(when=None):
    when = when or now_utc().replace(tzinfo=None)
    bul = read_csv(os.path.join(BUL_DIR, 'county_bulletin_latest.csv'))
    if bul is None:
        sys.exit('county_bulletin_latest.csv not found (BULLETIN_OUT_DIR)')
    ensure_templates(set(text(bul['state'])) - {''})
    plans = read_csv(os.path.join(AA_OUT, 'aap_status_latest.csv'))
    checklist = read_csv(os.path.join(AA_OUT, 'aap_checklist_latest.csv'))
    trig = read_csv(os.path.join(AA_OUT, 'aa_triggers.csv'))
    groups = read_csv(os.path.join(AA_CONFIG, 'recipient_groups.csv'))
    usable, langs = load_templates()
    items = county_items(bul, plans, trig)
    msgs, missing = build_messages(items, usable)
    missing_langs = {dict(LANGUAGES)[c] for _, _, c in missing if c != 'en'}

    stamp = when.strftime('%Y%m%d_%H%M')
    base = os.path.join(AA_OUT, 'dissemination')
    folder = os.path.join(base, stamp)
    os.makedirs(folder, exist_ok=True)
    briefs = {}
    p = os.path.join(folder, 'brief_national.md')
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write(brief('South Sudan', items, bul, plans, checklist, trig, when, missing_langs))
    briefs['national'] = p
    for st in sorted({i['state'] for i in items if i['state']}):
        p = os.path.join(folder, f'brief_{slug(st)}.md')
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(brief(st, items, bul, plans, checklist, trig, when, missing_langs, state=st))
        briefs[st] = p
    msgs.to_csv(os.path.join(folder, 'messages.csv'), index=False)
    long = msgs[(msgs['channel'] == 'sms') & (msgs['chars'] > SMS_MAX)] if len(msgs) else msgs
    if len(long):
        print(f"WARNING: {len(long)} SMS texts exceed {SMS_MAX} characters; shorten their templates")
    with open(os.path.join(folder, 'radio_scripts.md'), 'w', encoding='utf-8') as fh:
        fh.write(f"# Radio scripts - {when:%Y-%m-%d %H:%M} UTC\n\n> Drafts for SSMS / MHADM validation before broadcast. "
                 'Read slowly; repeat the key action twice.\n')
        for r in msgs[msgs['channel'] == 'radio'].itertuples() if len(msgs) else []:
            fh.write(f"\n## {r.county} ({r.state}) - {r.language_name}\n\n{r.text}\n")
    dist = distribution(groups, items, briefs, msgs, when)
    dist.to_csv(os.path.join(folder, 'distribution_plan.csv'), index=False)
    if len(dist):
        lp = os.path.join(AA_OUT, 'dissemination_log.csv')
        old = read_csv(lp)
        (dist if old is None else pd.concat([old.astype(object), dist.astype(object)], ignore_index=True)).to_csv(lp, index=False)
    latest = os.path.join(base, 'latest')
    shutil.rmtree(latest, ignore_errors=True)
    shutil.copytree(folder, latest)
    runs = sorted(d for d in os.listdir(base) if re.fullmatch(r'\d{8}_\d{4}', d))
    for d in runs[:-KEEP_RUNS]:
        shutil.rmtree(os.path.join(base, d), ignore_errors=True)

    g = groups if groups is not None else pd.DataFrame(columns=['level', 'channel', 'active'])
    active = g[text(g['active']).str.lower().isin(['yes', 'y', 'true', '1'])]
    sub = active[active['level'].isin(['state', 'county'])]
    hubs = active[(active['channel'] == 'radio_hub') | (active['level'] == 'community')]
    log_indicators([
        dict(pillar='5', activity='Quarterly updates on operations at all levels', indicator='TWG-AA situation briefs prepared',
             value=len(briefs), kind='event', unit='briefs', verification=os.path.relpath(folder, AA_OUT)),
        dict(pillar='5', activity='Community groups / radio listening hubs disseminate early warnings',
             indicator='Early warning messages prepared', value=len(msgs), kind='event', unit='messages',
             verification='messages.csv', note=', '.join(f'{k} {v}' for k, v in msgs['language'].value_counts().items())
             if len(msgs) else ''),
        dict(pillar='5', activity='Coordination platforms at subnational level linked to the NTWG-AA',
             indicator='Subnational TWG-AA groups active (state / county)', value=len(sub), kind='snapshot',
             unit='groups', verification='aa_config/recipient_groups.csv'),
        dict(pillar='5', activity='Community groups / radio listening hubs disseminate early warnings',
             indicator='Community groups / radio listening hubs registered', value=len(hubs), kind='snapshot',
             unit='groups', verification='aa_config/recipient_groups.csv'),
        dict(pillar='2', activity='Translate meteorological information into local languages',
             indicator='Languages with validated warning templates', value=len(langs), kind='snapshot',
             unit='languages', verification='aa_config/message_templates.csv', note=', '.join(sorted(langs))),
    ], 'aa_p5_dissemination.py')
    return folder, briefs, msgs, dist, missing_langs, items


def main():
    print('=== AA ADD-ON 6 (PILLAR 5): TWG-AA BRIEFS AND EARLY WARNING DISSEMINATION ===')
    folder, briefs, msgs, dist, missing_langs, items = run()
    n_alert = sum(1 for i in items if i['rank'] >= ALERT_RANK[MIN_ALERT])
    print(f"{n_alert} counties with an alert; {len(briefs)} briefs (national + {len(briefs) - 1} states); "
          f"{len(msgs)} messages; {len(dist)} distribution rows prepared")
    if missing_langs:
        print('Templates still to translate and validate: ' + ', '.join(sorted(missing_langs)))
    print('->', folder)
    print('->', os.path.join(AA_OUT, 'dissemination', 'latest'))


def selftest():
    global AA_CONFIG
    import tempfile
    AA_CONFIG = tempfile.mkdtemp(prefix='aa_dis_')
    bul = pd.DataFrame({'county': ['A', 'B', 'C'], 'state': ['S1', 'S1', 'S2'], 'alert_level': ['red', 'green', 'orange'],
                        'alert_hazard': ['flood / waterlogging', 'flood / waterlogging', 'drought / dry spell'],
                        'p_heavy_50mm_week1': [0.6, 0.0, 0.0], 'week1_rain_median_mm': [80.0, 5.0, 1.0],
                        'sm_rootzone_z': [1.2, 0.0, -1.0], 'p_dry_spell_7d_in_15d': [0.0, 0.1, 0.8],
                        'pop_flood_prone': [50000, 100, 0]})
    plans = pd.DataFrame({'plan_id': ['P1', 'P2'], 'county': ['A', 'B'], 'state': ['S1', 'S1'],
                          'stage': ['activated', 'readiness'], 'plan_status': ['validated 2026-06', 'draft (example)'],
                          'stage_since': ['2026-09-01 00:00'] * 2, 'river_level_m': [10.0, 9.0],
                          'readiness_level_m': [9.0, 9.5], 'activation_level_m': [9.8, 10.0]})
    ensure_templates({'S1', 'S2'})
    usable, langs = load_templates()
    assert langs == {'en'}
    items = county_items(bul, plans, None)
    by = {i['county']: i for i in items}
    assert by['A']['situations'][0] == 'aap_activated', 'a validated activated plan leads the messages'
    assert 'aap_readiness' not in by['B']['situations'] and by['B']['plan_notes'], 'draft plans give no community message'
    assert by['C']['situations'] == ['drought_orange']
    msgs, missing = build_messages(items, usable)
    sms = msgs[msgs['channel'] == 'sms']
    assert (sms['chars'] <= SMS_MAX).all(), sms[['county', 'chars']].to_string()
    assert ('flood_red', 'sms', 'din') in missing or ('aap_activated', 'sms', 'din') in missing
    assert 'chance of more than 50 millimetres' in msgs[(msgs['county'] == 'A') & (msgs['channel'] == 'radio')]['text'].iloc[0]
    b = brief('South Sudan', items, bul, plans, None, None, datetime.datetime(2026, 10, 5), {'Dinka (Thuongjang)'})
    assert 'P1: confirm the activated decision' in b and 'Dinka' in b
    shutil.rmtree(AA_CONFIG, ignore_errors=True)
    print('selftest passed: urgency order, no community messages for draft plans, SMS <= 160 characters, '
          'missing translations listed, briefs carry the decisions')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Pillar 5 TWG-AA briefs and early warning dissemination')
    ap.add_argument('--selftest', action='store_true', help='check message and brief rules on synthetic data and exit')
    a = ap.parse_args()
    selftest() if a.selftest else main()
