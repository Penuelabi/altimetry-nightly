# -*- coding: utf-8 -*-
"""
Per-subscriber report choices from the Google Form sheet (published as CSV).

The Subscribe form asks: whole report | selected states | specific counties. The sheet has one row per response
(oldest first); the latest row for an address wins. This module reads those rows, picks the matching county pages
from the full county list and builds one PDF per distinct choice (cover + chosen counties + method pages), so a
choice shared by many people is built once.
"""
import csv
import hashlib
import io
import os
import re
import urllib.request

EMAIL_RE = re.compile(r'^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$')


def _k(name):
    k = re.sub(r'[^a-z0-9]', '', str(name).lower())
    return 'abyei' if k.startswith('abyei') else k


def _split(cell):
    return [p.strip() for p in str(cell or '').split(',') if p.strip()]


def parse_prefs(text):
    """CSV text -> {email: {'mode': 'all'|'custom', 'states': set, 'counties': set}} (normalised names)."""
    out = {}
    rd = csv.reader(io.StringIO(text))
    try:
        head = next(rd)
    except StopIteration:
        return out
    col = {h.strip(): i for i, h in enumerate(head)}
    e_i = next((i for h, i in col.items() if h.lower().startswith('email')), None)
    m_i = next((i for h, i in col.items() if h.lower().startswith('what would you like')), None)
    s_i = col.get('States')
    c_idx = [i for h, i in col.items() if h.startswith('Counties:')]
    if e_i is None:
        return out
    for row in rd:
        if e_i >= len(row):
            continue
        addr = row[e_i].strip().lower()
        if not EMAIL_RE.match(addr):
            continue
        get = lambda i: row[i] if i is not None and i < len(row) else ''
        mode_txt = get(m_i).lower()
        states = {_k(s) for s in _split(get(s_i))}
        counties = {_k(c) for i in c_idx for c in _split(get(i))}
        if 'whole' in mode_txt or not (states or counties):
            out[addr] = {'mode': 'all', 'states': set(), 'counties': set()}
        else:                                  # states and counties ticked on the form are both honoured
            out[addr] = {'mode': 'custom', 'states': states, 'counties': counties}
    return out


def fetch_prefs(url):
    if not url:
        return {}
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return parse_prefs(r.read().decode('utf-8', 'replace'))
    except Exception as e:
        print(f'WARNING: subscriber choices not read ({type(e).__name__}: {e}); everyone gets the full report.')
        return {}


def select(counties, pref):
    """Counties (list of dicts with 'county', 'state') matching one choice; order kept."""
    if pref['mode'] == 'all':
        return list(counties)
    return [c for c in counties if _k(c.get('state', '')) in pref['states'] or _k(c['county']) in pref['counties']]


def group_key(pref):
    return hashlib.md5(repr((pref['mode'], sorted(pref['states']), sorted(pref['counties']))).encode()).hexdigest()[:10]


def groups(emails, prefs):
    """Split addresses into (full_report_list, {key: (pref, [emails])}) for the custom choices."""
    full, custom = [], {}
    for e in emails:
        p = prefs.get(e.lower())
        if not p or p['mode'] == 'all':
            full.append(e)
        else:
            custom.setdefault(group_key(p), (p, []))[1].append(e)
    return full, custom


def build_subset_pdf(inputs, pref, path):
    """inputs = dict saved by build_report (counties, cover, kwargs). Returns (path, n_counties) or (None, 0)."""
    import county_report_pdf as m
    sub = select(inputs['counties'], pref)
    if not sub:
        return None, 0
    m.build_pdf(sub, path, **inputs['kwargs'], cover=inputs['cover'])
    return path, len(sub)
