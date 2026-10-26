# -*- coding: utf-8 -*-
"""
List recent ReliefWeb reports on South Sudan as CANDIDATES for the weekly news compile (data/news.json).

It only prints. It never writes data/news.json: every candidate still has to be opened, dated and checked against
the article before it becomes an item (see the weekly compile task).

Needs the registered appname in RELIEFWEB_APPNAME (free, reliefweb.int/help/api), the same variable daily_brief.py uses.

    RELIEFWEB_APPNAME=xxx python3 reliefweb_candidates.py [days] [--json]

Two queries are merged and de-duplicated:
  1. reports tagged Flood / Flash Flood / Drought / Epidemic / Cholera outbreak-type disasters for South Sudan
  2. reports on South Sudan whose title or body mentions flood, rain, drought, dry spell, cholera, hepatitis,
     malaria, El Nino, Lake Victoria, dyke or food insecurity
"""
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

API = 'https://api.reliefweb.int/v1/reports'
FIELDS = ['title', 'url_alias', 'url', 'date.created', 'date.original', 'source.name', 'format.name', 'disaster_type.name']
KEYWORDS = ('flood OR flooding OR "heavy rain" OR rainfall OR drought OR "dry spell" OR cholera OR "hepatitis E" '
            'OR malaria OR "El Nino" OR "Lake Victoria" OR dyke OR "food insecurity"')


def _get(params, timeout=30):
    url = API + '?' + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'ssd-hydro-news-candidates'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _since(days):
    d = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return d.strftime('%Y-%m-%dT00:00:00+00:00')


def _base(app, days, limit):
    return {'appname': app, 'limit': limit, 'sort[]': 'date.created:desc',
            'fields[include][]': FIELDS,
            'filter[operator]': 'AND',
            'filter[conditions][0][field]': 'country.name', 'filter[conditions][0][value]': 'South Sudan',
            'filter[conditions][1][field]': 'date.created', 'filter[conditions][1][value][from]': _since(days)}


def collect(app, days=10, limit=50):
    seen, rows = set(), []
    q1 = _base(app, days, limit)
    q1.update({'filter[conditions][2][field]': 'disaster_type.name',
               'filter[conditions][2][value][]': ['Flood', 'Flash Flood', 'Drought', 'Epidemic', 'Cold Wave', 'Tropical Cyclone'],
               'filter[conditions][2][operator]': 'OR'})
    q2 = _base(app, days, limit)
    q2.update({'query[value]': KEYWORDS, 'query[operator]': 'OR', 'query[fields][]': ['title', 'body']})
    for label, q in (('disaster-type', q1), ('keyword', q2)):
        for d in _get(q).get('data', []):
            f = d.get('fields', {})
            url = f.get('url_alias') or f.get('url')
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append({'date_created': (f.get('date', {}).get('created') or '')[:10],
                         'date_original': (f.get('date', {}).get('original') or '')[:10],
                         'title': f.get('title', ''),
                         'source': ', '.join(s.get('name', '') for s in f.get('source', []) or []),
                         'format': ', '.join(s.get('name', '') for s in f.get('format', []) or []),
                         'disaster_type': ', '.join(s.get('name', '') for s in f.get('disaster_type', []) or []),
                         'url': url, 'matched_by': label})
    rows.sort(key=lambda r: r['date_original'] or r['date_created'], reverse=True)
    return rows


def main(argv):
    days = next((int(a) for a in argv if a.isdigit()), 10)
    app = os.environ.get('RELIEFWEB_APPNAME', '').strip()
    if not app:
        print('RELIEFWEB_APPNAME is not set (register an appname at reliefweb.int/help/api). Nothing fetched.')
        return 2
    try:
        rows = collect(app, days)
    except Exception as e:
        print(f'ReliefWeb not available ({type(e).__name__}: {e}).')
        return 1
    if '--json' in argv:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    print(f'{len(rows)} ReliefWeb candidates for South Sudan, last {days} days. Verify each against the article before use.\n')
    for r in rows:
        print(f"{r['date_original'] or r['date_created']}  {r['source']}  [{r['format']}] {r['disaster_type']}\n  {r['title']}\n  {r['url']}\n")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
