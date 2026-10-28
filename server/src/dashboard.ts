import type { GaugeReading, PublicUser, Register, SyncKind } from '@abuk/core';
import { seedRegister } from '@abuk/core';
import { sheetsRead } from './adapters/google';
import { commitsFor, readJson } from './adapters/github';
import { loadUsers, toPublic } from './auth';

export interface DashRecord { id: string; kind: SyncKind; at: string; by: string; data: Record<string, unknown> }
export const KINDS: SyncKind[] = ['monitor', 'harvest', 'plot', 'task', 'pest', 'payout', 'store', 'offer', 'voice'];

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
