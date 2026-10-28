import { describe, expect, it, beforeEach } from 'vitest';
import { generateKeyPairSync } from 'node:crypto';
import { parseCsv, csvObjects } from '../src/csv';
import { checkKey, makeUser, nextId, toPublic, issueSession, readSession } from '../src/auth';
import { stationsFrom, bulletinFrom, ifsFrom, inPolygon } from '../src/sources';
import { googleToken, loadImage, meanAround, terrainExpr } from '../src/adapters/google';
import { parseInbound } from '../src/adapters/sms';
import { app } from '../src/app';

describe('csv', () => {
  it('handles quoted commas', () => {
    expect(parseCsv('a,b\n"Baro, River",2\r\n')).toEqual([['a', 'b'], ['Baro, River', '2']]);
    expect(csvObjects('x,y\n1,2')).toEqual([{ x: '1', y: '2' }]);
  });
});

describe('auth', () => {
  it('hashes keys and checks status/expiry', () => {
    const { user, key } = makeUser([], 'Achol Deng', 'Group lead', 90);
    expect(key).toMatch(/^abk_[A-Za-z0-9]{24}$/);
    expect(user.hash).not.toContain(key);
    expect(user.id).toBe('EW‑001');
    const file = { users: [user] };
    expect(checkKey(file, 'ew-001', key).ok).toBe(true);
    expect(checkKey(file, 'EW‑001', key + 'x').ok).toBe(false);
    expect(checkKey({ users: [{ ...user, on: false }] }, 'EW‑001', key)).toMatchObject({ ok: false, error: expect.stringMatching(/revoked/) });
    expect(checkKey(file, 'EW‑001', key, new Date(Date.now() + 100 * 864e5))).toMatchObject({ ok: false, error: expect.stringMatching(/expired/) });
    expect(nextId([user], 'Admin')).toBe('AD‑001');
    expect(toPublic(user).meta).toMatch(/not signed in/);
  });
  it('round-trips sessions', async () => {
    process.env.SESSION_SECRET = 'x'.repeat(40);
    const { user } = makeUser([], 'Garang Mabior', 'Admin', 30);
    const s = await issueSession(user);
    expect(await readSession(s.token)).toEqual({ id: 'AD‑001', role: 'Admin', name: 'Garang Mabior' });
  });
});

describe('sources', () => {
  const csv = 'station_uid,type,name,latitude,longitude,last_date,last_level_m,vs_2yr_m,flood_status,level_class,rate_m_per_day\n' +
    'hydroweb:7877,river,White Nile km 4500,7.3975,30.6476,2026-10-20,407.1,-0.8,Below 2-yr level,Near normal,-0.01\n' +
    'dahiti:11635,river,"Baro, River",8.1811,34.2557,2026-10-19,422.99,-1.11,Below 2-yr level,Near normal,-0.04\n';
  it('falls back to the nearest stations outside the radius', () => {
    const r = stationsFrom(csv, 7.731, 31.402, 20);
    expect(r.fallback).toBe(true);
    expect(r.rows[0]).toMatchObject({ uid: 'hydroweb:7877', km: 91 });
  });
  it('finds the county row in the bulletin', () => {
    const b = bulletinFrom([['County', 'Alert level', 'Headline'], ['Bor South', 'yellow', 'x'], ['Duk', 'orange', 'Dry spell possible (46%)']], 'Duk');
    expect(b).toMatchObject({ alert: 'orange', headline: 'Dry spell possible (46%)' });
  });
  it('takes the latest IFS row per station', () => {
    const r = ifsFrom('station_uid,date,t2m,ro\nA,2026-10-27,33.1,0.1\nA,2026-10-28,34.0,0\nB,2026-10-28,1,1', ['A']);
    expect(r).toEqual([{ station: 'A', date: '2026-10-28', values: { t2m: 34, ro: 0 } }]);
  });
  it('tests points in polygons', () => {
    const sq = [[[31, 7], [32, 7], [32, 8], [31, 8], [31, 7]]];
    expect(inPolygon(31.4, 7.7, sq)).toBe(true);
    expect(inPolygon(30, 7.7, sq)).toBe(false);
  });
});

describe('earth engine expressions', () => {
  it('builds a mean over a buffered point', () => {
    const e = meanAround(loadImage('ic:users/x/flood'), 7.7, 31.4, 20000, 30) as any;
    const f = e.functionInvocationValue;
    expect(f.functionName).toBe('Image.reduceRegion');
    expect(f.arguments.image.functionInvocationValue.functionName).toBe('Collection.first');
    expect(f.arguments.geometry.functionInvocationValue.arguments.distance.constantValue).toBe(20000);
    expect((terrainExpr(7, 31) as any).functionInvocationValue.arguments.image.functionInvocationValue.functionName).toBe('Image.addBands');
  });
  it('signs a service-account JWT for the token exchange', async () => {
    const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
    process.env.GOOGLE_SERVICE_ACCOUNT_JSON = JSON.stringify({ client_email: 'sa@p.iam.gserviceaccount.com', private_key: privateKey.export({ type: 'pkcs8', format: 'pem' }) });
    let body = '';
    const token = await googleToken(async (_u, init) => { body = String(init!.body); return new Response(JSON.stringify({ access_token: 't0k', expires_in: 3600 })); });
    expect(token).toBe('t0k');
    expect(body).toMatch(/grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=ey/);
    delete process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  });
});

describe('http', () => {
  beforeEach(() => { delete process.env.GITHUB_TOKEN; delete process.env.SMS_WEBHOOK_SECRET; process.env.SESSION_SECRET = 'x'.repeat(40); });
  it('reports health and rejects missing auth', async () => {
    const h = await (await app.request("/api/health")).json() as any;
    expect(h.github.configured).toBe(false);
    expect((await app.request('/api/admin/users')).status).toBe(401);
  });
  it('returns 503 not_configured when GitHub keys are missing', async () => {
    const r = await app.request('/api/auth/signin', { method: 'POST', body: JSON.stringify({ id: 'EW-014', key: 'abk_abcdefgh' }), headers: { 'content-type': 'application/json' } });
    expect(r.status).toBe(503);
    expect(((await r.json()) as any).missing).toContain('GITHUB_TOKEN');
  });
  it('validates sign-in input before calling GitHub', async () => {
    const r = await app.request('/api/auth/signin', { method: 'POST', body: JSON.stringify({ id: 'nope', key: 'k' }), headers: { 'content-type': 'application/json' } });
    expect(r.status).toBe(400);
  });
  it('refuses the SMS webhook without the secret', async () => {
    expect((await app.request('/api/sms/inbound', { method: 'POST' })).status).toBe(401);
  });
  it('parses provider webhooks', () => {
    expect(parseInbound({ from: '+211', text: 'G 4.1' })).toEqual({ from: '+211', text: 'G 4.1' });
    expect(parseInbound({ From: '+211', Body: 'G 4.1' })).toEqual({ from: '+211', text: 'G 4.1' });
  });
});
