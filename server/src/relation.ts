// Which stations are upstream of, in, or downstream of a payam or county: station_relation.csv in the project Drive folder,
// written weekly by the exposure workflow from the HydroBASINS river network. Columns: place (payam|county), pcode, county,
// station_uid, relation (upstream|local|downstream), distance_km.
import type { StreamRelation } from '@abuk/core';
import { cfg } from './config';
import { driveDownload, driveFind } from './adapters/google';
import { fieldsOf } from './stations';

export const RELATION_FILE = 'station_relation.csv';
export interface Link { place: 'payam' | 'county'; pcode: string; county: string; uid: string; relation: StreamRelation }

const key = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
const RELS = new Set(['upstream', 'local', 'downstream']);

export function parseRelations(csv: string): Link[] {
  const lines = csv.replace(/^﻿/, '').split(/\r?\n/).filter(l => l.trim());
  if (lines.length < 2) return [];
  const head = fieldsOf(lines[0], 20).map(h => h.trim().toLowerCase());
  const [iPlace, iCode, iCounty, iUid, iRel] = ['place', 'pcode', 'county', 'station_uid', 'relation'].map(n => head.indexOf(n));
  if ([iPlace, iUid, iRel].some(i => i < 0)) return [];
  return lines.slice(1).flatMap(line => {
    const f = fieldsOf(line, 20).map(x => x.trim());
    const relation = (f[iRel] ?? '').toLowerCase(), place = (f[iPlace] ?? '').toLowerCase();
    if (!RELS.has(relation) || (place !== 'payam' && place !== 'county') || !f[iUid]) return [];
    return [{ place, pcode: iCode >= 0 ? (f[iCode] ?? '').toUpperCase() : '', county: iCounty >= 0 ? f[iCounty] ?? '' : '', uid: f[iUid], relation: relation as StreamRelation }];
  });
}

// station uid -> relation for one place: a payam by its code, or a whole county by its 6-character code (else by name).
export function relationFor(links: Link[], q: { pcode?: string; ccode?: string; county?: string }): Map<string, StreamRelation> {
  const code = (q.pcode ?? '').toUpperCase(), ccode = (q.ccode ?? '').toUpperCase();
  const mine = code ? links.filter(l => l.place === 'payam' && l.pcode === code)
    : ccode ? links.filter(l => l.place === 'county' && l.pcode === ccode)
      : q.county ? links.filter(l => l.place === 'county' && key(l.county) === key(q.county!)) : [];
  return new Map(mine.map(l => [l.uid, l.relation]));
}

const FRESH_MS = 6 * 3600_000;
let cache: { at: number; mod: string; links: Link[] } | null = null;
let inflight: Promise<Link[]> | null = null;

// Never throws: without the file the stations simply carry no upstream / downstream label.
export function relationTable(): Promise<Link[]> {
  if (cache && Date.now() - cache.at < FRESH_MS) return Promise.resolve(cache.links);
  inflight ??= (async () => {
    try {
      const f = await driveFind(cfg.driveFolder, RELATION_FILE);
      if (!f) { cache = { at: Date.now(), mod: '', links: [] }; return []; }
      if (cache && cache.mod === f.modifiedTime) { cache.at = Date.now(); return cache.links; }
      cache = { at: Date.now(), mod: f.modifiedTime, links: parseRelations((await driveDownload(f)).toString('utf8')) };
      return cache.links;
    } catch { return cache?.links ?? []; } finally { inflight = null; }
  })();
  return inflight;
}
