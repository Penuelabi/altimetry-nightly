import type { CSSProperties, ReactNode } from 'react';

export const Icon = ({ d, size = 22, sw = 1.5, color = 'currentColor' }: { d: string; size?: number; sw?: number; color?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
);
export const Chevron = () => <Icon d="m9 18 6-6-6-6" size={16} sw={1.6} color="var(--color-accent)" />;

export function Seg<T extends string | number>({ items, value, onPick, fontSize }: { items: [T, string][]; value: T; onPick: (v: T) => void; fontSize?: number }) {
  return (
    <div className="seg">
      {items.map(([k, label]) => <button key={String(k)} className={k === value ? 'on' : ''} style={fontSize ? { fontSize } : undefined} onClick={() => onPick(k)}>{label}</button>)}
    </div>
  );
}

export const Toggle = ({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) => (
  <button className={'toggle' + (on ? ' on' : '')} onClick={onClick} aria-label={label} aria-pressed={on}><span /></button>
);

export const Stat = ({ k, v, style }: { k: string; v: ReactNode; style?: CSSProperties }) => (
  <div className="stat" style={style}><div className="lbl">{k}</div><div className="stat-v">{v}</div></div>
);

export const Check = ({ on, round, size = 20 }: { on: boolean; round?: boolean; size?: number }) => (
  <span className="check" style={{ width: size, height: size, borderRadius: round ? '50%' : undefined }}>{on ? '✓' : ''}</span>
);

export const H2 = ({ children, right }: { children: ReactNode; right?: ReactNode }) => right
  ? <div className="between rule-b"><h2 className="h2 h20">{children}</h2>{right}</div>
  : <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>{children}</h2>;

export const Field = ({ label, children }: { label: ReactNode; children: ReactNode }) => <label className="field">{label}{children}</label>;

export const Msg = ({ children }: { children: ReactNode }) => children ? <div className="msg">{children}</div> : null;
