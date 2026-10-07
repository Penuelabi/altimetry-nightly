#!/usr/bin/env python3
"""Probe which public machine-readable interfaces each South Sudan news site offers (RSS, sitemap, WordPress feed).
Respects robots.txt (skips disallowed paths) and never tries to get past a bot challenge. Writes a markdown table."""
import os, re, sys, time, urllib.request, urllib.error, urllib.robotparser

UA = "SuddClimateNewsArchive/1.0 (research; contact: penuelabi@gmail.com)"
SITES = {
 "Radio Yei": ["https://radioyei.org"],
 "Eye Radio": ["https://www.eyeradio.org"],
 "Sudans Post": ["https://www.sudanspost.com"],
 "Radio Tamazuj": ["https://www.radiotamazuj.org", "https://radiotamazuj.org"],
 "Radio Miraya": ["https://www.radiomiraya.org", "https://radiomiraya.org", "https://miraya.unmissions.org", "https://www.miraya.org"],
 "Gurtong": ["https://www.gurtong.net", "https://gurtong.net"],
 "Juba Monitor": ["https://www.jubamonitor.com", "https://jubamonitor.com"],
 "Nyamilepedia": ["https://www.nyamilepedia.com", "https://nyamilepedia.com"],
 "The City Review": ["https://cityreviewss.com", "https://www.cityreviewss.com", "https://cityreview.ss"],
 "South Sudan News Agency": ["https://www.southsudannewsagency.com", "https://southsudannewsagency.com"],
 "Radio Bakhita": ["https://www.radiobakhita.org", "https://radiobakhita.org"],
 "Sudan Tribune": ["https://sudantribune.com", "https://www.sudantribune.com"],
 "The Niles": ["https://www.theniles.org", "https://theniles.org"],
 "Voice of America": ["https://www.voanews.com"],
 "UN News (Africa)": ["https://news.un.org"],
 "Upper Nile Times": ["https://uppernile.net", "https://www.uppernile.net"],
 "Dawn FM / Salam FM": ["https://www.radiodabanga.org"],
}
SM_RE = r"(?im)^sitemap:\s*(\S+)"
PATHS = ["/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link", "/feed/", "/rss", "/rss.xml", "/sitemap.xml",
         "/wp-sitemap.xml", "/sitemap_index.xml", "/news-sitemap.xml"]


def kind(code, ctype, body):
    b = body[:600].lower()
    if code in (403, 429, 503) or "just a moment" in b or "cf-chl" in b or "captcha" in b or "attention required" in b:
        return f"BLOCKED/challenge ({code})"
    if code != 200:
        return f"HTTP {code}"
    if "json" in ctype or b.lstrip().startswith(("[", "{")):
        return "JSON ok"
    if "xml" in ctype or b.lstrip().startswith("<?xml") or "<rss" in b or "<urlset" in b or "<sitemapindex" in b:
        n = len(re.findall(r"<(?:item|url|sitemap)>", body[:2_000_000]))
        return f"XML ok ({n} entries in first 2MB)"
    return "HTML (not a feed)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.headers.get("content-type", ""), r.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", "") if e.headers else "", ""
    except Exception as e:
        return 0, "", type(e).__name__ + " " + str(e)[:60]


out = ["# News source probe", "", f"UA: `{UA}`", ""]
for name, bases in SITES.items():
    out.append(f"## {name}")
    live = None
    for base in bases:
        code, ct, body = get(base + "/")
        if code in (200, 301, 302, 403, 429, 503) or code == 0 and False:
            live = base
            out.append(f"- home `{base}/` -> {kind(code, ct, body) if code else 'no connection'} (HTTP {code})")
            break
        out.append(f"- home `{base}/` -> {'no connection: ' + body if code == 0 else 'HTTP ' + str(code)}")
    if not live:
        out.append("- **no reachable home page**\n")
        continue
    rp = urllib.robotparser.RobotFileParser()
    try:
        rcode, _, rbody = get(live + "/robots.txt")
        if rcode == 200:
            rp.parse(rbody.splitlines())
            sm = re.findall(SM_RE, rbody)[:4]
            out.append(f"- robots.txt found; sitemaps declared: {sm}")
        else:
            rp = None
            out.append(f"- robots.txt: HTTP {rcode} (no restriction)")
    except Exception:
        rp = None
    for path in PATHS:
        url = live + path
        if rp and not rp.can_fetch(UA, url):
            out.append(f"- `{path}` -> **robots.txt disallows**, not fetched")
            continue
        time.sleep(1)
        code, ct, body = get(url)
        out.append(f"- `{path}` -> {kind(code, ct, body)}")
    out.append("")
os.makedirs("news_probe_out", exist_ok=True)
open("news_probe_out/probe.md", "w").write("\n".join(out))
print("\n".join(out))
