"""Build the combined all-county PDF (cover + one page per county) from the nightly bulletin.
Writes <bulletin dir>/county_report_latest.pdf and reports/latest.pdf (public download link used by the GEE app)."""
import os, json, shutil, datetime as dt
import pandas as pd
import county_report_pdf as m
import daily_brief as db

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get('BULLETIN_OUT_DIR', os.path.join(HERE, 'bulletin'))
ALT = os.environ.get('ALTIMETRY_OUT_DIR', os.path.join(HERE, 'altdata'))
D = lambda f: os.path.join(HERE, 'data', f)
YEARS = (2021, 2022, 2024, 2025)


def _num(v):
    return None if pd.isna(v) else int(round(float(v)))


def county_dicts(doc):
    pop = pd.read_csv(D('ssd_county_population_2025.csv'))
    aff = pd.read_csv(D('flood_affected_county_year.csv'))
    sc = pd.read_csv(D('flood_scenarios_2026_county.csv'))
    st = pd.read_csv(D('flood_settlements_sept2025.csv'))
    alias = {'Abyei Region': 'Abyei Administrative Area', 'Kajo-keji': 'Kajo-Keji'}
    out = []
    for c in sorted(doc['counties'], key=lambda c: (c['state'], c['county'])):
        name, state = c['county'], c['state']
        p = pop[(pop.county == name)]
        popn = _num(p.pop_2025.iloc[0]) if len(p) else _num((c.get('exposure') or {}).get('population'))
        a = aff[aff.county == name]
        prev = {y: (_num(a[a.year == y].affected.sum()) if (a.year == y).any() else None) for y in YEARS}
        s = sc[sc.county == alias.get(name, name)]
        scen = [_num(s.scenario1_lower.iloc[0]), _num(s.scenario2_planning.iloc[0]), _num(s.scenario3_severe.iloc[0]),
                _num(s.displaced_planning.iloc[0])] if len(s) else None
        t = st[st.county == name]
        sett = {}
        for payam, g in t.groupby('payam'):
            pp = lambda key: int(g[g.source.str.startswith(key)].population.sum())
            sett[payam] = {'n': len(g), 'pop': int(g.population.sum()), 'fl': pp('Other Flooded'), 'hg': pp('High Ground'), 'st': pp('Small Towns')}
        adv = c.get('advisory') or ([(c.get('alert') or {}).get('text')] if c.get('alert') else [])
        out.append({'county': name, 'state': state, 'population': popn, 'advisory': adv, 'previous': prev,
                    'scenarios': scen, 'settlements': sett or None})
    return out


def gauges():
    mg, ss = os.path.join(ALT, 'merged_altimetry_stations.csv'), os.path.join(ALT, 'station_status.csv')
    if not os.path.exists(mg):
        print('gauge watch skipped: merged_altimetry_stations.csv not found')
        return None
    try:
        return db.gauge_watch(mg, ss if os.path.exists(ss) else None)
    except Exception as e:
        print('gauge watch skipped:', e)
        return None


def main():
    doc = json.load(open(os.path.join(OUT, 'county_bulletin_latest.json'), encoding='utf-8'))
    today = dt.datetime.utcnow() + dt.timedelta(hours=2)   # Juba time (UTC+2)
    cover = m.cover_from_bulletin(doc, gauges(), today)
    logo = os.path.join(HERE, 'assets', 'uj_logo.png')
    path = os.path.join(OUT, 'county_report_latest.pdf')
    m.build_pdf(county_dicts(doc), path, run_label=str(doc.get('ecmwf_run_utc') or ''), today=today.date(), cover=cover, logo=logo)
    os.makedirs(os.path.join(HERE, 'reports'), exist_ok=True)
    shutil.copyfile(path, os.path.join(HERE, 'reports', 'latest.pdf'))
    print('wrote', path, 'and reports/latest.pdf')


if __name__ == '__main__':
    main()
