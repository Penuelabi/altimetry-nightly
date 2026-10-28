import { useEffect, useRef, useState } from 'react';
import { get as idbGet, set as idbSet } from 'idb-keyval';
import { P2P_PEERS, PICTO, STORE, TOOLS, editAllowed, newId, parseGauge, qrCells, type GaugeReading } from '@abuk/core';
import { farmChange, go, openRegister, record, setState, useApp, type Lead } from '../store';
import { api, explain } from '../api';
import { useOnline, usePlace } from '../net';
import { Check, Chevron, Field, Icon, Seg, Toggle } from '../ui';

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
// Sent from the phone's own Messages app: the app fills in the numbers and the text,
// the person presses Send, and the SMS goes from their SIM like any other text.
const ALERT_TEXT = {
  en: (rise: boolean, days: number) => rise
    ? 'ABUK FLOOD: water to top rows B-03 B-04 B-05 B-08 in ~4 days. Lift seed & tools to ridge. Check mounds. Reply 1=OK. -Abuk Project'
    : `ABUK: no flood risk to mound rows next ${days} days. Basin falling 2-3 cm/day. Sowing opens ~4 Dec. -Abuk Project`,
  ar: (rise: boolean, days: number) => rise
    ? 'أبوك - فيضان: سيصل الماء إلى قمم صفوف B-03 B-04 B-05 B-08 خلال 4 أيام تقريباً. انقلوا البذور والأدوات إلى المرتفع وافحصوا التلال. ردّوا 1 للتأكيد. -مشروع أبوك'
    : `أبوك: لا خطر فيضان على صفوف التلال خلال ${days} أيام. منسوب الحوض ينخفض 2-3 سم يومياً. تبدأ الزراعة نحو 4 ديسمبر. -مشروع أبوك`
};

// sms: link understood by Android Messages; recipients separated by commas.
const smsLink = (numbers: string[], body: string) => `sms:${numbers.join(',')}?body=${encodeURIComponent(body)}`;
const openMessages = (href: string) => { const a = document.createElement('a'); a.href = href; a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove(); };

export function Alerts() {
  const s = useApp(), online = useOnline();
  const role = s.session?.user.role ?? '';
  const canSend = role === 'Admin' || role === 'Group lead', isAdmin = role === 'Admin';
  const [days, setDays] = useState(5);
  const [rise, setRise] = useState(false);
  const [msg, setMsg] = useState('');
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    if (!online) return;
    api<{ id: string; name: string; group: string; rows: string; phone: string; lang: 'en' | 'ar' }[]>(`/api/leads${canSend ? '?full=1' : ''}`)
      .then(ls => setState(st => ({ leads: ls.map(l => ({ ...l, on: st.leads.find(x => x.id === l.id)?.on ?? true })) })), () => {});
  }, [online, canSend]);
  const leads = s.leads.filter(l => /^\+211\d{9}$/.test(l.phone));
  const chosen = leads.filter(l => l.on);
  const en = chosen.filter(l => l.lang !== 'ar'), ar = chosen.filter(l => l.lang === 'ar');
  const textEn = ALERT_TEXT.en(rise, days), textAr = ALERT_TEXT.ar(rise, days);

  const send = (lang: 'en' | 'ar') => {
    const to = lang === 'ar' ? ar : en, text = lang === 'ar' ? textAr : textEn;
    if (!to.length) return;
    openMessages(smsLink(to.map(l => l.phone), text));
    const stamp = new Date().toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    setState(st => ({ alertLog: [`${stamp} · opened Messages for ${to.length} lead${to.length > 1 ? 's' : ''} (${lang === 'ar' ? 'Arabic' : 'English'})`, ...st.alertLog].slice(0, 20) }));
    record('alert', { lang, to: to.map(l => l.id), text, scenario: rise ? 'rise' : 'falling', days });
    setMsg('Messages opened. Check the recipients and press Send there; the text goes from this phone’s SIM.');
  };

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="body" style={{ fontSize: 13.5 }}>Text group leads when the flood model forecasts a mound crest will be overtopped. The message is sent from this phone through its Messages app, so it reaches any phone, no app or data needed.</div>
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Warn when overtopping is forecast within</div>
        <Seg items={[[3, '3 days'], [5, '5 days'], [7, '7 days']]} value={days} onPick={setDays} />
      </div>
      <button className="btn plain between" style={{ minHeight: 44, padding: '0 12px', fontSize: 13, alignItems: 'center', display: 'flex' }} onClick={() => setRise(!rise)}><span>Scenario: river rises 8 cm</span><span className="it" style={{ color: 'var(--color-accent-800)' }}>{rise ? 'on' : 'off'}</span></button>
      <div style={{ borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)', padding: '10px 0', fontSize: 13.5 }}>
        {rise ? `Forecast: B‑03, B‑04, B‑05, B‑08 overtopped in ~${Math.min(days, 4)} days. Send the alert now.` : `Water is falling. No crest at risk in the next ${days} days; an all-clear message is optional.`}
      </div>
      <div>
        <div className="kick sm" style={{ marginBottom: 6 }}>SMS · English · {textEn.length} characters</div>
        <div className="mono" style={{ border: '1px solid var(--color-neutral-800)', borderRadius: 12, padding: 12, background: 'var(--color-neutral-100)', fontSize: 12.5, lineHeight: 1.5 }}>{textEn}</div>
        <div className="kick sm" style={{ margin: '10px 0 6px' }}>SMS · Arabic (for leads who chose Arabic)</div>
        <div dir="rtl" style={{ border: '1px solid var(--color-neutral-800)', borderRadius: 12, padding: 12, background: 'var(--color-neutral-100)', fontSize: 13.5, lineHeight: 1.6 }}>{textAr}</div>
        <div style={{ fontSize: 11, color: 'var(--color-neutral-700)', marginTop: 4 }}>Arabic texts are longer and may go as 2–3 SMS. Have a native speaker check the Arabic wording before the season.</div>
      </div>
      <div>
        <div className="between rule-b" style={{ paddingBottom: 4 }}><span className="kick sm">Recipients · {chosen.length} of {leads.length} selected</span>{isAdmin && <button className="link" style={{ padding: 0, fontSize: 12 }} onClick={() => setEditing(!editing)}>{editing ? 'Done' : 'Add or edit'}</button>}</div>
        {editing ? <LeadEditor onSaved={() => setEditing(false)} /> : <>
          {leads.map(l => (
            <div key={l.id} className="rowg" style={{ alignItems: 'center' }}>
              <span><span style={{ display: 'block', fontSize: 14 }}>{l.name}{l.group ? ` · ${l.group}` : ''}</span><span className="sub num">{l.rows ? `${l.rows} · ` : ''}{l.phone} · {l.lang === 'ar' ? 'Arabic' : 'English'}</span></span>
              <Toggle on={l.on} label={`Send to ${l.name}`} onClick={() => setState(st => ({ leads: st.leads.map(x => x.id === l.id ? { ...x, on: !x.on } : x) }))} />
            </div>
          ))}
          {!leads.length && <div className="note" style={{ padding: '8px 0' }}>{!online ? 'Recipients load when the phone has signal.' : isAdmin ? 'No recipients yet. Tap “Add or edit” to add group leads and their phone numbers.' : 'No recipients yet. Ask an admin to add group leads.'}</div>}
        </>}
      </div>
      {msg && <div className="msg">{msg}</div>}
      {canSend ? <>
        <button className="btn lg" disabled={!en.length} onClick={() => send('en')}>Send from this phone · English ({en.length})</button>
        {ar.length > 0 && <button className="btn" onClick={() => send('ar')}>Send Arabic copy ({ar.length})</button>}
      </> : <div className="note">Only admins and group leads send alerts.</div>}
      {s.alertLog.map((a, i) => <div key={i} className="num" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{a}</div>)}
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
export function Pest() {
  const place = usePlace();
  const s = useApp();
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [plot, setPlot] = useState(s.farm.plots[0]?.code ?? '');
  const [st, setSt] = useState<'idle' | 'busy' | 'done'>('idle');
  const [answered, setAnswered] = useState('');
  const file = useRef<HTMLInputElement>(null);
  const url = photo ? URL.createObjectURL(photo) : '';
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const me = s.session?.user.id ?? 'EW‑014';
  useEffect(() => { if (st !== 'busy') return; const t = setTimeout(() => setSt('done'), 1400); return () => clearTimeout(t); }, [st]);
  const answer = async (ok: boolean) => {
    const key = photo ? `pest-${Date.now()}` : null;
    if (key && photo) await idbSet(key, photo).catch(() => {});
    record('pest', { plot, photo: key, suggestion: 'Fall armyworm', confirmed: ok, by: me, place });
    setAnswered(ok ? `Confirmed by ${me}. Recorded for plot ${plot}; treat within 3 days and scout neighbouring plots.` : 'Sent to the county extension office with the photo for a second opinion.');
  };
  const reset = () => { setPhoto(null); setSt('idle'); setAnswered(''); };
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <button onClick={() => file.current?.click()} className="photo" style={{ height: 190, padding: 0, overflow: 'hidden', cursor: 'pointer', width: '100%' }}>
        {url ? <img src={url} alt="Crop photo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <span>Tap to take a photo of the damaged leaf or plant</span>}
      </button>
      <input ref={file} type="file" accept="image/*" capture="environment" hidden onChange={e => { const f = e.target.files?.[0]; if (f) { setPhoto(f); setSt('idle'); setAnswered(''); } e.target.value = ''; }} />
      <div className="grid2">
        <Field label="Plot"><select className="input" value={plot} onChange={e => setPlot(e.target.value)}>{s.farm.plots.map(p => <option key={p.id}>{p.code}</option>)}</select></Field>
        <button className="btn plain" style={{ alignSelf: 'end' }} onClick={() => file.current?.click()}>{photo ? 'Retake photo' : 'Take photo'}</button>
      </div>
      {photo && st === 'idle' && <button className="btn lg" onClick={() => setSt('busy')}>Compare with local library</button>}
      {st === 'busy' && <div className="it" style={{ fontSize: 13.5, color: 'var(--color-accent-800)' }}>Comparing with reference photos from {place.state || 'South Sudan'}…</div>}
      {st === 'done' && (
        <div className="col g12">
          <div>
            <div className="section">Closest matches · example results</div>
            {([['Fall armyworm', 78], ['Stem borer', 12], ['Leaf blight', 6]] as const).map(([n, p]) => (
              <div key={n} style={{ display: 'grid', gridTemplateColumns: '1fr 90px 40px', gap: 8, alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--color-divider)' }}>
                <span style={{ fontSize: 14 }}>{n}</span>
                <span style={{ height: 8, border: '1px solid var(--color-accent)', borderRadius: 2, position: 'relative' }}><span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: p + '%', background: 'var(--color-accent-300)' }} /></span>
                <span className="num" style={{ fontSize: 13, textAlign: 'right' }}>{p}%</span>
              </div>
            ))}
          </div>
          <div className="card accent" style={{ gap: 4 }}>
            <div className="kick sm">Suggested, needs confirmation</div>
            <div style={{ fontSize: 14, lineHeight: 1.45 }}>Fall armyworm. Hand‑pick egg masses and larvae at dawn; spray neem‑seed extract into leaf whorls within 3 days; check 20 plants per plot again in a week.</div>
          </div>
          {!answered ? (
            <div className="grid2" style={{ gap: 8 }}>
              <button className="btn plain" style={{ minHeight: 44, fontSize: 13.5 }} onClick={() => answer(false)}>Not this</button>
              <button className="btn" style={{ minHeight: 44, fontSize: 13.5 }} onClick={() => answer(true)}>Confirm ({me})</button>
            </div>
          ) : <>
            <div className="it" style={{ fontSize: 13, color: 'var(--color-accent-800)', borderTop: '1px solid var(--color-divider)', paddingTop: 8 }}>{answered}</div>
            <button className="btn plain" onClick={reset}>Check another photo</button>
          </>}
        </div>
      )}
      <div className="sub" style={{ lineHeight: 1.5 }}>Your photo and decision are saved and synced. The matches shown are examples until a reference photo library for {place.state || 'the area'} is loaded; an extension worker always confirms before any treatment is advised.</div>
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
export function Store() {
  const s = useApp();
  const [msg, setMsg] = useState('');
  const short = STORE.filter((x, i) => s.stock[i] < x[3]);
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <div className="body" style={{ fontSize: 13.5 }}>Stock in the Abuk store, reserved against the next planting windows from the flood model.</div>
      <div style={{ borderTop: '1px solid var(--color-divider)' }}>
        {STORE.map(([name, unit, , need, use, step], i) => {
          const have = s.stock[i], low = have < need;
          return (
            <div key={name} className="col g6" style={{ padding: '10px 0', borderBottom: '1px solid var(--color-divider)', gap: 5 }}>
              <div className="between"><span style={{ fontSize: 14 }}>{name}</span><span className="head num" style={{ fontSize: 19 }}>{have.toLocaleString('en')} {unit}</span></div>
              <div style={{ position: 'relative', height: 7, border: '1px solid var(--color-divider)', borderRadius: 2 }}><span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: Math.min(100, have / need * 100) + '%', background: low ? 'var(--color-accent-300)' : 'var(--color-neutral-400)' }} /></div>
              <div className="between" style={{ alignItems: 'center' }}>
                <span style={{ fontSize: 11.5, color: low ? 'var(--color-accent-800)' : 'var(--color-neutral-700)' }}>{low ? `short ${(need - have).toLocaleString('en')} ${unit} · ${use}` : `${need.toLocaleString('en')} ${unit} reserved · ${use}`}</span>
                <button className="btn plain" style={{ minHeight: 30, padding: '0 9px', fontSize: 11.5, flex: 'none' }} onClick={() => {
                  setState(st => ({ stock: st.stock.map((q, j) => (j === i ? Math.max(0, q - step) : q)) }));
                  record('store', { item: name, issued: step, unit, to: 'Group 4' });
                  setMsg(`Issued ${step} ${unit} ${name.toLowerCase()} to Group 4.`);
                }}>Issue {step} {unit}</button>
              </div>
            </div>
          );
        })}
      </div>
      {msg && <div className="msg">{msg}</div>}
      <button className="btn" onClick={() => { record('store', { request: short.map(x => x[0]) }); setMsg('Request queued for the project office: ' + short.map(x => x[0].toLowerCase()).join(', ') + '.'); }}>Request {short.length} short items</button>
    </div>
  );
}

// ---- vii Traceable bottles ----
export function Trace() {
  const s = useApp();
  const batches = [...s.farm.batches].sort((x, y) => y.pressed.localeCompare(x.pressed)); // newest first
  const [i, setI] = useState(0);
  const b = batches[Math.min(i, batches.length - 1)];
  const can = editAllowed(s.session?.user.role ?? '');
  if (!b) return (
    <div className="pad"><p className="body">No bottle batches yet.</p>{can && <button className="btn" onClick={() => openRegister('batches')}>+ Add a bottle batch</button>}</div>
  );
  const plot = s.farm.plots.find(p => p.id === b.plotId);
  const group = plot && s.farm.groups.find(g => g.id === plot.groupId);
  const origin = plot?.boundary[0] ? `${plot.boundary[0].lat.toFixed(2)}° N ${plot.boundary[0].lon.toFixed(2)}° E` : b.place;
  const rows: [string, string][] = [['Plot', `${plot?.code ?? '—'} · ${group ? `${group.name} (${group.members.length} farmers)` : plot?.holder || 'individual'}`], ['Fruit collected', b.fruit || '—'], ['Pressed', b.pressed], ['Batch size', `${b.bottles} × 1 L`], ['Origin', origin || '—'], ['Cooperative', 'Abuk Project, 160 farmers']];
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <Field label="Batch"><select className="input mono" value={Math.min(i, batches.length - 1)} onChange={e => setI(Number(e.target.value))}>{batches.map((x, j) => <option key={x.id} value={j}>{x.code} · {x.bottles} bottles</option>)}</select></Field>
      <div className="box" style={{ display: 'grid', gridTemplateColumns: '128px 1fr', gap: 14, alignItems: 'center', padding: 12 }}>
        <svg viewBox="0 0 25 25" width="128" height="128" style={{ display: 'block', background: 'var(--color-neutral-100)' }}>{qrCells(b.code).map(c => <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width="1" height="1" fill="var(--color-text)" />)}</svg>
        <div className="col" style={{ gap: 3 }}>
          <div className="kick sm">Bottle label</div>
          <div className="head" style={{ fontSize: 20, lineHeight: 1.1 }}>Desert date oil, 1 L</div>
          <div className="num" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Batch {b.code}</div>
          <div className="it" style={{ fontSize: 10.5, color: 'var(--color-neutral-600)' }}>placeholder QR pattern</div>
        </div>
      </div>
      <div>
        <div className="section">What the buyer sees on scan</div>
        {rows.map(([k, v]) => <div key={k} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--color-divider)', fontSize: 13.5 }}><span style={{ color: 'var(--color-neutral-700)' }}>{k}</span><span>{v}</span></div>)}
      </div>
      <button className="btn" onClick={() => window.print()}>Print labels for this batch</button>
      {can && <button className="btn plain" onClick={() => openRegister('batches')}>+ Add or edit bottle batches</button>}
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
