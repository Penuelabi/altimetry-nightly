# -*- coding: utf-8 -*-
"""
Email digest of the county bulletin: counties at Yellow / Orange / Red, with the PDF attached.
Optional: does nothing (exit 0) unless the SMTP secrets are set.

Environment: SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, DIGEST_TO (comma list),
DIGEST_FROM (default SMTP_USER), BULLETIN_OUT_DIR, DIGEST_MIN_LEVEL (yellow|orange|red, default yellow;
if nothing reaches it a short "no alerts" mail is still sent unless DIGEST_ONLY_IF_ALERTS=1).
"""
import json
import os
import smtplib
import sys
from email.message import EmailMessage

ORDER = ['green', 'yellow', 'orange', 'red']


def build_message(doc, pdf_path=None, min_level='yellow', sender='', to=''):
    lo = ORDER.index(min_level) if min_level in ORDER else 1
    rows = [c for c in doc['counties'] if c['alert']['level'] in ORDER and ORDER.index(c['alert']['level']) >= lo]
    rows.sort(key=lambda c: (-ORDER.index(c['alert']['level']), c['state'], c['county']))
    counts = {k: sum(1 for c in doc['counties'] if c['alert']['level'] == k) for k in ORDER}
    run = doc.get('ecmwf_run_utc') or 'n/a'
    msg = EmailMessage()
    msg['Subject'] = (f"South Sudan county hydro-climate bulletin {run[:10]}: "
                      f"{counts['red']} red, {counts['orange']} orange, {counts['yellow']} yellow")
    msg['From'], msg['To'] = sender, to
    lines = [f"ECMWF run {run} UTC | rain/soil data to {doc.get('antecedent_data_end')}",
             f"Counties: {counts['red']} red, {counts['orange']} orange, {counts['yellow']} yellow, "
             f"{counts['green']} green", ""]
    if not rows:
        lines.append(f"No county at {min_level} or above.")
    for c in rows:
        a = c['alert']
        lines.append(f"[{a['level'].upper()}] {c['county']} ({c['state']}) - {a['text']}")
        for adv in c.get('advisory', [])[:3]:
            lines.append(f"    - {adv}")
    lines += ["", "Decision support, not an official warning. Alert scales are provisional.", "",
              "Data: " + " ".join(doc.get('attribution', []))]
    msg.set_content("\n".join(lines))
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as fh:
            msg.add_attachment(fh.read(), maintype='application', subtype='pdf',
                               filename='county_bulletin_latest.pdf')
    return msg, len(rows)


def subscribers(url):
    """Addresses from a published Google Sheet CSV (any column containing '@'); blank/invalid skipped."""
    if not url:
        return []
    import csv, io, re, urllib.request
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            txt = r.read().decode('utf-8', 'replace')
    except Exception as e:
        print(f'WARNING: subscriber list not read ({type(e).__name__}: {e}); sending to DIGEST_TO only.')
        return []
    out = []
    for row in csv.reader(io.StringIO(txt)):
        for cell in row:
            m = re.fullmatch(r'\s*([^@\s,;]+@[^@\s,;]+\.[^@\s,;]+)\s*', cell)
            if m and m.group(1).lower() not in out:
                out.append(m.group(1).lower())
    return out


def rich_message(doc, out, sender, to, bcc, kind, today=None):
    """Daily (kind='daily') or weekly (kind='weekly') email with HTML body, PDF attached, BCC subscribers."""
    import daily_brief as db
    alt = os.environ.get('ALTIMETRY_OUT_DIR', 'altdata')
    sub = (os.environ.get('SUBSCRIBE_URL') or '').strip()
    if kind == 'weekly':
        news, note = db.fetch_news()
        subject, text, html = db.build_weekly(doc, news, note, sub, sender, today)
    else:
        merged = os.path.join(alt, 'merged_altimetry_stations.csv')
        gauges = None
        try:
            if os.path.exists(merged):
                gauges = db.gauge_watch(merged, os.path.join(alt, 'station_status.csv'), today)
        except Exception as e:
            print(f'WARNING: gauge watch skipped: {type(e).__name__}: {e}')
        subject, text, html = db.build_daily(doc, gauges, sub, sender, today)
    msg = EmailMessage()
    msg['Subject'], msg['From'], msg['To'] = subject, sender, to
    msg['Reply-To'] = sender
    msg.set_content(text)
    msg.add_alternative(html, subtype='html')
    pdf = os.path.join(out, 'county_bulletin_latest.pdf')
    if os.path.exists(pdf):
        with open(pdf, 'rb') as fh:
            msg.add_attachment(fh.read(), maintype='application', subtype='pdf', filename='county_bulletin_latest.pdf')
    return msg


def main():
    host, user, pw, to = (os.environ.get(k, '').strip() for k in ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'DIGEST_TO'))
    pw = pw.replace(' ', '')                       # Google shows app passwords in groups of four
    if not (host and user and pw and to):
        print('Email digest not configured (SMTP_HOST/SMTP_USER/SMTP_PASSWORD/DIGEST_TO); skipped.')
        return
    out = os.environ.get('BULLETIN_OUT_DIR', 'bulletin')
    jpath = os.path.join(out, 'county_bulletin_latest.json')
    if not os.path.exists(jpath) or os.path.getsize(jpath) < 20:
        print('Digest skipped: county_bulletin_latest.json was not written by this run. '
              'Look for "WARNING: impact/alert layer skipped" or "JSON/PDF outputs skipped" in the '
              '"Run county bulletin" step.')
        return
    doc = json.load(open(jpath, encoding='utf-8'))
    sender = os.environ.get('DIGEST_FROM') or user
    n = 0
    bcc = []
    if os.environ.get('DIGEST_FORMAT', 'rich') == 'rich':
        import datetime as dt
        now = dt.datetime.utcnow()
        kind = 'weekly' if (os.environ.get('DIGEST_KIND') == 'weekly' or
                            (now.weekday() == 0 and now.hour < 15 and os.environ.get('DIGEST_KIND') != 'daily')) else 'daily'
        # twice-daily workflow: only the morning run (UTC hour < 15) sends the rich daily mail
        if os.environ.get('DIGEST_KIND') is None and now.hour >= 15 and os.environ.get('GITHUB_EVENT_NAME') == 'schedule':
            print('Evening run: rich daily email already sent this morning; skipped.')
            return
        bcc = subscribers((os.environ.get('SUBSCRIBERS_CSV_URL') or '').strip())
        try:
            msg = rich_message(doc, out, sender, to, bcc, kind, now.date())
            n = 1
        except Exception as e:
            print(f'WARNING: rich email failed ({type(e).__name__}: {e}); falling back to plain digest.')
            msg = None
    else:
        msg = None
    if msg is None:
        msg, n = build_message(doc, os.path.join(out, 'county_bulletin_latest.pdf'),
                               (os.environ.get('DIGEST_MIN_LEVEL') or 'yellow').strip().lower(), sender, to)
    if n == 0 and os.environ.get('DIGEST_ONLY_IF_ALERTS') == '1':
        print('No alerts; digest not sent.')
        return
    port = int((os.environ.get('SMTP_PORT') or '587').strip())
    print(f'Sending via {host}:{port} as {user} to {len(to.split(","))} recipient(s) ...')
    with (smtplib.SMTP_SSL(host, port, timeout=60) if port == 465 else smtplib.SMTP(host, port, timeout=60)) as s:
        if port != 465:
            s.starttls()
        s.login(user, pw)
        s.send_message(msg, to_addrs=[t.strip() for t in to.split(',') if t.strip()] + bcc)
    print(f'Digest sent to {to} + {len(bcc)} subscriber(s) (BCC).')


if __name__ == '__main__':
    try:
        main()
    except smtplib.SMTPAuthenticationError as e:
        print(f'WARNING: digest failed: the mail server rejected the login ({e.smtp_code}). For Gmail use an '
              'APP PASSWORD (not your normal password), with 2-Step Verification on, and SMTP_USER = the same Gmail address.')
        sys.exit(0)
    except Exception as e:
        print(f'WARNING: digest failed: {type(e).__name__}: {e}')
        sys.exit(0)
