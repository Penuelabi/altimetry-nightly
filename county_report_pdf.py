# -*- coding: utf-8 -*-
"""
Combined county report PDF: one section per county, one PDF for all subscribers.

build_pdf(counties, path, run_label) takes a list of county dicts (see SAMPLE at the bottom for the shape)
and writes a PDF with a cover page, a contents table and one section per county:
  advisory | reported news | people affected, previous assessments | 2026 plan scenarios | settlements assessed Sept 2025 |
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
SUBSCRIBE_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSeDtY-twsGL0Xx9FlK_nLjC9X_6FSt7QxzTa4NXJqztwRe5VA/viewform'
UNSUB_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSfjTMvOg98EsZl56wfGGhxqKSlPHs-mM2mhblWZD6c1LEtXwQ/viewform'
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
        s.append(P('Infrastructure at risk of flooding, by payam (flood-prone ground)', H2))
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
    inow = c.get('infra_now')
    if inow:
        s.append(P('Infrastructure at risk of flooding, by payam (flooded now)', H2))
        s.append(P('At risk = flooded now, inside the current Sentinel-1 maximum flood extent.', SMALL))
        rows = [['Payam', 'Payam area km²', 'Flooded now km²', 'Schools (flooded)', 'Health (flooded)', 'Buildings (flooded)', 'Roads km (flooded)']]
        for r in inow:
            rows.append([r['payam'], n(r.get('area_km2')), n(r.get('area_now_km2')), f"{n(r.get('schools'))} ({n(r.get('schools_now'))})",
                         f"{n(r.get('health'))} ({n(r.get('health_now'))})", f"{n(r.get('buildings'))} ({n(r.get('buildings_now'))})",
                         f"{n(r.get('roads_km'), 1)} ({n(r.get('roads_now_km'), 1)})"])
        s.append(table(rows, [28 * mm, 24 * mm, 20 * mm, 24 * mm, 24 * mm, 26 * mm, 28 * mm]))
    s.extend(news_story(c))
    for g in c.get('stations', []):
        s.extend(station_story(g))
    if not c.get('stations') and c.get('linked_gauge'):
        s.extend(linked_gauge_story(c['linked_gauge']))
    return s


NEWS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'news.json')
NEWS_DAYS = 21          # items older than this are left out


def _nkey(name):
    import re
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def load_news(today=None, path=None, days=NEWS_DAYS):
    """Return (by_county, national). by_county maps a normalised county name to its news items (newest first);
    national holds items that name no county (state-level or countrywide). Missing file or no items = empty."""
    import json
    path = path or NEWS_PATH
    if not os.path.exists(path):
        return {}, []
    today = today or dt.date.today()
    today = today.date() if isinstance(today, dt.datetime) else today
    by, nat = {}, []
    for it in json.load(open(path, encoding='utf-8')).get('items', []):
        try:
            d = dt.date.fromisoformat(it['date'])
        except (KeyError, ValueError):
            continue
        if (today - d).days > days or d > today:
            continue
        if it.get('counties'):
            for c in it['counties']:
                by.setdefault(_nkey(c), []).append(it)
        else:
            nat.append(it)
    key = lambda it: it['date']
    return {k: sorted(v, key=key, reverse=True) for k, v in by.items()}, sorted(nat, key=key, reverse=True)


def _news_line(it, scope=None):
    d = dt.date.fromisoformat(it['date'])
    src = f"<a href=\"{it['url']}\" color=\"{LINK}\">{it['source']}</a>" if it.get('url') else it['source']
    tag = f"<b>{scope or it.get('hazard', '')}:</b> " if (scope or it.get('hazard')) else ''
    return f"• {d:%d %b}: {tag}{it['text']} ({src})"


def news_story(c):
    """Reported news for this county, newest first. Skipped when the county has no recent item."""
    items = c.get('news')
    if not items:
        return []
    s = [P('Reported news', H2)]
    for it in items[:4]:
        s.append(P(_news_line(it, it.get('hazard'))))
    s.append(P('From local media and ReliefWeb; single-source items are unverified. Counties are as named in the article, or inferred from the place where stated.', SMALL))
    return s


def linked_gauge_story(g):
    """Compact river-level readout for counties with no altimetry station within 25 km:
    the nearest / upstream gauge on the county's own river network."""
    rel_txt = {'upstream': 'upstream of the county', 'downstream': 'downstream of the county',
               'local': 'in the county’s own sub-basin', 'same-river': 'on the same river',
               'nearest': 'nearest gauge (different sub-basin)'}.get(str(g.get('relation')), str(g.get('relation')))
    name = g.get('river') or g.get('station_name') or g.get('station_uid')
    km = g.get('distance_km')
    km_txt = f"about {km:.0f} km away" if isinstance(km, (int, float)) and km == km else 'distance n/a'
    conf = g.get('confidence') or 'indicative'
    s = [P(f"River level — nearest gauge: {name}", H2)]
    s.append(P(f"No altimetry station falls within 25 km of this county, so this is the most relevant gauge on its "
               f"river network: {rel_txt}, {km_txt} ({conf} confidence). Altimetry levels are “as seen by satellite” "
               f"— an indicator of the river's state, not a local reading for the county.", SMALL))
    f2 = lambda v, d=2, suf='': '—' if not isinstance(v, (int, float)) or v != v else f'{v:.{d}f}{suf}'
    rows = [['Gauge', 'Status (latest pass)', 'Water level', 'Seasonal pct.', 'Trend', 'Last pass'],
            [str(g.get('station_uid')), g.get('flood_status') or '—', f2(g.get('last_level_m'), 2, ' m'),
             ('—' if not isinstance(g.get('seasonal_pctile'), (int, float)) or g.get('seasonal_pctile') != g.get('seasonal_pctile')
              else f"{g.get('seasonal_pctile'):.0f}th"),
             f2(g.get('rate_m_per_day'), 3, ' m/day') if not isinstance(g.get('rate_m_per_day'), (int, float)) or g.get('rate_m_per_day') != g.get('rate_m_per_day')
             else f"{g.get('rate_m_per_day'):+.3f} m/day", g.get('last_date') or '—']]
    s.append(table(rows, [32 * mm, 40 * mm, 24 * mm, 22 * mm, 28 * mm, 22 * mm]))
    return s


def station_story(g):
    s = [P(f"River station: {g['name']} ({g['uid']})", H2)]
    lv = g.get('level')
    if lv:
        f2 = lambda v, d=2: 'n/a' if v is None else f'{v:.{d}f}'
        s.append(P('River level status', H3))
        anom = f" anomaly {lv['wse'] - lv['median']:+.2f} m." if lv.get('wse') is not None and lv.get('median') is not None else ''
        s.append(P(f"Latest pass {lv['date']}: <b>{lv['cls']}</b>" + (f" (percentile {lv['pct']})" if lv.get('pct') is not None else '') +
                   f". Level {f2(lv.get('wse'))} m; seasonal median {f2(lv.get('median'))} m;{anom} "
                   f"Record: min {f2(lv.get('min'))} m, max {f2(lv.get('max'))} m, average {f2(lv.get('avg'))} m."))
        q = []
        if lv.get('years') is not None:
            q.append(f"Baseline: {lv['years']} years, {lv.get('passes')} passes within ±30 days, 2016–2025.")
        q.append(f"Quality: {lv.get('qc') or 'ok'}" + (f"; uncertainty ±{lv['unc']:.2f} m" if lv.get('unc') is not None else '') +
                 (f"; {lv['since_prev']} days since previous pass." if lv.get('since_prev') is not None else '.'))
        s.append(P(' '.join(q), SMALL))
    if g.get('routed'):
        s.append(P('Routed upstream signal', H3))
        rows = [['Upstream station', 'Status (latest pass)', 'Median travel time', 'Expected here around']]
        for r in g['routed']:
            rows.append([r['uid'], f"{r['cls']}" + (f" (percentile {r['pct']})" if r.get('pct') is not None else '') + f" on {r['date']}", (f"{r['lag']} days" if isinstance(r['lag'], int) else r['lag']), r['expected']])
        s.append(table(rows, [32 * mm, 62 * mm, 32 * mm, 40 * mm]))
    rd = g.get('routed_down')
    if rd is not None:
        s.append(P('Routed downstream signal', H3))
        if rd:
            rows = [['Downstream station', 'Status (latest pass)', 'Median travel time from here', 'This station\'s signal expected there around']]
            for r in rd:
                rows.append([r['uid'], f"{r['cls']}" + (f" (percentile {r['pct']})" if r.get('pct') is not None else '') + f" on {r['date']}", (f"{r['lag']} days" if isinstance(r['lag'], int) else r['lag']), r['expected']])
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
    np_ = cover.get('nile_pulse')
    if np_:
        import nile_pulse as _np
        s.append(P('Nile pulse countdown from Lake Victoria', H2))
        rows = [['Point', 'Expected', 'Days left']] + [[n, f'{w:%d %b %Y}', ('arrived' if st == 'arrived' else str(l))] for n, w, l, st in np_['points']]
        s.append(table(rows, [60 * mm, 40 * mm, 30 * mm]))
        if _np.alert_phrase(np_):
            s.append(P(f"<b><font color='#b00020'>{_np.alert_phrase(np_)}</font></b>", SMALL))
        if _np.level_phrase(np_):
            s.append(P(_np.level_phrase(np_) + '.', SMALL))
        s.append(P(f"Clock started {np_['signal_date']:%d %b %Y}. Travel time of 103 days from the lake to Nimule and 9 more to Rejaf (Juba). "
                   'Amber at 30 days, red at 10 days. If Lake Victoria reaches the May 2023 level, a second 30-day countdown to Juba starts. A travel-time estimate, not a river-level forecast.', SMALL))
    nat = cover.get('news') or []
    if nat:
        s.append(P('Countrywide and state-level news', H2))
        for it in nat[:5]:
            s.append(P(_news_line(it, it.get('scope') or it.get('hazard'))))
        s.append(P('News that names no county. County-level items are on each county page.', SMALL))
    bottom = links_block() + [Spacer(1, 4)] + signature_block() + [Spacer(1, 6),
        P('Decision support, not an official warning. One page per county follows. Rainfall figures are an outlook for local flooding and access, '
          'not a river-level forecast.', SMALL)]
    return s, bottom


def national_news(today=None):
    return load_news(today)[1]


def cover_from_bulletin(doc, gauges=None, today=None, n_monitor=5, n_gauges=5):
    """Build the cover from county_bulletin_latest.json (doc) and daily_brief.gauge_watch() output, same rules as the daily email."""
    import numpy as np
    import pandas as pd
    import daily_brief as db
    today = today or dt.datetime.utcnow()
    df = db.county_frame(doc)
    dw = db.drought_watch(df)
    fw = db.flood_watch(df, doc.get('sudd_river_trigger') or {}, exclude=dw['county'], gauges=db.load_county_gauges())
    counts = {k: int((df.level == k).sum()) for k in db.LEVEL_ORDER}
    f = db._f
    pct = lambda v: f(v * 100 if pd.notna(v) else np.nan, 0) + '%'
    drows = [[f"<b>{r.county}</b> ({r.state})", badge(r.level), f(r.sm_z, 2), f(r.deficit) + ' mm', f(r.rain2w) + ' mm', pct(r.p_dry)] for r in dw.itertuples()]
    frows = [[f"<b>{r.county}</b> ({r.state})" + (' <i>(river gauge)</i>' if r.basis == 'river' else ''), badge(r.level), f(r.sm_z, 2), f(r.wb30) + ' mm', f(r.rain2w) + ' mm', pct(r.p_heavy), f(r.pop_flood)]
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
         [58, 18, 16, 26, 26, 26], None if mrows else 'No other county is at red or orange.')],
            'news': national_news(today), 'nile_pulse': __import__('nile_pulse').pulse(today)}


def method_story(verification=None):
    """Closing pages: data sources, methods and references for everything in the report."""
    s = [P('About this report: data, methods and references', H1),
         P('Decision support, not an official warning. Alert levels follow the impact-based likelihood x impact approach of WMO-No. 1150; '
           'the scales are provisional. Figures are planning and monitoring information and carry the uncertainties listed below.', SMALL)]
    s.append(P('1. How the report is produced', H2))
    s.append(P('A GitHub Actions workflow runs the county bulletin twice a day, after the ECMWF 00 and 12 UTC releases (11:30 and 23:30 Juba). '
               'The combined report is rebuilt from that bulletin after the evening run (midnight Juba), emailed to subscribers as one PDF and published '
               'as the latest report linked from the live map. A weekly Earth Engine job refreshes the flood extent, the infrastructure-at-risk table and '
               'the 25 km station exposure. The weekly version label (vDDMMYY) is the Monday of the issue week; the first is v51026 (5 Oct 2026).'))
    s.append(P('2. County indicators and alert levels', H2))
    s.append(P('<b>Rain so far:</b> GSMaP v8 gauge-corrected rainfall, 7, 15 and 30-day totals against the same dates 2001–2025. '
               '<b>Soil and water balance:</b> NASA SMAP Level-4 root-zone soil moisture, evapotranspiration and runoff against 2015–2025; wetness is judged by the root-zone '
               'z-score (steadier than a percentile with about ten comparison years that include the flood years 2019–2022 and 2024). The soil deficit is the root-zone water '
               'missing against the median, in mm. '
               '<b>Outlook:</b> ECMWF IFS ensemble (up to 51 members, 15 days); chances of a 7-day dry spell, a 3-day wet spell and 50 mm in week 1 are the share of members '
               'that show the event. <b>Alert level:</b> likelihood x impact (green no action, yellow be aware, orange be prepared, red take action), for the hazard '
               '(drought / dry spell or flood / waterlogging) named in each county advisory; the likelihood and impact ratings are shown in the advisory text.'))
    if verification:
        s.append(P(f'Forecast check against observed rain: {verification}', SMALL))
    s.append(P('3. Cover lists', H2))
    s.append(P('<b>Drought watch:</b> counties with the lowest root-zone soil moisture that the next 2 weeks of rain will not fix. <b>Flood watch:</b> wettest soil, water surplus and heavy '
               'rain ahead, weighted by people on flood-prone ground. <b>Gauge watch:</b> stations where the water takes more than 5 days to reach the next station downstream and the last '
               'pass is newer than that travel time, so there is still time to warn downstream counties (star = a station already on the watch list). <b>Towns and counties to monitor:</b> '
               'red or orange counties not already in the drought or flood lists.'))
    s.append(P('4. Flood history, scenarios and settlements', H2))
    s.append(P('People affected in 2021, 2022, 2024 and 2025 come from the flood assessments compiled for the project (county totals; "not listed" means the county does not appear in that '
               'assessment, not that nobody was affected). The 2026 scenarios are planning figures from the 2026 Floods and Drought Plan (scenario 1 lower, 2 planning, 3 severe, and '
               'people displaced in the planning case); scenarios 1 and 3 apply the plan\'s state coefficients to the county planning case and are not forecasts or probabilities. '
               'Settlements are those assessed in September 2025 (OCHA 2024 and UNMISS 2025 high-ground list, other flooded settlements and small towns), grouped by payam. '
               'Population is the 2025 county estimate supplied to the project.'))
    s.append(P('5. Infrastructure at risk, by payam', H2))
    s.append(P('<b>At risk</b> = flooded in the current maximum flood extent, or flooded in at least 15% of the same-season baseline years (2020–2025) where at least three baseline years exist. '
               'The baseline is Sentinel-1 (descending VV): open water below -18 dB after a 50 m focal median, plus flooded vegetation where VV rises at least 3 dB over the Feb–Mar '
               'dry-season median, limited to terrain within 15 m above the nearest drainage (MERIT Hydro HAND). The current extent is the maximum over the latest 12 days of Sentinel-1, '
               'exported every Sunday to a fixed Earth Engine asset. Counts are per payam (512 payam polygons): schools and health facilities (OCHA point layers, counted when the point '
               'falls on at-risk ground), buildings (VIDA Google-Microsoft combined footprints; at-risk count skipped where a payam has more than 40,000), roads (GRIP4, 100 m raster, length '
               'on at-risk ground) and area. County totals are the sum of its payams.'))
    s.append(P('6. River stations', H2))
    s.append(P('Levels are satellite-altimetry passes from DAHITI (DGFI-TUM) and Hydroweb.Next (Theia / CNES, LEGOS), merged nightly with quality flags (jumps checked against neighbours, '
               'long gaps, high uncertainty). The <b>status</b> compares the latest level with passes within ±30 days of the same date in 2016–2025: unusually high from the 70th percentile, above normal '
               '60th–70th, near normal 40th–60th, below normal 30th–40th, unusually low below the 30th; fewer than 2 years or 6 passes counts as insufficient record. Low and insufficient stations are '
               'not shown. The <b>routed signal</b> reads the linked upstream and downstream stations: the median travel time is the typical lag between the two stations over their overlapping passes, and '
               '"expected here around" is the observation date plus that lag. Altimetry samples a river every 10–35 days, so a pass can miss a peak, and flood-level thresholds are "as seen by the satellite", '
               'not gauge return periods.'))
    s.append(P('7. Exposure within 25 km of a station', H2))
    s.append(P('Population (WorldPop 2020, 100 m), schools, health facilities and VIDA buildings inside a 25 km circle around the station, with the share on at-risk ground (definition in section 5) and '
               'a payam-by-payam breakdown of the part of each payam inside the circle. Circles overlap neighbouring counties, which are listed. A station is assigned to the county that contains it.'))
    s.append(P('8. News', H2))
    s.append(P('Reported news comes from Eye Radio, Radio Tamazuj, Sudans Post, UN and ReliefWeb items collected by the climate-news monitor and stored in data/news.json. '
               'Each county page lists items from the last 21 days that name that county; items naming no county appear on the cover. Items are summarised, not quoted; '
               'single-source items are unverified and county names may be inferred from places. Media coverage is partial and Facebook is not covered.'))
    s.append(P('9. Main limits', H2))
    for t in ('Rain, soil and flood layers are satellite products: coarse (GSMaP about 10 km, SMAP L4 about 9 km) and subject to retrieval error, especially in wetlands.',
              'The ensemble gives chances, not certainties; the dry-spell and heavy-rain chances are for the county as a whole.',
              'Flood extent from radar misses flooding under dense canopy and can over-detect on wet floodplain vegetation; the weekly window can miss short events.',
              'Population, building and facility layers are modelled or compiled, and may be out of date or incomplete in remote areas.',
              'River flooding from upstream can continue while local soils are dry: the land model does not include river overflow.',
              'Assessment and scenario figures describe past or planned situations, not the situation now.'):
        s.append(P('• ' + t))
    s.append(P('Data sources', H2))
    rows = [['Layer', 'Source', 'Used for'],
            ['Rainfall', 'GSMaP v8 operational, gauge-corrected (JAXA), via Google Earth Engine', 'Rain so far, anomalies'],
            ['Soil moisture, ET, runoff', 'NASA SMAP Level-4 SPL4SMGP', 'Soil z-score, deficit, water balance'],
            ['Forecast', 'ECMWF IFS ensemble open data (CC BY 4.0, © ECMWF)', 'Dry / wet spell and heavy-rain chances'],
            ['Forecast rain, 7-day', 'NOAA GFS 0.25°; ECMWF IFS NRT; CHIRPS daily (UCSB-CHG)', 'Station rainfall outlook in the app'],
            ['River levels', 'DAHITI (DGFI-TUM); Hydroweb.Next (Theia / CNES, LEGOS)', 'Station status and routed signals'],
            ['River discharge outlook', 'GEOGLOWS ECMWF Streamflow Model (BYU / ECMWF)', 'River alert, where available'],
            ['Flood extent and baseline', 'Copernicus Sentinel-1 GRD; MERIT Hydro HAND', 'Current and same-season flood extent'],
            ['Flood-prone ground', 'JRC Global Surface Water; Global Flood Database', 'Flood-prone share of population'],
            ['Population', 'County estimates 2025 (project); WorldPop 2020, 100 m (Univ. of Southampton, CC BY 4.0)', 'County and 25 km population'],
            ['Settlement and buildings', 'GHSL built-up surface (JRC); VIDA combined footprints; JRC GHS-OBAT 2020', 'Built-up area, building counts'],
            ['Roads', 'GRIP4 Africa (Meijer et al. 2018)', 'Road length at risk'],
            ['Schools, health facilities', 'OCHA (data.humdata.org/group/ssd)', 'Facilities at risk'],
            ['Cropland', 'ESA WorldCover 2021 v200 (CC BY 4.0)', 'Cropland in the county bulletin'],
            ['Catchments', 'HydroBASINS / HydroSHEDS', 'Upstream catchment rainfall'],
            ['Admin boundaries', 'OCHA (data.humdata.org/group/ssd); 512 payams', 'All county and payam figures'],
            ['Flood assessments, scenarios', 'Flood assessments 2021–2025; 2026 Floods and Drought Plan; OCHA 2024 / UNMISS 2025 settlement list', 'Earlier assessments, scenarios, settlements']]
    s.append(table(rows, [34 * mm, 90 * mm, 46 * mm], align_right_from=9))
    s.append(P('Key references', H2))
    for t in ('Gorelick, N. et al. (2017). Google Earth Engine: planetary-scale geospatial analysis for everyone. Remote Sensing of Environment 202, 18–27.',
              'Pekel, J.-F. et al. (2016). High-resolution mapping of global surface water and its long-term changes. Nature 540, 418–422.',
              'Tellman, B. et al. (2021). Satellite imaging reveals increased proportion of population exposed to floods. Nature 596, 80–86.',
              'Torres, R. et al. (2012). GMES Sentinel-1 mission. Remote Sensing of Environment 120, 9–24.',
              'Yamazaki, D. et al. (2019). MERIT Hydro: a high-resolution global hydrography map based on latest topography datasets. Water Resources Research 55, 5053–5073.',
              'Schwatke, C. et al. (2015). DAHITI: an innovative approach for estimating water level time series over inland waters using multi-mission satellite altimetry. Hydrology and Earth System Sciences 19, 4345–4364.',
              'Lehner, B. and Grill, G. (2013). Global river hydrography and network routing (HydroSHEDS, HydroBASINS). Hydrological Processes 27, 2171–2186.',
              'Meijer, J. R. et al. (2018). Global patterns of current and future road infrastructure. Environmental Research Letters 13, 064006.',
              'Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200. Zenodo.',
              'Gumbel, E. J. (1958). Statistics of Extremes. Columbia University Press.',
              'World Meteorological Organization (2015). WMO Guidelines on Multi-hazard Impact-based Forecast and Warning Services, WMO-No. 1150.',
              'Data providers: OCHA (schools, health facilities, administrative boundaries; data.humdata.org/group/ssd), JAXA (GSMaP), NASA (SMAP L4), ECMWF (IFS ensemble), NOAA (GFS), UCSB Climate Hazards Center (CHIRPS), DGFI-TUM (DAHITI), CNES / LEGOS (Hydroweb.Next), '
              'BYU / ECMWF (GEOGLOWS), University of Southampton (WorldPop), European Commission JRC (GSW, GHSL, GHS-OBAT), VIDA / Google / Microsoft (building footprints), ESA (WorldCover, Sentinel-1).'):
        s.append(P('• ' + t, SMALL))
    s.append(P('Method code and the live map', H2))
    s.append(P(f'Pipeline code: github.com/Penuelabi/altimetry-nightly. Live map: <link href="{APP_URL}" color="#1d5ede">{APP_URL}</link>. '
               'Prepared by ALLAU, Denis Abi, PhD, Abuk Project, Mayardit Academy for Space Sciences, University of Juba and University of California, Davis.', SMALL))
    return s


def fit_county(c, today, w, h):
    """One page per county: drop the second station, then trim the payam rows, then shrink slightly if it is still too tall."""
    from reportlab.platypus import KeepInFrame
    def height(cc):
        return sum(f.wrap(w, 10000)[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in county_story(cc, today))
    cc = dict(c)
    for step in range(5):
        if height(cc) <= h:
            break
        if step == 0 and len(cc.get('stations') or []) > 1:
            cc['stations'] = cc['stations'][:1]
        elif step == 1:
            cc['stations'] = [dict(g, exposure=dict(g['exposure'], payams=g['exposure']['payams'][:2])) if g.get('exposure') else g for g in cc.get('stations') or []]
        elif step == 2 and cc.get('infra_payam'):
            cc['infra_payam'] = cc['infra_payam'][:2]
        elif step == 3:
            cc['stations'] = [dict(g, exposure=dict(g['exposure'], payams=[])) if g.get('exposure') else g for g in cc.get('stations') or []]
    return [KeepInFrame(w, h, county_story(cc, today), mode='shrink')]


class Anchor(Flowable):
    """Zero-size marker: creates the PDF destination and records the page it lands on (for the contents page)."""
    def __init__(self, key, title, pages):
        super().__init__()
        self.key, self.title, self.pages = key, title, pages
        self.width = self.height = 0

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        c = self.canv
        c.bookmarkPage(self.key)
        c.addOutlineEntry(self.title, self.key, level=0, closed=True)
        self.pages[self.key] = c.getPageNumber()


def _ckey(c):
    import re
    return 'c_' + re.sub(r'[^A-Za-z0-9]', '', f"{c.get('state', '')}{c['county']}")


def toc_story(counties, pages, width):
    """Page 2: counties grouped by state, each a link to its page."""
    s = [P('Contents', H1), P('Counties by state. Click a county to jump to its page.', SMALL), Spacer(1, 2 * mm)]
    from itertools import groupby
    for state, grp in groupby(counties, key=lambda c: c.get('state', '')):
        rows = []
        for c in grp:
            k = _ckey(c)
            rows.append([P(f'<a href="#{k}" color="#1d5ede">{c["county"]}</a>', CELL), P(str(pages.get(k, '')), CELL)])
        t = Table(rows, colWidths=[width - 9 * mm, 9 * mm])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                               ('TOPPADDING', (0, 0), (-1, -1), 0.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 0.6),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        s.append(KeepTogether([P(f'{state} ({len(rows)})', H3), t]))
    return s


def build_pdf(counties, path, run_label=None, today=None, cover=None, logo=None, method=True, verification=None):
    pages = {}
    _build(counties, path, run_label, today, cover, logo, method, verification, pages)      # pass 1: find the pages
    _build(counties, path, run_label, today, cover, logo, method, verification, dict(pages), final=True)
    return path


def _build(counties, path, run_label, today, cover, logo, method, verification, pages, final=False):
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
    if cover and len(counties) > 1:
        gap = 5 * mm
        cw = (doc.width - 2 * gap) / 3
        doc.addPageTemplates([PageTemplate(id='toc', frames=[Frame(doc.leftMargin + i * (cw + gap), doc.bottomMargin, cw, doc.height, id=f't{i}', leftPadding=0, rightPadding=0)
                                                         for i in range(3)], onPage=_footer(run_label, True))])
    story = []
    if cover:
        from reportlab.platypus import FrameBreak, NextPageTemplate
        story.extend(cover_main)
        story.append(FrameBreak())
        story.extend(cover_bottom)
        if len(counties) > 1:
            story.append(NextPageTemplate('toc'))
            story.append(PageBreak())
            story.extend(toc_story(counties, pages, (doc.width - 10 * mm) / 3))
        story.append(NextPageTemplate('p'))
        story.append(PageBreak())
    for i, c in enumerate(counties):
        if i:
            story.append(PageBreak())
        story.append(Anchor(_ckey(c), f"{c.get('state', '')}: {c['county']}", pages if not final else {}))
        story.extend(fit_county(c, today, doc.width, doc.height - 2 * mm))
    if method:
        story.append(PageBreak())
        story.extend(method_story(verification))
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
