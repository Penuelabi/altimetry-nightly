import readXlsxFile from 'read-excel-file/node';
import type { BulletinRow, PullResult, Station } from '@abuk/core';
import { bulletinHeadline, payamAt, whereIs, withinRadius } from '@abuk/core';
import { cfg, need } from './config';
import { csvObjects, findCol, num, parseCsv } from './csv';
import { c, driveDownload, driveFind, eeCompute, fn, loadImage, meanAround, meanOver, polygonGeometry, terrainExpr } from './adapters/google';
import { waterExpr } from './satellite';

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
    // A configured soil-moisture asset wins; otherwise the newest ERA5-Land day (top 7 cm of soil, m³/m³), public like NDVI.
    run('soil moisture', async () => {
      const asset = cfg.soilAsset || 'ic:ECMWF/ERA5_LAND/DAILY_AGGR', band = cfg.soilAsset ? cfg.soilBand : 'volumetric_soil_water_layer_1';
      const img = loadImage(asset);
      const r = await eeCompute(meanAround(band ? fn('Image.select', { input: img, bandSelectors: c([band]) }) : img, lat, lon, radiusKm * 1000, cfg.soilAsset ? 9000 : 11132));
      const v = band ? r[band] : Object.values(r).find(x => typeof x === 'number');
      return typeof v === 'number' ? Math.round(v * 1000) / 1000 : null;
    }),
    // Flood extent is computed from public satellite data like NDVI, over the payam the phone is in
    // (or a circle round the point outside any payam): no asset has to be uploaded or configured.
    run('flood extent', async () => {
      const area = payamAt(lat, lon);
      const { flood } = waterExpr();
      const r = await eeCompute(area ? meanOver(flood, polygonGeometry(area.polygons), 500) : meanAround(flood, lat, lon, radiusKm * 1000, 500));
      const v = r.flood;
      return typeof v === 'number' ? Math.round(Math.max(0, Math.min(1, v)) * 1000) / 10 : null;
    })
  ]);
  return { soilMoisture, floodExtentPct, errors };
}

export async function terrain(lat: number, lon: number) {
  const r = await eeCompute(terrainExpr(lat, lon));
  const slopeDeg = typeof r.slope === 'number' ? r.slope : null;
  return {
    elevation: typeof r.elevation === 'number' ? Math.round(r.elevation * 10) / 10 : null,
    slopePct: slopeDeg === null ? null : Math.round(Math.tan(slopeDeg * Math.PI / 180) * 1000) / 10
  };
}
