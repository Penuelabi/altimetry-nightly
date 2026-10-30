import { useState } from 'react';
import { PROC, chainFor, editAllowed } from '@abuk/core';
import { runProduct } from './Register';
import { openRegister, tab, useApp } from '../store';

export function Process() {
  const s = useApp();
  // Products: everything already processed, then the usual product of each crop in the register.
  const products = [...new Set([...s.farm.runs.map(runProduct), ...s.farm.crops.map(c => chainFor(c.name).product)])];
  const [k, setK] = useState(products[0] ?? 'Balanites oil');
  const runs = s.farm.runs.filter(r => runProduct(r) === k).sort((a, b) => b.date.localeCompare(a.date));
  const run = runs[0];
  const sample = k === PROC.balanites.label ? PROC.balanites : k === PROC.moringa.label ? PROC.moringa : null;
  const tpl = chainFor(k);
  const p = run ? { intro: `Latest run, ${new Date(run.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}${run.crop ? ` · ${run.crop}` : ''}${run.plotIds?.length ? ` · plots ${run.plotIds.map(id => s.farm.plots.find(x => x.id === id)?.code ?? id).join(', ')}` : ''}. ${runs.length} run(s) recorded.`, steps: run.steps.filter(x => x.out).map(x => ({ name: x.name, out: x.out, note: '' })), foot: run.note }
    : sample ?? { intro: 'No run recorded yet. The usual steps are below; record a run to fill in the amounts.', steps: tpl.steps.map(name => ({ name, out: '—', note: '' })), foot: '' };
  const can = editAllowed(s.session?.user.role ?? '');
  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <select className="input" value={k} onChange={e => setK(e.target.value)} aria-label="Product">{products.map(x => <option key={x}>{x}</option>)}</select>
      <p className="body" style={{ fontSize: 13.5 }}>{p.intro}</p>
      <div style={{ position: 'relative', paddingLeft: 26 }}>
        <div style={{ position: 'absolute', left: 8, top: 10, bottom: 10, borderLeft: '1px solid var(--color-accent)' }} />
        {p.steps.map(st => (
          <div key={st.name} style={{ position: 'relative', padding: '8px 0 12px' }}>
            <span style={{ position: 'absolute', left: -24, top: 12, width: 13, height: 13, borderRadius: '50%', border: '1.5px solid var(--color-accent)', background: 'var(--color-bg)' }} />
            <div className="between"><span style={{ fontSize: 14 }}>{st.name}</span><span className="head num" style={{ fontSize: 20 }}>{st.out}</span></div>
            <div className="sub" style={{ lineHeight: 1.4 }}>{st.note}</div>
          </div>
        ))}
      </div>
      <div style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 10, fontSize: 12.5, color: 'var(--color-neutral-800)' }}>{p.foot}</div>
      {can && <button className="btn" onClick={() => openRegister('runs')}>+ Record a processing run</button>}
      <button className="btn plain" onClick={() => tab('market')}>List stock in the market</button>
    </div>
  );
}

export { Market } from './MarketBoard';
