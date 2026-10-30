// A readable copy of the farm register in the project's Google Sheet (in the Drive folder), one tab per list.
// The register itself lives in the private GitHub repo (versioned); this copy is for people who work in Drive,
// and is rewritten after every change that reaches the server.
import type { GaugeReading, Register } from '@abuk/core';
import { sheetsReplace } from './adapters/google';
import { missing } from './config';

export const MIRRORED = ['crops', 'groups', 'plots', 'people', 'batches', 'runs', 'stores', 'items', 'moves', 'orders', 'herds', 'livestockEvents', 'forestLogs', 'fishLogs', 'vslaGroups', 'vslaTxs', 'degradations', 'containers', 'containerLogs', 'tollgates', 'tasks', 'mounds', 'listings', 'offers', 'words', 'subscribers', 'waGroups'] as const;

export interface MirrorStatus { at: string | null; ok: boolean; error: string; lists: number; rows: number; running: boolean }
export const mirrorStatus: MirrorStatus = { at: null, ok: true, error: '', lists: 0, rows: 0, running: false };

const CELL = 45_000; // a Sheets cell holds up to 50,000 characters
const place = (v: unknown) => {
  if (!v || typeof v !== 'object' || Array.isArray(v) || !('payam' in v)) return null;
  const a = v as { village?: string; payam?: string; county?: string; state?: string };
  return [a.village, a.payam, a.county, a.state].filter(Boolean).join(', ');
};
const cell = (v: unknown): string | number => {
  if (v == null) return '';
  if (typeof v === 'number') return v;
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'string') return v.slice(0, CELL);
  return (place(v) ?? JSON.stringify(v)).slice(0, CELL);
};

// Columns are the keys the items use (id first, then a name or code), so the tab reads like a table.
export function tableOf(items: Record<string, unknown>[]): (string | number)[][] {
  const keys: string[] = [];
  for (const it of items) for (const k of Object.keys(it)) if (!keys.includes(k)) keys.push(k);
  const first = ['id', 'code', 'name', 'title'].filter(k => keys.includes(k));
  const cols = [...first, ...keys.filter(k => !first.includes(k))];
  return [cols, ...items.map(it => cols.map(k => cell(it[k])))];
}

// Only lists that changed since the last copy are rewritten (Sheets allows about 60 writes a minute); `all` rewrites everything.
const sent = new Map<string, string>();
let again: Register | null = null;
export async function mirrorRegister(reg: Register, all = false) {
  if (missing('sheets').length) { mirrorStatus.ok = false; mirrorStatus.error = 'Google Sheet not configured on the server (SHEET_ID).'; return; }
  if (mirrorStatus.running) { again = reg; return; } // a copy is being written: write the newest once it finishes
  mirrorStatus.running = true;
  try {
    let lists = 0, rows = 0;
    for (const name of MIRRORED) {
      const items = ((reg as unknown as Record<string, unknown>)[name] ?? []) as Record<string, unknown>[];
      if (!items.length && name !== 'plots' && name !== 'groups') continue;
      const json = JSON.stringify(items);
      lists++; rows += items.length;
      if (!all && sent.get(name) === json) continue;
      await sheetsReplace(`register_${name}`, tableOf(items));
      sent.set(name, json);
    }
    Object.assign(mirrorStatus, { at: new Date().toISOString(), ok: true, error: '', lists, rows });
  } catch (e) {
    Object.assign(mirrorStatus, { ok: false, error: (e as Error).message.slice(0, 300) });
  } finally {
    mirrorStatus.running = false;
    if (again) { const next = again; again = null; void mirrorRegister(next); }
  }
}

// The gauge log is copied the same way: the whole list (newest first) is rewritten when a reading arrives.
export async function mirrorGauge(list: GaugeReading[]) {
  if (missing('sheets').length) return;
  try { await sheetsReplace('gauge_readings', tableOf(list as unknown as Record<string, unknown>[])); }
  catch (e) { console.error('gauge mirror failed', (e as Error).message); }
}
