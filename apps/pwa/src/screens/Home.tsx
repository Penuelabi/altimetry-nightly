import { briefing, DEFAULT_MODEL, recessDays, SLOPE_STEP, ZONES, type Task } from '@abuk/core';
import { go, openRegister, setState, tab, useApp } from '../store';
import { Check, Stat } from '../ui';
import { allChecks, basinOpacity, moundLines, toggleTask, useGreet, useHereData, useL, useModel } from './common';
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
  const s = useApp(), L = useL(), place = usePlace(), model = useModel();
  const { weather, sat } = useHereData();
  const station = s.lastPull?.stations.rows[0];
  const b = briefing({
    now: new Date(), name: s.session?.user.name ?? '', place,
    gauge: (s.gauge ?? []).filter(g => g.status === 'ok' && g.v != null).map(g => ({ at: g.at, v: g.v as number })),
    station: station ? { name: station.name, km: station.km, level: station.lastLevel, vs2yr: station.vs2yr, ratePerDay: station.ratePerDay, levelClass: station.levelClass } : null,
    checks: allChecks(s).flatMap(c => (c.lat != null && c.lon != null ? [{ ...c, lat: c.lat, lon: c.lon }] : [])),
    weather, satellite: sat, rate: { v: model.rate, measured: model.rateSrc !== DEFAULT_MODEL.rateSrc }
  });
  const sow = recessDays(model);
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
        <div className="kick muted num">{b.kicker}</div>
        <h1 className="h1" style={{ margin: '6px 0 8px', fontSize: 34, lineHeight: 1.02, letterSpacing: '-.01em' }}>{b.headline}</h1>
        <p className="body">{b.body.join(' ')}{model.measured && sow != null && sow > 0 ? <> Recession sowing opens in about <strong style={{ fontWeight: 600 }}>{sow} days</strong> (flood model, from measurements).</> : null}</p>
      </div>
      <button onClick={() => go('flood')} className="box grid3" style={{ background: 'transparent', padding: 0, textAlign: 'left' }}>
        {b.tiles.map((t, i) => (
          <div key={t.k} style={{ padding: '10px 12px', borderRight: i < 2 ? '1px solid var(--color-divider)' : undefined, minWidth: 0 }}>
            <div className="lbl">{t.k}</div><div className="head num" style={{ fontSize: 24 }}>{t.v}</div><div className="sub" style={{ lineHeight: 1.3 }}>{t.s}</div>
          </div>
        ))}
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
  const s = useApp(), L = useL(), greet = useGreet(), sow = recessDays(useModel());
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
        <div className="kick">Next window · {sow == null ? 'water not falling yet' : sow <= 0 ? 'open now' : `in ${sow} days`}</div>
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
  basin: { kicker: 'Zone 3 · 22 ha', head: 'Balanites mounds and recession crops.', body: 'Balanites anchor on raised mounds; recession sowing of cowpea, sorghum and kudra follows the falling water.', stats: [['Trees', '1,936'], ['Mound rows', '24'], ['Groups', '7']] },
  slope: { kicker: 'Zone 2 · 8 ha · 0.22 m water', head: 'Groundnut lifted; sesame drying.', body: 'Transition soils between ridge and basin. Rainfed groundnut, sesame, millet and okra finish before the flood climbs the slope.', stats: [['Plots', '11'], ['Slope', '0.6%'], ['Groups', '3']] },
  ridge: { kicker: 'Zone 1 · 10 ha · dry', head: 'Moringa cut due on R‑02.', body: 'Safe from flood. High‑density Moringa leaf blocks, gum arabic tapping rows, shea and tamarind on the boundary.', stats: [['Moringa', '62k'], ['Gum trees', '410'], ['Groups', '2']] }
} as const;
const ZONE_TASK = { basin: 'Basin', ridge: 'Ridge', slope: 'Slope' } as const;

function Field() {
  const s = useApp(), L = useL();
  const z = ZINFO[s.zone], place = usePlace(), model = useModel(), sow = recessDays(model);
  // Live line for the basin and slope: fitted water depth and fall rate near the phone.
  const live = s.zone === 'ridge' ? '' : (() => {
    const d = s.zone === 'basin' ? model.d0 : Math.max(0, model.d0 - SLOPE_STEP);
    return ` · ${Math.round(d * 100)} cm water${model.measured ? '' : ' (estimate)'}`;
  })();
  const lbl = { fontFamily: 'Lora', fontSize: 10, letterSpacing: 1.2 };
  return (
    <div className="col">
      <div style={{ position: 'relative', borderBottom: '1px solid var(--color-divider)' }}>
        <svg viewBox="0 0 360 250" width="100%" style={{ display: 'block' }}>
          <rect x="0" y="0" width="360" height="70" fill="var(--color-accent-100)" />
          <rect x="0" y="70" width="360" height="50" fill="var(--color-neutral-100)" />
          <rect x="0" y="120" width="360" height="130" fill="var(--color-neutral-200)" />
          <rect x="0" y="120" width="360" height="130" fill="var(--color-neutral-500)" fillOpacity={basinOpacity(model.d0)} />
          <path d="M0 70 C90 62 180 78 360 68" fill="none" stroke="var(--color-neutral-500)" strokeDasharray="3 3" />
          <path d="M0 120 C100 112 220 128 360 118" fill="none" stroke="var(--color-neutral-500)" strokeDasharray="3 3" />
          {moundLines([150, 163, 176, 189, 202, 215, 228, 241], model.d0).map(l => <line key={l.y} x1="20" x2="340" y1={l.y} y2={l.y} stroke={l.c} strokeWidth="2" />)}
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
          <div className="kick">{z.kicker}{live}</div>
          <h1 className="h1" style={{ margin: '4px 0 6px', fontSize: 30, lineHeight: 1.05 }}>{z.head}</h1>
          <p className="body">{z.body}{s.zone === 'basin' ? ` ${model.rate > 0 ? `Water is falling ${(model.rate * 100).toFixed(1)} cm a day (${model.rateSrc === DEFAULT_MODEL.rateSrc ? 'design estimate' : 'measured'})${sow != null && sow > 0 ? `; the basin should be dry in about ${sow} days.` : '.'}` : 'The water is not falling yet.'}` : ''}</p>
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

