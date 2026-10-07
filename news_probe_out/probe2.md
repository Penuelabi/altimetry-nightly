# Probe 2

- Sudans Post `{'search': 'flood', 'per_page': 5, 'after': '2020-01-01T00:00:00', 'before': '2020-12-31T23:59:59'}` -> HTTP 200, application/json, final=same, starts: `'[{"id":5766,"date":"2020-12-18T17:27:24","link":"https:\\/\\/www.sudanspost.com\\/un-diplomat-calls-for-end-to-vi'`
- Sudans Post `{'search': 'flood', 'per_page': 5}` -> HTTP 200, application/json, final=same, starts: `'[{"id":54614,"date":"2026-09-21T07:06:01","link":"https:\\/\\/www.sudanspost.com\\/south-sudan-on-high-alert-as-u'`
- Sudans Post `{'per_page': 3}` -> HTTP 200, application/json, final=same, starts: `'[{"id":54786,"date":"2026-10-07T00:32:19","link":"https:\\/\\/www.sudanspost.com\\/south-sudan-rivals-trade-confl'`
- Radio Miraya `{'search': 'flood', 'per_page': 5, 'after': '2020-01-01T00:00:00', 'before': '2020-12-31T23:59:59'}` -> HTTP 200, application/json, final=https://thapcam-tv.work/wp-json/wp/v2/posts?search=flood&per, starts: `'[]'`
- Radio Miraya `{'search': 'flood', 'per_page': 5}` -> HTTP 200, application/json, final=https://thapcam-tv.work/wp-json/wp/v2/posts?search=flood&per, starts: `'[]'`
- Radio Miraya `{'per_page': 3}` -> HTTP 200, application/json, final=https://thapcam-tv.work/wp-json/wp/v2/posts?per_page=3&_fiel, starts: `'[{"id":550800,"date":"2026-07-17T05:00:57","link":"https:\\/\\/thapcam-tv.work\\/tay-ban-nha-vs-argentina-02h00-n'`
- Radio Miraya (no www) `{'search': 'flood', 'per_page': 5, 'after': '2020-01-01T00:00:00', 'before': '2020-12-31T23:59:59'}` -> HTTP 200, application/json, final=https://thapcam-tv.work/wp-json/wp/v2/posts?search=flood&per, starts: `'[]'`
- Radio Miraya (no www) `{'search': 'flood', 'per_page': 5}` -> HTTP 200, application/json, final=https://thapcam-tv.work/wp-json/wp/v2/posts?search=flood&per, starts: `'[]'`
- Radio Miraya (no www) `{'per_page': 3}` -> HTTP 200, application/json, final=https://thapcam-tv.work/wp-json/wp/v2/posts?per_page=3&_fiel, starts: `'[{"id":550800,"date":"2026-07-17T05:00:57","link":"https:\\/\\/thapcam-tv.work\\/tay-ban-nha-vs-argentina-02h00-n'`
- The Niles `{'search': 'flood', 'per_page': 5, 'after': '2020-01-01T00:00:00', 'before': '2020-12-31T23:59:59'}` -> HTTP 200, application/json, final=same, starts: `'[]'`
- The Niles `{'search': 'flood', 'per_page': 5}` -> HTTP 200, application/json, final=same, starts: `'[]'`
- The Niles `{'per_page': 3}` -> HTTP 200, application/json, final=same, starts: `'[]'`

## Radio Tamazuj robots.txt (Disallow/Allow lines)
    User-agent: *
    Disallow: /wp-json/
    Disallow: /?rest_route=

## Radio Yei: https://radioyei.org/sitemap.xml -> HTTP 200
  2 entries; first/last: [('https://radioyei.org/sitemap-index-1.xml', '2026-10-07T06:27:34Z'), ('https://radioyei.org/image-sitemap-index-1.xml', '2026-10-07T06:26:51Z')] ... [('https://radioyei.org/sitemap-index-1.xml', '2026-10-07T06:27:34Z'), ('https://radioyei.org/image-sitemap-index-1.xml', '2026-10-07T06:26:51Z')]

## Radio Tamazuj: https://www.radiotamazuj.org/en/sitemap_index.xml -> HTTP 200
  76 entries; first/last: [('https://www.radiotamazuj.org/post-sitemap.xml', '2026-10-07T13:37:36+00:00'), ('https://www.radiotamazuj.org/post-sitemap2.xml', '2013-07-22T15:38:00+00:00'), ('https://www.radiotamazuj.org/post-sitemap3.xml', '2013-12-30T08:18:00+00:00')] ... [('https://www.radiotamazuj.org/broadcast-sitemap6.xml', '2026-10-07T13:54:26+00:00'), ('https://www.radiotamazuj.org/category-sitemap.xml', '2026-10-07T13:37:36+00:00'), ('https://www.radiotamazuj.org/post_tag-sitemap.xml', '2024-12-12T17:42:11+00:00')]
  child https://www.radiotamazuj.org/post-sitemap.xml -> HTTP 200, 1002 urls, lastmod range  .. ; sample [('https://www.radiotamazuj.org/en/news', ''), ('https://www.radiotamazuj.org/ar/blog', '')]
  child https://www.radiotamazuj.org/post_tag-sitemap.xml -> HTTP 200, 49 urls, lastmod range  .. ; sample [('https://www.radiotamazuj.org/en/news/article/tag/al-fasher', ''), ('https://www.radiotamazuj.org/en/news/article/tag/cholera-infections', '')]

## Radio Tamazuj wp-sitemap: https://www.radiotamazuj.org/wp-sitemap.xml -> HTTP 200
  76 entries; first/last: [('https://www.radiotamazuj.org/post-sitemap.xml', '2026-10-07T13:37:36+00:00'), ('https://www.radiotamazuj.org/post-sitemap2.xml', '2013-07-22T15:38:00+00:00'), ('https://www.radiotamazuj.org/post-sitemap3.xml', '2013-12-30T08:18:00+00:00')] ... [('https://www.radiotamazuj.org/broadcast-sitemap6.xml', '2026-10-07T13:54:26+00:00'), ('https://www.radiotamazuj.org/category-sitemap.xml', '2026-10-07T13:37:36+00:00'), ('https://www.radiotamazuj.org/post_tag-sitemap.xml', '2024-12-12T17:42:11+00:00')]
  child https://www.radiotamazuj.org/post-sitemap.xml -> HTTP 200, 1002 urls, lastmod range  .. ; sample [('https://www.radiotamazuj.org/en/news', ''), ('https://www.radiotamazuj.org/ar/blog', '')]
  child https://www.radiotamazuj.org/post_tag-sitemap.xml -> HTTP 200, 49 urls, lastmod range  .. ; sample [('https://www.radiotamazuj.org/en/news/article/tag/al-fasher', ''), ('https://www.radiotamazuj.org/en/news/article/tag/cholera-infections', '')]

## Sudans Post: https://www.sudanspost.com/sitemap.xml -> HTTP 200
  3 entries; first/last: [('https://www.sudanspost.com/sitemap-index-1.xml', '2026-10-07T07:32:19Z'), ('https://www.sudanspost.com/image-sitemap-index-1.xml', '2026-10-07T04:14:30Z'), ('https://www.sudanspost.com/video-sitemap-1.xml', '2024-07-02T07:01:48Z')] ... [('https://www.sudanspost.com/sitemap-index-1.xml', '2026-10-07T07:32:19Z'), ('https://www.sudanspost.com/image-sitemap-index-1.xml', '2026-10-07T04:14:30Z'), ('https://www.sudanspost.com/video-sitemap-1.xml', '2024-07-02T07:01:48Z')]
  child https://www.sudanspost.com/sitemap-index-1.xml -> HTTP 200, 13 urls, lastmod range 2023-12-15T19:47:12Z .. 2026-10-07T07:32:19Z; sample [('https://www.sudanspost.com/sitemap-2.xml', '2026-09-23T03:24:54Z'), ('https://www.sudanspost.com/sitemap-5.xml', '2023-12-15T19:47:12Z')]
  child https://www.sudanspost.com/video-sitemap-1.xml -> HTTP 200, 6 urls, lastmod range 2019-12-27T19:13:52Z .. 2024-07-02T07:01:48Z; sample [('https://www.sudanspost.com/penton-k-comedy/', '2019-12-27T19:13:52Z'), ('https://www.sudanspost.com/bashir-regretted-helping-kiir-rig-2010-elections-against-dr-lam-documentary/', '2020-09-19T03:43:42Z')]

## Radio Miraya: https://www.radiomiraya.org/sitemap_index.xml -> HTTP 200
  5 entries; first/last: [('https://thapcam-tv.work/post-sitemap1.xml', '2026-07-16T08:43:52+00:00'), ('https://thapcam-tv.work/post-sitemap2.xml', '2026-07-16T08:39:52+00:00'), ('https://thapcam-tv.work/post-sitemap3.xml', '2026-07-13T08:21:16+00:00')] ... [('https://thapcam-tv.work/post-sitemap3.xml', '2026-07-13T08:21:16+00:00'), ('https://thapcam-tv.work/page-sitemap.xml', '2026-10-05T12:06:00+00:00'), ('https://thapcam-tv.work/category-sitemap.xml', '2025-12-23T08:52:32+00:00')]
  child https://thapcam-tv.work/post-sitemap1.xml -> HTTP 200, 200 urls, lastmod range 2025-02-16T11:12:40+00:00 .. 2026-07-16T22:00:57+00:00; sample [('https://thapcam-tv.work/tay-ban-nha-vs-argentina-02h00-ngay-20-7/', '2026-07-16T22:00:57+00:00'), ('https://thapcam-tv.work/phap-vs-anh-04h00-ngay-19-7/', '2026-07-16T08:39:52+00:00')]
  child https://thapcam-tv.work/post-sitemap3.xml -> HTTP 200, 62 urls, lastmod range 2023-10-29T02:06:39+00:00 .. 2024-01-19T20:30:41+00:00; sample [('https://thapcam-tv.work/lich-su-doi-dau-ha-lan-va-my/', '2024-01-19T20:30:41+00:00'), ('https://thapcam-tv.work/mu-vs-chelsea-lich-su-doi-dau/', '2024-01-18T19:27:55+00:00')]

## Gurtong: https://www.gurtong.net/sitemap.xml -> HTTP 200
  1 entries; first/last: [('https://www.gurtong.net/lander', '')] ... [('https://www.gurtong.net/lander', '')]

## Tamazuj robots on sample article path: True | paged feed: True