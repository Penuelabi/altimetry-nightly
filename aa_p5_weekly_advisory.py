#!/usr/bin/env python3
"""
Weekly early-warning advisory for the South Sudan hydro-climate platform (add-on, Pillar 5 coordination, Pillar 2 EWS).

Standalone add-on in the style of the other aa_*.py scripts: it only READS the files the app and the other add-ons
already produce and never edits them. It turns the week's data into a plain-language advisory for each state and for
the country, with sector advice (health, agriculture, livestock, water, communities) selected by the hazards that
actually have an alert this week.

Inputs (all read-only)
    county_bulletin_latest.csv            BULLETIN_OUT_DIR   alert level and hazard, week-1 rain, chance of heavy rain,
                                                             dry-spell chance, soil, people on flood-prone ground
    aa_out/aa_triggers.csv                                   river state at the county gauge (normal/readiness/activation)
    aa_out/p1_county_risk_profile.csv                        risk class (used to order counties)
    data/news.json                                           reports of flooding / dry spells in the last 21 days
    aa_config/weekly_blocks.csv           (written on first run)  the advice and sentence blocks, English + translations
    aa_config/seasonal_outlook.csv        (written on first run)  optional: seasonal rain / temperature outlook typed in
                                                             from the ICPAC / SSMD bulletin (not machine readable)

Outputs   aa_out/weekly/latest/  (and a dated copy aa_out/weekly/<date>/)
    advisory_national_en.md, advisory_<state>_en.md
    advisory_<area>_<lang>.md            only for languages whose blocks are validated (see below)
    preview_unvalidated/advisory_<area>_<lang>_DRAFT.md    machine drafts for native-speaker review, NEVER for release
    language_coverage.csv, weekly_summary.csv

Translation safety (same rule as aa_p5_dissemination.py)
    A block is used in another language only when its row in weekly_blocks.csv has `text` AND `validated_by`, and the
    English block has not changed since (en_hash). Otherwise the English block is shown. A language file is written
    only when at least MIN_COVERAGE of the blocks used are validated. Nothing is sent automatically; every advisory is
    labelled as needing SSMS / MHADM validation, because SSMS issues the official warnings.

Usage
    python aa_p5_weekly_advisory.py                 # build this week's advisories
    python aa_p5_weekly_advisory.py --init          # only write / sync aa_config/weekly_blocks.csv and the outlook template
    python aa_p5_weekly_advisory.py --selftest
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

# =========================================================================== #
# SETTINGS                                                                    #
# =========================================================================== #
HERE = os.path.dirname(os.path.abspath(__file__))
BUL_DIR = os.environ.get('BULLETIN_OUT_DIR', os.path.join(HERE, 'bulletin'))
AA_CONFIG = os.environ.get('AA_CONFIG_DIR', os.path.join(HERE, 'aa_config'))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))
DATA_DIR = os.environ.get('AA_DATA_DIR', os.path.join(HERE, 'data'))
SOURCE = os.environ.get('AA_SOURCE_NAME', 'SS Climate Monitor (advisory)')
MIN_ALERT = 1                      # yellow and above
NEWS_DAYS = 21
MIN_COVERAGE = 0.9                 # share of blocks that must be validated before a language file is written
KEEP_RUNS = 8
ALERT_RANK = {'green': 0, 'yellow': 1, 'orange': 2, 'red': 3}
ALIASES = {'abyeiadministrativearea': 'abyeiregion'}
DEFAULT_LANGS = [('en', 'English'), ('din', 'Dinka (Thuongjang)'), ('nus', 'Nuer (Thok Naath)'), ('swa', 'Swahili')]
STATUS = 'DRAFT: needs validation by SSMS / MHADM before release. Official warnings are issued by SSMS.'

# =========================================================================== #
# ENGLISH MASTER BLOCKS (corrected from the seasonal-forecast draft)          #
# =========================================================================== #
SECTORS = [('health', 'Health'), ('agriculture', 'Agriculture'), ('livestock', 'Livestock'), ('water', 'Water'),
           ('community', 'Communities and disaster risk reduction')]

ADVICE = {
    'flood': {
        'health': {
            'impact': ['Floodwater can contaminate drinking water.',
                       'Diseases such as cholera and malaria can spread.',
                       'Flooding can damage health facilities and cut the roads to them.',
                       'Losing a home, property or family members can cause stress and trauma.'],
            'action': ['Boil or treat drinking water.',
                       'Sleep under a treated mosquito net.',
                       'Avoid walking or playing in floodwater, and wash hands with soap.',
                       'Move to higher ground when a flood alert is issued.',
                       'Health partners: pre-position essential medicines at safe, central points.',
                       'Train Boma health workers and volunteers on emergency response and disease control.']},
        'agriculture': {
            'impact': ['Crops can be washed away or rot in waterlogged fields.',
                       'Planting and weeding can be delayed.',
                       'Seed and stored food can be spoiled.'],
            'action': ['Repair or build dykes early.',
                       'Keep seed and harvested food high and dry.',
                       'Where fields flood, choose crops that tolerate wet soil, such as rice.',
                       'Pre-position food and non-food items for families who may be affected.']},
        'livestock': {
            'impact': ['Waterborne diseases can spread among animals.',
                       'Pastures and cattle camps can be flooded, and animals can be stranded.'],
            'action': ['Move animals to higher ground early, together with your neighbours.',
                       'Vaccinate animals before the floods.',
                       'Keep a reserve of feed.']},
        'water': {
            'impact': ['River levels and stream flows rise.',
                       'Floodwater can contaminate boreholes, hand pumps and open water points.'],
            'action': ['Watch rising river levels and report danger levels to the local authorities.',
                       'Protect water points from floodwater, and treat water before drinking.',
                       'Collect storm water in clean containers.']},
        'community': {
            'impact': ['Roads and bridges can be cut and families can be displaced.',
                       'Tension can rise when many families share limited high ground.'],
            'action': ['Agree now on high ground and escape routes for people, animals and food.',
                       'Keep boats ready, and follow your chief, local authorities and the radio.',
                       'Hold community awareness sessions through disaster risk management committees (DRMCs).',
                       'Train community groups on disaster preparedness and response.',
                       'Share high ground peacefully, and look after children, older people and people with disabilities first.']},
    },
    'dry': {
        'health': {
            'impact': ['Less food and milk can lead to malnutrition.',
                       'Dust can cause breathing problems.',
                       'Water shortage and less hand washing can spread infectious diseases.'],
            'action': ['Save and protect clean water.',
                       'Wash hands with soap whenever water allows.',
                       'Share health advice through community radio and risk communication and community engagement (RCCE).']},
        'agriculture': {
            'impact': ['Planting can be delayed and early crops can fail.',
                       'Harvests and the area planted can fall.',
                       'Pests and crop diseases can increase, and the cost of production can rise.',
                       'Food shortages and malnutrition can follow.'],
            'action': ['Delay planting until the soil is moist enough.',
                       'Use drought-tolerant crops and short-maturity seed.',
                       'Practise water harvesting and water saving, and use drip irrigation where possible.',
                       'Diversify livelihoods and keep a food reserve.']},
        'livestock': {
            'impact': ['Pasture and water can become short, and animals can weaken in the heat.',
                       'Herders and animals may have to travel far to find water and pasture.',
                       'Milk and meat production can fall, and animal diseases can spread.'],
            'action': ['Vaccinate and deworm animals.',
                       'Give animals shade, feed and water.',
                       'Plan grazing moves early, and agree on routes and water points peacefully with neighbouring communities.']},
        'water': {
            'impact': ['Streams and water levels fall, and more water evaporates.',
                       'Less water soaks into the ground to refill wells and boreholes.'],
            'action': ['Use water carefully and store it.',
                       'Collect rainwater whenever it falls.',
                       'Use boreholes and hand pumps, and protect them from damage.']},
        'community': {
            'impact': ['Poor harvests and water shortage can lead to hunger and loss of livestock.',
                       'Disputes over water and pasture, including in cattle camps, can increase.'],
            'action': ['Stock food, and avoid long journeys in the heat.',
                       'Stay in the shade, and drink enough safe water: about 4 to 8 litres a day, depending on what is available.',
                       'Settle disputes over water and pasture through chiefs and local leaders.']},
    },
    'heat': {
        'health': {
            'impact': ['Heat can cause dehydration, heat exhaustion and heat stroke.',
                       'Children, older people and pregnant women are at greatest risk.'],
            'action': ['Drink enough safe water: about 4 to 8 litres a day, depending on what is available.',
                       'Avoid direct sun and wear light-coloured, loose clothes.',
                       'Reduce working hours in the midday heat.']},
        'livestock': {
            'impact': ['Animals suffer heat stress and give less milk and meat.'],
            'action': ['Give animals shade and water.']},
        'community': {
            'impact': ['Water points dry faster, and bush fires become more likely.'],
            'action': ['Make fire lines around villages and fields.',
                       'Reduce long journeys by people and animals.']},
    },
}
HAZARDS = [('flood', 'Heavy rain and flood'), ('dry', 'Dry spell and drought'), ('heat', 'Heat')]

SENTENCES = {
    'title.national': 'Weekly early warning advisory: South Sudan',
    'title.area': 'Weekly early warning advisory: {area}',
    'week_line': 'Week of {date}. Rain and soil data to {data_end}; forecast issued {run}.',
    'audience': 'For communities, chiefs, farmers, herders, local authorities and partners in {area}. Please share this message with your community and local radio.',
    'summary.some': '{n_alert} of {n_total} counties in {area} have an alert this week: {n_red} red, {n_orange} orange and {n_yellow} yellow.',
    'summary.none': 'No county in {area} has an alert this week. Keep watching the weather and the river, and follow the radio.',
    'flood_now': 'Flood or waterlogging risk: {counties}.',
    'dry_now': 'Dry-spell risk: {counties}.',
    'river_now': 'River gauges at readiness or activation level near: {counties}.',
    'less_rain_note': 'A dry-spell alert means less rain than usual. It does not mean there will be no rain.',
    'hdr.situation': 'What is happening',
    'hdr.todo': 'What should communities do?',
    'hdr.impact': 'What may happen',
    'hdr.action': 'What to do',
    'hdr.news': 'Recent reports (last 21 days, in English)',
    'hdr.outlook': 'Seasonal outlook',
    'col.county': 'County',
    'col.level': 'Alert',
    'col.hazard': 'Hazard',
    'col.rain': 'Rain this week (mm)',
    'col.heavy': 'Chance of heavy rain',
    'lvl.red': 'red', 'lvl.orange': 'orange', 'lvl.yellow': 'yellow', 'lvl.green': 'green',
    'hz.flood': 'flood', 'hz.dry': 'dry spell',
    'outlook.rain.below': 'Seasonal outlook ({season}): less rain than usual is more likely in {areas}.',
    'outlook.rain.near': 'Seasonal outlook ({season}): normal rain is more likely in {areas}.',
    'outlook.rain.above': 'Seasonal outlook ({season}): more rain than usual is more likely in {areas}.',
    'outlook.temp.above': 'Seasonal outlook ({season}): warmer than usual temperatures are more likely in {areas}.',
    'outlook.temp.near': 'Seasonal outlook ({season}): normal temperatures are more likely in {areas}.',
    'outlook.temp.below': 'Seasonal outlook ({season}): cooler than usual temperatures are more likely in {areas}.',
    'disclaimer': 'Official warnings are issued by the South Sudan Meteorological Service (SSMS). This advisory is decision support from the hydro-climate platform (satellite rain, soil, river levels and the ECMWF forecast).',
    'source_line': 'Source: {source}.',
}


def english_blocks():
    """{block_id: (group, english text)} in reading order."""
    out = {k: ('sentence', v) for k, v in SENTENCES.items()}
    for key, name in SECTORS:
        out[f'sector.{key}'] = ('heading', name)
    for key, name in HAZARDS:
        out[f'hz_title.{key}'] = ('heading', name)
    for hz, secs in ADVICE.items():
        for sec, parts in secs.items():
            for kind in ('impact', 'action'):
                for i, t in enumerate(parts[kind], 1):
                    out[f'{hz}.{sec}.{kind}.{i}'] = (f'advice-{hz}', t)
    return out


# =========================================================================== #
# SMALL HELPERS (repeated in each add-on so every file runs on its own)       #
# =========================================================================== #
def languages():
    """[(code, name)] from aa_config/languages.csv (enabled rows; English first). Falls back to DEFAULT_LANGS."""
    df = read_csv(os.path.join(AA_CONFIG, 'languages.csv'), dtype=str, keep_default_na=False)
    if df is None or not len(df):
        return list(DEFAULT_LANGS)
    out = [(r['code'], r['name']) for r in df.to_dict('records') if r.get('enabled', 'yes').lower() != 'no']
    return [x for x in out if x[0] == 'en'] + [x for x in out if x[0] != 'en'] if out else list(DEFAULT_LANGS)


def county_languages():
    """{county key: [codes]} (primary first) from aa_config/county_languages.csv, or None when the file is absent."""
    df = read_csv(os.path.join(AA_CONFIG, 'county_languages.csv'), dtype=str, keep_default_na=False)
    if df is None:
        return None
    out = {}
    for r in df.to_dict('records'):
        codes = [r['primary'].strip()] + [c.strip() for c in r['secondary'].split(';') if c.strip()]
        out[ckey(r['county'])] = [c for c in codes if c]
    return out


def ckey(name):
    k = re.sub(r'[^a-z0-9]+', '', str(name).lower())
    return ALIASES.get(k, k)


def slug(s):
    return re.sub(r'[^a-z0-9]+', '_', str(s).lower()).strip('_')


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def blank(v):
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() in ('', 'nan', 'None')


def text(series):
    return series.astype(object).where(series.notna(), '').astype(str).str.strip().replace({'nan': '', 'None': ''})


def read_csv(path, **kw):
    if path and os.path.exists(path) and os.path.getsize(path) > 2:
        try:
            return pd.read_csv(path, **kw)
        except Exception as e:
            print(f"WARNING: could not read {path}: {e}")
    return None


def num(v):
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def en_hash(t):
    return hashlib.sha1(t.encode('utf-8')).hexdigest()[:10]


def log_indicators(rows):
    if not rows:
        return
    os.makedirs(AA_OUT, exist_ok=True)
    path = os.path.join(AA_OUT, 'aa_indicator_ledger.csv')
    cols = ['run_utc', 'script', 'pillar', 'activity', 'indicator', 'value', 'kind', 'unit', 'verification', 'note']
    new = pd.DataFrame(rows)
    new['run_utc'] = now_utc().strftime('%Y-%m-%d %H:%M')
    new['script'] = 'aa_p5_weekly_advisory.py'
    for c in cols:
        if c not in new:
            new[c] = ''
    old = read_csv(path)
    df = new[cols] if old is None else pd.concat([old.astype(object), new[cols].astype(object)], ignore_index=True)
    dup = pd.DataFrame({'d': text(df['run_utc']).str[:10], 's': df['script'], 'i': df['indicator']}).duplicated(keep='last')
    df = df[~(df['kind'].eq('snapshot') & dup)]
    df.to_csv(path, index=False)


# =========================================================================== #
# BLOCK FILE (English master + translations)                                  #
# =========================================================================== #
BLOCK_COLS = ['block_id', 'group', 'language', 'language_name', 'text', 'en_hash', 'validated_by', 'validated_date', 'notes']


def no_mt_codes():
    df = read_csv(os.path.join(AA_CONFIG, 'languages.csv'), dtype=str, keep_default_na=False)
    return set() if df is None else {r['code'] for r in df.to_dict('records') if r.get('mt', '') == 'none'}


def sync_blocks():
    """Create or update aa_config/weekly_blocks.csv. Never deletes rows, never touches translations or validations."""
    path = os.path.join(AA_CONFIG, 'weekly_blocks.csv')
    NO_MT = no_mt_codes()
    master = english_blocks()
    old = read_csv(path, dtype=str, keep_default_na=False)
    rows = [] if old is None else old.to_dict('records')
    have = {(r['block_id'], r['language']): i for i, r in enumerate(rows)}
    changed = old is None
    today = now_utc().strftime('%Y-%m-%d')
    for bid, (grp, en) in master.items():
        h = en_hash(en)
        for code, name in languages():
            i = have.get((bid, code))
            if code == 'en':
                row = {'block_id': bid, 'group': grp, 'language': 'en', 'language_name': name, 'text': en, 'en_hash': h,
                       'validated_by': 'platform (English master)', 'validated_date': '', 'notes': ''}
            else:
                row = {'block_id': bid, 'group': grp, 'language': code, 'language_name': name, 'text': '', 'en_hash': h,
                       'validated_by': '', 'validated_date': '',
                       'notes': 'translate from the English text with a native speaker; fill validated_by when checked'}
                if code in NO_MT:
                    row['notes'] = 'no machine translation exists for this language: a native speaker translates by hand; fill validated_by when checked'
            if i is None:
                rows.append(row)
                changed = True
            elif code == 'en' and rows[i]['text'] != en:
                rows[i].update({'text': en, 'en_hash': h, 'group': grp})
                changed = True
            elif code != 'en':
                if rows[i].get('en_hash') != h and rows[i].get('text', '').strip() and not rows[i].get('notes', '').startswith('English changed'):
                    rows[i]['notes'] = f'English changed {today}: re-translate and re-validate'
                    changed = True
    if changed:
        os.makedirs(AA_CONFIG, exist_ok=True)
        pd.DataFrame(rows)[BLOCK_COLS].to_csv(path, index=False)
        print(f"Blocks file written/updated: {path} ({len(rows)} rows)")
    opath = os.path.join(AA_CONFIG, 'seasonal_outlook.csv')
    if not os.path.exists(opath):
        pd.DataFrame(columns=['season', 'area', 'variable', 'category', 'probability_pct', 'valid_to', 'source', 'note']).to_csv(opath, index=False)
        print(f"Template written: {opath} (area = national, a state, or a county; variable = rain or temperature; "
              "category = below, near or above; copy from the ICPAC / SSMD seasonal bulletin and check it against its maps)")
    return path


def load_blocks():
    """Return (master {id: (grp, en)}, usable {lang: {id: text}}, drafts {lang: {id: text}}, stale list)."""
    master = english_blocks()
    df = read_csv(os.path.join(AA_CONFIG, 'weekly_blocks.csv'), dtype=str, keep_default_na=False)
    usable, drafts, stale = {}, {}, []
    if df is None:
        return master, usable, drafts, stale
    for r in df.to_dict('records'):
        bid, lang, t = r['block_id'], r['language'], r['text'].strip()
        if lang == 'en' or bid not in master or not t:
            continue
        current = en_hash(master[bid][1])
        if r['validated_by'].strip():
            if r['en_hash'] in ('', current):
                usable.setdefault(lang, {})[bid] = t
            else:
                stale.append((bid, lang))
        else:
            drafts.setdefault(lang, {})[bid] = t
    return master, usable, drafts, stale


# =========================================================================== #
# DATA                                                                        #
# =========================================================================== #
def load_data(as_of):
    bul = read_csv(os.path.join(BUL_DIR, 'county_bulletin_latest.csv'))
    if bul is None:
        sys.exit('county_bulletin_latest.csv not found (BULLETIN_OUT_DIR)')
    trig = read_csv(os.path.join(AA_OUT, 'aa_triggers.csv'))
    risk = read_csv(os.path.join(AA_OUT, 'p1_county_risk_profile.csv'))
    outlook = read_csv(os.path.join(AA_CONFIG, 'seasonal_outlook.csv'), dtype=str, keep_default_na=False)
    news = []
    npath = os.path.join(DATA_DIR, 'news.json')
    if os.path.exists(npath):
        try:
            items = json.load(open(npath, encoding='utf-8')).get('items', [])
            cutoff = (as_of - datetime.timedelta(days=NEWS_DAYS)).strftime('%Y-%m-%d')
            news = [n for n in items if str(n.get('date', '')) >= cutoff]
        except Exception as e:
            print(f"WARNING: could not read news.json: {e}")
    return bul, trig, risk, outlook, news


def county_records(bul, trig, risk):
    tr = {ckey(r['county']): r for r in trig.to_dict('records')} if trig is not None else {}
    rk = {ckey(r['county']): r for r in risk.to_dict('records')} if risk is not None else {}
    recs = []
    for r in bul.to_dict('records'):
        lvl = str(r.get('alert_level') or '').lower()
        hz = str(r.get('alert_hazard') or '').lower()
        t = tr.get(ckey(r['county']), {})
        recs.append({
            'county': r['county'], 'state': r.get('state') or '', 'level': lvl, 'rank': ALERT_RANK.get(lvl, 0),
            'hazard': 'flood' if 'flood' in hz else 'dry' if 'drought' in hz or 'dry' in hz else '',
            'rain': num(r.get('week1_rain_median_mm')), 'heavy': num(r.get('p_heavy_50mm_week1')),
            'river': str(t.get('current_state') or ''), 'risk_rank': num(rk.get(ckey(r['county']), {}).get('risk_rank')) or 999,
            'run': str(r.get('run_utc') or ''), 'data_end': str(r.get('data_end_date') or '')})
    return recs


# =========================================================================== #
# COMPOSE                                                                     #
# =========================================================================== #
class Blocks:
    """Looks up a block in one language. Validated text first; machine drafts only when use_drafts (review previews);
    otherwise the English text. Tracks which blocks were validated so a language is released only when well covered."""

    def __init__(self, master, lang, usable, drafts=None, use_drafts=False):
        self.master, self.lang = master, lang
        self.usable = usable.get(lang, {})
        self.drafts = (drafts or {}).get(lang, {}) if use_drafts else {}
        self.used, self.hit, self.draft_hit = set(), set(), set()

    def __call__(self, bid):
        self.used.add(bid)
        if self.lang == 'en':
            self.hit.add(bid)
            return self.master[bid][1]
        if bid in self.usable:
            self.hit.add(bid)
            return self.usable[bid]
        if bid in self.drafts:
            self.draft_hit.add(bid)
            return self.drafts[bid]
        return self.master[bid][1]

    def coverage(self):
        return len(self.hit) / len(self.used) if self.used else 0.0


def fmt_list(names):
    names = list(names)
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1] if names else ''


def outlook_lines(B, outlook, area, area_counties, as_of):
    lines = []
    if outlook is None or not len(outlook):
        return lines
    keys = {ckey(area)} | {ckey(c) for c in area_counties}
    nat = ckey(area) == 'national'
    sel = outlook[(outlook['area'].map(ckey).isin(keys)) | (outlook['area'].map(ckey).eq('national'))]
    sel = sel[sel['valid_to'].map(lambda v: blank(v) or str(v) >= as_of.strftime('%Y-%m-%d'))]
    groups = {}
    for r in sel.to_dict('records'):
        var = 'temp' if str(r['variable']).lower().startswith('temp') else 'rain'
        cat = str(r['category']).lower()
        if (var, cat) in {('rain', 'below'), ('rain', 'near'), ('rain', 'above'), ('temp', 'above'), ('temp', 'near'), ('temp', 'below')}:
            nm = r['area'] if not (ckey(r['area']) == 'national') else ('South Sudan' if nat else r['area'])
            p = r.get('probability_pct')
            groups.setdefault((var, cat, r['season']), []).append(f"{nm} ({p}%)" if not blank(p) else nm)
    for (var, cat, season), areas in groups.items():
        lines.append(B(f'outlook.{var}.{cat}').format(season=season, areas=fmt_list(sorted(set(areas)))))
    return lines


def compose(area, recs, outlook, news, as_of, B, state_names=None):
    national = area == 'national'
    sub = recs if national else [r for r in recs if r['state'] == area]
    area_name = 'South Sudan' if national else area
    alerts = sorted([r for r in sub if r['rank'] >= MIN_ALERT], key=lambda r: (-r['rank'], r['risk_rank'], r['county']))
    n = {k: sum(1 for r in alerts if r['level'] == k) for k in ('red', 'orange', 'yellow')}
    run = next((r['run'] for r in sub if r['run']), '')
    data_end = next((r['data_end'] for r in sub if r['data_end']), '')
    out = [f"# {B('title.national') if national else B('title.area').format(area=area_name)}", '',
           f"*{STATUS}*", '',
           B('week_line').format(date=as_of.strftime('%Y-%m-%d'), data_end=data_end or '-', run=run or '-'), '',
           B('audience').format(area=area_name), '', f"## {B('hdr.situation')}", '']
    if alerts:
        out += [B('summary.some').format(n_alert=len(alerts), n_total=len(sub), area=area_name, n_red=n['red'],
                                         n_orange=n['orange'], n_yellow=n['yellow']), '']
        lv = lambda r: f"{r['county']} ({B('lvl.' + r['level'])}" + (f", {r['state']}" if national else '') + ')'
        fl = [lv(r) for r in alerts if r['hazard'] == 'flood']
        dr = [lv(r) for r in alerts if r['hazard'] == 'dry']
        if fl:
            out += [B('flood_now').format(counties=', '.join(fl)), '']
        if dr:
            out += [B('dry_now').format(counties=', '.join(dr)), B('less_rain_note'), '']
        rv = [r['county'] for r in sub if r['river'] in ('readiness', 'activation')]
        if rv:
            out += [B('river_now').format(counties=', '.join(rv)), '']
        out += [f"| {B('col.county')} | {B('col.level')} | {B('col.hazard')} | {B('col.rain')} | {B('col.heavy')} |",
                '|---|---|---|---|---|']
        for r in alerts:
            rain = '' if r['rain'] is None else '%.0f' % r['rain']
            heavy = '' if r['heavy'] is None else '%.0f%%' % (100 * r['heavy'])
            where = ' (' + r['state'] + ')' if national else ''
            hz = B('hz.' + r['hazard']) if r['hazard'] else ''
            out.append('| %s%s | %s | %s | %s | %s |' % (r['county'], where, B('lvl.' + r['level']), hz, rain, heavy))
        out.append('')
    else:
        out += [B('summary.none').format(area=area_name), '']
    ol = outlook_lines(B, outlook, area, [r['county'] for r in sub], as_of)
    if ol:
        out += [f"## {B('hdr.outlook')}", ''] + [x for l in ol for x in (l, '')]
    hazards = [h for h in ('flood', 'dry') if any(r['hazard'] == h for r in alerts)]
    if any(('temperature' in str(o.get('variable', '')).lower() or str(o.get('variable', '')).lower().startswith('temp'))
           and str(o.get('category', '')).lower() == 'above' for o in (outlook.to_dict('records') if outlook is not None else [])):
        hazards.append('heat')
    if hazards:
        out += [f"## {B('hdr.todo')}", '']
        for h in hazards:
            out += [f"### {B('hz_title.' + h)}", '']
            for sec, _ in SECTORS:
                if sec not in ADVICE[h]:
                    continue
                out += [f"**{B('sector.' + sec)}**", '', f"*{B('hdr.impact')}*", '']
                out += [f"- {B(f'{h}.{sec}.impact.{i}')}" for i in range(1, len(ADVICE[h][sec]['impact']) + 1)]
                out += ['', f"*{B('hdr.action')}*", '']
                out += [f"- {B(f'{h}.{sec}.action.{i}')}" for i in range(1, len(ADVICE[h][sec]['action']) + 1)]
                out.append('')
    cs = {ckey(r['county']) for r in sub}
    nw = [x for x in news if national or any(ckey(c) in cs for c in x.get('counties', []))]
    if nw:
        out += [f"## {B('hdr.news')}", '']
        for x in sorted(nw, key=lambda x: x['date'], reverse=True):
            out.append(f"- {x['date']} ({', '.join(x.get('counties', []))}, {x.get('hazard', '')}): {x['text']} ({x.get('source', '')})")
        out.append('')
    out += ['---', '', B('disclaimer'), '', B('source_line').format(source=SOURCE), '']
    return '\n'.join(out), {'area': area_name, 'alerts': len(alerts), 'counties': len(sub), **n}


# =========================================================================== #
# RUN                                                                         #
# =========================================================================== #
def run(as_of=None, previews=True):
    sync_blocks()
    as_of = as_of or now_utc().replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
    bul, trig, risk, outlook, news = load_data(as_of)
    recs = county_records(bul, trig, risk)
    master, usable, drafts, stale = load_blocks()
    states = sorted({r['state'] for r in recs if r['state']})
    areas = ['national'] + states
    stamp = as_of.strftime('%Y-%m-%d')
    latest = os.path.join(AA_OUT, 'weekly', 'latest')
    if os.path.isdir(latest):
        shutil.rmtree(latest)
    os.makedirs(os.path.join(latest, 'preview_unvalidated'), exist_ok=True)
    summary, coverage = [], []
    clang = county_languages()
    state_of = {ckey(r['county']): r['state'] for r in recs}
    lang_states = {}
    if clang:
        for ck, codes in clang.items():
            for c in codes:
                lang_states.setdefault(c, set()).add(state_of.get(ck, ''))
    pop = read_csv(os.path.join(DATA_DIR, 'ssd_county_population_2025.csv'))
    popmap = {ckey(r['county']): num(r['pop_2025']) or 0 for r in pop.to_dict('records')} if pop is not None else {}
    status = {}                                    # (area, lang) -> (released, coverage, file)
    for lang, lname in languages():
        wrote = 0
        for area in areas:
            if lang != 'en' and clang:
                st = lang_states.get(lang, set())
                if (area == 'national' and len(st - {''}) < 3) or (area != 'national' and area not in st):
                    continue                       # this language is not used there (national: only broad languages)
            B = Blocks(master, lang, usable)
            md, info = compose(area, recs, outlook, news, as_of, B)
            cov = B.coverage()
            fname = f"advisory_{slug(area)}_{lang}.md"
            if lang == 'en':
                summary.append(info)
            released = lang == 'en' or cov >= MIN_COVERAGE
            if released:
                with open(os.path.join(latest, fname), 'w', encoding='utf-8') as f:
                    f.write(md)
                wrote += 1
            status[(area, lang)] = ('yes' if released else 'no', round(cov, 2), fname if released else '')
            if lang != 'en' and previews and drafts.get(lang):
                P = Blocks(master, lang, usable, drafts, use_drafts=True)
                pmd, _ = compose(area, recs, outlook, news, as_of, P)
                banner = (f"> **MACHINE DRAFT in {lname}: not validated. For native-speaker review only; do not publish.** "
                          f"{len(P.draft_hit)} draft and {len(P.hit)} validated blocks; the rest are English.\n\n")
                with open(os.path.join(latest, 'preview_unvalidated', f"advisory_{slug(area)}_{lang}_DRAFT.md"), 'w', encoding='utf-8') as f:
                    f.write(banner + pmd)
        prim = [ck for ck, codes in (clang or {}).items() if codes and codes[0] == lang]
        coverage.append({'language': lang, 'language_name': lname, 'blocks_total': len(master),
                         'blocks_validated': len(master) if lang == 'en' else len(usable.get(lang, {})),
                         'blocks_draft_only': 0 if lang == 'en' else len(drafts.get(lang, {})),
                         'counties_primary': len(prim), 'population_primary': int(sum(popmap.get(ck, 0) for ck in prim)),
                         'counties_any': sum(1 for codes in (clang or {}).values() if lang in codes),
                         'files_written': wrote, 'released': 'yes' if wrote else 'no (needs validation)'})
    if clang:
        plan = []
        for r in sorted(recs, key=lambda r: (r['state'], r['county'])):
            codes = clang.get(ckey(r['county']), [])
            for k, code in enumerate(dict.fromkeys(['en'] + codes)):
                rel, cov, fn = status.get((r['state'], code), ('no', 0.0, ''))
                plan.append({'state': r['state'], 'county': r['county'], 'population': int(popmap.get(ckey(r['county']), 0)),
                             'alert_level': r['level'], 'hazard': r['hazard'], 'role': 'english' if code == 'en' else ('primary' if code == codes[0] else 'secondary'),
                             'language': code, 'state_advisory_file': fn, 'released': rel, 'validated_share': cov})
        pd.DataFrame(plan).to_csv(os.path.join(latest, 'county_language_plan.csv'), index=False)
    pd.DataFrame(summary).to_csv(os.path.join(latest, 'weekly_summary.csv'), index=False)
    pd.DataFrame(coverage).to_csv(os.path.join(latest, 'language_coverage.csv'), index=False)
    if stale:
        print(f"NOTE: {len(stale)} validated translation block(s) are stale because the English changed; they are not used until re-validated")
    dated = os.path.join(AA_OUT, 'weekly', stamp)
    if os.path.isdir(dated):
        shutil.rmtree(dated)
    shutil.copytree(latest, dated)
    runs = sorted(d for d in os.listdir(os.path.join(AA_OUT, 'weekly')) if re.match(r'\d{4}-\d{2}-\d{2}$', d))
    for d in runs[:-KEEP_RUNS]:
        shutil.rmtree(os.path.join(AA_OUT, 'weekly', d))
    langs_ok = sum(1 for c in coverage if c['released'] == 'yes')
    nfiles = len([f for f in os.listdir(latest) if f.endswith('.md')])
    log_indicators([
        dict(pillar='5', activity='Weekly early warning advisory', indicator='Weekly advisory files released', value=nfiles,
             kind='snapshot', unit='advisories', verification='aa_out/weekly/latest', note=''),
        dict(pillar='2', activity='Translate meteorological information into local languages', indicator='Languages with validated weekly advisory blocks',
             value=langs_ok, kind='snapshot', unit='languages', verification='aa_config/weekly_blocks.csv', note='English counts as 1')])
    print(f"Wrote {nfiles} advisories ({', '.join(c['language'] for c in coverage if c['released'] == 'yes')}) to {latest}")
    return latest


def selftest():
    tmp = tempfile.mkdtemp()
    global BUL_DIR, AA_CONFIG, AA_OUT, DATA_DIR
    BUL_DIR, AA_CONFIG, AA_OUT, DATA_DIR = (os.path.join(tmp, d) for d in ('bul', 'cfg', 'out', 'data'))
    for d in (BUL_DIR, AA_OUT, DATA_DIR):
        os.makedirs(d)
    pd.DataFrame({'county': ['Lafon', 'Magwi', 'Bor South', 'Wau'], 'state': ['Eastern Equatoria', 'Eastern Equatoria', 'Jonglei', 'Western Bahr el Ghazal'],
                  'alert_level': ['red', 'orange', 'orange', 'green'],
                  'alert_hazard': ['drought / dry spell', 'flood / waterlogging', 'drought / dry spell', ''],
                  'week1_rain_median_mm': [31, 52, 27, 40], 'p_heavy_50mm_week1': [0.14, 0.56, 0.1, 0.0],
                  'run_utc': ['2026-10-10 01:00'] * 4, 'data_end_date': ['2026-10-05'] * 4}).to_csv(os.path.join(BUL_DIR, 'county_bulletin_latest.csv'), index=False)
    pd.DataFrame({'county': ['Magwi'], 'current_state': ['readiness']}).to_csv(os.path.join(AA_OUT, 'aa_triggers.csv'), index=False)
    json.dump({'items': [{'date': '2026-10-08', 'counties': ['Magwi'], 'hazard': 'Flood', 'text': 'Test report.', 'source': 'Test'}]}, open(os.path.join(DATA_DIR, 'news.json'), 'w'))
    run(as_of=datetime.datetime(2026, 10, 10))
    blocks = pd.read_csv(os.path.join(AA_CONFIG, 'weekly_blocks.csv'), dtype=str, keep_default_na=False)
    assert len(blocks) == len(DEFAULT_LANGS) * len(english_blocks()), 'one row per block per language'
    nat = open(os.path.join(AA_OUT, 'weekly', 'latest', 'advisory_national_en.md'), encoding='utf-8').read()
    assert '3 of 4 counties' in nat and 'Lafon (red' in nat and 'Magwi' in nat and 'Test report.' in nat
    assert 'Dry-spell risk' in nat and 'Flood or waterlogging risk' in nat and 'River gauges at readiness' in nat
    assert not any(f.startswith('advisory_national_din') for f in os.listdir(os.path.join(AA_OUT, 'weekly', 'latest'))), 'no unvalidated release'
    # translate one block, unvalidated: must not be released, must appear only in the preview
    i = blocks.index[(blocks.block_id == 'summary.none') & (blocks.language == 'din')][0]
    blocks.loc[i, 'text'] = 'DRAFT-DINKA'
    blocks.to_csv(os.path.join(AA_CONFIG, 'weekly_blocks.csv'), index=False)
    run(as_of=datetime.datetime(2026, 10, 10))
    prev = os.path.join(AA_OUT, 'weekly', 'latest', 'preview_unvalidated')
    assert any('din' in f for f in os.listdir(prev)) is True
    # validate it, then change the English: the validated block must go stale and not be used
    blocks.loc[i, ['validated_by']] = 'Test Reviewer'
    blocks.to_csv(os.path.join(AA_CONFIG, 'weekly_blocks.csv'), index=False)
    _, usable, _, stale = load_blocks()
    assert usable['din'].get('summary.none') == 'DRAFT-DINKA' and not stale
    SENTENCES['summary.none'] = 'Changed English sentence for {area}.'
    _, usable, _, stale = load_blocks()
    assert 'summary.none' not in usable.get('din', {}) and stale, 'English change must make the translation stale'
    print('selftest passed')
    shutil.rmtree(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--init', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--no-previews', action='store_true')
    ap.add_argument('--date', help='YYYY-MM-DD (default: today, UTC)')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.init:
        return sync_blocks()
    as_of = datetime.datetime.strptime(a.date, '%Y-%m-%d') if a.date else None
    run(as_of, previews=not a.no_previews)


if __name__ == '__main__':
    main()
