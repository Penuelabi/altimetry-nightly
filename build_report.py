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
HIDDEN = ('Unusually low', 'Insufficient record', None)


def _num(v):
    return None if pd.isna(v) else int(round(float(v)))


def county_dicts(doc, cache=None, stations=None):
    cache, stations = cache or {}, stations or {}
    by_county = {}
    for uid, ex in (cache.get('stations') or {}).items():
        if uid in stations and ex.get('county'):
            by_county.setdefault(_key(ex['county']), []).append((stations[uid], ex))
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
        ip = sorted(cache.get('payams', {}).get(_key(name), []), key=lambda r: -(r.get('area_risk_km2') or 0))[:4]
        ip = [{k: _clean(v) if k.endswith('_risk') or k.startswith('buildings') else v for k, v in r.items()} for r in ip]
        cc = cache.get('county', {}).get(_key(name))
        allp = {r['payam']: r for r in cache.get('payams', {}).get(_key(name), [])}
        nowm = (cache.get('payams_now') or {}).get(_key(name)) or {}
        inow = []
        for pn, v in sorted(nowm.items(), key=lambda kv: -(kv[1].get('area_now_km2') or 0))[:4]:
            base = allp.get(pn, {})
            inow.append({'payam': pn, 'area_km2': base.get('area_km2'), 'area_now_km2': v.get('area_now_km2'),
                         'schools': base.get('schools'), 'schools_now': v.get('schools_now'),
                         'health': base.get('health'), 'health_now': v.get('health_now'),
                         'buildings': base.get('buildings'), 'buildings_now': _clean(v.get('buildings_now')),
                         'roads_km': base.get('roads_km'), 'roads_now_km': v.get('roads_now_km')})
        sts = []
        for si, ex in sorted([x for x in by_county.get(_key(name), []) if x[0]['age'] <= 45 and x[0]['cls'] not in HIDDEN],
                             key=lambda x: -(x[0]['pct'] or 0))[:2]:
            si = dict(si)
            si['exposure'] = {**{k: _clean(ex.get(k)) if k == 'buildings_risk' else ex.get(k) for k in
                                 ('pop', 'pop_risk', 'schools', 'schools_risk', 'health', 'health_risk', 'buildings', 'buildings_risk')},
                              'counties': ex.get('counties') or [], 'payams': (ex.get('payams') or [])[:4]}
            sts.append(si)
        out.append({'county': name, 'state': state, 'population': popn, 'advisory': adv, 'previous': prev,
                    'scenarios': scen, 'settlements': sett or None, 'infra_payam': ip or None, 'infra_county': cc if ip else None, 'infra_now': inow or None,
                    'stations': sts})
    return out


def _key(name):
    import re
    k = re.sub(r'[^a-z0-9]', '', str(name).lower())
    return {'abyeiadministrativearea': 'abyeiregion'}.get(k, k)


def load_cache():
    p = D('exposure_cache.json')
    if not os.path.exists(p):
        print('exposure cache not found: infrastructure and 25 km exposure sections are skipped')
        return {}
    c = json.load(open(p, encoding='utf-8'))
    c['payams'] = {_key(k): v for k, v in (c.get('payams') or {}).items()}
    c['county'] = {_key(k): v for k, v in (c.get('county') or {}).items()}
    return c


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, (int, float)) and v < 0):
        return None
    return v


def station_info():
    """Latest pass, level statistics and routed up/downstream signal per station, from merged_altimetry_stations.csv."""
    mg = os.path.join(ALT, 'merged_altimetry_stations.csv')
    if not os.path.exists(mg):
        print('merged_altimetry_stations.csv not found: station sections are skipped')
        return {}
    hdr = list(pd.read_csv(mg, nrows=0).columns)
    unc = next((c for c in hdr if 'uncertain' in c.lower()), None)
    want = ['station_uid', 'date', db.LEVEL_COL, 'location/river_name', 'minimium', 'maxmium', 'average', 'seasonal_median_m',
            'seasonal_pctile', 'base_n_obs', 'base_n_years', 'level_class', 'days_since_prev', 'qc_status', 'Lag Days',
            'Station After_this_station', 'Station Before_this_Station'] + ([unc] if unc else [])
    df = pd.read_csv(mg, usecols=[c for c in want if c in hdr], low_memory=False)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date')
    df['station_uid'] = df['station_uid'].astype(str)
    lag = pd.to_numeric(df.get('Lag Days'), errors='coerce').groupby(df['station_uid']).median() if 'Lag Days' in df else pd.Series(dtype=float)
    last = df.groupby('station_uid').tail(1).set_index('station_uid')
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()

    def g(r, col):
        v = r.get(col) if col else None
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else v

    def sig(uid, lagv, base_date=None):
        if not uid or uid not in last.index:
            return None
        r = last.loc[uid]
        lg = None if lagv is None or pd.isna(lagv) or lagv < 0 else int(round(lagv))
        d0 = pd.Timestamp(base_date) if base_date is not None else r['date']
        return {'uid': uid, 'cls': g(r, 'level_class') or 'n/a', 'pct': None if g(r, 'seasonal_pctile') is None else int(round(r['seasonal_pctile'])),
                'date': str(r['date'])[:10], 'lag': lg if lg is not None else 'not established',
                'expected': str((d0 + pd.Timedelta(days=lg)).date()) if lg is not None else 'n/a'}

    out = {}
    for uid, r in last.iterrows():
        f = lambda c: None if g(r, c) is None else float(r[c])
        i = lambda c: None if g(r, c) is None else int(round(float(r[c])))
        ups = [u.strip() for u in str(g(r, 'Station Before_this_Station') or '').split(',') if u.strip()][:2]
        down = str(g(r, 'Station After_this_station') or '').strip() or None
        own_lag = lag.get(uid) if len(lag) else None
        routed = [x for x in (sig(u, lag.get(u) if len(lag) else None) for u in ups) if x]
        rdown = sig(down, own_lag, r['date'])
        out[uid] = {
            'uid': uid, 'name': g(r, 'location/river_name') or uid, 'age': int((today - r['date']).days), 'pct': f('seasonal_pctile'),
            'cls': g(r, 'level_class'),
            'level': {'date': str(r['date'])[:10], 'cls': g(r, 'level_class') or 'n/a', 'pct': i('seasonal_pctile'), 'wse': f(db.LEVEL_COL),
                      'median': f('seasonal_median_m'), 'min': f('minimium'), 'max': f('maxmium'), 'avg': f('average'),
                      'years': i('base_n_years'), 'passes': i('base_n_obs'), 'qc': g(r, 'qc_status'), 'unc': f(unc) if unc else None,
                      'since_prev': i('days_since_prev')},
            'routed': routed, 'routed_down': [rdown] if rdown else [], 'routed_down_note': 'No downstream station linked.'}
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


def _verif(doc):
    v = (doc.get('forecast_verification') or {}).get('day 1-5')
    if not v:
        return None
    return (f"days 1–5, {v.get('n')} county-days: hit rate {v.get('hit_rate', 0):.0%}, false-alarm ratio {v.get('false_alarm_ratio', 0):.0%}, "
            f"Brier skill {v.get('brier_skill')}.")


def main():
    doc = json.load(open(os.path.join(OUT, 'county_bulletin_latest.json'), encoding='utf-8'))
    today = dt.datetime.utcnow() + dt.timedelta(hours=2)   # Juba time (UTC+2)
    cover = m.cover_from_bulletin(doc, gauges(), today)
    logo = os.path.join(HERE, 'assets', 'uj_logo.png')
    path = os.path.join(OUT, 'county_report_latest.pdf')
    m.build_pdf(county_dicts(doc, load_cache(), station_info()), path, run_label=str(doc.get('ecmwf_run_utc') or ''), today=today.date(), cover=cover, logo=logo, verification=_verif(doc))
    os.makedirs(os.path.join(HERE, 'reports'), exist_ok=True)
    shutil.copyfile(path, os.path.join(HERE, 'reports', 'latest.pdf'))
    print('wrote', path, 'and reports/latest.pdf')


if __name__ == '__main__':
    main()
