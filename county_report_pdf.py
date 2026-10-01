# -*- coding: utf-8 -*-
"""
Combined county report PDF: one section per county, one PDF for all subscribers.

build_pdf(counties, path, run_label) takes a list of county dicts (see SAMPLE at the bottom for the shape)
and writes a PDF with a cover page, a contents table and one section per county:
  advisory | people affected, previous assessments | 2026 plan scenarios | settlements assessed Sept 2025 |
  infrastructure at risk (payam) | river station status, routed upstream signal, flooding vs same season,
  exposure within 25 km.
Sections whose data is missing are skipped, never filled with placeholders.
"""
import datetime as dt
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

FONT, FONT_B = 'Helvetica', 'Helvetica-Bold'
_dv = '/usr/share/fonts/truetype/dejavu/'
if os.path.exists(_dv + 'DejaVuSans.ttf'):
    pdfmetrics.registerFont(TTFont('DV', _dv + 'DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DV-B', _dv + 'DejaVuSans-Bold.ttf'))
    pdfmetrics.registerFontFamily('DV', normal='DV', bold='DV-B', italic='DV', boldItalic='DV-B')
    FONT, FONT_B = 'DV', 'DV-B'

NAVY, BLUE, GREY, LIGHT = colors.HexColor('#12355b'), colors.HexColor('#1d5ede'), colors.HexColor('#666666'), colors.HexColor('#eef2f7')
AMBER, RED = colors.HexColor('#b35900'), colors.HexColor('#c62828')

ss = getSampleStyleSheet()
BODY = ParagraphStyle('b', parent=ss['Normal'], fontName=FONT, fontSize=8.2, leading=10.4)
SMALL = ParagraphStyle('s', parent=BODY, fontSize=7.4, leading=9.5, textColor=GREY)
H1 = ParagraphStyle('h1', parent=BODY, fontName=FONT_B, fontSize=15, leading=18, textColor=NAVY, spaceAfter=2)
H2 = ParagraphStyle('h2', parent=BODY, fontName=FONT_B, fontSize=10.5, leading=13, textColor=NAVY, spaceBefore=6, spaceAfter=2)
H3 = ParagraphStyle('h3', parent=BODY, fontName=FONT_B, fontSize=9, leading=11.5, spaceBefore=3, spaceAfter=1)
CELL = ParagraphStyle('c', parent=BODY, fontSize=7.4, leading=9)
CELLB = ParagraphStyle('cb', parent=CELL, fontName=FONT_B)


def n(v, d=0):
    if v is None or isinstance(v, str):
        return v if isinstance(v, str) else 'n/a'
    return f'{v:,.{d}f}'


def P(t, st=BODY):
    return Paragraph(t, st)


def table(rows, widths, header=True, align_right_from=1):
    data = [[P(str(c), CELLB if (header and i == 0) else CELL) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#cccccc')),
          ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]
    if header:
        st.append(('BACKGROUND', (0, 0), (-1, 0), LIGHT))
    t.setStyle(TableStyle(st))
    return t


class Bars(Flowable):
    """Simple bar chart: labels + values (km2), a marker line for the current value."""
    def __init__(self, labels, vals, now=None, now_label='Now', w=170 * mm, h=42 * mm, unit='km²'):
        super().__init__()
        self.labels, self.vals, self.now, self.now_label, self.w, self.h, self.unit = labels, vals, now, now_label, w, h, unit

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        c = self.canv
        labels, vals = list(self.labels), list(self.vals)
        if self.now is not None:
            labels.append(self.now_label)
            vals.append(self.now)
        top = max(vals) * 1.15 or 1
        base, plot_h = 12, self.h - 20
        bw = self.w / (len(vals) * 1.6)
        gap = (self.w - bw * len(vals)) / (len(vals) + 1)
        c.setStrokeColor(colors.HexColor('#999999'))
        c.line(0, base, self.w, base)
        for i, (lab, v) in enumerate(zip(labels, vals)):
            x = gap + i * (bw + gap)
            hgt = plot_h * v / top
            c.setFillColor(RED if (self.now is not None and i == len(vals) - 1) else BLUE)
            c.rect(x, base, bw, hgt, stroke=0, fill=1)
            c.setFillColor(colors.black)
            c.setFont(FONT, 6.8)
            c.drawCentredString(x + bw / 2, base + hgt + 2, f'{v:,.0f}')
            c.drawCentredString(x + bw / 2, 2, str(lab))
        c.setFont(FONT, 6.8)
        c.setFillColor(GREY)
        c.drawString(0, self.h - 7, f'Flooded lowland within 25 km ({self.unit})')



APP_URL = 'https://penuelabi.users.earthengine.app/view/south-sudan-weather-forecast'
SUBSCRIBE_URL = 'https://claude.ai/artifact/NW1fEYxo4VQ2BoUfsVfQoK'
UNSUB_URL = 'mailto:penuelabi@gmail.com?subject=UNSUBSCRIBE'
UCD_URL = 'https://globalaffairs.ucdavis.edu/news/exploring-complex-social-ecological-systems'
LINK = '#1d5ede'


def links_block():
    a = lambda u, t: f'<a href="{u}" color="{LINK}">{t}</a>'
    return [P(f'Open the live map: {a(APP_URL, APP_URL)}', BODY),
            P(f'Subscribe to the email list: {a(SUBSCRIBE_URL, SUBSCRIBE_URL)}. To stop receiving it, {a(UNSUB_URL, "unsubscribe here")}.', BODY)]


def signature_block():
    a = lambda u, t: f'<a href="{u}" color="{LINK}">{t}</a>'
    return [P('ALLAU, Denis Abi, PhD<br/>Abuk Project<br/>Mayardit Academy for Space Sciences<br/>'
              + a(UCD_URL, 'University of Juba and University of California, Davis') + '<br/>WhatsApp: +211 917 939 818<br/>'
              + a('mailto:penuelabi@gmail.com', 'Email: penuelabi@gmail.com'), BODY)]


def _footer(label, has_cover=False):
    def f(canvas, doc):
        canvas.saveState()
        if not (has_cover and doc.page == 1):          # header with links on every county page
            from reportlab.pdfbase.pdfmetrics import stringWidth
            y = A4[1] - 9 * mm
            for parts in ([('Open the live map: ', None), (APP_URL, APP_URL)],
                          [('Subscribe to the email list: ', None), (SUBSCRIBE_URL, SUBSCRIBE_URL), ('. To stop receiving it, ', None), ('unsubscribe here', UNSUB_URL)]):
                x = 18 * mm
                for text, url in parts:
                    canvas.setFont(FONT, 6.8)
                    canvas.setFillColor(LINK if url else GREY)
                    canvas.drawString(x, y, text)
                    w = stringWidth(text, FONT, 6.8)
                    if url:
                        canvas.linkURL(url, (x, y - 1.5, x + w, y + 6.5), relative=0)
                    x += w
                y -= 3.4 * mm
        canvas.setFillColor(GREY)
        canvas.setFont(FONT, 7)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 10 * mm, f'South Sudan county flood and hydro-climate report | {label} | '
                          'Decision support, not an official warning.')
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f'Page {doc.page}')
        canvas.restoreState()
    return f


def county_story(c, today=None):
    s = []
    s.append(P(f"{c['county']} County", H1))
    s.append(P(f"{c.get('state', '')}" + (f" | County population about {n(c['population'])}" if c.get('population') else '')
               + (f" | Issued {today:%d %B %Y}" if today else ''), SMALL))
    if c.get('advisory'):
        s.append(P('Advisory', H2))
        for a in (c['advisory'] if isinstance(c['advisory'], list) else [c['advisory']]):
            s.append(P('• ' + a))
    prev = c.get('previous')
    if prev:
        s.append(P('People affected by floods, previous assessments (county)', H2))
        yrs = sorted(prev)
        s.append(table([['Year'] + [str(y) for y in yrs], ['People affected'] + [n(prev[y]) if prev[y] is not None else 'not listed' for y in yrs]],
                       [30 * mm] + [24 * mm] * len(yrs)))
    sc = c.get('scenarios')
    if sc:
        s.append(P('Flood scenarios, 2026 Floods &amp; Drought Plan (county, people affected)', H2))
        s.append(table([['Scenario', 'People affected'], ['1 (lower)', n(sc[0])], ['2 (planning)', n(sc[1])],
                        ['3 (severe)', n(sc[2])], ['Displaced in the planning case', n(sc[3])]], [70 * mm, 40 * mm]))
        s.append(P("Planning figures, not forecasts or probabilities. Scenarios 1 and 3 apply the plan's state coefficients to the county planning case.", SMALL))
    st = c.get('settlements')
    if st:
        s.append(P('Settlements assessed Sept 2025', H2))
        rows = [['Payam', 'Settlements', 'People', 'Flooded', 'High ground', 'Small towns']]
        tot = [0, 0, 0, 0, 0]
        for k in sorted(st):
            v = st[k]
            rows.append([k, n(v['n']), n(v['pop']), n(v['fl']), n(v['hg']), n(v['st'])])
            tot = [a + b for a, b in zip(tot, (v['n'], v['pop'], v['fl'], v['hg'], v['st']))]
        rows.append([f"<b>{c['county']} County</b>"] + [f'<b>{n(x)}</b>' for x in tot])
        s.append(table(rows, [42 * mm, 24 * mm, 24 * mm, 24 * mm, 26 * mm, 26 * mm]))
    ip = c.get('infra_payam')
    if ip:
        s.append(P('Infrastructure at risk of flooding, by payam', H2))
        s.append(P('At risk = flooded now or in at least 15% of years in the same season (Sentinel-1, 2020–2025).', SMALL))
        rows = [['Payam', 'Payam area km²', 'At risk km²', 'Schools (at risk)', 'Health (at risk)', 'Buildings (at risk)', 'Roads km (at risk)']]
        for r in ip:
            rows.append([r['payam'], n(r.get('area_km2')), n(r.get('area_risk_km2')), f"{n(r.get('schools'))} ({n(r.get('schools_risk'))})",
                         f"{n(r.get('health'))} ({n(r.get('health_risk'))})", f"{n(r.get('buildings'))} ({n(r.get('buildings_risk'))})",
                         f"{n(r.get('roads_km'), 1)} ({n(r.get('roads_risk_km'), 1)})"])
        s.append(table(rows, [28 * mm, 24 * mm, 20 * mm, 24 * mm, 24 * mm, 26 * mm, 28 * mm]))
        cc = c.get('infra_county')
        if cc:
            s.append(P(f"Health facilities: {n(cc['health'])} in the county, {n(cc['health_risk'])} on flood-prone ground | "
                       f"Schools: {n(cc['schools'])} in the county, {n(cc['schools_risk'])} on flood-prone ground", SMALL))
    for g in c.get('stations', []):
        s.extend(station_story(g))
    return s


def station_story(g):
    s = [P(f"River station: {g['name']} ({g['uid']})", H2)]
    lv = g.get('level')
    if lv:
        s.append(P('River level status', H3))
        s.append(P(f"Latest pass {lv['date']}: <b>{lv['cls']}</b> (percentile {lv['pct']}). Level {lv['wse']:.2f} m; seasonal median {lv['median']:.2f} m; "
                   f"anomaly {lv['wse'] - lv['median']:+.2f} m. Record: min {lv['min']:.2f} m, max {lv['max']:.2f} m, average {lv['avg']:.2f} m."))
        s.append(P(f"Baseline: {lv['years']} years, {lv['passes']} passes within ±30 days, 2016–2025. Quality: {lv['qc']}; uncertainty ±{lv['unc']:.2f} m; "
                   f"{lv['since_prev']} days since previous pass.", SMALL))
    if g.get('routed'):
        s.append(P('Routed upstream signal', H3))
        rows = [['Upstream station', 'Status (latest pass)', 'Median travel time', 'Expected here around']]
        for r in g['routed']:
            rows.append([r['uid'], f"{r['cls']} (percentile {r['pct']}) on {r['date']}", f"{r['lag']} days", r['expected']])
        s.append(table(rows, [32 * mm, 62 * mm, 32 * mm, 40 * mm]))
    rd = g.get('routed_down')
    if rd is not None:
        s.append(P('Routed downstream signal', H3))
        if rd:
            rows = [['Downstream station', 'Status (latest pass)', 'Median travel time from here', 'This station\'s signal expected there around']]
            for r in rd:
                rows.append([r['uid'], f"{r['cls']} (percentile {r['pct']}) on {r['date']}", f"{r['lag']} days", r['expected']])
            s.append(table(rows, [32 * mm, 56 * mm, 36 * mm, 42 * mm]))
        else:
            s.append(P(g.get('routed_down_note') or 'No downstream station linked.', SMALL))
    ex = g.get('exposure')
    if ex:
        s.append(P('Exposure within 25 km of the station', H3))
        s.append(P(f"WorldPop population (2020): {n(ex['pop'])}, of which {n(ex['pop_risk'])} at risk. Schools: {n(ex['schools'])} ({n(ex['schools_risk'])} at risk). "
                   f"Health facilities: {n(ex['health'])} ({n(ex['health_risk'])} at risk). Buildings (VIDA): {n(ex['buildings'])} ({n(ex['buildings_risk'])} at risk). "
                   f"Counties within 25 km: {', '.join(ex.get('counties', []))}."))
        if ex.get('payams'):
            rows = [['Payam (county)', 'Population (at risk)', 'Buildings', 'Schools (at risk)', 'Health (at risk)']]
            for r in ex['payams']:
                rows.append([f"{r['payam']} ({r['county']})", f"{n(r['pop'])} ({n(r['pop_risk'])})", n(r['bld']),
                             f"{n(r['sch'])} ({n(r['sch_r'])})", f"{n(r['hl'])} ({n(r['hl_r'])})"])
            s.append(table(rows, [50 * mm, 38 * mm, 24 * mm, 30 * mm, 28 * mm]))
    return s



LEVEL_COLOR = {'red': '#c62828', 'orange': '#ef6c00', 'yellow': '#f9a825', 'green': '#2e7d32'}


def badge(level):
    c = LEVEL_COLOR.get(str(level).lower(), '#777777')
    return f'<font color="{c}"><b>{str(level or "n/a").upper()}</b></font>'


VERSION_START = dt.date(2026, 10, 5)      # first weekly version: Monday 5 October 2026 = v51026


def weekly_version(d=None):
    """Weekly version label: 'v' + day + month(2) + year(2) of the Monday of the issue week, e.g. 5 Oct 2026 -> v51026,
    12 Oct 2026 -> v121026. Dates before the start use the first version."""
    d = d.date() if isinstance(d, dt.datetime) else (d or dt.date.today())
    mon = max(d - dt.timedelta(days=d.weekday()), VERSION_START)
    return f'v{mon.day}{mon.month:02d}{mon:%y}'


def cover_story(cover, logo=None):
    """cover = dict(date_label, header_line, sections=[(title, headers, rows, widths_mm, note)])"""
    from reportlab.platypus import Image
    head = P(f"SOUTH SUDAN HYDRO-CLIMATE WATCH<br/><font size=10 color='#444444'>{cover['date_label']} | Weekly version {cover['version']}</font>",
             ParagraphStyle('ct', parent=H1, fontSize=17, leading=22))
    if logo and os.path.exists(logo):
        img = Image(logo, width=24 * mm, height=24 * mm)
        top = Table([[img, head]], colWidths=[28 * mm, 142 * mm])
        top.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        s = [top]
    else:
        s = [head]
    s.append(P(cover['header_line'], SMALL))
    for title, headers, rows, widths, note in cover['sections']:
        s.append(P(title, H2))
        if rows:
            s.append(table([headers] + rows, [w * mm for w in widths]))
        if note:
            s.append(P(note, SMALL))
    bottom = links_block() + [Spacer(1, 4)] + signature_block() + [Spacer(1, 6),
        P('Decision support, not an official warning. One page per county follows. Rainfall figures are an outlook for local flooding and access, '
          'not a river-level forecast.', SMALL)]
    return s, bottom


def cover_from_bulletin(doc, gauges=None, today=None, n_monitor=5, n_gauges=5):
    """Build the cover from county_bulletin_latest.json (doc) and daily_brief.gauge_watch() output, same rules as the daily email."""
    import numpy as np
    import pandas as pd
    import daily_brief as db
    today = today or dt.datetime.utcnow()
    df = db.county_frame(doc)
    dw, fw = db.drought_watch(df), db.flood_watch(df, doc.get('sudd_river_trigger') or {})
    counts = {k: int((df.level == k).sum()) for k in db.LEVEL_ORDER}
    f = db._f
    pct = lambda v: f(v * 100 if pd.notna(v) else np.nan, 0) + '%'
    drows = [[f"<b>{r.county}</b> ({r.state})", badge(r.level), f(r.sm_z, 2), f(r.deficit) + ' mm', f(r.rain2w) + ' mm', pct(r.p_dry)] for r in dw.itertuples()]
    frows = [[f"<b>{r.county}</b> ({r.state})", badge(r.level), f(r.sm_z, 2), f(r.wb30) + ' mm', f(r.rain2w) + ' mm', pct(r.p_heavy), f(r.pop_flood)]
             for r in fw.itertuples()]
    grows = []
    if gauges is not None and len(gauges):
        for r in gauges.head(n_gauges).itertuples():
            vs = getattr(r, 'vs_2yr', np.nan)
            grows.append([('★ ' if r.star else '') + f'{r.river} ({r.uid})', f'{r.level:.2f} m ({r.last_date})',
                          (('above' if vs > 0 else 'below') + f' 2-yr by {abs(vs):.2f} m') if pd.notna(vs) else 'n/a',
                          ('rising' if r.rising else 'steady/falling') + f' {r.trend_m:+.2f} m', f'{r.lag_days:.0f} d',
                          f'{r.days_to_warn:.0f} d', str(r.downstream or 'n/a')])
    # towns and counties at red or orange that are not already in the drought / flood top 3
    skip = set(dw.county) | set(fw.county)
    town_of = {c: t for t, c in db.TOWNS}
    m = df[df.level.isin(['red', 'orange']) & ~df.county.isin(skip)].copy()
    m['lv'] = m.level.map({'red': 1, 'orange': 0})
    m['sc'] = m[['p_heavy', 'p_dry']].max(axis=1).fillna(0)
    m = m.sort_values(['lv', 'sc'], ascending=False).head(n_monitor)
    mrows = [[(f"{town_of[r.county]} ({r.county})" if r.county in town_of else r.county) + f" – {r.state}", badge(r.level), f(r.sm_z, 2),
              f(r.rain2w) + ' mm', pct(r.p_heavy), pct(r.p_dry)] for r in m.itertuples()]
    run = doc.get('ecmwf_run_utc') or 'n/a'
    header = (f"ECMWF run {run} UTC | rain and soil data to {doc.get('antecedent_data_end')} | "
              f"{counts['red']} red, {counts['orange']} orange, {counts['yellow']} yellow, {counts['green']} green counties")
    return {'date_label': today.strftime('%d %b %Y'), 'version': weekly_version(today), 'header_line': header, 'sections': [
        ('Top 3 drought-watch counties', ['County', 'Alert', 'Soil z', 'Soil deficit', 'Rain next 2 wk (median)', 'Chance 7-day dry spell'], drows,
         [50, 18, 14, 24, 32, 32], 'Lowest root-zone soil moisture that the next 2 weeks of rain will not fix.'),
        ('Top 3 flood-watch counties', ['County', 'Alert', 'Soil z', '30-d surplus', 'Rain next 2 wk', 'Chance 50 mm wk 1', 'People on flood-prone ground'], frows,
         [42, 18, 13, 20, 22, 24, 31], 'Wettest soil, water surplus and heavy rain ahead, weighted by people on flood-prone ground.'),
        (f'{n_gauges} Gauge watch list', ['Station', 'Last level', 'vs 2-yr level', 'Last 3 passes', 'Travel time', 'Warning left', 'Next station'], grows,
         [36, 26, 26, 26, 16, 19, 21], 'Travel time to the next station over 5 days and last pass newer than the travel time. ★ = station you already watch.'
         if grows else 'No gauge meets the rule today.'),
        (f'{n_monitor} Towns and counties to monitor (red or orange, not in the lists above)', ['Town / county', 'Alert', 'Soil z', 'Rain next 2 wk', 'Chance 50 mm wk 1', 'Chance 7-day dry spell'], mrows,
         [58, 18, 16, 26, 26, 26], None if mrows else 'No other county is at red or orange.')]}


def build_pdf(counties, path, run_label=None, today=None, cover=None, logo=None):
    today = today or dt.date.today()
    run_label = run_label or str(today)
    doc = BaseDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=19 * mm, bottomMargin=15 * mm,
                          title='South Sudan county flood and hydro-climate report', author='Penuel Abi')
    fr = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='f')
    cover_main = cover_bottom = None
    if cover:
        cover_main, cover_bottom = cover_story(cover, logo)
        bh = sum(f.wrap(doc.width - 12, 1000)[1] for f in cover_bottom) + 12      # height of the pinned block
        fb = Frame(doc.leftMargin, doc.bottomMargin, doc.width, bh, id='fb')
        fm = Frame(doc.leftMargin, doc.bottomMargin + bh, doc.width, doc.height - bh, id='fm')
        doc.addPageTemplates([PageTemplate(id='cover', frames=[fm, fb], onPage=_footer(run_label, True))])
    doc.addPageTemplates([PageTemplate(id='p', frames=[fr], onPage=_footer(run_label, bool(cover)))])
    story = []
    if cover:
        from reportlab.platypus import FrameBreak, NextPageTemplate
        story.extend(cover_main)
        story.append(FrameBreak())
        story.extend(cover_bottom)
        story.append(NextPageTemplate('p'))
        story.append(PageBreak())
    for i, c in enumerate(counties):
        if i:
            story.append(PageBreak())
        story.extend(county_story(c, today))
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# SAMPLE: Twic East, from the figures shown in the app                         #
# --------------------------------------------------------------------------- #
SAMPLE = [{
    'county': 'Twic East', 'state': 'Jonglei', 'population': 130000,
    'advisory': ['Soil moisture deficit (moderate): soil about 70 mm below median in the top metre (30-day rain 59% of normal); '
                 '~45 mm expected over 2 weeks = 64% of the deficit. Monitor crops and pasture; delay new planting until soils recover'],
    'previous': {2021: 58069, 2022: None, 2024: 55349, 2025: 101675},
    'scenarios': [23245, 36159, 69735, 10062],
    'settlements': {'Ajuong': {'n': 1, 'pop': 11100, 'fl': 0, 'hg': 0, 'st': 11100}, 'Kongor': {'n': 2, 'pop': 21300, 'fl': 0, 'hg': 0, 'st': 21300},
                    'Lith': {'n': 3, 'pop': 10950, 'fl': 9200, 'hg': 0, 'st': 1750}, 'Nyuak': {'n': 3, 'pop': 16800, 'fl': 1600, 'hg': 2200, 'st': 13000},
                    'Pakeer': {'n': 2, 'pop': 14900, 'fl': 1300, 'hg': 0, 'st': 13600}},
    'infra_payam': [{'payam': 'Pakeer', 'area_km2': 1326, 'area_risk_km2': 1145, 'schools': 5, 'schools_risk': 5, 'health': 2, 'health_risk': 2,
                     'buildings': 2033, 'buildings_risk': 76, 'roads_km': 361.9, 'roads_risk_km': 80.4}],
    'infra_county': {'health': 8, 'health_risk': 8, 'schools': 21, 'schools_risk': 21},
    'stations': [{
        'name': 'White Nile, River', 'uid': 'dahiti:17752',
        'level': {'date': '2026-09-13', 'cls': 'Above normal', 'pct': 68, 'wse': 415.44, 'median': 415.31, 'min': 413.89, 'max': 415.78,
                  'avg': 415.04, 'years': 10, 'passes': 22, 'qc': 'ok', 'unc': 0.02, 'since_prev': 27},
        'routed': [{'uid': 'dahiti:3246', 'cls': 'Unusually high', 'pct': 75, 'date': '2026-08-25', 'lag': 12, 'expected': '2026-09-06'},
                   {'uid': 'dahiti:3247', 'cls': 'Unusually high', 'pct': 78, 'date': '2026-08-25', 'lag': 5, 'expected': '2026-08-30'}],
        'routed_down': [], 'routed_down_note': 'Sample only: downstream station values were not in the figures provided.',
        'flood': {'now': (3.5, 69), 'normal': (0.4, 9), 'recurrent': (1.7, 33), 'occasional': (1.3, 25), 'unusual': (0.1, 2), 'nobase': (0.0, 0), 'drier': (7.3, 142)},
        'flood_by_year': {2020: 1317, 2021: 558, 2022: 272, 2023: 517, 2024: 464, 2025: 407}, 'flood_now_km2': 84,
        'flood_summary': 'Flooded lowland now: 84 km²; baseline mean 589 km² (range 272–1,317). Wetter than 0 of 6 baseline years (percentile 0).',
        'exposure': {'pop': 32123, 'pop_risk': 24034, 'schools': 2, 'schools_risk': 2, 'health': 0, 'health_risk': 0, 'buildings': 1277, 'buildings_risk': 44,
                     'counties': ['Twic East', 'Yirol East'],
                     'payams': [{'payam': 'Ajuong', 'county': 'Twic East', 'pop': 9301, 'pop_risk': 6152, 'bld': 100, 'sch': 0, 'sch_r': 0, 'hl': 0, 'hl_r': 0},
                                {'payam': 'Pakeer', 'county': 'Twic East', 'pop': 9279, 'pop_risk': 6091, 'bld': 1051, 'sch': 0, 'sch_r': 0, 'hl': 0, 'hl_r': 0},
                                {'payam': 'Malek', 'county': 'Yirol East', 'pop': 7821, 'pop_risk': 6970, 'bld': 82, 'sch': 1, 'sch_r': 1, 'hl': 0, 'hl_r': 0},
                                {'payam': 'Adior', 'county': 'Yirol East', 'pop': 3378, 'pop_risk': 2631, 'bld': 42, 'sch': 1, 'sch_r': 1, 'hl': 0, 'hl_r': 0},
                                {'payam': 'Nyuak', 'county': 'Twic East', 'pop': 2343, 'pop_risk': 2190, 'bld': 2, 'sch': 0, 'sch_r': 0, 'hl': 0, 'hl_r': 0}]}}],
}]

if __name__ == '__main__':
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else 'sample_county_report.pdf'
    note = 'Sample: this table is filled automatically from the latest bulletin when the report is generated.'
    cover = {'date_label': '01 Oct 2026', 'version': weekly_version(dt.date(2026, 10, 1)),
             'header_line': 'ECMWF run 2026-10-01 00 UTC | rain and soil data to 2026-09-28 | 0 red, 35 orange, 3 yellow, 41 green counties',
             'sections': [('Top 3 drought-watch counties', [], [], [], note), ('Top 3 flood-watch counties', [], [], [], note),
                          ('5 Gauge watch list', [], [], [], note),
                          ('5 Towns and counties to monitor (red or orange, not in the lists above)', [], [], [], note)]}
    logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uj_logo.png')
    build_pdf(SAMPLE, out, run_label='sample', today=dt.date(2026, 10, 1), cover=cover, logo=logo)
    print('wrote', out)
