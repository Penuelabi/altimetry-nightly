import { useEffect, useRef, useState } from 'react';
import { get as idbGet, set as idbSet } from 'idb-keyval';
import { BATCHES, MEMBERS, P2P_PEERS, PICTO, STORE, TOOLS, parseGauge, qrCells, type GaugeReading } from '@abuk/core';
import { go, record, setState, useApp, type Lead } from '../store';
import { api, explain } from '../api';
import { useOnline } from '../net';
import { Check, Chevron, Icon, Seg, Toggle } from '../ui';

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
export function Alerts() {
  const s = useApp(), online = useOnline();
  const [days, setDays] = useState(5);
  const [rise, setRise] = useState(false);
  const [msg, setMsg] = useState('');
  useEffect(() => {
    if (online) api<{ id: string; name: string; group: string; rows: string; phone: string }[]>('/api/leads')
      .then(ls => ls.length && setState(st => ({ leads: ls.map(l => ({ id: l.id, name: `${l.name} · ${l.group}`, rows: l.rows, phone: l.phone, on: st.leads.find(x => x.id === l.id)?.on ?? true })) })), () => {});
  }, [online]);
  const sms = rise ? 'ABUK FLOOD: water to top rows B-03 B-04 B-05 B-08 in ~4 days. Lift seed & tools to ridge. Check mounds. Reply 1=OK. -Abuk Project'
    : `ABUK: no flood risk to mound rows next ${days} days. Basin falling 2-3 cm/day. Sowing opens ~4 Dec. -Abuk Project`;
  const send = async () => {
    const ids = s.leads.filter(l => l.on).map(l => l.id);
    const stamp = new Date().toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    try {
      const r = await api<{ sent: number }>('/api/sms/alert', { body: { leadIds: ids, text: sms } });
      setState(st => ({ alertLog: [`${stamp} · test · ${r.sent} of ${ids.length} sent`, ...st.alertLog] })); setMsg('');
    } catch (e) { setMsg(explain(e)); }
  };
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="body" style={{ fontSize: 13.5 }}>Text group leads when the flood model forecasts a mound crest will be overtopped. Works on any phone, no app or data needed.</div>
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Warn when overtopping is forecast within</div>
        <Seg items={[[3, '3 days'], [5, '5 days'], [7, '7 days']]} value={days} onPick={setDays} />
      </div>
      <button className="btn plain between" style={{ minHeight: 44, padding: '0 12px', fontSize: 13, alignItems: 'center', display: 'flex' }} onClick={() => setRise(!rise)}><span>Scenario: river rises 8 cm</span><span className="it" style={{ color: 'var(--color-accent-800)' }}>{rise ? 'on' : 'off'}</span></button>
      <div style={{ borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)', padding: '10px 0', fontSize: 13.5 }}>
        {rise ? `Forecast: B‑03, B‑04, B‑05, B‑08 overtopped in ~${Math.min(days, 4)} days. Alert will go to 2 leads.` : `Water is falling. No crest at risk in the next ${days} days; no SMS will be sent.`}
      </div>
      <div>
        <div className="kick sm" style={{ marginBottom: 6 }}>SMS preview · {sms.length} of 160 characters</div>
        <div className="mono" style={{ border: '1px solid var(--color-neutral-800)', borderRadius: 12, padding: 12, background: 'var(--color-neutral-100)', fontSize: 12.5, lineHeight: 1.5 }}>{sms}</div>
        <div style={{ fontSize: 11, color: 'var(--color-neutral-700)', marginTop: 4 }}>Arabic copy is sent to leads who chose Arabic. Reply 1 to confirm receipt.</div>
      </div>
      <div>
        <div className="section">Recipients</div>
        {s.leads.map((l: Lead) => (
          <div key={l.id} className="rowg" style={{ alignItems: 'center' }}>
            <span><span style={{ display: 'block', fontSize: 14 }}>{l.name}</span><span className="sub num">{l.rows} · {l.phone}</span></span>
            <Toggle on={l.on} label={`Send to ${l.name}`} onClick={() => setState(st => ({ leads: st.leads.map(x => x.id === l.id ? { ...x, on: !x.on } : x) }))} />
          </div>
        ))}
      </div>
      {msg && <div className="msg">{msg}</div>}
      <button className="btn" onClick={send}>Send test SMS to selected</button>
      {s.alertLog.map((a, i) => <div key={i} className="num" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{a}</div>)}
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
      setState(st => ({ gauge: [r.reading, ...(st.gauge ?? [])] })); setMsg(`Reply sent: "${r.reply}"`);
    } catch (e) {
      // Offline: show what the server will decide, so volunteers can practise the format.
      const v = parseGauge(t, h[h.length - 1]);
      setMsg(`${explain(e)} Format check: ${v.kind === 'bad' ? 'not understood' : v.kind === 'held' ? 'would be held for the admin' : 'would be accepted'}.`);
    }
  };
  const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="box grid2" style={{ gap: 0 }}>
        <div style={{ padding: '10px 12px', borderRight: '1px solid var(--color-divider)' }}><div className="lbl">SMS</div><div className="mono" style={{ fontSize: 14 }}>G 4.12</div><div style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}>to the project short code</div></div>
        <div style={{ padding: '10px 12px' }}><div className="lbl">USSD</div><div className="mono" style={{ fontSize: 14 }}>*384*22#</div><div style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}>1 Gauge · 2 Rain · 3 Flood</div></div>
      </div>
      <div>
        <div className="between"><span className="kick sm">Bor gauge · last {h.length} readings</span><span className="head num" style={{ fontSize: 22 }}>{h[h.length - 1].toFixed(2)} m</span></div>
        <svg viewBox="0 0 320 70" width="100%" height="70" style={{ display: 'block', borderBottom: '1px solid var(--color-divider)' }}>
          <polyline points={pts.map(p => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--color-accent)" strokeWidth="1.6" />
          {pts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="2.5" fill={i === pts.length - 1 ? 'var(--color-accent)' : 'var(--color-bg)'} stroke="var(--color-accent)" />)}
        </svg>
      </div>
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Try it: send a reading as the Bor volunteer</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8 }}>
          <input className="input mono" style={{ minHeight: 42 }} placeholder="G 4.10" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
          <button className="btn md" style={{ padding: '0 14px' }} onClick={send}>Send</button>
        </div>
        {msg && <div className="msg">{msg}</div>}
      </div>
      <div>
        <div className="section">Inbox → gauge sheet{s.gauge ? '' : ' · sample until first sync'}</div>
        {rows.slice(0, 12).map((m, i) => (
          <div key={i} className="rowg">
            <span><span className="mono" style={{ display: 'block', fontSize: 13.5 }}>"{m.text}"</span><span className="sub">{m.from} · {when(m.at)}</span></span>
            <span className="it" style={{ fontSize: 12, textAlign: 'right', color: m.status === 'ok' ? 'var(--color-neutral-700)' : 'var(--color-accent-800)' }}>{m.status === 'bad' ? 'not understood · reply sent' : m.status === 'ok' ? `accepted · ${m.v!.toFixed(2)} m` : 'held for admin'}</span>
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
            <Icon d={d} size={52} sw={1.3} />
            <span style={{ fontSize: 12, color: 'var(--color-neutral-800)' }}>{l}</span>
            <span style={{ position: 'absolute', top: 8, right: 10, fontSize: 13, color: 'var(--color-accent-800)' }}>{s.doneP.includes(k) ? '✓' : ''}</span>
          </button>
        ))}
      </div>
      <div style={{ minHeight: 44, display: 'flex', alignItems: 'center', gap: 10, borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)', padding: '8px 0' }}>
        <span style={{ display: 'flex', gap: 3, alignItems: 'flex-end', height: 20 }}>{[bar('18px'), bar('10px'), bar('20px'), bar('10px')].map((h, i) => <span key={i} style={{ width: 3, height: recording ? '14px' : h, background: 'var(--color-accent)' }} />)}</span>
        <span style={{ fontSize: 13, color: 'var(--color-neutral-800)', flex: 1 }}>{status}</span>
        {canLead && playing && <button className="btn plain sm" onClick={toggleRec}>{recording ? 'Stop' : have[playing] ? 'Re‑record' : 'Record'}</button>}
      </div>
      <div className="sub" style={{ lineHeight: 1.5 }}>Prompts are recorded once by a group lead in the local dialect and stored on the phone (about 40 KB each). Leads and admins can re-record any prompt.</div>
    </div>
  );
}

// ---- iv Pest photo check ----
export function Pest() {
  const [st, setSt] = useState<'idle' | 'busy' | 'done'>('idle');
  const [answered, setAnswered] = useState('');
  const me = useApp().session?.user.id ?? 'EW‑014';
  useEffect(() => { if (st !== 'busy') return; const t = setTimeout(() => setSt('done'), 1400); return () => clearTimeout(t); }, [st]);
  const answer = (ok: boolean) => {
    record('pest', { plot: 'B‑12', suggestion: 'Fall armyworm', confirmed: ok, by: me });
    setAnswered(ok ? `Confirmed by ${me}. Task added for Group 6: treat B‑12 within 3 days. Neighbouring plots flagged for scouting.` : 'Sent to the county extension office with the photo for a second opinion.');
  };
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="photo" style={{ height: 170 }}>Crop‑check photo · sorghum leaf, B‑12</div>
      {st === 'idle' && <button className="btn lg" onClick={() => setSt('busy')}>Compare with local library</button>}
      {st === 'busy' && <div className="it" style={{ fontSize: 13.5, color: 'var(--color-accent-800)' }}>Comparing with 46 reference photos from Jonglei…</div>}
      {st === 'done' && (
        <div className="col g12">
          <div>
            <div className="section">Closest matches</div>
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
          ) : <div className="it" style={{ fontSize: 13, color: 'var(--color-accent-800)', borderTop: '1px solid var(--color-divider)', paddingTop: 8 }}>{answered}</div>}
        </div>
      )}
      <div className="sub" style={{ lineHeight: 1.5 }}>Preview: the matcher shows example results until the Jonglei reference library is loaded. The app only suggests; an extension worker confirms before any treatment is advised.</div>
    </div>
  );
}

// ---- v Work days & payout ----
export function Payout() {
  const s = useApp();
  const [msg, setMsg] = useState('');
  const days = MEMBERS.map((m, i) => m[1] + (s.present[i] ? 1 : 0)), tot = days.reduce((a, b) => a + b, 0);
  const share = (i: number) => 459 * days[i] / tot;
  const approve = () => {
    record('payout', { sale: 'Nile Botanicals 40 L', pool: 459, shares: MEMBERS.map((m, i) => ({ name: m[0], days: days[i], usd: Math.round(share(i) * 100) / 100 })) });
    setMsg('Approved. The mobile‑money list goes to the project office at the next sync for payment.');
  };
  const date = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="between"><div><div className="kick">Group 4 · roll‑call {date}</div><div className="head" style={{ fontSize: 24 }}>{s.present.filter(Boolean).length} of 12 present</div></div><button className="btn plain sm" onClick={() => setState({ present: MEMBERS.map(() => true) })}>All present</button></div>
      <div>
        <div style={{ display: 'grid', gridTemplateColumns: '28px 1fr 52px 64px', gap: 8 }} className="lbl rule-b"><span /><span>Member</span><span style={{ textAlign: 'right' }}>Days</span><span style={{ textAlign: 'right' }}>Share</span></div>
        {MEMBERS.map((m, i) => (
          <button key={m[0]} className="row" onClick={() => setState(st => ({ present: st.present.map((p, j) => (j === i ? !p : p)) }))} style={{ display: 'grid', gridTemplateColumns: '28px 1fr 52px 64px', gap: 8, alignItems: 'center', padding: '8px 0', fontSize: 13.5, minHeight: 40 }}>
            <Check on={s.present[i]} /><span>{m[0]}</span><span className="num" style={{ textAlign: 'right' }}>{days[i]}</span><span className="head num" style={{ textAlign: 'right', fontSize: 17 }}>${share(i).toFixed(2)}</span>
          </button>
        ))}
      </div>
      <div className="num rule-b" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '4px 10px', fontSize: 13, paddingBottom: 10 }}>
        <span>Oil sale, Nile Botanicals (40 L)</span><span style={{ textAlign: 'right' }}>$540.00</span>
        <span style={{ color: 'var(--color-neutral-700)' }}>Cooperative fund 15%</span><span style={{ textAlign: 'right', color: 'var(--color-neutral-700)' }}>− $81.00</span>
        <span style={{ fontWeight: 600 }}>Shared by work days</span><span style={{ textAlign: 'right', fontWeight: 600 }}>$459.00</span>
      </div>
      {msg && <div className="msg">{msg}</div>}
      <button className="btn" onClick={approve}>Approve & send mobile‑money list</button>
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
  const [i, setI] = useState(0);
  const b = BATCHES[i];
  const rows: [string, string][] = [['Plot', b.plot], ['Fruit collected', b.fruit], ['Pressed', b.pressed], ['Batch size', b.bottles], ['Origin', b.place], ['Cooperative', 'Abuk Project, 160 farmers']];
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <Seg items={BATCHES.map((x, j) => [j, x.id] as [number, string])} value={i} onPick={setI} fontSize={12} />
      <div className="box" style={{ display: 'grid', gridTemplateColumns: '128px 1fr', gap: 14, alignItems: 'center', padding: 12 }}>
        <svg viewBox="0 0 25 25" width="128" height="128" style={{ display: 'block', background: 'var(--color-neutral-100)' }}>{qrCells(b.id).map(c => <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width="1" height="1" fill="var(--color-text)" />)}</svg>
        <div className="col" style={{ gap: 3 }}>
          <div className="kick sm">Bottle label</div>
          <div className="head" style={{ fontSize: 20, lineHeight: 1.1 }}>Desert date oil, 1 L</div>
          <div className="num" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Batch {b.id}</div>
          <div className="it" style={{ fontSize: 10.5, color: 'var(--color-neutral-600)' }}>placeholder QR pattern</div>
        </div>
      </div>
      <div>
        <div className="section">What the buyer sees on scan</div>
        {rows.map(([k, v]) => <div key={k} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--color-divider)', fontSize: 13.5 }}><span style={{ color: 'var(--color-neutral-700)' }}>{k}</span><span>{v}</span></div>)}
      </div>
      <button className="btn" onClick={() => window.print()}>Print labels for this batch</button>
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
