import { useState } from 'react';
import { harvestError } from '@abuk/core';
import { record, setState, today, useApp } from '../store';
import { useOnline } from '../net';
import { Field } from '../ui';

export function Harvest() {
  const s = useApp(), online = useOnline();
  const crops = s.farm.crops.map(c => c.name), plots = s.farm.plots.map(p => p.code);
  const [form, setForm] = useState({ crop: crops[0] ?? '', plot: plots[0] ?? '', kg: '' });
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState(false);
  const who = s.session?.user.meta.match(/Group \d+/)?.[0] ?? s.session?.user.name ?? 'Group 4';
  const upd = (k: keyof typeof form) => (e: { target: { value: string } }) => { setForm({ ...form, [k]: e.target.value }); setSaved(false); if (k === 'kg') setErr(''); };
  const save = () => {
    const kg = Number(form.kg), bad = harvestError(kg);
    if (bad) return setErr(bad);
    const rid = record('harvest', { crop: form.crop, plot: form.plot, kg, who });
    setState(st => ({ harvests: [{ crop: form.crop, plot: form.plot, kg, who, date: today(), synced: false, rid }, ...st.harvests] }));
    setForm({ ...form, kg: '' }); setSaved(true); setErr('');
  };
  return (
    <div className="pad g14">
      <div className="box col g10" style={{ padding: 14 }}>
        <h2 className="h2 h20">New entry</h2>
        <Field label="Crop"><select className="input" value={form.crop} onChange={upd('crop')}>{crops.map(o => <option key={o}>{o}</option>)}</select></Field>
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
