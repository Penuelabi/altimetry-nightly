# -*- coding: utf-8 -*-
"""
Daily and weekly email briefs (HTML + plain text) built from county_bulletin_latest.json,
station_status.csv and merged_altimetry_stations.csv.

Daily : 3 drought-watch counties, 3 flood-watch counties, river trigger, gauge watch list, towns to monitor.
Weekly: forecast confidence, priorities for the next 2 weeks, climate/flood news (ReliefWeb, if reachable).

Pure functions, no SMTP here (send_digest.py sends).
"""
import datetime
import html
import json
import os
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

APP_URL = 'https://penuelabi.users.earthengine.app/view/south-sudan-weather-forecast'
SIGNATURE_LINES = [
    'ALLAU, Denis Abi, PhD',
    'Abuk Project',
    'Mayardit Academy for Space Sciences',
    ('University of Juba and University of California, Davis',
     'https://globalaffairs.ucdavis.edu/news/exploring-complex-social-ecological-systems'),
    'WhatsApp: +211 917 939 818',
    ('Email: penuelabi@gmail.com', 'mailto:penuelabi@gmail.com'),
]
LEVEL_COLOR = {'red': '#c62828', 'orange': '#ef6c00', 'yellow': '#f9a825', 'green': '#2e7d32'}
LEVEL_ORDER = ['green', 'yellow', 'orange', 'red']

# town / place -> county of the bulletin
TOWNS = [('Juba', 'Juba'), ('Mangalla', 'Terekeka'), ('Bor / Jalle', 'Bor South'), ('Panyijiar', 'Panyijiar'),
         ('Duk Padiet', 'Duk'), ('Adok', 'Leer'), ('Ayod', 'Ayod'), ('Fangak', 'Fangak'), ('Lankien', 'Nyirol'),
         ('Pibor', 'Pibor'), ('Akobo', 'Akobo'), ('Canal/Pigi', 'Canal/Pigi'), ('Malakal', 'Malakal'),
         ('Fashoda', 'Fashoda'), ('Aweil', 'Aweil Centre'), ('Mayom', 'Mayom'), ('Bentiu', 'Rubkona'),
         ('Guit', 'Guit')]
# gauge stations the project already watches (numeric station ids, any source); marked with a star
WATCH_IDS = {107879, 106716, 100905, 112211, 101187, 16098, 967, 15556, 7854, 7966, 7894, 7889, 7960, 7883,
             17752, 17750, 17749, 7887, 15557, 7880, 7879}
LEVEL_COL = 'Water Surface Elevation - values(m)'


def _f(v, nd=0, default='n/a'):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    return f'{v:,.{nd}f}'


def county_frame(doc):
    rows = []
    for c in doc['counties']:
        a, o, e = c.get('antecedent', {}), c.get('outlook', {}), c.get('exposure', {})
        w1, w2 = o.get('week1_rain_median_mm'), o.get('week2_rain_median_mm')
        rows.append(dict(
            county=c['county'], state=c['state'], level=(c.get('alert') or {}).get('level'),
            hazard=(c.get('alert') or {}).get('hazard'),
            sm_z=a.get('sm_rootzone_z'), sm_pct=a.get('sm_rootzone_pctile'), deficit=a.get('soil_deficit_mm'),
            soil_class=a.get('soil_rootzone_class'), rain30=a.get('rain_30d_mm'), rain30_pct=a.get('rain_30d_pct_of_normal'),
            wb30=a.get('wb_30d_mm'), runoff_class=a.get('runoff_30d_class'),
            rain2w=(w1 or 0) + (w2 or 0) if (w1 is not None or w2 is not None) else np.nan,
            p_heavy=o.get('p_heavy_50mm_week1'), p_dry=o.get('p_dry_spell_7d'),
            pop=e.get('population'), pop_flood=e.get('population_on_flood_prone_ground'),
            cropland=e.get('cropland_km2')))
    df = pd.DataFrame(rows)
    for c in df.columns.difference(['county', 'state', 'level', 'hazard', 'soil_class', 'runoff_class']):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def drought_watch(df, n=3):
    """Lowest root-zone soil moisture that the coming 2 weeks of rain will not fix."""
    d = df.dropna(subset=['sm_z']).copy()
    d['score'] = d['sm_z'].rank(ascending=True) + d['rain2w'].fillna(d['rain2w'].median()).rank(ascending=True) \
        + d['p_dry'].fillna(0).rank(ascending=False) * 0.5
    return d.sort_values('score').head(n)


def flood_watch(df, trigger=None, n=3):
    """Wet soil + water surplus + heavy rain ahead, weighted by people living on flood-prone ground."""
    d = df.dropna(subset=['sm_z']).copy()
    wet = d['sm_z'].rank(ascending=False) + d['wb30'].fillna(d['wb30'].median()).rank(ascending=False) \
        + d['rain2w'].fillna(0).rank(ascending=False) + d['p_heavy'].fillna(0).rank(ascending=False)
    d['score'] = wet + d['pop_flood'].fillna(0).rank(ascending=False) * 0.5
    return d.sort_values('score').head(n)


def gauge_watch(merged_csv, status_csv=None, today=None, max_rows=12):
    """Stations where the water takes > 5 days to reach the next station downstream and the last pass is newer
    than that travel time, so there is still time to warn the downstream counties."""
    cols = ['station_uid', 'date', LEVEL_COL, 'Lag Days', 'location/river_name', 'Station After_this_station']
    hdr = pd.read_csv(merged_csv, nrows=0).columns
    use = [c for c in cols if c in hdr]
    if 'Lag Days' not in use or LEVEL_COL not in use:
        return pd.DataFrame()
    df = pd.read_csv(merged_csv, usecols=use, low_memory=False)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df[LEVEL_COL] = pd.to_numeric(df[LEVEL_COL], errors='coerce')
    df = df.dropna(subset=['date', LEVEL_COL])
    df['uid'] = df['station_uid'].astype(str)
    sid = pd.to_numeric(df['uid'].str.split(':').str[-1], errors='coerce')
    today = pd.Timestamp(today or pd.Timestamp.now('UTC').tz_localize(None)).normalize()
    thr = None
    if status_csv and os.path.exists(status_csv) and os.path.getsize(status_csv) > 50:
        thr = pd.read_csv(status_csv).set_index('station_uid')
    rows = []
    for uid, g in df.groupby('uid'):
        lag = pd.to_numeric(g['Lag Days'], errors='coerce').median()
        if not (lag > 5):
            continue
        g = g.sort_values('date')
        last3 = g.tail(3)
        age = (today - last3['date'].iloc[-1]).days
        if age >= lag:
            continue
        lv = last3[LEVEL_COL].to_numpy()
        trend = float(lv[-1] - lv[0]) if len(lv) >= 2 else np.nan
        rec = dict(uid=uid, station_id=int(sid[g.index[0]]) if pd.notna(sid[g.index[0]]) else None,
                   river=g['location/river_name'].iloc[-1], last_date=last3['date'].iloc[-1].date().isoformat(),
                   age_days=int(age), level=float(lv[-1]), trend_m=trend, lag_days=float(lag),
                   days_to_warn=float(lag - age),
                   downstream=(g['Station After_this_station'].iloc[-1] if 'Station After_this_station' in g else None),
                   star=bool(WATCH_IDS & {int(sid[g.index[0]])} if pd.notna(sid[g.index[0]]) else False))
        if thr is not None and uid in thr.index:
            t = thr.loc[uid]
            rec['lvl_2yr'] = t.get('lvl_2yr_m')
            rec['vs_2yr'] = rec['level'] - float(t.get('lvl_2yr_m')) if pd.notna(t.get('lvl_2yr_m')) else np.nan
            rec['status'] = t.get('flood_status')
        rows.append(rec)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out['rising'] = out['trend_m'] > 0.02
    # keep the starred stations plus those within 0.3 m of the 2-yr level or rising
    keep = out['star'] | out['rising'] | (out.get('vs_2yr', pd.Series(-9, index=out.index)).fillna(-9) > -0.3)
    out = out[keep].sort_values(['days_to_warn', 'age_days'], ascending=[True, True])
    return out.head(max_rows)


# ----------------------------------------------------------------------------------------------
def _signature_html():
    parts = []
    for ln in SIGNATURE_LINES:
        if isinstance(ln, tuple):
            parts.append(f'<a href="{html.escape(ln[1])}">{html.escape(ln[0])}</a>')
        else:
            parts.append(html.escape(ln))
    return '<br>'.join(parts)


def _signature_text():
    return '\n'.join(ln[0] + f' ({ln[1]})' if isinstance(ln, tuple) else ln for ln in SIGNATURE_LINES)


def _badge(level):
    c = LEVEL_COLOR.get(level, '#777')
    return f'<span style="background:{c};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">{html.escape(str(level or "n/a").upper())}</span>'


def _table(headers, rows, widths=None):
    th = ''.join(f'<th style="text-align:left;padding:3px 6px;background:#eceff1;font-size:12px">{html.escape(h)}</th>' for h in headers)
    trs = ''.join('<tr>' + ''.join(f'<td style="padding:3px 6px;border-bottom:1px solid #eee;font-size:12px">{c}</td>' for c in r) + '</tr>' for r in rows)
    return f'<table style="border-collapse:collapse;width:100%"><tr>{th}</tr>{trs}</table>'


def _footer(subscribe_url, unsubscribe_to):
    unsub = (os.environ.get('UNSUBSCRIBE_URL') or '').strip()
    stop_h = (f'. To stop receiving it, <a href="{html.escape(unsub)}">unsubscribe here</a>.' if unsub
              else '. To stop receiving it, reply with "unsubscribe".')
    stop_t = f'unsubscribe: {unsub}' if unsub else 'reply "unsubscribe" to stop'
    h = (f'<p style="font-size:12px">Open the live map: <a href="{APP_URL}">{APP_URL}</a></p>'
         + (f'<p style="font-size:12px">Subscribe to the email list: <a href="{html.escape(subscribe_url)}">{html.escape(subscribe_url)}</a>'
            f'{stop_h}</p>' if subscribe_url else
            f'<p style="font-size:12px">To join or leave this list, reply to {html.escape(unsubscribe_to)}.</p>')
         + f'<p style="font-size:13px">{_signature_html()}</p>')
    t = (f'\nLive map: {APP_URL}\n'
         + (f'Subscribe to the email list: {subscribe_url} ({stop_t})\n' if subscribe_url else '')
         + '\n' + _signature_text() + '\n')
    return h, t


def build_daily(doc, gauges=None, subscribe_url='', reply_to='penuelabi@gmail.com', today=None):
    df = county_frame(doc)
    trig = doc.get('sudd_river_trigger') or {}
    dw, fw = drought_watch(df), flood_watch(df, trig)
    run = doc.get('ecmwf_run_utc') or 'n/a'
    counts = {k: int((df.level == k).sum()) for k in LEVEL_ORDER}
    date = (today or datetime.datetime.utcnow()).strftime('%d %b %Y')
    subject = (f"South Sudan hydro-climate watch {date}: {counts['red']} red, {counts['orange']} orange, "
               f"{counts['yellow']} yellow counties")

    # --- drought
    drows = [[f"<b>{html.escape(r.county)}</b> ({html.escape(r.state)})", _badge(r.level), _f(r.sm_z, 2),
              _f(r.deficit, 0) + ' mm', _f(r.rain2w, 0) + ' mm', _f(r.p_dry * 100 if pd.notna(r.p_dry) else np.nan, 0) + '%']
             for r in dw.itertuples()]
    dh = _table(['County', 'Alert', 'Soil z', 'Soil deficit', 'Rain next 2 wk (median)', 'Chance 7-day dry spell'], drows)
    dt = ['Drought watch (lowest root-zone soil moisture that the next 2 weeks of rain will not fix):'] + [
        f"  {i}. {r.county} ({r.state}) soil z {_f(r.sm_z, 2)}, deficit {_f(r.deficit)} mm, next 2 wk rain {_f(r.rain2w)} mm"
        for i, r in enumerate(dw.itertuples(), 1)]
    # --- flood
    frows = [[f"<b>{html.escape(r.county)}</b> ({html.escape(r.state)})", _badge(r.level), _f(r.sm_z, 2),
              _f(r.wb30, 0) + ' mm', _f(r.rain2w, 0) + ' mm', _f(r.p_heavy * 100 if pd.notna(r.p_heavy) else np.nan, 0) + '%',
              _f(r.pop_flood, 0)] for r in fw.itertuples()]
    fh = _table(['County', 'Alert', 'Soil z', '30-d water surplus', 'Rain next 2 wk (median)', 'Chance 50 mm day wk 1',
                 'People on flood-prone ground'], frows)
    ft = ['Flood watch (wettest soil, water surplus and heavy rain ahead, weighted by people on flood-prone ground):'] + [
        f"  {i}. {r.county} ({r.state}) soil z {_f(r.sm_z, 2)}, surplus {_f(r.wb30)} mm, next 2 wk rain {_f(r.rain2w)} mm, "
        f"{_f(r.pop_flood)} people on flood-prone ground" for i, r in enumerate(fw.itertuples(), 1)]
    infra_note = ('Settlement area, buildings, roads, schools and health facilities at flood risk by payam will be added '
                  'here once the infrastructure layer is in place.')
    # --- river trigger
    trig_h = (f'<p style="font-size:13px"><b>River trigger (experimental):</b> {html.escape(trig["text"])}</p>' if trig.get('text') else '')
    trig_t = (f'River trigger (experimental): {trig["text"]}' if trig.get('text') else '')
    # --- gauges
    gh = gt = ''
    if gauges is not None and len(gauges):
        grows = []
        for r in gauges.itertuples():
            vs = getattr(r, 'vs_2yr', np.nan)
            grows.append([('&#9733; ' if r.star else '') + html.escape(str(r.river)) + f' <span style="color:#777">({html.escape(r.uid)})</span>',
                          f'{r.level:.2f} m ({r.last_date})',
                          ('above' if vs > 0 else 'below') + f' 2-yr by {abs(vs):.2f} m' if pd.notna(vs) else 'n/a',
                          ('rising' if r.rising else 'steady/falling') + f' {r.trend_m:+.2f} m',
                          f'{r.lag_days:.0f} d', f'{r.days_to_warn:.0f} d', html.escape(str(r.downstream or 'n/a'))])
        gh = _table(['Station', 'Last level', 'vs 2-yr level', 'Last 3 passes', 'Travel time to next station', 'Warning time left', 'Next station downstream'], grows)
        gt = 'Gauge watch list (travel time > 5 days and last pass newer than the travel time):\n' + '\n'.join(
            f"  {'*' if r.star else ' '} {r.river} ({r.uid}) {r.level:.2f} m on {r.last_date}, trend {r.trend_m:+.2f} m, "
            f"lag {r.lag_days:.0f} d, {r.days_to_warn:.0f} d left" for r in gauges.itertuples())
    else:
        gh = '<p style="font-size:12px;color:#777">No gauge meets the rule today (travel time over 5 days and a pass newer than that).</p>'
        gt = 'Gauge watch list: no gauge meets the rule today.'
    # --- towns
    ix = df.set_index('county')
    trows, ttxt = [], []
    for town, county in TOWNS:
        if county in ix.index:
            r = ix.loc[county]
            trows.append([html.escape(town), html.escape(county), _badge(r.level), _f(r.sm_z, 2), _f(r.rain2w, 0) + ' mm',
                          _f(r.p_heavy * 100 if pd.notna(r.p_heavy) else np.nan, 0) + '%'])
            ttxt.append(f"  {town} ({county}): {str(r.level).upper()}, soil z {_f(r.sm_z, 2)}, next 2 wk rain {_f(r.rain2w)} mm")
    towh = _table(['Town', 'County', 'Alert', 'Soil z', 'Rain next 2 wk', 'Chance 50 mm day wk 1'], trows)

    foot_h, foot_t = _footer(subscribe_url, reply_to)
    body_h = (f'<div style="font-family:Arial,sans-serif;max-width:860px">'
              f'<h2 style="margin-bottom:2px">South Sudan hydro-climate watch &ndash; {date}</h2>'
              f'<div style="font-size:12px;color:#555">ECMWF run {html.escape(run)} UTC | rain and soil data to {html.escape(str(doc.get("antecedent_data_end")))} | '
              f'{counts["red"]} red, {counts["orange"]} orange, {counts["yellow"]} yellow, {counts["green"]} green counties</div>'
              f'<h3>Top 3 drought-watch counties</h3>{dh}<h3>Top 3 flood-watch counties</h3>{fh}'
              f'<p style="font-size:11px;color:#777">{infra_note}</p>{trig_h}'
              f'<h3>Gauge watch list</h3>{gh}<h3>Towns and counties to monitor</h3>{towh}'
              f'<p style="font-size:11px;color:#777">Decision support, not an official warning. Full county detail is in the attached PDF. '
              f'Data: {html.escape(" ".join(doc.get("attribution", [])))}</p>{foot_h}</div>')
    body_t = '\n'.join([f"South Sudan hydro-climate watch - {date}", f"ECMWF run {run} UTC | {counts['red']} red, {counts['orange']} orange, "
                        f"{counts['yellow']} yellow, {counts['green']} green", ''] + dt + [''] + ft + ['', infra_note, '', trig_t, '', gt, '',
                        'Towns and counties to monitor:'] + ttxt + ['', 'Decision support, not an official warning. Full detail in the attached PDF.', foot_t])
    return subject, body_t, body_h


def fetch_news(days=7, limit=8, timeout=20):
    """Climate / flood news for South Sudan from the ReliefWeb API (needs a registered appname in RELIEFWEB_APPNAME)."""
    app = os.environ.get('RELIEFWEB_APPNAME', '').strip()
    if not app:
        return [], 'ReliefWeb news skipped: set the RELIEFWEB_APPNAME variable (free registration at reliefweb.int/help/api).'
    q = {'appname': app, 'limit': limit, 'sort[]': 'date:desc',
         'fields[include][]': ['title', 'url_alias', 'date.created', 'source.name'],
         'filter[operator]': 'AND',
         'filter[conditions][0][field]': 'country.name', 'filter[conditions][0][value]': 'South Sudan',
         'filter[conditions][1][field]': 'disaster_type.name', 'filter[conditions][1][value][]': ['Flood', 'Drought', 'Flash Flood'],
         'filter[conditions][1][operator]': 'OR',
         'filter[conditions][2][field]': 'date.created',
         'filter[conditions][2][value][from]': (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime('%Y-%m-%dT00:00:00+00:00')}
    url = 'https://api.reliefweb.int/v1/reports?' + urllib.parse.urlencode(q, doseq=True)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'ssd-hydro-brief'}), timeout=timeout) as r:
            data = json.load(r)
        items = [dict(title=d['fields']['title'], url=d['fields'].get('url_alias') or d['fields'].get('url'),
                      date=d['fields']['date']['created'][:10], source=(d['fields'].get('source') or [{}])[0].get('name', ''))
                 for d in data.get('data', [])]
        return items, ''
    except Exception as e:
        return [], f'ReliefWeb news not available ({type(e).__name__}: {e}).'


def build_weekly(doc, news=None, news_note='', subscribe_url='', reply_to='penuelabi@gmail.com', today=None):
    df = county_frame(doc)
    ver = doc.get('forecast_verification') or {}
    date = (today or datetime.datetime.utcnow()).strftime('%d %b %Y')
    subject = f'South Sudan hydro-climate weekly outlook {date}'
    # confidence
    n = len(df)
    have = {k: int(df[k].notna().sum()) for k in ('sm_z', 'rain30', 'rain2w', 'wb30', 'pop_flood')}
    conf = [('Soil moisture (SMAP L4)', f'{have["sm_z"]}/{n} counties with data'),
            ('Rainfall to date (GSMaP)', f'{have["rain30"]}/{n} counties'),
            ('2-week rain forecast (ECMWF ENS)', f'{have["rain2w"]}/{n} counties; ' + (
                f'past-forecast check: {ver.get("summary")}' if ver.get('summary') else 'forecast verification is still building up')),
            ('Runoff / water surplus', f'{have["wb30"]}/{n} counties (30-day balance from SMAP)'),
            ('Flood-prone people (map-based)', f'{have["pop_flood"]}/{n} counties, WorldPop shares scaled to 2025 county totals')]
    # priorities: counties with highest hazard likelihood in the next 2 weeks
    pri = df.assign(sc=df[['p_heavy', 'p_dry']].max(axis=1).fillna(0)).sort_values(['sc', 'level'], ascending=False).head(8)
    prows = [[html.escape(r.county), html.escape(r.state), _badge(r.level), 'heavy rain' if (r.p_heavy or 0) >= (r.p_dry or 0) else 'dry spell',
              f'{r.sc * 100:.0f}%'] for r in pri.itertuples()]
    ptxt = [f'  {r.county} ({r.state}): {r.level}, {"heavy rain" if (r.p_heavy or 0) >= (r.p_dry or 0) else "dry spell"} chance {r.sc * 100:.0f}%'
            for r in pri.itertuples()]
    nh = ''.join(f'<li><a href="{html.escape(x["url"])}">{html.escape(x["title"])}</a> <span style="color:#777">({html.escape(x["source"])}, {x["date"]})</span></li>'
                 for x in (news or [])) or f'<li style="color:#777">{html.escape(news_note or "No matching reports this week.")}</li>'
    nt = '\n'.join(f'  - {x["title"]} ({x["source"]}, {x["date"]}) {x["url"]}' for x in (news or [])) or f'  {news_note or "No matching reports this week."}'
    foot_h, foot_t = _footer(subscribe_url, reply_to)
    body_h = (f'<div style="font-family:Arial,sans-serif;max-width:860px"><h2>South Sudan hydro-climate weekly outlook &ndash; {date}</h2>'
              f'<h3>How confident is this week&rsquo;s forecast?</h3>{_table(["Input", "Coverage and checks"], [[html.escape(a), html.escape(b)] for a, b in conf])}'
              f'<h3>Priorities for the next 2 weeks (counties and towns to watch)</h3>'
              f'{_table(["County", "State", "Alert", "Main hazard", "Chance"], prows)}'
              f'<h3>Climate and flood news from the past week</h3><ul style="font-size:13px">{nh}</ul>'
              f'<p style="font-size:11px;color:#777">Decision support, not an official warning.</p>{foot_h}</div>')
    body_t = '\n'.join([f'South Sudan hydro-climate weekly outlook - {date}', '', 'Forecast confidence:'] + [f'  {a}: {b}' for a, b in conf]
                       + ['', 'Priorities for the next 2 weeks:'] + ptxt + ['', 'News from the past week:', nt, '', foot_t])
    return subject, body_t, body_h
