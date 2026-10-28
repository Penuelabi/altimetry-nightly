import { SignJWT, importPKCS8 } from 'jose';
import { cfg, need } from '../config';

const SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/earthengine', 'https://www.googleapis.com/auth/devstorage.read_write'];
let cached: { token: string; exp: number } | null = null;

export async function googleToken(fetcher = fetch): Promise<string> {
  need('google');
  if (cached && cached.exp > Date.now() + 60_000) return cached.token;
  const sa = JSON.parse(cfg.serviceAccount) as { client_email: string; private_key: string; token_uri?: string };
  const aud = sa.token_uri || 'https://oauth2.googleapis.com/token';
  const key = await importPKCS8(sa.private_key, 'RS256');
  const assertion = await new SignJWT({ scope: SCOPES.join(' ') })
    .setProtectedHeader({ alg: 'RS256', typ: 'JWT' })
    .setIssuer(sa.client_email).setAudience(aud).setIssuedAt().setExpirationTime('1h').sign(key);
  const res = await fetcher(aud, { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion }) });
  if (!res.ok) throw new Error(`Google token exchange failed: ${res.status} ${await res.text()}`);
  const j = await res.json() as { access_token: string; expires_in: number };
  cached = { token: j.access_token, exp: Date.now() + j.expires_in * 1000 };
  return j.access_token;
}

async function gfetch(url: string, init: RequestInit = {}) {
  const res = await fetch(url, { ...init, headers: { ...(init.headers || {}), authorization: `Bearer ${await googleToken()}` } });
  if (!res.ok) throw new Error(`${init.method || 'GET'} ${url.split('?')[0]} → ${res.status} ${(await res.text()).slice(0, 300)}`);
  return res;
}

export interface DriveFile { id: string; name: string; mimeType: string; modifiedTime: string; size?: string }

export async function driveFind(parent: string, name: string): Promise<DriveFile | null> {
  const q = `'${parent}' in parents and name = '${name.replace(/'/g, "\\'")}' and trashed = false`;
  const res = await gfetch(`https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(q)}&fields=files(id,name,mimeType,modifiedTime,size)&supportsAllDrives=true&includeItemsFromAllDrives=true`);
  return ((await res.json()) as { files: DriveFile[] }).files[0] ?? null;
}

export async function driveList(parent: string): Promise<DriveFile[]> {
  const q = `'${parent}' in parents and trashed = false`;
  const res = await gfetch(`https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(q)}&pageSize=200&fields=files(id,name,mimeType,modifiedTime,size)&supportsAllDrives=true&includeItemsFromAllDrives=true`);
  return ((await res.json()) as { files: DriveFile[] }).files;
}

// Downloads are cached by file id + modifiedTime: the nightly workflow updates files once a day.
const blobCache = new Map<string, { mod: string; buf: Buffer }>();
export async function driveDownload(f: DriveFile): Promise<Buffer> {
  const hit = blobCache.get(f.id);
  if (hit && hit.mod === f.modifiedTime) return hit.buf;
  const res = await gfetch(`https://www.googleapis.com/drive/v3/files/${f.id}?alt=media&supportsAllDrives=true`);
  const buf = Buffer.from(await res.arrayBuffer());
  blobCache.set(f.id, { mod: f.modifiedTime, buf });
  return buf;
}

const knownTabs = new Set<string>();
async function ensureTab(tab: string) {
  if (knownTabs.has(tab)) return;
  const meta = await (await gfetch(`https://sheets.googleapis.com/v4/spreadsheets/${cfg.sheetId}?fields=sheets.properties.title`)).json() as { sheets: { properties: { title: string } }[] };
  meta.sheets.forEach(x => knownTabs.add(x.properties.title));
  if (knownTabs.has(tab)) return;
  // First record of this kind: add the tab with a header row.
  await gfetch(`https://sheets.googleapis.com/v4/spreadsheets/${cfg.sheetId}:batchUpdate`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ requests: [{ addSheet: { properties: { title: tab } } }] })
  });
  await gfetch(`https://sheets.googleapis.com/v4/spreadsheets/${cfg.sheetId}/values/${encodeURIComponent(`${tab}!A1`)}?valueInputOption=RAW`, {
    method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ values: [['record_id', 'recorded_at', 'worker_id', 'data']] })
  });
  knownTabs.add(tab);
}

export async function sheetsAppend(tab: string, rows: (string | number)[][]) {
  need('sheets');
  await ensureTab(tab);
  const range = encodeURIComponent(`${tab}!A1`);
  await gfetch(`https://sheets.googleapis.com/v4/spreadsheets/${cfg.sheetId}/values/${range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ values: rows })
  });
}

// Reads a whole record tab back (rows after the header); missing tabs are simply empty.
export async function sheetsRead(tab: string): Promise<string[][]> {
  need('sheets');
  const range = encodeURIComponent(`${tab}!A2:D`);
  const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${cfg.sheetId}/values/${range}`, { headers: { authorization: `Bearer ${await googleToken()}` } });
  if (res.status === 400) return [];
  if (!res.ok) throw new Error(`Sheets read ${tab} → ${res.status}`);
  return ((await res.json()) as { values?: string[][] }).values ?? [];
}

// ---- Earth Engine REST: expressions are built as plain JSON graphs ----
type Node = { constantValue: unknown } | { functionInvocationValue: { functionName: string; arguments: Record<string, Node> } };
export const c = (v: unknown): Node => ({ constantValue: v });
export const fn = (functionName: string, args: Record<string, Node>): Node => ({ functionInvocationValue: { functionName, arguments: args } });

// "ic:ID" → newest image of an ImageCollection; plain ID → an Image asset.
export function loadImage(asset: string): Node {
  if (asset.startsWith('ic:')) {
    const coll = fn('ImageCollection.load', { id: c(asset.slice(3)) });
    return fn('Collection.first', { collection: fn('Collection.limit', { collection: coll, limit: c(1), key: c('system:time_start'), ascending: c(false) }) });
  }
  return fn('Image.load', { id: c(asset) });
}

export function meanAround(image: Node, lat: number, lon: number, radiusM: number, scale: number): Node {
  const geometry = fn('Geometry.buffer', { geometry: fn('GeometryConstructors.Point', { coordinates: c([lon, lat]) }), distance: c(radiusM) });
  return fn('Image.reduceRegion', { image, reducer: fn('Reducer.mean', {}), geometry, scale: c(scale), maxPixels: c(1e9), bestEffort: c(true) });
}

export async function eeCompute(expr: Node): Promise<Record<string, number | null>> {
  need('gee');
  const res = await gfetch(`https://earthengine.googleapis.com/v1/projects/${cfg.geeProject}/value:compute`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ expression: { result: '0', values: { '0': expr } } })
  });
  return ((await res.json()) as { result: Record<string, number | null> }).result;
}

export function terrainExpr(lat: number, lon: number): Node {
  const dem = fn('Image.load', { id: c('USGS/SRTMGL1_003') });
  const both = fn('Image.addBands', { dstImg: dem, srcImg: fn('Terrain.slope', { input: dem }) });
  return meanAround(both, lat, lon, 45, 30);
}

// Photos in a private Cloud Storage bucket. Writing with ifGenerationMatch=0 makes a re-sent upload a no-op.
export async function photoPut(bucket: string, name: string, body: Uint8Array, type: string) {
  const res = await fetch(`https://storage.googleapis.com/upload/storage/v1/b/${bucket}/o?uploadType=media&ifGenerationMatch=0&name=${encodeURIComponent(name)}`, {
    method: 'POST', headers: { authorization: `Bearer ${await googleToken()}`, 'content-type': type }, body
  });
  if (res.status === 412) return; // already stored
  if (!res.ok) throw new Error(`photo upload → ${res.status} ${(await res.text()).slice(0, 200)}`);
}

export async function photoGet(bucket: string, name: string): Promise<Response | null> {
  const res = await fetch(`https://storage.googleapis.com/storage/v1/b/${bucket}/o/${encodeURIComponent(name)}?alt=media`, { headers: { authorization: `Bearer ${await googleToken()}` } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`photo read → ${res.status}`);
  return res;
}
