// ============================================================================
// Paste this into code.earthengine.google.com and click Run.
//
// Whole-country anticipatory-action watch, all 79 South Sudan counties at once
// (not a test subset) -- both hazards side by side, same thresholds as
// bulletin_extras.py's red/activation rule:
//
//   FLOOD:   at least 50% of a county's buildings (JRC GHS-OBAT 2020, VIDA
//            fallback), schools, health facilities, or GHSL built-up
//            settlement extent on flood-prone ground.
//   DROUGHT: more than 21 days since the last county-wide wet day (GSMaP),
//            computed properly here (not just charted) -- the observed half
//            of the drought rule.
//
// Honesty note: the drought side stops at the observed dry-spell count. The
// production rule's other clause -- less than 60% chance that 2 weeks of
// FORECAST rain, net of evapotranspiration, refill the soil deficit -- needs
// the ECMWF ensemble forecast, which is not an Earth Engine asset, so it
// isn't in this script. A county flagged here for drought is "in an observed
// dry spell", not yet "drought red" in the app's full sense; see
// gee_test_drought_recovery.py (run as a GitHub Action) for the fuller test
// that includes the ECMWF step, or the live bulletin for the real call.
// A county NOT flagged on this map can still be a flood/drought red in the
// real bulletin via a confirming news report alone (bulletin_extras.py) --
// that path has no Earth Engine input to test here.
//
// Read-only and standalone: never writes to any Earth Engine asset or to the
// altimetry-nightly repository; not wired into any GitHub Actions workflow.
// ============================================================================

var PAYAM = 'users/penuelabi/ssd_payam';
var SCHOOLS = 'projects/ee-penuelabi/assets/SDD_Schools';
var HEALTH = 'projects/ee-penuelabi/assets/SSD_Health';
var BUILD_GHSOBAT = 'projects/sat-io/open-datasets/JRC/GHS-OBAT/GHS_OBAT_GPKG_SSD_E2020_R2024A_V1_0';
var BUILD_VIDA = 'projects/sat-io/open-datasets/VIDA_COMBINED/SSD';
var GHSL_BUILT_S = 'JRC/GHSL/P2023A/GHS_BUILT_S/2020';
var FLOOD_EXTENT_ASSET = 'projects/sudan-1575919084043/assets/maximum_flood_extent';
var BASELINE_ASSET = 'projects/wajaras-remote-s-1565857510402/assets/flood_baseline_s1_0915_0926_2017_2025';
var SMAP_ID = 'NASA/SMAP/SPL4SMGP/008';     // change to .../007 if your account can't read 008
var GSMAP_ID = 'JAXA/GPM_L3/GSMaP/v8/operational';
var GSMAP_BAND = 'hourlyPrecipRateGC';
var A2 = 'ADM2_EN';

var FREQ_RARE = 0.15, MIN_FLOOD_YEARS = 3, BUILDINGS_SKIP_ABOVE = 40000;
var FLOOD_COUNTY_SHARE_SEVERE = 0.50;          // bulletin_extras.py FLOOD_COUNTY_SHARE_SEVERE
var DROUGHT_RED_DRY_DAYS = 21;                 // bulletin_extras.py DROUGHT_RED_DRY_DAYS
var WET_DAY_MM = 1.0;
var DRY_SPELL_LOOKBACK_DAYS = 45;
var DEFICIT_MIN_MM = 20;
var CLIM_YEARS = [2015, 2024];                 // SMAP record starts 2015

var payam = ee.FeatureCollection(PAYAM);       // whole country -- no county filter
print('Payams (whole country):', payam.size());

// ============================================================================
// FLOOD: buildings / settlement / schools / health exposure, county level
// ============================================================================
var risk, riskBasis;
try {
  ee.data.getAsset(BASELINE_ASSET);
  var base = ee.Image(BASELINE_ASSET);
  var freq = base.select('freq').unmask(0);
  var hasBase = base.select('n_years').unmask(0).gte(MIN_FLOOD_YEARS);
  var flooded;
  try {
    ee.data.getAsset(FLOOD_EXTENT_ASSET);
    flooded = ee.Image(FLOOD_EXTENT_ASSET).select(0).gt(0).unmask(0);
    riskBasis = 'Sentinel-1 same-season baseline + current extent';
  } catch (e2) {
    flooded = ee.Image.constant(0);
    riskBasis = 'Sentinel-1 same-season baseline';
  }
  risk = flooded.max(freq.gte(FREQ_RARE).and(hasBase)).rename('risk');
} catch (e) {
  var gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('max_extent').eq(1).unmask(0);
  var gfd = ee.ImageCollection('GLOBAL_FLOOD_DB/MODIS_EVENTS/V1').select('flooded').sum().gt(0).unmask(0);
  risk = gsw.max(gfd).rename('risk');
  riskBasis = 'JRC surface water + Global Flood DB (baseline asset not accessible)';
}
print('Flood-risk basis:', riskBasis);
var risk30 = risk.reproject('EPSG:4326', null, 30);

var bld, buildingsBasis;
try {
  ee.data.getAsset(BUILD_GHSOBAT);
  bld = ee.FeatureCollection(BUILD_GHSOBAT);
  buildingsBasis = 'JRC GHS-OBAT 2020 (sat-io)';
} catch (e) {
  bld = ee.FeatureCollection(BUILD_VIDA);
  buildingsBasis = 'VIDA combined buildings (sat-io) -- GHS-OBAT not accessible';
}
print('Buildings basis:', buildingsBasis);

var ghsl = ee.Image(GHSL_BUILT_S).select('built_surface').divide(1e6);   // m2/cell -> km2
var schoolsRisk = risk30.reduceRegions(ee.FeatureCollection(SCHOOLS), ee.Reducer.max(), 30);
var healthRisk = risk30.reduceRegions(ee.FeatureCollection(HEALTH), ee.Reducer.max(), 30);
var area = ee.Image.pixelArea().divide(1e6);

function perPayamFlood(f) {
  var g = f.geometry();
  var bands = area.rename('a').addBands(area.multiply(risk).rename('ar'))
    .addBands(ghsl.rename('bu')).addBands(ghsl.multiply(risk).rename('bur'));
  var a = bands.reduceRegion({reducer: ee.Reducer.sum(), geometry: g, scale: 100, maxPixels: 1e10, tileScale: 8});
  var sch = schoolsRisk.filterBounds(g), hlt = healthRisk.filterBounds(g), b = bld.filterBounds(g), nb = b.size();
  var bldRisk = ee.Number(ee.Algorithms.If(
    nb.lt(BUILDINGS_SKIP_ABOVE),
    risk30.reduceRegions({collection: b, reducer: ee.Reducer.max(), scale: 30, tileScale: 8})
      .filter(ee.Filter.gt('max', 0)).size(), -1));
  return f.set({
    county: f.get(A2), built_km2: a.get('bu'), built_risk_km2: a.get('bur'),
    schools: sch.size(), schools_risk: sch.filter(ee.Filter.gt('max', 0)).size(),
    health: hlt.size(), health_risk: hlt.filter(ee.Filter.gt('max', 0)).size(),
    buildings: nb, buildings_risk: bldRisk
  });
}
var payamFlood = payam.map(perPayamFlood);
var countyNames = ee.List(payamFlood.aggregate_array(A2)).distinct();

function perCountyFlood(name) {
  name = ee.String(name);
  var rows = payamFlood.filter(ee.Filter.eq(A2, name));
  function sumValid(p) { return ee.Number(rows.filter(ee.Filter.gte(p, 0)).aggregate_sum(p)); }
  function shareOf(total, risk_) { return ee.Number(ee.Algorithms.If(total.gt(0), risk_.divide(total), -1)); }
  var bShare = shareOf(sumValid('buildings'), sumValid('buildings_risk'));
  var sShare = shareOf(sumValid('schools'), sumValid('schools_risk'));
  var hShare = shareOf(sumValid('health'), sumValid('health_risk'));
  var settleShare = shareOf(sumValid('built_km2'), sumValid('built_risk_km2'));
  var maxShare = bShare.max(sShare).max(hShare).max(settleShare);
  return ee.Feature(null, {
    county: name, buildings_share: bShare, schools_share: sShare, health_share: hShare,
    settlement_share: settleShare, flood_severe: maxShare.gte(FLOOD_COUNTY_SHARE_SEVERE)
  });
}
var floodStats = ee.FeatureCollection(countyNames.map(perCountyFlood));

// ============================================================================
// DROUGHT: observed dry-spell days (GSMaP) + ET/soil-deficit context (SMAP L4)
// ============================================================================
var smap = ee.ImageCollection(SMAP_ID);
var endDate = ee.Date(Date.now()).advance(-3, 'day');

function landImage(end) {
  var e = ee.Date(end).advance(1, 'day');
  var et = smap.filterDate(e.advance(-30, 'day'), e).select(['land_evapotranspiration_flux'])
    .mean().multiply(86400 * 30).rename('et_30d_mm');
  var sm = smap.filterDate(e.advance(-3, 'day'), e).select(['sm_rootzone']).mean();
  return ee.Image.cat([et, sm]);
}

// dissolve payams to one geometry per county for the drought reduceRegions calls
var countyGeoms = ee.FeatureCollection(countyNames.map(function (name) {
  name = ee.String(name);
  return ee.Feature(payam.filter(ee.Filter.eq(A2, name)).geometry(1000), {county: name});
}));

var nowLand = landImage(endDate);
var climYears = ee.List.sequence(CLIM_YEARS[0], CLIM_YEARS[1]);
var climCollection = ee.ImageCollection.fromImages(climYears.map(function (y) {
  return landImage(endDate.update({year: ee.Number(y)}));
}));
var deficitImg = climCollection.select('sm_rootzone').median().subtract(nowLand.select('sm_rootzone'))
  .multiply(1000).max(0).rename('soil_deficit_mm');          // 0.01 m3/m3 over 1 m = 10 mm

var landStats = nowLand.addBands(deficitImg)
  .reduceRegions({collection: countyGeoms, reducer: ee.Reducer.mean(), scale: 10000, tileScale: 4});

// daily wet/dry per county for the last DRY_SPELL_LOOKBACK_DAYS days, newest first (d0 = most recent complete day)
var rain = ee.ImageCollection(GSMAP_ID).select(GSMAP_BAND);
var dayBands = ee.List.sequence(0, DRY_SPELL_LOOKBACK_DAYS - 1).map(function (i) {
  var d = endDate.advance(ee.Number(i).multiply(-1), 'day');
  return rain.filterDate(d, d.advance(1, 'day')).sum().gte(WET_DAY_MM).unmask(0).rename(ee.String('d').cat(ee.Number(i).int().format()));
});
var dayStack = ee.ImageCollection(dayBands).toBands().rename(ee.List.sequence(0, DRY_SPELL_LOOKBACK_DAYS - 1).map(
  function (i) { return ee.String('d').cat(ee.Number(i).int().format()); }));
var wetStats = dayStack.reduceRegions({collection: countyGeoms, reducer: ee.Reducer.mean(), scale: 10000, tileScale: 4});

function dryStreak(f) {
  var dayNames = ee.List.sequence(0, DRY_SPELL_LOOKBACK_DAYS - 1).map(
    function (i) { return ee.String('d').cat(ee.Number(i).int().format()); });
  var vals = dayNames.map(function (n) { return f.get(n); });
  var result = ee.Dictionary(vals.iterate(function (wetVal, acc) {
    acc = ee.Dictionary(acc);
    var done = ee.Number(acc.get('done'));
    var count = ee.Number(acc.get('count'));
    var isWet = ee.Number(wetVal).gte(0.5);       // county-mean of a 0/1 band; >=0.5 = "wet" for most of the county
    var newDone = done.max(isWet);
    var newCount = count.add(ee.Number(1).subtract(done).multiply(ee.Number(1).subtract(isWet)));
    return ee.Dictionary({done: newDone, count: newCount});
  }, ee.Dictionary({done: 0, count: 0})));
  return f.set('dry_spell_days', result.get('count'));
}
var dryStats = wetStats.map(dryStreak).select(['county', 'dry_spell_days']);

// join the three drought tables (land + dry-spell) on county name
var droughtJoined = ee.Join.inner().apply(
  landStats.select(['county', 'et_30d_mm', 'soil_deficit_mm']), dryStats,
  ee.Filter.equals({leftField: 'county', rightField: 'county'}));
var droughtStats = droughtJoined.map(function (pair) {
  var l = ee.Feature(pair.get('primary')), r = ee.Feature(pair.get('secondary'));
  var days = ee.Number(r.get('dry_spell_days'));
  return ee.Feature(null, {
    county: l.get('county'), et_30d_mm: l.get('et_30d_mm'), soil_deficit_mm: l.get('soil_deficit_mm'),
    dry_spell_days: days, dry_spell_over_bar: days.gt(DROUGHT_RED_DRY_DAYS)
  });
});

// ============================================================================
// COMBINE: one AA watch table + map for the whole country
// ============================================================================
var combined = ee.Join.inner().apply(
  floodStats, droughtStats, ee.Filter.equals({leftField: 'county', rightField: 'county'})
).map(function (pair) {
  var l = ee.Feature(pair.get('primary')), r = ee.Feature(pair.get('secondary'));
  var floodSevere = ee.Number(l.get('flood_severe'));
  var droughtFlag = ee.Number(r.get('dry_spell_over_bar'));
  return ee.Feature(null, {
    county: l.get('county'),
    flood_severe: floodSevere, buildings_share: l.get('buildings_share'), schools_share: l.get('schools_share'),
    health_share: l.get('health_share'), settlement_share: l.get('settlement_share'),
    dry_spell_days: r.get('dry_spell_days'), dry_spell_over_bar: droughtFlag,
    et_30d_mm: r.get('et_30d_mm'), soil_deficit_mm: r.get('soil_deficit_mm'),
    aa_watch: floodSevere.max(droughtFlag)
  });
});
var combinedFc = ee.FeatureCollection(combined);

print('South Sudan, all counties -- AA watch (1 = flagged; drought here is the observed dry-spell clause only, ' +
      'see the note at the top of the script for what is not included):', combinedFc);
print('Counties flagged for flood (exposure >= ' + (FLOOD_COUNTY_SHARE_SEVERE * 100) + '%):',
      combinedFc.filter(ee.Filter.eq('flood_severe', 1)).size());
print('Counties flagged for drought (dry spell > ' + DROUGHT_RED_DRY_DAYS + ' days):',
      combinedFc.filter(ee.Filter.eq('dry_spell_over_bar', 1)).size());

// --- map, whole country ---------------------------------------------------------------------------------------
Map.centerObject(payam, 6);
Map.addLayer(payam.style({color: '888888', fillColor: '00000000'}), {}, 'Payam boundaries');

var floodNames = combinedFc.filter(ee.Filter.eq('flood_severe', 1)).aggregate_array('county');
var droughtNames = combinedFc.filter(ee.Filter.eq('dry_spell_over_bar', 1)).aggregate_array('county');
Map.addLayer(payam.filter(ee.Filter.inList(A2, floodNames)).style({color: '1565c0', fillColor: '1565c033', width: 2}),
             {}, 'Flood-flagged counties');
Map.addLayer(payam.filter(ee.Filter.inList(A2, droughtNames)).style({color: 'd84315', fillColor: 'd8431533', width: 2}),
             {}, 'Drought (dry-spell)-flagged counties');
