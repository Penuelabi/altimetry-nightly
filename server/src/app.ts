import { Hono, type Context } from 'hono';
import { cors } from 'hono/cors';
import { serveStatic } from '@hono/node-server/serve-static';
import type { AdminLoc, GaugeReading, Role, SyncRecord } from '@abuk/core';
import { applyOps, editAllowed, normId, opAllowed, opError, parseGauge, seedRegister, seedStore, signinError, whereIs, type FarmOp, type Register } from '@abuk/core';
import { cfg, health, missing, NotConfigured } from './config';
import { EXPIRY_DAYS, PIN, PIN_LOCK_MIN, PIN_MAX_FAILS, changeUsers, checkKey, checkPin, issueSession, loadUsers, makeUser, pinFields, readSession, toPublic, type Session } from './auth';
import { readJson, updateJson } from './adapters/github';
import { photoGet, photoPut, sheetsAppend } from './adapters/google';
import { parseInbound, sendSms } from './adapters/sms';
import { geeSummary, pull, terrain } from './sources';
import { resolvePayam, satelliteForPayam } from './satellite';
import { overview, recentChecks } from './dashboard';

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

// Names for the sign-in drop-down: active workers' ID and name only (no roles, keys or contacts).
app.get('/api/auth/roster', async c => {
  const f = await loadUsers();
  return c.json(f.users.filter(u => u.on && new Date(u.expires) > new Date()).map(u => ({ id: u.id, name: u.name, hasPin: !!u.pinHash })).sort((a, b) => a.name.localeCompare(b.name)));
});

app.post('/api/auth/signin-pin', async c => {
  if (limited(c.req.header('x-forwarded-for') || 'local')) return c.json({ error: 'too_many', message: 'Too many tries. Wait a minute.' }, 429);
  const { id = '', pin = '' } = await c.req.json<{ id?: string; pin?: string }>();
  if (!PIN.test(pin)) return c.json({ error: 'invalid', message: 'The PIN has 4 digits.' }, 400);
  const v = checkPin(await loadUsers(true), id, pin);
  if (!v.ok) {
    if ('fail' in v) {
      // Count the miss; the fifth in a row locks PIN sign-in for this worker for a while.
      const nid = normId(id);
      await changeUsers(`pin miss ${nid}`, f => ({ users: f.users.map(u => {
        if (u.id !== nid) return u;
        const n = (u.pinFails ?? 0) + 1;
        return { ...u, pinFails: n, pinLockedUntil: n >= PIN_MAX_FAILS ? new Date(Date.now() + PIN_LOCK_MIN * 60_000).toISOString() : u.pinLockedUntil };
      }) })).catch(() => {});
    }
    return c.json({ error: 'denied', message: v.error }, 401);
  }
  const s = await issueSession(v.user);
  changeUsers(`seen ${v.user.id}`, f => ({ users: f.users.map(u => u.id === v.user.id ? { ...u, lastSeen: new Date().toISOString(), pinFails: 0, pinLockedUntil: undefined } : u) })).catch(() => {});
  return c.json({ ...s, user: toPublic(v.user) });
});

app.post('/api/auth/pin', auth(), async c => {
  const { pin = '' } = await c.req.json<{ pin?: string }>();
  if (!PIN.test(pin)) return c.json({ error: 'invalid', message: 'The PIN has 4 digits.' }, 400);
  if (/^(\d)\1{3}$|^(0123|1234|2345|3456|4567|5678|6789|9876|8765|7654|6543|5432|4321|3210)$/.test(pin)) return c.json({ error: 'invalid', message: 'Choose a PIN that is harder to guess than 1111 or 1234.' }, 400);
  const me = c.get('me');
  await changeUsers(`set PIN ${me.id} (hash only)`, f => ({ users: f.users.map(u => (u.id === me.id ? { ...u, ...pinFields(pin) } : u)) }));
  return c.json({ ok: true });
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

app.get('/api/sources/gee', auth(), async c => {
  const p = coords(c), radius = Math.min(200, Math.max(1, Number(c.req.query('radius')) || 20));
  if (!p) return c.json({ error: 'invalid', message: 'lat and lon are required' }, 400);
  return c.json(await geeSummary(p.lat, p.lon, radius));
});

// Satellite indices averaged over one payam: ?pcode=SS030504, or ?lat=&lon= for the payam that point is in.
app.get('/api/sources/satellite', auth(), async c => {
  const pcode = c.req.query('pcode');
  const p = pcode ? null : coords(c);
  if (!pcode && !p) return c.json({ error: 'invalid', message: 'pcode, or lat and lon, is required' }, 400);
  const area = resolvePayam(pcode ? { pcode } : p!);
  if (!area) return c.json({ error: 'not_found', message: pcode ? `unknown payam code ${pcode}` : 'that point is outside the payam boundaries' }, 404);
  return c.json(await satelliteForPayam(area));
});
// Payam / county / state for a point (also works offline in the app from the same boundaries).
app.get('/api/where', async c => {
  const p = coords(c);
  if (!p) return c.json({ error: 'invalid', message: 'lat and lon are required' }, 400);
  return c.json(whereIs(p.lat, p.lon));
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

// ---- admin dashboard ----
app.get('/api/admin/overview', auth(['Admin']), async c => c.json(await overview(c.req.query('fresh') === '1')));

// Recent crop checks from all phones: the flood model and SMS alerts work from the whole farm, not one phone.
app.get('/api/checks/recent', auth(), async c => c.json(await recentChecks()));

// ---- farm register (plots, crops, groups, batches, processing runs) ----
const FARM_PATH = 'config/farm.json';
// Registers saved before the store ledger existed get the starting store and items.
const withStore = (r: Register): Register => ({ ...seedStore(), ...r });
app.get('/api/farm', auth(), async c => c.json(withStore((await readJson<Register>(FARM_PATH, seedRegister())).data)));

// Ops arrive in the order they were made on the phone (possibly offline); all of a batch commit together.
app.post('/api/farm/ops', auth(), async c => {
  const me = c.get('me');
  const { ops = [] } = await c.req.json<{ ops?: FarmOp[] }>();
  // The current register is only needed to check a worker's crop change (adding a pest name).
  const needCur = !editAllowed(me.role) && ops.some(o => o.op === 'upsert' && o.kind === 'crop');
  const cur = needCur ? withStore((await readJson<Register>(FARM_PATH, seedRegister())).data) : seedRegister();
  for (const o of ops) {
    if (!opAllowed(me.role, o, cur)) return c.json({ error: 'forbidden', message: o.op === 'remove' ? 'Only admins can delete from the farm register.' : 'Only admins and group leads can make this change to the farm register.' }, 403);
    const bad = opError(o);
    if (bad) return c.json({ error: 'invalid', message: `Farm change rejected: ${bad}.` }, 400);
  }
  if (!ops.length) return c.json(withStore((await readJson<Register>(FARM_PATH, seedRegister())).data));
  const r = await updateJson<Register>(FARM_PATH, seedRegister(), `farm: ${ops.length} change${ops.length > 1 ? 's' : ''} by ${me.id}`, reg => applyOps(withStore(reg), ops.slice(0, 200)));
  return c.json(r.data);
});

// ---- photos (crop checks, pest checks, crops) ----
const PHOTO_KEY = /^[a-z]+-[a-z0-9-]{4,80}$/;
app.put('/api/photos/:key', auth(), async c => {
  const key = c.req.param('key') ?? '';
  if (!PHOTO_KEY.test(key)) return c.json({ error: 'invalid', message: 'Bad photo name.' }, 400);
  if (missing('photos').length) return c.json({ error: 'not_configured', message: 'Photo storage is not set up on the server yet.' }, 503);
  const type = c.req.header('content-type') || 'image/jpeg';
  if (!/^image\/(jpeg|png|webp)$/.test(type)) return c.json({ error: 'invalid', message: 'Only JPEG, PNG or WebP photos.' }, 400);
  const body = new Uint8Array(await c.req.arrayBuffer());
  if (!body.length || body.length > 4_000_000) return c.json({ error: 'invalid', message: 'Photo is empty or larger than 4 MB.' }, 400);
  await photoPut(cfg.photoBucket, `photos/${key}`, body, type);
  return c.json({ ok: true, key });
});
app.get('/api/photos/:key', auth(), async c => {
  const key = c.req.param('key') ?? '';
  if (!PHOTO_KEY.test(key) || missing('photos').length) return c.json({ error: 'not_found' }, 404);
  const r = await photoGet(cfg.photoBucket, `photos/${key}`);
  if (!r) return c.json({ error: 'not_found' }, 404);
  return new Response(r.body, { headers: { 'content-type': r.headers.get('content-type') || 'image/jpeg', 'cache-control': 'private, max-age=31536000, immutable' } });
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

// Full numbers only for the people who send alerts from their own phone's Messages app.
app.get('/api/leads', auth(), async c => {
  const leads = (await readJson<Lead[]>('config/leads.json', [])).data;
  const full = c.req.query('full') === '1' && ['Admin', 'Group lead'].includes(c.get('me').role);
  return c.json(full ? leads : leads.map(l => ({ ...l, phone: mask(l.phone) })));
});

export const PHONE = /^\+211\d{9}$/;
app.put('/api/leads', auth(['Admin']), async c => {
  const { leads = [] } = await c.req.json<{ leads?: Lead[] }>();
  const clean = leads.map(l => ({ id: String(l.id || ''), name: String(l.name || '').trim(), group: String(l.group || '').trim(), rows: String(l.rows || '').trim(), phone: String(l.phone || '').replace(/[\s-]/g, ''), lang: l.lang === 'ar' ? 'ar' as const : 'en' as const }));
  const bad = clean.find(l => !l.id || !l.name || !PHONE.test(l.phone));
  if (bad) return c.json({ error: 'invalid', message: `Check ${bad.name || 'a recipient'}: name and a South Sudan number like +211 912 345 678 are needed.` }, 400);
  const r = await updateJson<Lead[]>('config/leads.json', [], `alert recipients updated by ${c.get('me').id}`, () => clean);
  return c.json(r.data);
});

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
async function recordGauge(from: string, text: string, extra: { at?: string; admin?: AdminLoc; by?: string } = {}): Promise<GaugeReading> {
  let reading: GaugeReading | null = null;
  await updateJson<GaugeReading[]>(GAUGE_PATH, [], `gauge reading from ${from.slice(-3)}`, list => {
    const last = list.find(r => r.status === 'ok')?.v ?? null;
    const v = parseGauge(text, last);
    reading = { from, text, at: extra.at ?? new Date().toISOString(), v: v.kind === 'bad' ? null : v.v, status: v.kind, ...(extra.admin ? { admin: extra.admin } : {}), ...(extra.by ? { by: extra.by } : {}) };
    // Newest reading first, so a reading entered late for an earlier day still lands in date order.
    return [reading, ...list].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 2000);
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

// Gauge readings typed into the app by any signed-in worker (no SMS gateway needed).
app.post('/api/gauge/test', auth(), async c => {
  const { text = '', at, sender, admin } = await c.req.json<{ text?: string; at?: string; sender?: string; admin?: AdminLoc }>();
  const when = at ? Date.parse(at) : Date.now();
  if (isNaN(when) || when > Date.now() + 5 * 60_000 || when < Date.now() - 30 * 864e5) return c.json({ error: 'invalid', message: 'The reading date must be within the last 30 days and not in the future.' }, 400);
  const place = admin && admin.state && admin.county && admin.payam ? { state: String(admin.state), county: String(admin.county), payam: String(admin.payam), village: String(admin.village ?? '') } : undefined;
  const r = await recordGauge(String(sender ?? '').trim().slice(0, 60) || c.get('me').name, text, { at: new Date(when).toISOString(), admin: place, by: c.get('me').id });
  return c.json({ reading: r, reply: replyFor(r) });
});

app.get('/api/gauge', auth(), async c => {
  const list = (await readJson<GaugeReading[]>(GAUGE_PATH, [])).data;
  return c.json(list.slice(0, 50).map(r => ({ ...r, from: /^\+?\d{6,}$/.test(r.from) ? mask(r.from) : r.from })));
});

// ---- admin dashboard web page (built from apps/dashboard) ----
const DASH = process.env.DASHBOARD_DIR || 'apps/dashboard/dist';
app.get('/admin', c => c.redirect('/admin/'));
app.use('/admin/*', serveStatic({ root: DASH, rewriteRequestPath: p => p.replace(/^\/admin/, '') }));
app.get('/admin/*', serveStatic({ path: `${DASH}/index.html` }));
