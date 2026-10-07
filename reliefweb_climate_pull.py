#!/usr/bin/env python3
"""Pull climate-related ReliefWeb reports for South Sudan (default: last 30 days).

Standalone add-on: reads nothing from the app, modifies no existing script, sends nothing.
Needs the ReliefWeb *approved appname* in the environment variable RELIEFWEB_APPNAME
(GitHub Actions secret of the same name). Standard library only.

Outputs (in --out-dir, default ./data):
    reliefweb_climate.json   full records (for other scripts to read)
    reliefweb_climate.csv    one row per report, easy to open in Excel

Usage:
    RELIEFWEB_APPNAME=xxxx python reliefweb_climate_pull.py            # last 30 days
    python reliefweb_climate_pull.py --days 60 --out-dir data
    python reliefweb_climate_pull.py --selftest                        # no network, no secret
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://api.reliefweb.int/v2/reports"
COUNTRY = "South Sudan"
THEMES = ["Climate Change and Environment"]
DISASTER_TYPES = ["Flood", "Flash Flood", "Drought", "Epidemic"]  # Epidemic kept out below; see build_payload
KEYWORDS = ("flood OR flooding OR rainfall OR rains OR drought OR \"dry spell\" OR "
            "\"climate change\" OR waterlogging OR \"river level\" OR \"El Nino\" OR "
            "\"La Nina\" OR ICPAC OR \"seasonal forecast\" OR \"weather forecast\"")
FIELDS_INCLUDE = ["title", "date.original", "date.created", "source.name", "url_alias",
                  "disaster_type.name", "theme.name", "format.name", "body"]


def build_payload(days):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00+00:00")
    return {
        "limit": 1000,
        "sort": ["date.original:desc"],
        "fields": {"include": FIELDS_INCLUDE},
        "query": {"value": KEYWORDS, "operator": "OR"},
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "country.name", "value": COUNTRY},
                {"field": "date.original", "value": {"from": since}},
                {"operator": "OR", "conditions": [
                    {"field": "theme.name", "value": THEMES},
                    {"field": "disaster_type.name", "value": ["Flood", "Flash Flood", "Drought"],
                     "operator": "OR"},
                ]},
            ],
        },
    }


def fetch(appname, days):
    url = f"{API_URL}?appname={appname}"
    data = json.dumps(build_payload(days)).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        if e.code in (401, 403):
            sys.exit(f"ReliefWeb refused the request (HTTP {e.code}). Check that RELIEFWEB_APPNAME is an "
                     f"*approved* appname (register at https://apidoc.reliefweb.int). {body}")
        sys.exit(f"ReliefWeb API error HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach ReliefWeb: {e}")


def _names(v):
    if isinstance(v, list):
        return [x.get("name", x) if isinstance(x, dict) else x for x in v]
    if isinstance(v, dict):
        return [v.get("name", "")]
    return [v] if v else []


def clean(text, n=600):
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()
    return text[:n] + ("..." if len(text) > n else "")


def parse(resp):
    rows = []
    for item in resp.get("data", []):
        f = item.get("fields", {})
        d = f.get("date", {})
        rows.append({
            "id": item.get("id"),
            "date": (d.get("original") or d.get("created") or "")[:10],
            "title": f.get("title", ""),
            "source": "; ".join(_names(f.get("source"))),
            "disaster_type": "; ".join(_names(f.get("disaster_type"))),
            "theme": "; ".join(_names(f.get("theme"))),
            "format": "; ".join(_names(f.get("format"))),
            "url": f.get("url_alias") or item.get("href", ""),
            "excerpt": clean(f.get("body")),
        })
    return rows


def save(rows, out_dir, days):
    os.makedirs(out_dir, exist_ok=True)
    meta = {"country": COUNTRY, "window_days": days,
            "pulled_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "count": len(rows), "reports": rows}
    with open(os.path.join(out_dir, "reliefweb_climate.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    cols = ["date", "title", "source", "disaster_type", "theme", "format", "url", "excerpt", "id"]
    with open(os.path.join(out_dir, "reliefweb_climate.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def selftest():
    fake = {"data": [{"id": "1", "fields": {
        "title": "South Sudan: Flood update", "date": {"original": "2026-10-01T00:00:00+00:00"},
        "source": [{"name": "OCHA"}], "disaster_type": [{"name": "Flood"}],
        "theme": [{"name": "Climate Change and Environment"}], "format": [{"name": "Situation Report"}],
        "url_alias": "https://reliefweb.int/report/south-sudan/x", "body": "<p>Heavy   rain</p>"}}]}
    rows = parse(fake)
    assert rows[0]["date"] == "2026-10-01" and rows[0]["excerpt"] == "Heavy rain", rows
    p = build_payload(30)
    assert p["filter"]["conditions"][0]["value"] == COUNTRY
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out-dir", default="data")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    appname = os.environ.get("RELIEFWEB_APPNAME", "").strip()
    if not appname:
        sys.exit("RELIEFWEB_APPNAME is not set.")
    rows = parse(fetch(appname, a.days))
    save(rows, a.out_dir, a.days)
    print(f"{len(rows)} South Sudan climate-related reports from the last {a.days} days "
          f"-> {a.out_dir}/reliefweb_climate.json and .csv")
    for r in rows[:10]:
        print(f"  {r['date']}  {r['title'][:90]}  [{r['source']}]")


if __name__ == "__main__":
    main()
