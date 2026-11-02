// Exposure per payam: payam_exposure.csv in the project Drive folder, one row per payam. Columns are found by name, so
// the order does not matter. Needed: ADM3_PCODE (or the payam name). Per kind (population, buildings, schools, health
// facilities) a total column and an "at risk" column, e.g. population, population_at_risk, schools, schools_at_risk.
// Optional: ADM2_EN (county, to tell two payams of one name apart), hazard (what "at risk" means), as_of.
import type { Count, Exposure } from '@abuk/core';
import { cfg } from './config';
import { driveDownload, driveFind } from './adapters/google';
import { fieldsOf } from './stations';

export const EXPOSURE_FILE = 'payam_exposure.csv';

type Kind = 'population' | 'buildings' | 'schools' | 'health';
const KINDS: [Kind, RegExp][] = [['population', /pop/], ['buildings', /build/], ['schools', /school|educat/], ['health', /health|clinic|hospital/]];
const RISK = /risk|expos|flood|affect|threat/;
const NOT_COUNT = /pct|percent|share|ratio|rate|%/;

const num = (s: string | undefined): number | null => {
  const t = (s ?? '').replace(/[,\s]/g, '');
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : null;
};
const key = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');

export function parseExposure(csv: string): Exposure[] {
  const lines = csv.replace(/^﻿/, '').split(/\r?\n/).filter(l => l.trim());
  if (lines.length < 2) return [];
  const head = fieldsOf(lines[0], 200).map(h => h.trim().toLowerCase());
  const at = (re: RegExp) => head.findIndex(h => re.test(h));
  const iCode = at(/^(adm3_?)?pcode$/), iPayam = at(/^(adm3_en|payam|payam_name|name)$/), iCounty = at(/^(adm2_en|county)$/);
  const iHazard = at(/^hazard$/), iAsOf = at(/^(as_?of|year|date)$/);
  if (iCode < 0 && iPayam < 0) return [];
  // The first matching column of each kind is its total, the first matching "at risk" column its risk.
  const col = {} as Record<Kind, { total: number; risk: number }>;
  for (const [k] of KINDS) col[k] = { total: -1, risk: -1 };
  head.forEach((h, i) => {
    if (NOT_COUNT.test(h)) return;
    const kind = KINDS.find(([, re]) => re.test(h))?.[0];
    if (!kind) return;
    const slot = RISK.test(h) ? 'risk' : 'total';
    if (col[kind][slot] < 0) col[kind][slot] = i;
  });
  if (KINDS.every(([k]) => col[k].total < 0 && col[k].risk < 0)) return [];
  return lines.slice(1).map(line => {
    const f = fieldsOf(line, 200).map(x => x.trim());
    const count = (k: Kind): Count => ({ total: col[k].total < 0 ? null : num(f[col[k].total]), risk: col[k].risk < 0 ? null : num(f[col[k].risk]) });
    return {
      pcode: iCode >= 0 ? (f[iCode] ?? '').toUpperCase() : '',
      payam: iPayam >= 0 ? f[iPayam] ?? '' : '',
      county: iCounty >= 0 ? f[iCounty] ?? '' : '',
      hazard: iHazard >= 0 ? f[iHazard] ?? '' : '',
      asOf: iAsOf >= 0 ? f[iAsOf] ?? '' : '',
      population: count('population'), buildings: count('buildings'), schools: count('schools'), health: count('health'),
    };
  }).filter(r => r.pcode || r.payam);
}

// The row for one payam: by code, else by payam name (and county when the name occurs more than once).
export function findExposure(rows: Exposure[], q: { pcode?: string; payam?: string; county?: string }): Exposure | null {
  const code = (q.pcode ?? '').toUpperCase();
  if (code) {
    const hit = rows.find(r => r.pcode === code);
    if (hit) return hit;
  }
  if (!q.payam) return null;
  let named = rows.filter(r => key(r.payam) === key(q.payam!));
  if (named.length > 1 && q.county) named = named.filter(r => !r.county || key(r.county) === key(q.county!));
  return named.length === 1 ? named[0] : null;
}

const FRESH_MS = 30 * 60_000, MISSING_MS = 5 * 60_000;
let cache: { at: number; mod: string; found: boolean; rows: Exposure[] } | null = null;
let inflight: Promise<{ rows: Exposure[]; found: boolean; stale: boolean }> | null = null;

// The parsed file; looked up again at most every 30 minutes (5 while it is missing), downloaded only when it changed.
export function exposureTable(): Promise<{ rows: Exposure[]; found: boolean; stale: boolean }> {
  if (cache && Date.now() - cache.at < (cache.found ? FRESH_MS : MISSING_MS)) return Promise.resolve({ rows: cache.rows, found: cache.found, stale: false });
  inflight ??= (async () => {
    try {
      const f = await driveFind(cfg.driveFolder, EXPOSURE_FILE);
      if (!f) { cache = { at: Date.now(), mod: '', found: false, rows: [] }; return { rows: [], found: false, stale: false }; }
      if (cache?.found && cache.mod === f.modifiedTime) { cache.at = Date.now(); return { rows: cache.rows, found: true, stale: false }; }
      const rows = parseExposure((await driveDownload(f)).toString('utf8'));
      cache = { at: Date.now(), mod: f.modifiedTime, found: true, rows };
      return { rows, found: true, stale: false };
    } catch (e) {
      if (cache?.found) return { rows: cache.rows, found: true, stale: true };
      throw e;
    } finally { inflight = null; }
  })();
  return inflight;
}
