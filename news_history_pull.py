#!/usr/bin/env python3
"""Historical South Sudan climate-news harvest (2016 -> today) into one Excel workbook.

Standalone add-on: reads data/ssd_county_population_2025.csv (county -> state) and writes only to
OUT_DIR (default data/news_history). Modifies no existing script and does not touch data/news.json.

Sources
  * ReliefWeb API (needs RELIEFWEB_APPNAME; run it in GitHub Actions where the secret exists)
  * WordPress news sites through their public /wp-json/wp/v2/posts search feed:
    Radio Yei, Eye Radio, Sudans Post, Radio Tamazuj, Radio Miraya, Gurtong, Juba Monitor ...
    (see SITES; add more with one line). Each site's robots.txt is checked with this script's own
    User-Agent first; a site that disallows it, or has no feed, is skipped and listed on the Coverage sheet.

Per article it extracts: state, county, year, month, date, narrative, households (HH), individuals,
the sentence the figures came from, hazard, source and link. Extraction is rule-based (see METHOD):
treat every row as a lead to verify against the link, not as a finished statistic.

    python news_history_pull.py --from 2016-01-01                 # everything
    python news_history_pull.py --from 2025-01-01 --sites radioyei,eyeradio
    python news_history_pull.py --selftest
"""
import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("AA_DATA_DIR") or os.path.join(HERE, "data")
OUT_DIR = os.environ.get("NEWS_HISTORY_OUT") or os.path.join(DATA, "news_history")
POP = os.path.join(DATA, "ssd_county_population_2025.csv")
UA = "SuddClimateNewsArchive/1.0 (research; contact: penuelabi@gmail.com)"
MAX_SITE_SECONDS = 35 * 60   # per-site time budget
PAUSE = 0.8          # seconds between requests to any one site

SITES = {  # key: (display name, base url)
    "radioyei": ("Radio Yei", "https://radioyei.org"),
    "eyeradio": ("Eye Radio", "https://www.eyeradio.org"),
    "sudanspost": ("Sudans Post", "https://www.sudanspost.com"),
    "tamazuj": ("Radio Tamazuj", "https://www.radiotamazuj.org"),
    "miraya": ("Radio Miraya", "https://radiomiraya.org"),
    "gurtong": ("Gurtong", "https://www.gurtong.net"),
    "jubamonitor": ("Juba Monitor", "https://www.jubamonitor.com"),
    "nyamilepedia": ("Nyamilepedia", "https://www.nyamilepedia.com"),
    "cityreview": ("The City Review", "https://cityreviewss.com"),
}
SEARCH_TERMS = ["flood", "drought", "dry spell", "heavy rain", "rainfall"]   # WordPress search is substring-based: "flood" also finds flooding/floods
HAZARDS = [("Flood", ("flood", "waterlog", "inundat", "submerged", "overflow", "dyke", "dike breach")),
           ("Heavy rainfall", ("heavy rain", "torrential", "downpour", "rainstorm")),
           ("Drought", ("drought", "dry spell", "dry-spell", "crop failure", "water shortage")),
           ]
HAZ_WORDS = [w for _, ws in HAZARDS for w in ws] + ["rainfall", "rains"]
SELF_NAMES = re.compile(r"radio\s+yei|eye\s+radio|radio\s+tamazuj|radio\s+miraya|sudans?\s+post|juba\s+monitor|"
                        r"the\s+city\s+review|city\s+review|gurtong", re.I)
STATES = ["Central Equatoria", "Eastern Equatoria", "Western Equatoria", "Jonglei", "Lakes", "Unity",
          "Upper Nile", "Warrap", "Northern Bahr el Ghazal", "Western Bahr el Ghazal", "Ruweng",
          "Greater Pibor", "Abyei"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ------------------------------------------------------------------ helpers
def log(*a):
    print(*a, file=sys.stderr, flush=True)


_last = defaultdict(float)


def http_json(url, post=None, host_key=None, tries=3, timeout=25):
    for k in range(tries):
        wait = PAUSE - (time.time() - _last[host_key])
        if wait > 0:
            time.sleep(wait)
        _last[host_key] = time.time()
        data = json.dumps(post).encode() if post is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if post is not None else "GET",
                                     headers={"User-Agent": UA, "Accept": "application/json",
                                              **({"Content-Type": "application/json"} if post is not None else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace")), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code == 400:                      # WordPress: page number beyond the last page
                return None, {}
            if e.code in (429, 500, 502, 503, 504) and k < tries - 1:
                time.sleep(5 * (k + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if k < tries - 1:
                time.sleep(4 * (k + 1))
                continue
            raise
    return None, {}


def robots_ok(base, path="/wp-json/wp/v2/posts"):
    rp = urllib.robotparser.RobotFileParser()
    try:
        req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            rp.parse(r.read().decode("utf-8", "replace").splitlines())
    except urllib.error.HTTPError as e:
        return e.code != 401 and e.code != 403            # no robots.txt (404) = no restriction
    except Exception:
        return True
    return rp.can_fetch(UA, base + path)


def strip_html(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s or "")
    s = re.sub(r"(?i)</(p|div|li|h\d|br)\s*>|<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace(" ", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


# ------------------------------------------------------------------ geography
def load_geo():
    county_state = {}
    with open(POP, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            c, s = (r.get("county") or "").strip(), (r.get("state") or "").strip()
            if c:
                county_state[c] = s
    # longest first so "Akobo East" wins over "Akobo"
    names = sorted(county_state, key=len, reverse=True)
    pats = {c: re.compile(rf"(?<![A-Za-z]){re.escape(c)}(?![A-Za-z])", re.I) for c in names}
    return county_state, pats


TOWN_TO_COUNTY = {"Bentiu": "Rubkona", "Bor": "Bor South", "Nimule": "Magwi", "Kuajok": "Gogrial West",
                  "Rumbek": "Rumbek Centre", "Mingkaman": "Awerial", "Yida": "Pariang", "Aweil": "Aweil Centre",
                  "Torit": "Torit", "Yambio": "Yambio", "Wau": "Wau", "Malakal": "Malakal"}


def locate(title, body, geo):
    """-> (state, county, other counties, basis). Title match wins; a body-only county needs >=2 mentions
    (>=3 for Juba, which is often just 'the capital') or a mention in the opening lines."""
    county_state, pats = geo
    t = SELF_NAMES.sub(" ", title or "")
    b = SELF_NAMES.sub(" ", body or "")
    head = b[:350]
    in_title, counts, in_head = [], Counter(), set()
    for c, p in pats.items():
        if p.search(t):
            in_title.append(c)
        n = len(p.findall(b))
        if n:
            counts[c] = n
        if p.search(head):
            in_head.add(c)
    for town, c in TOWN_TO_COUNTY.items():
        if c in county_state and c not in counts or c not in in_title:
            rx = re.compile(rf"(?<![A-Za-z]){town}(?![A-Za-z])")
            if c in county_state and rx.search(t) and c not in in_title:
                in_title.append(c)
            elif c in county_state and (n := len(rx.findall(b))):
                counts[c] += n

    def drop_sub(lst):
        return [c for c in lst if not any(c != o and c.lower() in o.lower() for o in lst)]

    in_title = drop_sub(in_title)
    body_ok = [c for c, n in counts.most_common()
               if (n >= 3) or (c != "Juba" and (n >= 2 or c in in_head))]
    allc = drop_sub(list(dict.fromkeys(in_title + body_ok)))
    primary = in_title[0] if in_title else (allc[0] if allc else "")
    state = county_state.get(primary, "")
    if not state:
        blob = f"{t} {b[:1500]}"
        hit = [s for s in STATES if re.search(rf"(?<![A-Za-z]){re.escape(s)}(?![A-Za-z])", blob, re.I)]
        state = hit[0] if hit else ""
    basis = "title" if in_title else ("body" if primary else ("state only" if state else "not found"))
    return state, primary, "; ".join(c for c in allc[:8] if c != primary), basis


# ------------------------------------------------------------------ numbers
_NUM = r"(\d{1,3}(?:[,\s]\d{3})+|\d+(?:\.\d+)?)\s*(million|thousand|k|m)?\b"
HH_RE = re.compile(_NUM + r"\s+(?:(?:flood|displaced|affected|vulnerable|returnee|IDP)\s+)?"
                   r"(households?|house-?holds?|HHs?|families)\b", re.I)
HH_RE2 = re.compile(r"\b(?:households?|HHs?)\s*(?:\(HH\)\s*)?(?:of|:|totaling|totalling|number(?:ing)?)?\s*" + _NUM, re.I)
IND_RE = re.compile(_NUM + r"\s+(?:\w+\s+){0,2}?(people|persons|individuals|residents|civilians|children|IDPs|"
                    r"inhabitants|villagers|farmers|pupils|students|women)\b", re.I)
MEASURE = [("displaced", r"displac|fled|flee|relocat|evacuat|homeless|stranded|marooned|IDP"),
           ("affected", r"affect|impact|hit by|victim"),
           ("in need", r"in need|needing|requir|food insecur|IPC")]


def to_num(txt, unit):
    n = float(re.sub(r"[,\s]", "", txt))
    u = (unit or "").lower()
    if u in ("million", "m"):
        n *= 1_000_000
    elif u in ("thousand", "k"):
        n *= 1_000
    return int(round(n))


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def extract_numbers(text, county="", state=""):
    """-> dict(households, individuals, measure, scope, figure_context, all_figures).
    Figures in a sentence that names the article's county rank first, then its state, then the rest."""
    figs = []
    for sent in sentences(text):
        low = sent.lower()
        scope = 2 if county and re.search(re.escape(county), sent, re.I) else (
            1 if state and re.search(re.escape(state), sent, re.I) else 0)
        for rx, kind in ((HH_RE, "HH"), (HH_RE2, "HH"), (IND_RE, "Ind")):
            for m in rx.finditer(sent):
                num, unit = m.group(1), m.group(2)
                try:
                    v = to_num(num, unit)
                except ValueError:
                    continue
                if not unit and 1990 <= v <= 2035 and "," not in num:        # a year, not a count
                    continue
                if v < 5 or v > 40_000_000:
                    continue
                meas = next((n for n, p in MEASURE if re.search(p, low)), "reported")
                figs.append((kind, v, meas, sent, scope))

    def pick(kind):
        lst = [f for f in figs if f[0] == kind]
        if not lst:
            return None
        return max(lst, key=lambda f: (f[4], f[2] in ("displaced", "affected"), f[1]))

    best_hh, best_ind = pick("HH"), pick("Ind")
    chosen = [f for f in (best_ind, best_hh) if f]
    top = max((f[4] for f in chosen), default=-1)
    return {
        "households": best_hh[1] if best_hh else None,
        "individuals": best_ind[1] if best_ind else None,
        "measure": (best_ind or best_hh or (None, None, ""))[2],
        "scope": {2: "county named in same sentence", 1: "state named in same sentence", 0: "wider / not specified",
                  -1: ""}[top],
        "figure_context": " | ".join(dict.fromkeys(f[3] for f in chosen))[:500],
        "all_figures": "; ".join(f"{f[1]:,} {'HH' if f[0]=='HH' else 'ind'} ({f[2]})" for f in figs[:8]),
    }


def hazard_of(title, body):
    t = (title or "").lower()
    b = f"{t} {(body or '').lower()}"
    for label, ws in HAZARDS:
        if any(w in t for w in ws):
            return label
    for label, ws in HAZARDS:
        if sum(b.count(w) for w in ws) >= 3:
            return label
    return ""


def narrative(title, body):
    keep = [s for s in sentences(body) if any(w in s.lower() for w in HAZ_WORDS)]
    txt = " ".join(keep[:3]) or " ".join(sentences(body)[:2])
    txt = re.sub(r"\s+", " ", txt)
    return (txt[:480].rsplit(" ", 1)[0] + "...") if len(txt) > 480 else txt


def make_row(source, date_iso, title, body, url, geo):
    haz = hazard_of(title, body)
    if not haz:
        return None
    d = dt.date.fromisoformat(date_iso[:10])
    state, county, counties_all, basis = locate(title, body, geo)
    nums = extract_numbers(f"{title}. {body}", county, state)
    return {
        "state": state, "county": county, "year": d.year, "month": d.month, "month_name": MONTHS[d.month - 1],
        "date": d.isoformat(), "hazard": haz, "title": (title or "").strip(),
        "narrative": narrative(title, body), "households_HH": nums["households"],
        "individuals": nums["individuals"], "figure_measure": nums["measure"], "figure_scope": nums["scope"],
        "figure_context": nums["figure_context"], "all_figures_found": nums["all_figures"],
        "other_counties_named": counties_all, "source": source, "link": url,
        "location_basis": basis,
    }


# ------------------------------------------------------------------ fetchers
def fetch_wp(key, since, until, geo, stats):
    name, base = SITES[key]
    st = stats[name] = {"status": "", "fetched": 0, "kept": 0, "earliest": "", "latest": ""}
    if not robots_ok(base):
        st["status"] = "skipped: robots.txt disallows automated access"
        log(name, st["status"])
        return []
    rows, seen = [], set()
    year0, year1 = since.year, until.year
    fails = 0
    t_start = time.time()
    for term in SEARCH_TERMS:
        if fails >= 3 or time.time() - t_start > MAX_SITE_SECONDS:
            st["status"] = st["status"] or ("stopped: repeated errors" if fails >= 3 else "stopped: time budget reached")
            break
        for y in range(year0, year1 + 1):
            if fails >= 3 or time.time() - t_start > MAX_SITE_SECONDS:
                break
            after = max(since, dt.date(y, 1, 1)).isoformat() + "T00:00:00"
            before = min(until, dt.date(y, 12, 31)).isoformat() + "T23:59:59"
            page = 1
            while page <= 60:
                q = urllib.parse.urlencode({"search": term, "per_page": 100, "page": page, "after": after,
                                            "before": before, "orderby": "date", "order": "asc",
                                            "_fields": "id,date,link,title,content"})
                try:
                    data, hdr = http_json(f"{base}/wp-json/wp/v2/posts?{q}", host_key=key)
                except Exception as e:
                    fails += 1
                    st["status"] = st["status"] or f"partial: {type(e).__name__} {e}"[:120]
                    log(name, term, y, "error", e)
                    break
                fails = 0
                if not data:
                    break
                for p in data:
                    if p["id"] in seen:
                        continue
                    seen.add(p["id"])
                    st["fetched"] += 1
                    title = strip_html((p.get("title") or {}).get("rendered", ""))
                    body = strip_html((p.get("content") or {}).get("rendered", ""))
                    r = make_row(name, p["date"], title, body, p["link"], geo)
                    if r:
                        rows.append(r)
                if len(data) < 100:
                    break
                page += 1
    if not st["status"]:
        st["status"] = "ok" if st["fetched"] else "no posts returned (feed missing or empty)"
    st["kept"] = len(rows)
    ds = sorted(r["date"] for r in rows)
    st["earliest"], st["latest"] = (ds[0], ds[-1]) if ds else ("", "")
    log(name, st)
    return rows


def fetch_reliefweb(since, until, geo, stats):
    name = "ReliefWeb"
    st = stats[name] = {"status": "", "fetched": 0, "kept": 0, "earliest": "", "latest": ""}
    app = os.environ.get("RELIEFWEB_APPNAME", "").strip()
    if not app:
        st["status"] = "skipped: RELIEFWEB_APPNAME not set"
        return []
    rows, offset = [], 0
    kw = ('flood OR flooding OR drought OR "dry spell" OR "heavy rain" OR rainfall OR waterlogging OR '
          '"climate change" OR "El Nino" OR displacement')
    while True:
        payload = {"limit": 200, "offset": offset, "sort": ["date.original:asc"],
                   "fields": {"include": ["title", "date.original", "source.name", "url_alias", "body"]},
                   "query": {"value": kw, "operator": "OR"},
                   "filter": {"operator": "AND", "conditions": [
                       {"field": "country.name", "value": "South Sudan"},
                       {"field": "date.original", "value": {"from": since.isoformat() + "T00:00:00+00:00",
                                                            "to": until.isoformat() + "T23:59:59+00:00"}},
                       {"operator": "OR", "conditions": [
                           {"field": "disaster_type.name", "value": ["Flood", "Flash Flood", "Drought"], "operator": "OR"},
                           {"field": "theme.name", "value": ["Climate Change and Environment"]}]}]}}
        try:
            data, _ = http_json(f"https://api.reliefweb.int/v2/reports?appname={app}", post=payload, host_key="rw")
        except Exception as e:
            st["status"] = f"partial: {type(e).__name__} {e}"[:120]
            break
        items = (data or {}).get("data", [])
        if not items:
            break
        for it in items:
            f = it.get("fields", {})
            st["fetched"] += 1
            src = f.get("source") or []
            sname = (src[0].get("name") if src and isinstance(src[0], dict) else "") or "ReliefWeb"
            r = make_row(f"ReliefWeb ({sname})", (f.get("date") or {}).get("original", ""),
                         f.get("title", ""), strip_html(f.get("body", "")), f.get("url_alias") or "", geo)
            if r:
                rows.append(r)
        offset += len(items)
        if len(items) < 200:
            break
    if not st["status"]:
        st["status"] = "ok"
    st["kept"] = len(rows)
    ds = sorted(r["date"] for r in rows)
    st["earliest"], st["latest"] = (ds[0], ds[-1]) if ds else ("", "")
    log(name, st)
    return rows


# ------------------------------------------------------------------ output
COLS = ["state", "county", "year", "month", "month_name", "date", "hazard", "title", "narrative", "households_HH",
        "individuals", "figure_measure", "figure_scope", "figure_context", "all_figures_found", "other_counties_named",
        "source", "link", "location_basis", "possible_duplicate_of"]

METHOD = [
    "WHAT THIS IS: a lead list built by software from public news and ReliefWeb. It is NOT verified data.",
    "Selection: an article is kept when its title or text clearly concerns flooding, heavy rain or drought (Hazard column).",
    "County/state: county names (79-county list used by the bulletin) are matched as whole words, title first, then most-mentioned in the text; "
    "state comes from the county. If no county is named, the state is taken from a state name in the text, else left blank. "
    "Pre-2020 county names and boundaries differ from the 2025 list, so older rows may show no county. 'Location_basis' says where the match came from.",
    "Figures: households (HH) and individuals are read from sentences such as '12,000 households' or '45,000 people affected/displaced'. "
    "When an article has several, the largest figure tied to 'affected' or 'displaced' is reported; every figure found is in All_figures_found. "
    "The figure may be a national or state total rather than the county's, and may repeat across outlets: do not sum rows.",
    "Possible_duplicate_of: rows with the same county, month and individuals/HH figure from another link.",
    "Media coverage differs by year (many outlets started after 2016) and search only returns posts the site's own search finds. "
    "See the Coverage sheet for what each source returned and any site skipped (robots.txt, no feed, errors).",
    "Check every number against the link before using it in a report.",
]


def flag_duplicates(rows):
    seen = {}
    for r in sorted(rows, key=lambda x: x["date"]):
        fig = r["individuals"] or r["households_HH"]
        r["possible_duplicate_of"] = ""
        if r["county"] and fig:
            k = (r["county"], r["year"], r["month"], fig)
            if k in seen:
                r["possible_duplicate_of"] = seen[k]
            else:
                seen[k] = r["link"]


def write_outputs(rows, stats, out_dir, since, until):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    os.makedirs(out_dir, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["date"], r["source"]), reverse=True)
    flag_duplicates(rows)
    with open(os.path.join(out_dir, "south_sudan_climate_news.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    wb = Workbook()
    hdr_font, hdr_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")

    def sheet(ws, header, data, widths=None):
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill, c.alignment = hdr_font, hdr_fill, Alignment(vertical="top", wrap_text=True)
        for row in data:
            ws.append(row)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, h in enumerate(header, 1):
            ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(h, max(10, min(28, len(str(h)) + 4)))

    ws = wb.active
    ws.title = "Events"
    widths = {"title": 50, "narrative": 70, "figure_context": 55, "figure_scope": 26, "all_figures_found": 38, "link": 50,
              "other_counties_named": 28, "source": 24, "state": 22, "county": 16}
    sheet(ws, COLS, [[r.get(c) for c in COLS] for r in rows], widths)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if c.column_letter in ("I", "H", "M"):
                c.alignment = Alignment(wrap_text=True, vertical="top")
        link = row[COLS.index("link")]
        if link.value:
            link.hyperlink = link.value
            link.font = Font(color="0563C1", underline="single")
    for col in ("households_HH", "individuals"):
        L = get_column_letter(COLS.index(col) + 1)
        for c in ws[L][1:]:
            c.number_format = "#,##0"

    # monthly summary: articles per month by hazard, plus the biggest individuals figure that month
    by_m = defaultdict(lambda: {"Flood": 0, "Heavy rainfall": 0, "Drought": 0, "n": 0, "maxind": 0, "maxhh": 0,
                                "counties": set(), "src": set()})
    for r in rows:
        m = by_m[(r["year"], r["month"])]
        m[r["hazard"]] += 1
        m["n"] += 1
        m["maxind"] = max(m["maxind"], r["individuals"] or 0)
        m["maxhh"] = max(m["maxhh"], r["households_HH"] or 0)
        if r["county"]:
            m["counties"].add(r["county"])
        m["src"].add(r["source"].split(" (")[0])
    data = []
    for (y, mo) in sorted(by_m, reverse=True):
        m = by_m[(y, mo)]
        data.append([y, mo, MONTHS[mo - 1], m["n"], m["Flood"], m["Heavy rainfall"], m["Drought"],
                     len(m["counties"]), m["maxind"] or None, m["maxhh"] or None, len(m["src"])])
    sheet(wb.create_sheet("Monthly"), ["year", "month", "month_name", "articles", "flood", "heavy_rainfall", "drought",
                                       "counties_named", "largest_individuals_figure", "largest_HH_figure", "sources"], data)

    by_sy = defaultdict(lambda: [0, 0, 0, set()])
    for r in rows:
        k = (r["state"] or "(not identified)", r["year"])
        by_sy[k][0] += 1
        by_sy[k][1] = max(by_sy[k][1], r["individuals"] or 0)
        by_sy[k][2] = max(by_sy[k][2], r["households_HH"] or 0)
        if r["county"]:
            by_sy[k][3].add(r["county"])
    sheet(wb.create_sheet("State-Year"), ["state", "year", "articles", "largest_individuals_figure", "largest_HH_figure",
                                          "counties_named"],
          [[s, y, v[0], v[1] or None, v[2] or None, "; ".join(sorted(v[3]))] for (s, y), v in sorted(by_sy.items())],
          {"counties_named": 60, "state": 24})

    sheet(wb.create_sheet("Coverage"), ["source", "status", "posts_fetched", "rows_kept", "earliest", "latest"],
          [[n, s["status"], s["fetched"], s["kept"], s["earliest"], s["latest"]] for n, s in stats.items()],
          {"status": 60, "source": 24})
    wm = wb.create_sheet("Method and caveats")
    wm.column_dimensions["A"].width = 140
    wm.append([f"Window {since} to {until}. Built {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC."])
    for line in METHOD:
        wm.append([line])
    for r in wm.iter_rows():
        r[0].alignment = Alignment(wrap_text=True, vertical="top")
    path = os.path.join(out_dir, f"south_sudan_climate_news_{since.year}_{until.year}.xlsx")
    wb.save(path)
    return path


# ------------------------------------------------------------------ self-test
def selftest():
    geo = load_geo()
    t = ("Floods displace 12,000 households in Fangak County, Jonglei State. Over 72,000 people have been affected "
         "since August, the commissioner said. Radio Yei reported the figures. In 2019 more were hit.")
    r = make_row("Radio Yei", "2021-10-05T10:00:00", "Floods displace thousands in Fangak", t, "http://x/1", geo)
    assert r["county"] == "Fangak" and r["state"] == "Jonglei", r
    assert r["households_HH"] == 12000 and r["individuals"] == 72000, r
    assert r["year"] == 2021 and r["month"] == 10 and r["hazard"] == "Flood"
    assert locate("News from Radio Yei", "Radio Yei says", geo)[1] == ""
    assert locate("Warrap appeal", "Warrap needs help. Aid reached Juba once.", geo)[1] == ""
    assert locate("Bentiu flood crisis", "x", geo)[1] == "Rubkona"          # site name is not the county Yei
    assert extract_numbers("About 1.2 million people are facing hunger.")["individuals"] == 1_200_000
    assert extract_numbers("In 2019 people moved.")["individuals"] is None
    assert extract_numbers("25k households were affected")["households"] == 25000
    assert make_row("x", "2020-01-01", "Peace talks", "No weather here", "u", geo) is None
    rows = [r, dict(r, link="http://x/2")]
    stats = {"Radio Yei": {"status": "ok", "fetched": 2, "kept": 2, "earliest": "2021-10-05", "latest": "2021-10-05"}}
    p = write_outputs(rows, stats, "/tmp/nh_selftest", dt.date(2016, 1, 1), dt.date(2026, 10, 7))
    from openpyxl import load_workbook
    wb = load_workbook(p)
    assert wb.sheetnames == ["Events", "Monthly", "State-Year", "Coverage", "Method and caveats"], wb.sheetnames
    ev = wb["Events"]
    assert ev.max_row == 3 and ev["S3"].value or ev["S2"].value, "duplicate flag"
    print("selftest OK ->", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="since", default="2016-01-01")
    ap.add_argument("--to", dest="until", default=dt.date.today().isoformat())
    ap.add_argument("--sites", default=",".join(SITES), help="comma list of keys; 'none' to skip media")
    ap.add_argument("--no-reliefweb", action="store_true")
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    since, until = dt.date.fromisoformat(a.since), dt.date.fromisoformat(a.until)
    geo = load_geo()
    stats, rows = {}, []
    if not a.no_reliefweb:
        rows += fetch_reliefweb(since, until, geo, stats)
    for key in [k.strip() for k in a.sites.split(",") if k.strip() and k.strip() != "none"]:
        if key not in SITES:
            log("unknown site", key)
            continue
        rows += fetch_wp(key, since, until, geo, stats)
    path = write_outputs(rows, stats, a.out_dir, since, until)
    print(f"{len(rows)} rows -> {path}")
    for n, s in stats.items():
        print(f"  {n}: {s['status']} | fetched {s['fetched']} | kept {s['kept']} | {s['earliest']}..{s['latest']}")


if __name__ == "__main__":
    main()
