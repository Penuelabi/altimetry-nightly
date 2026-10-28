import { useEffect, useState } from 'react';
import { SOURCES, type PullResult } from '@abuk/core';
import { go, setState, useApp } from '../store';
import { api, explain } from '../api';
import { useOnline, usePlace } from '../net';
import { Field, Seg, Toggle } from '../ui';

interface Extra { kind: 'GitHub' | 'Drive'; url: string; by: string; at: string }
const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

// Which pull section feeds which listed source, so each row can show its own status.
const SECTION: Record<string, (p: PullResult) => string | null> = {
  bull: p => (p.bulletin ? '1 row' : null), ens: p => (p.bulletin ? 'from bulletin' : null),
  stat: p => (p.stations.rows.length ? `${p.stations.rows.length} station${p.stations.rows.length > 1 ? 's' : ''}${p.stations.fallback ? ', nearest outside radius' : ''}` : null),
  alt: p => (p.stations.rows.length ? 'nearby rows' : null), ifs: p => (p.ifs.length ? `${p.ifs.length} stations` : null),
  sm: p => (p.gee.soilMoisture != null ? 'mean in radius' : null), fx: p => (p.gee.floodExtentPct != null ? 'mean in radius' : null),
  payam: () => 'built into the app'
};

export function Sources() {
  const s = useApp(), online = useOnline(), at = usePlace();
  const [geeBusy, setGeeBusy] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [msg, setMsg] = useState('');
  const [conn, setConn] = useState<'GitHub' | 'Drive' | null>(null);
  const [url, setUrl] = useState('');
  const [extra, setExtra] = useState<Extra[]>([]);
  const p = s.lastPull;
  const isAdmin = s.session?.user.role === 'Admin';

  useEffect(() => {
    if (online) api<Extra[]>('/api/sources/extra').then(setExtra, () => {});
  }, [online]);

  const pull = async () => {
    if (!online) return setMsg('No signal. Pull is queued and will run when the phone reconnects.');
    setPulling(true); setMsg('');
    try {
      const q = `lat=${at.lat}&lon=${at.lon}&radius=${s.radius}`;
      // Earth Engine runs alongside; its numbers drop in when ready instead of holding up the rest.
      setGeeBusy(true);
      const gee = api<PullResult['gee']>(`/api/sources/gee?${q}`)
        .then(g => setState(st => (st.lastPull ? { lastPull: { ...st.lastPull, gee: g } } : {})), () => {})
        .finally(() => setGeeBusy(false));
      const r = await api<PullResult>(`/api/sources/pull?${q}`);
      setState(st => ({ lastPull: { ...r, gee: st.lastPull?.gee.soilMoisture != null || st.lastPull?.gee.floodExtentPct != null ? st.lastPull.gee : r.gee } }));
      setMsg(r.errors.length ? `Pulled with ${r.errors.length} problem${r.errors.length > 1 ? 's' : ''}: ${r.errors.join('; ')}` : 'Pulled. Satellite soil moisture and flood extent follow in a moment.');
      setPulling(false);
      await gee;
    } catch (e) { setMsg(explain(e)); setPulling(false); }
  };

  const connect = async () => {
    if (!url.trim()) return setMsg('Paste a link first.');
    try { setExtra(await api<Extra[]>('/api/sources/extra', { body: { kind: conn, url: url.trim() } })); setConn(null); setUrl(''); setMsg('Connected. Files will be indexed on the next nightly run.'); }
    catch (e) { setMsg(explain(e)); }
  };

  const rows = [...SOURCES, ...extra.map((x, i) => ({ id: 'x' + i, kind: x.kind, name: 'Added source', path: x.url, size: '—', last: `added ${when(x.at)} by ${x.by}`, feeds: 'not mapped yet', on: false }))];
  const on = (id: string) => s.sourcesOn[id] ?? false;

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13.5 }}>Pulled from the colab_waterlevel Drive folder and Earth Engine, filtered to where this phone is. Only rows inside the radius are downloaded and kept for offline use.</p>
      <div className="card accent">
        <div className="kick sm">Current location</div>
        <div className="num" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 10px', fontSize: 13 }}>
          <span><span className="lbl" style={{ display: 'block', textTransform: 'none', letterSpacing: 0 }}>GPS</span>{at.lat.toFixed(4)}° N, {at.lon.toFixed(4)}° E{at.gps ? (at.acc ? ` ±${Math.round(at.acc)} m` : '') : ' (farm, no GPS yet)'}</span>
          <span><span className="lbl" style={{ display: 'block', textTransform: 'none', letterSpacing: 0 }}>County · State</span>{at.county} · {at.state}</span>
          <span><span className="lbl" style={{ display: 'block', textTransform: 'none', letterSpacing: 0 }}>Payam</span>{at.payam}</span>
          <span><span className="lbl" style={{ display: 'block', textTransform: 'none', letterSpacing: 0 }}>Covers</span>{s.radius} km around you</span>
        </div>
        <Seg items={[[10, '10 km'], [20, '20 km'], [50, '50 km']]} value={s.radius} onPick={r => setState({ radius: r })} fontSize={12.5} />
      </div>
      <div className="between" style={{ alignItems: 'center', borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)', padding: '8px 0' }}>
        <span className="num" style={{ fontSize: 12.5, color: 'var(--color-neutral-800)' }}>{rows.filter(r => on(r.id)).length} of {rows.length} feeding the model · {s.radius} km{p ? ` · pulled ${when(p.at)}` : ''}</span>
        <button className="btn sm" style={{ fontSize: 13, minHeight: 38 }} onClick={pull}>{pulling ? 'Pulling…' : online ? 'Pull now' : 'Pull when online'}</button>
      </div>
      {msg && <div className="msg">{msg}</div>}
      <div>
        {rows.map(r => {
          const st = p && SECTION[r.id]?.(p);
          return (
            <div key={r.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, padding: '10px 0', borderBottom: '1px solid var(--color-divider)', alignItems: 'start' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}><span style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase', border: '1px solid var(--color-divider)', borderRadius: 'var(--radius-sm)', padding: '1px 5px', color: 'var(--color-neutral-800)', flex: 'none' }}>{r.kind}</span><span style={{ fontSize: 14, lineHeight: 1.3 }}>{r.name}</span></div>
                <div className="sub num" style={{ marginTop: 3, wordBreak: 'break-all' }}>{r.path}</div>
                <div className="sub num">{r.size} · {(pulling || (geeBusy && r.kind === 'GEE')) && on(r.id) ? 'pulling…' : p && SECTION[r.id] ? (st ? `${st} · ${when(p.at)}` : 'no data on last pull') : r.last} · feeds <em>{r.feeds}</em></div>
              </div>
              <Toggle on={on(r.id)} label="Use in model" onClick={() => setState(x => ({ sourcesOn: { ...x.sourcesOn, [r.id]: !on(r.id) } }))} />
            </div>
          );
        })}
      </div>
      <div className="col g8">
        {isAdmin && <button className="btn plain" style={{ minHeight: 44, fontSize: 13.5, marginBottom: 6 }} onClick={() => go('admin')}>Manage users & access keys (admin)</button>}
        <h2 className="h2 h20">Connect a source</h2>
        <div className="grid2">
          <button className="btn" style={{ fontSize: 13.5, borderColor: conn === 'GitHub' ? 'var(--color-accent-800)' : undefined }} onClick={() => { setConn('GitHub'); setUrl(''); }}>GitHub repository</button>
          <button className="btn" style={{ fontSize: 13.5, borderColor: conn === 'Drive' ? 'var(--color-accent-800)' : undefined }} onClick={() => { setConn('Drive'); setUrl(''); }}>Google Drive folder</button>
        </div>
        {conn && (
          <div className="box col g8" style={{ padding: 12 }}>
            <Field label={conn === 'Drive' ? 'Shared Drive folder link' : 'Repository and folder'}>
              <input className="input" style={{ fontSize: 13 }} value={url} onChange={e => setUrl(e.target.value)} placeholder={conn === 'Drive' ? 'drive.google.com/drive/folders/…' : 'github.com/owner/repo/tree/main/data'} />
            </Field>
            <div className="sub" style={{ lineHeight: 1.45 }}>Accepted: CSV, GeoJSON, GeoTIFF (clipped to the farm), Google Sheets. Share Drive folders with the project's service account first.{isAdmin ? '' : ' Only admins can add sources.'}</div>
            <button className="btn md" disabled={!isAdmin} onClick={connect}>Connect</button>
          </div>
        )}
      </div>
    </div>
  );
}
