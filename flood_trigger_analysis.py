# -*- coding: utf-8 -*-
"""
Flood-trigger analysis: how far ahead of flood displacement do upstream / local / downstream
altimetry levels (DAHITI + Hydroweb), antecedent rainfall (GSMaP) and root-zone soil moisture (SMAP L4) move,
and at what value does displacement become likely?

Design (county-month, because DTM displacement is dated by assessment month):
  positive month = flood-triggered displacement recorded in that county-month (data/flood_displacement_county_month.csv)
  negative month = any other month 2020-2025 in the same counties
  predictors     = river level percentile (station's own record) of the nearest station in each position group
                   (upstream / local / downstream of the county, on the north-flowing Nile axis), monthly max level,
                   county monthly rainfall, rainfall % of normal, root-zone soil moisture z-score
  lags           = 0..LAGS months BEFORE the displacement month
  skill          = ROC-AUC per predictor and lag, all months and the flood season only (Jul-Jan), so seasonality alone
                   does not look like skill; best threshold = maximum true skill statistic (POD - POFA)
  combined       = logistic regression on the best predictor of each kind, leave-one-year-out AUC

Inputs : merged_altimetry_stations.csv, counties_dissolved.geojson (bulletin folder), Earth Engine (rain, soil moisture)
Outputs: flood_trigger_analysis.xlsx, flood_trigger_features.csv, summary in $GITHUB_STEP_SUMMARY
Run    : python flood_trigger_analysis.py            (needs EE credentials)
         python flood_trigger_analysis.py --selftest (synthetic data, no network)
"""
import os
import sys

import numpy as np
import pandas as pd

LEVEL_COL = 'Water Surface Elevation - values(m)'
LAGS = 4
NEAREST = 3              # stations kept per county and position group (nearest first)
MAX_KM = 150.0           # stations farther than this from a county are not candidates
LOCAL_BAND_DEG = 0.15    # |lat difference| below this = "local"; north of it = downstream, south = upstream
FLOOD_SEASON = {7, 8, 9, 10, 11, 12, 1}
YEARS = (2019, 2025)     # climate + levels are extracted from 2019 so 2020 months have lags
OUT_DIR = os.environ.get('ANALYSIS_OUT_DIR', '.')
ALT_DIR = os.environ.get('ALTIMETRY_OUT_DIR', 'data')
BUL_DIR = os.environ.get('BULLETIN_OUT_DIR', 'bulletin')


# ----------------------------------------------------------------------------- #
# statistics helpers (pure)                                                      #
# ----------------------------------------------------------------------------- #
def auc(y, x):
    """ROC-AUC by rank (Mann-Whitney); nan if one class is missing."""
    y = np.asarray(y, bool)
    x = np.asarray(x, float)
    m = ~np.isnan(x)
    y, x = y[m], x[m]
    n1, n0 = y.sum(), (~y).sum()
    if n1 < 3 or n0 < 3:
        return np.nan
    r = pd.Series(x).rank().values
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def best_threshold(y, x):
    """Threshold on x (x >= t -> warn) that maximises POD - POFA. Returns dict or None."""
    y = np.asarray(y, bool)
    x = np.asarray(x, float)
    m = ~np.isnan(x)
    y, x = y[m], x[m]
    if y.sum() < 3 or (~y).sum() < 3:
        return None
    best = None
    for t in np.unique(x):
        w = x >= t
        hit, miss, fa, cn = (w & y).sum(), (~w & y).sum(), (w & ~y).sum(), (~w & ~y).sum()
        pod = hit / (hit + miss)
        pofd = fa / (fa + cn)
        tss = pod - pofd
        if best is None or tss > best['TSS'] + 1e-12:
            far = fa / (hit + fa) if hit + fa else np.nan
            csi = hit / (hit + miss + fa)
            best = dict(threshold=float(t), POD=pod, POFD=pofd, FAR=far, CSI=csi, TSS=tss,
                        hits=int(hit), misses=int(miss), false_alarms=int(fa), correct_neg=int(cn))
    return best


def logistic_loyo(df, cols, ycol='y', ycluster='year'):
    """Logistic regression (standardised, light ridge) with leave-one-year-out AUC. Returns (coef dict, auc)."""
    from sklearn.linear_model import LogisticRegression
    d = df.dropna(subset=cols + [ycol]).copy()
    if d[ycol].sum() < 10 or (~d[ycol].astype(bool)).sum() < 10 or len(cols) == 0:
        return None, np.nan, len(d)
    X = d[cols].values
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    y = d[ycol].astype(int).values
    pred = np.full(len(d), np.nan)
    for yr in d[ycluster].unique():
        te = (d[ycluster] == yr).values
        if y[~te].sum() < 3 or y[te].size == 0:
            continue
        mdl = LogisticRegression(C=1.0, class_weight='balanced', max_iter=500).fit(Z[~te], y[~te])
        pred[te] = mdl.predict_proba(Z[te])[:, 1]
    full = LogisticRegression(C=1.0, class_weight='balanced', max_iter=500).fit(Z, y)
    return dict(zip(cols, full.coef_[0])), auc(y, pred), len(d)


# ----------------------------------------------------------------------------- #
# stations -> counties, monthly level features                                   #
# ----------------------------------------------------------------------------- #
def station_table(df):
    d = df.copy()
    d['date'] = pd.to_datetime(d['date'], errors='coerce')
    d[LEVEL_COL] = pd.to_numeric(d[LEVEL_COL], errors='coerce')
    if 'station_uid' not in d.columns:
        sid = pd.to_numeric(d['station_id'], errors='coerce')
        d['station_uid'] = (d['source'].astype(str).str.lower() + ':' + sid.round().astype('Int64').astype(str))
    if 'qc_status' in d.columns:
        ok = d['qc_status'].astype(str).str.lower().eq('ok')
        if ok.mean() > 0.5:
            d = d[ok]
    d = d.dropna(subset=['date', LEVEL_COL, 'latitude', 'longitude'])
    return d


def monthly_levels(d):
    """Per station-month: max level percentile (of the station's own record), count of passes."""
    rows = []
    for uid, g in d.groupby('station_uid'):
        if len(g) < 40:
            continue
        pct = g[LEVEL_COL].rank(pct=True)
        gg = g.assign(pct=pct.values, ym=g['date'].dt.to_period('M'))
        m = gg.groupby('ym').agg(level_pct=('pct', 'max'), level_m=(LEVEL_COL, 'max'), n=('pct', 'size')).reset_index()
        m['station_uid'] = uid
        m['lat'] = g['latitude'].median()
        m['lon'] = g['longitude'].median()
        rows.append(m)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def assign_stations(counties, st):
    """For every county and position group (upstream/local/downstream) the stations within MAX_KM."""
    import geopandas as gpd
    pts = gpd.GeoDataFrame(st[['station_uid', 'lat', 'lon']].drop_duplicates('station_uid'),
                           geometry=gpd.points_from_xy(st.drop_duplicates('station_uid')['lon'],
                                                       st.drop_duplicates('station_uid')['lat']), crs=4326)
    proj = 32636
    pp = pts.to_crs(proj)
    out = []
    for _, c in counties.to_crs(proj).iterrows():
        cen_lat = gpd.GeoSeries([c.geometry.centroid], crs=proj).to_crs(4326).iloc[0].y
        dist = pp.geometry.distance(c.geometry) / 1000.0
        for (_, p), dk in zip(pts.iterrows(), dist):
            if dk <= MAX_KM:
                dl = p['lat'] - cen_lat
                grp = 'local' if abs(dl) <= LOCAL_BAND_DEG else ('downstream' if dl > 0 else 'upstream')
                out.append(dict(county=c['county'], station_uid=p['station_uid'], group=grp, km=round(dk, 1)))
    out = pd.DataFrame(out)
    if out.empty:
        return out
    # keep only the nearest few stations per county and position: averaging 50+ stations washes the signal out
    return out.sort_values('km').groupby(['county', 'group']).head(NEAREST).reset_index(drop=True)


def level_features(assign, ml, months):
    """county x month x group: mean over the group's stations of the monthly max level percentile, and 1-month rise."""
    ml = ml.copy()
    ml['ym'] = ml['ym'].astype('period[M]')
    frames = []
    for county, ac in assign.groupby('county'):
        cf = pd.DataFrame({'county': county, 'ym': months})
        for grp, a in ac.groupby('group'):
            sub = ml[ml['station_uid'].isin(a['station_uid'])]
            if sub.empty:
                continue
            s = sub.groupby('ym')['level_pct'].mean().reindex(months)
            cf[f'lvl_{grp}'] = s.values
            cf[f'rise_{grp}'] = (s - s.shift(1)).values
        frames.append(cf)
    if not frames:
        return pd.DataFrame(columns=['county', 'ym'])
    return pd.concat(frames, ignore_index=True)


# ----------------------------------------------------------------------------- #
# climate from Earth Engine                                                      #
# ----------------------------------------------------------------------------- #
def fetch_climate(counties):
    import ee
    import ee_util
    ee_util.init_ee()
    from shapely.geometry import mapping
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(mapping(g)), {'county': n})
                               for n, g in zip(counties['county'], counties.geometry)])
    rain = ee.ImageCollection('JAXA/GPM_L3/GSMaP/v8/operational').select('hourlyPrecipRateGC')
    sm = None
    for sid in ['NASA/SMAP/SPL4SMGP/008', 'NASA/SMAP/SPL4SMGP/007']:
        try:
            ee.ImageCollection(sid).limit(1).size().getInfo()
            sm = ee.ImageCollection(sid).select('sm_rootzone')
            break
        except Exception:
            continue
    rows = []
    for y in range(YEARS[0], YEARS[1] + 1):
        for mth in range(1, 13):
            start = ee.Date.fromYMD(y, mth, 1)
            end = start.advance(1, 'month')
            if pd.Timestamp(y, mth, 1) > pd.Timestamp.utcnow().tz_localize(None):
                continue
            img = rain.filterDate(start, end).sum().rename('rain_mm')
            if sm is not None:
                img = img.addBands(sm.filterDate(start, end).mean().rename('sm_rz'))
            res = img.reduceRegions(fc, ee.Reducer.mean(), scale=5000, tileScale=4).getInfo()
            for f in res['features']:
                p = f['properties']
                rows.append(dict(county=p['county'], ym=pd.Period(f'{y}-{mth:02d}'),
                                 rain_mm=p.get('rain_mm'), sm_rz=p.get('sm_rz')))
        print(f'  climate {y} done', flush=True)
    return pd.DataFrame(rows)


def climate_features(clim):
    c = clim.copy()
    c['moy'] = c['ym'].dt.month
    g = c.groupby(['county', 'moy'])
    c['rain_pct_normal'] = 100 * c['rain_mm'] / g['rain_mm'].transform('mean').replace(0, np.nan)
    c['sm_z'] = (c['sm_rz'] - g['sm_rz'].transform('mean')) / g['sm_rz'].transform('std').replace(0, np.nan)
    c = c.sort_values(['county', 'ym'])
    c['rain_2mo_mm'] = c.groupby('county')['rain_mm'].transform(lambda s: s.rolling(2, min_periods=2).sum())
    c['rain_3mo_mm'] = c.groupby('county')['rain_mm'].transform(lambda s: s.rolling(3, min_periods=3).sum())
    return c.drop(columns=['moy'])


# ----------------------------------------------------------------------------- #
# assemble + analyse                                                             #
# ----------------------------------------------------------------------------- #
def build_panel(disp, feats, months_eval):
    """One row per county x month with target y and all predictors at lags 0..LAGS."""
    disp = disp.copy()
    disp['ym'] = pd.PeriodIndex(pd.to_datetime(dict(year=disp.year, month=disp.month, day=1)), freq='M')
    f = disp.groupby(['county', 'ym'])['flood'].sum()
    counties = sorted(f.groupby('county').sum().loc[lambda s: s > 0].index)
    base = pd.MultiIndex.from_product([counties, months_eval], names=['county', 'ym']).to_frame(index=False)
    base['flood_people'] = [f.get((c, m), 0) for c, m in zip(base.county, base.ym)]
    base['y'] = base.flood_people > 0
    pred_cols = [c for c in feats.columns if c not in ('county', 'ym')]
    feats = feats.sort_values(['county', 'ym']).reset_index(drop=True)
    panel = base.copy()
    for L in range(0, LAGS + 1):
        sh = feats.copy()
        sh['ym'] = sh['ym'] + L            # value observed L months before target month
        sh = sh.rename(columns={c: f'{c}__L{L}' for c in pred_cols})
        panel = panel.merge(sh, on=['county', 'ym'], how='left')
    panel['year'] = panel['ym'].dt.year
    panel['season'] = panel['ym'].dt.month.isin(FLOOD_SEASON)
    return panel, pred_cols


def analyse(panel, pred_cols):
    lag_rows, thr_rows = [], []
    for c in pred_cols:
        for L in range(0, LAGS + 1):
            col = f'{c}__L{L}'
            if col not in panel:
                continue
            for scope, sub in (('all months', panel), ('flood season Jul-Jan', panel[panel.season])):
                a = auc(sub.y.values, sub[col].values)
                lag_rows.append(dict(predictor=c, lag_months=L, scope=scope, AUC=a,
                                     n_months=int(sub[col].notna().sum()), n_events=int((sub.y & sub[col].notna()).sum())))
    lag = pd.DataFrame(lag_rows)
    season = lag[lag.scope == 'flood season Jul-Jan'].dropna(subset=['AUC'])
    # best lag per predictor by season-controlled AUC (AUC below .5 means the predictor works in the other direction)
    if season.empty:
        return lag, pd.DataFrame(), {}
    season = season.assign(skill=(season.AUC - 0.5).abs())
    best = season.sort_values('skill', ascending=False).groupby('predictor').head(1)
    picks = {}
    for _, r in best.iterrows():
        col = f"{r.predictor}__L{int(r.lag_months)}"
        sub = panel[panel.season]
        sign = 1 if r.AUC >= 0.5 else -1
        t = best_threshold(sub.y.values, sign * sub[col].values)
        if t is None:
            continue
        t['threshold'] = sign * t['threshold']
        t['rule'] = f"{r.predictor} {'>=' if sign > 0 else '<='} {t['threshold']:.3g}"
        thr_rows.append(dict(predictor=r.predictor, lag_months=int(r.lag_months), AUC_flood_season=r.AUC, **t))
        picks[r.predictor] = (col, r.AUC)
    return lag, pd.DataFrame(thr_rows).sort_values('TSS', ascending=False), picks


def combined_model(panel, picks):
    """Best predictor of each kind -> logistic regression, leave-one-year-out AUC (flood season months only)."""
    kinds = {'river upstream': 'lvl_upstream', 'river local': 'lvl_local', 'river downstream': 'lvl_downstream',
             'rain': 'rain_pct_normal', 'soil moisture': 'sm_z'}
    cols = [picks[v][0] for v in kinds.values() if v in picks]
    sub = panel[panel.season].copy()
    res = []
    for label, cs in (('all selected predictors', cols),
                      ('river only', [c for c in cols if c.startswith('lvl_')]),
                      ('rain + soil only', [c for c in cols if c.startswith(('rain', 'sm_'))])):
        if not cs:
            continue
        coef, a, n = logistic_loyo(sub, cs)
        res.append(dict(model=label, predictors=', '.join(cs), LOYO_AUC=a, n_rows=n,
                        coefficients='; '.join(f'{k}: {v:+.2f}' for k, v in (coef or {}).items())))
    return pd.DataFrame(res)


# ----------------------------------------------------------------------------- #
def selftest():
    rng = np.random.default_rng(1)
    months = pd.period_range('2019-01', '2025-12', freq='M')
    counties = ['A', 'B', 'C']
    feats, disp = [], []
    for c in counties:
        for m in months:
            season = np.sin((m.month - 4) / 12 * 2 * np.pi) * 0.3 + 0.5
            lvl = np.clip(season + rng.normal(0, .15), 0, 1)
            feats.append(dict(county=c, ym=m, lvl_upstream=lvl, rain_pct_normal=rng.normal(100, 30),
                              sm_z=rng.normal(), lvl_local=np.nan))
    F = pd.DataFrame(feats).sort_values(['county', 'ym'])
    F['lvl_upstream'] = F.groupby('county')['lvl_upstream'].shift(0)
    for c in counties:
        s = F[F.county == c].set_index('ym')['lvl_upstream']
        for m in months[12:]:
            if m.year >= 2020 and s.get(m - 2, 0) > 0.75:          # floods follow high upstream level by 2 months
                disp.append(dict(county=c, year=m.year, month=m.month, flood=1000))
    D = pd.DataFrame(disp)
    panel, pc = build_panel(D, F.drop(columns=['lvl_local']), pd.period_range('2020-01', '2025-12', freq='M'))
    lag, thr, picks = analyse(panel, pc)
    top = lag[(lag.scope == 'flood season Jul-Jan') & (lag.predictor == 'lvl_upstream')].sort_values('AUC').iloc[-1]
    print(lag[(lag.predictor == 'lvl_upstream') & (lag.scope != 'all months')].round(3).to_string())
    assert int(top.lag_months) == 2 and top.AUC > .8, top
    print(thr.round(3).to_string())
    print(combined_model(panel, picks).round(3).to_string())
    print('SELFTEST OK')


def main():
    import geopandas as gpd
    disp = pd.read_csv('data/flood_displacement_county_month.csv')
    counties = gpd.read_file(os.path.join(BUL_DIR, 'counties_dissolved.geojson'))
    alt = pd.read_csv(os.path.join(ALT_DIR, 'merged_altimetry_stations.csv'), low_memory=False)
    st = station_table(alt)
    ml = monthly_levels(st)
    print(f'{ml.station_uid.nunique()} stations with enough passes, {len(ml)} station-months')
    months_all = pd.period_range(f'{YEARS[0]}-01', f'{YEARS[1]}-12', freq='M')
    months_eval = pd.period_range('2020-01', '2025-12', freq='M')
    flood_counties = sorted(disp.loc[disp.flood > 0, 'county'].unique())
    cs = counties[counties.county.isin(flood_counties)].reset_index(drop=True)
    assign = assign_stations(cs, ml)
    assign.to_csv(os.path.join(OUT_DIR, 'flood_trigger_station_assignment.csv'), index=False)
    print('station assignment:\n', assign.groupby(['county', 'group']).size().unstack(fill_value=0).to_string())
    lvl = level_features(assign, ml, months_all)
    clim = climate_features(fetch_climate(cs))
    feats = lvl.merge(clim[['county', 'ym', 'rain_mm', 'rain_pct_normal', 'rain_2mo_mm', 'rain_3mo_mm', 'sm_z']],
                      on=['county', 'ym'], how='outer')
    panel, pc = build_panel(disp, feats, months_eval)
    panel.assign(ym=panel.ym.astype(str)).to_csv(os.path.join(OUT_DIR, 'flood_trigger_features.csv'), index=False)
    lag, thr, picks = analyse(panel, pc)
    model = combined_model(panel, picks)
    notes = pd.DataFrame({'note': [
        'Target: flood-triggered displacement recorded in a county-month (IOM DTM event tracking, assessment month), 2020-2025. Displacement is dated by assessment, so true onset is probably earlier and the lags here are, if anything, too long.',
        'Only counties with at least one flood displacement record are analysed; other months in those counties are the negatives.',
        f'Stations within {MAX_KM:.0f} km of a county polygon. Position on the river is approximated by latitude (Nile flows north): south of the county = upstream, north = downstream, within {LOCAL_BAND_DEG} deg = local. This is wrong on east-west reaches (Sobat, Pibor) and should be checked in station_assignment.',
        'River predictor = monthly maximum of the station level as a percentile of that station\'s own record, averaged over the group. Altimetry passes are 10-35 days apart so monthly maxima are under-sampled.',
        'AUC: 0.5 = no skill, 1 = perfect. "flood season" repeats the test on Jul-Jan only, so a predictor does not look skilful just because both rivers and floods peak in the same season. Trust that column.',
        'Thresholds maximise POD - POFD on flood-season months; with few events they are indicative, not operational. Validate on future events before adopting them in the alert levels.',
        'Soil moisture (SMAP L4) starts in 2015; rain is GSMaP v8 gauge-corrected. Both are county means at 5 km.']})
    path = os.path.join(OUT_DIR, 'flood_trigger_analysis.xlsx')
    with pd.ExcelWriter(path) as w:
        thr.to_excel(w, sheet_name='Best_thresholds', index=False)
        lag.to_excel(w, sheet_name='Lag_AUC', index=False)
        model.to_excel(w, sheet_name='Combined_model', index=False)
        assign.to_excel(w, sheet_name='Station_assignment', index=False)
        notes.to_excel(w, sheet_name='Notes', index=False)
    print('wrote', path)
    summ = os.environ.get('GITHUB_STEP_SUMMARY')
    if summ:
        with open(summ, 'a') as fh:
            fh.write('### Flood trigger analysis\n\n')
            if not thr.empty:
                cols = ['predictor', 'lag_months', 'AUC_flood_season', 'rule', 'POD', 'FAR', 'TSS']
                fh.write(thr[cols].round(2).to_markdown(index=False) + '\n\n')
            if not model.empty:
                fh.write(model[['model', 'LOYO_AUC', 'n_rows']].round(2).to_markdown(index=False) + '\n')
    print(thr.round(3).to_string())
    print(model.round(3).to_string())


if __name__ == '__main__':
    selftest() if '--selftest' in sys.argv else main()
