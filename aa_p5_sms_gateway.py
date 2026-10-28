# -*- coding: utf-8 -*-
"""
ANTICIPATORY ACTION ADD-ON 8 - PILLAR 5 / PILLAR 2: SMS DELIVERY THROUGH SMSGate (https://sms-gate.app)
Sends the SMS texts prepared by aa_p5_dissemination.py through an Android phone running SMSGate
(github.com/capcom6/android-sms-gateway), in Local, Cloud or Private mode. It talks to the SMSGate REST API
(POST /messages, same call the official clients make: Python `android-sms-gateway`, Go
`github.com/android-sms-gateway/client-go`), so it needs no extra package.

Safe by design - NOTHING is sent unless ALL of these are true
  1. you run it with --send  (default is a dry run that only prints and logs what would go out)
  2. SMS_GATE_ENABLED=yes is set
  3. the message is listed in aa_config/sms_release.csv with approved_by and approved_date
     (SSMS / MHADM / TWG-AA release; the dissemination drafts are labelled 'draft - validate before release')
  It is NOT part of the aa-addons.yml workflow; run it by hand or add your own approved workflow.

Inputs   aa_out/dissemination/latest/messages.csv  (channel == sms)
         aa_config/sms_release.csv                  columns: county, situation, language, approved_by, approved_date
                                                    (county '*' = all counties for that situation/language)
         recipients file, KEPT OUT OF THE PUBLIC REPOSITORY: SMS_RECIPIENTS_FILE (csv path) or SMS_RECIPIENTS_CSV
         (the csv text itself, e.g. a GitHub secret). Columns: phone, county, language, group_id
         (county blank = every county; language blank = every language; phone in international format, +211...)
Env      SMS_GATE_URL       default https://api.sms-gate.app/3rdparty/v1  (Local mode: http://<phone-ip>:8080)
         SMS_GATE_USER, SMS_GATE_PASSWORD   from the SMSGate app home screen
         SMS_GATE_SIM       optional SIM slot number (1, 2, ...)
         SMS_MAX_PER_RUN    safety cap on recipients per run, default 200
Outputs  aa_out/sms_send_log.csv (no phone numbers - only counts and a short hash), indicator rows in
         aa_indicator_ledger.csv, aa_config/sms_release.csv template on the first run
Run:     python aa_p5_sms_gateway.py            (dry run)
         python aa_p5_sms_gateway.py --send
         python aa_p5_sms_gateway.py --selftest
"""
import argparse
import base64
import datetime
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
AA_CONFIG = os.environ.get('AA_CONFIG_DIR', os.path.join(HERE, 'aa_config'))
AA_OUT = os.environ.get('AA_OUT_DIR', os.path.join(HERE, 'aa_out'))
API_URL = os.environ.get('SMS_GATE_URL', 'https://api.sms-gate.app/3rdparty/v1').rstrip('/')
MAX_PER_RUN = int(os.environ.get('SMS_MAX_PER_RUN', '200'))
BATCH = 50                                   # phone numbers per API call
SMS_MAX = 160
PHONE_RE = re.compile(r'^\+\d{8,15}$')
RELEASE_COLS = ['county', 'situation', 'language', 'approved_by', 'approved_date']


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def blank(x):
    return x is None or (isinstance(x, float) and x != x) or str(x).strip() == ''


def read_csv(path_or_buf):
    try:
        return pd.read_csv(path_or_buf, dtype=str, keep_default_na=False)
    except Exception as e:
        print(f"WARNING: could not read {path_or_buf if isinstance(path_or_buf, str) else 'recipients'}: {e}")
        return None


# --------------------------------------------------------------------------- #
# Inputs                                                                      #
# --------------------------------------------------------------------------- #
def load_messages(path=None):
    path = path or os.path.join(AA_OUT, 'dissemination', 'latest', 'messages.csv')
    if not os.path.exists(path):
        print(f"No messages file at {path}; run aa_p5_dissemination.py first.")
        return pd.DataFrame()
    m = read_csv(path)
    if m is None or not len(m):
        return pd.DataFrame()
    return m[m['channel'] == 'sms'].copy()


def load_release(path=None):
    path = path or os.path.join(AA_CONFIG, 'sms_release.csv')
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pd.DataFrame([{'county': '*', 'situation': 'flood_red', 'language': 'en', 'approved_by': '',
                       'approved_date': ''}], columns=RELEASE_COLS).to_csv(path, index=False)
        print(f"Wrote release template {path}: fill approved_by and approved_date to release a message type.")
    r = read_csv(path)
    return r if r is not None else pd.DataFrame(columns=RELEASE_COLS)


def is_released(row, rel):
    for _, r in rel.iterrows():
        if blank(r.get('approved_by')) or blank(r.get('approved_date')):
            continue
        if all(str(r[k]).strip() in ('*', str(row[k]).strip()) for k in ('county', 'situation', 'language')):
            return True
    return False


def load_recipients():
    """Recipients are personal data: never stored in this public repository."""
    csv_text = os.environ.get('SMS_RECIPIENTS_CSV', '')
    path = os.environ.get('SMS_RECIPIENTS_FILE', '')
    if csv_text.strip():
        df = read_csv(io.StringIO(csv_text))
    elif path and os.path.exists(path):
        df = read_csv(path)
    else:
        return pd.DataFrame(columns=['phone', 'county', 'language', 'group_id'])
    if df is None:
        return pd.DataFrame(columns=['phone', 'county', 'language', 'group_id'])
    for c in ('phone', 'county', 'language', 'group_id'):
        if c not in df:
            df[c] = ''
    df['phone'] = df['phone'].str.replace(r'[\s\-()]', '', regex=True)
    bad = ~df['phone'].apply(lambda p: bool(PHONE_RE.match(p)))
    if bad.any():
        print(f"WARNING: {int(bad.sum())} recipient rows skipped: phone must look like +211912345678")
    return df[~bad].drop_duplicates(subset=['phone', 'county', 'language'])


def recipients_for(msg, rec):
    ok = rec['county'].apply(lambda c: blank(c) or c.strip().lower() == str(msg['county']).strip().lower())
    ok &= rec['language'].apply(lambda l: blank(l) or l.strip().lower() == str(msg['language']).strip().lower())
    return sorted(set(rec.loc[ok, 'phone']))


# --------------------------------------------------------------------------- #
# SMSGate API                                                                 #
# --------------------------------------------------------------------------- #
def post_messages(text, phones):
    """POST {API_URL}/messages. Returns (ok, detail). Replaced in the selftest."""
    user, pw = os.environ.get('SMS_GATE_USER', ''), os.environ.get('SMS_GATE_PASSWORD', '')
    if not user or not pw:
        return False, 'SMS_GATE_USER / SMS_GATE_PASSWORD not set'
    body = {'textMessage': {'text': text}, 'phoneNumbers': phones}
    sim = os.environ.get('SMS_GATE_SIM', '').strip()
    if sim.isdigit():
        body['simNumber'] = int(sim)
    req = urllib.request.Request(
        API_URL + '/messages', data=json.dumps(body).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Basic ' + base64.b64encode(f'{user}:{pw}'.encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8') or '{}')
            return True, str(data.get('id', resp.status))
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code}'
    except Exception as e:                                           # network down, phone offline, ...
        return False, type(e).__name__


# --------------------------------------------------------------------------- #
# Run                                                                         #
# --------------------------------------------------------------------------- #
def short_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:10]


def already_sent(log, key):
    return log is not None and len(log) and ((log['key'] == key) & (log['status'] == 'sent')).any()


def run(send=False, messages=None, release=None, recipients=None):
    msgs = load_messages() if messages is None else messages
    rel = load_release() if release is None else release
    rec = load_recipients() if recipients is None else recipients
    live = send and os.environ.get('SMS_GATE_ENABLED', '').strip().lower() in ('yes', 'true', '1')
    if send and not live:
        print('--send given but SMS_GATE_ENABLED is not "yes": running as a dry run.')
    mode = 'LIVE' if live else 'DRY RUN'
    log_path = os.path.join(AA_OUT, 'sms_send_log.csv')
    log = read_csv(log_path) if os.path.exists(log_path) else None
    rows, total = [], 0
    stamp = now_utc().strftime('%Y-%m-%d %H:%M')
    today = stamp[:10]
    for _, m in msgs.iterrows():
        text = str(m['text'])
        base = {'run_utc': stamp, 'mode': mode, 'county': m['county'], 'situation': m['situation'],
                'language': m['language'], 'chars': len(text), 'text_hash': short_hash(text)}
        if len(text) > SMS_MAX:
            rows.append({**base, 'recipients': 0, 'status': 'skipped: over 160 characters', 'key': ''})
            continue
        if not is_released(m, rel):
            rows.append({**base, 'recipients': 0, 'status': 'held: not in sms_release.csv', 'key': ''})
            continue
        phones = recipients_for(m, rec)
        key = f"{today}|{m['county']}|{m['situation']}|{m['language']}|{base['text_hash']}"
        if not phones:
            rows.append({**base, 'recipients': 0, 'status': 'skipped: no recipients', 'key': key})
            continue
        if already_sent(log, key):
            rows.append({**base, 'recipients': len(phones), 'status': 'skipped: already sent today', 'key': key})
            continue
        if total + len(phones) > MAX_PER_RUN:
            rows.append({**base, 'recipients': len(phones), 'status': f'held: would pass SMS_MAX_PER_RUN={MAX_PER_RUN}',
                         'key': key})
            continue
        if not live:
            rows.append({**base, 'recipients': len(phones), 'status': 'would send', 'key': key})
            continue
        ok_all, detail = True, ''
        for i in range(0, len(phones), BATCH):
            ok, detail = post_messages(text, phones[i:i + BATCH])
            ok_all &= ok
            if not ok:
                break
        total += len(phones) if ok_all else 0
        rows.append({**base, 'recipients': len(phones), 'status': 'sent' if ok_all else f'failed: {detail}',
                     'key': key})
    out = pd.DataFrame(rows)
    if len(out):
        os.makedirs(AA_OUT, exist_ok=True)
        out = out.reindex(columns=['run_utc', 'mode', 'county', 'situation', 'language', 'chars', 'text_hash',
                                   'recipients', 'status', 'key'])
        pd.concat([log, out], ignore_index=True).to_csv(log_path, index=False) if log is not None \
            else out.to_csv(log_path, index=False)
    n_sent = int((out['status'] == 'sent').sum()) if len(out) else 0
    n_people = int(out.loc[out['status'] == 'sent', 'recipients'].sum()) if len(out) else 0
    print(f"[{mode}] {len(out)} message types checked; "
          f"{(out['status'].isin(['sent', 'would send'])).sum() if len(out) else 0} "
          f"{'sent' if live else 'ready'}; held/skipped: {len(out) - (out['status'].isin(['sent', 'would send'])).sum() if len(out) else 0}")
    if live and n_sent:
        log_indicator(n_sent, n_people)
    return out


def log_indicator(n_msgs, n_people):
    path = os.path.join(AA_OUT, 'aa_indicator_ledger.csv')
    cols = ['run_utc', 'script', 'pillar', 'activity', 'indicator', 'value', 'kind', 'unit', 'verification', 'note']
    new = pd.DataFrame([{
        'run_utc': now_utc().strftime('%Y-%m-%d %H:%M'), 'script': 'aa_p5_sms_gateway.py', 'pillar': 5,
        'activity': 'Disseminate early warnings through SMS and community channels',
        'indicator': 'Warning SMS released through SMSGate', 'value': n_msgs, 'kind': 'event', 'unit': 'messages',
        'verification': 'sms_send_log.csv', 'note': f'{n_people} recipients'}], columns=cols)
    if os.path.exists(path):
        old = read_csv(path)
        new = pd.concat([old, new.astype(str)], ignore_index=True) if old is not None else new
    new.to_csv(path, index=False)


# --------------------------------------------------------------------------- #
# Self-test (no network, no phone)                                            #
# --------------------------------------------------------------------------- #
def selftest():
    import tempfile
    global AA_OUT, AA_CONFIG, post_messages
    AA_OUT, AA_CONFIG = tempfile.mkdtemp(), tempfile.mkdtemp()
    sent = []
    post_messages = lambda text, phones: (sent.append((text, list(phones))) or (True, 'id1'))
    msgs = pd.DataFrame([
        {'state': 'Jonglei', 'county': 'Duk', 'situation': 'flood_red', 'channel': 'sms', 'language': 'en',
         'text': 'RED FLOOD ALERT Duk: move people and food to high ground.'},
        {'state': 'Jonglei', 'county': 'Bor', 'situation': 'flood_orange', 'channel': 'sms', 'language': 'en',
         'text': 'Orange flood alert Bor.'},
        {'state': 'Jonglei', 'county': 'Duk', 'situation': 'flood_red', 'channel': 'sms', 'language': 'din',
         'text': 'x' * 170}])
    rel = pd.DataFrame([{'county': '*', 'situation': 'flood_red', 'language': '*', 'approved_by': 'SSMS',
                         'approved_date': '2026-10-28'}])
    rec = pd.DataFrame([{'phone': '+211912345678', 'county': 'Duk', 'language': '', 'group_id': 'g1'},
                        {'phone': '+211922222222', 'county': '', 'language': 'en', 'group_id': 'g2'}])
    os.environ.pop('SMS_GATE_ENABLED', None)
    out = run(send=True, messages=msgs, release=rel, recipients=rec)          # not enabled -> dry run
    assert not sent and (out['status'] == 'would send').sum() == 1, out
    assert 'held: not in sms_release.csv' in set(out['status'])
    assert any(s.startswith('skipped: over 160') for s in out['status'])
    os.environ['SMS_GATE_ENABLED'] = 'yes'
    out = run(send=True, messages=msgs, release=rel, recipients=rec)
    assert len(sent) == 1 and sorted(sent[0][1]) == ['+211912345678', '+211922222222'], sent
    out2 = run(send=True, messages=msgs, release=rel, recipients=rec)         # same day again -> no duplicate
    assert len(sent) == 1 and 'skipped: already sent today' in set(out2['status'])
    logtxt = open(os.path.join(AA_OUT, 'sms_send_log.csv'), encoding='utf-8').read()
    assert '+2119' not in logtxt, 'phone numbers must not be logged'
    print('selftest passed: dry run by default, release gate, 160-character limit, no duplicates, no numbers in log')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--send', action='store_true', help='really send (also needs SMS_GATE_ENABLED=yes)')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        run(send=a.send)


if __name__ == '__main__':
    main()
