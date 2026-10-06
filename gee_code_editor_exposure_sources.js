// ============================================================================
// Paste this into code.earthengine.google.com and click Run.
//
// Flood exposure sources test: JRC GHS-OBAT 2020 buildings (VIDA combined
// buildings fallback) and GHSL built-up settlement extent, aggregated to
// COUNTY level (not payam), checked against the 50% severe-exposure bar used
// for the flood red/activation rule in bulletin_extras.py.
//
// Read-only and standalone: this script never writes to any Earth Engine
// asset or to the altimetry-nightly repository, and is not wired into any
// GitHub Actions workflow. It's the interactive, in-browser twin of
// gee_test_exposure_sources.py (same repo, run as a GitHub Action instead).
// ============================================================================

var PAYAM = 'users/penuelabi/ssd_payam';
var SCHOOLS = 'projects/ee-penuelabi/assets/SDD_Schools';
var HEALTH = 'projects/ee-penuelabi/assets/SSD_Health';
var BUILD_GHSOBAT = 'projects/sat-io/open-datasets/JRC/GHS-OBAT/GHS_OBAT_GPKG_SSD_E2020_R2024A_V1_0';
var BUILD_VIDA = 'projects/sat-io/open-datasets/VIDA_COMBINED/SSD';
var GHSL_BUILT_S = 'JRC/GHSL/P2023A/GHS_BUILT_S/2020';
var FLOOD_EXTENT_ASSET = 'projects/sudan-1575919084043/assets/maximum_flood_extent';
var BASELINE_ASSET = 'projects/wajaras-remote-s-1565857510402/assets/flood_baseline_s1_0915_0926_2017_2025';
var FREQ_RARE = 0.15;
var MIN_FLOOD_YEARS = 3;
var A2 = 'ADM2_EN';
var FLOOD_COUNTY_SHARE_SEVERE = 0.50;      // matches bulletin_extras.py -- kept in sync by hand, not imported
var BUILDINGS_SKIP_ABOVE = 40000;          // same safety cap as exposure_cache.py: skip per-building risk check above this

// Edit this to test a few counties fast instead of all 79, e.g. ['Duk', 'Fangak']
var ONLY_COUNTIES = [];

var payam = ee.FeatureCollection(PAYAM);
if (ONLY_COUNTIES.length) {
  payam = payam.filter(ee.Filter.inList(A2, ONLY_COUNTIES));
}
print('Payams selected:', payam.size());

// --- flood-risk raster: same definition as exposure_cache.py / the GEE app ------------------------------------
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
Map.addLayer(risk30.selfMask(), {palette: ['3388ff']}, 'Flood-prone ground', false);

// --- buildings: GHS-OBAT with VIDA fallback ---------------------------------------------------------------------
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

// --- settlement extent: GHSL built-up surface, 2020 --------------------------------------------------------------
var ghsl = ee.Image(GHSL_BUILT_S).select('built_surface').divide(1e6);   // m2/cell -> km2
Map.addLayer(ghsl.selfMask(), {min: 0, max: 0.01, palette: ['ffffcc', '800026']},
             'GHSL built-up surface (km2/cell)', false);

var schools = ee.FeatureCollection(SCHOOLS);
var health = ee.FeatureCollection(HEALTH);
var schoolsRisk = risk30.reduceRegions(schools, ee.Reducer.max(), 30);
var healthRisk = risk30.reduceRegions(health, ee.Reducer.max(), 30);

// --- per-payam exposure, computed server-side ---------------------------------------------------------------------
var area = ee.Image.pixelArea().divide(1e6);

function perPayam(f) {
  var g = f.geometry();
  var bands = area.rename('a').addBands(area.multiply(risk).rename('ar'))
    .addBands(ghsl.rename('bu')).addBands(ghsl.multiply(risk).rename('bur'));
  var a = bands.reduceRegion({reducer: ee.Reducer.sum(), geometry: g, scale: 100, maxPixels: 1e10, tileScale: 8});
  var sch = schoolsRisk.filterBounds(g);
  var hlt = healthRisk.filterBounds(g);
  var b = bld.filterBounds(g);
  var nb = b.size();
  // Same safety cap as exposure_cache.py: skip the per-building risk check above BUILDINGS_SKIP_ABOVE (-1 = unknown,
  // excluded from the county sum below rather than silently counted as 0 at-risk buildings).
  var bldRisk = ee.Number(ee.Algorithms.If(
    nb.lt(BUILDINGS_SKIP_ABOVE),
    risk30.reduceRegions({collection: b, reducer: ee.Reducer.max(), scale: 30, tileScale: 8})
      .filter(ee.Filter.gt('max', 0)).size(),
    -1));
  return f.set({
    county: f.get(A2),
    built_km2: a.get('bu'), built_risk_km2: a.get('bur'),
    schools: sch.size(), schools_risk: sch.filter(ee.Filter.gt('max', 0)).size(),
    health: hlt.size(), health_risk: hlt.filter(ee.Filter.gt('max', 0)).size(),
    buildings: nb, buildings_risk: bldRisk
  });
}
var payamStats = payam.map(perPayam);

// --- aggregate to county level, skipping any -1 (unknown) payam values -------------------------------------------
var counties = ee.List(payamStats.aggregate_array(A2)).distinct();

function perCounty(name) {
  name = ee.String(name);
  var rows = payamStats.filter(ee.Filter.eq(A2, name));

  function sumValid(prop) {
    return ee.Number(rows.filter(ee.Filter.gte(prop, 0)).aggregate_sum(prop));
  }

  var buildings = sumValid('buildings'), buildingsRisk = sumValid('buildings_risk');
  var schoolsT = sumValid('schools'), schoolsRiskT = sumValid('schools_risk');
  var healthT = sumValid('health'), healthRiskT = sumValid('health_risk');
  var builtKm2 = sumValid('built_km2'), builtRiskKm2 = sumValid('built_risk_km2');

  function shareOf(total, riskSum) {
    return ee.Number(ee.Algorithms.If(total.gt(0), riskSum.divide(total), -1));
  }

  var bShare = shareOf(buildings, buildingsRisk);
  var sShare = shareOf(schoolsT, schoolsRiskT);
  var hShare = shareOf(healthT, healthRiskT);
  var settleShare = shareOf(builtKm2, builtRiskKm2);
  var maxShare = bShare.max(sShare).max(hShare).max(settleShare);
  var severe = maxShare.gte(FLOOD_COUNTY_SHARE_SEVERE);

  return ee.Feature(null, {
    county: name,
    buildings_share: bShare, schools_share: sShare,
    health_share: hShare, settlement_share: settleShare,
    severe_flood_exposure: severe
  });
}

var countyStats = ee.FeatureCollection(counties.map(perCounty));

print('County-level exposure shares (-1 = not enough data; severe = any share >= ' +
      (FLOOD_COUNTY_SHARE_SEVERE * 100) + '%):', countyStats);
print('Counties at/above the severe bar:', countyStats.filter(ee.Filter.eq('severe_flood_exposure', true)).size());

// --- map context --------------------------------------------------------------------------------------------------
Map.centerObject(payam, 6);
Map.addLayer(payam.style({color: '888888', fillColor: '00000000'}), {}, 'Payam boundaries');

// Outline, in red, the payams of any county that reached the severe bar.
var severeNames = countyStats.filter(ee.Filter.eq('severe_flood_exposure', true)).aggregate_array('county');
var severePayams = payam.filter(ee.Filter.inList(A2, severeNames));
Map.addLayer(severePayams.style({color: 'ff0000', fillColor: '00000000', width: 2}),
             {}, 'Counties >= severe exposure bar');
