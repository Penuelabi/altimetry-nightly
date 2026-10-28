import { useEffect, useMemo, useState } from 'react';
import { conditionSummary, signinError, whereIs, type GaugeReading, type PlotCondition, type PublicUser, type Register, type SigninResponse, type SyncKind } from '@abuk/core';
import { DayBars } from './DayBars';
import { DashMap, type CheckPoint } from './DashMap';

interface Rec { id: string; kind: SyncKind; at: string; by: string; data: Record<string, unknown> }
interface Overview { generated: string; records: Rec[]; errors: string[]; users: (PublicUser & { lastSeen: string | null })[]; farm: Register; farmChanges: { sha: string; message: string; date: string }[]; gauge: GaugeReading[] }

const KEY = 'abuk-admin-session';
const KIND_LABEL: Record<string, string> = { monitor: 'Crop check', harvest: 'Harvest', plot: 'Plot mapped', task: 'Task', pest: 'Pest report', payout: 'Payout', store: 'Store', offer: 'Market offer', voice: 'Pictures & voice', alert: 'Flood alert sent' };
const fmt = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const day = (iso: string) => iso.slice(0, 10);

function loadSession(): SigninResponse | null {
  try { const s = JSON.parse(localStorage.getItem(KEY) || 'null') as SigninResponse | null; return s && Date.parse(s.expires) > Date.now() ? s : null; } catch { return null; }
}

// Plain-language one-liner for each record type.
export function summary(r: Rec, farm: Register): string {
  const d = r.data as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  switch (r.kind) {
    case 'monitor': return [d.plot, d.crop, d.stage, d.condition ? conditionSummary(d.condition as PlotCondition) : '', d.cond ? `health ${d.cond}/5` : '', (d.pests as string[] | undefined)?.filter(p => p !== 'None').join(', ')].filter(Boolean).join(' · ');
    case 'harvest': return `${d.crop} · ${d.kg} kg · plot ${d.plot}${d.who ? ` · ${d.who}` : ''}`;
    case 'plot': return `${d.plot ? `Plot ${d.plot}` : 'Unassigned capture'} · ${d.mode === 'walk' ? `boundary${d.ha ? `, ${d.ha} ha` : ''}` : 'pin'}`;
    case 'task': return `Task ${d.id} ${d.done ? 'done' : 'reopened'}`;
    case 'pest': return `${d.plot ?? ''} · ${d.suggestion} ${d.confirmed ? 'confirmed' : 'rejected, sent for second opinion'}`;
    case 'payout': return `${d.group ?? ''} · $${d.amount ?? d.pool} · ${(d.shares as unknown[] | undefined)?.length ?? 0} members`;
    case 'store': return d.request ? `Requested: ${(d.request as string[]).join(', ')}` : `Issued ${d.issued} ${d.unit} ${d.item} to ${d.to}`;
    case 'offer': return `${d.buyer}: ${d.answer} at $${d.price}/L`;
    case 'voice': return `Activity done: ${d.activity}`;
    case 'alert': return `${d.lang === 'ar' ? 'Arabic' : 'English'} SMS to ${(d.to as string[] | undefined)?.length ?? 0} leads from the sender's phone: "${d.text}"`;
    default: return JSON.stringify(d).slice(0, 90);
  }
}

// Flags an admin should look at today.
function attention(r: Rec): string | null {
  const d = r.data as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  if (r.kind === 'monitor') {
    const c = d.condition as PlotCondition | undefined;
    if (c && ['flooded', 'waterlogged'].includes(c.water)) return c.water === 'flooded' ? `Flooded ${c.floodDepthCm} cm` : 'Waterlogged';
    if (c?.around === 'cut-off') return 'Plot cut off by water';
    if (c?.trend === 'rising' && c.around !== 'dry') return 'Water rising around plot';
    if (c?.surface?.some(s => s.startsWith('erosion') || s === 'mound-damage')) return 'Erosion or mound damage';
    if (Number(d.cond) <= 2) return `Crop health ${d.cond}/5`;
    if ((d.pests as string[] | undefined)?.some(p => p !== 'None')) return `Pests: ${(d.pests as string[]).filter(p => p !== 'None').join(', ')}`;
  }
  if (r.kind === 'pest' && d.confirmed) return `Pest confirmed: ${d.suggestion}`;
  return null;
}

export function Dashboard() {
  const [session, setSession] = useState<SigninResponse | null>(loadSession);
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [range, setRange] = useState(30);
  const [kind, setKind] = useState<string>('all');
  const [who, setWho] = useState<string>('all');

  const load = async (fresh = false) => {
    if (!session) return;
    setBusy(true); setErr('');
    try {
      const r = await fetch(`/api/admin/overview${fresh ? '?fresh=1' : ''}`, { headers: { authorization: `Bearer ${session.token}` } });
      if (r.status === 401) { localStorage.removeItem(KEY); setSession(null); return; }
      const j = await r.json();
      if (!r.ok) throw new Error(j.message || j.error);
      setData(j);
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };
  useEffect(() => { load(); const iv = setInterval(() => load(), 120_000); return () => clearInterval(iv); }, [session]); // eslint-disable-line react-hooks/exhaustive-deps

  const since = useMemo(() => new Date(Date.now() - range * 864e5).toISOString(), [range, data]);
  const inRange = useMemo(() => (data?.records ?? []).filter(r => r.at >= since), [data, since]);
  const shown = inRange.filter(r => (kind === 'all' || r.kind === kind) && (who === 'all' || r.by === who));

  if (!session) return <Login onDone={setSession} />;

  const users = data?.users ?? [];
  const nameOf = (id: string) => users.find(u => u.id === id)?.name ?? id;
  const checks = inRange.filter(r => r.kind === 'monitor');
  const harvestKg = inRange.filter(r => r.kind === 'harvest').reduce((a, r) => a + (Number(r.data.kg) || 0), 0);
  const active = new Set(inRange.map(r => r.by)).size;
  const flags = inRange.map(r => ({ r, why: attention(r) })).filter((x): x is { r: Rec; why: string } => !!x.why);
  const gaugeOk = data?.gauge.find(g => g.status === 'ok');
  const held = data?.gauge.filter(g => g.status === 'held').length ?? 0;
  const mapped = data?.farm.plots.filter(p => p.boundary.length > 2).length ?? 0;

  const days = Array.from({ length: Math.min(range, 60) }, (_, i) => day(new Date(Date.now() - (Math.min(range, 60) - 1 - i) * 864e5).toISOString()));
  const perDay = days.map(d => {
    const rs = shown.filter(r => day(r.at) === d);
    const by: Record<string, number> = {};
    rs.forEach(r => { by[r.kind] = (by[r.kind] || 0) + 1; });
    return { day: d, count: rs.length, detail: Object.entries(by).map(([k, n]) => `${KIND_LABEL[k] ?? k}: ${n}`).join(' · ') };
  });

  const points: CheckPoint[] = checks.flatMap(r => {
    const g = r.data.gps as { lat: number; lon: number } | null;
    return g ? [{ lat: g.lat, lon: g.lon, label: `${fmt(r.at)} · ${nameOf(r.by)}`, text: summary(r, data!.farm), flag: !!attention(r) }] : [];
  });

  const csv = () => {
    const rows = [['time', 'type', 'worker', 'payam', 'summary', 'data'], ...shown.map(r => {
      const g = r.data.gps as { lat: number; lon: number } | null;
      return [r.at, KIND_LABEL[r.kind] ?? r.kind, `${nameOf(r.by)} (${r.by})`, g ? whereIs(g.lat, g.lon)?.payam ?? '' : '', summary(r, data!.farm), JSON.stringify(r.data)];
    })];
    const blob = new Blob([rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')], { type: 'text/csv' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `abuk-records-${day(new Date().toISOString())}.csv`; a.click();
  };

  return (
    <div className="dash">
      <div className="dash-top">
        <img src="/admin/icon.png" alt="" />
        <div style={{ flex: 1, minWidth: 220 }}>
          <div className="kick">Abuk Project · admin</div>
          <div className="dash-title">Field updates</div>
        </div>
        <span className="note">{data ? `Updated ${fmt(data.generated)}` : busy ? 'Loading…' : ''} · signed in as {session.user.name}</span>
        <button className="btn plain sm" onClick={() => load(true)} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh'}</button>
        <button className="link" onClick={() => { localStorage.removeItem(KEY); setSession(null); }}>Sign out</button>
      </div>

      {err && <div className="err">Could not load: {err}</div>}
      {data?.errors.length ? <div className="note">Some sources did not load: {data.errors.join('; ')}</div> : null}

      <div className="filters">
        <div className="seg">{[7, 30, 90, 365].map(d => <button key={d} className={range === d ? 'on' : ''} onClick={() => setRange(d)}>{d === 365 ? '1 year' : `${d} days`}</button>)}</div>
        <select className="input" style={{ width: 'auto', minHeight: 36 }} value={kind} onChange={e => setKind(e.target.value)}>
          <option value="all">All update types</option>{Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <select className="input" style={{ width: 'auto', minHeight: 36 }} value={who} onChange={e => setWho(e.target.value)}>
          <option value="all">All workers</option>{users.map(u => <option key={u.id} value={u.id}>{u.name} ({u.id})</option>)}
        </select>
        <button className="btn plain sm" onClick={csv} disabled={!shown.length}>Download CSV ({shown.length})</button>
      </div>

      <div className="tiles">
        <Tile k="Updates" v={inRange.length} s={`last ${range} days`} />
        <Tile k="Crop checks" v={checks.length} s={`${new Set(checks.map(c => c.data.plot)).size} plots visited`} />
        <Tile k="Needs attention" v={flags.length} s="flood, damage, pests, poor health" />
        <Tile k="Harvest" v={`${Math.round(harvestKg).toLocaleString('en')} kg`} s={`${inRange.filter(r => r.kind === 'harvest').length} entries`} />
        <Tile k="Active workers" v={`${active} / ${users.filter(u => u.on).length}`} s="sent updates in range" />
        <Tile k="Bor gauge" v={gaugeOk?.v != null ? `${gaugeOk.v.toFixed(2)} m` : '—'} s={gaugeOk ? `${fmt(gaugeOk.at)}${held ? ` · ${held} held for review` : ''}` : 'no readings yet'} />
        <Tile k="Plots mapped" v={`${mapped} / ${data?.farm.plots.length ?? 0}`} s="with GPS boundary" />
      </div>

      <div className="panel">
        <h2>Updates per day{kind !== 'all' ? ` · ${KIND_LABEL[kind]}` : ''}</h2>
        <DayBars data={perDay} />
      </div>

      <div className="cols">
        <div className="panel">
          <h2>Map · plots and crop checks</h2>
          <DashMap plots={data?.farm.plots ?? []} points={points} />
          <div className="note">Outlines: mapped plots. Dots: crop checks with GPS; ringed dots need attention. Click a dot for details.</div>
        </div>
        <div className="panel">
          <h2>Needs attention · {flags.length}</h2>
          <div className="tbl-wrap" style={{ maxHeight: 420 }}>
            <table className="tbl"><thead><tr><th>When</th><th>Issue</th><th>Where / who</th></tr></thead>
              <tbody>{flags.slice(0, 100).map(({ r, why }) => (
                <tr key={r.id}><td style={{ whiteSpace: 'nowrap' }}>{fmt(r.at)}</td><td><span className="pill warn">⚠ {why}</span></td><td>{String(r.data.plot ?? '')} · {nameOf(r.by)}</td></tr>
              ))}{!flags.length && <tr><td colSpan={3} className="note">Nothing flagged in this period.</td></tr>}</tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Latest updates · {shown.length}</h2>
        <div className="tbl-wrap">
          <table className="tbl"><thead><tr><th>Time</th><th>Type</th><th>Worker</th><th>Details</th></tr></thead>
            <tbody>{shown.slice(0, 300).map(r => (
              <tr key={r.id}><td style={{ whiteSpace: 'nowrap' }}>{fmt(r.at)}</td><td><span className="pill">{KIND_LABEL[r.kind] ?? r.kind}</span></td><td style={{ whiteSpace: 'nowrap' }}>{nameOf(r.by)}</td><td>{data ? summary(r, data.farm) : ''}{attention(r) ? <> <span className="pill warn">⚠ {attention(r)}</span></> : null}</td></tr>
            ))}{!shown.length && <tr><td colSpan={4} className="note">{data ? 'No updates in this period. Records appear here after phones sync.' : 'Loading…'}</td></tr>}</tbody>
          </table>
        </div>
      </div>

      <div className="cols">
        <div className="panel">
          <h2>Workers</h2>
          <div className="tbl-wrap">
            <table className="tbl"><thead><tr><th>Name</th><th>Role</th><th>Last sign‑in</th><th style={{ textAlign: 'right' }}>Updates</th></tr></thead>
              <tbody>{users.map(u => (
                <tr key={u.id} style={{ opacity: u.on ? 1 : .5 }}><td>{u.name} <span className="mono sub">{u.id}</span></td><td>{u.role}{u.on ? '' : ' · revoked'}</td><td>{u.lastSeen ? fmt(u.lastSeen) : 'never'}</td><td className="num" style={{ textAlign: 'right' }}>{inRange.filter(r => r.by === u.id).length}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <h2>Farm register changes</h2>
          <div className="note">{data ? `${data.farm.plots.length} plots · ${data.farm.crops.length} crops · ${data.farm.groups.length} groups (${data.farm.groups.reduce((a, g) => a + g.members.length, 0)} members) · ${data.farm.batches.length} bottle batches` : ''}</div>
          <div className="tbl-wrap">
            <table className="tbl"><thead><tr><th>When</th><th>Change</th></tr></thead>
              <tbody>{(data?.farmChanges ?? []).map(c => <tr key={c.sha}><td style={{ whiteSpace: 'nowrap' }}>{fmt(c.date)}</td><td>{c.message.replace(/^farm: /, '')}</td></tr>)}
                {!data?.farmChanges.length && <tr><td colSpan={2} className="note">No changes saved to the server yet.</td></tr>}</tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

const Tile = ({ k, v, s }: { k: string; v: string | number; s: string }) => (
  <div className="tile"><div className="k">{k}</div><div className="v">{v}</div><div className="s">{s}</div></div>
);

function Login({ onDone }: { onDone: (s: SigninResponse) => void }) {
  const [id, setId] = useState(''), [key, setKey] = useState(''), [err, setErr] = useState(''), [busy, setBusy] = useState(false);
  const go = async () => {
    const bad = signinError(id, key);
    if (bad) return setErr(bad);
    setBusy(true); setErr('');
    try {
      const r = await fetch('/api/auth/signin', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ id, key }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.message || j.error);
      if (j.user.role !== 'Admin') throw new Error('This dashboard is for admins only.');
      try { localStorage.setItem(KEY, JSON.stringify(j)); } catch { /* session only */ }
      onDone(j);
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <div className="login">
      <img src="/admin/icon.png" alt="" style={{ width: 64, height: 64, borderRadius: '50%' }} />
      <div><div className="kick">Abuk Project</div><h1 className="h1" style={{ fontSize: 34, margin: '4px 0 0' }}>Admin dashboard</h1></div>
      <label className="field">Admin ID<input className="input" value={id} placeholder="AD‑001" onChange={e => setId(e.target.value.toUpperCase())} /></label>
      <label className="field">Access key<input className="input mono" type="password" value={key} placeholder="abk_…" onChange={e => setKey(e.target.value.trim())} onKeyDown={e => e.key === 'Enter' && go()} /></label>
      {err && <div className="err">{err}</div>}
      <button className="btn lg" onClick={go} disabled={busy}>{busy ? 'Checking…' : 'Sign in'}</button>
    </div>
  );
}
