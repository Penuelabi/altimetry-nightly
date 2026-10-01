# -*- coding: utf-8 -*-
"""
Post the county alert summary to a Facebook Page and/or a LinkedIn profile or page.
Optional: each channel is skipped unless its secrets are set. Never fails the workflow.

Facebook : FB_PAGE_ID, FB_PAGE_TOKEN          (Graph API, Page access token with pages_manage_posts)
LinkedIn : LI_AUTHOR_URN, LI_ACCESS_TOKEN     (urn:li:person:xxxx or urn:li:organization:xxxx; token with w_member_social
                                               or w_organization_social; LinkedIn tokens expire, about 60 days)
Settings (repo Variables, all optional):
    SOCIAL_MIN_LEVEL   orange (default) | yellow | red   - counties at or above this level are listed
    SOCIAL_RUN_HOURS   "00" (default) | "00,12"          - post only for these ECMWF cycles (default: once a day)
    SOCIAL_DRY_RUN     1 = print the post but do not publish
    SOCIAL_ONLY_IF_ALERTS 1 (default) = skip when no county reaches the level
"""
import json
import os
import re
import sys

import requests

ORDER = ['green', 'yellow', 'orange', 'red']
ICON = {'red': 'RED', 'orange': 'ORANGE', 'yellow': 'YELLOW'}
GRAPH = 'https://graph.facebook.com/v21.0'
LI_POSTS = 'https://api.linkedin.com/rest/posts'
LI_VERSION = os.environ.get('LI_API_VERSION', '202506')


def build_text(doc, min_level='orange', max_list=12):
    lo = ORDER.index(min_level) if min_level in ORDER else 2
    cs = doc['counties']
    counts = {k: sum(1 for c in cs if c['alert']['level'] == k) for k in ORDER}
    hit = [c for c in cs if c['alert']['level'] in ORDER and ORDER.index(c['alert']['level']) >= lo]
    hit.sort(key=lambda c: (-ORDER.index(c['alert']['level']), c['state'], c['county']))
    run = (doc.get('ecmwf_run_utc') or '')[:10]
    lines = [f"South Sudan county hydro-climate outlook, {run}",
             f"Alert levels for the next 15 days: {counts['red']} red, {counts['orange']} orange, "
             f"{counts['yellow']} yellow, {counts['green']} green (of {len(cs)} counties).", ""]
    for c in hit[:max_list]:
        a = c['alert']
        lines.append(f"{ICON[a['level']]} - {c['county']} ({c['state']}): {a['hazard']}")
    if len(hit) > max_list:
        lines.append(f"... and {len(hit) - max_list} more counties.")
    lines += ["",
              "Each county page of the full report now carries guidance by humanitarian cluster (WASH, Food Security, Health and Nutrition, "
              "Shelter and NFIs, Education, Protection): "
              "https://raw.githubusercontent.com/Penuelabi/altimetry-nightly/main/reports/latest.pdf",
              "",
              "Impact-based alert = hazard likelihood x people exposed. Decision support, not an official warning; "
              "scales are provisional.",
              "Data: GSMaP (JAXA), NASA SMAP, ECMWF IFS ensemble open data (CC BY 4.0, (c) ECMWF), WorldPop."]
    return '\n'.join(lines), len(hit)


def post_facebook(text, page_id, token):
    r = requests.post(f'{GRAPH}/{page_id}/feed', data={'message': text, 'access_token': token}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f'Facebook {r.status_code}: {r.text[:300]}')
    return r.json().get('id')


def li_escape(text):
    """LinkedIn 'little text' reserves these characters in commentary."""
    return re.sub(r'([\\|{}@\[\]()<>#*_~])', r'\\\1', text)


def post_linkedin(text, author, token):
    body = {'author': author, 'commentary': li_escape(text)[:2900], 'visibility': 'PUBLIC',
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
            'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False}
    r = requests.post(LI_POSTS, json=body, timeout=60, headers={
        'Authorization': f'Bearer {token}', 'LinkedIn-Version': LI_VERSION,
        'X-Restli-Protocol-Version': '2.0.0', 'Content-Type': 'application/json'})
    if r.status_code >= 300:
        raise RuntimeError(f'LinkedIn {r.status_code}: {r.text[:300]}')
    return r.headers.get('x-restli-id', 'ok')


def main():
    env = lambda k: (os.environ.get(k) or '').strip()
    fb_ok = env('FB_PAGE_ID') and env('FB_PAGE_TOKEN')
    li_ok = env('LI_AUTHOR_URN') and env('LI_ACCESS_TOKEN')
    if not (fb_ok or li_ok):
        print('Social posting not configured (FB_* / LI_* secrets); skipped.')
        return
    out = env('BULLETIN_OUT_DIR') or 'bulletin'
    jpath = os.path.join(out, 'county_bulletin_latest.json')
    if not os.path.exists(jpath) or os.path.getsize(jpath) < 20:
        print('Social post skipped: county_bulletin_latest.json was not written by this run.')
        return
    doc = json.load(open(jpath, encoding='utf-8'))
    hour = (doc.get('ecmwf_run_utc') or '')[-2:]
    allowed = [h.strip() for h in (env('SOCIAL_RUN_HOURS') or '00').split(',')]
    if hour not in allowed:
        print(f'Social post skipped: ECMWF {hour} UTC run is not in SOCIAL_RUN_HOURS ({",".join(allowed)}).')
        return
    text, n = build_text(doc, (env('SOCIAL_MIN_LEVEL') or 'orange').lower())
    if n == 0 and env('SOCIAL_ONLY_IF_ALERTS') != '0':
        print('No county at the alert level; nothing posted.')
        return
    print('----- post text -----\n' + text + '\n---------------------')
    if env('SOCIAL_DRY_RUN') == '1':
        print('DRY RUN: not published.')
        return
    for name, ok, fn in (('Facebook', fb_ok, lambda: post_facebook(text, env('FB_PAGE_ID'), env('FB_PAGE_TOKEN'))),
                         ('LinkedIn', li_ok, lambda: post_linkedin(text, env('LI_AUTHOR_URN'), env('LI_ACCESS_TOKEN')))):
        if not ok:
            continue
        try:
            pid = fn()
            link = f' https://www.linkedin.com/feed/update/{pid}/' if name == 'LinkedIn' and str(pid).startswith('urn:li:') else ''
            print(f'{name}: posted ({pid}){link}')
        except Exception as e:
            print(f'WARNING: {name} post failed: {type(e).__name__}: {e}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'WARNING: social posting failed: {type(e).__name__}: {e}')
    sys.exit(0)
