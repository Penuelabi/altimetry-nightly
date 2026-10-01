# -*- coding: utf-8 -*-
"""
Mailing list by e-mail, no web form needed. People subscribe by sending a message to the sender's Gmail
with the subject SUBSCRIBE, and leave with the subject UNSUBSCRIBE (the digest footer has ready-made mailto links).
Each run reads the inbox over IMAP, updates subscribers.csv (kept in the bulletin Drive folder) and returns the list.

Safeguards: only messages whose Authentication-Results show dkim=pass or spf=pass count (so nobody can
subscribe or unsubscribe someone else with a forged From address); the address is taken from From.
Needs IMAP enabled in the Gmail settings and the same app password as the digest (SMTP_USER / SMTP_PASSWORD).
"""
import csv
import datetime as dt
import email
import imaplib
import os
import re
from email.utils import getaddresses, parsedate_to_datetime

EMAIL_RE = re.compile(r'^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$')


def read_list(path):
    out = {}
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if r.get('email'):
                    out[r['email'].lower()] = r.get('since', '')
    return out


def write_list(path, d):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['email', 'since'])
        for k in sorted(d):
            w.writerow([k, d[k]])


def authenticated(msg):
    ar = ' '.join(msg.get_all('Authentication-Results', []) or []).lower()
    return 'dkim=pass' in ar or 'spf=pass' in ar


def sync(path, host='imap.gmail.com', user=None, password=None, days=10, own=None):
    """Update `path` from the inbox; return (list_of_emails, n_added, n_removed). Never raises on IMAP trouble."""
    cur = read_list(path)
    user = user or os.environ.get('SMTP_USER', '')
    password = (password or os.environ.get('SMTP_PASSWORD', '')).replace(' ', '')
    own = (own or user).lower()
    added = removed = 0
    try:
        m = imaplib.IMAP4_SSL(host, timeout=30)
        m.login(user, password)
        m.select('INBOX', readonly=True)
        since = (dt.date.today() - dt.timedelta(days=days)).strftime('%d-%b-%Y')
        events = []
        for word in ('SUBSCRIBE', 'UNSUBSCRIBE'):
            typ, data = m.search(None, f'(SINCE {since} SUBJECT "{word}")')
            for num in (data[0].split() if typ == 'OK' and data and data[0] else []):
                typ, md = m.fetch(num, '(BODY.PEEK[HEADER])')
                if typ != 'OK':
                    continue
                msg = email.message_from_bytes(md[0][1])
                subj = (msg.get('Subject') or '').strip().lower()
                if subj.startswith(('re:', 'fwd:')):
                    continue
                kind = 'unsub' if 'unsubscribe' in subj else ('sub' if 'subscribe' in subj else None)
                addr = [a for _, a in getaddresses(msg.get_all('From', [])) if EMAIL_RE.match(a or '')]
                if not kind or not addr or addr[0].lower() == own or not authenticated(msg):
                    continue
                try:
                    when = parsedate_to_datetime(msg.get('Date')).timestamp()
                except Exception:
                    when = 0
                events.append((when, kind, addr[0].lower()))
        m.logout()
        for when, kind, addr in sorted(events):       # oldest first so the last message wins
            if kind == 'sub' and addr not in cur:
                cur[addr] = dt.date.today().isoformat(); added += 1
            elif kind == 'unsub' and addr in cur:
                del cur[addr]; removed += 1
        write_list(path, cur)
    except Exception as e:
        print(f'WARNING: subscriber inbox not read ({type(e).__name__}: {e}). Using the saved list. '
              'Check that IMAP is enabled in Gmail settings.')
    return sorted(cur), added, removed
