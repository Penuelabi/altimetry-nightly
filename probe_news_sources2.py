#!/usr/bin/env python3
"""Second probe: how deep do the sitemaps go, and why did the WordPress query fail on some sites. Respects robots.txt."""
import os, re, time, urllib.request, urllib.error, urllib.robotparser, urllib.parse
UA = "SuddClimateNewsArchive/1.0 (research; contact: penuelabi@gmail.com)"
def get(url, n=400_000):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            return r.status, r.headers.get("content-type", ""), r.read(n).decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", "", url
    except Exception as e:
        return 0, "", type(e).__name__, url
out = []
def P(*a): out.append(" ".join(str(x) for x in a))

# 1. exact harvest query on the WP sites that returned JSON in probe 1
for name, base in [("Sudans Post", "https://www.sudanspost.com"), ("Radio Miraya", "https://www.radiomiraya.org"),
                   ("Radio Miraya (no www)", "https://radiomiraya.org"), ("The Niles", "https://www.theniles.org")]:
    for q in ({"search": "flood", "per_page": 5, "after": "2020-01-01T00:00:00", "before": "2020-12-31T23:59:59", "_fields": "id,date,link,title"},
              {"search": "flood", "per_page": 5, "_fields": "id,date,link,title"},
              {"per_page": 3, "_fields": "id,date,link"}):
        time.sleep(1.2)
        u = f"{base}/wp-json/wp/v2/posts?" + urllib.parse.urlencode(q)
        c, ct, body, final = get(u, 600)
        P(f"- {name} `{ {k: v for k, v in q.items() if k != '_fields'} }` -> HTTP {c}, {ct.split(';')[0]}, final={final[:60] if final != u else 'same'}, starts: `{body[:110].strip()!r}`")

# 2. robots.txt of Tamazuj (Disallow lines) and sitemap depth for the sites with sitemaps
P("\n## Radio Tamazuj robots.txt (Disallow/Allow lines)")
c, ct, b, _ = get("https://www.radiotamazuj.org/robots.txt")
P("\n".join("    " + l for l in b.splitlines() if re.match(r"(?i)\s*(user-agent|disallow|allow|crawl-delay)", l))[:1500])

def sitemap_children(url, label):
    c, ct, b, _ = get(url, 2_000_000)
    P(f"\n## {label}: {url} -> HTTP {c}")
    kids = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>\s*([^<\s]+)\s*</lastmod>)?", b)
    P(f"  {len(kids)} entries; first/last: {kids[:3]} ... {kids[-3:]}")
    return [k[0] for k in kids]

for label, u in [("Radio Yei", "https://radioyei.org/sitemap.xml"), ("Radio Tamazuj", "https://www.radiotamazuj.org/en/sitemap_index.xml"),
                 ("Radio Tamazuj wp-sitemap", "https://www.radiotamazuj.org/wp-sitemap.xml"), ("Sudans Post", "https://www.sudanspost.com/sitemap.xml"),
                 ("Radio Miraya", "https://www.radiomiraya.org/sitemap_index.xml"), ("Gurtong", "https://www.gurtong.net/sitemap.xml")]:
    time.sleep(1.2)
    kids = sitemap_children(u, label)
    # one level deeper: the first post-type sitemap, to see the date range and whether article URLs carry words
    post = [k for k in kids if re.search(r"post|news|article|node|story|\d{4}", k, re.I)]
    for k in post[:1] + post[-1:]:
        time.sleep(1.2)
        c, ct, b, _ = get(k, 3_000_000)
        urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>\s*([^<\s]+)\s*</lastmod>)?", b)
        P(f"  child {k} -> HTTP {c}, {len(urls)} urls, lastmod range {min([u[1] for u in urls if u[1]] or [''])} .. {max([u[1] for u in urls if u[1]] or [''])}; sample {urls[:2]}")

# 3. RSS depth for Tamazuj (allowed by robots) and whether article pages are fetchable
rp = urllib.robotparser.RobotFileParser(); c, ct, b, _ = get("https://www.radiotamazuj.org/robots.txt"); rp.parse(b.splitlines())
P("\n## Tamazuj robots on sample article path:", rp.can_fetch(UA, "https://www.radiotamazuj.org/en/news/article/example"), "| paged feed:", rp.can_fetch(UA, "https://www.radiotamazuj.org/feed/?paged=2"))
os.makedirs("news_probe_out", exist_ok=True)
open("news_probe_out/probe2.md", "w").write("# Probe 2\n\n" + "\n".join(out))
print("\n".join(out))
