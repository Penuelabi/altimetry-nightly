# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 2 - PILLAR 2: TRIGGER AND EARLY WARNING SYSTEMS (thresholds and triggers)
South Sudan Roadmap on Anticipatory Action 2025-2030, Outcome 2: capacity to provide impact-based forecasting and
early warning; activity b "technical guidance and tools for the design of triggers, thresholds ... and data
requirements" and the indicator "hazards with defined thresholds".

What it does
  Turns each county's linked river gauge (county_station_link.csv) into two proposed river-level triggers, with the
  evidence a technical working group needs to accept or change them:
    readiness level   (m)  lower level with a high hit rate: prepare, verify, alert partners
    activation level  (m)  higher level with few false alarms: release pre-agreed funds and act
  Candidate levels are tested against recorded flood impacts:
    monthly  : flood displacement in a county-month (IOM DTM, data/flood_displacement_county_month.csv), with the
               river signal 0, 1 or 2 months earlier, flood season July-January
    seasonal : did the season's highest level cross the level, and was flood displacement recorded that season
  Skill scores: hit rate (POD), false alarm ratio (FAR), critical success index (CSI), true skill statistic (TSS),
  and lead time in days from the first crossing to the first displacement month. Candidates are station-relative
  (percentiles of each station's record; 2-, 5-, 10-year levels from station_status.csv), so the evidence is pooled
  across counties and then converted to metres at each county's own gauge.

  Altimetry samples rivers every 10-35 days, displacement records are incomplete, and the sample is small: the
  output is a PROPOSAL for validation with SSMS, MWRI and the national TWG-AA, never an automatic trigger.

Inputs   merged_altimetry_stations.csv, station_status.csv (ALTIMETRY_OUT_DIR); county_station_link.csv
         (BULLETIN_OUT_DIR, else the repository root); data/flood_displacement_county_month.csv,
         data/flood_affected_county_year.csv; optional county_bulletin_latest.csv and aa_out/p1_county_risk_profile.csv
Outputs  aa_out/aa_triggers.csv (read by aa_p3_aap_engine.py), p2_trigger_skill_monthly.csv,
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
FLOOD_SEASON = (7, 8, 9, 10, 11, 12, 1)       # January belongs to the season that started the previous July
LEADS = (0, 1, 2)                             # months between the river signal and the displacement month
REC_LEAD = 1                                  # lead shown first in the monthly evidence table
READINESS_MIN_POD = 0.60                      # readiness: catch at least 60% of displacement seasons on time ...
ACTIVATION_MAX_FAR = 0.50                     # activation: at most half of activations without recorded displacement
MIN_GAP_M = 0.25                              # activation level at least this far above readiness
ON_TIME_DAYS = 15                             # a crossing up to 15 days after the first displacement month began
                                              # still counts as on time (DTM records are monthly)
DISPLACEMENT_COLS = ['flood', 'natural disaster (unspecified)']
MIN_OBS_PER_YEAR, MIN_YEARS_GUMBEL, EULER = 6, 8, 0.5772156649     # same rules as station_thresholds.py
PCTL_TYPES = (50, 60, 70, 75, 80, 85, 90, 95)  # percentile-of-record candidates
RP_TYPES = [('2yr-0.50m', 'lvl_2yr_m', -0.50), ('2yr-0.25m', 'lvl_2yr_m', -0.25), ('2yr', 'lvl_2yr_m', 0.0),
            ('2yr+0.25m', 'lvl_2yr_m', 0.25), ('5yr', 'lvl_5yr_m', 0.0), ('10yr', 'lvl_10yr_m', 0.0)]
STALE_DAYS = 45
N_PLOTS = 6
ALIASES = {'abyeiadministrativearea': 'abyeiregion'}
SURFACE, INK, INK2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
LINE, READY_C, ACT_C, IMPACT_C = '#2a78d6', '#52514e', '#0b0b0b', '#d03b3b'


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
    df = new[cols] if old is None else pd.concat([old, new[cols]], ignore_index=True)
    dup = pd.DataFrame({'d': text(df['run_utc']).str[:10], 's': df['script'], 'i': df['indicator']}).duplicated(keep='last')
    df = df[~(df['kind'].eq('snapshot') & dup)]
    df.to_csv(path, index=False)
    return path


# =========================================================================== #
# DATA                                                                        #
# =========================================================================== #
def load_levels(path):
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
        ok = text(d['qc_status']).str.lower().eq('ok')
        if ok.mean() > 0.5:
            d = d[ok]
    return d[['station_uid', 'date', 'level']].sort_values(['station_uid', 'date']).reset_index(drop=True)


def gumbel(annual_max, T):
    x = np.asarray(annual_max, float)
    beta = x.std(ddof=1) * np.sqrt(6) / np.pi
    mu = x.mean() - EULER * beta
    return mu - beta * np.log(-np.log(1 - 1.0 / T))


def station_levels(levels, status):
    """2/5/10-year levels from station_status.csv where present, else the same Gumbel rules computed here;
    plus percentiles of each station's own record."""
    st = {}
    if status is not None and 'station_uid' in status:
        for r in status.to_dict('records'):
            if pd.notna(r.get('lvl_2yr_m')):
                st[r['station_uid']] = {'lvl_2yr_m': r['lvl_2yr_m'], 'lvl_5yr_m': r.get('lvl_5yr_m'),
                                        'lvl_10yr_m': r.get('lvl_10yr_m'), 'thr_confidence': r.get('thr_confidence'),
                                        'n_years': r.get('n_years'), 'thr_source': 'station_status.csv'}
    rows = []
    for uid, g in levels.groupby('station_uid'):
        rec = dict(st.get(uid, {}))
        if not rec:
            yearly = g.groupby(g['date'].dt.year)['level'].agg(['max', 'count'])
            yearly = yearly[yearly['count'] >= MIN_OBS_PER_YEAR]
            if len(yearly) >= MIN_YEARS_GUMBEL and yearly['max'].std(ddof=1) > 0:
                lv = sorted(gumbel(yearly['max'], T) for T in (2, 5, 10))
                conf = 'medium' if len(yearly) < 15 else 'high'
            elif len(g) >= 20:
                lv = list(np.percentile(g['level'], (85, 95, 99)))
                conf = 'low'
            else:
                continue
            rec = {'lvl_2yr_m': lv[0], 'lvl_5yr_m': lv[1], 'lvl_10yr_m': lv[2], 'thr_confidence': conf,
                   'n_years': len(yearly), 'thr_source': 'computed here (no station_status.csv row)'}
        rec['station_uid'] = uid
        for p in PCTL_TYPES:
            rec[f'P{p}'] = float(np.percentile(g['level'], p))
        rec['record_start'] = g['date'].min().date().isoformat()
        rec['last_date'] = g['date'].max().date().isoformat()
        rec['last_level_m'] = float(g['level'].iloc[-1])
        rows.append(rec)
    out = pd.DataFrame(rows)
    for name, base, off in RP_TYPES:
        out[name] = pd.to_numeric(out[base], errors='coerce') + off
    return out.set_index('station_uid')


def candidate_types(thr):
    """Candidate names ordered from lowest to highest by their typical height relative to the 2-year level."""
    names = [f'P{p}' for p in PCTL_TYPES] + [n for n, _, _ in RP_TYPES]
    offs = {n: float((pd.to_numeric(thr[n], errors='coerce') - pd.to_numeric(thr['lvl_2yr_m'], errors='coerce')).median())
            for n in names}
    return sorted(names, key=lambda n: offs[n]), offs


def load_events(disp):
    d = disp.copy()
    d['key'] = d['county'].map(ckey)
    cols = [c for c in DISPLACEMENT_COLS if c in d.columns]
    d['n'] = d[cols].apply(pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
    d = d[d['n'] > 0]
    ym = pd.PeriodIndex([pd.Period(year=int(y), month=int(m), freq='M') for y, m in zip(d['year'], d['month'])])
    return set(zip(d['key'], ym)), int(disp['year'].min()), int(disp['year'].max())


def season_of(period):
    return period.year if period.month >= 7 else period.year - 1


def eval_months(y0, y1):
    out = []
    for y in range(y0, y1 + 1):
        for m in FLOOD_SEASON:
            yy = y if m >= 7 else y + 1
            if yy <= y1:
                out.append(pd.Period(year=yy, month=m, freq='M'))
    return out


# =========================================================================== #
# SKILL                                                                       #
# =========================================================================== #
def scores(h, m, f, c):
    pod = h / (h + m) if h + m else np.nan
    far = f / (h + f) if h + f else np.nan
    csi = h / (h + m + f) if h + m + f else np.nan
    pofd = f / (f + c) if f + c else np.nan
    tss = pod - pofd if pd.notna(pod) and pd.notna(pofd) else np.nan
    bias = (h + f) / (h + m) if h + m else np.nan
    return pod, far, csi, tss, bias


def monthly_panel(link, levels, events, y0, y1):
    mm = levels.assign(ym=levels['date'].dt.to_period('M')).groupby(['station_uid', 'ym'])['level'].max()
    rows = []
    months = eval_months(y0, y1)
    for r in link.itertuples():
        for m in months:
            for L in LEADS:
                x = mm.get((r.station_uid, m - L), np.nan)
                if pd.notna(x):
                    rows.append((r.key, r.county, r.station_uid, m, L, x, (r.key, m) in events))
    return pd.DataFrame(rows, columns=['key', 'county', 'station_uid', 'month', 'lead', 'level', 'event'])


def skill_table(panel, thr, types, by='lead'):
    out = []
    for t in types:
        lv = panel['station_uid'].map(thr[t])
        fired = panel['level'] >= lv
        valid = lv.notna()
        for L, g in panel[valid].groupby(by):
            f, e = fired[g.index], g['event']
            h, m = int((f & e).sum()), int((~f & e).sum())
            fa, c = int((f & ~e).sum()), int((~f & ~e).sum())
            pod, far, csi, tss, bias = scores(h, m, fa, c)
            out.append({'candidate': t, by: L, 'n': len(g), 'events': h + m, 'hits': h, 'misses': m,
                         'false_alarms': fa, 'correct_negatives': c, 'POD': pod, 'FAR': far, 'CSI': csi, 'TSS': tss,
                         'bias': bias})
    return pd.DataFrame(out)


def station_seasons(levels):
    """{(station_uid, season): flood-season passes sorted by date}; a season runs July-January."""
    lv = levels[levels['date'].dt.month.isin(FLOOD_SEASON)].copy()
    lv['season'] = np.where(lv['date'].dt.month >= 7, lv['date'].dt.year, lv['date'].dt.year - 1)
    return {k: g[['date', 'level']].reset_index(drop=True) for k, g in lv.groupby(['station_uid', 'season'])}


def first_cross(g, level):
    """Date of the first pass at or above `level` in a season table, or None."""
    if g is None or level is None or not np.isfinite(level):
        return None
    hit = g['level'].to_numpy() >= level
    return g['date'].iloc[int(hit.argmax())] if hit.any() else None


def season_panel(link, seasons, events, affected_years, y0, y1):
    ev_season = {}
    for k, m in events:
        ev_season.setdefault((k, season_of(m)), []).append(m)
    rows = []
    for r in link.itertuples():
        for s in range(y0, y1 + 1):
            g = seasons.get((r.station_uid, s))
            if g is None or g.empty:
                continue
            months = sorted(ev_season.get((r.key, s), []))
            rows.append({'key': r.key, 'county': r.county, 'station_uid': r.station_uid, 'season': s,
                         'season_max_m': float(g['level'].max()), 'event': bool(months),
                         'first_displacement_month': str(months[0]) if months else '',
                         'affected_listed': (r.key, s) in affected_years})
    return pd.DataFrame(rows)


def season_skill(sp, thr, types, seasons):
    """Per candidate and county-season. 'on time': in a displacement season the level must be crossed no later than
    ON_TIME_DAYS after the first displacement month began (a later crossing is a miss: too late to anticipate);
    in other seasons any crossing is a false alarm. 'any time' ignores timing."""
    onset = [pd.Period(m, 'M').start_time if m else None for m in sp['first_displacement_month']]
    tol = pd.Timedelta(days=ON_TIME_DAYS)
    out = []
    for t in types:
        lvl = sp['station_uid'].map(thr[t])
        cross = [first_cross(seasons.get((u, se)), l) for u, se, l in zip(sp['station_uid'], sp['season'], lvl)]
        crossed = pd.Series([c is not None for c in cross], index=sp.index)
        timely = pd.Series([c is not None and o is not None and c <= o + tol for c, o in zip(cross, onset)],
                           index=sp.index)
        leads = [(o - c).days for c, o, ok in zip(cross, onset, timely) if ok]
        variants = (('flood displacement', 'on time', sp['event'], timely.where(sp['event'], crossed)),
                    ('flood displacement', 'any time in season', sp['event'], crossed),
                    ('displacement or listed in flood assessment', 'any time in season',
                     sp['event'] | sp['affected_listed'], crossed))
        for definition, timing, ev, fired in variants:
            ok = lvl.notna()
            f, e = fired[ok].astype(bool), ev[ok].astype(bool)
            h, m = int((f & e).sum()), int((~f & e).sum())
            fa, c = int((f & ~e).sum()), int((~f & ~e).sum())
            pod, far, csi, tss, bias = scores(h, m, fa, c)
            out.append({'impact_definition': definition, 'timing': timing, 'candidate': t,
                        'county_seasons': int(ok.sum()), 'events': h + m, 'hits': h, 'misses': m,
                        'false_alarms': fa, 'correct_negatives': c, 'POD': pod, 'FAR': far, 'CSI': csi, 'TSS': tss,
                        'median_lead_days': float(np.median(leads)) if (timing == 'on time' and leads) else np.nan})
    return pd.DataFrame(out)


def choose(skill_s, order, offs):
    """Uses the season table, impact = flood displacement, timing = on time (what an anticipatory plan needs).
    Activation first (the funding decision): best CSI among candidates with FAR <= ACTIVATION_MAX_FAR, else the
    lowest FAR. Readiness: a LOWER candidate that catches at least as many displacement seasons on time (POD >= the
    larger of READINESS_MIN_POD and the activation POD), best TSS: earlier warning, more false alarms."""
    s = skill_s[(skill_s['impact_definition'] == 'flood displacement') & (skill_s['timing'] == 'on time')]
    s = s.set_index('candidate').reindex(order)
    s = s[s['events'] > 0]
    if s.empty:
        return '2yr-0.25m', '2yr', 'no displacement seasons to test; default 2-year rule used'
    good = s[s['FAR'] <= ACTIVATION_MAX_FAR]
    if len(good) and good['CSI'].notna().any():
        act, why = good['CSI'].idxmax(), f'best CSI among levels with FAR <= {ACTIVATION_MAX_FAR:.0%}'
    else:
        act = s.sort_values(['FAR', 'POD'], ascending=[True, False]).index[0]
        why = f'no level kept FAR <= {ACTIVATION_MAX_FAR:.0%}; the lowest FAR was used'
    lower = s[[offs[c] < offs[act] for c in s.index]]
    need = max(READINESS_MIN_POD, float(s.loc[act, 'POD']) if pd.notna(s.loc[act, 'POD']) else 0.0)
    okr = lower[lower['POD'] >= need]
    if len(okr) and okr['TSS'].notna().any():
        best = okr['TSS'].max()
        ready = [c for c in okr.index if okr.loc[c, 'TSS'] == best][-1]     # highest of equally skilful levels
    elif len(lower):
        ready = lower['POD'].idxmax()
    else:
        ready = act
        why += '; no lower level, readiness = activation minus the gap'
    return ready, act, why


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


def plot_hydrographs(trig, levels, events, out_png, years=6):
    plt = _plt()
    if plt is None or trig.empty:
        return None
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    rows = trig.head(N_PLOTS)
    n = len(rows)
    fig, axes = plt.subplots(n, 1, figsize=(10, 2.15 * n + 0.9), dpi=140, sharex=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    t1 = levels['date'].max()
    t0 = t1 - pd.DateOffset(years=years)
    for ax, r in zip(axes[:, 0], rows.itertuples()):
        ax.set_facecolor(SURFACE)
        g = levels[(levels['station_uid'] == r.station_uid) & (levels['date'] >= t0)]
        for k, m in events:
            if k == ckey(r.county) and m.start_time >= t0:
                ax.axvspan(m.start_time, m.end_time, color=IMPACT_C, alpha=0.14, lw=0)
        ax.plot(g['date'], g['level'], color=LINE, lw=1.6, marker='o', ms=2.2)
        ax.axhline(r.readiness_level_m, color=READY_C, lw=1.1, ls='--')
        ax.axhline(r.activation_level_m, color=ACT_C, lw=1.1, ls='-.')
        ax.text(1.003, r.readiness_level_m, 'readiness', transform=ax.get_yaxis_transform(), fontsize=7,
                color=INK2, va='center')
        ax.text(1.003, r.activation_level_m, 'activation', transform=ax.get_yaxis_transform(), fontsize=7,
                color=INK, va='center')
        ax.set_title(f"{r.county} ({r.state}) - gauge {r.station_name or r.station_uid}, {r.relation}",
                     fontsize=9, color=INK, loc='left')
        ax.grid(axis='y', color=GRID, lw=0.6)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        ax.tick_params(colors=INK2, labelsize=7)
        ax.set_ylabel('m', color=INK2, fontsize=8)
    handles = [Line2D([], [], color=LINE, lw=1.6, marker='o', ms=3, label='water level (satellite passes)'),
               Line2D([], [], color=READY_C, ls='--', label='proposed readiness level'),
               Line2D([], [], color=ACT_C, ls='-.', label='proposed activation level'),
               Patch(color=IMPACT_C, alpha=0.25, label='month with flood displacement recorded')]
    fig.legend(handles=handles, loc='upper left', ncol=4, frameon=False, fontsize=8, bbox_to_anchor=(0.01, 1.0))
    fig.tight_layout(rect=(0, 0, 0.97, 1 - 0.55 / (2.15 * n + 0.9)))
    fig.savefig(out_png, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)
    return out_png


def md_table(df, cols, fmt=None):
    fmt = fmt or {}
    lines = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    for r in df[cols].itertuples(index=False):
        cells = []
        for c, v in zip(cols, r):
            if c in fmt and pd.notna(v):
                cells.append(fmt[c].format(v))
            else:
                cells.append('' if (isinstance(v, float) and np.isnan(v)) else str(v))
        lines.append('| ' + ' | '.join(cells) + ' |')
    return lines


def write_note(path, ready, act, why, skill_m, skill_s, trig, y0, y1, n_events):
    pct = {'POD': '{:.0%}', 'FAR': '{:.0%}', 'CSI': '{:.2f}', 'TSS': '{:.2f}'}
    rec = skill_m[skill_m['lead'] == REC_LEAD].copy()
    lines = ['# River-level triggers - design note (proposal for validation)', '',
             f"Generated {now_utc():%Y-%m-%d %H:%M} UTC by aa_p2_trigger_scorecard.py "
             '(Roadmap on Anticipatory Action, Pillar 2: Trigger and Early Warning Systems).', '',
             '## Proposed rule',
             f"- **Activation**: water level at the county's gauge at or above its **{act}** level ({why}).",
             f"- **Readiness**: at or above its **{ready}** level (a lower level that caught at least "
             f"{READINESS_MIN_POD:.0%} of displacement seasons on time, and at least as many as activation; best TSS).",
             f"- On time = crossed no later than {ON_TIME_DAYS} days after the first displacement month began. "
             'Both levels are judged per flood season (July-January), as a plan activates once per season.',
             '- Levels in metres for every county are in aa_triggers.csv.', '']
    chosen = skill_s[(skill_s['impact_definition'] == 'flood displacement') & (skill_s['timing'] == 'on time') &
                     skill_s['candidate'].isin([ready, act])]
    weak = chosen[~(chosen['TSS'] > 0)]['candidate'].tolist()
    if weak:
        lines += [f"> **Warning:** {', '.join(weak)} shows no skill over chance in this record (TSS <= 0). Treat the "
                  'level as a placeholder until SSMS/MWRI and the TWG-AA agree a level from local flood marks or '
                  'bankfull data.', '']
    lines += ['## Evidence',
             f"Impact record: {n_events} county-months with flood displacement, {y0}-{y1} (IOM DTM; flood + "
             'unspecified natural disaster). River signal: satellite levels at the linked gauge.', '',
             '### Per season, on time (used for the choice)']
    on = skill_s[(skill_s['impact_definition'] == 'flood displacement') & (skill_s['timing'] == 'on time')]
    lines += md_table(on, ['candidate', 'county_seasons', 'events', 'hits', 'misses', 'false_alarms', 'POD', 'FAR',
                           'CSI', 'TSS', 'median_lead_days'], pct | {'median_lead_days': '{:.0f}'})
    lines += ['', '### Per season, other impact definitions (chosen levels)']
    ss = skill_s[skill_s['candidate'].isin([ready, act]) & (skill_s['timing'] != 'on time')]
    lines += md_table(ss, ['impact_definition', 'timing', 'candidate', 'county_seasons', 'events', 'hits', 'misses',
                           'false_alarms', 'POD', 'FAR', 'CSI'], pct)
    lines += ['', f"### Monthly (flood-season county-months, river signal {REC_LEAD} month earlier)",
              'Monthly scores look poor by design: a level stays high for months while displacement is recorded in '
              'one or two of them. Use them to compare lead times, not to judge a level.']
    lines += md_table(rec, ['candidate', 'n', 'events', 'hits', 'misses', 'false_alarms', 'POD', 'FAR', 'CSI', 'TSS'], pct)
    near = trig[trig['current_state'].isin(['activation', 'readiness'])]
    names = [f"{r.county} ({r.current_state})" for r in near.itertuples()]
    more = f" and {len(names) - 15} more (see aa_triggers.csv)" if len(names) > 15 else ''
    lines += ['', f"## Status now: {len(near)} counties at or above a proposed level",
              (', '.join(names[:15]) + more) if names else 'none', '',
              '## How to read and validate',
              '- POD: share of displacement months the level caught. FAR: share of crossings with no displacement '
              'recorded. CSI and TSS combine both; higher is better. Lead time: days from first crossing to the first '
              'displacement month (see p2_trigger_track_record.csv).',
              '- Small samples: one or two seasons can swing the numbers. Prefer rules that also make physical sense '
              '(bankfull levels known to MWRI, local flood marks).',
              '- Satellite levels are sampled every 10-35 days, so a peak can be missed; displacement records miss '
              'floods where nobody moved or nobody counted.',
              '- Confirm per county with SSMS / MWRI and the state TWG-AA; record the decision (date, who, levels) in '
              'aa_triggers.csv (columns validated_by, validated_date) before using the levels in an anticipatory action '
              'plan.']
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return path


# =========================================================================== #
# MAIN                                                                        #
# =========================================================================== #
def run(levels, status, link, disp, affected, today=None):
    today = pd.Timestamp(today or now_utc().date())
    thr = station_levels(levels, status)
    order, offs = candidate_types(thr)
    events, y0, y1 = load_events(disp)
    lk = link.copy()
    lk['key'] = lk['county'].map(ckey)
    lk = lk[text(lk['station_uid']).ne('') & lk['station_uid'].isin(thr.index)]
    aff = set()
    if affected is not None:
        a = affected[pd.to_numeric(affected['affected'], errors='coerce') > 0]
        aff = set(zip(a['county'].map(ckey), a['year'].astype(int)))
    panel = monthly_panel(lk, levels, events, y0, y1)
    skill_m = skill_table(panel, thr, order) if len(panel) else pd.DataFrame()
    seasons = station_seasons(levels)
    sp = season_panel(lk, seasons, events, aff, y0, y1)
    skill_s = season_skill(sp, thr, order, seasons) if len(sp) else pd.DataFrame()
    ready, act, why = choose(skill_s, order, offs) if len(skill_s) else ('2yr-0.25m', '2yr', 'no season data')

    by_st = {u: g for u, g in levels.groupby('station_uid')}
    trig_rows, track = [], []
    for r in lk.itertuples():
        t = thr.loc[r.station_uid]
        rl, al = float(t[ready]), float(t[act])
        note = ''
        if not np.isfinite(al) and not np.isfinite(rl):
            continue
        if not np.isfinite(rl) or ready == act:
            rl, note = al - MIN_GAP_M, f'readiness set {MIN_GAP_M} m below activation'
        elif not np.isfinite(al) or al < rl + MIN_GAP_M:
            al, note = rl + MIN_GAP_M, f'activation set {MIN_GAP_M} m above readiness'
        g = by_st[r.station_uid]
        last_d, last_l = g['date'].iloc[-1], float(g['level'].iloc[-1])
        age = int((today - last_d.normalize()).days)
        state = 'stale' if age > STALE_DAYS else ('activation' if last_l >= al else 'readiness' if last_l >= rl else 'below')
        sub = sp[sp['key'] == r.key]
        h = m_ = fa = 0
        leads = []
        for s in sub.itertuples():
            gs = seasons.get((r.station_uid, s.season))
            cr, ca = first_cross(gs, rl), first_cross(gs, al)
            ev0 = pd.Period(s.first_displacement_month, 'M').start_time if s.first_displacement_month else None
            lead_r = (ev0 - cr).days if ev0 is not None and cr is not None else np.nan
            lead_a = (ev0 - ca).days if ev0 is not None and ca is not None else np.nan
            on_time = ca is not None and ev0 is not None and ca <= ev0 + pd.Timedelta(days=ON_TIME_DAYS)
            out = ('hit' if s.event and on_time else 'late' if s.event and ca is not None else 'miss' if s.event else
                   'false alarm' if ca is not None else 'correct negative')
            h += out == 'hit'
            m_ += out in ('miss', 'late')
            fa += out == 'false alarm'
            if out == 'hit' and pd.notna(lead_a):
                leads.append(lead_a)
            track.append({'county': r.county, 'state': getattr(r, 'state', ''), 'station_uid': r.station_uid,
                          'season': f"{s.season}-{str(s.season + 1)[-2:]}", 'season_max_m': round(s.season_max_m, 3),
                          'readiness_level_m': round(rl, 3), 'activation_level_m': round(al, 3),
                          'first_readiness_crossing': '' if cr is None else cr.date().isoformat(),
                          'first_activation_crossing': '' if ca is None else ca.date().isoformat(),
                          'flood_displacement': s.event, 'first_displacement_month': s.first_displacement_month,
                          'listed_in_flood_assessment': s.affected_listed,
                          'lead_days_readiness': lead_r, 'lead_days_activation': lead_a, 'outcome_activation': out})
        trig_rows.append({
            'county': r.county, 'state': getattr(r, 'state', ''), 'station_uid': r.station_uid,
            'station_name': getattr(r, 'station_name', ''), 'relation': getattr(r, 'relation', ''),
            'link_confidence': getattr(r, 'confidence', ''), 'readiness_rule': ready, 'activation_rule': act,
            'readiness_level_m': round(rl, 3), 'activation_level_m': round(al, 3),
            'lvl_2yr_m': round(float(t['lvl_2yr_m']), 3), 'lvl_5yr_m': round(float(t['lvl_5yr_m']), 3),
            'lvl_10yr_m': round(float(t['lvl_10yr_m']), 3), 'thr_confidence': t.get('thr_confidence'),
            'thr_source': t.get('thr_source'), 'record_start': t.get('record_start'),
            'last_date': last_d.date().isoformat(), 'last_level_m': round(last_l, 3), 'days_since_obs': age,
            'current_state': state, 'seasons_tested': len(sub), 'hits_on_time': h, 'misses_or_late': m_,
            'false_alarms': fa,
            'median_lead_days': float(np.median(leads)) if leads else np.nan, 'note': note,
            'status': 'proposed - validate with SSMS/MWRI and TWG-AA', 'validated_by': '', 'validated_date': ''})
    trig = pd.DataFrame(trig_rows)
    return trig, pd.DataFrame(track), skill_m, skill_s, (ready, act, why), events, (y0, y1), thr


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
    levels = load_levels(mpath)
    status = read_csv(os.path.join(ALT_DIR, 'station_status.csv'))
    link = read_csv(lpath)
    affected = read_csv(os.path.join(DATA_DIR, 'flood_affected_county_year.csv'))
    print(f"{levels['station_uid'].nunique()} stations, {len(levels):,} passes; {len(link)} county links ({lpath})")

    trig, track, skill_m, skill_s, (ready, act, why), events, (y0, y1), thr = run(levels, status, link, disp, affected)
    risk = read_csv(os.path.join(AA_OUT, 'p1_county_risk_profile.csv'))
    if risk is not None and len(trig):
        trig = trig.merge(risk[['county', 'risk_rank', 'risk_class']], on='county', how='left')
        trig = trig.sort_values(['risk_rank', 'county'], na_position='last')
    else:
        trig = trig.sort_values(['hits_on_time', 'county'], ascending=[False, True])
    out = {k: os.path.join(AA_OUT, v) for k, v in {
        'trig': 'aa_triggers.csv', 'sm': 'p2_trigger_skill_monthly.csv', 'ss': 'p2_trigger_skill_season.csv',
        'tr': 'p2_trigger_track_record.csv', 'note': 'p2_trigger_design_note.md',
        'png': 'p2_trigger_hydrographs.png'}.items()}
    old = read_csv(out['trig'])
    if old is not None and 'validated_by' in old:          # keep validation records already entered
        keep = old[text(old['validated_by']).ne('')][['county', 'validated_by', 'validated_date',
                                                      'readiness_level_m', 'activation_level_m']]
        if len(keep):
            keep = keep.rename(columns={'readiness_level_m': 'r_v', 'activation_level_m': 'a_v'})
            trig = trig.drop(columns=['validated_by', 'validated_date']).merge(keep, on='county', how='left')
            v = text(trig['validated_by']).ne('')
            trig.loc[v, 'readiness_level_m'] = trig.loc[v, 'r_v']
            trig.loc[v, 'activation_level_m'] = trig.loc[v, 'a_v']
            trig.loc[v, 'status'] = 'validated (levels kept as entered)'
            trig = trig.drop(columns=['r_v', 'a_v'])
            print(f"Kept {int(v.sum())} validated county levels")
    trig.to_csv(out['trig'], index=False)
    skill_m.round(3).to_csv(out['sm'], index=False)
    skill_s.round(3).to_csv(out['ss'], index=False)
    track.to_csv(out['tr'], index=False)
    write_note(out['note'], ready, act, why, skill_m, skill_s, trig, y0, y1, len(events))
    png = plot_hydrographs(trig[trig['hits_on_time'] + trig['misses_or_late'] > 0] if len(trig) else trig,
                           levels, events, out['png'])

    hazards = {'riverine flood (river level)'}
    bul = read_csv(os.path.join(BUL_DIR, 'county_bulletin_latest.csv'))
    if bul is not None and 'alert_hazard' in bul:
        hazards |= {h for h in text(bul['alert_hazard']).unique() if h and h != 'n/a'}
    rec = skill_s[(skill_s['impact_definition'] == 'flood displacement') & (skill_s['timing'] == 'on time') &
                  skill_s['candidate'].isin([ready, act])].set_index('candidate')
    log_indicators([
        dict(pillar='2', activity='Develop technical guidance and tools for triggers and thresholds',
             indicator='Hazards with defined thresholds and data requirements', value=len(hazards), kind='snapshot',
             unit='hazards', verification='p2_trigger_design_note.md; county bulletin advisory rules',
             note='; '.join(sorted(hazards))),
        dict(pillar='2', activity='Develop technical guidance and tools for triggers and thresholds',
             indicator='Counties with proposed river trigger levels', value=len(trig), kind='snapshot',
             unit='counties', verification='aa_triggers.csv'),
        dict(pillar='2', activity='Develop technical guidance and tools for triggers and thresholds',
             indicator='Counties with validated river trigger levels',
             value=int(text(trig['validated_by']).ne('').sum()) if len(trig) else 0, kind='snapshot',
             unit='counties', verification='aa_triggers.csv (validated_by, validated_date)'),
        dict(pillar='2', activity='Map hazards, vulnerabilities and impacts to inform IbF and AA protocols',
             indicator='Trigger skill evaluations against recorded impacts', value=1, kind='event', unit='evaluations',
             verification='p2_trigger_skill_season.csv; p2_trigger_track_record.csv',
             note=(f"readiness {ready} POD {rec.loc[ready, 'POD']:.0%} FAR {rec.loc[ready, 'FAR']:.0%}; activation "
                   f"{act} POD {rec.loc[act, 'POD']:.0%} FAR {rec.loc[act, 'FAR']:.0%}")
             if ready in rec.index and act in rec.index else ''),
    ], 'aa_p2_trigger_scorecard.py')

    print(f"Proposed: readiness = {ready}, activation = {act} ({why}); per season, on time:")
    if ready in rec.index and act in rec.index:
        for c in (ready, act):
            r = rec.loc[c]
            print(f"  {c:>10}: POD {r['POD']:.0%}  FAR {r['FAR']:.0%}  CSI {r['CSI']:.2f}  TSS {r['TSS']:.2f} "
                  f"({int(r['hits'])} hits, {int(r['misses'])} misses, {int(r['false_alarms'])} false alarms)")
            if not r['TSS'] > 0:
                print(f"  WARNING: {c} shows no skill over chance in this record (TSS {r['TSS']:.2f}); validate locally.")
    print(f"Counties now: {trig['current_state'].value_counts().to_dict()}")
    for k in ('trig', 'sm', 'ss', 'tr', 'note'):
        print('->', out[k])
    if png:
        print('->', png)


def selftest():
    rng = np.random.default_rng(3)
    days = pd.date_range('2016-01-05', '2025-12-31', freq='11D')
    wet = {2019, 2020, 2021, 2022, 2024}
    rows = []
    for uid, base in (('dahiti:1', 400.0), ('dahiti:2', 380.0)):
        for d in days:
            seas = 1.2 * np.exp(-((d.dayofyear - 260) / 45.0) ** 2)
            boost = 0.9 if d.year in wet and 200 < d.dayofyear < 340 else 0.0
            rows.append({'station_uid': uid, 'date': d, 'level': base + seas + boost + rng.normal(0, 0.05)})
    levels = pd.DataFrame(rows)
    link = pd.DataFrame({'county': ['A', 'B'], 'state': ['S', 'S'], 'station_uid': ['dahiti:1', 'dahiti:2'],
                         'station_name': ['g1', 'g2'], 'relation': ['local', 'upstream'], 'confidence': ['high', 'high']})
    disp = pd.DataFrame([{'county': c, 'year': y, 'month': 10, 'flood': 1000, 'natural disaster (unspecified)': 0}
                         for c in ('A', 'B') for y in (2020, 2021, 2022, 2024)] +
                        [{'county': 'A', 'year': 2023, 'month': 3, 'flood': 0, 'natural disaster (unspecified)': 0}])
    trig, track, sm, ss, (ready, act, why), ev, yrs, thr = run(levels, None, link, disp, None,
                                                               today=pd.Timestamp('2026-01-10'))
    assert len(trig) == 2 and (trig['activation_level_m'] >= trig['readiness_level_m'] + MIN_GAP_M - 1e-9).all()
    order, offs = candidate_types(thr)
    assert offs[ready] < offs[act], 'readiness must sit below activation'
    r = ss[(ss['timing'] == 'on time') & (ss['impact_definition'] == 'flood displacement') &
           (ss['candidate'] == ready)].iloc[0]
    assert r['POD'] >= READINESS_MIN_POD, 'readiness must meet the minimum on-time hit rate on clean synthetic data'
    a = ss[(ss['impact_definition'] == 'flood displacement') & (ss['timing'] == 'any time in season') &
           (ss['candidate'] == act)].iloc[0]
    assert a['POD'] >= 0.75 and a['FAR'] <= 0.25, f'activation should separate wet seasons: {a.to_dict()}'
    assert set(track['outcome_activation']) <= {'hit', 'late', 'miss', 'false alarm', 'correct negative'}
    assert scores(5, 5, 0, 10)[0] == 0.5 and scores(5, 0, 5, 10)[1] == 0.5
    print(f'selftest passed: readiness {ready}, activation {act}; season POD {a["POD"]:.0%} FAR {a["FAR"]:.0%}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Pillar 2 river trigger scorecard')
    ap.add_argument('--selftest', action='store_true', help='check the scoring on synthetic data and exit')
    a = ap.parse_args()
    selftest() if a.selftest else main()
