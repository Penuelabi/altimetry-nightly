import type { GaugeReading, PublicUser, Register, SyncKind } from '@abuk/core';
import { seedRegister } from '@abuk/core';
import { sheetsRead } from './adapters/google';
import { commitsFor, readJson } from './adapters/github';
import { loadUsers, toPublic } from './auth';

export interface DashRecord { id: string; kind: SyncKind; at: string; by: string; data: Record<string, unknown> }
export const KINDS: SyncKind[] = ['monitor', 'harvest', 'plot', 'task', 'pest', 'payout', 'store', 'offer', 'voice', 'alert'];

// Everything the admin dashboard shows, in one call. Sheet reads are cached for a minute
// so several admins refreshing do not hammer the Sheets quota.
let cache: { at: number; v: Overview } | null = null;
export interface Overview {
  generated: string; records: DashRecord[]; errors: string[];
  users: (PublicUser & { lastSeen: string | null })[];
  farm: Register; farmChanges: { sha: string; message: string; date: string }[];
  gauge: GaugeReading[];
}

export async function overview(fresh = false): Promise<Overview> {
  if (!fresh && cache && Date.now() - cache.at < 60_000) return cache.v;
  const errors: string[] = [];
  const guard = async <T>(label: string, f: () => Promise<T>, fb: T): Promise<T> => { try { return await f(); } catch (e) { errors.push(`${label}: ${(e as Error).message}`); return fb; } };
  const [perKind, users, farm, farmChanges, gauge] = await Promise.all([
    Promise.all(KINDS.map(k => guard(`sheet tab ${k}`, async () => (await sheetsRead(k)).map(r => parseRow(k, r)).filter((x): x is DashRecord => !!x), [] as DashRecord[]))),
    guard('users', async () => (await loadUsers(true)).users.map(u => ({ ...toPublic(u), lastSeen: u.lastSeen ?? null })), []),
    guard('farm register', async () => (await readJson<Register>('config/farm.json', seedRegister())).data, seedRegister()),
    guard('farm history', () => commitsFor('config/farm.json'), []),
    guard('gauge', async () => (await readJson<GaugeReading[]>('data/gauge.json', [])).data.slice(0, 60), [])
  ]);
  const records = perKind.flat().sort((a, b) => b.at.localeCompare(a.at));
  const v: Overview = { generated: new Date().toISOString(), records, errors, users, farm, farmChanges, gauge };
  cache = { at: Date.now(), v };
  return v;
}

export function parseRow(kind: SyncKind, r: string[]): DashRecord | null {
  const [id, at, by, json] = r;
  if (!id || !at) return null;
  let data: Record<string, unknown> = {};
  try { data = JSON.parse(json || '{}'); } catch { data = { raw: json }; }
  return { id, kind, at, by: by || '', data };
}

// Recent crop checks from every phone, cut down to what the flood model and alerts need
// (plot, time, place, water on and around the plot). Any signed-in worker may read these.
export interface CheckLite { id: string; at: string; by: string; plot: string; crop: string; lat: number | null; lon: number | null; water: string; depthCm: number | null; around: string; aroundDepthCm: number | null; trend: string; field: string }
let checksCache: { at: number; v: CheckLite[] } | null = null;
const numOrNull = (x: unknown) => (x === '' || x == null || isNaN(Number(x)) ? null : Number(x));

export function checkFrom(r: DashRecord): CheckLite {
  const d = r.data as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const cond = (d.condition ?? {}) as Record<string, unknown>;
  return {
    id: r.id, at: String(d.stampedAt || r.at), by: r.by, plot: String(d.plot ?? '').split(' · ')[0], crop: String(d.crop ?? ''),
    lat: numOrNull(d.gps?.lat), lon: numOrNull(d.gps?.lon),
    water: String(cond.water ?? ''), depthCm: numOrNull(cond.floodDepthCm), around: String(cond.around ?? ''), aroundDepthCm: numOrNull(cond.aroundDepthCm),
    trend: String(cond.trend ?? ''), field: String(d.notes ?? '')
  };
}

export async function recentChecks(days = 21): Promise<CheckLite[]> {
  if (checksCache && Date.now() - checksCache.at < 5 * 60_000) return checksCache.v;
  const since = Date.now() - days * 864e5;
  const v = (await sheetsRead('monitor')).map(r => parseRow('monitor', r)).filter((x): x is DashRecord => !!x)
    .map(checkFrom).filter(c => c.plot && Date.parse(c.at) >= since).sort((a, b) => b.at.localeCompare(a.at)).slice(0, 2000);
  checksCache = { at: Date.now(), v };
  return v;
}
