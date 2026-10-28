import { SEASON } from '@abuk/core';
import { openSpecies } from '../store';
import { usePlace } from '../net';

const MONTHS = 'JFMAMJJASOND'.split('');
const COLS = '92px repeat(12,1fr)';

export function Season() {
  const m = new Date().getMonth(), place = usePlace();
  const hatch = 'repeating-linear-gradient(90deg,var(--color-accent-200) 0 1px,transparent 1px 4px)';
  const lab = { fontSize: 9.5, fontStyle: 'italic', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-neutral-700)' } as const;
  return (
    <div className="pad g12" style={{ padding: '16px 14px 24px' }}>
      <p className="body" style={{ margin: '0 4px', fontSize: 13.5 }}>{place.payam} runs on the river. Plant by water, not by date: the bars below shift when the flood model updates.</p>
      <div className="num" style={{ display: 'grid', gridTemplateColumns: COLS, fontSize: 9.5, textAlign: 'center', borderBottom: '1px solid var(--color-divider)', paddingBottom: 4 }}>
        <span />{MONTHS.map((l, i) => <span key={i} style={{ color: i === m ? 'var(--color-accent-700)' : 'var(--color-neutral-700)' }}>{l}</span>)}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: COLS, height: 22 }}>
        <span style={{ fontSize: 11, color: 'var(--color-neutral-700)', alignSelf: 'center' }}>Water</span>
        <div style={{ gridColumn: '2 / 3', background: hatch }} />
        <div style={{ ...lab, gridColumn: '3 / 6' }}>dry</div>
        <div style={{ ...lab, gridColumn: '6 / 9', borderLeft: '1px solid var(--color-divider)' }}>rains</div>
        <div style={{ ...lab, gridColumn: '9 / 13', color: 'var(--color-text)', background: 'repeating-linear-gradient(135deg,var(--color-neutral-300) 0 1.5px,transparent 1.5px 5px)' }}>flood</div>
        <div style={{ gridColumn: '13 / 14', background: hatch }} />
      </div>
      {SEASON.map(g => (
        <div key={g.zone}>
          <div className="kick sm" style={{ padding: '8px 0 4px', borderBottom: '1px solid var(--color-divider)' }}>{g.zone}</div>
          {g.rows.map(([name, key, bars]) => (
            <button key={key} className="hov" onClick={() => openSpecies(key)} style={{ width: '100%', display: 'grid', gridTemplateColumns: COLS, alignItems: 'center', minHeight: 30, border: 'none', borderBottom: '1px solid var(--color-divider)', background: 'transparent', padding: 0, textAlign: 'left' }}>
              <span style={{ fontSize: 12, gridColumn: '1 / 2', gridRow: 1 }}>{name}</span>
              {bars.map(([a, b, k], i) => <span key={i} style={{ gridRow: 1, gridColumn: `${a + 2} / ${b + 3}`, height: 12, border: '1px solid var(--color-accent)', borderRadius: 'var(--radius-sm)', background: k === 'h' ? 'var(--color-accent-300)' : 'transparent' }} />)}
              <span style={{ gridRow: 1, gridColumn: `${m + 2} / ${m + 3}`, justifySelf: 'center', width: 0, height: '100%', borderLeft: '1px dashed var(--color-accent-700)' }} />
            </button>
          ))}
        </div>
      ))}
      <div style={{ display: 'flex', gap: 14, fontSize: 11, color: 'var(--color-neutral-700)', padding: '0 4px' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 14, height: 9, border: '1px solid var(--color-accent)', borderRadius: 2 }} />growing</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 14, height: 9, border: '1px solid var(--color-accent)', background: 'var(--color-accent-300)', borderRadius: 2 }} />harvest</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 0, height: 10, borderLeft: '1px dashed var(--color-accent-700)' }} />today</span>
      </div>
    </div>
  );
}
