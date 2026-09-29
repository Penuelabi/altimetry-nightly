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
    lo = ORDER.index(min_level)
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


def main():
    host, user, pw, to = (os.environ.get(k, '') for k in ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'DIGEST_TO'))
    if not (host and user and pw and to):
        print('Email digest not configured (SMTP_HOST/SMTP_USER/SMTP_PASSWORD/DIGEST_TO); skipped.')
        return
    out = os.environ.get('BULLETIN_OUT_DIR', 'bulletin')
    doc = json.load(open(os.path.join(out, 'county_bulletin_latest.json'), encoding='utf-8'))
    msg, n = build_message(doc, os.path.join(out, 'county_bulletin_latest.pdf'),
                           os.environ.get('DIGEST_MIN_LEVEL', 'yellow').lower(),
                           os.environ.get('DIGEST_FROM') or user, to)
    if n == 0 and os.environ.get('DIGEST_ONLY_IF_ALERTS') == '1':
        print('No alerts; digest not sent.')
        return
    port = int(os.environ.get('SMTP_PORT') or 587)
    with (smtplib.SMTP_SSL(host, port, timeout=60) if port == 465 else smtplib.SMTP(host, port, timeout=60)) as s:
        if port != 465:
            s.starttls()
        s.login(user, pw)
        s.send_message(msg, to_addrs=[t.strip() for t in to.split(',') if t.strip()])
    print(f'Digest sent to {to} ({n} counties listed).')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'WARNING: digest failed: {type(e).__name__}: {e}')
        sys.exit(0)
