import { basinDepth } from '@abuk/core';
import { go, openSpecies } from '../store';
import { Stat } from '../ui';

export function Plot() {
  const stats: [string, string][] = [['Area', '0.62 ha'], ['Elevation', '409.6 m'], ['Slope', '0.3 %'], ['Mound', '1.00 m'], ['Soil', 'Vertisol'], ['Water', basinDepth(0).toFixed(2) + ' m']];
  const trees: [string, string][] = [['Balanites, grafted 2024', '82'], ['Balanites, wild', '6 (GPS missing)'], ['First fruit expected', 'Jan 2027'], ['Centroid', '7.7312° N, 31.4022° E']];
  return (
    <div className="pad">
      <div>
        <div className="kick">Zone 3 · Basin · Mixed plot</div>
        <h1 className="h1" style={{ margin: '4px 0 6px', fontSize: 32 }}>88 grafted Balanites on a one‑metre mound.</h1>
        <p className="body">Worked by Group 4 (12 farmers) with two individual strips held by Ayen Kuol and Deng Bol. Intercropped with cowpea and jute mallow after the water drops.</p>
      </div>
      <div className="grid3" style={{ borderTop: '1px solid var(--color-divider)' }}>
        {stats.map(([k, v]) => <Stat key={k} k={k} v={v} style={{ padding: '9px 6px 9px 0', borderBottom: '1px solid var(--color-divider)' }} />)}
      </div>
      <div>
        <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Trees</h2>
        {trees.map(([k, v]) => <div key={k} className="rowg" style={{ padding: '8px 0', fontSize: 13.5 }}><span>{k}</span><span className="num" style={{ color: 'var(--color-neutral-700)' }}>{v}</span></div>)}
      </div>
      <div className="grid2">
        <button className="btn" onClick={() => go('harvest')}>Log harvest</button>
        <button className="btn plain" onClick={() => openSpecies('balanites')}>Balanites guide</button>
        <button className="btn span2" onClick={() => go('monitor')}>Record a crop check for B‑07</button>
      </div>
    </div>
  );
}
