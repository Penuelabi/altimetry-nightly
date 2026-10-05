# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 7 - PILLAR 5: COORDINATION AND LEGAL FRAMEWORK (results tracking)
South Sudan Roadmap on Anticipatory Action 2025-2030, Pillar 5: "quarterly meetings at all levels, providing updates
on operations, sharing experiences, and jointly developing AA tools for implementation and monitoring", and the
roadmap's results framework (activities, output indicators, means of verification).

What it does
  Turns everything the other add-ons log into a quarterly progress report for the TWG-AA, against your targets:
    aa_out/aa_indicator_ledger.csv     written by every add-on ('snapshot' = latest value in the quarter is kept;
                                       'event' = summed over the quarter)
    aa_out/aap_activation_log.csv      readiness and activation decisions
    aa_out/simulations/*/evaluation.csv  an exercise counts as CONDUCTED once 'conducted_date' is filled
    aa_out/dissemination_log.csv       items marked 'sent'
    aa_config/meetings_log.csv         TWG-AA meetings (national, state, county)
    aa_config/feedback_log.csv         community feedback on warnings
    aa_config/indicator_targets.csv    yearly targets 2026-2030 (template written on the first run)
  The report lists every roadmap indicator the platform can measure for Pillars 1, 2, 3 and 5, with the last four
  quarters, the year to date, the target and % achieved, the plan activations of the quarter, the indicators with no
  data yet, and suggested next steps.

Outputs  aa_out/p5_indicator_report_<YYYYQn>.csv / .md / .png and p5_indicator_report_latest.md
Run:     python aa_p5_indicator_tracker.py [--quarter 2026Q4]        python aa_p5_indicator_tracker.py --selftest
"""
import argparse
import datetime
import glob
import os

import numpy as np
import pandas as pd

# =========================================================================== #
# SETTINGS                                                                    #
# =========================================================================== #
HERE = os.path.dirname(os.path.abspath(__file__))
AA_CONFIG = os.environ.get('AA_CONFIG_DIR', os.path.join(HERE, 'aa_config'))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))
YEARS = range(2026, 2031)
SURFACE, INK, INK2, GRID, BAR = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df', '#2a78d6'

# pillar, roadmap activity, indicator (as logged), how it is counted, means of verification
CATALOGUE = [
    ('1', 'Assess risk profiles for hazards', 'Counties with a flood risk profile', 'snapshot', 'p1_county_risk_profile.csv'),
    ('1', 'Exposure and coping analysis for livelihood zones', 'Livelihood zones with exposure analysis', 'snapshot',
     'p1_zone_profile.csv'),
    ('1', 'Identify and validate vulnerability indicators', 'Vulnerability and coping indicators in use', 'snapshot',
     'aa_config/county_vulnerability.csv'),
    ('1', 'Develop and validate risk maps', 'Risk maps produced', 'event', 'p1_risk_map.png'),
    ('1', 'Integrate risk information into the information management system',
     'Risk datasets exported in HXL for the IMS', 'event', 'p1_county_risk_profile_hxl.csv'),
    ('2', 'Develop technical guidance and tools for triggers and thresholds',
     'Hazards with defined thresholds and data requirements', 'snapshot', 'p2_trigger_design_note.md'),
    ('2', 'Develop technical guidance and tools for triggers and thresholds',
     'Counties with proposed river trigger levels', 'snapshot', 'aa_triggers.csv'),
    ('2', 'Develop technical guidance and tools for triggers and thresholds',
     'Counties with validated river trigger levels', 'snapshot', 'aa_triggers.csv'),
    ('2', 'Map hazards, vulnerabilities and impacts to inform IbF and AA protocols',
     'Trigger skill evaluations against recorded impacts', 'event', 'p2_trigger_skill_season.csv'),
    ('2', 'Centralized repository for multi-hazard IbF, EW and trigger-threshold data',
     'Datasets packaged and validated for the repository', 'event', 'aa_data_package_*.zip'),
    ('2', 'Translate meteorological information into local languages', 'Languages with validated warning templates',
     'snapshot', 'aa_config/message_templates.csv'),
    ('3', 'Develop standardised AAPs for multi-hazard', 'Anticipatory action plans developed', 'snapshot',
     'aa_config/aap_plans.csv'),
    ('3', 'Develop standardised AAPs for multi-hazard', 'Anticipatory action plans validated', 'snapshot',
     'aa_config/aap_plans.csv'),
    ('3', 'Joint simulation exercises on the agreed activation mechanisms', 'Simulation exercise packs prepared', 'event',
     'aa_out/simulations'),
    ('3', 'Joint simulation exercises on the agreed activation mechanisms', 'Simulation exercises conducted', 'derived',
     'simulations/*/evaluation.csv (conducted_date)'),
    ('3', 'Joint activation of the AAPs when the threshold is reached', 'Readiness stages reached', 'event',
     'aap_activation_log.csv'),
    ('3', 'Joint activation of the AAPs when the threshold is reached', 'AAPs activated', 'event',
     'aap_activation_log.csv; aap_reports'),
    ('5', 'Coordination platforms at subnational level linked to the NTWG-AA',
     'Subnational TWG-AA groups active (state / county)', 'snapshot', 'aa_config/recipient_groups.csv'),
    ('5', 'Quarterly meetings at all levels', 'TWG-AA meetings held', 'derived', 'aa_config/meetings_log.csv'),
    ('5', 'Quarterly updates on operations at all levels', 'TWG-AA situation briefs prepared', 'event',
     'aa_out/dissemination'),
    ('5', 'Community groups / radio listening hubs disseminate early warnings',
     'Community groups / radio listening hubs registered', 'snapshot', 'aa_config/recipient_groups.csv'),
    ('5', 'Community groups / radio listening hubs disseminate early warnings', 'Early warning messages prepared',
     'event', 'dissemination/*/messages.csv'),
    ('5', 'Community groups / radio listening hubs disseminate early warnings', 'Early warning items sent', 'derived',
     'dissemination_log.csv (status sent)'),
    ('5', 'Community groups / radio listening hubs disseminate early warnings', 'Community feedback records', 'derived',
     'aa_config/feedback_log.csv'),
]


# =========================================================================== #
# SMALL HELPERS (repeated in each add-on so every file runs on its own)       #
# =========================================================================== #
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


def quarter_of(dates):
    return pd.to_datetime(dates, errors='coerce').dt.to_period('Q')


# =========================================================================== #
# COLLECT                                                                     #
# =========================================================================== #
def ledger_values(ledger):
    """(indicator, quarter) -> value from the ledger, by its kind."""
    if ledger is None or ledger.empty:
        return pd.DataFrame(columns=['indicator', 'quarter', 'value'])
    d = ledger.copy()
    d['quarter'] = quarter_of(d['run_utc'])
    d['value'] = pd.to_numeric(d['value'], errors='coerce')
    d = d.dropna(subset=['quarter', 'value'])
    snap = d[d['kind'] == 'snapshot'].sort_values('run_utc').groupby(['indicator', 'quarter'])['value'].last()
    ev = d[d['kind'] == 'event'].groupby(['indicator', 'quarter'])['value'].sum()
    return pd.concat([snap, ev]).rename('value').reset_index()


def derived_values():
    rows = []
    for f in glob.glob(os.path.join(AA_OUT, 'simulations', '*', 'evaluation.csv')):
        e = read_csv(f)
        if e is None or 'item' not in e:
            continue
        v = e.loc[e['item'] == 'conducted_date', 'observed']
        d = pd.to_datetime(v.iloc[0], errors='coerce') if len(v) else pd.NaT
        if pd.notna(d):
            rows.append(('Simulation exercises conducted', d.to_period('Q'), 1))
    m = read_csv(os.path.join(AA_CONFIG, 'meetings_log.csv'))
    if m is not None and 'date' in m:
        for q in quarter_of(m['date']).dropna():
            rows.append(('TWG-AA meetings held', q, 1))
    s = read_csv(os.path.join(AA_OUT, 'dissemination_log.csv'))
    if s is not None and 'status' in s:
        sent = s[text(s['status']).str.lower().eq('sent')]
        when = sent['sent_utc'].where(text(sent['sent_utc']).ne(''), sent['prepared_utc'])
        for q in quarter_of(when).dropna():
            rows.append(('Early warning items sent', q, 1))
    fb = read_csv(os.path.join(AA_CONFIG, 'feedback_log.csv'))
    if fb is not None and 'date' in fb:
        for q in quarter_of(fb['date']).dropna():
            rows.append(('Community feedback records', q, 1))
    if not rows:
        return pd.DataFrame(columns=['indicator', 'quarter', 'value'])
    return pd.DataFrame(rows, columns=['indicator', 'quarter', 'value']).groupby(
        ['indicator', 'quarter'], as_index=False)['value'].sum()


def ensure_targets():
    path = os.path.join(AA_CONFIG, 'indicator_targets.csv')
    if not os.path.exists(path):
        os.makedirs(AA_CONFIG, exist_ok=True)
        t = pd.DataFrame([{'pillar': p, 'indicator': i, **{f'target_{y}': '' for y in YEARS},
                           'notes': 'snapshot: value to reach by year end' if k == 'snapshot' else
                           'count over the year'} for p, a, i, k, v in CATALOGUE])
        t.to_csv(path, index=False)
        print(f"Template written: {path} (fill the yearly targets agreed with the TWG-AA)")
    return read_csv(path)


# =========================================================================== #
# REPORT                                                                      #
# =========================================================================== #
def build(quarter, ledger, derived, targets):
    q = pd.Period(quarter, 'Q')
    qs = [q - 3, q - 2, q - 1, q]
    parts = [d for d in (ledger_values(ledger), derived) if len(d)]
    vals = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=['indicator', 'quarter', 'value'])
    vals['quarter'] = vals['quarter'].astype('period[Q-DEC]')
    tgt = targets.set_index('indicator') if targets is not None and 'indicator' in targets else pd.DataFrame()
    known = {c[2] for c in CATALOGUE}
    extra = sorted(set(vals['indicator']) - known)
    lk = ledger[['indicator', 'pillar', 'activity', 'kind']].drop_duplicates('indicator').set_index('indicator') \
        if ledger is not None and len(ledger) else pd.DataFrame()
    rows = []
    for p, act, ind, kind, verif in CATALOGUE + [(str(lk.loc[i, 'pillar']), lk.loc[i, 'activity'], i,
                                                  lk.loc[i, 'kind'], 'aa_indicator_ledger.csv') for i in extra if i in lk.index]:
        v = vals[vals['indicator'] == ind].set_index('quarter')['value']
        rec = {'pillar': p, 'activity': act, 'indicator': ind, 'counted_as': kind, 'verification': verif}
        for qq in qs:
            rec[str(qq)] = v.get(qq, np.nan)
        year = v[[x for x in v.index if x.year == q.year and x <= q]]
        if kind == 'snapshot':
            ytd = year.loc[max(year.index)] if len(year) else np.nan
        else:
            ytd = year.sum() if len(year) else np.nan
        rec['year_to_date'] = ytd
        t = pd.to_numeric(tgt.loc[ind, f'target_{q.year}'], errors='coerce') if ind in tgt.index and \
            f'target_{q.year}' in tgt.columns else np.nan
        if isinstance(t, pd.Series):
            t = t.iloc[0]
        rec['target'] = t
        rec['achieved_pct'] = round(100 * ytd / t, 0) if pd.notna(ytd) and pd.notna(t) and t > 0 else np.nan
        rows.append(rec)
    out = pd.DataFrame(rows)
    out['_o'] = out['pillar'].astype(str)
    out = out.sort_values('_o', kind='stable').drop(columns='_o').reset_index(drop=True)
    return out, qs


def next_steps(rep, q):
    s = []
    get = lambda name: rep.loc[rep['indicator'] == name, 'year_to_date'].fillna(0).max() if \
        (rep['indicator'] == name).any() else 0
    if get('Vulnerability and coping indicators in use') == 0:
        s.append('Agree vulnerability indicators (e.g. IPC phase, IDP share) and fill aa_config/county_vulnerability.csv.')
    if get('Livelihood zones with exposure analysis') == 0:
        s.append('Add FEWS NET livelihood zones in aa_config/county_livelihood_zones.csv for the zone profile.')
    if get('Counties with validated river trigger levels') == 0:
        s.append('Validate the proposed river trigger levels with SSMS / MWRI (aa_triggers.csv: validated_by, validated_date).')
    if get('Anticipatory action plans validated') == 0:
        s.append('Take the draft anticipatory action plans to the TWG-AA for validation (aa_config/aap_plans.csv).')
    if get('Simulation exercises conducted') == 0:
        s.append('Run a simulation exercise with a pack from aa_p3_simulation.py and record conducted_date.')
    if get('Languages with validated warning templates') <= 1:
        s.append('Translate and validate the warning templates in at least two local languages.')
    if get('Subnational TWG-AA groups active (state / county)') == 0:
        s.append('Register the state TWG-AA groups that exist (aa_config/recipient_groups.csv, active = yes).')
    if get('TWG-AA meetings held') == 0:
        s.append('Log TWG-AA meetings in aa_config/meetings_log.csv so the quarterly-meeting indicator is counted.')
    return s


def _plt():
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        return plt
    except Exception as e:
        print(f"Chart skipped: matplotlib not available ({e}).")
        return None


def plot(rep, q, path):
    """Progress as % of the yearly target (one comparable scale). Indicators without a target are left out."""
    plt = _plt()
    if plt is None:
        return None
    d = rep[rep['achieved_pct'].notna()].copy()
    if d.empty:
        print('Progress chart skipped: no yearly targets filled in aa_config/indicator_targets.csv yet.')
        return None
    d['label'] = 'P' + d['pillar'].astype(str) + '  ' + d['indicator']
    d = d.iloc[::-1]
    shown = d['achieved_pct'].clip(upper=150)
    fig, ax = plt.subplots(figsize=(10, 0.4 * len(d) + 1.5), dpi=140)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.barh(d['label'], shown, color=BAR, height=0.6)
    ax.axvline(100, color=INK, lw=1.2, ls='--')
    ax.text(100, 1.0, ' target', transform=ax.get_xaxis_transform(), fontsize=7.5, color=INK, va='bottom')
    for y, v, ytd, t in zip(d['label'], shown, d['year_to_date'], d['target']):
        ax.text(v, y, f' {ytd:,.0f} of {t:,.0f}', va='center', fontsize=7.5, color=INK)
    ax.set_xlim(0, max(160, shown.max() + 25))
    ax.set_xlabel('% of the target for the year', color=INK2, fontsize=8)
    ax.set_title(f'Roadmap indicators with targets, {q.year} to date ({q})', loc='left', fontsize=11, color=INK)
    ax.grid(axis='x', color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8)
    fig.savefig(path, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)
    return path


def write_md(rep, qs, q, acts, steps, png, path):
    def f(v):
        return '' if pd.isna(v) else (f'{v:,.0f}' if float(v).is_integer() else f'{v:,.2f}')
    lines = [f"# Anticipatory action roadmap - progress report {q}", '',
             f"Prepared {now_utc():%Y-%m-%d %H:%M} UTC by aa_p5_indicator_tracker.py for the quarterly TWG-AA meeting "
             '(South Sudan Roadmap on Anticipatory Action 2025-2030, Pillars 1, 2, 3 and 5).', '',
             'Snapshot indicators show the latest value in the quarter; event indicators are counts in the quarter.', '']
    if png:
        lines += [f"![progress]({os.path.basename(png)})", '']
    names = {'1': 'Pillar 1 - Risk knowledge', '2': 'Pillar 2 - Trigger and early warning systems',
             '3': 'Pillar 3 - Anticipatory action', '5': 'Pillar 5 - Coordination and legal framework'}
    for p in sorted(rep['pillar'].astype(str).unique()):
        sub = rep[rep['pillar'].astype(str) == p]
        lines += [f"## {names.get(p, 'Pillar ' + p)}", '',
                  '| Indicator | ' + ' | '.join(str(x) for x in qs) + ' | Year to date | Target | Achieved | Verification |',
                  '|---|' + '---|' * (len(qs) + 4)]
        for r in sub.to_dict('records'):
            ach = '' if pd.isna(r['achieved_pct']) else f"{r['achieved_pct']:.0f}%"
            lines.append(f"| {r['indicator']} | " + ' | '.join(f(r[str(x)]) for x in qs) +
                         f" | {f(r['year_to_date'])} | {f(r['target'])} | {ach} | {r['verification']} |")
        lines.append('')
    lines += [f"## Plan decisions in {q}"]
    if acts is not None and len(acts):
        lines += ['| Date | Plan | County | Change | Plan status |', '|---|---|---|---|---|']
        for r in acts.itertuples():
            lines.append(f"| {r.time_utc} | {r.plan_id} | {r.county} | {r.from_stage} -> {r.to_stage} | {r.plan_status} |")
    else:
        lines.append('No readiness or activation decisions this quarter.')
    nodata = rep[rep[[str(x) for x in qs]].isna().all(axis=1)]['indicator'].tolist()
    lines += ['', '## No data yet', ', '.join(nodata) if nodata else 'Every indicator has data.', '',
              '## Suggested next steps'] + ([f'- {s}' for s in steps] or ['- Keep the routine running.'])
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return path


def run(quarter=None):
    q = pd.Period(quarter or pd.Timestamp(now_utc().date()), 'Q')
    ledger = read_csv(os.path.join(AA_OUT, 'aa_indicator_ledger.csv'))
    targets = ensure_targets()
    rep, qs = build(q, ledger, derived_values(), targets)
    log = read_csv(os.path.join(AA_OUT, 'aap_activation_log.csv'))
    acts = None
    if log is not None and len(log):
        log['quarter'] = quarter_of(log['time_utc'])
        acts = log[(log['quarter'] == q) & log['to_stage'].isin(['readiness', 'activated'])]
    os.makedirs(AA_OUT, exist_ok=True)
    base = os.path.join(AA_OUT, f'p5_indicator_report_{q}')
    rep.to_csv(base + '.csv', index=False)
    png = plot(rep, q, base + '.png')
    md = write_md(rep, qs, q, acts, next_steps(rep, q), png, base + '.md')
    with open(md, encoding='utf-8') as fh, \
            open(os.path.join(AA_OUT, 'p5_indicator_report_latest.md'), 'w', encoding='utf-8') as out:
        out.write(fh.read())
    return rep, q, base, png, md


def main():
    ap = argparse.ArgumentParser(description='Pillar 5 roadmap indicator tracker')
    ap.add_argument('--quarter', help='e.g. 2026Q4 (default: the current quarter)')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    print('=== AA ADD-ON 7 (PILLAR 5): ROADMAP INDICATOR TRACKER ===')
    rep, q, base, png, md = run(a.quarter)
    show = rep[['pillar', 'indicator', 'year_to_date', 'target', 'achieved_pct']]
    print(show.to_string(index=False))
    for p in (base + '.csv', md, png):
        if p:
            print('->', p)


def selftest():
    global AA_OUT, AA_CONFIG
    import tempfile
    AA_OUT = AA_CONFIG = tempfile.mkdtemp(prefix='aa_trk_')
    led = pd.DataFrame([
        {'run_utc': '2026-07-02 09:30', 'script': 'x', 'pillar': '3', 'activity': 'a', 'indicator': 'AAPs activated',
         'value': 1, 'kind': 'event'},
        {'run_utc': '2026-08-02 09:30', 'script': 'x', 'pillar': '3', 'activity': 'a', 'indicator': 'AAPs activated',
         'value': 1, 'kind': 'event'},
        {'run_utc': '2026-07-01 09:30', 'script': 'x', 'pillar': '1', 'activity': 'a',
         'indicator': 'Counties with a flood risk profile', 'value': 70, 'kind': 'snapshot'},
        {'run_utc': '2026-09-01 09:30', 'script': 'x', 'pillar': '1', 'activity': 'a',
         'indicator': 'Counties with a flood risk profile', 'value': 79, 'kind': 'snapshot'},
        {'run_utc': '2026-04-01 09:30', 'script': 'x', 'pillar': '3', 'activity': 'a', 'indicator': 'AAPs activated',
         'value': 1, 'kind': 'event'}])
    led.to_csv(os.path.join(AA_OUT, 'aa_indicator_ledger.csv'), index=False)
    pd.DataFrame({'date': ['2026-08-15', '2026-09-20'], 'level': ['national', 'state']}).to_csv(
        os.path.join(AA_CONFIG, 'meetings_log.csv'), index=False)
    os.makedirs(os.path.join(AA_OUT, 'simulations', 'SIM-1'))
    pd.DataFrame({'section': ['meta'], 'item': ['conducted_date'], 'target': [''], 'observed': ['2026-09-10'],
                  'notes': ['']}).to_csv(os.path.join(AA_OUT, 'simulations', 'SIM-1', 'evaluation.csv'), index=False)
    ensure_targets()
    t = pd.read_csv(os.path.join(AA_CONFIG, 'indicator_targets.csv'))
    t.loc[t['indicator'] == 'AAPs activated', 'target_2026'] = 4
    t.to_csv(os.path.join(AA_CONFIG, 'indicator_targets.csv'), index=False)
    rep, q, base, png, md = run('2026Q3')
    r = rep.set_index('indicator')
    assert r.loc['AAPs activated', '2026Q3'] == 2 and r.loc['AAPs activated', 'year_to_date'] == 3
    assert r.loc['AAPs activated', 'achieved_pct'] == 75
    assert r.loc['Counties with a flood risk profile', '2026Q3'] == 79, 'snapshot keeps the latest value'
    assert r.loc['TWG-AA meetings held', '2026Q3'] == 2 and r.loc['Simulation exercises conducted', '2026Q3'] == 1
    assert os.path.exists(md)
    import shutil
    shutil.rmtree(AA_OUT, ignore_errors=True)
    print('selftest passed: events summed, snapshots latest, year to date, targets, meetings and exercises counted')


if __name__ == '__main__':
    main()
