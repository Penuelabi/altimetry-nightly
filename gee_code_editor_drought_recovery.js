// ============================================================================
// Paste this into code.earthengine.google.com and click Run.
//
// Drought/recovery inputs test: 30-day SMAP L4 evapotranspiration, root-zone
// soil-moisture deficit (vs. a multi-year same-day climatology), and a chart
// of the last 45 days of county rain so you can read the dry spell visually.
//
// Honesty note: this covers the two inputs that ARE Earth Engine data (SMAP
// L4 ET/soil moisture, GSMaP observed rain). The evaporation-adjusted
// "chance that 2 weeks of forecast rain refill the deficit" also needs the
// ECMWF ensemble forecast, which is NOT an Earth Engine asset (it's the same
// ecmwf-opendata API county_bulletin.py calls outside of GEE) -- so it is
// not reproduced here. See gee_test_drought_recovery.py in the repo (run as
// a GitHub Action) for the fuller test that includes that step.
//
// Read-only and standalone: never writes to any asset, not wired into any
// GitHub Actions workflow.
// ============================================================================

var AOI_ASSET = 'users/penuelabi/ssd_payam';
var A2 = 'ADM2_EN';
var SMAP_ID = 'NASA/SMAP/SPL4SMGP/008';     // falls back to 007 below if 008 has no data
var GSMAP_ID = 'JAXA/GPM_L3/GSMaP/v8/operational';
var GSMAP_BAND = 'hourlyPrecipRateGC';
var CLIM_YEARS = [2015, 2024];              // SMAP record starts 2015; current year excluded automatically
var DRY_SPELL_LOOKBACK_DAYS = 45;
var WET_DAY_MM = 1.0;

// Edit this to test a few counties fast instead of all 79, e.g. ['Duk', 'Fangak']
var ONLY_COUNTIES = ['Duk', 'Fangak', 'Ayod'];

var aoi = ee.FeatureCollection(AOI_ASSET);
var counties = ONLY_COUNTIES.length ? aoi.filter(ee.Filter.inList(A2, ONLY_COUNTIES)) : aoi;
print('Counties selected:', counties.aggregate_array(A2).distinct());

var smap = ee.ImageCollection(SMAP_ID);   // if your account can't read SPL4SMGP/008, change SMAP_ID above to .../007
var endDate = ee.Date(Date.now()).advance(-3, 'day');   // SMAP L4 runs ~3 days behind; adjust if needed

function landImage(end) {
  var e = ee.Date(end).advance(1, 'day');
  var flux = smap.filterDate(e.advance(-30, 'day'), e)
    .select(['land_evapotranspiration_flux']).mean().multiply(86400 * 30).rename('et_30d_mm');
  var sm = smap.filterDate(e.advance(-3, 'day'), e).select(['sm_rootzone']).mean();
  return ee.Image.cat([flux, sm]);
}

function countyMeans(img, label) {
  return img.reduceRegions({collection: counties, reducer: ee.Reducer.mean(), scale: 10000, tileScale: 4})
    .map(function (f) { return f.set('county', f.get(A2)).set('label', label); });
}

var now = landImage(endDate);
var nowStats = countyMeans(now, 'now');
print('Current 30-day ET (mm) and root-zone soil moisture, per county:', nowStats);

// --- climatology for the soil deficit: same day-of-year, CLIM_YEARS[0]-CLIM_YEARS[1] -------------------------------
var climYears = ee.List.sequence(CLIM_YEARS[0], CLIM_YEARS[1]);
var climImgs = climYears.map(function (y) {
  y = ee.Number(y);
  var sameDay = endDate.update({year: y});
  return landImage(sameDay).set('year', y);
});
var climCollection = ee.ImageCollection.fromImages(climImgs);
var climMedianSM = climCollection.select('sm_rootzone').median().rename('sm_rootzone_median');

var deficitImg = climMedianSM.subtract(now.select('sm_rootzone')).multiply(1000)   // 0.01 m3/m3 over 1 m = 10 mm
  .max(0).rename('soil_deficit_mm');
var deficitStats = countyMeans(deficitImg, 'deficit');
print('Soil deficit (mm, 0 = at or above the ' + CLIM_YEARS[0] + '-' + CLIM_YEARS[1] +
      ' median for this day of year):', deficitStats);

// --- visual dry-spell check: chart the last N days of county rain ---------------------------------------------------
var rain = ee.ImageCollection(GSMAP_ID).select(GSMAP_BAND);
var days = ee.List.sequence(0, DRY_SPELL_LOOKBACK_DAYS - 1).map(function (i) {
  var d = endDate.advance(ee.Number(i).multiply(-1), 'day');
  return rain.filterDate(d, d.advance(1, 'day')).sum().set('system:time_start', d.millis());
});
var rainSeries = ee.ImageCollection.fromImages(days);

var chart = ui.Chart.image.seriesByRegion({
  imageCollection: rainSeries, regions: counties, reducer: ee.Reducer.mean(),
  band: GSMAP_BAND, scale: 10000, seriesProperty: A2, xProperty: 'system:time_start'
}).setOptions({
  title: 'Daily county rain, last ' + DRY_SPELL_LOOKBACK_DAYS + ' days (read the dry spell off this: a run of ' +
         'days at/near 0 mm, most recent on the right)',
  vAxis: {title: 'mm/day'}, hAxis: {title: 'date'},
  lineWidth: 2, pointSize: 3
});
print(chart);
print('The ' + WET_DAY_MM + ' mm/day line is the wet/dry threshold the app uses -- a county is in a dry spell for ' +
      'every consecutive day below that, counting back from the most recent day with data.');

// --- map context ------------------------------------------------------------------------------------------------
Map.centerObject(counties, 6);
Map.addLayer(counties.style({color: '888888', fillColor: '00000000'}), {}, 'County boundaries');
Map.addLayer(deficitImg.clip(counties), {min: 0, max: 60, palette: ['ffffcc', 'fd8d3c', '800026']},
             'Soil deficit (mm)');
