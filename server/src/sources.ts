import readXlsxFile from 'read-excel-file/node';
import * as shapefile from 'shapefile';
import type { BulletinRow, PullResult, Station } from '@abuk/core';
import { withinRadius } from '@abuk/core';
import { cfg, need } from './config';
import { csvObjects, findCol, num } from './csv';
import { driveDownload, driveFind, driveList, eeCompute, loadImage, meanAround, terrainExpr } from './adapters/google';

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
  const pick = (re: RegExp) => { const k = findCol(cols, re); return k ? String(values[k] ?? '') : ''; };
  return { county, issued: pick(/issue|run|date/i), alert: pick(/alert|level|colour|color/i), headline: pick(/headline|message|advice|summary/i), values };
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

// Ray casting over GeoJSON rings.
export function inPolygon(lon: number, lat: number, coords: number[][][]) {
  let inside = false;
  for (const ring of coords) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

let payamCache: { shp: string; feats: { name: string; county: string; polys: number[][][][] }[] } | null = null;
async function payamAt(lat: number, lon: number) {
  const folder = await driveFind(cfg.driveFolder, 'ssd_payam');
  if (!folder) throw new Error('ssd_payam folder not found');
  const files = await driveList(folder.id);
  const shp = files.find(f => f.name.toLowerCase().endsWith('.shp')), dbf = files.find(f => f.name.toLowerCase().endsWith('.dbf'));
  if (!shp || !dbf) throw new Error('ssd_payam has no .shp/.dbf');
  if (payamCache?.shp !== shp.modifiedTime) {
    const src = await shapefile.open(await driveDownload(shp), await driveDownload(dbf));
    const feats: NonNullable<typeof payamCache>['feats'] = [];
    for (let r = await src.read(); !r.done; r = await src.read()) {
      const g = r.value.geometry as { type: string; coordinates: number[][][] | number[][][][] };
      const p = r.value.properties as Record<string, unknown>;
      const keys = Object.keys(p);
      const nk = keys.find(k => /payam|adm3_?en|adm3_?name|^adm3$/i.test(k)) ?? keys[0];
      const ck = keys.find(k => /county|adm2_?en|adm2_?name/i.test(k));
      feats.push({ name: String(p[nk] ?? ''), county: ck ? String(p[ck] ?? '') : '', polys: g.type === 'MultiPolygon' ? g.coordinates as number[][][][] : [g.coordinates as number[][][]] });
    }
    payamCache = { shp: shp.modifiedTime, feats };
  }
  return payamCache.feats.find(f => f.polys.some(poly => inPolygon(lon, lat, poly))) ?? null;
}

export async function pull(lat: number, lon: number, radiusKm: number, county = 'Duk'): Promise<PullResult> {
  need('google');
  const errors: string[] = [];
  const guard = async <T>(label: string, f: () => Promise<T>, fallback: T): Promise<T> => {
    try { return await f(); } catch (e) { errors.push(`${label}: ${(e as Error).message}`); return fallback; }
  };
  const root = cfg.driveFolder;
  const stations = await guard('station_status.csv', async () => stationsFrom(await text(root, 'station_status.csv'), lat, lon, radiusKm), { rows: [], fallback: true });
  const bulletin = await guard('county bulletin', async () => {
    const folder = await driveFind(root, 'county_bulletin');
    const f = folder && await driveFind(folder.id, 'county_bulletin_latest.xlsx');
    if (!f) throw new Error('county_bulletin_latest.xlsx not found');
    const [sheet] = await readXlsxFile(await driveDownload(f));
    return bulletinFrom(sheet.data as unknown[][], county);
  }, null);
  const ifs = await guard('cache_ecmwf_ifs_daily.csv', async () => ifsFrom(await text(root, 'cache_ecmwf_ifs_daily.csv'), stations.rows.map(s => s.uid)), []);
  const payam = await guard('ssd_payam', () => payamAt(lat, lon), null);
  const gee = await geeSummary(lat, lon, radiusKm);
  return { at: new Date().toISOString(), radiusKm, location: { lat, lon, county: payam?.county || county, payam: payam?.name ?? null }, stations, bulletin, ifs, gee, errors };
}

export async function geeSummary(lat: number, lon: number, radiusKm: number) {
  const errors: string[] = [];
  let soilMoisture: number | null = null, floodExtentPct: number | null = null;
  try {
    need('gee');
    if (!cfg.soilAsset) errors.push('GEE_SOIL_MOISTURE_ASSET is not set');
    else {
      const r = await eeCompute(meanAround(loadImage(cfg.soilAsset), lat, lon, radiusKm * 1000, 9000));
      const v = cfg.soilBand ? r[cfg.soilBand] : Object.values(r).find(x => typeof x === 'number');
      soilMoisture = typeof v === 'number' ? v : null;
    }
    if (!cfg.floodAsset) errors.push('GEE_FLOOD_EXTENT_ASSET is not set');
    else {
      const r = await eeCompute(meanAround(loadImage(cfg.floodAsset), lat, lon, radiusKm * 1000, 30));
      const v = Object.values(r).find(x => typeof x === 'number');
      floodExtentPct = typeof v === 'number' ? Math.round(v * 1000) / 10 : null;
    }
  } catch (e) { errors.push((e as Error).message); }
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
