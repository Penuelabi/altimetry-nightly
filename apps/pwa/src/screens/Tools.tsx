import { useEffect, useMemo, useRef, useState } from 'react';
import { get as idbGet, set as idbSet } from 'idb-keyval';
import { P2P_PEERS, PARTS, PICTO, STORE, TOOLS, bulletinInputs, pestInfo, pestOptions, plotLabel, type Part, editAllowed, leadAlert, newId, parseGauge, qrCells, type GaugeReading } from '@abuk/core';
import { farmChange, go, openRegister, record, setState, useApp, type Lead } from '../store';
import { api, explain } from '../api';
import { oneFix, useOnline, usePlace } from '../net';
import { Check, Chevron, Field, Icon, Seg, Toggle } from '../ui';
import { allChecks, useHereData, useModel } from './common';
import { loadChecks } from '../daily';
import { savePhoto } from '../photos';

export function Tools() {
  return (
    <div style={{ padding: '10px 18px 24px' }}>
      {TOOLS.map(([n, k, name, sub]) => (
        <button key={k} className="row hov" onClick={() => go(k)} style={{ display: 'grid', gridTemplateColumns: '34px 1fr 16px', gap: 10, alignItems: 'center', padding: '12px 0', minHeight: 56 }}>
          <span className="head" style={{ fontSize: 20, color: 'var(--color-accent)' }}>{n}</span>
          <span><span className="head" style={{ display: 'block', fontWeight: 600, fontSize: 18, lineHeight: 1.15 }}>{name}</span><span style={{ fontSize: 12, color: 'var(--color-neutral-700)', lineHeight: 1.35 }}>{sub}</span></span>
          <Chevron />
        </button>
      ))}
    </div>
  );
}

// ---- i Flood SMS alerts ----
// One message per group lead, built from live data (see leadAlert): their own plots' latest crop checks
// from every phone, the fitted water model, rain forecast and the county bulletin. Sent from the phone's
// own Messages app: the app fills in the number and text, the person presses Send, and it goes from their SIM.
const smsLink = (numbers: string[], body: string) => `sms:${numbers.join(',')}?body=${encodeURIComponent(body)}`;
const openMessages = (href: string) => { const a = document.createElement('a'); a.href = href; a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove(); };
const LEVEL_WORD = { warn: 'Warning', watch: 'Watch', clear: 'All clear' } as const;

export function Alerts() {
  const s = useApp(), online = useOnline(), place = usePlace(), model = useModel(), { weather } = useHereData();
  const role = s.session?.user.role ?? '';
  const canSend = role === 'Admin' || role === 'Group lead', isAdmin = role === 'Admin';
  const [days, setDays] = useState(5);
  const [msg, setMsg] = useState('');
  const [editing, setEditing] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [sent, setSent] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (!online) return;
    api<{ id: string; name: string; group: string; rows: string; phone: string; lang: 'en' | 'ar' }[]>(`/api/leads${canSend ? '?full=1' : ''}`)
      .then(ls => setState(st => ({ leads: ls.map(l => ({ ...l, on: st.leads.find(x => x.id === l.id)?.on ?? true })) })), () => {});
    loadChecks().catch(() => {});
  }, [online, canSend]);
  const leads = s.leads.filter(l => /^\+211\d{9}$/.test(l.phone));
  const bulletin = s.lastPull?.bulletin ? bulletinInputs(s.lastPull.bulletin.values) : null;
  const checks = allChecks(s);
  const alerts = leads.map(l => ({ l, a: leadAlert({ lead: l, reg: s.farm, checks, model, bulletin, rainNext7: weather?.rainNext7 ?? null, days, payam: place.payam, now: new Date() }) }));
  const warn = alerts.filter(x => x.a.level === 'warn').length, watch = alerts.filter(x => x.a.level === 'watch').length;
  const fresh = [s.autoPull?.state === 'ok' ? `data ${new Date(s.autoPull.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : '', `${checks.length} crop checks`, bulletin?.dataEnd ? `bulletin to ${bulletin.dataEnd}` : 'no bulletin yet'].filter(Boolean).join(' · ');

  const send = (l: Lead, text: string, level: string) => {
    openMessages(smsLink([l.phone], text));
    setSent(x => ({ ...x, [l.id]: true }));
    const stamp = new Date().toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    setState(st => ({ alertLog: [`${stamp} · opened Messages for ${l.name} (${level})`, ...st.alertLog].slice(0, 20) }));
    record('alert', { lang: l.lang ?? 'en', to: [l.id], text, level, days });
    setMsg('Messages opened. Press Send there; the text goes from this phone’s SIM. Then come back for the next lead.');
  };

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="body" style={{ fontSize: 13.5 }}>Each group lead gets their own text: the latest crop check on each of their plots, the basin water forecast, rain for the next 7 days and the county alert. It is sent from this phone’s Messages app, so it reaches any phone.</div>
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Look ahead for mound rows going under water</div>
        <Seg items={[[3, '3 days'], [5, '5 days'], [7, '7 days']]} value={days} onPick={setDays} />
      </div>
      <div style={{ borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)', padding: '10px 0', fontSize: 13.5 }}>
        {leads.length ? (warn ? `${warn} lead${warn > 1 ? 's' : ''} need a warning now${watch ? `, ${watch} to watch` : ''}.` : watch ? `${watch} lead${watch > 1 ? 's' : ''} to watch; no warning needed.` : 'All clear for every group; an update is optional.') : 'No recipients yet.'}
        <div className="sub" style={{ marginTop: 4 }}>{fresh}</div>
      </div>
      <div>
        <div className="between rule-b" style={{ paddingBottom: 4 }}><span className="kick sm">Group leads · {leads.length}</span>{isAdmin && <button className="link" style={{ padding: 0, fontSize: 12 }} onClick={() => setEditing(!editing)}>{editing ? 'Done' : 'Add or edit'}</button>}</div>
        {editing ? <LeadEditor onSaved={() => setEditing(false)} /> : <>
          {alerts.map(({ l, a }) => {
            const text = l.lang === 'ar' ? a.ar : a.en;
            return (
              <div key={l.id} style={{ borderBottom: '1px solid var(--color-divider)', padding: '10px 0' }}>
                <button className="between" style={{ width: '100%', textAlign: 'left', background: 'none', border: 0, padding: 0, alignItems: 'baseline' }} onClick={() => setOpen(open === l.id ? null : l.id)}>
                  <span><span style={{ display: 'block', fontSize: 14 }}>{l.name} · {a.group}</span><span className="sub num">{a.plots.length ? a.plots.map(p => p.code).join(' ') : 'no plots linked'} · {l.phone}</span></span>
                  <span className="it" style={{ fontSize: 12.5, color: a.level === 'clear' ? 'var(--color-neutral-600)' : 'var(--color-accent-800)', fontWeight: a.level === 'warn' ? 600 : 400 }}>{LEVEL_WORD[a.level]}{sent[l.id] ? ' · sent' : ''}</span>
                </button>
                {a.reasons.length > 0 && <div className="sub" style={{ marginTop: 4 }}>{a.reasons.join('; ')}</div>}
                {open === l.id && <div className="col g8" style={{ marginTop: 8 }}>
                  <div className="kick sm">SMS · {l.lang === 'ar' ? 'Arabic' : 'English'} · {text.length} characters{l.lang !== 'ar' ? ` · ${Math.ceil(text.length / 153)} SMS` : ''}</div>
                  <div dir={l.lang === 'ar' ? 'rtl' : undefined} className={l.lang === 'ar' ? '' : 'mono'} style={{ border: '1px solid var(--color-neutral-800)', borderRadius: 12, padding: 12, background: 'var(--color-neutral-100)', fontSize: 12.5, lineHeight: 1.5 }}>{text}</div>
                  {canSend && <button className="btn md" onClick={() => send(l, text, a.level)}>Send to {l.name.split(' ')[0]} from this phone</button>}
                </div>}
                {open !== l.id && canSend && <button className="link" style={{ padding: 0, fontSize: 12.5, marginTop: 4 }} onClick={() => setOpen(l.id)}>Preview and send</button>}
              </div>
            );
          })}
          {!leads.length && <div className="note" style={{ padding: '8px 0' }}>{!online ? 'Recipients load when the phone has signal.' : isAdmin ? 'No recipients yet. Tap “Add or edit” to add group leads and their phone numbers.' : 'No recipients yet. Ask an admin to add group leads.'}</div>}
        </>}
      </div>
      <div className="note">A lead is matched to a group by the group name or the group’s lead in the Farm register; their plots are that group’s plots. Plots with no crop check in two weeks say so. Have a native speaker check the Arabic wording.</div>
      {msg && <div className="msg">{msg}</div>}
      {!canSend && <div className="note">Only admins and group leads send alerts.</div>}
      {s.alertLog.map((x, i) => <div key={i} className="num" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{x}</div>)}
    </div>
  );
}

function LeadEditor({ onSaved }: { onSaved: () => void }) {
  const s = useApp();
  const [rows, setRows] = useState(s.leads.filter(l => /^\+211/.test(l.phone)).map(l => ({ id: l.id, name: l.name, group: l.group ?? '', rows: l.rows, phone: l.phone, lang: l.lang ?? 'en' })));
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (i: number, k: string, v: string) => setRows(r => r.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const save = async () => {
    setBusy(true); setErr('');
    try {
      const saved = await api<Lead[]>('/api/leads', { method: 'PUT', body: { leads: rows.map(r => ({ ...r, phone: r.phone.replace(/[\s-]/g, '').replace(/^0/, '+211') })) } });
      setState(st => ({ leads: saved.map(l => ({ ...l, on: st.leads.find(x => x.id === l.id)?.on ?? true })) }));
      onSaved();
    } catch (e) { setErr(explain(e)); }
    finally { setBusy(false); }
  };
  return (
    <div className="col g10" style={{ paddingTop: 8 }}>
      {rows.map((r, i) => (
        <div key={r.id} className="box col g8" style={{ padding: 10 }}>
          <div className="grid2"><Field label="Name"><input className="input" value={r.name} onChange={e => set(i, 'name', e.target.value)} /></Field><Field label="Group"><input className="input" value={r.group} onChange={e => set(i, 'group', e.target.value)} /></Field></div>
          <div className="grid2"><Field label="Phone"><input className="input num" type="tel" inputMode="tel" value={r.phone} placeholder="+211 9…" onChange={e => set(i, 'phone', e.target.value)} /></Field><Field label="Mound rows"><input className="input" value={r.rows} placeholder="B‑01–B‑08" onChange={e => set(i, 'rows', e.target.value)} /></Field></div>
          <div className="between" style={{ alignItems: 'center' }}><Seg items={[['en', 'English'], ['ar', 'Arabic']]} value={r.lang} onPick={v => set(i, 'lang', v)} fontSize={12} /><button className="btn plain sm" onClick={() => setRows(rs => rs.filter((_, j) => j !== i))}>Remove</button></div>
        </div>
      ))}
      <button className="btn plain" onClick={() => setRows(r => [...r, { id: newId('lead'), name: '', group: '', rows: '', phone: '+211', lang: 'en' }])}>+ Add recipient</button>
      {err && <div className="msg">{err}</div>}
      <button className="btn" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save recipients'}</button>
    </div>
  );
}

// ---- ii Gauge by SMS / USSD ----
const SEED_GAUGE: GaugeReading[] = [
  { from: 'Garang M.', text: 'G 4.12', at: '2026-10-28T06:58:00Z', v: 4.12, status: 'ok' }, { from: 'Garang M.', text: 'G 4.15', at: '2026-10-27T07:02:00Z', v: 4.15, status: 'ok' },
  { from: 'Bol M.', text: 'g4.18', at: '2026-10-26T18:10:00Z', v: 4.18, status: 'ok' }, { from: 'unknown', text: 'G 41.2', at: '2026-10-25T09:15:00Z', v: 41.2, status: 'held' }
];
const SEED_HIST = [4.36, 4.33, 4.31, 4.29, 4.27, 4.24, 4.22, 4.18, 4.15, 4.12];

export function Gauge() {
  const s = useApp(), online = useOnline();
  const [input, setInput] = useState('');
  const [msg, setMsg] = useState('');
  useEffect(() => { if (online) api<GaugeReading[]>('/api/gauge').then(g => setState({ gauge: g }), () => {}); }, [online]);
  const rows = s.gauge ?? SEED_GAUGE;
  const okVals = rows.filter(r => r.status === 'ok' && r.v !== null).map(r => r.v as number).reverse();
  const h = (s.gauge && okVals.length >= 2 ? okVals : SEED_HIST).slice(-10);
  const mn = Math.min(...h) - 0.05, mx = Math.max(...h) + 0.05;
  const pts = h.map((v, i) => ({ x: 10 + i * 33, y: Math.round(62 - (v - mn) / (mx - mn) * 54) }));
  const send = async () => {
    const t = input.trim();
    if (!t) return;
    setInput('');
    try {
      const r = await api<{ reading: GaugeReading; reply: string }>('/api/gauge/test', { body: { text: t } });
      setState(st => ({ gauge: [r.reading, ...(st.gauge ?? [])] })); setMsg(r.reading.status === 'ok' ? `Saved: ${r.reading.v?.toFixed(2)} m.` : r.reading.status === 'held' ? `Saved, but ${r.reading.v} m is far from the last reading, so an admin will check it.` : 'Not understood. Type G then the level, e.g. G 4.12');
    } catch (e) {
      // Offline: show what the server will decide, so volunteers can practise the format.
      const v = parseGauge(t, h[h.length - 1]);
      setMsg(`${explain(e)} Format check: ${v.kind === 'bad' ? 'not understood' : v.kind === 'held' ? 'would be held for the admin' : 'would be accepted'}.`);
    }
  };
  const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="box" style={{ padding: '10px 12px', fontSize: 13, lineHeight: 1.5 }}>Read the staff gauge at Bor, then type <span className="mono">G</span> and the level in metres, e.g. <span className="mono">G 4.12</span>. Volunteers without the app can text the reading to their group lead, who enters it here.</div>
      <div>
        <div className="between"><span className="kick sm">Bor gauge · last {h.length} readings</span><span className="head num" style={{ fontSize: 22 }}>{h[h.length - 1].toFixed(2)} m</span></div>
        <svg viewBox="0 0 320 70" width="100%" height="70" style={{ display: 'block', borderBottom: '1px solid var(--color-divider)' }}>
          <polyline points={pts.map(p => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--color-accent)" strokeWidth="1.6" />
          {pts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="2.5" fill={i === pts.length - 1 ? 'var(--color-accent)' : 'var(--color-bg)'} stroke="var(--color-accent)" />)}
        </svg>
      </div>
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Today's reading</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8 }}>
          <input className="input mono" style={{ minHeight: 42 }} placeholder="G 4.10" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
          <button className="btn md" style={{ padding: '0 14px' }} onClick={send}>Send</button>
        </div>
        {msg && <div className="msg">{msg}</div>}
      </div>
      <div>
        <div className="section">Readings{s.gauge ? '' : ' · sample until first sync'}</div>
        {rows.slice(0, 12).map((m, i) => (
          <div key={i} className="rowg">
            <span><span className="mono" style={{ display: 'block', fontSize: 13.5 }}>"{m.text}"</span><span className="sub">{m.from} · {when(m.at)}</span></span>
            <span className="it" style={{ fontSize: 12, textAlign: 'right', color: m.status === 'ok' ? 'var(--color-neutral-700)' : 'var(--color-accent-800)' }}>{m.status === 'bad' ? 'not understood' : m.status === 'ok' ? `accepted · ${m.v!.toFixed(2)} m` : 'held for admin'}</span>
          </div>
        ))}
      </div>
      <div className="note">Readings more than 30 cm from the last one are held for the admin to check before they feed the flood model. Satellite altimetry in station_status.csv is the cross-check.</div>
    </div>
  );
}

// ---- iii Pictures & voice ----
export function Voice() {
  const s = useApp();
  const [playing, setPlaying] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [have, setHave] = useState<Record<string, boolean>>({});
  const rec = useRef<MediaRecorder | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const cam = useRef<HTMLInputElement>(null);
  const [pics, setPics] = useState<Record<string, string>>({});
  // A lead can replace any tile's drawing with a photo of the real task on this farm.
  useEffect(() => {
    let urls: string[] = [];
    Promise.all(PICTO.map(async ([k]) => [k, await idbGet<Blob>(`picto-photo-${k}`).catch(() => undefined)] as const)).then(r => {
      const m: Record<string, string> = {};
      for (const [k, b] of r) if (b) { const u = URL.createObjectURL(b); urls.push(u); m[k] = u; }
      setPics(m);
    });
    return () => urls.forEach(URL.revokeObjectURL);
  }, []);
  const setPhoto = async (f: File) => {
    if (!playing) return;
    await idbSet(`picto-photo-${playing}`, f).catch(() => {});
    setPics(p => ({ ...p, [playing]: URL.createObjectURL(f) }));
  };
  const canLead = s.session?.user.role !== 'Extension worker';

  useEffect(() => { Promise.all(PICTO.map(async ([k]) => [k, !!(await idbGet(`prompt-${k}`).catch(() => null))] as const)).then(r => setHave(Object.fromEntries(r))); }, []);
  useEffect(() => () => { audio.current?.pause(); rec.current?.state === 'recording' && rec.current.stop(); }, []);

  const tap = async (k: string) => {
    audio.current?.pause();
    if (playing === k) {
      setPlaying(null);
      if (!s.doneP.includes(k)) { setState(st => ({ doneP: [...st.doneP, k] })); record('voice', { activity: k, group: s.session?.user.meta ?? '' }); }
      return;
    }
    setPlaying(k);
    const blob = await idbGet<Blob>(`prompt-${k}`).catch(() => undefined);
    if (blob) { audio.current = new Audio(URL.createObjectURL(blob)); audio.current.play().catch(() => {}); }
  };

  const toggleRec = async () => {
    if (!playing) return;
    if (recording) { rec.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [], r = new MediaRecorder(stream), key = playing;
      r.ondataavailable = e => chunks.push(e.data);
      r.onstop = async () => { stream.getTracks().forEach(t => t.stop()); await idbSet(`prompt-${key}`, new Blob(chunks, { type: r.mimeType })); setHave(h => ({ ...h, [key]: true })); setRecording(false); };
      rec.current = r; r.start(); setRecording(true);
    } catch { setRecording(false); }
  };

  const label = PICTO.find(p => p[0] === playing)?.[1];
  const status = recording ? `Recording "${label}"… tap Stop when done` : playing ? (have[playing] ? `Playing "${label}" in Thuɔŋjäŋ · tap again to mark done` : `No recording for "${label}" yet · tap again to mark done`) : s.doneP.length ? `${s.doneP.length} done today, saved for your group` : 'Nothing playing';
  const bar = (on: string, off = '4px') => (playing && have[playing] ? on : off);
  return (
    <div className="pad g12" style={{ padding: '14px 16px 24px' }}>
      <div style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--color-neutral-800)' }}>Tap a picture to hear it in Thuɔŋjäŋ. Tap again to record that you did it today.</div>
      <div className="grid2">
        {PICTO.map(([k, l, d]) => (
          <button key={k} onClick={() => tap(k)} style={{ height: 128, border: `1.5px solid ${playing === k ? 'var(--color-accent)' : 'var(--color-divider)'}`, borderRadius: 'var(--radius-lg)', background: s.doneP.includes(k) ? 'var(--color-accent-100)' : 'transparent', color: 'var(--color-accent-900)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, position: 'relative' }}>
            {pics[k] ? <img src={pics[k]} alt={l} style={{ width: 84, height: 70, objectFit: 'cover', borderRadius: 'var(--radius-md)' }} /> : <Icon d={d} size={52} sw={1.3} />}
            <span style={{ fontSize: 12, color: 'var(--color-neutral-800)' }}>{l}</span>
            <span style={{ position: 'absolute', top: 8, right: 10, fontSize: 13, color: 'var(--color-accent-800)' }}>{s.doneP.includes(k) ? '✓' : ''}</span>
          </button>
        ))}
      </div>
      <div style={{ minHeight: 44, display: 'flex', alignItems: 'center', gap: 10, borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)', padding: '8px 0' }}>
        <span style={{ display: 'flex', gap: 3, alignItems: 'flex-end', height: 20 }}>{[bar('18px'), bar('10px'), bar('20px'), bar('10px')].map((h, i) => <span key={i} style={{ width: 3, height: recording ? '14px' : h, background: 'var(--color-accent)' }} />)}</span>
        <span style={{ fontSize: 13, color: 'var(--color-neutral-800)', flex: 1 }}>{status}</span>
        {canLead && playing && <>
          <button className="btn plain sm" onClick={toggleRec}>{recording ? 'Stop' : have[playing] ? 'Re‑record' : 'Record'}</button>
          {!recording && <button className="btn plain sm" onClick={() => cam.current?.click()}>{pics[playing] ? 'New photo' : 'Photo'}</button>}
        </>}
        <input ref={cam} type="file" accept="image/*" capture="environment" hidden onChange={e => { const f = e.target.files?.[0]; if (f) setPhoto(f); e.target.value = ''; }} />
      </div>
      <div className="sub" style={{ lineHeight: 1.5 }}>Prompts are recorded once by a group lead in the local dialect and stored on the phone (about 40 KB each). Leads and admins can tap a tile, then Record or Photo, to replace its voice prompt or picture.</div>
    </div>
  );
}

// ---- iv Pest photo check ----
// Pest check: the worker identifies the pest from a short list for the crop and plant part, helped by
// the signs and first action from the pest library. Photos, plot, crop, GPS and time are saved with it;
// a name typed under "Other" is added to the crop in the Farm register so others can pick it next time.
// No automatic photo recognition yet: an extension worker confirms before treatment is advised.
export function Pest() {
  const place = usePlace();
  const s = useApp();
  const plots = s.farm.plots;
  const [plotId, setPlotId] = useState(plots[0]?.id ?? '');
  const plot = plots.find(p => p.id === plotId);
  const [crop, setCrop] = useState(plot?.crop ?? s.farm.crops[0]?.name ?? '');
  const [part, setPart] = useState<Part | ''>('');
  const [pest, setPest] = useState('');
  const [other, setOther] = useState('');
  const [share, setShare] = useState<'' | 'few' | 'some' | 'many'>('');
  const [photos, setPhotos] = useState<Blob[]>([]);
  const [done, setDone] = useState('');
  const [err, setErr] = useState('');
  const file = useRef<HTMLInputElement>(null);
  const urls = useMemo(() => photos.map(p => URL.createObjectURL(p)), [photos]);
  useEffect(() => () => urls.forEach(u => URL.revokeObjectURL(u)), [urls]);
  const me = s.session?.user.id ?? '';
  const cropRec = s.farm.crops.find(c => c.name === crop) ?? null;
  const opts = pestOptions(crop, part, cropRec);
  const name = pest === '__other' ? other.trim() : pest;
  const info = pest && pest !== '__other' && pest !== '__unsure' ? pestInfo(pest) : null;
  const pickPlot = (id: string) => { setPlotId(id); const p = plots.find(x => x.id === id); if (p?.crop) setCrop(p.crop); setPest(''); };

  const save = async () => {
    if (!photos.length) return setErr('Take at least one photo of the damage.');
    if (!part) return setErr('Choose the part of the plant.');
    if (!pest || (pest === '__other' && !name)) return setErr('Choose the pest, “Not sure”, or type its name under Other.');
    if (!share) return setErr('Choose how many plants are affected.');
    setErr('');
    const fix = await oneFix(8000).catch(() => null);
    const keys = await Promise.all(photos.map(b => savePhoto(b, 'pest')));
    const unsure = pest === '__unsure';
    record('pest', { plot: plot?.code ?? '', plotId, crop, part, pest: unsure ? '' : name, unsure, affected: share, photos: keys, by: me, at: new Date().toISOString(), gps: fix && { lat: fix.lat, lon: fix.lon, acc: fix.acc }, place: { payam: place.payam, county: place.county, state: place.state }, suggested: info ? info.action : '' });
    if (pest === '__other' && cropRec && !(cropRec.pests ?? []).some(n => n.toLowerCase() === name.toLowerCase()))
      farmChange({ op: 'upsert', kind: 'crop', item: { ...cropRec, pests: [...(cropRec.pests ?? []), name] } });
    setDone(unsure ? 'Saved with photos as “not sure”. The extension worker will look at it and reply.' : `Saved: ${name} on ${crop} (${PARTS.find(p => p[0] === part)?.[1].toLowerCase()}), plot ${plot?.code ?? ''}. The extension worker confirms before treatment.`);
    setPhotos([]); setPest(''); setOther(''); setShare(''); setPart('');
  };

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="grid2">
        <Field label="Plot"><select className="input" value={plotId} onChange={e => pickPlot(e.target.value)}>{plots.map(p => <option key={p.id} value={p.id}>{plotLabel(p, s.farm)}</option>)}</select></Field>
        <Field label="Crop"><select className="input" value={crop} onChange={e => { setCrop(e.target.value); setPest(''); }}>{s.farm.crops.map(c => <option key={c.id}>{c.name}</option>)}</select></Field>
      </div>
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Part of the plant</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{PARTS.map(([k, l]) => <button key={k} className={'chip' + (part === k ? ' on' : '')} style={{ minHeight: 36, padding: '0 10px', fontSize: 12.5 }} onClick={() => { setPart(k); setPest(''); }}>{l}</button>)}</div>
      </div>
      <div className="col g6">
        <div className="between"><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Photos of the damage (close-up, then the whole plant)</span><span className="num" style={{ fontSize: 12.5 }}>{photos.length}</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 6 }}>
          {urls.map((u, i) => <div key={u} style={{ position: 'relative' }}><img src={u} alt={`Pest photo ${i + 1}`} style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', borderRadius: 8 }} /><button aria-label={`Remove photo ${i + 1}`} onClick={() => setPhotos(p => p.filter((_, j) => j !== i))} style={{ position: 'absolute', top: 4, right: 4, width: 24, height: 24, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,.55)', color: '#fff', fontSize: 14, lineHeight: '24px', padding: 0 }}>×</button></div>)}
          <button className="photo" style={{ aspectRatio: '1', minHeight: 0 }} onClick={() => file.current?.click()}>+ Photo</button>
        </div>
        <input ref={file} type="file" accept="image/*" capture="environment" hidden onChange={e => { const f = e.target.files?.[0]; if (f) { setPhotos(p => [...p, f]); setDone(''); } e.target.value = ''; }} />
      </div>
      <Field label={`Pest or disease${part ? '' : ' (choose the plant part first to narrow the list)'}`}>
        <select className="input" value={pest} onChange={e => setPest(e.target.value)}>
          <option value="">Choose…</option>
          {opts.map(o => <option key={o.name} value={o.name}>{o.name}{o.info ? ` · ${o.info.type}` : ' · added by workers'}</option>)}
          <option value="__unsure">Not sure (send photos for an opinion)</option>
          <option value="__other">Other (type the name)</option>
        </select>
      </Field>
      {pest === '__other' && <Field label="Name you know it by"><input className="input" value={other} onChange={e => setOther(e.target.value)} placeholder="Local or English name" /></Field>}
      {info && <div className="card accent" style={{ gap: 6 }}>
        <div className="kick sm">Check it matches · {info.type}</div>
        <div style={{ fontSize: 13.5, lineHeight: 1.45 }}><b>Look for:</b> {info.signs}</div>
        <div style={{ fontSize: 13.5, lineHeight: 1.45 }}><b>First action (suggested):</b> {info.action}</div>
      </div>}
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Plants affected in the plot</div>
        <Seg items={[['few', 'Under 10%'], ['some', '10–30%'], ['many', 'Over 30%']]} value={share} onPick={v => setShare(v as typeof share)} fontSize={12.5} />
      </div>
      {err && <div className="msg">{err}</div>}
      <button className="btn lg" onClick={save}>Save pest check</button>
      {done && <div className="it" style={{ fontSize: 13, color: 'var(--color-accent-800)' }}>{done}</div>}
      <div className="sub" style={{ lineHeight: 1.5 }}>GPS, time, payam ({place.payam}) and your ID are added when you save. The list shows pests common on {crop || 'this crop'}{part ? ` for this plant part` : ''} in South Sudan, then general ones, then names other workers have added. Photos are not yet recognised automatically; an extension worker confirms before treatment.</div>
    </div>
  );
}

// ---- v Work days & payout ----
export function Payout() {
  const s = useApp();
  const can = editAllowed(s.session?.user.role ?? '');
  const groups = s.farm.groups.filter(g => g.members.length || can);
  const [gid, setGid] = useState(groups.find(g => g.id === 'g4')?.id ?? groups[0]?.id ?? '');
  const g = s.farm.groups.find(x => x.id === gid);
  const [absent, setAbsent] = useState<string[]>([]);
  const [sale, setSale] = useState({ buyer: 'Nile Botanicals (40 L oil)', amount: '540', fund: '15' });
  const [who, setWho] = useState('');
  const [msg, setMsg] = useState('');
  const members = g?.members ?? [];
  const present = (id: string) => !absent.includes(id);
  const days = members.map(m => m.workDays + (present(m.id) ? 1 : 0)), tot = days.reduce((a, b) => a + b, 0) || 1;
  const amount = Number(sale.amount) || 0, fund = Math.round(amount * (Number(sale.fund) || 0)) / 100, pool = amount - fund;
  const share = (i: number) => pool * days[i] / tot;
  const addMember = () => {
    if (!g || !who.trim()) return;
    farmChange({ op: 'upsert', kind: 'group', item: { ...g, members: [...g.members, { id: newId('m'), name: who.trim(), workDays: 0 }] } });
    setWho('');
  };
  const approve = () => {
    if (!g) return;
    if (!(amount > 0)) return setMsg('Enter the sale amount.');
    const here = members.filter(m => present(m.id)).map(m => m.id);
    if (can) farmChange({ op: 'workdays', groupId: g.id, memberIds: here });
    record('payout', { group: g.name, sale: sale.buyer, amount, fundPct: Number(sale.fund) || 0, pool, shares: members.map((m, i) => ({ id: m.id, name: m.name, days: days[i], usd: Math.round(share(i) * 100) / 100 })) });
    setMsg(`Approved. Today's roll-call is added to work days, and the mobile‑money list goes to the project office at the next sync.`);
    setAbsent([]);
  };
  const date = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <Field label="Group"><select className="input" value={gid} onChange={e => { setGid(e.target.value); setAbsent([]); setMsg(''); }}>{s.farm.groups.map(x => <option key={x.id} value={x.id}>{x.name} · {x.members.length} members</option>)}</select></Field>
      <div className="between"><div><div className="kick">{g?.name ?? '—'} · roll‑call {date}</div><div className="head" style={{ fontSize: 24 }}>{members.length - absent.filter(a => members.some(m => m.id === a)).length} of {members.length} present</div></div><button className="btn plain sm" onClick={() => setAbsent([])}>All present</button></div>
      <div>
        <div style={{ display: 'grid', gridTemplateColumns: '28px 1fr 52px 64px', gap: 8 }} className="lbl rule-b"><span /><span>Member</span><span style={{ textAlign: 'right' }}>Days</span><span style={{ textAlign: 'right' }}>Share</span></div>
        {members.map((m, i) => (
          <button key={m.id} className="row" onClick={() => setAbsent(a => (a.includes(m.id) ? a.filter(x => x !== m.id) : [...a, m.id]))} style={{ display: 'grid', gridTemplateColumns: '28px 1fr 52px 64px', gap: 8, alignItems: 'center', padding: '8px 0', fontSize: 13.5, minHeight: 40 }}>
            <Check on={present(m.id)} /><span>{m.name}</span><span className="num" style={{ textAlign: 'right' }}>{days[i]}</span><span className="head num" style={{ textAlign: 'right', fontSize: 17 }}>${share(i).toFixed(2)}</span>
          </button>
        ))}
        {!members.length && <div className="note" style={{ padding: '8px 0' }}>No members in this group yet.</div>}
        {can && g && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, marginTop: 8 }}>
            <input className="input" style={{ minHeight: 40 }} value={who} placeholder="Add a member to this group" onChange={e => setWho(e.target.value)} onKeyDown={e => e.key === 'Enter' && addMember()} />
            <button className="btn md" style={{ padding: '0 12px' }} onClick={addMember}>Add</button>
          </div>
        )}
      </div>
      <div className="box col g8" style={{ padding: 12 }}>
        <div className="section">Sale to share</div>
        <Field label="Buyer / what was sold"><input className="input" value={sale.buyer} onChange={e => setSale({ ...sale, buyer: e.target.value })} /></Field>
        <div className="grid2">
          <Field label="Amount ($)"><input className="input num" type="number" inputMode="decimal" value={sale.amount} onChange={e => { setSale({ ...sale, amount: e.target.value }); setMsg(''); }} /></Field>
          <Field label="Cooperative fund %"><input className="input num" type="number" inputMode="decimal" value={sale.fund} onChange={e => setSale({ ...sale, fund: e.target.value })} /></Field>
        </div>
        <div className="num" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '4px 10px', fontSize: 13 }}>
          <span>{sale.buyer || 'Sale'}</span><span style={{ textAlign: 'right' }}>${amount.toFixed(2)}</span>
          <span style={{ color: 'var(--color-neutral-700)' }}>Cooperative fund {Number(sale.fund) || 0}%</span><span style={{ textAlign: 'right', color: 'var(--color-neutral-700)' }}>− ${fund.toFixed(2)}</span>
          <span style={{ fontWeight: 600 }}>Shared by work days</span><span style={{ textAlign: 'right', fontWeight: 600 }}>${pool.toFixed(2)}</span>
        </div>
      </div>
      {msg && <div className="msg">{msg}</div>}
      <button className="btn" onClick={approve} disabled={!members.length}>Approve & send mobile‑money list</button>
    </div>
  );
}

// ---- vi Seed & input store ----
export { Store } from './Store';

// ---- vii Traceable bottles ----
export function Trace() {
  const s = useApp();
  const batches = [...s.farm.batches].sort((x, y) => y.pressed.localeCompare(x.pressed)); // newest first
  const [i, setI] = useState(0);
  const b = batches[Math.min(i, batches.length - 1)];
  const can = editAllowed(s.session?.user.role ?? '');
  if (!b) return (
    <div className="pad"><p className="body">No product batches yet.</p>{can && <button className="btn" onClick={() => openRegister('batches')}>+ Add a product batch</button>}</div>
  );
  const plot = s.farm.plots.find(p => p.id === b.plotId);
  const group = plot && s.farm.groups.find(g => g.id === plot.groupId);
  const gps = b.lat != null && b.lon != null ? `${b.lat.toFixed(4)}° N ${b.lon.toFixed(4)}° E` : plot?.boundary[0] ? `${plot.boundary[0].lat.toFixed(4)}° N ${plot.boundary[0].lon.toFixed(4)}° E` : '';
  const product = b.product ?? 'Balanites oil', unit = b.unit ?? '1 L bottle';
  const run = b.runId ? s.farm.runs.find(r => r.id === b.runId) : null;
  const members = s.farm.groups.reduce((n, g) => n + g.members.length, 0);
  const rows: [string, string][] = ([
    ['Product', `${product}${b.crop ? ` · from ${b.crop}` : ''}`], ['Plot', `${plot?.code ?? '—'} · ${group ? `${group.name} (${group.members.length} farmers)` : plot?.holder || 'individual'}`],
    ['GPS', gps], ['Harvested', b.fruit], ['Processed', run ? `${run.date}: ${run.steps.filter(x => x.out).map(x => x.name).join(' → ')}` : ''], ['Packed', `${b.pressed}${b.packedBy ? ` by ${b.packedBy}` : ''}`],
    ['Batch size', `${b.bottles} × ${unit}`], ['Quality', b.quality ?? ''], ['Origin', b.place], ['Cooperative', `Abuk Project${members ? `, ${members} farmers` : ''}`]
  ] as [string, string][]).filter(([, v]) => v);
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <Field label="Batch"><select className="input mono" value={Math.min(i, batches.length - 1)} onChange={e => setI(Number(e.target.value))}>{batches.map((x, j) => <option key={x.id} value={j}>{x.code} · {x.product ?? 'Balanites oil'} · {x.bottles}</option>)}</select></Field>
      <div className="box" style={{ display: 'grid', gridTemplateColumns: '128px 1fr', gap: 14, alignItems: 'center', padding: 12 }}>
        <svg viewBox="0 0 25 25" width="128" height="128" style={{ display: 'block', background: 'var(--color-neutral-100)' }}>{qrCells(b.code).map(c => <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width="1" height="1" fill="var(--color-text)" />)}</svg>
        <div className="col" style={{ gap: 3 }}>
          <div className="kick sm">Bottle label</div>
          <div className="head" style={{ fontSize: 20, lineHeight: 1.1 }}>{product}, {unit}</div>
          <div className="num" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Batch {b.code}</div>
          <div className="it" style={{ fontSize: 10.5, color: 'var(--color-neutral-600)' }}>placeholder QR pattern</div>
        </div>
      </div>
      <div>
        <div className="section">What the buyer sees on scan</div>
        {rows.map(([k, v]) => <div key={k} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--color-divider)', fontSize: 13.5 }}><span style={{ color: 'var(--color-neutral-700)' }}>{k}</span><span>{v}</span></div>)}
      </div>
      <button className="btn" onClick={() => window.print()}>Print labels for this batch</button>
      {can && <button className="btn plain" onClick={() => openRegister('batches')}>+ Add or edit product batches</button>}
    </div>
  );
}

// ---- viii Phone-to-phone sync ----
export function P2p() {
  const s = useApp();
  const [msg, setMsg] = useState('');
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="body" style={{ fontSize: 13.5 }}>Swap records with nearby group‑lead phones over Bluetooth. Whoever reaches signal first uploads everyone's.</div>
      <div className="grid2" style={{ gap: 0, borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)' }}>
        <div style={{ padding: '10px 0' }}><div className="lbl">On this phone</div><div className="head num" style={{ fontSize: 26 }}>{s.outbox.length}</div><div style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}>records to upload</div></div>
        <div style={{ padding: '10px 0 10px 12px', borderLeft: '1px solid var(--color-divider)' }}><div className="lbl">From phones</div><div className="head num" style={{ fontSize: 26 }}>0</div><div style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}>swapped today</div></div>
      </div>
      <div>
        <div className="section">Nearby · Bluetooth · example list in the web version</div>
        {P2P_PEERS.map(([name, dist, recs]) => (
          <div key={name} className="rowg" style={{ padding: '10px 0', alignItems: 'center' }}>
            <span><span style={{ display: 'block', fontSize: 14 }}>{name}</span><span className="sub">{dist} · {recs} new records</span></span>
            <button className="btn" style={{ minHeight: 38, minWidth: 84, padding: '0 10px', fontSize: 12.5 }} onClick={() => setMsg('Bluetooth swaps need the Android app. This web version cannot reach nearby phones; it uploads its own records when it has signal.')}>Swap</button>
          </div>
        ))}
      </div>
      {msg && <div className="msg">{msg}</div>}
      <div className="sub" style={{ lineHeight: 1.5 }}>Records are signed with each worker's key and encrypted in transit, so a carrier phone can pass them on but not change them.</div>
    </div>
  );
}
