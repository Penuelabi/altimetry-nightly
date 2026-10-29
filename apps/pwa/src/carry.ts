// Moving records from one phone to another without signal: a "carry bundle" holds the records waiting
// to upload and the register edits. It travels as a file (share sheet, Nearby Share, Bluetooth file
// send, WhatsApp) or as text pasted into a message; the receiving phone adds it to its own queue and
// uploads it when it next has signal.
import type { SyncRecord } from '@abuk/core';
import type { FarmOp } from '@abuk/core';
import { applyOps } from '@abuk/core';
import { getState, setState } from './store';

export interface Bundle { app: 'abuk'; v: 1; at: string; from: { id: string; name: string }; records: SyncRecord[]; ops: FarmOp[] }
const PREFIX = 'ABUK1:';

export function makeBundle(): Bundle {
  const s = getState();
  return { app: 'abuk', v: 1, at: new Date().toISOString(), from: { id: s.session?.user.id ?? 'unknown', name: s.session?.user.name ?? '' }, records: s.outbox, ops: s.farmOps };
}

const toB64 = (u: Uint8Array) => { let b = ''; for (const x of u) b += String.fromCharCode(x); return btoa(b); };
const fromB64 = (t: string) => Uint8Array.from(atob(t), c => c.charCodeAt(0));
async function pipe(data: Uint8Array, stream: CompressionStream | DecompressionStream): Promise<Uint8Array> {
  const out = new Response(new Blob([data as BlobPart]).stream().pipeThrough(stream));
  return new Uint8Array(await out.arrayBuffer());
}

// Text form for pasting into a message: gzip + base64 when the phone can, else plain JSON.
export async function bundleText(b: Bundle): Promise<string> {
  const json = new TextEncoder().encode(JSON.stringify(b));
  if (typeof CompressionStream === 'undefined') return JSON.stringify(b);
  return PREFIX + toB64(await pipe(json, new CompressionStream('gzip')));
}

export async function parseBundle(text: string): Promise<Bundle> {
  const t = text.trim();
  let json = t;
  if (t.startsWith(PREFIX)) {
    if (typeof DecompressionStream === 'undefined') throw new Error('This phone cannot open the compressed text. Ask for the file instead.');
    json = new TextDecoder().decode(await pipe(fromB64(t.slice(PREFIX.length).replace(/\s+/g, '')), new DecompressionStream('gzip')));
  }
  let b: Bundle;
  try { b = JSON.parse(json); } catch { throw new Error('That is not an Abuk records bundle.'); }
  if (b?.app !== 'abuk' || b.v !== 1 || !Array.isArray(b.records) || !Array.isArray(b.ops)) throw new Error('That is not an Abuk records bundle.');
  return b;
}

// Adds a bundle to this phone: new records join the upload queue (marked with who wrote them and who carried them),
// register edits are applied here and queued too. A record seen before (same id) is skipped, so the same file twice is harmless.
export function absorb(b: Bundle): { records: number; ops: number; skipped: number } {
  const s = getState();
  const seen = new Set([...s.outbox.map(r => r.id), ...s.carried]);
  const fresh = b.records.filter(r => r && typeof r.id === 'string' && typeof r.kind === 'string' && !seen.has(r.id));
  const carriedBy = s.session?.user.id ?? 'unknown';
  // The server stamps the uploader on every row, so the original author travels inside the record.
  const rec = fresh.map(r => ({ ...r, data: { ...r.data, carriedFrom: r.by, carriedBy } }));
  const ops = b.ops.filter(o => o && typeof o === 'object');
  setState(st => ({
    outbox: [...st.outbox, ...rec],
    farm: ops.length ? applyOps(st.farm, ops) : st.farm,
    farmOps: [...st.farmOps, ...ops],
    carried: [...st.carried, ...fresh.map(r => r.id)].slice(-3000),
    p2pLog: [{ at: new Date().toISOString(), who: b.from.name || b.from.id, n: fresh.length, dir: 'in' as const }, ...st.p2pLog].slice(0, 30)
  }));
  return { records: fresh.length, ops: ops.length, skipped: b.records.length - fresh.length };
}

export function logSent(n: number, how: string) {
  setState(st => ({ p2pLog: [{ at: new Date().toISOString(), who: how, n, dir: 'out' as const }, ...st.p2pLog].slice(0, 30) }));
}

export const bundleName = () => `abuk-records-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.json`;

// Hands the file to the phone's share sheet where the browser allows it; false means the caller should fall back.
export async function shareBundle(b: Bundle): Promise<'shared' | 'cancelled' | 'unsupported'> {
  const file = new File([JSON.stringify(b)], bundleName(), { type: 'application/json' });
  const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
  if (!nav.share || !nav.canShare?.({ files: [file] })) return 'unsupported';
  try { await nav.share({ files: [file], title: 'Abuk records' }); return 'shared'; }
  catch (e) { return (e as Error).name === 'AbortError' ? 'cancelled' : 'unsupported'; }
}

export function downloadBundle(b: Bundle) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(b)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url; a.download = bundleName(); document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
