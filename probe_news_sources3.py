import os, re, time, urllib.request, urllib.error, urllib.parse, json
UA = "SuddClimateNewsArchive/1.0 (research; contact: penuelabi@gmail.com)"
def get(url, n=3_000_000, hdrs=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, **(hdrs or {})}), timeout=40) as r:
            return r.status, r.headers.get("content-type", ""), r.read(n).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, "", ""
    except Exception as e:
        return 0, "", type(e).__name__ + str(e)[:50]
out = []
P = lambda *a: out.append(" ".join(str(x) for x in a))
loc = lambda b: re.findall(r"<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>\s*([^<\s]+)\s*</lastmod>)?", b)


def sec0():
    P("## Sudans Post: which request shape fails")
    for pp, fields in [(100, "id,date,link,title,content"), (50, "id,date,link,title,content"), (20, "id,date,link,title,content"), (100, "id,date,link,title")]:
        time.sleep(1.5)
        q = urllib.parse.urlencode({"search": "flood", "per_page": pp, "page": 1, "after": "2021-01-01T00:00:00", "before": "2021-12-31T23:59:59", "orderby": "date", "order": "asc", "_fields": fields})
        c, ct, b = get("https://www.sudanspost.com/wp-json/wp/v2/posts?" + q, 80)
        P(f"- per_page={pp} fields={fields}: HTTP {c} {ct.split(';')[0]} starts {b[:70]!r}")
try:
    sec0()
except Exception as e:
    P('SECTION 0 ERROR', type(e).__name__, e)

def sec1():
    P("\n## Radio Yei sitemap-index-1.xml children")
    c, ct, b = get("https://radioyei.org/sitemap-index-1.xml")
    kids = loc(b); P(f"HTTP {c}: {len(kids)} children: {kids[:12]}")
    for k, _ in kids[:1] + kids[-1:]:
        time.sleep(1.5); c, ct, b2 = get(k); u = loc(b2)
        P(f"  {k}: HTTP {c}, {len(u)} urls, lastmod {min([x[1] for x in u if x[1]] or [''])} .. {max([x[1] for x in u if x[1]] or [''])}, sample {u[:2]}")
try:
    sec1()
except Exception as e:
    P('SECTION 1 ERROR', type(e).__name__, e)

def sec2():
    P("\n## Radio Tamazuj sitemap list")
    c, ct, b = get("https://www.radiotamazuj.org/wp-sitemap.xml"); names = loc(b)
    P("names:", [n[0].rsplit("/", 1)[-1] for n in names])
    posts = [n for n in names if re.search(r"/post-sitemap\d*\.xml$", n[0])]
    P(f"{len(posts)} post sitemaps")
    for k, lm in posts[:3] + posts[-2:]:
        time.sleep(1.5); c, ct, b2 = get(k); u = loc(b2)
        P(f"  {k.rsplit('/',1)[-1]}: HTTP {c}, {len(u)} urls, per-url lastmod {min([x[1] for x in u if x[1]] or [''])[:10]} .. {max([x[1] for x in u if x[1]] or [''])[:10]}; sample {[x[0] for x in u[:3]]}")
    # one article page: is date/title parsable without JS?
    if posts:
        time.sleep(1.5); c, ct, b2 = get(posts[1][0]); u = loc(b2)
        art = next((x[0] for x in u if "/news/article/" in x[0] or re.search(r"flood|drought", x[0])), u[0][0] if u else "")
        time.sleep(1.5); c, ct, h = get(art, 400_000)
        OG = re.compile(r'og:title.{0,10}content=.([^"]+)'); PUB = re.compile(r'article:published_time.{0,10}content=.([^"]+)')
    og = OG.findall(h)[:1]; pub = PUB.findall(h)[:1]
    P("article", art, "HTTP", c, len(h), "bytes; og:title=", og, "published=", pub, "jsonld=", "ld+json" in h, "<article>=", "<article" in h)
try:
    sec2()
except Exception as e:
    P('SECTION 2 ERROR', type(e).__name__, e)

os.makedirs("news_probe_out", exist_ok=True)
open("news_probe_out/probe3.md", "w").write("# Probe 3\n\n" + "\n".join(out)); print("\n".join(out))
