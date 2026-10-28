import { useEffect, useRef, useState } from 'react';
import { savePhoto } from '../photos';
import { ACTIVITIES, CRACK_WIDTH, MIN_PHOTOS, pestOptions, SOIL_MOISTURE, SURFACE, WATER_AROUND, WATER_STATE, WATER_TREND, conditionSummary, plotLabel, plotForGps, pointInPolygon, type PlotCondition, type Term, SKIES, STAGES, EW_ID, monitorError, normId, whereIs } from '@abuk/core';
import { record, setState, today, useApp } from '../store';
import { oneFix, useOnline, type Fix } from '../net';
import { Field, Seg } from '../ui';
import { fetchWeather, lastWeather, type Weather } from '../weather';

const isoToday = () => new Date().toISOString().slice(0, 10);

export function Monitor() {
  const s = useApp(), online = useOnline();
  const myId = s.session?.user.id.startsWith('EW') ? s.session.user.id : '';
  const lw = lastWeather();
  const plotOpts = s.farm.plots.map(p => plotLabel(p, s.farm)), cropOpts = s.farm.crops.map(c => c.name);
  const blank = { plot: plotOpts[0] ?? '', ew: myId, date: isoToday(), acts: ['Weeding'], crop: cropOpts.includes('Cowpea') ? 'Cowpea' : cropOpts[0] ?? '', stage: 'Seedbed', cond: 4, pests: [] as string[], sky: (lw?.sky ?? 'Sunny') as string, temp: lw ? String(lw.temp) : '', rain: lw ? String(lw.rain24) : '', notes: '', condition: { moisture: '', water: '', floodDepthCm: '', around: '', aroundDepthCm: '', aroundDistanceM: '', trend: '', surface: [], crackWidth: '' } as PlotCondition };
  const [m, setM] = useState(blank);
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState(false);
  const [photos, setPhotos] = useState<Blob[]>([]);
  const [fix, setFix] = useState<Fix | null>(null);
  const [fixErr, setFixErr] = useState('');
  const [gpsWarn, setGpsWarn] = useState('');
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
      const match = plotForGps(f, s.farm.plots);
      if (match && !edited.current.has('plot')) {
        const label = plotOpts.find(o => o.startsWith(match.code));
        if (label) setM(x => ({ ...x, plot: label }));
        if (!match.inside) setGpsWarn(`GPS is near ${match.code} (${Math.round(match.distKm * 1000)} m from centre) but outside its boundary`);
      } else if (!match && s.farm.plots.some(p => p.boundary.length > 2)) {
        setGpsWarn('GPS position does not fall inside any mapped plot');
      }
      fetchWeather(f.lat, f.lon).then(w => {
        setWx({ w, live: true, err: '' });
        setM(x => ({ ...x, ...(edited.current.has('temp') ? {} : { temp: String(w.temp) }), ...(edited.current.has('rain') ? {} : { rain: String(w.rain24) }), ...(edited.current.has('sky') ? {} : { sky: w.sky }) }));
      }, e => setWx(x => ({ ...x, err: (e as Error).message })));
    }, e => setFixErr((e as Error).message));
    const iv = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(iv);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const upd = <K extends keyof typeof m>(k: K, v: (typeof m)[K]) => {
    edited.current.add(k);
    setM(x => ({ ...x, [k]: v }));
    setErr(''); setSaved(false);
    if (k === 'plot' && fix) {
      const code = (v as string).split(' · ')[0];
      const plot = s.farm.plots.find(p => p.code === code);
      if (plot && plot.boundary.length > 2) {
        if (!pointInPolygon(fix, plot.boundary)) setGpsWarn(`GPS is outside ${code}'s boundary — are you at the right plot?`);
        else setGpsWarn('');
      } else setGpsWarn('');
    }
  };
  const setCond = (c: Partial<PlotCondition>) => { setM(x => ({ ...x, condition: { ...x.condition, ...c } })); setErr(''); setSaved(false); };
  const tog = (k: 'acts' | 'pests', v: string) => upd(k, m[k].includes(v) ? m[k].filter(x => x !== v) : [...m[k], v]);

  const save = async () => {
    const bad = monitorError({ ...m, photos: photos.length });
    if (bad) return setErr(bad);
    const ew = normId(m.ew);
    const photoKeys = await Promise.all(photos.map(b => savePhoto(b, 'check')));
    const at = new Date(), place = fix ? whereIs(fix.lat, fix.lon) : null;
    const rid = record('monitor', { ...m, ew, gps: fix && { lat: fix.lat, lon: fix.lon, acc: fix.acc }, place, stampedAt: at.toISOString(), weather: { source: wx.live ? 'open-meteo' : wx.w ? 'last reading' : 'entered', edited: [...edited.current].filter(k => ['temp', 'rain', 'sky'].includes(k)) }, photos: photoKeys });
    setState(st => ({ monLog: [{ plot: m.plot.split(' · ')[0], crop: m.crop, acts: m.acts.join(', '), ew, date: today(), cond: m.cond, synced: false, rid, field: conditionSummary(m.condition), at: at.toISOString(), ...(fix ? { lat: fix.lat, lon: fix.lon } : {}), water: m.condition.water, depthCm: Number(m.condition.floodDepthCm) || null, around: m.condition.around, aroundDepthCm: Number(m.condition.aroundDepthCm) || null, trend: m.condition.trend }, ...st.monLog].slice(0, 300) }));
    setM({ ...m, notes: '', pests: [], condition: { ...m.condition, surface: [], crackWidth: '', floodDepthCm: '', aroundDepthCm: '', aroundDistanceM: '' } }); setPhotos([]); setSaved(true);
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
        {gpsWarn && <div style={{ padding: '8px 10px', borderRadius: 'var(--radius-md)', background: '#fef3cd', color: '#856404', fontSize: 12.5, lineHeight: 1.45 }}>⚠ {gpsWarn}</div>}
        <Field label="Farm / plot"><select className="input" value={m.plot} onChange={e => upd('plot', e.target.value)}>{plotOpts.map(o => <option key={o}>{o}</option>)}</select></Field>
        <div className="grid2">
          <Field label="Extension worker ID"><input className={'input num' + (err && !EW_ID.test(m.ew) ? ' bad' : '')} value={m.ew} placeholder="EW‑000" onChange={e => upd('ew', e.target.value.toUpperCase())} style={{ textTransform: 'uppercase' }} /></Field>
          <Field label="Date"><input className="input" type="date" value={m.date} onChange={e => upd('date', e.target.value)} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
        </div>
      </div>
      <div className="col g10">
        {sec('2 · Plot condition today', 'FAO soil description terms')}
        <TermPick label="Soil moisture (squeeze a handful from 10 cm down)" terms={SOIL_MOISTURE} value={m.condition.moisture} onPick={v => setCond({ moisture: v })} />
        <TermPick label="Water on the plot" terms={WATER_STATE} value={m.condition.water} onPick={v => setCond({ water: v })} />
        {['ponding', 'flooded', 'receding'].includes(m.condition.water) && <Field label="Water depth on the plot, deepest point (cm)"><input className="input num" type="number" inputMode="numeric" value={m.condition.floodDepthCm} onChange={e => setCond({ floodDepthCm: e.target.value })} /></Field>}
        <TermPick label="Water around the plot" terms={WATER_AROUND} value={m.condition.around} onPick={v => setCond({ around: v })} />
        {m.condition.around && m.condition.around !== 'dry' && (
          <div className="grid2">
            <Field label="Depth of that water (cm)"><input className="input num" type="number" inputMode="numeric" value={m.condition.aroundDepthCm} onChange={e => setCond({ aroundDepthCm: e.target.value })} /></Field>
            {m.condition.around === 'nearby' && <Field label="Distance from plot (m)"><input className="input num" type="number" inputMode="numeric" value={m.condition.aroundDistanceM} onChange={e => setCond({ aroundDistanceM: e.target.value })} /></Field>}
          </div>
        )}
        {(m.condition.water && m.condition.water !== 'none') || (m.condition.around && m.condition.around !== 'dry')
          ? <TermPick label="Water level since the last visit" terms={WATER_TREND} value={m.condition.trend} onPick={v => setCond({ trend: v })} /> : null}
        <div className="sub">Measure depth with a stick marked every 10 cm, at the deepest point you can reach safely.</div>
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Surface and damage seen (tap all that apply)</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {SURFACE.map(t => { const on = m.condition.surface.includes(t.id); return (
            <button key={t.id} className={'chip' + (on ? ' on' : '')} style={{ minHeight: 36, padding: '0 10px', fontSize: 12.5 }} title={t.desc}
              onClick={() => setCond({ surface: on ? m.condition.surface.filter(x => x !== t.id) : [...m.condition.surface, t.id] })}>{on ? '✓ ' : ''}{t.label}</button>
          ); })}
        </div>
        {m.condition.surface.length > 0 && <div className="sub">{m.condition.surface.map(id => SURFACE.find(t => t.id === id)!).map(t => `${t.label}: ${t.desc}`).join(' · ')}</div>}
        {m.condition.surface.includes('cracking') && <TermPick label="Widest cracks (FAO width class)" terms={CRACK_WIDTH} value={m.condition.crackWidth} onPick={v => setCond({ crackWidth: v })} showDesc />}
      </div>
      <div className="col g8">
        {sec('3 · Activity done')}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {ACTIVITIES.map(a => <button key={a} className={'chip' + (m.acts.includes(a) ? ' on' : '')} onClick={() => tog('acts', a)}>{m.acts.includes(a) ? '✓ ' : ''}{a}</button>)}
        </div>
      </div>
      <div className="col g10">
        {sec('4 · Crop')}
        <Field label="Crop"><select className="input" value={m.crop} onChange={e => upd('crop', e.target.value)}>{cropOpts.map(o => <option key={o}>{o}</option>)}</select></Field>
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Growth stage</div>
        <Seg items={STAGES.map(x => [x, x] as [string, string])} value={m.stage} onPick={v => upd('stage', v)} fontSize={12} />
        <div className="between"><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Condition</span><span className="it" style={{ fontSize: 12.5, color: 'var(--color-accent-800)' }}>{['', 'failing', 'poor', 'fair', 'good', 'excellent'][m.cond]}</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 6 }}>
          {[1, 2, 3, 4, 5].map(n => <button key={n} className={'chip head num' + (m.cond === n ? ' on' : '')} style={{ minHeight: 42, fontSize: 20 }} onClick={() => upd('cond', n)}>{n}</button>)}
        </div>
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Pests or disease seen</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {['None', ...pestOptions(m.crop, '', s.farm.crops.find(c => c.name === m.crop)).map(o => o.name).slice(0, 12)].map(p => <button key={p} className={'chip' + (m.pests.includes(p) ? ' on' : '')} style={{ minHeight: 36, padding: '0 10px', fontSize: 12.5 }} onClick={() => tog('pests', p)}>{m.pests.includes(p) ? '✓ ' : ''}{p}</button>)}
        </div>
      </div>
      <div className="col g10">
        {sec('5 · Local weather', wx.live ? `auto from Open‑Meteo ${new Date(wx.w!.at).toTimeString().slice(0, 5)}, editable` : wx.w ? `offline: last reading ${new Date(wx.w.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : fix ? (wx.err ? 'no weather data: enter by hand' : 'fetching weather…') : 'waiting for GPS')}
        <Seg items={SKIES.map(x => [x, x] as [string, string])} value={m.sky} onPick={v => upd('sky', v)} fontSize={12.5} />
        <div className="grid2">
          <Field label="Temperature °C"><input className="input num" type="number" value={m.temp} onChange={e => upd('temp', e.target.value)} /></Field>
          <Field label="Rain last 24 h (mm)"><input className="input num" type="number" value={m.rain} onChange={e => upd('rain', e.target.value)} /></Field>
        </div>
      </div>
      <div className="col g10">
        {sec('6 · Evidence')}
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
            <span><span style={{ display: 'block', fontSize: 14 }}>{r.plot} · {r.crop}</span><span className="sub">{r.acts} · {r.ew} · {r.date}</span>{r.field && <span className="sub" style={{ display: 'block' }}>{r.field}</span>}</span>
            <span style={{ textAlign: 'right' }}><span className="head" style={{ display: 'block', fontSize: 19 }}>{r.cond}/5</span><span className="it" style={{ fontSize: 11, color: 'var(--color-accent-700)' }}>{r.synced ? 'synced' : 'on phone'}</span></span>
          </div>
        ))}
      </div>
    </div>
  );
}

// One-of picker for a list of standard terms; the chosen term's description shows underneath.
function TermPick({ label, terms, value, onPick, showDesc }: { label: string; terms: Term[]; value: string; onPick: (id: string) => void; showDesc?: boolean }) {
  const cur = terms.find(t => t.id === value);
  return (
    <div className="col g6">
      <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{label}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {terms.map(t => <button key={t.id} className={'chip' + (value === t.id ? ' on' : '')} style={{ minHeight: 36, padding: '0 10px', fontSize: 12.5 }} onClick={() => onPick(t.id)}>{t.label}{showDesc ? ` ${t.desc}` : ''}</button>)}
      </div>
      {cur && !showDesc && <div className="sub it">{cur.desc}</div>}
    </div>
  );
}
