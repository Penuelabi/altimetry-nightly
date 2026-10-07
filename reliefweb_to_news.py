#!/usr/bin/env python3
"""Stage (and optionally merge) ReliefWeb climate reports into data/news.json.

Standalone add-on. Reads data/reliefweb_climate.json (from reliefweb_climate_pull.py) and
data/ssd_county_population_2025.csv (county names). Modifies no existing script.

WHY THE REVIEW STEP: in bulletin_extras.py an item in news.json that names a county and has a
flood/heavy-rain or drought/dry-spell hazard is enough, on its own, to make that county RED
(NEWS_CONFIRM_DAYS = 21). So this script is deliberately conservative:
  * a county is tagged only when its name appears in the report TITLE as a whole word
    (never guessed from the body text; a body-only mention leaves counties empty = national/state item,
    which never confirms a county);
  * forecasts, outlooks, warnings, alerts and appeals are labelled 'Flood outlook' / 'Drought outlook'
    style hazards, which news_confirmations() ignores (NEWS_NOT_CONFIRMING);
  * default mode only STAGES: it writes data/news_reliefweb_staged.json for you to read.
    Nothing reaches news.json until you run with --apply.

Usage:
    python reliefweb_to_news.py              # stage only -> data/news_reliefweb_staged.json (+ printed table)
    python reliefweb_to_news.py --apply      # merge staged items into data/news.json (dedupe by url)
    python reliefweb_to_news.py --days 21    # window (default 21 = NEWS_DAYS)
    python reliefweb_to_news.py --selftest
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("AA_DATA_DIR") or os.path.join(HERE, "data")
SRC = os.path.join(DATA, "reliefweb_climate.json")
NEWS = os.path.join(DATA, "news.json")
STAGED = os.path.join(DATA, "news_reliefweb_staged.json")
POP = os.path.join(DATA, "ssd_county_population_2025.csv")

NOT_CONFIRMING = ("outlook", "forecast", "warning", "alert", "appeal", "preparedness", "scenario")
# order matters: first match wins
HAZARDS = [
    ("Flood", ("flood", "waterlog", "inundat", "overflow")),
    ("Heavy rainfall", ("heavy rain", "rainfall", "torrential")),
    ("Drought", ("drought",)),
    ("Dry spell", ("dry spell", "dry-spell", "below-normal rain", "below normal rain")),
]
GENERIC_FORECAST_SOURCES = ("ICPAC", "FAO", "SSMS", "WMO", "FEWS")
MAX_TEXT = 260


def load_counties():
    names = []
    with open(POP, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            n = (r.get("county") or "").strip()
            if n:
                names.append(n)
    return names


def find_counties(title, counties):
    t = f" {title} "
    out = []
    for c in counties:
        # whole-word, case-insensitive; "Juba" must not match "Jubaland"
        if re.search(rf"(?<![A-Za-z]){re.escape(c)}(?![A-Za-z])", t, re.I):
            out.append(c)
    # a county name that is a substring of a longer matched county (e.g. Akobo / Akobo East) -> keep the longer
    return [c for c in out if not any(c != o and c.lower() in o.lower() for o in out)]


def classify(title, excerpt):
    """(hazard label, confirming?) from title first, excerpt second."""
    blob_t = title.lower()
    blob = f"{title} {excerpt}".lower()
    hz = None
    for label, words in HAZARDS:
        if any(w in blob_t for w in words) or (hz is None and any(w in blob for w in words)):
            hz = label
            break
    if hz is None:
        return None, False
    if any(w in blob_t for w in NOT_CONFIRMING):
        return f"{hz} outlook", False
    return hz, True


def one_line(excerpt, title):
    s = re.sub(r"\s+", " ", excerpt or "").strip()
    s = re.sub(r"\.\.\.$", "", s)
    if not s:
        s = title
    if len(s) > MAX_TEXT:
        s = s[:MAX_TEXT].rsplit(" ", 1)[0] + "..."
    return s


def stage(reports, counties, today, days):
    items = []
    for r in reports:
        try:
            d = datetime.date.fromisoformat(r["date"])
        except (KeyError, ValueError):
            continue
        if d > today or (today - d).days > days:
            continue
        hz, confirming = classify(r.get("title", ""), r.get("excerpt", ""))
        if hz is None:
            continue
        cs = find_counties(r.get("title", ""), counties)
        src = r.get("source") or "ReliefWeb"
        items.append({
            "date": r["date"],
            "counties": cs,
            **({} if cs else {"scope": "National / state"}),
            "hazard": hz,
            "text": one_line(r.get("excerpt"), r.get("title", "")),
            "source": f"ReliefWeb ({src})",
            "url": r.get("url", ""),
            "_review": ("COUNTY-CONFIRMING: would count toward red for " + ", ".join(cs)) if (cs and confirming)
                       else "no effect on alerts (outlook/forecast or no county named in title)",
        })
    items.sort(key=lambda i: i["date"], reverse=True)
    return items


def merge(news, staged):
    have = {i.get("url") for i in news.get("items", [])}
    added = []
    for it in staged:
        if it["url"] in have:
            continue
        clean = {k: v for k, v in it.items() if k != "_review"}
        news.setdefault("items", []).append(clean)
        added.append(clean)
    news["items"].sort(key=lambda i: str(i.get("date")), reverse=True)
    return added


def selftest():
    cs = ["Juba", "Akobo", "Akobo East", "Fangak"]
    assert find_counties("Floods in Akobo East County", cs) == ["Akobo East"]
    assert find_counties("Jubaland drought", cs) == []
    assert classify("Flood update: Fangak", "") == ("Flood", True)
    assert classify("Flood outlook for Juba", "")[1] is False
    assert classify("Food security bulletin", "") == (None, False)
    rep = [{"date": "2026-10-02", "title": "South Sudan: Flooding in Fangak County", "excerpt": "Heavy rain...",
            "source": "OCHA", "url": "u1"},
           {"date": "2026-10-03", "title": "Weekly forecast heavy rainfall", "excerpt": "", "source": "FAO", "url": "u2"}]
    s = stage(rep, cs, datetime.date(2026, 10, 7), 21)
    assert s[1]["counties"] == ["Fangak"] and s[1]["_review"].startswith("COUNTY")
    assert s[0]["hazard"].endswith("outlook") or s[0]["counties"] == []
    news = {"items": [{"url": "u1", "date": "2026-10-02"}]}
    assert [i["url"] for i in merge(news, s)] == ["u2"]
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="merge staged items into data/news.json")
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not os.path.exists(SRC):
        sys.exit(f"{SRC} not found: run reliefweb_climate_pull.py first.")
    reports = json.load(open(SRC, encoding="utf-8")).get("reports", [])
    items = stage(reports, load_counties(), datetime.date.today(), a.days)
    json.dump({"_note": "Staged ReliefWeb items. Review, then run reliefweb_to_news.py --apply.", "items": items},
              open(STAGED, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(items)} ReliefWeb items staged -> {STAGED}")
    for i in items:
        print(f"  {i['date']} [{i['hazard']}] {','.join(i['counties']) or '-'}  | {i['_review']}")
    if a.apply:
        news = json.load(open(NEWS, encoding="utf-8"))
        added = merge(news, items)
        json.dump(news, open(NEWS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"APPLIED: {len(added)} new item(s) added to {NEWS}")
    else:
        print("Not applied. Re-run with --apply to merge into data/news.json.")


if __name__ == "__main__":
    main()
