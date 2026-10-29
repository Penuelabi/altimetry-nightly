import { useEffect, useState } from 'react';
import { WATER_TREND, adminLabel, basinDepth, recessDays, whereIs, zoneDepths, type AdminLoc } from '@abuk/core';
import { record, setState, today, useApp } from '../store';
import { oneFix, useOnline, type Fix } from '../net';
import { AdminPicker, nowLocal, useHereAdmin } from '../pickers';
import { Field, Seg } from '../ui';
import { allChecks, useModel } from './common';

const WATER: [string, string][] = [['flooded', 'Flooded'], ['receding', 'Receding'], ['ponding', 'Ponding'], ['waterlogged', 'Waterlogged'], ['none', 'Dry']];

// Measured water depth. The flood model starts from these readings: no readings, no measured depth.
export function Depth() {
  const s = useApp(), online = useOnline(), model = useModel(), here = useHereAdmin();
  const [zone, setZone] = useState<'basin' | 'slope' | 'ridge'>('basin');
  const [plot, setPlot] = useState('');
  const [admin, setAdmin] = useState<AdminLoc>(here);
  const [cm, setCm] = useState('');
  const [water, setWater] = useState('flooded');
  const [trend, setTrend] = useState('unknown');
  const [at, setAt] = useState(nowLocal());
  const [by, setBy] = useState(s.session?.user.name ?? '');
  const [note, setNote] = useState('');
  const [fix, setFix] = useState<Fix | null>(null);
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState('');
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    oneFix().then(f => {
      setFix(f);
      const w = whereIs(f.lat, f.lon);
      if (w && auto) setAdmin(a => (a.payam === here.payam ? { state: w.state, county: w.county, payam: w.payam, village: a.village } : a));
    }, () => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const z = zoneDepths(model);
  const days = recessDays(model);
  const checks = allChecks(s).filter(c => c.water && c.lat != null).slice(0, 8);
  const p = plot ? s.farm.plots.find(x => x.id === plot) : null;
  const label = p ? p.code : `${zone[0].toUpperCase()}${zone.slice(1)} zone`;

  const save = () => {
    const depth = Number(cm);
    if (water !== 'none' && !(depth > 0)) return setErr('Enter how deep the water is, in centimetres.');
    if (depth > 300) return setErr('That is deeper than 3 m. Check the number.');
    if (!admin.state || !admin.county || !admin.payam) return setErr('Choose the state, county and payam.');
    if (!by.trim()) return setErr('Say who measured it.');
    const when = new Date(at);
    if (isNaN(+when) || +when > Date.now() + 3600_000) return setErr('The date and time must not be in the future.');
    const depthCm = water === 'none' ? 0 : depth;
    const rid = record('monitor', {
      plot: label, crop: '', acts: ['Water depth'], ew: s.session?.user.id ?? '', date: at.slice(0, 10), stampedAt: when.toISOString(),
      gps: fix && { lat: fix.lat, lon: fix.lon, acc: fix.acc }, place: admin, zone: p ? p.zone : zone, measuredBy: by.trim(), source: 'depth-form', notes: note,
      condition: { water, floodDepthCm: String(depthCm), trend, moisture: '', around: '', aroundDepthCm: '', aroundDistanceM: '', surface: [], crackWidth: '' }
    });
    setState(st => ({ monLog: [{ plot: label, crop: '', acts: 'Water depth', ew: s.session?.user.id ?? '', date: today(), cond: 3, synced: false, rid, field: `${water}${depthCm ? ` ${depthCm} cm` : ''}`, at: when.toISOString(), ...(fix ? { lat: fix.lat, lon: fix.lon } : {}), water, depthCm, around: '', aroundDepthCm: null, trend }, ...st.monLog].slice(0, 300) }));
    setSaved(`Saved: ${label}, ${depthCm} cm. The flood model now starts from this reading.`);
    setCm(''); setNote(''); setErr('');
  };

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="box col g8" style={{ padding: 12 }}>
        <div className="between"><span className="kick sm">Depth the model is using</span><span className="it" style={{ fontSize: 11.5, color: model.measured ? 'var(--color-accent-800)' : '#856404' }}>{model.measured ? 'measured' : 'not measured'}</span></div>
        <div className="grid2" style={{ gap: 0 }}>
          {(['ridge', 'slope', 'basin'] as const).map(k => (
            <div key={k} style={{ padding: '6px 0' }}><div className="lbl">{k}</div><div className="head num" style={{ fontSize: 22 }}>{z[k].toFixed(2)} m</div></div>
          ))}
          <div style={{ padding: '6px 0' }}><div className="lbl">Dry in</div><div className="head num" style={{ fontSize: 22 }}>{days == null ? '—' : `${days} days`}</div></div>
        </div>
        <div className="sub">Basin: {model.d0Src}. Falling rate: {model.rateSrc}. Slope is the basin depth minus 0.70 m (farm survey); the ridge stays dry.</div>
        {!model.measured && <div className="sub it">{basinDepth(0).toFixed(2)} m is the design example. Record a reading below to replace it.</div>}
      </div>

      <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Record water depth</h2>
      <div className="col g10">
        <Seg items={[['basin', 'Basin'], ['slope', 'Slope'], ['ridge', 'Ridge']]} value={zone} onPick={z2 => { setZone(z2); setPlot(''); }} />
        <Field label="Plot (optional)">
          <select className="input" value={plot} onChange={e => { setPlot(e.target.value); const q = s.farm.plots.find(x => x.id === e.target.value); if (q) setZone(q.zone); }}>
            <option value="">No plot: the {zone} in general</option>
            {s.farm.plots.map(q => <option key={q.id} value={q.id}>{q.code} · {q.crop}</option>)}
          </select>
        </Field>
        <AdminPicker value={admin} onChange={a => { setAuto(false); setAdmin(a); }} label="Where" />
        <div className="sub num">{fix ? `GPS ${fix.lat.toFixed(5)}, ${fix.lon.toFixed(5)} ±${Math.round(fix.acc)} m · stamped automatically` : 'Waiting for GPS…'}</div>
        <Seg items={WATER} value={water} onPick={setWater} fontSize={12} />
        {water !== 'none' && <Field label="Depth of water at the deepest point (cm)"><input className="input num" type="number" inputMode="numeric" value={cm} onChange={e => { setCm(e.target.value); setErr(''); }} /></Field>}
        <div className="sub">Measure with a stick marked every 10 cm, where you can safely reach.</div>
        <Seg items={WATER_TREND.map(t => [t.id, t.label] as [string, string])} value={trend} onPick={setTrend} fontSize={12} />
        <div className="grid2">
          <Field label="Date and time"><input className="input" type="datetime-local" value={at} max={nowLocal()} onChange={e => setAt(e.target.value)} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
          <Field label="Measured by"><input className="input" value={by} onChange={e => setBy(e.target.value)} /></Field>
        </div>
        <textarea className="input" rows={2} placeholder="Notes (optional)" value={note} onChange={e => setNote(e.target.value)} />
        {err && <div className="msg">{err}</div>}
        {saved && <div className="msg">{saved}</div>}
        <button className="btn lg" onClick={save}>{online ? 'Save reading' : 'Save on phone'}</button>
        <div className="sub">At {adminLabel(admin) || 'this place'}. Readings sync with the crop checks and feed the flood model for everyone nearby.</div>
      </div>

      {checks.length > 0 && (
        <div>
          <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Recent readings</h2>
          {checks.map((c, i) => (
            <div key={i} className="rowg"><span><span style={{ display: 'block', fontSize: 14 }}>{c.plot}</span><span className="sub">{new Date(c.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · {c.water}</span></span><span className="head num" style={{ fontSize: 20 }}>{c.depthCm != null ? `${c.depthCm} cm` : '—'}</span></div>
          ))}
        </div>
      )}
    </div>
  );
}
