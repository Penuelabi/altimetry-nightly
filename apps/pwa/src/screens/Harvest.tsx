import { useEffect, useRef, useState } from 'react';
import { harvestError, plotForGps, pointInPolygon } from '@abuk/core';
import { record, setState, today, useApp } from '../store';
import { oneFix, useOnline, type Fix } from '../net';
import { Field } from '../ui';

export function Harvest() {
  const s = useApp(), online = useOnline();
  const crops = s.farm.crops.map(c => c.name), plots = s.farm.plots.map(p => p.code);
  const [form, setForm] = useState({ crop: crops[0] ?? '', plot: plots[0] ?? '', kg: '' });
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState(false);
  const [fix, setFix] = useState<Fix | null>(null);
  const [gpsWarn, setGpsWarn] = useState('');
  const edited = useRef(new Set<string>());
  const who = s.session?.user.meta.match(/Group \d+/)?.[0] ?? s.session?.user.name ?? 'Group 4';

  useEffect(() => {
    oneFix().then(f => {
      setFix(f);
      const match = plotForGps(f, s.farm.plots);
      if (match && !edited.current.has('plot')) {
        setForm(x => ({ ...x, plot: match.code }));
        if (!match.inside) setGpsWarn(`GPS is near ${match.code} (${Math.round(match.distKm * 1000)} m from centre) but outside its boundary`);
      } else if (!match && s.farm.plots.some(p => p.boundary.length > 2)) {
        setGpsWarn('GPS position does not fall inside any mapped plot');
      }
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const upd = (k: keyof typeof form) => (e: { target: { value: string } }) => {
    edited.current.add(k);
    setForm({ ...form, [k]: e.target.value }); setSaved(false); if (k === 'kg') setErr('');
    if (k === 'plot' && fix) {
      const plot = s.farm.plots.find(p => p.code === e.target.value);
      if (plot && plot.boundary.length > 2) {
        if (!pointInPolygon(fix, plot.boundary)) setGpsWarn(`GPS is outside ${e.target.value}'s boundary — are you at the right plot?`);
        else setGpsWarn('');
      } else setGpsWarn('');
    }
  };
  const save = () => {
    const kg = Number(form.kg), bad = harvestError(kg);
    if (bad) return setErr(bad);
    const rid = record('harvest', { crop: form.crop, plot: form.plot, kg, who, ...(fix ? { gps: { lat: fix.lat, lon: fix.lon, acc: fix.acc } } : {}) });
    setState(st => ({ harvests: [{ crop: form.crop, plot: form.plot, kg, who, date: today(), synced: false, rid }, ...st.harvests] }));
    setForm({ ...form, kg: '' }); setSaved(true); setErr('');
  };
  return (
    <div className="pad g14">
      <div className="box col g10" style={{ padding: 14 }}>
        <h2 className="h2 h20">New entry</h2>
        <Field label="Crop"><select className="input" value={form.crop} onChange={upd('crop')}>{crops.map(o => <option key={o}>{o}</option>)}</select></Field>
        {fix && <div className="sub num" style={{ fontSize: 11.5, color: 'var(--color-neutral-600)' }}>GPS: {fix.lat.toFixed(5)}, {fix.lon.toFixed(5)} ±{Math.round(fix.acc)} m</div>}
        {gpsWarn && <div style={{ padding: '8px 10px', borderRadius: 'var(--radius-md)', background: '#fef3cd', color: '#856404', fontSize: 12.5, lineHeight: 1.45 }}>⚠ {gpsWarn}</div>}
        <div className="grid2">
          <Field label="Plot"><select className="input" value={form.plot} onChange={upd('plot')}>{plots.map(o => <option key={o}>{o}</option>)}</select></Field>
          <Field label="Weight (kg)"><input className={'input num' + (err ? ' bad' : '')} type="number" inputMode="decimal" placeholder="0" value={form.kg} onChange={upd('kg')} style={{ fontSize: 16 }} /></Field>
        </div>
        {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}
        <button className="btn" onClick={save}>{saved ? (online ? 'Saved, syncing ✓' : 'Saved on phone ✓') : 'Save entry'}</button>
      </div>
      <div>
        <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>This month</h2>
        {s.harvests.map((h, i) => (
          <div key={i} className="rowg">
            <span><span style={{ display: 'block', fontSize: 14 }}>{h.crop}</span><span className="sub">{h.plot} · {h.who} · {h.date}</span></span>
            <span style={{ textAlign: 'right' }}><span className="head num" style={{ display: 'block', fontSize: 20 }}>{h.kg.toLocaleString('en')} kg</span><span className="it" style={{ fontSize: 11, color: 'var(--color-accent-700)' }}>{h.synced ? 'synced' : 'on phone'}</span></span>
          </div>
        ))}
      </div>
    </div>
  );
}
