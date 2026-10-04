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


def _latest_level(uid, path=None):
    import csv
    f = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'lake_victoria_levels.csv')
    last = None
    try:
        for r in csv.DictReader(open(f, encoding='utf-8')):
            if r['station_uid'] == uid:
                last = (dt.date.fromisoformat(r['date'][:10]), float(r['level_m']))
    except Exception:
        return None
    return last


def pulse(today=None, path=None, levels_path=None):
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
    lv = None
    trig = cfg.get('trigger_level_m')
    last = _latest_level(cfg.get('level_station', 'dahiti:2'), levels_path)
    hw = _latest_level(cfg.get('hydroweb_station', ''), levels_path)
    if last and trig:
        lv = {'date': last[0], 'level': last[1], 'trigger': float(trig), 'label': cfg.get('trigger_label', 'trigger level'),
              'diff': round(last[1] - float(trig), 3), 'hit': last[1] >= float(trig),
              'hw': ({'date': hw[0], 'level': hw[1], 'trigger': cfg.get('hydroweb_trigger_level_m')} if hw else None)}
    juba_days = pts[-1][2]
    limit = int(cfg.get('double_alert_days_to_juba', 30))
    time_hit = 0 <= juba_days <= limit
    level_hit = bool(lv and lv['hit'])
    mode = 'double' if (level_hit and time_hit) else ('level' if level_hit else ('time' if time_hit else 'none'))
    return {'signal_date': start, 'signal': cfg.get('signal', ''), 'points': pts, 'levels': cfg.get('levels_m', []),
            'lake': lv, 'mode': mode, 'limit': limit}


def _phrase(name, when, left, state):
    if state == 'arrived':
        return f"{name}: expected {when:%d %b %Y} ({-left} days ago)"
    return f"{name}: {left} days left, expected {when:%d %b %Y}"


def level_phrase(p):
    lv = p.get('lake')
    if not lv:
        return ''
    side = 'above' if lv['diff'] >= 0 else 'below'
    return f"Lake Victoria {lv['level']:.2f} m on {lv['date']:%d %b} ({abs(lv['diff']):.2f} m {side} the {lv['label']} of {lv['trigger']:.2f} m)"


def alert_phrase(p):
    return {'double': f"DOUBLE ALERT: lake at or above the trigger level and Juba {p['limit']} days or less away",
            'level': 'LEVEL ALERT: lake at or above the trigger level',
            'time': f"TIME ALERT: Juba {p['limit']} days or less away, lake still below the trigger level",
            'none': ''}[p.get('mode', 'none')]


def one_line(p):
    out = 'Nile pulse from Lake Victoria (started ' + f"{p['signal_date']:%d %b}" + '): ' + '; '.join(_phrase(*x) for x in p['points'])
    if alert_phrase(p):
        out = alert_phrase(p) + '. ' + out
    return out


def text_block(p):
    lp = level_phrase(p)
    return one_line(p) + '. ' + (lp + '. ' if lp else '') + 'Travel-time estimate, not a river-level forecast.'


COL = {'watch': '#1a6e3c', 'amber': '#b36b00', 'red': '#b00020', 'arrived': '#555555'}


def html_block(p):
    rows = ''.join(f"<li><b style='color:{COL[s]}'>{n}</b>: " + (f"expected {w:%d %b %Y}, {-l} days ago" if s == 'arrived'
                   else f"<b>{l} days left</b>, expected {w:%d %b %Y}") + '</li>' for n, w, l, s in p['points'])
    mode = p.get('mode', 'none')
    banner = (f"<div style='background:{'#b00020' if mode == 'double' else '#b36b00'};color:#fff;padding:5px 8px;font-weight:bold;margin-bottom:6px'>"
              f"{alert_phrase(p)}</div>") if mode != 'none' else ''
    lp = level_phrase(p)
    lvl = f"<div style='margin:2px 0'>{lp}.</div>" if lp else ''
    return ("<div style='border:1px solid #ccc;border-left:4px solid #1a4f7a;padding:8px 12px;margin:10px 0;font-size:13px'>" + banner +
            f"<b>Nile pulse countdown from Lake Victoria</b> (clock started {p['signal_date']:%d %b %Y}){lvl}<ul style='margin:6px 0 4px 18px'>{rows}</ul>"
            "<span style='font-size:11px;color:#666'>Travel-time estimate (103 days to Nimule, then 9 days to Rejaf). Not a river-level forecast.</span></div>")
