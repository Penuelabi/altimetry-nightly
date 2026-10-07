# News source probe

UA: `SuddClimateNewsArchive/1.0 (research; contact: penuelabi@gmail.com)`

## Radio Yei
- home `https://radioyei.org/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: ['https://radioyei.org/sitemap.xml', 'https://radioyei.org/news-sitemap.xml']
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> JSON ok
- `/feed/` -> XML ok (101 entries in first 2MB)
- `/rss` -> XML ok (101 entries in first 2MB)
- `/rss.xml` -> HTTP 404
- `/sitemap.xml` -> XML ok (2 entries in first 2MB)
- `/wp-sitemap.xml` -> HTTP 404
- `/sitemap_index.xml` -> HTTP 404
- `/news-sitemap.xml` -> XML ok (93 entries in first 2MB)

## Eye Radio
- home `https://www.eyeradio.org/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: ['https://eyeradio.org/sitemap.xml', 'https://eyeradio.org/sitemap.rss', 'https://eyeradio.org/sitemap_index.xml']
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> JSON ok
- `/feed/` -> XML ok (11 entries in first 2MB)
- `/rss` -> XML ok (11 entries in first 2MB)
- `/rss.xml` -> XML ok (50 entries in first 2MB)
- `/sitemap.xml` -> XML ok (38 entries in first 2MB)
- `/wp-sitemap.xml` -> XML ok (38 entries in first 2MB)
- `/sitemap_index.xml` -> XML ok (38 entries in first 2MB)
- `/news-sitemap.xml` -> HTTP 404

## Sudans Post
- home `https://www.sudanspost.com/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: ['https://www.sudanspost.com/sitemap.xml', 'https://www.sudanspost.com/news-sitemap.xml', 'https://www.sudanspost.com/sitemap_index.xml']
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> JSON ok
- `/feed/` -> XML ok (11 entries in first 2MB)
- `/rss` -> HTML (not a feed)
- `/rss.xml` -> HTML (not a feed)
- `/sitemap.xml` -> XML ok (3 entries in first 2MB)
- `/wp-sitemap.xml` -> XML ok (20 entries in first 2MB)
- `/sitemap_index.xml` -> XML ok (20 entries in first 2MB)
- `/news-sitemap.xml` -> XML ok (4 entries in first 2MB)

## Radio Tamazuj
- home `https://www.radiotamazuj.org/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: ['https://www.radiotamazuj.org/en/sitemap_index.xml']
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> **robots.txt disallows**, not fetched
- `/feed/` -> XML ok (13 entries in first 2MB)
- `/rss` -> XML ok (13 entries in first 2MB)
- `/rss.xml` -> HTTP 404
- `/sitemap.xml` -> HTTP 404
- `/wp-sitemap.xml` -> XML ok (76 entries in first 2MB)
- `/sitemap_index.xml` -> XML ok (76 entries in first 2MB)
- `/news-sitemap.xml` -> HTTP 404

## Radio Miraya
- home `https://www.radiomiraya.org/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: []
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> JSON ok
- `/feed/` -> XML ok (11 entries in first 2MB)
- `/rss` -> XML ok (11 entries in first 2MB)
- `/rss.xml` -> HTML (not a feed)
- `/sitemap.xml` -> HTML (not a feed)
- `/wp-sitemap.xml` -> HTML (not a feed)
- `/sitemap_index.xml` -> XML ok (5 entries in first 2MB)
- `/news-sitemap.xml` -> HTML (not a feed)

## Gurtong
- home `https://www.gurtong.net/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: ['/sitemap.xml']
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> HTML (not a feed)
- `/feed/` -> HTML (not a feed)
- `/rss` -> HTML (not a feed)
- `/rss.xml` -> HTML (not a feed)
- `/sitemap.xml` -> XML ok (1 entries in first 2MB)
- `/wp-sitemap.xml` -> HTML (not a feed)
- `/sitemap_index.xml` -> HTML (not a feed)
- `/news-sitemap.xml` -> HTML (not a feed)

## Juba Monitor
- home `https://www.jubamonitor.com/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: []
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> HTML (not a feed)
- `/feed/` -> HTML (not a feed)
- `/rss` -> HTML (not a feed)
- `/rss.xml` -> HTML (not a feed)
- `/sitemap.xml` -> HTML (not a feed)
- `/wp-sitemap.xml` -> HTML (not a feed)
- `/sitemap_index.xml` -> HTML (not a feed)
- `/news-sitemap.xml` -> HTML (not a feed)

## Nyamilepedia
- home `https://www.nyamilepedia.com/` -> BLOCKED/challenge (503) (HTTP 503)
- robots.txt: HTTP 503 (no restriction)
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> HTTP 0
- `/feed/` -> HTTP 0
- `/rss` -> HTTP 0
- `/rss.xml` -> HTTP 0
- `/sitemap.xml` -> HTTP 0
- `/wp-sitemap.xml` -> HTTP 0
- `/sitemap_index.xml` -> HTTP 0
- `/news-sitemap.xml` -> HTTP 0

## The City Review
- home `https://cityreviewss.com/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: []
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> HTTP 404
- `/feed/` -> HTTP 404
- `/rss` -> HTTP 404
- `/rss.xml` -> HTTP 404
- `/sitemap.xml` -> HTTP 404
- `/wp-sitemap.xml` -> HTTP 404
- `/sitemap_index.xml` -> HTTP 404
- `/news-sitemap.xml` -> HTTP 404

## South Sudan News Agency
- home `https://www.southsudannewsagency.com/` -> HTML (not a feed) (HTTP 200)
- robots.txt: HTTP 404 (no restriction)
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> BLOCKED/challenge (403)
- `/feed/` -> HTML (not a feed)
- `/rss` -> HTML (not a feed)
- `/rss.xml` -> HTML (not a feed)
- `/sitemap.xml` -> HTTP 404
- `/wp-sitemap.xml` -> HTML (not a feed)
- `/sitemap_index.xml` -> HTTP 404
- `/news-sitemap.xml` -> HTML (not a feed)

## Radio Bakhita
- home `https://www.radiobakhita.org/` -> no connection: URLError <urlopen error [Errno -2] Name or service not known>
- home `https://radiobakhita.org/` -> no connection: URLError <urlopen error [Errno -2] Name or service not known>
- **no reachable home page**

## Sudan Tribune
- home `https://sudantribune.com/` -> BLOCKED/challenge (403) (HTTP 403)
- robots.txt: HTTP 403 (no restriction)
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> BLOCKED/challenge (403)
- `/feed/` -> BLOCKED/challenge (403)
- `/rss` -> BLOCKED/challenge (403)
- `/rss.xml` -> BLOCKED/challenge (403)
- `/sitemap.xml` -> BLOCKED/challenge (403)
- `/wp-sitemap.xml` -> BLOCKED/challenge (403)
- `/sitemap_index.xml` -> BLOCKED/challenge (403)
- `/news-sitemap.xml` -> BLOCKED/challenge (403)

## The Niles
- home `https://www.theniles.org/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: ['https://www.theniles.org/wp-sitemap.xml']
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> JSON ok
- `/feed/` -> XML ok (1 entries in first 2MB)
- `/rss` -> XML ok (1 entries in first 2MB)
- `/rss.xml` -> HTTP 404
- `/sitemap.xml` -> XML ok (10 entries in first 2MB)
- `/wp-sitemap.xml` -> XML ok (10 entries in first 2MB)
- `/sitemap_index.xml` -> HTTP 404
- `/news-sitemap.xml` -> HTTP 404

## Voice of America
- home `https://www.voanews.com/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: ['https://www.voanews.com/sitemap.xml']
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> HTTP 404
- `/feed/` -> HTTP 404
- `/rss` -> HTML (not a feed)
- `/rss.xml` -> HTTP 404
- `/sitemap.xml` -> XML ok (52 entries in first 2MB)
- `/wp-sitemap.xml` -> HTTP 404
- `/sitemap_index.xml` -> HTTP 404
- `/news-sitemap.xml` -> HTTP 404

## UN News (Africa)
- home `https://news.un.org/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: ['https://news.un.org/en/sitemap.xml', 'https://news.un.org/fr/sitemap.xml', 'https://news.un.org/ar/sitemap.xml', 'https://news.un.org/zh/sitemap.xml']
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> HTTP 404
- `/feed/` -> HTML (not a feed)
- `/rss` -> HTTP 404
- `/rss.xml` -> HTTP 404
- `/sitemap.xml` -> HTTP 404
- `/wp-sitemap.xml` -> HTTP 404
- `/sitemap_index.xml` -> HTTP 404
- `/news-sitemap.xml` -> HTTP 404

## Upper Nile Times
- home `https://uppernile.net/` -> no connection: URLError <urlopen error [Errno -2] Name or service not known>
- home `https://www.uppernile.net/` -> no connection: URLError <urlopen error [Errno -2] Name or service not known>
- **no reachable home page**

## Dawn FM / Salam FM
- home `https://www.radiodabanga.org/` -> HTML (not a feed) (HTTP 200)
- robots.txt found; sitemaps declared: []
- `/wp-json/wp/v2/posts?per_page=1&_fields=id,date,link` -> HTML (not a feed)
- `/feed/` -> HTML (not a feed)
- `/rss` -> HTML (not a feed)
- `/rss.xml` -> HTML (not a feed)
- `/sitemap.xml` -> HTML (not a feed)
- `/wp-sitemap.xml` -> HTML (not a feed)
- `/sitemap_index.xml` -> HTML (not a feed)
- `/news-sitemap.xml` -> HTML (not a feed)
