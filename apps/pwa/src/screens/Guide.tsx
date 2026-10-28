import { SPECIES } from '@abuk/core';
import { openSpecies, useApp } from '../store';
import { Chevron } from '../ui';

export function Guide() {
  const groups = [{ label: 'Trees', g: 'trees' }, { label: 'Field & recession crops', g: 'field' }] as const;
  return (
    <div className="pad" style={{ paddingTop: 14, gap: 4 }}>
      <p className="body" style={{ fontSize: 13.5, marginBottom: 8 }}>Twelve species grown on the Abuk land, all native or long‑naturalised in South Sudan. Works without signal.</p>
      {groups.map(g => (
        <div key={g.g}>
          <div className="kick sm" style={{ padding: '12px 0 4px', borderBottom: '1px solid var(--color-divider)' }}>{g.label}</div>
          {SPECIES.filter(x => x.g === g.g).map(x => (
            <button key={x.key} className="row hov" onClick={() => openSpecies(x.key)} style={{ display: 'grid', gridTemplateColumns: '1fr auto 16px', gap: 8, alignItems: 'center', padding: '10px 0', minHeight: 48 }}>
              <span><span className="head" style={{ display: 'block', fontSize: 19, fontWeight: 600, lineHeight: 1.1 }}>{x.name}</span><span className="it" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{x.sci}</span></span>
              <span style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>{x.ar}</span>
              <Chevron />
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

export function Species() {
  const s = useApp();
  const sp = SPECIES.find(x => x.key === s.species) ?? SPECIES[0];
  return (
    <div className="pad g14">
      <div>
        <div className="it" style={{ fontSize: 12.5, color: 'var(--color-neutral-700)' }}>{sp.sci}</div>
        <h1 className="h1" style={{ margin: '2px 0 4px', fontSize: 36, lineHeight: 1 }}>{sp.name}</h1>
        <div style={{ fontSize: 13, color: 'var(--color-accent-800)' }}>{sp.ar}{sp.local ? ` · ${sp.local}` : ''}</div>
      </div>
      <div className="photo" style={{ height: 150 }}>Field photograph · {sp.name}</div>
      <div className="grid2" style={{ gap: 0, borderTop: '1px solid var(--color-divider)' }}>
        <div style={{ padding: '9px 0', borderBottom: '1px solid var(--color-divider)' }}><div className="lbl">Zone</div><div style={{ fontSize: 14 }}>{sp.zone}</div></div>
        <div style={{ padding: '9px 0 9px 10px', borderBottom: '1px solid var(--color-divider)', borderLeft: '1px solid var(--color-divider)' }}><div className="lbl">Season</div><div style={{ fontSize: 14 }}>{sp.season}</div></div>
      </div>
      <div><h2 className="h2 h20" style={{ marginBottom: 4 }}>Growing it here</h2><p className="body">{sp.notes}</p></div>
      <div><h2 className="h2 h20" style={{ marginBottom: 4 }}>Uses</h2><p className="body">{sp.uses}</p></div>
      <div style={{ borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)', padding: '10px 0' }}>
        <div className="kick sm" style={{ marginBottom: 4 }}>Value chain</div>
        <div style={{ fontSize: 13, lineHeight: 1.55 }}>{sp.chain}</div>
      </div>
    </div>
  );
}
