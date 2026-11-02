#!/usr/bin/env python3
"""Build payam_exposure.csv for the Abuk app (the "Within <payam>" card on the Water stations screen).

Python 3.8+, standard library only. Upload the result to the project Drive folder under the exact name
payam_exposure.csv; the server picks it up within 30 minutes.

What goes in (download the files from Drive first; give --cache and/or --population; everything else is optional):

  --all-payams  Write every payam in the cache, not only those in the --population files. This is the default when no
                --population file is given: then the payam codes and the population come from the cache's "payams_pop"
                table (GHSL GHS-POP 2020, whole country), which exposure-cache.yml fills once its population step has run.
  --population  Population-by-payam exports (Duk_population_by_payam.csv, KapoetaEast_population_by_payam.csv, ...).
                Files, folders or wildcards, as many as you like. Needs ADM2_EN, ADM3_EN, ADM3_PCODE and a "sum"
                column. A *_exposure_by_payam.csv export (columns pop and exposed) works too and also gives
                population at risk; those figures are never overwritten by --estimate-population. They give the payam codes the app looks payams up by, so only payams in these files are written.
  --cache       data/exposure_cache.json from the main branch (written every Sunday by exposure-cache.yml after the
                flood extent is exported). It gives schools, health facilities and buildings with how many are at
                risk, for all payams. It has no payam codes and no population, hence --population. Payams are
                matched by county and payam name; the ones that do not match are counted and listed at the end.
  --basis       Which cache counts are "at risk": "risk" (default; flooded now OR flooded in at least 15% of past
                same-season years) or "now" (only inside the current maximum flood extent). Buildings the job found
                too many to count (-1) stay empty.
  --buildings   Flooded-buildings table: ADM3_EN, total_buildings, then one column per year with the buildings
                flooded that year (GHS_OBAT_FloodedBuildings_by_Year_Payam*.csv). Overrides the cache buildings.
  --year        Which year of --buildings counts as "at risk": a year (2025), "latest" (default) or "worst"
                (the year with the most flooded buildings in each payam).
  --facilities  One row per school or health facility: a payam code (ADM3_PCODE) or payam name (ADM3_EN, optionally
                ADM2_EN), a type column (school / primary / health / clinic / hospital / PHCC ...) and, if known,
                a flooded column (1/0, yes/no, true/false). Without that column the at-risk count stays empty.
  --risk        A table with ADM3_PCODE (or ADM3_EN) and any of population_at_risk, buildings_at_risk,
                schools_at_risk, health_at_risk (and the matching totals). These values win over everything else:
                use it for numbers from your own flood-extent analysis.

  --estimate-population buildings|area
                Opt in: where population_at_risk is empty, estimate it as the population times the share of
                buildings (or of land area, from the cache) at risk. It is only an estimate and the hazard column
                says so. In the cache the share of buildings at risk is far lower than the share of land at risk
                (about 2% against more than half), so the two choices differ a lot; neither knows where people live.
  --hazard TEXT           What "at risk" means; printed on the card. Default is built from --year.
  --as-of TEXT            Shown on the card. Default is the --buildings year, else the current year.

Nothing is guessed silently: a cell with no source stays empty and the app shows a dash, never a zero.

Later sources win over earlier ones: population, cache, buildings, facilities, risk.

Example (cache from the main branch: git show origin/main:data/exposure_cache.json > exposure_cache.json):
  python make_payam_exposure.py --population downloads/*_population_by_payam.csv \\
      --cache exposure_cache.json --basis risk --estimate-population area -o payam_exposure.csv
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys
from collections import defaultdict

csv.field_size_limit(2**31 - 1)  # the population exports carry a whole polygon in one cell

COLUMNS = ['ADM3_PCODE', 'ADM3_EN', 'ADM2_EN', 'hazard', 'as_of', 'population', 'population_at_risk', 'buildings',
           'buildings_at_risk', 'schools', 'schools_at_risk', 'health_facilities', 'health_at_risk',
           'population_2025', 'population_2025_at_risk']
KINDS = {'population': 'population', 'buildings': 'buildings', 'schools': 'schools', 'health': 'health_facilities'}
RISK_FIELD = {'population': 'population_at_risk', 'buildings': 'buildings_at_risk', 'schools': 'schools_at_risk', 'health': 'health_at_risk'}
TRUE = {'1', 'true', 'yes', 'y', 'flooded', 'at risk', 'x'}
FALSE = {'0', 'false', 'no', 'n', '', 'none'}
warnings = []


def warn(msg):
    warnings.append(msg)
    print('warning: ' + msg, file=sys.stderr)


def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def num(s):
    """A non-negative number, or None for an empty or unreadable cell."""
    t = re.sub(r'[,\s]', '', str(s if s is not None else ''))
    if t == '':
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v >= 0 else None


def fac_col(subtype):
    return 'fac_' + (re.sub(r'[^a-z0-9]+', '_', subtype.lower()).strip('_') or 'unknown')


def whole(v):
    return None if v is None else int(round(v))


def read_table(path):
    """Rows as dicts with lower-case, stripped column names."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        rd = csv.DictReader(f)
        if not rd.fieldnames:
            sys.exit('%s is empty' % path)
        names = {n: (n or '').strip().lower() for n in rd.fieldnames}
        return [{names[k]: (v or '').strip() for k, v in row.items() if k is not None} for row in rd]


def expand(patterns):
    out = []
    for p in patterns:
        if os.path.isdir(p):
            out += sorted(glob.glob(os.path.join(p, '*.csv')))
        else:
            hits = sorted(glob.glob(p))
            if not hits:
                sys.exit('no file matches %s' % p)
            out += hits
    return out


def pick(row, *names):
    for n in names:
        if row.get(n, '') != '':
            return row[n]
    return ''


class Payams:
    """The rows being built, found again by payam code or by payam name (and county when a name repeats)."""

    def __init__(self):
        self.rows = []
        self.by_code = {}

    def add(self, code, payam, county):
        r = {c: '' for c in COLUMNS}
        r.update({'ADM3_PCODE': code.upper(), 'ADM3_EN': payam, 'ADM2_EN': county})
        self.rows.append(r)
        if code:
            self.by_code[code.upper()] = r
        return r

    def find(self, code='', payam='', county='', create=False, source='', quiet=False):
        if code and code.upper() in self.by_code:
            return self.by_code[code.upper()]
        if payam:
            hits = [r for r in self.rows if norm(r['ADM3_EN']) == norm(payam)]
            if len(hits) > 1 and county:
                hits = [r for r in hits if not r['ADM2_EN'] or norm(r['ADM2_EN']) == norm(county)]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                if not quiet:
                    warn('%s: "%s" matches %d payams; add ADM3_PCODE or ADM2_EN to tell them apart' % (source, payam, len(hits)))
                return None
        if create:
            return self.add(code, payam, county)
        if not quiet:
            warn('%s: no payam "%s" %s in the population files, row skipped' % (source, payam or code, code))
        return None


def load_population(paths, payams):
    """Population per payam. A *_exposure_by_payam.csv export (columns pop and exposed) also gives population at risk.

    Returns how many payams got a population-at-risk figure that way.
    """
    with_risk = 0
    for path in expand(paths):
        n = 0
        for row in read_table(path):
            code, name = pick(row, 'adm3_pcode', 'pcode'), pick(row, 'adm3_en', 'payam', 'payam_name')
            val = num(pick(row, 'sum', 'population', 'pop'))
            if not (code or name) or val is None:
                continue
            if val <= 0:
                # A payam with nobody in it is almost always a failed export, not a fact: leave it empty.
                warn('%s: population of %s is 0, ignored' % (os.path.basename(path), name or code))
                continue
            r = payams.find(code, name, pick(row, 'adm2_en', 'county'), create=True, source=path)
            if r is not None:
                r['population'] = whole(val)
                exposed = num(row.get('exposed'))
                if exposed is not None:
                    r['population_at_risk'] = whole(min(exposed, val))
                    with_risk += 1
                n += 1
        print('%s: %d payams' % (os.path.basename(path), n))
    return with_risk


def load_cache(path, basis, payams, create=False):
    """Schools, health facilities and buildings (totals and at risk) from data/exposure_cache.json.

    Also population per payam and the payam codes when the cache has the "payams_pop" table. With create=True every
    payam in the cache gets a row, so the whole country is written; otherwise only payams already in the population files.
    Returns (what "at risk" means, the date the cache was built, how many payams got population from the cache).
    """
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    table = data.get('payams') or {}
    now = data.get('payams_now') or {}
    if not table:
        sys.exit('%s has no "payams" table; is it data/exposure_cache.json?' % path)
    if basis == 'now' and not now:
        sys.exit('%s has no "payams_now" table (the flooded-now step has not finished); use --basis risk' % path)
    pops = data.get('payams_pop') or {}
    new = data.get('payams_new') or {}
    if not new:
        warn('%s has no "payams_new" table yet, so population_2025 and the facility columns stay empty' % os.path.basename(path))
    if create and not pops:
        warn('%s has no "payams_pop" table yet, so the rows have no payam code or population (run exposure-cache.yml with the '
             'population step first)' % os.path.basename(path))
    matched, missing, pop_filled = 0, [], 0
    for county, plist in table.items():
        for p in plist:
            name = p.get('payam', '')
            entry = (pops.get(county) or {}).get(name) or {}
            code = str(entry.get('pcode') or '').upper()
            r = payams.find(code, name, county, quiet=True)
            if r is None and create:
                r = payams.add(code, name, county)
            if r is None:
                missing.append('%s / %s' % (county, name))
                continue
            if code and not r['ADM3_PCODE']:
                r['ADM3_PCODE'] = code
                payams.by_code[code] = r
            at = (now.get(county) or {}).get(name) or {}
            for total_col, risk_col, total_key, risk_key, now_key in (
                    ('schools', 'schools_at_risk', 'schools', 'schools_risk', 'schools_now'),
                    ('health_facilities', 'health_at_risk', 'health', 'health_risk', 'health_now'),
                    ('buildings', 'buildings_at_risk', 'buildings', 'buildings_risk', 'buildings_now')):
                total = num(p.get(total_key))  # num() turns the job's "-1 = too many to count" into empty
                risk = num(p.get(risk_key) if basis == 'risk' else at.get(now_key))
                if total is None:
                    continue
                r[total_col] = whole(total)
                r[risk_col] = whole(None if risk is None else min(risk, total))
            e25 = (new.get(county) or {}).get(name) or {}
            if e25:
                p25, p25_risk = num(e25.get('pop25')), num(e25.get('pop25_risk') if basis == 'risk' else e25.get('pop25_now'))
                if p25 is not None:
                    r['population_2025'] = whole(p25)
                    r['population_2025_at_risk'] = whole(None if p25_risk is None else min(p25_risk, p25))
                tot, rk = e25.get('fac_t') or {}, e25.get('fac_r' if basis == 'risk' else 'fac_n') or {}
                r['_fac'] = {k: (int(v), int(rk.get(k, 0))) for k, v in tot.items()}
            pop_total = num(entry.get('pop'))
            if r['population'] == '' and pop_total:
                pop_risk = num(entry.get('pop_risk') if basis == 'risk' else entry.get('pop_now'))
                r['population'] = whole(pop_total)
                r['population_at_risk'] = whole(None if pop_risk is None else min(pop_risk, pop_total))
                pop_filled += 1
            area, area_risk = num(p.get('area_km2')), num(p.get('area_risk_km2') if basis == 'risk' else at.get('area_now_km2'))
            if area and area_risk is not None:
                r['_area_share'] = min(1.0, area_risk / area)
            matched += 1
    print('%s: %d of %d payams matched to the population files' % (os.path.basename(path), matched, matched + len(missing)))
    if missing:
        warn('%d cache payams are not in the population files (a county without a population file, or a different '
             'spelling), for example: %s' % (len(missing), '; '.join(missing[:5])))
    built = str(data.get('generated_utc') or '')[:10]
    if basis == 'now':
        text = 'inside the current maximum flood extent (Sentinel-1)'
    else:
        text = 'flooded now or in at least 15%% of past same-season years (%s)' % (data.get('risk_basis') or 'Sentinel-1')
    return text, built, pop_filled


def load_buildings(path, year, payams):
    """total_buildings plus the flooded count for the chosen year. Returns the label of the year used."""
    rows = read_table(path)
    if not rows:
        sys.exit('%s is empty' % path)
    years = sorted(c for c in rows[0] if re.fullmatch(r'(19|20)\d\d', c))
    if not years:
        sys.exit('%s has no year columns (2019, 2020, ...)' % path)
    if year not in ('latest', 'worst') and year not in years:
        sys.exit('%s has years %s, not %s' % (path, ', '.join(years), year))
    use = years[-1] if year == 'latest' else year
    n = 0
    for row in rows:
        total = num(pick(row, 'total_buildings', 'total_original', 'total'))
        name = pick(row, 'adm3_en', 'payam', 'payam_name')
        r = payams.find(pick(row, 'adm3_pcode', 'pcode'), name, pick(row, 'adm2_en', 'county'), source=path)
        if r is None or total is None:
            continue
        flooded = [num(row.get(y)) for y in years]
        flooded = [v for v in flooded if v is not None]
        risk = max(flooded) if year == 'worst' and flooded else num(row.get(use))
        r['buildings'] = whole(total)
        r['buildings_at_risk'] = whole(None if risk is None else min(risk, total))
        n += 1
    print('%s: %d payams, at risk = %s' % (os.path.basename(path), n, 'worst year' if year == 'worst' else use))
    return 'worst year' if year == 'worst' else use


def kind_of(t):
    t = (t or '').lower()
    if re.search(r'school|educat|nursery|primary|secondary|vocational|universit|college|ecd', t):
        return 'schools'
    if re.search(r'health|clinic|hospital|phcu|phcc|dispensar|medical|pharmac', t):
        return 'health'
    return None


def load_facilities(path, payams):
    counts = defaultdict(lambda: {'schools': [0, 0, 0], 'health': [0, 0, 0]})  # total, at risk, rows with a flood answer
    seen = 0
    for row in read_table(path):
        kind = kind_of(pick(row, 'type', 'facility_type', 'category', 'kind'))
        if kind is None:
            continue
        r = payams.find(pick(row, 'adm3_pcode', 'pcode'), pick(row, 'adm3_en', 'payam', 'payam_name'), pick(row, 'adm2_en', 'county'), source=path)
        if r is None:
            continue
        c = counts[id(r)][kind]
        c[0] += 1
        seen += 1
        raw = pick(row, 'flooded', 'at_risk', 'atrisk', 'exposed').lower()
        if raw in TRUE:
            c[1] += 1
            c[2] += 1
        elif raw in FALSE and any(k in row for k in ('flooded', 'at_risk', 'atrisk', 'exposed')) and raw != '':
            c[2] += 1
    for r in payams.rows:
        c = counts.get(id(r))
        if not c:
            continue
        for kind, total_col, risk_col in (('schools', 'schools', 'schools_at_risk'), ('health', 'health_facilities', 'health_at_risk')):
            t, risk, answered = c[kind]
            if t:
                r[total_col] = t
                # Only a facility list that says which are flooded can give an at-risk count; otherwise leave it empty.
                if answered == t:
                    r[risk_col] = risk
    print('%s: %d facilities counted' % (os.path.basename(path), seen))


def load_risk(path, payams):
    n = 0
    for row in read_table(path):
        r = payams.find(pick(row, 'adm3_pcode', 'pcode'), pick(row, 'adm3_en', 'payam', 'payam_name'), pick(row, 'adm2_en', 'county'), create=True, source=path)
        if r is None:
            continue
        for col in COLUMNS[5:]:
            v = num(row.get(col))
            if v is not None:
                r[col] = whole(v)
        n += 1
    print('%s: %d payams (these values override the other sources)' % (os.path.basename(path), n))


def estimate_population(payams, how):
    """Population at risk where nothing better is known: population x share of buildings (or of land area) at risk."""
    n = 0
    for r in payams.rows:
        if r['population_at_risk'] != '' or r['population'] == '':
            continue
        if how == 'buildings' and r['buildings'] and r['buildings_at_risk'] != '':
            share = r['buildings_at_risk'] / r['buildings']
        elif how == 'area' and '_area_share' in r:
            share = r['_area_share']
        else:
            continue
        r['population_at_risk'] = whole(r['population'] * share)
        n += 1
    print('estimated population at risk for %d payams from the share of %s at risk' % (n, how))
    return n


def floor_population(payams, per_building, pop_col='population', risk_col='population_at_risk'):
    """A payam cannot have fewer people than buildings: where it does (or has no population), use buildings x per_building.
    The at-risk figure keeps its share of the total; with no at-risk figure it falls back to buildings at risk x per_building."""
    n = 0
    for r in payams.rows:
        b = r['buildings']
        if b == '' or not b:
            continue
        floor = b * per_building
        old = r[pop_col]
        if old != '' and old >= b:
            continue
        r[pop_col] = whole(floor)
        risk = r[risk_col]
        if old not in ('', 0) and risk != '':
            risk = risk * floor / old
        elif r['buildings_at_risk'] != '':
            risk = r['buildings_at_risk'] * per_building
        else:
            risk = ''
        r[risk_col] = '' if risk == '' else whole(min(risk, floor))
        n += 1
    print('%s raised to %g x buildings for %d payams with fewer people than buildings' % (pop_col, per_building, n))
    return n


def main():
    ap = argparse.ArgumentParser(description='Build payam_exposure.csv for the Abuk app.', formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('--population', nargs='*', default=[], metavar='FILE')
    ap.add_argument('--all-payams', action='store_true')
    ap.add_argument('--cache', metavar='FILE')
    ap.add_argument('--basis', choices=('risk', 'now'), default='risk')
    ap.add_argument('--buildings', metavar='FILE')
    ap.add_argument('--year', default='latest')
    ap.add_argument('--facilities', metavar='FILE')
    ap.add_argument('--risk', metavar='FILE')
    ap.add_argument('--estimate-population', choices=('buildings', 'area'))
    ap.add_argument('--persons-per-building', type=float, default=4.5, metavar='N',
                    help='where population is below the number of buildings, use buildings x N (default 4.5; 0 turns it off)')
    ap.add_argument('--hazard', default=None)
    ap.add_argument('--as-of', default=None)
    ap.add_argument('-o', '--output', default='payam_exposure.csv')
    a = ap.parse_args()

    payams = Payams()
    if not a.population and not a.cache:
        sys.exit('give --cache (the whole country) and/or --population (the payams in those files)')
    pop_risk = load_population(a.population, payams)
    if a.population and not payams.rows:
        sys.exit('no payams found in the population files (need ADM3_EN and a "sum" column)')
    label, cache_text, cache_built, cache_pop = '', '', '', 0
    if a.cache:
        cache_text, cache_built, cache_pop = load_cache(a.cache, a.basis, payams, create=a.all_payams or not a.population)
    if not payams.rows:
        sys.exit('no payams to write')
    if a.buildings:
        label = load_buildings(a.buildings, a.year, payams)
    if a.facilities:
        load_facilities(a.facilities, payams)
    if a.risk:
        load_risk(a.risk, payams)
    estimated = estimate_population(payams, a.estimate_population) if a.estimate_population else 0
    raised = floor_population(payams, a.persons_per_building) if a.persons_per_building > 0 else 0
    if a.persons_per_building > 0 and any(r['population_2025'] != '' for r in payams.rows):
        raised += floor_population(payams, a.persons_per_building, 'population_2025', 'population_2025_at_risk')

    hazard = a.hazard
    if hazard is None:
        parts = []
        if cache_text:
            parts.append(('schools and health facilities' if a.buildings else 'schools, health facilities and buildings') + ': ' + cache_text)
        if label:
            parts.append('buildings: flooded in ' + (label if label != 'worst year' else 'the worst year on record'))
        if a.facilities:
            parts.append('schools and health facilities taken from the supplied facility list')
        if a.risk:
            parts.append('counts from the supplied risk table take priority')
        if cache_pop:
            parts.append('population: GHSL GHS-POP 2020 inside the same area')
        if pop_risk:
            parts.append('population: the exposed share from the *_exposure_by_payam exports')
        if estimated:
            parts.append('population: estimated from the share of %s at risk' % ('land area' if a.estimate_population == 'area' else 'buildings'))
        if raised:
            parts.append('population: where the layer gave fewer people than buildings it is %g x buildings' % a.persons_per_building)
        if any('_fac' in r for r in payams.rows):
            parts.append('population_2025: SSD_2025q2 population grid (April 2025); fac_*: SSD_Facilities counted by Facility subtype')
        hazard = '; '.join(parts)
    if a.as_of is not None:
        as_of = a.as_of
    elif cache_built:
        as_of = cache_built
    elif re.fullmatch(r'\d{4}', label):
        as_of = label
    else:
        as_of = str(datetime.date.today().year)
    for r in payams.rows:
        r['hazard'], r['as_of'] = hazard, as_of

    rows = sorted(payams.rows, key=lambda r: (r['ADM3_PCODE'] or '~', r['ADM3_EN']))
    subtypes = sorted({k for r in rows for k in r.get('_fac', {})}, key=lambda k: fac_col(k))
    fields = COLUMNS + [c for k in subtypes for c in (fac_col(k), fac_col(k) + '_at_risk')]
    for r in rows:
        if '_fac' in r:
            for k in subtypes:
                r[fac_col(k)], r[fac_col(k) + '_at_risk'] = r['_fac'].get(k, (0, 0))
    with open(a.output, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', restval='')
        w.writeheader()
        w.writerows(rows)

    print('\nwrote %d payams to %s' % (len(rows), a.output))
    for kind, col in (('population', 'population'), ('buildings', 'buildings'), ('schools', 'schools'), ('health', 'health_facilities')):
        have = sum(1 for r in rows if r[col] != '')
        risk = sum(1 for r in rows if r[RISK_FIELD[kind]] != '')
        print('  %-18s total for %3d payams, at risk for %3d' % (col, have, risk))
    if warnings:
        print('%d warning(s) above; those rows were left out or left empty.' % len(warnings))
    print('Upload %s to the project Drive folder as payam_exposure.csv.' % os.path.basename(a.output))


if __name__ == '__main__':
    main()
