// Where each kind of data comes from and where it is saved, with the live state of this phone's queue and of the server's copy in Drive.
import { useEffect, useState } from 'react';
import { api, explain } from '../api';
import { go, useApp } from '../store';
import { useOnline } from '../net';

interface Storage {
  records: { sheet: boolean }; register: { github: boolean }; photos: { bucket: boolean };
  mirror: { at: string | null; ok: boolean; error: string; lists: number; rows: number; running: boolean }; sheetUrl: string;
}

const ago = (iso: string | null) => {
  if (!iso) return 'never';
  const m = Math.round((Date.now() - Date.parse(iso)) / 60000);
  return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};

// [what, where it is saved, how it gets updated]
const ROWS: [string, string, string][] = [
  ['Crop checks, harvests, water-depth readings, alerts sent, payout lists, pest checks', 'Google Sheet "Abuk Project records" in the Drive folder, one tab for each kind', 'Saved on this phone first; sent at the next sync when there is signal (or carried by another phone)'],
  ['Farm register: plots, groups, people, VSLA, stores and orders, herds, containers, land assessments, tasks, mound survey', 'Master copy in the project\'s private GitHub repository (every change is versioned), and a readable copy in the Drive sheet (tabs named register_…)', 'Every change is applied on the phone at once and sent with signal; the Drive copy is rewritten after each change that reaches the server'],
  ['River gauge readings', 'GitHub (data/gauge.json) and the Drive sheet tab gauge_readings', 'When a reading is typed in the app or arrives by SMS'],
  ['Photos (crop checks, pests, crops)', 'A private Google Cloud Storage bucket, not the Drive folder', 'Kept on the phone and uploaded with signal'],
  ['County bulletin, rain ensemble, river stations, altimetry, ECMWF', 'Read from the Drive folder (colab_waterlevel); the project\'s nightly job writes them there', 'The app downloads what is near you once a day with signal, or when you tap Pull now'],
  ['NDVI, VCI, SPI, SPEI, flood extent, soil moisture', 'Not stored: computed by Google Earth Engine for the payam each time (kept 6 hours on the server)', 'When you open Satellite indices or Flood model with signal'],
  ['Weather at your GPS point', 'Not stored: Open-Meteo', 'Each time you open the app with signal'],
  ['Flood model: depth by zone, days to dry, planting window, mound status', 'Not stored: worked out on the phone from the depth readings, the gauge and the mound survey above', 'Changes when any of those change']
];

export function DataMap() {
  const s = useApp(), online = useOnline();
  const admin = s.session?.user.role === 'Admin';
  const [st, setSt] = useState<Storage | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => {
    if (!s.session || s.session.demo) return;
    api<Storage>('/api/storage').then(r => { setSt(r); setErr(''); }, e => setErr(explain(e)));
  };
  useEffect(load, [!!s.session]); // eslint-disable-line react-hooks/exhaustive-deps

  const backup = async () => {
    setBusy(true); setErr('');
    try { await api('/api/storage/backup', { method: 'POST', body: {} }); load(); }
    catch (e) { setErr(explain(e)); }
    finally { setBusy(false); }
  };

  const tile = (k: string, v: string, sub: string) => (
    <div style={{ padding: '10px 12px', minWidth: 0 }}><div className="lbl">{k}</div><div className="head num" style={{ fontSize: 22 }}>{v}</div><div className="sub">{sub}</div></div>
  );
  const flag = (ok: boolean | undefined) => (ok === undefined ? '—' : ok ? 'set up' : 'not set up');

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13.5 }}>Everything you record is kept on this phone first, so it works with no signal. It is copied to the project when the phone has signal. This page shows what is waiting and where each kind of data ends up.</p>

      <div className="box grid3">
        <div style={{ borderRight: '1px solid var(--color-divider)' }}>{tile('Waiting', String(s.outbox.length), 'records to send')}</div>
        <div style={{ borderRight: '1px solid var(--color-divider)' }}>{tile('Edits', String(s.farmOps.length), 'register changes waiting')}</div>
        {tile('Last sync', s.lastSync ? ago(s.lastSync) : 'never', online ? 'online' : 'offline')}
      </div>
      {s.outbox.length + s.farmOps.length > 0 && <div className="sub">These are only on this phone until it syncs. <button className="link" onClick={() => go('p2p')}>Pass them to another phone</button> if you have no signal.</div>}

      <div className="col g8">
        <div className="section">Project storage</div>
        {s.session?.demo || !s.session ? <div className="note">Sign in to see the server's storage status.</div> : st ? (
          <>
            <div className="rowg"><span style={{ fontSize: 13.5 }}>Records sheet in Drive</span><span className="it" style={{ fontSize: 13 }}>{flag(st.records.sheet)}</span></div>
            <div className="rowg"><span style={{ fontSize: 13.5 }}>Register master copy (GitHub)</span><span className="it" style={{ fontSize: 13 }}>{flag(st.register.github)}</span></div>
            <div className="rowg"><span style={{ fontSize: 13.5 }}>Photo storage</span><span className="it" style={{ fontSize: 13 }}>{flag(st.photos.bucket)}</span></div>
            <div className="rowg"><span><span style={{ display: 'block', fontSize: 13.5 }}>Register copy in Drive</span><span className="sub">{st.mirror.running ? 'writing now…' : st.mirror.at ? `${st.mirror.lists} tabs, ${st.mirror.rows} rows, ${ago(st.mirror.at)}` : 'not written since the server last started'}</span></span><span className="it" style={{ fontSize: 13, color: st.mirror.ok ? 'var(--color-accent-800)' : '#a02018' }}>{st.mirror.ok ? 'ok' : 'failed'}</span></div>
            {!st.mirror.ok && st.mirror.error && <div className="msg" style={{ fontSize: 12 }}>{st.mirror.error}</div>}
            {admin && <div className="grid2"><button className="btn plain" disabled={busy} onClick={backup}>{busy ? 'Writing to Drive…' : 'Back up to Drive now'}</button>{st.sheetUrl ? <a className="btn plain" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }} href={st.sheetUrl} target="_blank" rel="noreferrer">Open the sheet</a> : <span />}</div>}
          </>
        ) : <div className="note">{err || 'Loading…'}</div>}
        {err && st && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}
      </div>

      <div>
        <div className="section">What goes where</div>
        {ROWS.map(([what, where, how]) => (
          <div key={what} className="col g6" style={{ padding: '10px 0', borderBottom: '1px solid var(--color-divider)' }}>
            <span style={{ fontSize: 13.5 }}>{what}</span>
            <span className="sub" style={{ lineHeight: 1.45 }}><strong style={{ fontWeight: 600 }}>Saved in:</strong> {where}</span>
            <span className="sub" style={{ lineHeight: 1.45 }}><strong style={{ fontWeight: 600 }}>Updated:</strong> {how}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
