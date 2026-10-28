import { useState } from 'react';
import { LISTINGS, PROC, chainFor, editAllowed } from '@abuk/core';
import { runProduct } from './Register';
import { go, openRegister, record, setState, tab, useApp } from '../store';

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

export function Market() {
  const s = useApp();
  const [note, setNote] = useState('');
  const msg = s.offer === 'accepted' ? 'Accepted. Pickup booked for 3 Nov at Bor; Group 4 lead notified.' : s.offer === 'countered' ? 'Counter sent at $14.00 / L. Waiting for reply.' : '';
  const answer = (offer: 'accepted' | 'countered') => { setState({ offer }); record('offer', { buyer: 'Nile Botanicals', litres: 40, price: offer === 'accepted' ? 13.5 : 14, answer: offer }); };
  return (
    <div className="pad">
      <div>
        <div className="kick muted">Cooperative sales · 2026 season</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}><span className="head num" style={{ fontSize: 42 }}>{s.offer === 'accepted' ? '$19,180' : '$18,640'}</span><span style={{ fontSize: 12.5, color: 'var(--color-accent-700)' }}>shared across 160 farmers</span></div>
      </div>
      {s.offer === 'open' && (
        <div className="card accent">
          <div className="kick">New offer · Juba</div>
          <div style={{ fontSize: 14, lineHeight: 1.45 }}>Nile Botanicals asks for <strong style={{ fontWeight: 600 }}>40 L Balanites oil</strong> at $13.50 / L, collected at Bor.</div>
          <div className="grid2" style={{ gap: 8 }}>
            <button className="btn plain md" onClick={() => answer('countered')}>Counter</button>
            <button className="btn md" onClick={() => answer('accepted')}>Accept · $540</button>
          </div>
        </div>
      )}
      {msg && <div className="it" style={{ fontSize: 13, color: 'var(--color-accent-800)', borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)', padding: '8px 0' }}>{msg}</div>}
      <div>
        <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Our listings</h2>
        {LISTINGS.map(l => (
          <div key={l.name} className="rowg" style={{ padding: '10px 0' }}>
            <span><span style={{ display: 'block', fontSize: 14 }}>{l.name}</span><span className="sub">{l.stock} in stock · {l.offers}</span></span>
            <span style={{ textAlign: 'right' }}><span className="head num" style={{ display: 'block', fontSize: 20 }}>{l.price}</span><span style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}>{l.unit}</span></span>
          </div>
        ))}
      </div>
      {note && <div className="msg">{note}</div>}
      <div className="grid2">
        <button className="btn plain" onClick={() => go('process')}>Stock & processing</button>
        <button className="btn" onClick={() => setNote('Listing new produce opens once the buyer marketplace is connected. Offers from buyers already arrive here.')}>List produce</button>
      </div>
    </div>
  );
}
