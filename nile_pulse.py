# -*- coding: utf-8 -*-
"""Countdown for the Lake Victoria -> Nimule -> Juba (Rejaf) travel time.
Reads data/lake_victoria_pulse.json. Used by the PDF cover, the email and the Facebook post.
Colours: amber 30 days or less before arrival, red 10 days or less, 'arrived' after the date."""
import datetime as dt
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'lake_victoria_pulse.json')


def _state(days):
    if days < 0:
        return 'arrived'
    if days <= 10:
        return 'red'
    if days <= 30:
        return 'amber'
    return 'watch'


def pulse(today=None, path=None):
    """dict(signal_date, points=[(name, date, days_left, state)], levels) or None when the file is missing."""
    try:
        cfg = json.load(open(path or PATH, encoding='utf-8'))
        start = dt.date.fromisoformat(cfg['signal_date'])
    except Exception:
        return None
    today = today or dt.date.today()
    today = today.date() if isinstance(today, dt.datetime) else today
    pts = []
    for name, d in (('Nimule', cfg.get('lake_to_nimule_days', 103)),
                    ('Juba (Rejaf)', cfg.get('lake_to_juba_days', 112))):
        when = start + dt.timedelta(days=int(d))
        left = (when - today).days
        pts.append((name, when, left, _state(left)))
    return {'signal_date': start, 'signal': cfg.get('signal', ''), 'points': pts, 'levels': cfg.get('levels_m', [])}


def _phrase(name, when, left, state):
    if state == 'arrived':
        return f"{name}: expected {when:%d %b %Y} ({-left} days ago)"
    return f"{name}: {left} days left, expected {when:%d %b %Y}"


def one_line(p):
    return 'Nile pulse from Lake Victoria (started ' + f"{p['signal_date']:%d %b}" + '): ' + '; '.join(_phrase(*x) for x in p['points'])


def text_block(p):
    return one_line(p) + '. Travel-time estimate, not a river-level forecast.'


COL = {'watch': '#1a6e3c', 'amber': '#b36b00', 'red': '#b00020', 'arrived': '#555555'}


def html_block(p):
    rows = ''.join(f"<li><b style='color:{COL[s]}'>{n}</b>: " + (f"expected {w:%d %b %Y}, {-l} days ago" if s == 'arrived'
                   else f"<b>{l} days left</b>, expected {w:%d %b %Y}") + '</li>' for n, w, l, s in p['points'])
    return ("<div style='border:1px solid #ccc;border-left:4px solid #1a4f7a;padding:8px 12px;margin:10px 0;font-size:13px'>"
            f"<b>Nile pulse countdown from Lake Victoria</b> (clock started {p['signal_date']:%d %b %Y})<ul style='margin:6px 0 4px 18px'>{rows}</ul>"
            "<span style='font-size:11px;color:#666'>Travel-time estimate (103 days to Nimule, then 9 days to Rejaf). Not a river-level forecast.</span></div>")
