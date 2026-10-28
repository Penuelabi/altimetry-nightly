import { recessDays, ZONES, type Task } from '@abuk/core';
import { go, openRegister, setState, tab, useApp } from '../store';
import { Check, Stat } from '../ui';
import { basinOpacity, moundLines, toggleTask, useGreet, useL } from './common';
import { usePlace } from '../net';

const MONTHS = 'JFMAMJJASOND'.split('');
const monthColor = (i: number) => (i === new Date().getMonth() ? 'var(--color-accent-700)' : 'var(--color-neutral-700)');
const dateLine = () => new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).replace(',', '');

export function Home() {
  const s = useApp();
  return s.homeLayout === 'almanac' ? <Almanac /> : s.homeLayout === 'field' ? <Field /> : <Ledger />;
}

const TaskRow = ({ t, round, meta }: { t: Task; round?: boolean; meta?: boolean }) => (
  <button className="row" onClick={() => toggleTask(t.id)}>
    <Check on={t.done} round={round} />
    <span style={{ flex: 1 }}>
      <span style={{ display: 'block', fontSize: 14, lineHeight: 1.35, textDecoration: t.done ? 'line-through' : 'none' }}>{t.t}</span>
      {meta && <span className="sub">{t.zone} · {t.who}</span>}
    </span>
  </button>
);

function Ledger() {
  const s = useApp(), L = useL(), greet = useGreet();
  const today = s.tasks.filter(t => t.due === 'today').slice(0, 3);
  const open = s.tasks.filter(t => !t.done).length;
  const BTN: [string, () => void, boolean, string?][] = [
    ['Log harvest', () => go('harvest'), true], ['Map a plot', () => tab('map'), true], ['Processing', () => go('process'), false],
    ['Flood model', () => go('flood'), false], ['Crop check', () => go('monitor'), true], ['Data sources', () => go('sources'), false],
    ['Farm register · plots, crops, groups', () => openRegister('plots'), false, 'span2'],
    ['Field tools · SMS alerts, voice, payout, store…', () => go('tools'), true, 'span2']
  ];
  return (
    <div className="pad g18" style={{ paddingTop: 18 }}>
      <div>
        <div className="kick muted num">{dateLine()} · Flood season, week 11</div>
        <h1 className="h1" style={{ margin: '6px 0 8px', fontSize: 34, lineHeight: 1.02, letterSpacing: '-.01em' }}>{greet}. The basin is draining.</h1>
        <p className="body">The White Nile at Bor fell 3 cm overnight. Mound row B‑05 is still under water; the rest of the Balanites rows are clear. Recession sowing opens in about <strong style={{ fontWeight: 600 }}>{recessDays()} days</strong>.</p>
      </div>
      <button onClick={() => go('flood')} className="box grid3" style={{ background: 'transparent', padding: 0, textAlign: 'left' }}>
        <div style={{ padding: '10px 12px', borderRight: '1px solid var(--color-divider)' }}><div className="lbl">Bor gauge</div><div className="head num" style={{ fontSize: 24 }}>4.12 m</div><div style={{ fontSize: 11.5, color: 'var(--color-accent-700)' }}>↓ 3 cm / day</div></div>
        <div style={{ padding: '10px 12px', borderRight: '1px solid var(--color-divider)' }}><div className="lbl">Basin depth</div><div className="head num" style={{ fontSize: 24 }}>0.92 m</div><div className="sub">mounds 1.0 m</div></div>
        <div style={{ padding: '10px 12px' }}><div className="lbl">Today</div><div className="head num" style={{ fontSize: 24 }}>34°</div><div className="sub">no rain</div></div>
      </button>
      <div>
        <div className="between rule-b"><h2 className="h2">{L.tasks}</h2><button className="link" onClick={() => go('tasks')}>{L.seeAll} · {open} open</button></div>
        {today.map(t => <TaskRow key={t.id} t={t} meta />)}
      </div>
      <div>
        <h2 className="h2 rule" style={{ marginBottom: 4 }}>{L.zones}</h2>
        {ZONES.map(z => (
          <button key={z.n} onClick={() => tab('map')} className="row" style={{ display: 'grid', gridTemplateColumns: '22px 1fr auto', gap: 10, alignItems: 'baseline', padding: '10px 0' }}>
            <span className="head num" style={{ fontSize: 20, color: 'var(--color-accent)' }}>{z.n}</span>
            <span><span style={{ display: 'block', fontSize: 14 }}>{z.name} <span style={{ color: 'var(--color-neutral-700)', fontSize: 12 }}>· {z.ha}</span></span><span className="sub">{z.crops}</span></span>
            <span className="it" style={{ fontSize: 12, color: 'var(--color-accent-800)' }}>{z.status}</span>
          </button>
        ))}
      </div>
      <div className="grid2">
        {BTN.map(([label, fn, accent, cls]) => <button key={label} className={`btn${accent ? '' : ' plain'} ${cls ?? ''}`} onClick={fn}>{label}</button>)}
      </div>
    </div>
  );
}

function Almanac() {
  const s = useApp(), L = useL(), greet = useGreet();
  const today = s.tasks.filter(t => t.due === 'today').slice(0, 3);
  const hatch = (c: string, w: number) => `repeating-linear-gradient(${w}deg,${c} 0 1px,transparent 1px 5px)`;
  const cell = { display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontStyle: 'italic', color: 'var(--color-neutral-700)', borderLeft: '1px solid var(--color-divider)' } as const;
  const now = new Date(), yearPct = (now.getMonth() + now.getDate() / 31) / 12 * 100;
  return (
    <div className="pad g18" style={{ paddingTop: 18 }}>
      <div className="kick muted">{greet} · {dateLine()}</div>
      <div className="box" style={{ padding: '14px 12px 12px' }}>
        <div className="num" style={{ display: 'grid', gridTemplateColumns: 'repeat(12,1fr)', fontSize: 10, textAlign: 'center' }}>{MONTHS.map((m, i) => <span key={i} style={{ color: monthColor(i) }}>{m}</span>)}</div>
        <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'repeat(12,1fr)', height: 58, marginTop: 6, borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)' }}>
          <div style={{ gridColumn: '1 / 2', background: hatch('var(--color-accent-200)', 90) }} />
          <div style={{ ...cell, gridColumn: '2 / 5' }}>Dry</div>
          <div style={{ ...cell, gridColumn: '5 / 8' }}>Rains</div>
          <div style={{ ...cell, gridColumn: '8 / 12', color: 'var(--color-neutral-900)', background: 'repeating-linear-gradient(135deg,var(--color-neutral-300) 0 1.5px,transparent 1.5px 6px)' }}>Flood</div>
          <div style={{ ...cell, gridColumn: '12 / 13', fontSize: 10, color: 'var(--color-accent-800)', background: hatch('var(--color-accent-200)', 90) }}>Rec.</div>
          <div style={{ position: 'absolute', top: -6, bottom: -6, left: `${yearPct}%`, borderLeft: '2px solid var(--color-accent)' }} />
        </div>
        <div className="between sub" style={{ marginTop: 10 }}><span>Today ▲ late flood</span><span>Recession opens ~4 Dec</span></div>
      </div>
      <div>
        <div className="kick">Next window · in {recessDays()} days</div>
        <h1 className="h1" style={{ margin: '4px 0 6px', fontSize: 32 }}>Sow the recession silt.</h1>
        <p className="body">As water leaves the basin, broadcast cowpea, Feterita sorghum and jute mallow between the Balanites mounds. Seed stock check is on this week's list.</p>
      </div>
      <div className="grid3" style={{ borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)' }}>
        {[['Cowpea', '6 groups · 7 ha'], ['Sorghum', 'Feterita · 9 ha'], ['Kudra', 'jute · 2 ha']].map(([n, d], i) => (
          <div key={n} style={{ padding: i ? '10px 8px' : '10px 4px', borderLeft: i ? '1px solid var(--color-divider)' : undefined }}><div className="head" style={{ fontSize: 22 }}>{n}</div><div className="sub">{d}</div></div>
        ))}
      </div>
      <div>
        <div className="between rule-b"><h2 className="h2">{L.tasks}</h2><button className="link" onClick={() => go('tasks')}>{L.seeAll}</button></div>
        {today.map(t => <TaskRow key={t.id} t={t} round />)}
      </div>
      <button className="btn" onClick={() => tab('season')}>Open full crop calendar</button>
    </div>
  );
}

const ZINFO = {
  basin: { kicker: 'Zone 3 · 22 ha · 0.92 m water', head: 'Mounds clear except B‑05.', body: `Balanites anchor. Water is falling 2–3 cm a day; recession sowing of cowpea, sorghum and kudra follows in about ${recessDays()} days.`, stats: [['Trees', '1,936'], ['Mound rows', '24'], ['Groups', '7']] },
  slope: { kicker: 'Zone 2 · 8 ha · 0.22 m water', head: 'Groundnut lifted; sesame drying.', body: 'Transition soils between ridge and basin. Rainfed groundnut, sesame, millet and okra finish before the flood climbs the slope.', stats: [['Plots', '11'], ['Slope', '0.6%'], ['Groups', '3']] },
  ridge: { kicker: 'Zone 1 · 10 ha · dry', head: 'Moringa cut due on R‑02.', body: 'Safe from flood. High‑density Moringa leaf blocks, gum arabic tapping rows, shea and tamarind on the boundary.', stats: [['Moringa', '62k'], ['Gum trees', '410'], ['Groups', '2']] }
} as const;
const ZONE_TASK = { basin: 'Basin', ridge: 'Ridge', slope: 'Slope' } as const;

function Field() {
  const s = useApp(), L = useL();
  const z = ZINFO[s.zone], place = usePlace();
  const lbl = { fontFamily: 'Lora', fontSize: 10, letterSpacing: 1.2 };
  return (
    <div className="col">
      <div style={{ position: 'relative', borderBottom: '1px solid var(--color-divider)' }}>
        <svg viewBox="0 0 360 250" width="100%" style={{ display: 'block' }}>
          <rect x="0" y="0" width="360" height="70" fill="var(--color-accent-100)" />
          <rect x="0" y="70" width="360" height="50" fill="var(--color-neutral-100)" />
          <rect x="0" y="120" width="360" height="130" fill="var(--color-neutral-200)" />
          <rect x="0" y="120" width="360" height="130" fill="var(--color-neutral-500)" fillOpacity={basinOpacity()} />
          <path d="M0 70 C90 62 180 78 360 68" fill="none" stroke="var(--color-neutral-500)" strokeDasharray="3 3" />
          <path d="M0 120 C100 112 220 128 360 118" fill="none" stroke="var(--color-neutral-500)" strokeDasharray="3 3" />
          {moundLines([150, 163, 176, 189, 202, 215, 228, 241]).map(l => <line key={l.y} x1="20" x2="340" y1={l.y} y2={l.y} stroke={l.c} strokeWidth="2" />)}
          <text x="14" y="22" {...lbl} fill="var(--color-accent-800)">1 · DRY RIDGE · 10 HA</text>
          <text x="14" y="88" {...lbl} fill="var(--color-neutral-700)">2 · SLOPE · 8 HA</text>
          <text x="14" y="138" {...lbl} fill="var(--color-neutral-900)">3 · FLOODPLAIN BASIN · 22 HA</text>
          <circle cx="300" cy="190" r="5" fill="none" stroke="var(--color-accent)" strokeWidth="2" />
          <circle cx="300" cy="190" r="12" fill="none" stroke="var(--color-accent)" strokeOpacity=".4" />
        </svg>
        <div className="num" style={{ position: 'absolute', right: 12, top: 10, fontSize: 11, background: 'var(--color-bg)', border: '1px solid var(--color-divider)', borderRadius: 'var(--radius-sm)', padding: '3px 6px' }}>{place.lat.toFixed(3)}° N · {place.lon.toFixed(3)}° E</div>
      </div>
      <div className="pad g14" style={{ paddingTop: 14 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {(['ridge', 'slope', 'basin'] as const).map(k => (
            <button key={k} className={'chip' + (s.zone === k ? ' on' : '')} style={{ flex: 1, minHeight: 40 }} onClick={() => setState({ zone: k })}>{k[0].toUpperCase() + k.slice(1)}</button>
          ))}
        </div>
        <div>
          <div className="kick">{z.kicker}</div>
          <h1 className="h1" style={{ margin: '4px 0 6px', fontSize: 30, lineHeight: 1.05 }}>{z.head}</h1>
          <p className="body">{z.body}</p>
        </div>
        <div className="grid3" style={{ borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)' }}>
          {z.stats.map(([k, v]) => <Stat key={k} k={k} v={v} />)}
        </div>
        <div>
          <div style={{ fontSize: 13, color: 'var(--color-neutral-700)', marginBottom: 2 }}>{L.tasks} in this zone</div>
          {s.tasks.filter(t => t.zone === ZONE_TASK[s.zone]).slice(0, 3).map(t => <TaskRow key={t.id} t={t} />)}
        </div>
        <div className="grid2">
          <button className="btn" onClick={() => go('plot')}>Open plot B‑07</button>
          <button className="btn plain" onClick={() => go('flood')}>Flood model</button>
        </div>
      </div>
    </div>
  );
}

