import { useState } from 'react';
import { DEGRADATION_INDICATORS, newId, plotLabel, type DegradationAssessment } from '@abuk/core';
import { farmChange, useApp } from '../store';
import { Field } from '../ui';

const SEVERITY = [
  { v: 0, label: 'None', color: 'var(--color-accent)' },
  { v: 1, label: 'Mild', color: '#b8a040' },
  { v: 2, label: 'Moderate', color: '#c87830' },
  { v: 3, label: 'Severe', color: '#c03020' },
];

export function Degradation() {
  const s = useApp();
  const plots = s.farm.plots;
  const assessments = (s.farm.degradations ?? []).sort((a, b) => b.date.localeCompare(a.date));
  const [scores, setScores] = useState<Record<string, number>>({});
  const [form, setForm] = useState({ site: '', plotId: plots[0]?.id ?? '', note: '' });
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState('');

  const set = (id: string, v: number) => { setScores(s => ({ ...s, [id]: v })); setErr(''); setSaved(false); };

  const save = () => {
    if (!form.site.trim()) return setErr('Enter a site name.');
    const filled = Object.entries(scores).filter(([, v]) => v > 0);
    if (filled.length === 0) return setErr('Score at least one indicator.');
    const a: DegradationAssessment = { id: newId('deg'), date: new Date().toISOString().slice(0, 10), site: form.site, plotId: form.plotId, by: s.session?.user.id ?? '', scores, photos: [], note: form.note };
    farmChange({ op: 'upsert', kind: 'degradation', item: a });
    setScores({}); setSaved(true); setErr('');
  };

  const avg = (a: DegradationAssessment) => { const vals = Object.values(a.scores); return vals.length ? (vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(1) : '—'; };

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>Score land degradation indicators from the University of Juba survey framework. These assessments track EbA intervention impact over time.</p>

      <div className="grid2">
        <Field label="Site name"><input className="input" value={form.site} placeholder="e.g. Duk Padiet A" onChange={e => { setForm({ ...form, site: e.target.value }); setErr(''); setSaved(false); }} /></Field>
        <Field label="Nearest plot">
          <select className="input" value={form.plotId} onChange={e => setForm({ ...form, plotId: e.target.value })}>
            {plots.map(p => <option key={p.id} value={p.id}>{plotLabel(p, s.farm)}</option>)}
          </select>
        </Field>
      </div>

      <div className="col g6">
        <div className="section">Degradation indicators</div>
        <div className="sub" style={{ marginBottom: 4 }}>Tap a severity level for each indicator observed at this site.</div>
        {DEGRADATION_INDICATORS.map(ind => (
          <div key={ind.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--color-divider)' }}>
            <div style={{ fontSize: 13.5, marginBottom: 6 }}>{ind.label}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
              {SEVERITY.map(sv => (
                <button key={sv.v} className={'chip' + (scores[ind.id] === sv.v ? ' on' : '')} style={{ minHeight: 36, fontSize: 12, padding: '0 6px', ...(scores[ind.id] === sv.v ? { borderColor: sv.color, color: sv.color } : {}) }} onClick={() => set(ind.id, sv.v)}>{sv.label}</button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <textarea className="input" rows={2} placeholder="Notes (optional)" value={form.note} onChange={e => { setForm({ ...form, note: e.target.value }); setSaved(false); }} />
      {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}
      <button className="btn lg" onClick={save}>{saved ? 'Saved ✓' : 'Save assessment'}</button>

      {assessments.length > 0 && (
        <div>
          <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Past assessments</h2>
          {assessments.map(a => (
            <div key={a.id} className="rowg">
              <span><span style={{ display: 'block', fontSize: 14 }}>{a.site}</span><span className="sub">{a.date} · {a.by} · {Object.keys(a.scores).length} indicators scored</span></span>
              <span style={{ textAlign: 'right' }}><span className="head num" style={{ display: 'block', fontSize: 20 }}>{avg(a)}/3</span><span className="it" style={{ fontSize: 11, color: 'var(--color-accent-700)' }}>avg severity</span></span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
