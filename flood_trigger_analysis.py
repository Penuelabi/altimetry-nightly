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
    """Per station-month: max level percentile (of the station's own record), monthly max level, share of passes above the
    station's own 90th percentile (exc90, a flood-stage proxy), and the monthly max level as a z-score against the same
    calendar month in other years (level_z, removes the seasonal cycle)."""
    rows = []
    for uid, g in d.groupby('station_uid'):
        if len(g) < 40:
            continue
        pct = g[LEVEL_COL].rank(pct=True)
        p90 = g[LEVEL_COL].quantile(0.9)
        gg = g.assign(pct=pct.values, ym=g['date'].dt.to_period('M'), hi=(g[LEVEL_COL] >= p90).astype(float))
        m = gg.groupby('ym').agg(level_pct=('pct', 'max'), level_m=(LEVEL_COL, 'max'), n=('pct', 'size'),
                                 exc90=('hi', 'mean')).reset_index()
        moy = m['ym'].dt.month
        grp = m.groupby(moy)['level_m']
        sd = grp.transform('std').replace(0, np.nan)
        z = (m['level_m'] - grp.transform('mean')) / sd
        m['level_z'] = z.where(grp.transform('count') >= 3)
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
    """county x month x group: mean over the group's stations of the monthly max level percentile (lvl), 1- and 3-month rise,
    seasonal z-score (lvlz) and share of passes above the station's own P90 (exc)."""
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
            cf[f'rise3_{grp}'] = (s - s.shift(3)).values
            if 'level_z' in sub:
                cf[f'lvlz_{grp}'] = sub.groupby('ym')['level_z'].mean().reindex(months).values
            if 'exc90' in sub:
                cf[f'exc_{grp}'] = sub.groupby('ym')['exc90'].mean().reindex(months).values
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
            if pd.Timestamp(y, mth, 1) > pd.Timestamp.now('UTC').tz_localize(None):
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
    # onset = first month of an episode: flood recorded this month but not in the previous month of the same county
    base['onset'] = base.y & np.array([not (f.get((c, m - 1), 0) > 0) for c, m in zip(base.county, base.ym)])
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


def analyse(panel, pred_cols, ycol='y'):
    """In-sample screening: AUC per predictor and lag, best lag and threshold. OPTIMISTIC (choices made on all the data);
    use nested_eval() for honest skill."""
    lag_rows, thr_rows = [], []
    for c in pred_cols:
        for L in range(0, LAGS + 1):
            col = f'{c}__L{L}'
            if col not in panel:
                continue
            for scope, sub in (('all months', panel), ('flood season Jul-Jan', panel[panel.season])):
                a = auc(sub[ycol].values, sub[col].values)
                lag_rows.append(dict(predictor=c, lag_months=L, scope=scope, AUC=a,
                                     n_months=int(sub[col].notna().sum()), n_events=int((sub[ycol] & sub[col].notna()).sum())))
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
        t = best_threshold(sub[ycol].values, sign * sub[col].values)
        if t is None:
            continue
        t['threshold'] = sign * t['threshold']
        t['rule'] = f"{r.predictor} {'>=' if sign > 0 else '<='} {t['threshold']:.3g}"
        thr_rows.append(dict(predictor=r.predictor, lag_months=int(r.lag_months), AUC_flood_season=r.AUC, **t))
        picks[r.predictor] = (col, r.AUC)
    return lag, pd.DataFrame(thr_rows).sort_values('TSS', ascending=False), picks


# ----------------------------------------------------------------------------- #
# honest validation: nested CV, cluster bootstrap, county effects, risk ranking  #
# ----------------------------------------------------------------------------- #
def boot_auc(y, s, clusters, n=300, seed=0):
    """95% CI of the AUC from a cluster bootstrap (whole counties resampled, because neighbouring months/counties are not independent)."""
    y, s, cl = np.asarray(y, bool), np.asarray(s, float), np.asarray(clusters)
    m = ~np.isnan(s)
    y, s, cl = y[m], s[m], cl[m]
    ucl = np.unique(cl)
    if len(ucl) < 3:
        return np.nan, np.nan
    idx = {c: np.where(cl == c)[0] for c in ucl}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        ii = np.concatenate([idx[c] for c in rng.choice(ucl, len(ucl), replace=True)])
        a = auc(y[ii], s[ii])
        if not np.isnan(a):
            vals.append(a)
    if len(vals) < 20:
        return np.nan, np.nan
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


def pick_lag_threshold(tr, pred, ycol):
    """Inside a TRAINING set only: best lag (largest |AUC-0.5|), its sign, and the TSS-maximising threshold."""
    best = None
    for L in range(0, LAGS + 1):
        col = f'{pred}__L{L}'
        if col not in tr:
            continue
        a = auc(tr[ycol].values, tr[col].values)
        if not np.isnan(a) and (best is None or abs(a - 0.5) > best[1]):
            best = (L, abs(a - 0.5), 1 if a >= 0.5 else -1)
    if best is None:
        return None
    L, _, sign = best
    t = best_threshold(tr[ycol].values, sign * tr[f'{pred}__L{L}'].values)
    if t is None:
        return None
    return dict(lag=L, sign=sign, thr=t['threshold'])


def _contingency(y, warn):
    m = ~np.isnan(warn)
    y, w = np.asarray(y, bool)[m], warn[m].astype(bool)
    hit, miss, fa, cn = (w & y).sum(), (~w & y).sum(), (w & ~y).sum(), (~w & ~y).sum()
    pod = hit / (hit + miss) if hit + miss else np.nan
    pofd = fa / (fa + cn) if fa + cn else np.nan
    far = fa / (hit + fa) if hit + fa else np.nan
    csi = hit / (hit + miss + fa) if hit + miss + fa else np.nan
    return pod, far, csi, pod - pofd


def nested_eval(panel, preds, ycol, fold_col, n_boot=300):
    """Nested cross-validation of every single predictor. For each held-out year (fold_col='year') or county
    (fold_col='county') the lag, sign and threshold are chosen on the other folds only, then applied to the held-out one.
    Returns one row per predictor with pooled out-of-fold AUC, a county-cluster bootstrap 95% CI and POD/FAR/CSI/TSS."""
    d = panel[panel.season].reset_index(drop=True)
    rows = []
    for pred in preds:
        score = np.full(len(d), np.nan)
        warn = np.full(len(d), np.nan)
        lags = []
        for g in d[fold_col].unique():
            te = (d[fold_col] == g).values
            tr = d[~te]
            if tr[ycol].sum() < 5:
                continue
            pk = pick_lag_threshold(tr, pred, ycol)
            if pk is None:
                continue
            x = pk['sign'] * d.loc[te, f"{pred}__L{pk['lag']}"].values
            score[te] = x
            warn[te] = np.where(np.isnan(x), np.nan, (x >= pk['thr']).astype(float))
            lags.append(pk['lag'])
        if not lags:
            continue
        a = auc(d[ycol].values, score)
        lo, hi = boot_auc(d[ycol].values, score, d['county'].values, n_boot)
        pod, far, csi, tss = _contingency(d[ycol].values, warn)
        rows.append(dict(predictor=pred, validation=f'leave-one-{fold_col}-out', AUC_cv=a, AUC_lo95=lo, AUC_hi95=hi,
                         POD=pod, FAR=far, CSI=csi, TSS=tss, n_scored=int((~np.isnan(score)).sum()),
                         n_events=int((d[ycol].values & ~np.isnan(score)).sum()),
                         lag_most_chosen=int(pd.Series(lags).mode().iloc[0]), lags_chosen=len(set(lags))))
    return pd.DataFrame(rows)


def _county_onehot(df, counties):
    return (df['county'].to_numpy(dtype=object)[:, None] == np.array(counties, dtype=object)[None, :]).astype(float)


def cv_logistic(d, preds, ycol, fold_col, county_fx=False):
    """Out-of-fold probabilities of a ridge logistic model on the best lag of each predictor (lag picked on the training
    folds only). county_fx=True adds one dummy per county (county effects), only valid when folds are years."""
    from sklearn.linear_model import LogisticRegression
    oof = np.full(len(d), np.nan)
    counties = sorted(d['county'].unique())
    for g in d[fold_col].unique():
        te = (d[fold_col] == g).values
        tr = d[~te]
        if tr[ycol].sum() < 5 or te.sum() == 0:
            continue
        cols = []
        for p in preds:
            pk = pick_lag_threshold(tr, p, ycol)
            if pk:
                cols.append(f"{p}__L{pk['lag']}")
        if not cols and not county_fx:
            continue
        trd, ted = tr.dropna(subset=cols), d[te].dropna(subset=cols)
        if trd[ycol].sum() < 5 or len(ted) == 0:
            continue
        if cols:
            Xtr = trd[cols].values
            mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
            Ztr, Zte = (Xtr - mu) / sd, (ted[cols].values - mu) / sd
        else:
            Ztr, Zte = np.zeros((len(trd), 0)), np.zeros((len(ted), 0))
        if county_fx:
            Ztr, Zte = np.hstack([Ztr, _county_onehot(trd, counties)]), np.hstack([Zte, _county_onehot(ted, counties)])
        mdl = LogisticRegression(C=1.0, class_weight='balanced', max_iter=1000).fit(Ztr, trd[ycol].astype(int).values)
        oof[d.index.get_indexer(ted.index)] = mdl.predict_proba(Zte)[:, 1]
    return oof


def county_baseline_oof(d, ycol, fold_col='year'):
    """Climatology benchmark: score = the county's own event rate in the other years. No river, rain or soil information."""
    oof = np.full(len(d), np.nan)
    for g in d[fold_col].unique():
        te = (d[fold_col] == g).values
        rate = d[~te].groupby('county')[ycol].mean()
        oof[te] = d.loc[te, 'county'].map(rate).values
    return oof


def ranking_metrics(d, score, ycol, label, ks=(3, 5)):
    """Risk-ranking view: each flood-season month, rank the counties by score and look at the top k. Compares with chance."""
    rows = []
    t = d.assign(score=score).dropna(subset=['score'])
    for k in ks:
        cap = tot = n_slots = 0
        exp_recall = []
        for _, g in t.groupby('ym'):
            if len(g) < k + 1:
                continue
            top = g.sort_values('score', ascending=False).head(k)
            cap += int(top[ycol].sum())
            tot += int(g[ycol].sum())
            n_slots += k
            if g[ycol].sum() > 0:
                exp_recall.append(k / len(g))
        if tot == 0:
            continue
        base = float(t[ycol].mean())
        prec = cap / n_slots
        rows.append(dict(model=label, top_k=k, events=tot, captured_in_top_k=cap, recall=cap / tot,
                         recall_by_chance=float(np.mean(exp_recall)), precision=prec, base_rate=base,
                         lift=prec / base if base else np.nan))
    return rows


def model_eval(panel, ycol, pred_cols, n_boot=300):
    """Combined models with honest validation. Returns (models table, ranking table)."""
    d = panel[panel.season].reset_index(drop=True)
    river = [p for p in pred_cols if p.startswith(('lvl_', 'lvlz_', 'exc_', 'rise'))]
    climate = [p for p in pred_cols if p.startswith(('rain', 'sm_'))]
    variants = [('river (levels, anomalies, exceedance)', river, False),
                ('rain + soil moisture', climate, False),
                ('all predictors', river + climate, False),
                ('all predictors + county effects', river + climate, True)]
    rows, rank_rows = [], []
    for fold_col in ('year', 'county'):
        for label, preds, fx in variants:
            if not preds or (fx and fold_col == 'county'):
                continue          # a held-out county has no county effect
            oof = cv_logistic(d, preds, ycol, fold_col, county_fx=fx)
            a = auc(d[ycol].values, oof)
            lo, hi = boot_auc(d[ycol].values, oof, d['county'].values, n_boot)
            rows.append(dict(model=label, validation=f'leave-one-{fold_col}-out', AUC_cv=a, AUC_lo95=lo, AUC_hi95=hi,
                             n_scored=int((~np.isnan(oof)).sum()), n_events=int((d[ycol].values & ~np.isnan(oof)).sum())))
            if fold_col == 'year':
                rank_rows += ranking_metrics(d, oof, ycol, label)
    base = county_baseline_oof(d, ycol)          # benchmark: county climatology only
    a = auc(d[ycol].values, base)
    lo, hi = boot_auc(d[ycol].values, base, d['county'].values, n_boot)
    rows.append(dict(model='BENCHMARK county event rate only (no predictors)', validation='leave-one-year-out', AUC_cv=a,
                     AUC_lo95=lo, AUC_hi95=hi, n_scored=int((~np.isnan(base)).sum()),
                     n_events=int((d[ycol].values & ~np.isnan(base)).sum())))
    rank_rows += ranking_metrics(d, base, ycol, 'BENCHMARK county event rate only')
    return pd.DataFrame(rows), pd.DataFrame(rank_rows)


def load_extent_target(panel, path):
    """Optional second target from observed flooding (Sentinel-1 flooded area per county-month), not tied to when an
    assessment happened. File: county,year,month,flooded_km2. y_extent = flooded area in the county's own top quartile."""
    if not os.path.exists(path):
        return None
    e = pd.read_csv(path)
    need = {'county', 'year', 'month', 'flooded_km2'}
    if not need <= set(e.columns):
        print(f'WARNING: {path} lacks columns {sorted(need - set(e.columns))}; extent target skipped')
        return None
    e['ym'] = pd.PeriodIndex(pd.to_datetime(dict(year=e.year, month=e.month, day=1)), freq='M')
    p = panel.merge(e[['county', 'ym', 'flooded_km2']], on=['county', 'ym'], how='left')
    q = p.groupby('county')['flooded_km2'].transform(lambda s: s.quantile(0.75))
    p['y_extent'] = (p['flooded_km2'] >= q) & p['flooded_km2'].notna() & (q > 0)
    return p if p['y_extent'].sum() >= 10 else None


# ----------------------------------------------------------------------------- #
def selftest():
    rng = np.random.default_rng(1)
    months = pd.period_range('2019-01', '2025-12', freq='M')
    counties = ['A', 'B', 'C', 'D', 'E', 'F']
    feats, disp = [], []
    for c in counties:
        for m in months:
            season = np.sin((m.month - 4) / 12 * 2 * np.pi) * 0.3 + 0.5
            lvl = np.clip(season + rng.normal(0, .15), 0, 1)
            feats.append(dict(county=c, ym=m, lvl_upstream=lvl, rain_pct_normal=rng.normal(100, 30),
                              sm_z=rng.normal(), lvl_local=np.nan))
    F = pd.DataFrame(feats).sort_values(['county', 'ym'])
    for c in counties:
        s = F[F.county == c].set_index('ym')['lvl_upstream']
        for m in months[12:]:
            if m.year >= 2020 and s.get(m - 2, 0) > 0.75:          # floods follow high upstream level by 2 months
                disp.append(dict(county=c, year=m.year, month=m.month, flood=1000))
    D = pd.DataFrame(disp)
    panel, pc = build_panel(D, F.drop(columns=['lvl_local']), pd.period_range('2020-01', '2025-12', freq='M'))
    assert panel['onset'].sum() < panel['y'].sum() and panel['onset'].sum() > 5, 'onset should be a subset of flood months'
    lag, thr, picks = analyse(panel, pc)
    top = lag[(lag.scope == 'flood season Jul-Jan') & (lag.predictor == 'lvl_upstream')].sort_values('AUC').iloc[-1]
    print(lag[(lag.predictor == 'lvl_upstream') & (lag.scope != 'all months')].round(3).to_string())
    assert int(top.lag_months) == 2 and top.AUC > .8, top
    print(thr.round(3).to_string())

    # honest validation recovers a real signal: lag 2 chosen in the folds, CI well above 0.5
    for fold_col in ('year', 'county'):
        ne = nested_eval(panel, pc, 'y', fold_col, n_boot=100)
        r = ne[ne.predictor == 'lvl_upstream'].iloc[0]
        print(ne.round(3).to_string())
        assert r.AUC_cv > .8 and r.AUC_lo95 > .6 and r.lag_most_chosen == 2, r
        noise = ne[ne.predictor != 'lvl_upstream']
        assert (noise.AUC_cv < .65).all(), noise          # pure-noise predictors must not look skilful
    models, rank = model_eval(panel, 'y', pc, n_boot=100)
    print(models.round(3).to_string())
    print(rank.round(3).to_string())
    m_all = models[(models.model == 'all predictors') & (models.validation == 'leave-one-year-out')].iloc[0]
    assert m_all.AUC_cv > .8, m_all

    # null test: with the target shuffled across months there must be NO significant skill
    sh = panel.copy()
    sh['y'] = np.random.default_rng(7).permutation(sh['y'].values)
    ne0 = nested_eval(sh, pc, 'y', 'year', n_boot=100)
    print('null test (shuffled target):\n', ne0.round(3).to_string())
    assert (ne0.AUC_lo95.fillna(0) < .55).all() and (ne0.AUC_cv < .65).all(), ne0

    # anomaly features from a synthetic station record
    dates = pd.date_range('2015-01-01', '2025-12-31', freq='10D')
    lev = 400 + 3 * np.sin((dates.month.values - 3) / 12 * 2 * np.pi) + rng.normal(0, .5, len(dates))
    st = pd.DataFrame(dict(date=dates, **{LEVEL_COL: lev}, latitude=7.0, longitude=31.0, station_uid='x:1'))
    ml = monthly_levels(st)
    assert {'level_z', 'exc90', 'level_pct'} <= set(ml.columns) and ml['level_z'].notna().mean() > .9
    assert abs(ml['level_z'].mean()) < .2 and ml['exc90'].between(0, 1).all(), 'z-scores should be centred, exc90 a share'
    asg = pd.DataFrame(dict(county=['A'], station_uid=['x:1'], group=['upstream'], km=[10.0]))
    lf = level_features(asg, ml, pd.period_range('2019-01', '2025-12', freq='M'))
    assert {'lvlz_upstream', 'exc_upstream', 'rise3_upstream'} <= set(lf.columns)

    # optional flood-extent target
    ext = pd.DataFrame([dict(county=c, year=m.year, month=m.month, flooded_km2=float(rng.gamma(2, 50)))
                        for c in counties for m in pd.period_range('2020-01', '2025-12', freq='M')])
    tmp = os.path.join(OUT_DIR, '_selftest_extent.csv')
    ext.to_csv(tmp, index=False)
    pe = load_extent_target(panel, tmp)
    os.remove(tmp)
    assert pe is not None and 0.15 < pe['y_extent'].mean() < 0.35, 'top-quartile target should be about a quarter of months'
    assert load_extent_target(panel, tmp) is None
    print('SELFTEST OK')


def run_target(panel, pc, ycol, label):
    lag, thr, picks = analyse(panel, pc, ycol)
    nested = pd.concat([nested_eval(panel, pc, ycol, f) for f in ('year', 'county')], ignore_index=True)
    models, rank = model_eval(panel, ycol, pc)
    for t in (lag, thr, nested, models, rank):
        if not t.empty:
            t.insert(0, 'target', label)
    return lag, thr, nested, models, rank


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
    extent_path = os.environ.get('FLOOD_EXTENT_CSV', 'data/flood_extent_county_month.csv')
    pe = load_extent_target(panel, extent_path)
    targets = [('onset', 'onset', panel), ('any flood month', 'y', panel)]
    if pe is not None:
        targets.append(('observed flooded area (Sentinel-1, top quartile)', 'y_extent', pe))
        panel = pe
    else:
        print(f'no {extent_path}: observed-flooding target skipped')
    out = [run_target(p, pc, ycol, label) for label, ycol, p in targets]
    lag, thr, nested, models, rank = (pd.concat([o[i] for o in out], ignore_index=True) for i in range(5))
    panel.assign(ym=panel.ym.astype(str)).to_csv(os.path.join(OUT_DIR, 'flood_trigger_features.csv'), index=False)
    n_on, n_any = int(panel['onset'].sum()), int(panel['y'].sum())
    notes = pd.DataFrame({'note': [
        f'Targets: (1) onset = first month of a flood displacement episode in a county ({n_on} county-months), the main target; (2) any month with flood displacement recorded ({n_any}); (3) observed flooded area from Sentinel-1 if data/flood_extent_county_month.csv exists (columns county,year,month,flooded_km2; top quartile within each county) - this one does not depend on when an assessment happened. {"Used." if pe is not None else "NOT available this run, so skipped."}',
        'Displacement is dated by assessment month (IOM DTM), so true onset is probably earlier than recorded; months with no report are not confirmed dry.',
        'Only counties with at least one flood displacement record are analysed; other months in those counties are the negatives.',
        f'Stations within {MAX_KM:.0f} km of a county polygon. Position on the river is approximated by latitude (Nile flows north): south = upstream, north = downstream, within {LOCAL_BAND_DEG} deg = local. Check Station_assignment for east-west reaches (Sobat, Pibor).',
        'River predictors: lvl = monthly max level as percentile of the station\'s own record; lvlz = z-score against the same calendar month in other years (removes the seasonal cycle); exc = share of passes above the station\'s own 90th percentile (flood-stage proxy); rise/rise3 = 1- and 3-month change. Altimetry passes are 10-35 days apart so monthly values are under-sampled.',
        'Lag_AUC and Best_thresholds are IN-SAMPLE screening (lag and cut-off picked on all the data) and are optimistic. Use Nested_CV and Models for skill.',
        'Nested_CV: for every held-out year (or county) the lag, direction and threshold are chosen on the other folds only. AUC_lo95/hi95 = bootstrap over whole counties. If the interval includes 0.5 there is no demonstrated skill.',
        'Models: ridge logistic on the best lag of each predictor (lag chosen inside each training fold). "+ county effects" adds a dummy per county; it can only be validated by leaving out years. The BENCHMARK row (a county\'s own event rate) is the bar to beat: predictors only add value if they beat it.',
        'Risk_ranking: each flood-season month the counties are ranked by out-of-fold model score; recall = share of events falling in the top k, compared with chance (k / counties). lift = precision / base rate.',
        'Soil moisture (SMAP L4) starts in 2015; rain is GSMaP v8 gauge-corrected. Both are county means at 5 km.']})
    path = os.path.join(OUT_DIR, 'flood_trigger_analysis.xlsx')
    with pd.ExcelWriter(path) as w:
        nested.to_excel(w, sheet_name='Nested_CV', index=False)
        models.to_excel(w, sheet_name='Models', index=False)
        rank.to_excel(w, sheet_name='Risk_ranking', index=False)
        thr.to_excel(w, sheet_name='Best_thresholds_insample', index=False)
        lag.to_excel(w, sheet_name='Lag_AUC_insample', index=False)
        assign.to_excel(w, sheet_name='Station_assignment', index=False)
        notes.to_excel(w, sheet_name='Notes', index=False)
    print('wrote', path)
    summ = os.environ.get('GITHUB_STEP_SUMMARY')
    if summ:
        with open(summ, 'a') as fh:
            fh.write('### Flood trigger analysis (honest validation)\n\n')
            for title, t, cols in (
                    ('Models vs benchmark', models, ['target', 'model', 'validation', 'AUC_cv', 'AUC_lo95', 'AUC_hi95', 'n_events']),
                    ('Risk ranking (top-k counties per month)', rank, ['target', 'model', 'top_k', 'recall', 'recall_by_chance', 'lift']),
                    ('Single predictors, nested CV (onset target)', nested[nested.target == 'onset'].sort_values('AUC_cv', ascending=False).head(12),
                     ['predictor', 'validation', 'AUC_cv', 'AUC_lo95', 'AUC_hi95', 'POD', 'FAR', 'TSS'])):
                if not t.empty:
                    fh.write(f'**{title}**\n\n' + t[cols].round(2).to_markdown(index=False) + '\n\n')
    print(models.round(3).to_string())
    print(rank.round(3).to_string())
    print(nested.round(3).to_string())


if __name__ == '__main__':
    selftest() if '--selftest' in sys.argv else main()
