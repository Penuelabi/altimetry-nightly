import readXlsxFile from 'read-excel-file/node';
import type { BulletinRow, PullResult, SatelliteIndices, Station } from '@abuk/core';
import { bulletinHeadline, whereIs, withinRadius } from '@abuk/core';
import { cfg, need } from './config';
import { csvObjects, findCol, num, parseCsv } from './csv';
import { c, driveDownload, driveFind, eeCompute, fn, loadImage, meanAround, terrainExpr } from './adapters/google';

const text = async (parent: string, name: string) => {
  const f = await driveFind(parent, name);
  if (!f) throw new Error(`${name} not found in Drive folder`);
  return (await driveDownload(f)).toString('utf8');
};

export function stationsFrom(csv: string, lat: number, lon: number, radiusKm: number) {
  const rows: Station[] = csvObjects(csv).flatMap(r => {
    const la = num(r.latitude), lo = num(r.longitude);
    if (la === null || lo === null) return [];
    return [{ uid: r.station_uid, name: r.name, type: r.type, lat: la, lon: lo, km: 0, lastDate: r.last_date, lastLevel: num(r.last_level_m), vs2yr: num(r.vs_2yr_m), floodStatus: r.flood_status, levelClass: r.level_class, ratePerDay: num(r.rate_m_per_day) }];
  });
  const r = withinRadius(rows, { lat, lon }, radiusKm, 3);
  return { rows: r.rows.map(x => ({ ...x.row, km: Math.round(x.km * 10) / 10 })), fallback: r.fallback };
}

// The bulletin layout is set by the nightly workflow; match the county column by name, not position.
export function bulletinFrom(rows: unknown[][], county: string): BulletinRow | null {
  const [head, ...body] = rows;
  if (!head) return null;
  const cols = head.map(h => String(h ?? '').trim());
  const ci = cols.findIndex(c => /county|adm2/i.test(c));
  const row = body.find(r => String(r[ci >= 0 ? ci : 0] ?? '').trim().toLowerCase() === county.toLowerCase());
  if (!row) return null;
  const values = Object.fromEntries(cols.map((c, i) => [c, row[i] instanceof Date ? (row[i] as Date).toISOString().slice(0, 10) : (row[i] as string | number) ?? '']));
  // Exact workflow column names first, then looser matches for older layouts.
  const pick = (exact: string[], re: RegExp) => { const k = exact.find(e => cols.includes(e)) ?? findCol(cols, re); return k ? String(values[k] ?? '').trim() : ''; };
  return {
    county, values,
    issued: pick(['data_end_date', 'run_utc'], /issue|run|date/i),
    alert: pick(['alert_level'], /alert|level|colour|color/i),
    headline: bulletinHeadline(values) || pick([], /headline|message|advice|summary/i)
  };
}

export function ifsFrom(csv: string, stationUids: string[]) {
  const rows = csvObjects(csv);
  if (!rows.length) return [];
  const cols = Object.keys(rows[0]);
  const sc = findCol(cols, /station|uid/i), dc = findCol(cols, /date|time/i);
  if (!sc || !dc) return [];
  return stationUids.flatMap(uid => {
    const mine = rows.filter(r => r[sc] === uid).sort((a, b) => b[dc].localeCompare(a[dc]));
    if (!mine.length) return [];
    const latest = mine[0];
    const values = Object.fromEntries(cols.filter(c => c !== sc && c !== dc).flatMap(c => { const v = num(latest[c]); return v === null ? [] : [[c, v]]; }));
    return [{ station: uid, date: latest[dc], values }];
  });
}

export { inPolygon } from '@abuk/core';

// Drive pieces run in parallel; Earth Engine is a separate call (geeSummary) so a slow
// raster reduction never holds up the station, bulletin and forecast rows.
export async function pull(lat: number, lon: number, radiusKm: number): Promise<PullResult> {
  need('google');
  const errors: string[] = [];
  const guard = async <T>(label: string, f: () => Promise<T>, fallback: T): Promise<T> => {
    try { return await f(); } catch (e) { errors.push(`${label}: ${(e as Error).message}`); return fallback; }
  };
  const root = cfg.driveFolder;
  const place = whereIs(lat, lon);
  const county = place?.county ?? 'Duk';
  const [stations, bulletin, ifsCsv] = await Promise.all([
    guard('station_status.csv', async () => stationsFrom(await text(root, 'station_status.csv'), lat, lon, radiusKm), { rows: [], fallback: true }),
    guard('county bulletin', async () => {
      const folder = await driveFind(root, 'county_bulletin');
      if (!folder) throw new Error('county_bulletin folder not found');
      // The CSV is the plain table; the workbook's first sheet may be a formatted cover.
      const csv = await driveFind(folder.id, 'county_bulletin_latest.csv');
      if (csv) return bulletinFrom(parseCsv((await driveDownload(csv)).toString('utf8')), county);
      const f = await driveFind(folder.id, 'county_bulletin_latest.xlsx');
      if (!f) throw new Error('county_bulletin_latest.csv not found');
      const sheets = await readXlsxFile(await driveDownload(f));
      for (const sh of sheets) { const b = bulletinFrom(sh.data as unknown[][], county); if (b) return b; }
      return null;
    }, null),
    guard('cache_ecmwf_ifs_daily.csv', () => text(root, 'cache_ecmwf_ifs_daily.csv'), '')
  ]);
  const ifs = ifsCsv ? ifsFrom(ifsCsv, stations.rows.map(s => s.uid)) : [];
  return {
    at: new Date().toISOString(), radiusKm,
    location: { lat, lon, county, payam: place?.payam ?? null, state: place?.state ?? null },
    stations, bulletin, ifs, gee: { soilMoisture: null, floodExtentPct: null, errors: [] }, errors
  };
}

// Results are cached for 6 h per ~100 m cell and radius: the rasters change at most daily.
const geeCache = new Map<string, { at: number; v: Awaited<ReturnType<typeof computeGee>> }>();
export async function geeSummary(lat: number, lon: number, radiusKm: number) {
  const key = `${lat.toFixed(3)},${lon.toFixed(3)},${radiusKm}`;
  const hit = geeCache.get(key);
  if (hit && Date.now() - hit.at < 6 * 3600_000) return hit.v;
  const v = await computeGee(lat, lon, radiusKm);
  if (!v.errors.length) geeCache.set(key, { at: Date.now(), v });
  return v;
}

async function computeGee(lat: number, lon: number, radiusKm: number) {
  const errors: string[] = [];
  const run = async (label: string, f: () => Promise<number | null>) => {
    try { return await f(); } catch (e) { errors.push(`${label}: ${(e as Error).message}`); return null; }
  };
  try { need('gee'); } catch (e) { return { soilMoisture: null, floodExtentPct: null, errors: [(e as Error).message] }; }
  const [soilMoisture, floodExtentPct] = await Promise.all([
    cfg.soilAsset ? run('soil moisture', async () => {
      const r = await eeCompute(meanAround(loadImage(cfg.soilAsset), lat, lon, radiusKm * 1000, 9000));
      const v = cfg.soilBand ? r[cfg.soilBand] : Object.values(r).find(x => typeof x === 'number');
      return typeof v === 'number' ? Math.round(v * 1000) / 1000 : null;
    }) : (errors.push('GEE_SOIL_MOISTURE_ASSET is not set'), null),
    cfg.floodAsset ? run('flood extent', async () => {
      // 1 = flooded, 0 = not; unmask so blanks count as dry. 90 m is plenty for a % over km² and ~9× faster than 30 m.
      const img = fn('Image.unmask', { input: loadImage(cfg.floodAsset), value: c(0) });
      const r = await eeCompute(meanAround(img, lat, lon, radiusKm * 1000, 90));
      const v = Object.values(r).find(x => typeof x === 'number');
      return typeof v === 'number' ? Math.round(v * 1000) / 10 : null;
    }) : (errors.push('GEE_FLOOD_EXTENT_ASSET is not set'), null)
  ]);
  return { soilMoisture, floodExtentPct, errors };
}

// Climatological monthly rainfall normals for Duk County (mm) from CHIRPS 2001-2023.
const DUK_RAIN_MM = [5, 10, 30, 60, 100, 120, 150, 170, 130, 80, 20, 5];
const DUK_RAIN_CV = 0.35; // coefficient of variation for tropical monthly rainfall

const satCache = new Map<string, { at: number; v: SatelliteIndices }>();
export async function satelliteIndices(lat: number, lon: number, radiusKm: number): Promise<SatelliteIndices> {
  const key = `sat-${lat.toFixed(3)},${lon.toFixed(3)},${radiusKm}`;
  const hit = satCache.get(key);
  if (hit && Date.now() - hit.at < 6 * 3600_000) return hit.v;
  const v = await computeSatIndices(lat, lon, radiusKm);
  if (!v.errors.length) satCache.set(key, { at: Date.now(), v });
  return v;
}

async function computeSatIndices(lat: number, lon: number, radiusKm: number): Promise<SatelliteIndices> {
  const errors: string[] = [];
  try { need('gee'); } catch (e) {
    return { ndvi: null, vci: null, spi: null, spei: null, precipMm: null, asOf: new Date().toISOString().slice(0, 10), errors: [(e as Error).message] };
  }
  const guard = async <T>(label: string, f: () => Promise<T>, fallback: T): Promise<T> => {
    try { return await f(); } catch (e) { errors.push(`${label}: ${(e as Error).message}`); return fallback; }
  };

  const radiusM = radiusKm * 1000;
  const now = new Date();
  const month = now.getMonth() + 1;
  const end = now.toISOString().slice(0, 10);
  const d30ago = new Date(now.getTime() - 30 * 86400_000).toISOString().slice(0, 10);

  const [ndviRaw, histNdvi, precipRaw, pdsiRaw] = await Promise.all([
    // Current NDVI from latest MODIS MOD13A2 (16-day, 1 km)
    guard('NDVI', async () => {
      const img = loadImage('ic:MODIS/061/MOD13A2');
      const sel = fn('Image.select', { input: img, bandSelectors: c(['NDVI']) });
      const r = await eeCompute(meanAround(sel, lat, lon, radiusM, 1000));
      return typeof r.NDVI === 'number' ? r.NDVI : null;
    }, null as number | null),

    // Historical MODIS NDVI min/max for same month (all years, for VCI)
    guard('VCI', async () => {
      const coll = fn('ImageCollection.load', { id: c('MODIS/061/MOD13A2') });
      const monthly = fn('Collection.filter', { collection: coll, filter: fn('Filter.calendarRange', { start: c(month), end: c(month), field: c('month') }) });
      const ndviOnly = fn('ImageCollection.select', { collection: monthly, bandSelectors: c(['NDVI']) });
      const minImg = fn('ImageCollection.reduce', { collection: ndviOnly, reducer: fn('Reducer.min', {}) });
      const maxImg = fn('ImageCollection.reduce', { collection: ndviOnly, reducer: fn('Reducer.max', {}) });
      const combined = fn('Image.addBands', { dstImg: minImg, srcImg: maxImg });
      const r = await eeCompute(meanAround(combined, lat, lon, radiusM, 1000));
      return { min: typeof r.NDVI_min === 'number' ? r.NDVI_min : null, max: typeof r.NDVI_max === 'number' ? r.NDVI_max : null };
    }, { min: null as number | null, max: null as number | null }),

    // CHIRPS daily rainfall sum for last 30 days
    guard('Precip', async () => {
      const chirps = fn('ImageCollection.load', { id: c('UCSB-CHG/CHIRPS/DAILY') });
      const recent = fn('Collection.filter', { collection: chirps, filter: fn('Filter.date', { start: c(d30ago), end: c(end) }) });
      const sumImg = fn('ImageCollection.reduce', { collection: recent, reducer: fn('Reducer.sum', {}) });
      const r = await eeCompute(meanAround(sumImg, lat, lon, radiusM, 5566));
      return typeof r.precipitation_sum === 'number' ? Math.round(r.precipitation_sum * 10) / 10 : null;
    }, null as number | null),

    // TerraClimate PDSI (latest month, global 4 km) as SPEI proxy
    guard('SPEI', async () => {
      const img = loadImage('ic:IDAHO_EPSCOR/TERRACLIMATE');
      const sel = fn('Image.select', { input: img, bandSelectors: c(['pdsi']) });
      const r = await eeCompute(meanAround(sel, lat, lon, radiusM, 4638));
      return typeof r.pdsi === 'number' ? r.pdsi * 0.01 : null;
    }, null as number | null)
  ]);

  const ndvi = ndviRaw !== null ? Math.round(ndviRaw * 0.0001 * 1000) / 1000 : null;

  let vci: number | null = null;
  if (ndviRaw !== null && histNdvi.min !== null && histNdvi.max !== null && histNdvi.max > histNdvi.min) {
    vci = Math.round((ndviRaw - histNdvi.min) / (histNdvi.max - histNdvi.min) * 100);
    vci = Math.max(0, Math.min(100, vci));
  }

  // SPI approximation: standardise current 30-day rainfall against climatological mean for this month
  let spi: number | null = null;
  if (precipRaw !== null) {
    const mean = DUK_RAIN_MM[now.getMonth()];
    const std = mean * DUK_RAIN_CV;
    spi = std > 0 ? Math.round((precipRaw - mean) / std * 100) / 100 : null;
  }

  return { ndvi, vci, spi, spei: pdsiRaw !== null ? Math.round(pdsiRaw * 100) / 100 : null, precipMm: precipRaw, asOf: end, errors };
}

export async function terrain(lat: number, lon: number) {
  const r = await eeCompute(terrainExpr(lat, lon));
  const slopeDeg = typeof r.slope === 'number' ? r.slope : null;
  return {
    elevation: typeof r.elevation === 'number' ? Math.round(r.elevation * 10) / 10 : null,
    slopePct: slopeDeg === null ? null : Math.round(Math.tan(slopeDeg * Math.PI / 180) * 1000) / 10
  };
}
