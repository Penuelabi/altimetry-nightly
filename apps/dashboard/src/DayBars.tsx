import { useRef, useState } from 'react';

// Single-series daily bars: thin rounded-top bars, recessive grid, hover tooltip, table view.
export function DayBars({ data, height = 180 }: { data: { day: string; count: number; detail: string }[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const W = 1000, H = height, pad = { l: 34, r: 8, t: 10, b: 24 };
  const max = Math.max(4, ...data.map(d => d.count));
  const step = Math.ceil(max / 4), top = step * 4;
  const iw = (W - pad.l - pad.r) / data.length, bw = Math.max(2, Math.min(28, iw - 2));
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / top);
  const label = (d: string) => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  const every = Math.ceil(data.length / 10);
  if (table) return (
    <div className="tbl-wrap" style={{ maxHeight: 260 }}>
      <button className="link" onClick={() => setTable(false)}>Show chart</button>
      <table className="tbl"><thead><tr><th>Day</th><th style={{ textAlign: 'right' }}>Updates</th><th>By type</th></tr></thead>
        <tbody>{[...data].reverse().map(d => <tr key={d.day}><td>{label(d.day)}</td><td className="num" style={{ textAlign: 'right' }}>{d.count}</td><td>{d.detail}</td></tr>)}</tbody></table>
    </div>
  );
  const h = hover !== null ? data[hover] : null;
  return (
    <div className="chart" ref={box} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height }} role="img" aria-label="Updates per day">
        {[0, 1, 2, 3, 4].map(i => <g key={i}>
          <line x1={pad.l} x2={W - pad.r} y1={y(step * i)} y2={y(step * i)} stroke="var(--grid)" vectorEffect="non-scaling-stroke" />
          <text x={pad.l - 6} y={y(step * i) + 4} textAnchor="end" fontSize="11" fill="var(--color-neutral-700)" style={{ fontVariantNumeric: 'tabular-nums' }}>{step * i}</text>
        </g>)}
        {data.map((d, i) => {
          const x = pad.l + i * iw + (iw - bw) / 2, yy = y(d.count), hh = H - pad.b - yy;
          return <g key={d.day}>
            {d.count > 0 && <path d={`M${x},${H - pad.b} V${yy + Math.min(4, hh)} Q${x},${yy} ${x + Math.min(4, bw / 2)},${yy} H${x + bw - Math.min(4, bw / 2)} Q${x + bw},${yy} ${x + bw},${yy + Math.min(4, hh)} V${H - pad.b} Z`} fill="var(--bar)" opacity={hover === null || hover === i ? 1 : 0.45} />}
            <rect x={pad.l + i * iw} y={pad.t} width={iw} height={H - pad.t - pad.b} fill="transparent" onMouseEnter={() => setHover(i)} />
            {i % every === 0 && <text x={pad.l + i * iw + iw / 2} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--color-neutral-700)">{label(d.day)}</text>}
          </g>;
        })}
        <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="var(--color-neutral-500)" vectorEffect="non-scaling-stroke" />
      </svg>
      {h && hover !== null && (
        <div className="tip" style={{ left: `${((pad.l + hover * iw + iw / 2) / W) * 100}%`, top: `${(y(h.count) / H) * height}px` }}>
          <strong>{label(h.day)}: {h.count} update{h.count === 1 ? '' : 's'}</strong>{h.detail && <><br />{h.detail}</>}
        </div>
      )}
      <button className="link" style={{ fontSize: 12 }} onClick={() => setTable(true)}>Show as table</button>
    </div>
  );
}
