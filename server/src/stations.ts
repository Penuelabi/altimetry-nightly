// Water-level history for the stations: merged_altimetry_stations.csv in the project Drive folder (about 40 MB, one row
// per station per observation, refreshed by the nightly workflow). Parsed once, only the newest rows of each station kept.
import type { Obs } from '@abuk/core';
import { cfg } from './config';
import { driveDownload, driveFind } from './adapters/google';

export interface Hist { uid: string; name: string; type: string; lat: number; lon: number; obs: Obs[] }

// The first `upTo` fields of one CSV line, honouring quotes ("Victoria, Lake").
export function fieldsOf(line: string, upTo: number): string[] {
  const out: string[] = [];
  let f = '', q = false;
  for (let i = 0; i < line.length && out.length < upTo; i++) {
    const ch = line[i];
    if (q) { if (ch === '"') { if (line[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += ch; }
    else if (ch === '"') q = true;
    else if (ch === ',') { out.push(f); f = ''; }
    else f += ch;
  }
  if (out.length < upTo) out.push(f);
  return out;
}

// Reads the station table line by line (the whole file is never turned into objects). keep = newest observations per station.
export function parseStationHistory(csv: string, keep = 60): Hist[] {
  const nl = csv.indexOf('\n');
  if (nl < 0) return [];
  const head = fieldsOf(csv.slice(0, nl).replace(/^﻿/, '').replace(/\r$/, ''), 60).map(h => h.trim().toLowerCase());
  const at = (re: RegExp) => head.findIndex(h => re.test(h));
  const iUid = at(/^station_uid$/), iId = at(/^station_id$/), iSrc = at(/^(merged )?source$/), iType = at(/^type$/), iName = at(/river_name|^name$/);
  const iLat = at(/^latitude$/), iLon = at(/^longitude$/), iDate = at(/^date$/), iVal = at(/^water surface elevation/);
  if ([iLat, iLon, iDate, iVal].some(i => i < 0) || (iUid < 0 && iId < 0)) return [];
  const upTo = Math.max(iUid, iId, iSrc, iType, iName, iLat, iLon, iDate, iVal) + 1;
  const by = new Map<string, Hist>();
  for (let s = nl + 1; s < csv.length;) {
    let e = csv.indexOf('\n', s);
    if (e < 0) e = csv.length;
    const line = csv.slice(s, e).replace(/\r$/, '');
    s = e + 1;
    if (!line) continue;
    const f = fieldsOf(line, upTo);
    const v = Number(f[iVal]), d = (f[iDate] ?? '').slice(0, 10);
    if (f[iVal] === '' || !Number.isFinite(v) || !/^\d{4}-\d{2}-\d{2}$/.test(d)) continue;
    const uid = iUid >= 0 && f[iUid] ? f[iUid] : `${f[iSrc] ?? ''}:${f[iId]}`;
    let h = by.get(uid);
    if (!h) {
      const lat = Number(f[iLat]), lon = Number(f[iLon]);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      h = { uid, name: (iName >= 0 ? f[iName] : '') || uid, type: iType >= 0 ? f[iType] : '', lat, lon, obs: [] };
      by.set(uid, h);
    }
    h.obs.push({ d, v });
  }
  for (const h of by.values()) {
    h.obs.sort((a, b) => a.d.localeCompare(b.d));
    // One value per date (a repeat keeps the later row), then only the newest.
    h.obs = h.obs.filter((o, i, a) => i === a.length - 1 || a[i + 1].d !== o.d).slice(-keep);
  }
  return [...by.values()];
}

const FILE = 'merged_altimetry_stations.csv';
const FRESH_MS = 30 * 60_000;
let cache: { at: number; mod: string; list: Hist[] } | null = null;
let inflight: Promise<{ list: Hist[]; stale: boolean }> | null = null;

// The parsed history; looked up again at most every 30 minutes, downloaded only when the file changed.
export function stationHistory(): Promise<{ list: Hist[]; stale: boolean }> {
  if (cache && Date.now() - cache.at < FRESH_MS) return Promise.resolve({ list: cache.list, stale: false });
  inflight ??= (async () => {
    try {
      const f = await driveFind(cfg.driveFolder, FILE);
      if (!f) throw new Error(`${FILE} not found in the Drive folder`);
      if (cache && cache.mod === f.modifiedTime) { cache.at = Date.now(); return { list: cache.list, stale: false }; }
      const csv = (await driveDownload(f, false)).toString('utf8');
      cache = { at: Date.now(), mod: f.modifiedTime, list: parseStationHistory(csv) };
      return { list: cache.list, stale: false };
    } catch (e) {
      // Better an older graph than none.
      if (cache) return { list: cache.list, stale: true };
      throw e;
    } finally { inflight = null; }
  })();
  return inflight;
}
