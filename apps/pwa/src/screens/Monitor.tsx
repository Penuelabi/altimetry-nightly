import { useEffect, useRef, useState } from 'react';
import { set as idbSet } from 'idb-keyval';
import { ACTIVITIES, MIN_PHOTOS, MON_CROPS, MON_PLOTS, PESTS, SKIES, STAGES, EW_ID, monitorError, normId, whereIs } from '@abuk/core';
import { record, setState, today, useApp } from '../store';
import { oneFix, useOnline, type Fix } from '../net';
import { Field, Seg } from '../ui';
import { fetchWeather, lastWeather, type Weather } from '../weather';

const isoToday = () => new Date().toISOString().slice(0, 10);

export function Monitor() {
  const s = useApp(), online = useOnline();
  const myId = s.session?.user.id.startsWith('EW') ? s.session.user.id : '';
  const lw = lastWeather();
  const blank = { plot: MON_PLOTS[0], ew: myId, date: isoToday(), acts: ['Weeding'], crop: 'Cowpea', stage: 'Seedbed', cond: 4, pests: [] as string[], sky: (lw?.sky ?? 'Sunny') as string, temp: lw ? String(lw.temp) : '', rain: lw ? String(lw.rain24) : '', notes: '' };
  const [m, setM] = useState(blank);
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState(false);
  const [photos, setPhotos] = useState<Blob[]>([]);
  const [fix, setFix] = useState<Fix | null>(null);
  const [fixErr, setFixErr] = useState('');
  const [now, setNow] = useState(new Date());
  const [wx, setWx] = useState<{ w: Weather | null; live: boolean; err: string }>({ w: lw, live: false, err: '' });
  const edited = useRef(new Set<string>());
  const file = useRef<HTMLInputElement>(null);
  const urls = photos.map(p => URL.createObjectURL(p));
  useEffect(() => () => urls.forEach(URL.revokeObjectURL), [photos]); // eslint-disable-line react-hooks/exhaustive-deps

  // GPS, clock and weather fill themselves in; the worker only edits what looks wrong.
  useEffect(() => {
    oneFix().then(f => {
      setFix(f);
      fetchWeather(f.lat, f.lon).then(w => {
        setWx({ w, live: true, err: '' });
        setM(x => ({ ...x, ...(edited.current.has('temp') ? {} : { temp: String(w.temp) }), ...(edited.current.has('rain') ? {} : { rain: String(w.rain24) }), ...(edited.current.has('sky') ? {} : { sky: w.sky }) }));
      }, e => setWx(x => ({ ...x, err: (e as Error).message })));
    }, e => setFixErr((e as Error).message));
    const iv = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(iv);
  }, []);

  const upd = <K extends keyof typeof m>(k: K, v: (typeof m)[K]) => { edited.current.add(k); setM(x => ({ ...x, [k]: v })); setErr(''); setSaved(false); };
  const tog = (k: 'acts' | 'pests', v: string) => upd(k, m[k].includes(v) ? m[k].filter(x => x !== v) : [...m[k], v]);

  const save = async () => {
    const bad = monitorError({ ...m, photos: photos.length });
    if (bad) return setErr(bad);
    const ew = normId(m.ew);
    const photoKeys = await Promise.all(photos.map(async (b, i) => { const k = `photo-${Date.now()}-${i}`; await idbSet(k, b).catch(() => {}); return k; }));
    const at = new Date(), place = fix ? whereIs(fix.lat, fix.lon) : null;
    const rid = record('monitor', { ...m, ew, gps: fix && { lat: fix.lat, lon: fix.lon, acc: fix.acc }, place, stampedAt: at.toISOString(), weather: { source: wx.live ? 'open-meteo' : wx.w ? 'last reading' : 'entered', edited: [...edited.current].filter(k => ['temp', 'rain', 'sky'].includes(k)) }, photos: photoKeys });
    setState(st => ({ monLog: [{ plot: m.plot.split(' · ')[0], crop: m.crop, acts: m.acts.join(', '), ew, date: today(), cond: m.cond, synced: false, rid }, ...st.monLog] }));
    setM({ ...m, notes: '', pests: [] }); setPhotos([]); setSaved(true);
    edited.current.clear();
  };

  const sec = (n: string, right?: string) => right
    ? <div className="between rule-b" style={{ paddingBottom: 4 }}><span className="kick sm">{n}</span><span className="it" style={{ fontSize: 11, color: 'var(--color-neutral-600)' }}>{right}</span></div>
    : <div className="section">{n}</div>;

  return (
    <div className="pad" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>One record per plot visit. GPS and time are stamped automatically; the form saves on the phone and syncs to the cooperative's Drive sheet.</p>
      <div className="col g10">
        {sec('1 · Where & who')}
        <div className="box num" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 10px', padding: '10px 12px', fontSize: 13, background: 'var(--color-accent-100)' }}>
          <span><span className="lbl" style={{ display: 'block' }}>GPS · auto</span>{fix ? `${fix.lat.toFixed(5)}, ${fix.lon.toFixed(5)} ±${Math.round(fix.acc)} m` : fixErr || 'getting fix…'}</span>
          <span><span className="lbl" style={{ display: 'block' }}>Time · auto</span>{now.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
          <span><span className="lbl" style={{ display: 'block' }}>Payam · auto</span>{fix ? (whereIs(fix.lat, fix.lon)?.payam ?? 'outside South Sudan') : '—'}</span>
          <span><span className="lbl" style={{ display: 'block' }}>Temperature · auto</span>{m.temp ? `${m.temp} °C` : '—'}</span>
        </div>
        <Field label="Farm / plot"><select className="input" value={m.plot} onChange={e => upd('plot', e.target.value)}>{MON_PLOTS.map(o => <option key={o}>{o}</option>)}</select></Field>
        <div className="grid2">
          <Field label="Extension worker ID"><input className={'input num' + (err && !EW_ID.test(m.ew) ? ' bad' : '')} value={m.ew} placeholder="EW‑000" onChange={e => upd('ew', e.target.value.toUpperCase())} style={{ textTransform: 'uppercase' }} /></Field>
          <Field label="Date"><input className="input" type="date" value={m.date} onChange={e => upd('date', e.target.value)} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
        </div>
      </div>
      <div className="col g8">
        {sec('2 · Activity done')}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {ACTIVITIES.map(a => <button key={a} className={'chip' + (m.acts.includes(a) ? ' on' : '')} onClick={() => tog('acts', a)}>{m.acts.includes(a) ? '✓ ' : ''}{a}</button>)}
        </div>
      </div>
      <div className="col g10">
        {sec('3 · Crop')}
        <Field label="Crop"><select className="input" value={m.crop} onChange={e => upd('crop', e.target.value)}>{MON_CROPS.map(o => <option key={o}>{o}</option>)}</select></Field>
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Growth stage</div>
        <Seg items={STAGES.map(x => [x, x] as [string, string])} value={m.stage} onPick={v => upd('stage', v)} fontSize={12} />
        <div className="between"><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Condition</span><span className="it" style={{ fontSize: 12.5, color: 'var(--color-accent-800)' }}>{['', 'failing', 'poor', 'fair', 'good', 'excellent'][m.cond]}</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 6 }}>
          {[1, 2, 3, 4, 5].map(n => <button key={n} className={'chip head num' + (m.cond === n ? ' on' : '')} style={{ minHeight: 42, fontSize: 20 }} onClick={() => upd('cond', n)}>{n}</button>)}
        </div>
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Pests or disease seen</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {PESTS.map(p => <button key={p} className={'chip' + (m.pests.includes(p) ? ' on' : '')} style={{ minHeight: 36, padding: '0 10px', fontSize: 12.5 }} onClick={() => tog('pests', p)}>{m.pests.includes(p) ? '✓ ' : ''}{p}</button>)}
        </div>
      </div>
      <div className="col g10">
        {sec('4 · Local weather', wx.live ? `auto from Open‑Meteo ${new Date(wx.w!.at).toTimeString().slice(0, 5)}, editable` : wx.w ? `offline: last reading ${new Date(wx.w.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : fix ? (wx.err ? 'no weather data: enter by hand' : 'fetching weather…') : 'waiting for GPS')}
        <Seg items={SKIES.map(x => [x, x] as [string, string])} value={m.sky} onPick={v => upd('sky', v)} fontSize={12.5} />
        <div className="grid2">
          <Field label="Temperature °C"><input className="input num" type="number" value={m.temp} onChange={e => upd('temp', e.target.value)} /></Field>
          <Field label="Rain last 24 h (mm)"><input className="input num" type="number" value={m.rain} onChange={e => upd('rain', e.target.value)} /></Field>
        </div>
      </div>
      <div className="col g10">
        {sec('5 · Evidence')}
        <div className="between"><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Photos: whole plot, close-up of leaves, any damage</span><span className="num" style={{ fontSize: 12.5, color: photos.length >= MIN_PHOTOS ? 'var(--color-accent-800)' : 'var(--color-text)' }}>{photos.length} / {MIN_PHOTOS}{photos.length >= MIN_PHOTOS ? ' ✓' : ''}</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
          {urls.map((u, i) => (
            <div key={u} style={{ position: 'relative', height: 92, borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '1px solid var(--color-divider)' }}>
              <img src={u} alt={`Photo ${i + 1}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              <button aria-label={`Remove photo ${i + 1}`} onClick={() => setPhotos(p => p.filter((_, j) => j !== i))} style={{ position: 'absolute', top: 4, right: 4, width: 24, height: 24, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,.55)', color: '#fff', fontSize: 14, lineHeight: '24px', padding: 0 }}>×</button>
            </div>
          ))}
          <button onClick={() => file.current?.click()} style={{ height: 92, border: '1px dashed var(--color-accent)', borderRadius: 'var(--radius-md)', background: 'repeating-linear-gradient(135deg,var(--color-neutral-200) 0 1px,transparent 1px 8px)', color: 'var(--color-accent-800)', fontSize: 12 }}>
            + Photo{photos.length < MIN_PHOTOS ? ` ${photos.length + 1} of ${MIN_PHOTOS}` : ''}
          </button>
        </div>
        <input ref={file} type="file" accept="image/*" capture="environment" hidden onChange={e => { const f = e.target.files?.[0]; if (f) { setPhotos(p => [...p, f]); setErr(''); } e.target.value = ''; }} />
        <div className="sub">Photos stay on the phone until photo upload is set up.</div>
        <textarea className="input" rows={2} placeholder="Notes (optional)" value={m.notes} onChange={e => upd('notes', e.target.value)} />
      </div>
      {err && <div className="msg" style={{ borderTop: '1px solid var(--color-accent-300)', paddingTop: 8 }}>{err}</div>}
      <button className="btn lg" onClick={save}>{saved ? (online ? 'Saved, syncing ✓' : 'Saved on phone ✓') : 'Save crop check'}</button>
      <div>
        <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Recent checks</h2>
        {s.monLog.map((r, i) => (
          <div key={i} className="rowg">
            <span><span style={{ display: 'block', fontSize: 14 }}>{r.plot} · {r.crop}</span><span className="sub">{r.acts} · {r.ew} · {r.date}</span></span>
            <span style={{ textAlign: 'right' }}><span className="head" style={{ display: 'block', fontSize: 19 }}>{r.cond}/5</span><span className="it" style={{ fontSize: 11, color: 'var(--color-accent-700)' }}>{r.synced ? 'synced' : 'on phone'}</span></span>
          </div>
        ))}
      </div>
    </div>
  );
}
