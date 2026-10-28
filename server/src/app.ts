import { Hono, type Context } from 'hono';
import { cors } from 'hono/cors';
import type { GaugeReading, Role, SyncRecord } from '@abuk/core';
import { parseGauge, signinError } from '@abuk/core';
import { cfg, health, NotConfigured } from './config';
import { EXPIRY_DAYS, changeUsers, checkKey, issueSession, loadUsers, makeUser, readSession, toPublic, type Session } from './auth';
import { readJson, updateJson } from './adapters/github';
import { sheetsAppend } from './adapters/google';
import { parseInbound, sendSms } from './adapters/sms';
import { pull, terrain } from './sources';

type Env = { Variables: { me: Session } };
export const app = new Hono<Env>();

app.use('/api/*', cors({ origin: o => (cfg.allowedOrigins.includes('*') || cfg.allowedOrigins.includes(o) ? o : null), allowHeaders: ['authorization', 'content-type'] }));

app.onError((e, c) => {
  if (e instanceof NotConfigured) return c.json({ error: 'not_configured', missing: e.keys, message: e.message }, 503);
  console.error(e);
  return c.json({ error: 'upstream', message: e.message }, 502);
});

// Crude per-IP limiter for sign-in attempts.
const attempts = new Map<string, number[]>();
const limited = (ip: string) => {
  const now = Date.now(), hits = (attempts.get(ip) || []).filter(t => now - t < 60_000);
  hits.push(now); attempts.set(ip, hits);
  return hits.length > 10;
};

const auth = (roles?: Role[]) => async (c: Context<Env>, next: () => Promise<void>) => {
  const h = c.req.header('authorization') || '';
  try {
    const me = await readSession(h.replace(/^Bearer\s+/i, ''));
    if (roles && !roles.includes(me.role)) return c.json({ error: 'forbidden' }, 403);
    c.set('me', me);
  } catch (e) {
    if (e instanceof NotConfigured) throw e;
    return c.json({ error: 'unauthorized' }, 401);
  }
  await next();
};

app.get('/api/health', c => c.json(health()));

app.post('/api/auth/signin', async c => {
  if (limited(c.req.header('x-forwarded-for') || 'local')) return c.json({ error: 'too_many', message: 'Too many tries. Wait a minute.' }, 429);
  const { id = '', key = '' } = await c.req.json<{ id?: string; key?: string }>();
  const bad = signinError(id, key);
  if (bad) return c.json({ error: 'invalid', message: bad }, 400);
  const v = checkKey(await loadUsers(true), id, key);
  if (!v.ok) return c.json({ error: 'denied', message: v.error }, 401);
  const s = await issueSession(v.user);
  // lastSeen is best-effort; a failed commit must not block sign-in.
  changeUsers(`seen ${v.user.id}`, f => ({ users: f.users.map(u => u.id === v.user.id ? { ...u, lastSeen: new Date().toISOString() } : u) })).catch(() => {});
  return c.json({ ...s, user: toPublic(v.user) });
});

app.get('/api/me', auth(), c => c.json(c.get('me')));

// ---- admin: users & keys ----
app.get('/api/admin/users', auth(['Admin']), async c => c.json((await loadUsers(true)).users.map(toPublic)));

app.post('/api/admin/users', auth(['Admin']), async c => {
  const { name = '', role = 'Extension worker', exp = '90 days' } = await c.req.json<{ name?: string; role?: Role; exp?: string }>();
  if (name.trim().split(/\s+/).length < 2) return c.json({ error: 'invalid', message: 'Enter first and last name.' }, 400);
  if (!['Admin', 'Group lead', 'Extension worker'].includes(role)) return c.json({ error: 'invalid', message: 'Unknown role.' }, 400);
  let made: ReturnType<typeof makeUser> | null = null;
  const r = await changeUsers(`add user (hash only) by ${c.get('me').id}`, f => {
    made = makeUser(f.users, name.trim(), role, EXPIRY_DAYS[exp] ?? 90);
    return { users: [made.user, ...f.users] };
  });
  const m = made as unknown as ReturnType<typeof makeUser>;
  return c.json({ user: toPublic(m.user), key: m.key, commit: r.commit.slice(0, 7) });
});

app.post('/api/admin/users/:id/toggle', auth(['Admin']), async c => {
  const id = c.req.param('id'), me = c.get('me');
  if (id === me.id) return c.json({ error: 'invalid', message: 'You cannot revoke your own key.' }, 400);
  const r = await changeUsers(`toggle ${id} by ${me.id}`, f => ({ users: f.users.map(u => u.id === id ? { ...u, on: !u.on, note: u.on ? `revoked ${new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}` : undefined } : u) }));
  return c.json(r.data.users.map(toPublic));
});

// ---- data sources ----
const coords = (c: Context<Env>) => {
  const lat = Number(c.req.query('lat')), lon = Number(c.req.query('lon'));
  if (!isFinite(lat) || !isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon };
};

app.get('/api/sources/pull', auth(), async c => {
  const p = coords(c), radius = Math.min(200, Math.max(1, Number(c.req.query('radius')) || 20));
  if (!p) return c.json({ error: 'invalid', message: 'lat and lon are required' }, 400);
  return c.json(await pull(p.lat, p.lon, radius));
});

app.get('/api/terrain', auth(), async c => {
  const p = coords(c);
  if (!p) return c.json({ error: 'invalid', message: 'lat and lon are required' }, 400);
  return c.json(await terrain(p.lat, p.lon));
});

interface ExtraSource { kind: 'GitHub' | 'Drive'; url: string; by: string; at: string }
app.get('/api/sources/extra', auth(), async c => c.json((await readJson<ExtraSource[]>('config/sources.json', [])).data));
app.post('/api/sources/extra', auth(['Admin']), async c => {
  const { kind, url = '' } = await c.req.json<{ kind?: string; url?: string }>();
  const ok = kind === 'GitHub' ? /^(https:\/\/)?github\.com\/[\w.-]+\/[\w.-]+/.test(url) : kind === 'Drive' ? /drive\.google\.com\/drive\/folders\/[\w-]+/.test(url) : false;
  if (!ok) return c.json({ error: 'invalid', message: 'Paste a github.com repository link or a Drive folder link.' }, 400);
  const r = await updateJson<ExtraSource[]>('config/sources.json', [], `add source by ${c.get('me').id}`, l => [...l, { kind: kind as ExtraSource['kind'], url, by: c.get('me').id, at: new Date().toISOString() }]);
  return c.json(r.data);
});

// ---- offline records ----
app.post('/api/sync', auth(), async c => {
  const { records = [] } = await c.req.json<{ records?: SyncRecord[] }>();
  const byKind = new Map<string, (string | number)[][]>();
  for (const r of records.slice(0, 500)) {
    const rows = byKind.get(r.kind) || [];
    rows.push([r.id, r.at, c.get('me').id, JSON.stringify(r.data)]);
    byKind.set(r.kind, rows);
  }
  for (const [kind, rows] of byKind) await sheetsAppend(kind, rows);
  return c.json({ accepted: records.slice(0, 500).map(r => r.id) });
});

// ---- SMS: leads, alerts, gauge readings ----
interface Lead { id: string; name: string; group: string; rows: string; phone: string; lang: 'en' | 'ar' }
const mask = (p: string) => p.replace(/^(\+\d{3}\s?\d{2})\d(.*)(\d{3})$/, (_, a, _b, z) => `${a}• ••• ${z}`);

app.get('/api/leads', auth(), async c => c.json((await readJson<Lead[]>('config/leads.json', [])).data.map(l => ({ ...l, phone: mask(l.phone) }))));

app.post('/api/sms/alert', auth(['Admin', 'Group lead']), async c => {
  const { leadIds = [], text = '', textAr } = await c.req.json<{ leadIds?: string[]; text?: string; textAr?: string }>();
  if (!text.trim() || text.length > 160) return c.json({ error: 'invalid', message: 'Message must be 1–160 characters.' }, 400);
  const leads = (await readJson<Lead[]>('config/leads.json', [])).data.filter(l => leadIds.includes(l.id));
  if (!leads.length) return c.json({ error: 'invalid', message: 'No recipients. Add lead phone numbers in config/leads.json.' }, 400);
  const en = leads.filter(l => l.lang !== 'ar' || !textAr), ar = leads.filter(l => l.lang === 'ar' && textAr);
  const results = [...(en.length ? await sendSms(en.map(l => l.phone), text) : []), ...(ar.length ? await sendSms(ar.map(l => l.phone), textAr!) : [])];
  return c.json({ sent: results.filter(r => r.ok).length, results: results.map(r => ({ ...r, to: mask(r.to) })) });
});

const GAUGE_PATH = 'data/gauge.json';
async function recordGauge(from: string, text: string): Promise<GaugeReading> {
  let reading: GaugeReading | null = null;
  await updateJson<GaugeReading[]>(GAUGE_PATH, [], `gauge reading from ${from.slice(-3)}`, list => {
    const last = list.find(r => r.status === 'ok')?.v ?? null;
    const v = parseGauge(text, last);
    reading = { from, text, at: new Date().toISOString(), v: v.kind === 'bad' ? null : v.v, status: v.kind };
    return [reading, ...list].slice(0, 2000);
  });
  return reading!;
}
const replyFor = (r: GaugeReading) => r.status === 'ok' ? `Abuk: gauge ${r.v!.toFixed(2)} m received. Thank you.` : r.status === 'held' ? `Abuk: ${r.v} m is far from the last reading; the admin will check it.` : 'Abuk: not understood. Send G then the level, e.g. G 4.12';

// Public webhook for the SMS provider; protected by a shared secret in the URL.
app.post('/api/sms/inbound', async c => {
  if (!cfg.smsWebhookSecret || c.req.query('secret') !== cfg.smsWebhookSecret) return c.json({ error: 'unauthorized' }, 401);
  const isJson = (c.req.header('content-type') || '').includes('json');
  const { from, text } = parseInbound(isJson ? await c.req.json() : await c.req.parseBody() as Record<string, string>);
  if (!/^\s*g/i.test(text)) return c.json({ ignored: true });
  const r = await recordGauge(from, text);
  sendSms([from], replyFor(r)).catch(e => console.error('reply failed', e));
  return c.json(r);
});

// Lets an admin test the parser end-to-end without a phone.
app.post('/api/gauge/test', auth(['Admin', 'Group lead']), async c => {
  const { text = '' } = await c.req.json<{ text?: string }>();
  const r = await recordGauge(`${c.get('me').name} (test)`, text);
  return c.json({ reading: r, reply: replyFor(r) });
});

app.get('/api/gauge', auth(), async c => {
  const list = (await readJson<GaugeReading[]>(GAUGE_PATH, [])).data;
  return c.json(list.slice(0, 50).map(r => ({ ...r, from: /^\+?\d{6,}$/.test(r.from) ? mask(r.from) : r.from })));
});
