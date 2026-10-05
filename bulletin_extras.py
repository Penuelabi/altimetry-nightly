# -*- coding: utf-8 -*-
"""
Extras for the county bulletin: population exposure, impact-based alert levels, attributions,
a JSON file for other systems, and a printable PDF (one page per county).

Everything here is called from county_bulletin.py inside try/except, so a failure in any extra
never stops the bulletin itself.

Impact-based alert level (WMO multi-hazard impact-based forecast guidance, WMO-No. 1150):
level = f(likelihood of the hazard, impact on people), shown as Green / Yellow / Orange / Red.
Both scales below are PROVISIONAL and should be agreed with your partners (as the advisory
thresholds in county_bulletin.py should).
"""
import datetime
import json
import os
import re
import textwrap

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# settings                                                                    #
# --------------------------------------------------------------------------- #
LIKELIHOOD_BANDS = [(0.50, 'high'), (0.20, 'medium'), (0.0, 'low')]      # probability >= edge
# Flood impact, from people living on flood-prone ground in the county:
#   minor     fewer than FLOOD_PEOPLE_MODERATE people
#   moderate  FLOOD_PEOPLE_MODERATE or more; or, whatever the people count, more than FLOOD_BUILDINGS_MIN buildings on
#             flood-prone ground, or a payam with more than FLOOD_PAYAM_SHARE of its buildings, settlements, schools,
#             health facilities or people on flood-prone ground (data/exposure_cache.json,
#             data/flood_settlements_sept2025.csv)
#   severe    more than FLOOD_PEOPLE_SEVERE people, or a payam with at least FLOOD_PAYAM_SHARE_SEVERE of its buildings,
#             listed settlements, schools or health facilities on flood-prone ground, AND a news report of flooding in
#             the county (data/news.json, last NEWS_CONFIRM_DAYS days). Without the report the impact stays moderate,
#             so red (high likelihood x severe) needs the news confirmation.
# A payam share counts only when the payam has at least PAYAM_MIN_ITEMS of that item (PAYAM_MIN_PEOPLE people),
# so 1 of 2 schools does not decide a county's impact.
FLOOD_PEOPLE_MODERATE = 3_000
FLOOD_PEOPLE_SEVERE = 10_000
FLOOD_BUILDINGS_MIN = 500
FLOOD_PAYAM_SHARE = 0.30
FLOOD_PAYAM_SHARE_SEVERE = 0.50
PAYAM_MIN_ITEMS = 3
PAYAM_MIN_PEOPLE = 500
IMPACT_ORDER = {'minor': 0, 'moderate': 1, 'significant': 2, 'severe': 3}
# Drought impact by county population. There is no population tier for 'severe': a drought alert is red only by the
# rule below, so the matrix alone stops at orange.
DROUGHT_IMPACT_TIERS = [(200_000, 'significant'), (75_000, 'moderate'), (0, 'minor')]
# Drought red: an observed dry spell of more than DROUGHT_RED_DRY_DAYS days (no wet county-day in GSMaP), less than
# DROUGHT_RED_P_RECOVERY chance that the next 2 weeks of rain (ECMWF ensemble) refill the soil deficit, AND a news
# report of drought or a dry spell in the county within NEWS_CONFIRM_DAYS days.
DROUGHT_RED_DRY_DAYS = 21
DROUGHT_RED_P_RECOVERY = 0.60
# News confirmation (data/news.json, kept by the climate-news monitor): an item that names the county, dated within
# NEWS_CONFIRM_DAYS of the run, whose hazard contains one of the words below. Items that name no county (state-wide
# or countrywide) and forecasts in the news do not confirm a county.
NEWS_CONFIRM_DAYS = 21                     # as NEWS_DAYS in county_report_pdf.py: the report shows the same items
NEWS_HAZARD_WORDS = {'flood / waterlogging': ('flood', 'heavy rain'),
                     'drought / dry spell': ('drought', 'dry spell')}
NEWS_NOT_CONFIRMING = ('outlook', 'forecast', 'warning')
MATRIX = {                                    # likelihood x impact -> level
    'low':    {'minor': 'green',  'moderate': 'green',  'significant': 'yellow', 'severe': 'yellow'},
    'medium': {'minor': 'green',  'moderate': 'yellow', 'significant': 'orange', 'severe': 'orange'},
    'high':   {'minor': 'yellow', 'moderate': 'orange', 'significant': 'orange', 'severe': 'red'},
}
LEVEL_ORDER = {'green': 0, 'yellow': 1, 'orange': 2, 'red': 3}
LEVEL_MEANING = {
    'green': 'No action needed; routine monitoring',
    'yellow': 'Be aware: follow updates; check preparedness',
    'orange': 'Be prepared: consider early action and pre-positioning',
    'red': 'Take action: impacts on many people are likely',
}

ATTRIBUTION = [
    'Rainfall: GSMaP v8 (JAXA), gauge-corrected, via Google Earth Engine.',
    'Soil moisture, evapotranspiration, runoff: NASA SMAP Level-4 (SPL4SMGP), via Google Earth Engine.',
    'Forecast: ECMWF IFS ensemble (ENS) open data, CC BY 4.0, (c) European Centre for Medium-Range '
    'Weather Forecasts; processed by this platform (probabilities per county derived from the 51 members).',
    'Population: county estimates for 2025 (Admin2 totals supplied by the project); flood-prone share from WorldPop '
    '(2020, 100 m, University of Southampton, CC BY 4.0); cropland: ESA WorldCover 2021 v200, CC BY 4.0; flood-prone ground: JRC Global Surface Water '
    '(EC JRC / Google, 1984-2021) and Global Flood Database (Cloud to Street / Dartmouth Flood Observatory, 2000-2018).',
    'River levels: DAHITI (DGFI-TUM) and Hydroweb.Next (Theia / CNES, LEGOS) satellite altimetry.',
    'River discharge outlook: GEOGLOWS ECMWF Streamflow Model (BYU / ECMWF), where available.',
    'Alert levels follow the impact-based likelihood x impact approach of WMO-No. 1150; '
    'scales are provisional. This is decision support, not an official warning.',
]

COLORS = {'green': '#2e7d32', 'yellow': '#f9a825', 'orange': '#ef6c00', 'red': '#c62828'}

EXPOSURE_COLS = ['pop_total', 'pop_flood_prone', 'cropland_km2']
EXPOSURE_METHOD = 'gsw+gfd-v2'      # bump to force a recompute of the cached exposure


# --------------------------------------------------------------------------- #
# exposure (Earth Engine, cached)                                             #
# --------------------------------------------------------------------------- #
def add_exposure(bulletin, counties, ee, out_dir, batch=8):
    """Adds pop_total, pop_flood_prone (people on ground mapped as water or flooded at least once), cropland_km2.
    Values are cached in county_exposure_cache.csv: slow-changing, computed once."""
    from shapely.geometry import mapping
    path = os.path.join(out_dir, 'county_exposure_cache.csv')
    cache = None
    if os.path.exists(path) and os.path.getsize(path) > 10:
        try:
            cache = pd.read_csv(path)
        except Exception:
            cache = None
    names = list(counties['county'])
    if cache is None or sorted(cache['county']) != sorted(names) or not set(EXPOSURE_COLS) <= set(cache.columns) \
            or 'method' not in cache.columns or cache['method'].iloc[0] != EXPOSURE_METHOD:
        print("Computing county exposure (population, flood-prone population, cropland) - first run only...")
        pop = ee.ImageCollection('WorldPop/GP/100m/pop').filter(ee.Filter.eq('country', 'SSD')) \
            .filter(ee.Filter.eq('year', 2020)).mosaic().select('population')
        # flood-prone ground = mapped as water at least once (JRC Global Surface Water 1984-2021, 30 m)
        # OR inside a Global Flood Database event (MODIS, 2000-2018). The Flood Database alone misses most
        # of the Sudd, so it gave zero flood-prone people for the wetland counties.
        gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent').eq(1).unmask(0)
        gfd = ee.ImageCollection('GLOBAL_FLOOD_DB/MODIS_EVENTS/V1').select('flooded').sum().gt(0).unmask(0)
        flooded = gsw.max(gfd).selfMask()
        crop = ee.ImageCollection('ESA/WorldCover/v200').first().eq(40) \
            .multiply(ee.Image.pixelArea()).divide(1e6).rename('cropland_km2')
        img = ee.Image.cat([pop.rename('pop_total'),
                            pop.updateMask(flooded).rename('pop_flood_prone'),
                            crop])
        geo = counties.set_index('county').geometry
        rows = []
        for k in range(0, len(names), batch):
            part = names[k:k + batch]
            fc = ee.FeatureCollection([ee.Feature(ee.Geometry(mapping(geo[n])), {'county': n}) for n in part])
            res = img.reduceRegions(collection=fc, reducer=ee.Reducer.sum(), scale=100, tileScale=16).getInfo()
            for f in res['features']:
                p = f['properties']
                rows.append({'county': p['county'], 'pop_total': p.get('pop_total'),
                             'pop_flood_prone': p.get('pop_flood_prone') or 0.0,
                             'cropland_km2': p.get('cropland_km2')})
            print(f"  exposure: {min(k + batch, len(names))}/{len(names)} counties")
        cache = pd.DataFrame(rows).round(1)
        cache['method'] = EXPOSURE_METHOD
        cache.to_csv(path, index=False)
    cache = apply_official_population(cache)
    out = bulletin.merge(cache[['county'] + EXPOSURE_COLS], on='county', how='left')
    try:
        out = out.merge(flood_exposure_detail(), on='county', how='left')
    except Exception as e:                                   # the people-based tier still works without it
        print(f"WARNING: building / payam flood exposure not added ({type(e).__name__}: {e})")
    return out


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def flood_exposure_detail(data_dir=DATA_DIR):
    """Per county: buildings on flood-prone ground, the payam with the largest share of buildings, settlements,
    schools, health facilities or people on flood-prone ground, and the largest share leaving out people (used for
    the severe tier) ('at risk' in exposure_cache.json = flooded now or in >= 15% of same-season Sentinel-1 baseline
    years; settlements = Sept 2025 flooded-settlement list; payam people = people around the river gauges, as the
    cache has no payam population totals)."""
    with open(os.path.join(data_dir, 'exposure_cache.json'), encoding='utf-8') as fh:
        ex = json.load(fh)
    shares = {}                                              # (county, payam) -> [(share, label, item)]

    def add(county, payam, item, n, r, minimum):
        if n is None or r is None or n < minimum or r < 0:
            return
        shares.setdefault((county, payam), []).append((r / n, f"{payam}: {r:,.0f} of {n:,.0f} {item}", item))

    bld = {}
    for county, plist in (ex.get('payams') or {}).items():
        bld[county] = sum(max(p.get('buildings_risk') or 0, 0) for p in plist)
        for p in plist:
            for item in ('buildings', 'schools', 'health'):
                add(county, p.get('payam'), 'health facilities' if item == 'health' else item,
                    p.get(item), p.get(item + '_risk'), PAYAM_MIN_ITEMS)
    people = {}
    for st in (ex.get('stations') or {}).values():
        for p in st.get('payams') or []:
            key = (p.get('county'), p.get('payam'))
            if p.get('pop'):
                people[key] = max(people.get(key, (0, 0)), (p['pop'], p.get('pop_risk') or 0))
    for (county, payam), (n, r) in people.items():
        add(county, payam, 'people', round(n), round(r), PAYAM_MIN_PEOPLE)
    sp = os.path.join(data_dir, 'flood_settlements_sept2025.csv')
    if os.path.exists(sp):
        st = pd.read_csv(sp)
        for (county, payam), g in st.groupby(['county', 'payam']):
            add(county, payam, 'listed settlements', len(g), int((g['source'] == 'Other Flooded Settlements').sum()),
                PAYAM_MIN_ITEMS)
    rows = []
    for county in sorted(set(bld) | {c for c, _ in shares}):
        mine = [x for (c, _), v in shares.items() if c == county for x in v]
        best = max(mine, default=(np.nan, '', ''))
        fac = max((x for x in mine if x[2] != 'people'), default=(np.nan, '', ''))
        rows.append({'county': county, 'bld_flood_prone': bld.get(county, np.nan),
                     'payam_max_share': best[0], 'payam_max_share_item': best[1],
                     'payam_max_facility_share': fac[0], 'payam_max_facility_share_item': fac[1]})
    return pd.DataFrame(rows)


def _known(v):
    return v is not None and not (isinstance(v, str) and not v.strip()) and not pd.isna(v)


def flood_impact(r, news_item=None):
    """(impact tier, reasons) for floods. People on flood-prone ground give minor or moderate, raised to at least
    moderate by buildings or a payam share; severe needs the severe exposure bar AND a news report of flooding."""
    people = r.get('pop_flood_prone')
    imp = None if not _known(people) else 'moderate' if people >= FLOOD_PEOPLE_MODERATE else 'minor'
    severe = severe_flood_exposure(r)
    if severe and news_item:
        return 'severe', severe + [news_phrase(news_item)]
    why = []
    b, s = r.get('bld_flood_prone'), r.get('payam_max_share')
    if _known(b) and b > FLOOD_BUILDINGS_MIN:
        why.append(f'{b:,.0f} buildings on flood-prone ground')
    if _known(s) and s > FLOOD_PAYAM_SHARE:
        why.append(f"{s:.0%} in {r.get('payam_max_share_item')}")
    if why and (imp is None or IMPACT_ORDER[imp] < IMPACT_ORDER['moderate']):
        return 'moderate', why
    return imp, []


def severe_flood_exposure(r):
    """Reasons the county meets the severe flood exposure bar (people or payam facility share), news aside; [] if not."""
    people, fs = r.get('pop_flood_prone'), r.get('payam_max_facility_share')
    why = []
    if _known(people) and people > FLOOD_PEOPLE_SEVERE:
        why.append(f'{people:,.0f} people on flood-prone ground')
    if _known(fs) and fs >= FLOOD_PAYAM_SHARE_SEVERE:
        why.append(f"{fs:.0%} in {r.get('payam_max_facility_share_item')}")
    return why


def drought_red(r, news_item=None):
    """('red' | 'unconfirmed' | None, reasons) for the drought red rule: dry spell, recovery chance, news report."""
    days, p_rec = r.get('dry_spell_days'), r.get('p_soil_recovery_2wk')
    if not (_known(days) and _known(p_rec)) or not (days > DROUGHT_RED_DRY_DAYS and p_rec < DROUGHT_RED_P_RECOVERY):
        return None, []
    why = [f"no wet day for {days:.0f} days", f"{p_rec:.0%} chance that 2 weeks of rain refill the soil deficit"]
    if news_item:
        return 'red', why + [news_phrase(news_item)]
    return 'unconfirmed', why


# --------------------------------------------------------------------------- #
# news confirmation (data/news.json)                                          #
# --------------------------------------------------------------------------- #
def _nkey(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def news_confirmations(today=None, path=None, days=NEWS_CONFIRM_DAYS):
    """{county key: {hazard: newest confirming item}} from data/news.json. Missing or unreadable file = {}."""
    path = path or os.path.join(DATA_DIR, 'news.json')
    if not os.path.exists(path):
        return {}
    today = today or datetime.date.today()
    today = today.date() if isinstance(today, datetime.datetime) else today
    try:
        items = json.load(open(path, encoding='utf-8')).get('items', [])
    except Exception as e:
        print(f"WARNING: news file not read ({type(e).__name__}: {e}); no news confirmation this run")
        return {}
    out = {}
    for it in items:
        try:
            d = datetime.date.fromisoformat(str(it.get('date')))
        except ValueError:
            continue
        if d > today or (today - d).days > days or not it.get('counties'):
            continue
        hz = str(it.get('hazard', '')).lower()
        if any(w in hz for w in NEWS_NOT_CONFIRMING):
            continue
        for hazard, words in NEWS_HAZARD_WORDS.items():
            if any(w in hz for w in words):
                for c in it['counties']:
                    cur = out.setdefault(_nkey(c), {}).get(hazard)
                    if cur is None or str(it['date']) > str(cur['date']):
                        out[_nkey(c)][hazard] = it
    return out


def news_phrase(it):
    try:
        when = f"{datetime.date.fromisoformat(str(it['date'])):%d %b}"
    except (KeyError, ValueError):
        when = str(it.get('date', ''))
    return f"{str(it.get('hazard', 'event')).lower()} reported {when} ({it.get('source', 'news')})"


POP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ssd_county_population_2025.csv')


def apply_official_population(cache):
    """Replaces WorldPop county totals by the 2025 county estimates (data/ssd_county_population_2025.csv).
    pop_flood_prone is rescaled by official/WorldPop so the flood-prone share still comes from the maps."""
    cache = cache.copy()
    try:
        off = pd.read_csv(POP_FILE).set_index('county')['pop_2025']
    except Exception as e:
        print(f"WARNING: official population file not used ({e}); keeping WorldPop 2020")
        return cache
    wp = cache['pop_total'].astype(float)
    new = cache['county'].map(off).astype(float)
    ratio = (new / wp).where(wp > 0)
    cache['pop_flood_prone'] = (cache['pop_flood_prone'].astype(float) * ratio).fillna(cache['pop_flood_prone']).round(0)
    cache['pop_total'] = new.fillna(wp).round(0)
    miss = cache.loc[new.isna(), 'county'].tolist()
    if miss:
        print(f"WARNING: no 2025 population for {miss}; WorldPop used for these")
    return cache


# --------------------------------------------------------------------------- #
# alert levels                                                                #
# --------------------------------------------------------------------------- #
def likelihood_class(p):
    if p is None or pd.isna(p):
        return None
    for edge, name in LIKELIHOOD_BANDS:
        if p >= edge:
            return name
    return 'low'


def impact_class(people, tiers):
    if people is None or pd.isna(people):
        return None
    for edge, name in tiers:
        if people >= edge:
            return name
    return 'minor'


FLOOD, DROUGHT = 'flood / waterlogging', 'drought / dry spell'


def county_alert(r, p_heavy_col, p_dry_col, p_wsp_col, z_wet, recovery_severe, recovery_moderate, news=None):
    """(level, hazard, likelihood, impact, text, red_needs_news) for one bulletin row.
    news: {hazard: newest news item confirming that hazard in this county} (see news_confirmations)."""
    news = news or {}
    cands = []
    p_heavy, p_dry, p_wsp = r.get(p_heavy_col), r.get(p_dry_col), r.get(p_wsp_col)
    z, deficit = r.get('sm_rootzone_z'), r.get('soil_deficit_mm')

    # flood / waterlogging: heavy rain, or a long wet spell on already wet soils
    if pd.notna(p_heavy):
        p = p_heavy
        if pd.notna(z) and pd.notna(p_wsp) and z >= z_wet and p_wsp >= 0.6:
            p = max(p, 0.35)
        cands.append((FLOOD, p, r, None))

    # drought: observed deficit (already happening) or a likely dry spell
    p_dr = None
    w1, w2 = r.get('week1_rain_median_mm'), r.get('week2_rain_median_mm')
    if pd.notna(deficit) and deficit >= 20 and pd.notna(z) and z <= -1.0 and pd.notna(w1) and pd.notna(w2):
        recovery = (w1 + w2) / deficit
        p_dr = 0.9 if recovery < recovery_severe else 0.5 if recovery < recovery_moderate else None
    if pd.notna(p_dry):
        p_dr = max(p_dr or 0.0, p_dry if (p_dry >= 0.3 and pd.notna(z) and z <= -0.75) else 0.0) or p_dr
    dr_state, dr_why = drought_red(r, news.get(DROUGHT))
    if dr_state == 'red' and p_dr is None:                   # the red rule stands on its own
        p_dr = 1.0 - float(r.get('p_soil_recovery_2wk'))
    if p_dr is not None:
        cands.append((DROUGHT, p_dr, r.get('pop_total'), DROUGHT_IMPACT_TIERS))

    best = None
    for hazard, p, people, tiers in cands:
        lk = likelihood_class(p)
        why, note, pending = [], '', ''
        if tiers is None:                                    # flood: people, buildings, payam shares, news
            imp, why = flood_impact(people, news.get(FLOOD))
        else:
            imp = impact_class(people, tiers)
        assumed = imp is None
        imp = imp or 'moderate'
        level = MATRIX[lk][imp]
        if hazard == DROUGHT and dr_state == 'red':
            level, lk, imp, why = 'red', 'high', 'severe', dr_why
        elif hazard == DROUGHT and dr_state == 'unconfirmed':
            why, note, pending = dr_why, ' Red if news confirms drought or a dry spell in the county.', DROUGHT
        elif hazard == FLOOD and lk == 'high' and imp != 'severe' and severe_flood_exposure(people):
            note = f" Red if news confirms flooding in the county ({'; '.join(severe_flood_exposure(people))})."
            pending = FLOOD
        if level == 'red' and not ((hazard == FLOOD and imp == 'severe') or (hazard == DROUGHT and dr_state == 'red')):
            level = 'orange'                                 # red only by the confirmed rules above
        item = (LEVEL_ORDER[level], p, level, hazard, lk, imp if not assumed else imp + ' (assumed)', why, note,
                pending)
        if best is None or item[:2] > best[:2]:
            best = item
    if best is None:
        return ('n/a', 'n/a', 'n/a', 'n/a', 'not available (needs both antecedent and outlook data)', '')
    _, p, level, hazard, lk, imp, why, note, pending = best
    detail = f" ({'; '.join(why)})" if why else ''
    if hazard == DROUGHT and level == 'red':
        text = f"RED: {hazard}; {'; '.join(why)}. {LEVEL_MEANING[level]}."
    else:
        text = f"{level.upper()}: {hazard}; likelihood {lk} ({p:.0%}), impact {imp}{detail}. {LEVEL_MEANING[level]}.{note}"
    return (level, hazard, lk, imp, text, pending)


def add_alert_levels(bulletin, p_heavy_col, p_dry_col, p_wsp_col, z_wet, recovery_severe, recovery_moderate,
                     today=None):
    conf = news_confirmations(today)
    res = bulletin.apply(lambda r: county_alert(r, p_heavy_col, p_dry_col, p_wsp_col, z_wet, recovery_severe,
                                                recovery_moderate, conf.get(_nkey(r['county']), {})), axis=1)
    out = bulletin.copy()
    out['alert_level'] = [x[0] for x in res]
    out['alert_hazard'] = [x[1] for x in res]
    out['alert_likelihood'] = [x[2] for x in res]
    out['alert_impact'] = [x[3] for x in res]
    out['alert_text'] = [x[4] for x in res]
    out['red_needs_news'] = [x[5] for x in res]              # hazard whose red rule is met except the news report
    for hazard, col in ((FLOOD, 'news_flood_report'), (DROUGHT, 'news_drought_report')):
        out[col] = [news_phrase(conf[_nkey(c)][hazard]) if hazard in conf.get(_nkey(c), {}) else ''
                    for c in out['county']]
    return out


def exposure_sentence(r):
    """Short people-at-risk sentence for the advisory text (only where an alert is raised)."""
    lvl = r.get('alert_level')
    if lvl not in ('yellow', 'orange', 'red'):
        return ''
    pf, pt = r.get('pop_flood_prone'), r.get('pop_total')
    if r.get('alert_hazard') == 'flood / waterlogging' and pd.notna(pf) and pf > 0:
        return f"About {round(pf, -3):,.0f} people live on ground that has flooded before (of ~{round(pt, -3):,.0f} in the county)"
    if pd.notna(pt):
        return f"County population about {round(pt, -3):,.0f}"
    return ''


def append_exposure_to_advisory(bulletin):
    def f(r):
        s = exposure_sentence(r)
        return r['advisory_flags'] + (f' | Exposure: {s}' if s else '')
    return bulletin.apply(f, axis=1)


def notes_rows(recovery_note=''):
    rows = [('alert_level', 'Green / Yellow / Orange / Red from hazard likelihood x impact on people '
                            '(WMO-No. 1150 approach). ' + ' '.join(f'{k.title()}: {v}.' for k, v in LEVEL_MEANING.items())),
            ('alert scales (provisional)',
             f'Likelihood: low < 20%, medium 20-50%, high >= 50%. Flood impact by people living on ground mapped as water '
             f'or flooded at least once (1984-2021): minor below {FLOOD_PEOPLE_MODERATE:,}, moderate from {FLOOD_PEOPLE_MODERATE:,}; '
             f'at least moderate when more than {FLOOD_BUILDINGS_MIN} buildings are on flood-prone ground or more than '
             f'{FLOOD_PAYAM_SHARE:.0%} of a payam\'s buildings, settlements, schools, health facilities or people are '
             f'(payams with at least {PAYAM_MIN_ITEMS} of the item or {PAYAM_MIN_PEOPLE} people). Severe when more than '
             f'{FLOOD_PEOPLE_SEVERE:,} people, or at least {FLOOD_PAYAM_SHARE_SEVERE:.0%} of a payam\'s buildings, listed '
             f'settlements, schools or health facilities, are on flood-prone ground AND news reported flooding or heavy '
             f'rainfall in the county within {NEWS_CONFIRM_DAYS} days; without the report the impact stays moderate. '
             f'Drought impact by county population (minor < 75,000; moderate < 200,000; significant above). A severe soil '
             f'deficit counts as high likelihood (already happening).'),
            ('red (take action; anticipatory action activation)',
             f'Flood: high likelihood x severe impact, so a high chance of heavy rain, the severe exposure bar and a news '
             f'report of flooding. Drought: more than {DROUGHT_RED_DRY_DAYS} days without a wet county-day (GSMaP), less '
             f'than {DROUGHT_RED_P_RECOVERY:.0%} chance that the next 2 weeks of rain refill the soil deficit (ECMWF '
             f'ensemble) and a news report of drought or a dry spell in the county within {NEWS_CONFIRM_DAYS} days. '
             f'Otherwise the level stops at orange; red_needs_news names the hazard when only the news report is missing.'),
            ('news_flood_report / news_drought_report',
             f'Newest item in data/news.json (climate-news monitor) that names the county and reports flooding or heavy '
             f'rainfall / drought or a dry spell, within {NEWS_CONFIRM_DAYS} days. State-wide or countrywide items and '
             f'news of forecasts or outlooks do not count.'),
            ('pop_total / pop_flood_prone / cropland_km2',
             '2025 county population estimates; population on ground mapped as water at least once (JRC Global Surface Water) or flooded in a Global Flood Database event (WorldPop 2020 shares scaled to the 2025 county totals); '
             'cropland area from ESA WorldCover 2021 (sampled at 100 m, approximate). Static: refreshed only if the '
             'county list changes.')]
    rows += [('sudd river trigger (experimental)',
              'Mean percentile of the monthly maximum level at the 3 nearest upstream altimetry stations of the counties with recorded '
              'flood displacement. Watch from the 55th, elevated from the 70th percentile. Derived from 6 flood onsets in 2020-2025: '
              'to be scored in 2026, not a validated warning. Logged in sudd_trigger_log.csv.')]
    rows += [('attribution', a) for a in ATTRIBUTION]
    return rows


# --------------------------------------------------------------------------- #
# JSON                                                                        #
# --------------------------------------------------------------------------- #
def _txt(v):
    return v if _known(v) else None


def _num(v, nd=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)) or v is pd.NA:
        return None
    if isinstance(v, (np.floating, float)):
        return round(float(v), nd)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def build_json(bulletin, p_cols, run_utc, data_end, verification=None, river_trigger=None):
    p_heavy, p_dry, p_wsp = p_cols
    day_cols = sorted(c for c in bulletin.columns if re.fullmatch(r'p_wet_\d{4}', c))
    counties = []
    for r in bulletin.to_dict('records'):
        counties.append({
            'county': r['county'], 'state': r['state'],
            'alert': {'level': r.get('alert_level'), 'hazard': r.get('alert_hazard'),
                      'likelihood': r.get('alert_likelihood'), 'impact': r.get('alert_impact'),
                      'text': r.get('alert_text'), 'red_needs_news': _txt(r.get('red_needs_news')),
                      'news_flood_report': _txt(r.get('news_flood_report')),
                      'news_drought_report': _txt(r.get('news_drought_report'))},
            'antecedent': {k: _num(r.get(k)) for k in
                           ('rain_30d_mm', 'rain_30d_pct_of_normal', 'sm_rootzone_z', 'sm_rootzone_pctile',
                            'soil_deficit_mm', 'et_30d_mm', 'wb_30d_mm', 'dry_spell_days')} |
                          {k: r.get(k) for k in ('soil_rootzone_class', 'rain_30d_class', 'runoff_30d_class')},
            'outlook': {'week1_rain_median_mm': _num(r.get('week1_rain_median_mm'), 1),
                        'week1_rain_p20_mm': _num(r.get('week1_rain_p20_mm'), 1),
                        'week1_rain_p80_mm': _num(r.get('week1_rain_p80_mm'), 1),
                        'week2_rain_median_mm': _num(r.get('week2_rain_median_mm'), 1),
                        'p_dry_spell_7d': _num(r.get(p_dry)), 'p_wet_spell_3d_week1': _num(r.get(p_wsp)),
                        'p_heavy_50mm_week1': _num(r.get(p_heavy)),
                        'p_soil_recovery_2wk': _num(r.get('p_soil_recovery_2wk')),
                        'spell_windows': r.get('spell_windows'),
                        'p_wet_daily': {c[-4:]: _num(r.get(c)) for c in day_cols}},
            'exposure': {'population': _num(r.get('pop_total'), 0),
                         'population_on_flood_prone_ground': _num(r.get('pop_flood_prone'), 0),
                         'cropland_km2': _num(r.get('cropland_km2'), 0),
                         'buildings_on_flood_prone_ground': _num(r.get('bld_flood_prone'), 0),
                         'largest_payam_share_on_flood_prone_ground': _num(r.get('payam_max_share')),
                         'largest_payam_share_detail': _txt(r.get('payam_max_share_item')),
                         'largest_payam_facility_share_on_flood_prone_ground': _num(r.get('payam_max_facility_share')),
                         'largest_payam_facility_share_detail': _txt(r.get('payam_max_facility_share_item'))},
            'advisory': [a.strip() for a in str(r.get('advisory_flags', '')).split(' | ') if a.strip()],
        })
    return {
        'schema_version': 1,
        'generated_utc': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
        'ecmwf_run_utc': run_utc, 'antecedent_data_end': str(data_end),
        'alert_levels': {k: LEVEL_MEANING[k] for k in LEVEL_ORDER},
        'forecast_verification': verification or None,
        'sudd_river_trigger': river_trigger or None,
        'attribution': ATTRIBUTION,
        'counties': counties,
    }


def write_json(bulletin, p_cols, run_utc, data_end, out_dir, verification=None, river_trigger=None):
    doc = build_json(bulletin, p_cols, run_utc, data_end, verification, river_trigger)
    path = os.path.join(out_dir, 'county_bulletin_latest.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    return path


# --------------------------------------------------------------------------- #
# PDF                                                                         #
# --------------------------------------------------------------------------- #
def write_pdf(bulletin, p_cols, run_utc, data_end, out_dir, river_trigger=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Flowable)
    p_heavy, p_dry, p_wsp = p_cols
    day_cols = sorted(c for c in bulletin.columns if re.fullmatch(r'p_wet_\d{4}', c))
    ss = getSampleStyleSheet()
    body = ParagraphStyle('b', parent=ss['BodyText'], fontSize=9, leading=12)
    small = ParagraphStyle('s', parent=body, fontSize=7, leading=9, textColor=colors.HexColor('#555555'))
    h1 = ParagraphStyle('h1', parent=ss['Title'], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle('h2', parent=ss['Heading2'], fontSize=12, spaceAfter=2)
    stamp = f"ECMWF run {run_utc or 'n/a'} UTC | rain/soil data to {data_end} | generated {datetime.datetime.utcnow():%Y-%m-%d %H:%M} UTC"

    class Bars(Flowable):
        """15-day chance-of-wet-day bars."""
        def __init__(self, vals, labels, w=170 * mm, h=38 * mm):
            super().__init__()
            self.vals, self.labels, self.w, self.h = vals, labels, w, h

        def wrap(self, *_):
            return self.w, self.h

        def draw(self):
            c, n = self.canv, len(self.vals)
            bw = self.w / max(n, 1)
            c.setFont('Helvetica', 6)
            for i, (v, lab) in enumerate(zip(self.vals, self.labels)):
                v = 0 if v is None or pd.isna(v) else float(v)
                col = colors.HexColor('#1565c0') if v >= 0.5 else colors.HexColor('#90a4ae')
                c.setFillColor(col)
                c.rect(i * bw + 1, 8, bw - 3, (self.h - 14) * v, stroke=0, fill=1)
                c.setFillColor(colors.black)
                c.drawCentredString(i * bw + bw / 2, 1, lab)
                c.drawCentredString(i * bw + bw / 2, 9 + (self.h - 14) * v, f"{v:.0%}")
            c.setStrokeColor(colors.HexColor('#cccccc'))
            y = 8 + (self.h - 14) * 0.5
            c.line(0, y, self.w, y)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(15 * mm, 9 * mm, stamp)
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f'page {doc.page}')
        canvas.restoreState()

    path = os.path.join(out_dir, 'county_bulletin_latest.pdf')
    doc = BaseDocTemplate(path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                          bottomMargin=16 * mm, title='South Sudan county hydro-climate bulletin',
                          author='Hydro-climate platform')
    doc.addPageTemplates([PageTemplate(id='p', frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width,
                                                             doc.height, id='f')], onPage=footer)])
    story = [Paragraph('South Sudan county hydro-climate bulletin', h1), Paragraph(stamp, small), Spacer(1, 4 * mm)]

    # cover: counts + county table by alert level
    counts = bulletin['alert_level'].value_counts()
    legend = [[Paragraph(f'<font color="white"><b>{k.upper()}</b></font>', body),
               Paragraph(f'{int(counts.get(k, 0))} counties. {LEVEL_MEANING[k]}', body)] for k in
              ('red', 'orange', 'yellow', 'green')]
    lt = Table(legend, colWidths=[24 * mm, 150 * mm])
    lt.setStyle(TableStyle([('BACKGROUND', (0, i), (0, i), colors.HexColor(COLORS[k])) for i, k in
                            enumerate(('red', 'orange', 'yellow', 'green'))] +
                           [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.25, colors.white)]))
    story += [lt, Spacer(1, 4 * mm)]
    if river_trigger and river_trigger.get('text'):
        story += [Paragraph(river_trigger['text'], body), Spacer(1, 3 * mm)]
    raised = bulletin[bulletin['alert_level'].isin(['red', 'orange', 'yellow'])].copy()
    raised['o'] = raised['alert_level'].map(LEVEL_ORDER)
    raised = raised.sort_values(['o', 'county'], ascending=[False, True])
    if len(raised):
        story.append(Paragraph('Counties with an alert', h2))
        rows = [['Level', 'County', 'State', 'Hazard', 'Chance']]
        for r in raised.itertuples():
            pv = {'flood / waterlogging': getattr(r, p_heavy), 'drought / dry spell': getattr(r, p_dry)}.get(r.alert_hazard)
            rows.append([r.alert_level.upper(), r.county, r.state, r.alert_hazard, '' if pv is None or pd.isna(pv) else f'{pv:.0%}'])
        t = Table(rows, colWidths=[20 * mm, 45 * mm, 38 * mm, 45 * mm, 20 * mm], repeatRows=1)
        st = [('FONTSIZE', (0, 0), (-1, -1), 8), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eeeeee')),
              ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cccccc'))]
        for i, r in enumerate(raised.itertuples(), start=1):
            st += [('BACKGROUND', (0, i), (0, i), colors.HexColor(COLORS[r.alert_level])),
                   ('TEXTCOLOR', (0, i), (0, i), colors.white)]
        t.setStyle(TableStyle(st))
        story.append(t)
    story += [Spacer(1, 5 * mm), Paragraph('Sources and notes', h2)]
    story += [Paragraph('- ' + a, small) for a in ATTRIBUTION]

    # county pages
    for r in bulletin.sort_values(['state', 'county']).to_dict('records'):
        story.append(PageBreak())
        lvl = r.get('alert_level') if r.get('alert_level') in COLORS else 'green'
        head = Table([[Paragraph(f'<font color="white" size="15"><b>{r["county"]}</b></font><font color="white" size="9">'
                                 f' &nbsp; {r["state"]}</font>', body),
                       Paragraph(f'<font color="white"><b>{str(r.get("alert_level")).upper()}</b></font>', body)]],
                     colWidths=[145 * mm, 29 * mm])
        head.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(COLORS[lvl])),
                                  ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 6),
                                  ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story += [head, Spacer(1, 3 * mm), Paragraph(str(r.get('alert_text', '')), body), Spacer(1, 2 * mm)]

        def f(v, fmt='{:.0f}', unit=''):
            return 'n/a' if v is None or pd.isna(v) else fmt.format(v) + unit
        kv = [['Soil (root zone)', f"{r.get('soil_rootzone_class', 'n/a')} (z {f(r.get('sm_rootzone_z'), '{:+.1f}')}, "
                                   f"deficit {f(r.get('soil_deficit_mm'))} mm)"],
              ['Rain, last 30 days', f"{f(r.get('rain_30d_mm'))} mm = {f(r.get('rain_30d_pct_of_normal'))}% of normal "
                                     f"({r.get('rain_30d_class', 'n/a')})"],
              ['Rain outlook, week 1', f"{f(r.get('week1_rain_median_mm'))} mm (likely range {f(r.get('week1_rain_p20_mm'))}"
                                       f"-{f(r.get('week1_rain_p80_mm'))})"],
              ['Rain outlook, week 2', f"{f(r.get('week2_rain_median_mm'))} mm"],
              ['Chance of heavy rain (>=50 mm, week 1)', f(r.get(p_heavy) * 100 if pd.notna(r.get(p_heavy)) else None, '{:.0f}', '%')],
              ['Chance of a 7-day dry spell (15 days)', f(r.get(p_dry) * 100 if pd.notna(r.get(p_dry)) else None, '{:.0f}', '%')],
              ['Days since a wet day (observed)', f(r.get('dry_spell_days'))],
              ['Chance 2 weeks of rain refill the soil deficit',
               f(r.get('p_soil_recovery_2wk') * 100 if _known(r.get('p_soil_recovery_2wk')) else None, '{:.0f}', '%')],
              ['Population / on flood-prone ground', f"{f(r.get('pop_total'), '{:,.0f}')} / {f(r.get('pop_flood_prone'), '{:,.0f}')}"]]
        t = Table([[Paragraph(a, body), Paragraph(b, body)] for a, b in kv], colWidths=[62 * mm, 112 * mm])
        t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
                               ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f5f5')),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story += [t, Spacer(1, 4 * mm), Paragraph('Chance of a wet day, next 15 days (bars at or above 50% are dark blue)', h2)]
        story.append(Bars([r.get(c) for c in day_cols], [f'{c[-2:]}/{c[-4:-2]}' for c in day_cols]))
        story += [Spacer(1, 3 * mm), Paragraph('Advisory', h2)]
        for a in str(r.get('advisory_flags', '')).split(' | '):
            story.append(Paragraph('- ' + a.strip(), body))
        story += [Spacer(1, 3 * mm), Paragraph(r.get('spell_windows', '') and ('Day-by-day: ' + str(r['spell_windows'])) or '', small)]
    doc.build(story)
    return path
