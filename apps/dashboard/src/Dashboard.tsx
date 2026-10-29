import { useEffect, useMemo, useRef, useState } from 'react';
import { conditionSummary, listPayams, signinError, whereIs, type GaugeReading, type PlotCondition, type PublicUser, type Register, type SatelliteIndices, type SigninResponse, type SyncKind } from '@abuk/core';
import { DayBars } from './DayBars';
import { DashMap, type CheckPoint, type DashMapHandle } from './DashMap';

interface Rec { id: string; kind: SyncKind; at: string; by: string; data: Record<string, unknown> }
interface Overview { generated: string; records: Rec[]; errors: string[]; users: (PublicUser & { lastSeen: string | null })[]; farm: Register; farmChanges: { sha: string; message: string; date: string }[]; gauge: GaugeReading[] }

interface SatState { v?: SatelliteIndices; error?: string; loading?: boolean }
const PAYAMS = listPayams();

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
  const mapRef = useRef<DashMapHandle>(null);
  const [sat, setSat] = useState<Record<string, SatState>>({});
  const [extraPayams, setExtraPayams] = useState<string[]>([]);

  const loadPayam = async (pcode: string) => {
    if (!session) return;
    setSat(s => ({ ...s, [pcode]: { ...s[pcode], loading: true } }));
    try {
      const r = await fetch(`/api/sources/satellite?pcode=${pcode}`, { headers: { authorization: `Bearer ${session.token}` } });
      const j = await r.json();
      if (!r.ok) throw new Error(j.message || j.error);
      setSat(s => ({ ...s, [pcode]: { v: j as SatelliteIndices } }));
    } catch (e) { setSat(s => ({ ...s, [pcode]: { error: (e as Error).message } })); }
  };

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

  // Payams that workers' GPS records fall in (busiest first), then payams holding a mapped plot, then any the admin added.
  const payamCodes = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of inRange) {
      const g = r.data.gps as { lat?: number; lon?: number } | null | undefined;
      const p = g && typeof g.lat === 'number' && typeof g.lon === 'number' ? whereIs(g.lat, g.lon) : null;
      if (p) counts.set(p.pcode, (counts.get(p.pcode) ?? 0) + 1);
    }
    for (const plot of data?.farm.plots ?? []) {
      const b = plot.boundary[0], p = b ? whereIs(b.lat, b.lon) : null;
      if (p && !counts.has(p.pcode)) counts.set(p.pcode, 0);
    }
    const fromGps = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
    return [...new Set([...fromGps, ...extraPayams])].slice(0, 12);
  }, [inRange, data, extraPayams]);

  const loadAllPayams = async (force = false) => {
    const todo = payamCodes.filter(p => force || !sat[p]);
    for (let i = 0; i < todo.length; i += 2) await Promise.all(todo.slice(i, i + 2).map(loadPayam));
  };
  useEffect(() => { void loadAllPayams(); }, [session, payamCodes.join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

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
          <DashMap ref={mapRef} plots={data?.farm.plots ?? []} points={points} />
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
        <h2>Satellite indices by payam · GEE</h2>
        <div className="note">
          NDVI, VCI, SPI and SPEI from Google Earth Engine, each averaged over the whole payam boundary. Shown for the payams where workers' GPS records fall in this period, plus payams with a mapped plot. SPI and SPEI are z-scores against 1991–2020 (−3 to +3). Kept 6 h per payam.
        </div>
        <div className="tbl-wrap" style={{ marginTop: 8 }}>
          <table className="tbl"><thead><tr><th>Payam</th><th>County</th><th style={{ textAlign: 'right' }}>km²</th><th style={{ textAlign: 'right' }}>NDVI</th><th style={{ textAlign: 'right' }}>VCI</th><th style={{ textAlign: 'right' }}>SPI</th><th style={{ textAlign: 'right' }}>SPEI</th><th style={{ textAlign: 'right' }}>Rain 30 d</th><th /></tr></thead>
            <tbody>{payamCodes.map(code => {
              const st = sat[code], v = st?.v, place = PAYAMS.find(p => p.pcode === code);
              const cell = (x: number | null | undefined, suffix = '') => <td className="num" style={{ textAlign: 'right' }}>{x == null ? '—' : `${x}${suffix}`}</td>;
              return [
                <tr key={code}>
                  <td><strong>{place?.payam ?? code}</strong>{st?.loading && <span className="note"> · loading…</span>}</td>
                  <td>{place ? `${place.county}, ${place.state}` : ''}</td>
                  <td className="num" style={{ textAlign: 'right' }}>{v?.areaKm2.toLocaleString('en') ?? '—'}</td>
                  {cell(v?.ndvi)}{cell(v?.vci, '%')}{cell(v?.spi)}{cell(v?.spei)}{cell(v?.precipMm, ' mm')}
                  <td>{extraPayams.includes(code) && <button className="link" onClick={() => setExtraPayams(x => x.filter(c => c !== code))}>remove</button>}</td>
                </tr>,
                (st?.error || v?.errors.length) ? <tr key={`${code}-err`}><td colSpan={9} className="note" style={{ color: '#c03020', fontSize: 11 }}>{st?.error ?? v?.errors.join('; ')}</td></tr> : null
              ];
            })}{!payamCodes.length && <tr><td colSpan={9} className="note">No GPS records or mapped plots in this period yet. Add a payam below.</td></tr>}</tbody>
          </table>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select aria-label="Add a payam" value="" onChange={e => { const code = e.target.value; if (code) setExtraPayams(x => (x.includes(code) ? x : [...x, code])); }}>
            <option value="">Add a payam…</option>
            {PAYAMS.map(p => <option key={p.pcode} value={p.pcode}>{p.payam} · {p.county} · {p.state}</option>)}
          </select>
          <button className="link" onClick={() => void loadAllPayams(true)}>Refresh all</button>
        </div>
      </div>

      <div className="panel">
        <h2>Plots · {data?.farm.plots.length ?? 0}</h2>
        <div className="tbl-wrap" style={{ maxHeight: 460 }}>
          <table className="tbl"><thead><tr><th>#</th><th>Code</th><th>Zone</th><th>Crop</th><th>Holder</th><th>Group</th><th style={{ textAlign: 'right' }}>Area (ha)</th><th style={{ textAlign: 'right' }}>Checks</th><th>GPS</th></tr></thead>
            <tbody>{(data?.farm.plots ?? []).map((p, i) => {
              const grp = data?.farm.groups.find(g => g.id === p.groupId);
              const plotChecks = inRange.filter(r => r.kind === 'monitor' && r.data.plot === p.code).length;
              const hasBoundary = p.boundary.length > 2;
              return (
                <tr key={p.id} style={{ cursor: hasBoundary ? 'pointer' : 'default' }} onClick={() => mapRef.current?.focusPlot(p.id)}>
                  <td>{i + 1}</td>
                  <td><strong>{p.code}</strong></td>
                  <td>{p.zone}</td>
                  <td>{p.crop}{p.crops?.length ? `, ${p.crops.join(', ')}` : ''}</td>
                  <td>{p.holder}</td>
                  <td>{grp?.name ?? p.groupId}</td>
                  <td className="num" style={{ textAlign: 'right' }}>{p.areaHa != null ? p.areaHa.toFixed(1) : '—'}</td>
                  <td className="num" style={{ textAlign: 'right' }}>{plotChecks}</td>
                  <td>{hasBoundary ? 'mapped' : p.boundary[0] ? 'pin' : '—'}</td>
                </tr>
              );
            })}{!data?.farm.plots.length && <tr><td colSpan={9} className="note">No plots registered yet.</td></tr>}</tbody>
          </table>
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
