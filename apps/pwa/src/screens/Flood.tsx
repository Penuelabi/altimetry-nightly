import { useState } from 'react';
import { MOUNDS, SLOPE_STEP, basinDepth, bulletinInputs, dayLabel, editAllowed, headline, moundRows, nextRise, plantAlert, recessDays, slopeDepth, soilWord, type BulletinInputs, type Model, type PullResult } from '@abuk/core';
import { useHereData, useModel, useMounds } from './common';
import type { Weather } from '../weather';
import { farmChange, go, useApp } from '../store';
import { useOnline, usePlace } from '../net';

const ago = (iso: string) => {
  const m = Math.round((Date.now() - Date.parse(iso)) / 60000);
  return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};

const r0 = (x: number) => Math.round(x);
const dateOf = (iso: string) => (iso ? new Date(iso.slice(0, 10)).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '');

// Model inputs: measured or downloaded values only; "—" where there is no data yet.
// Local values (weather at the GPS point, satellite within 2 km) come first; the county bulletin fills the rest.
function inputs(p: PullResult | null, m: Model, w: Weather | null, sat: { floodPct: number | null; soil: number | null; radiusKm: number } | null, b: BulletinInputs | null) {
  const near = p?.stations.rows[0];
  const ifs = p?.ifs[0]?.values ?? {};
  const pick = (re: RegExp) => { const k = Object.keys(ifs).find(x => re.test(x)); return k ? ifs[k] : null; };
  const soil = sat?.soil ?? p?.gee.soilMoisture ?? b?.smRoot ?? null, flood = sat?.floodPct ?? p?.gee.floodExtentPct ?? null;
  const ifsRunoff = pick(/runoff|^ro$/i);
  const local = w ? `Open‑Meteo at your GPS point, ${new Date(w.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : '';
  const county = b ? `${p?.bulletin?.county} county bulletin, data to ${dateOf(b.dataEnd)}` : '';
  const either = <T,>(lv: T | null | undefined, bv: T | null | undefined) => (lv != null ? { v: lv, src: local } : bv != null ? { v: bv, src: county } : { v: null, src: 'loads with signal' });
  const rain30 = either(w?.rain30, b?.rain30), et30 = either(w?.et30, b?.et30);
  const wb = w?.rain30 != null && w.et30 != null ? { v: w.rain30 - w.et30, src: local } : b?.wb30 != null ? { v: b.wb30, src: county } : { v: null, src: 'loads with signal' };
  const runoff = b?.runoff30 != null ? { v: `${b.runoff30.toFixed(1)} mm`, src: `${county}${b.runoff30Class ? ` · ${b.runoff30Class}` : ''}` } : ifsRunoff != null ? { v: ifsRunoff.toFixed(1), src: 'ECMWF IFS, nearest station' } : { v: '—', src: 'pull data sources to load' };
  const wk = (x: BulletinInputs['week1']) => (x.median != null ? `${r0(x.median)} mm${x.p20 != null && x.p80 != null ? ` (${r0(x.p20)}–${r0(x.p80)})` : ''}` : '—');
  const wetDays = b?.pWetByDay.filter(d => d.p >= 0.5).map(d => d.day) ?? [];
  return [
    { k: 'Water depth now (model start)', v: `${Math.round(m.d0 * 100)} cm`, src: m.d0Src },
    { k: 'Water level change', v: `${m.rate >= 0 ? '−' : '+'}${Math.abs(m.rate * 100).toFixed(1)} cm/day`, src: m.rateSrc },
    { k: 'Rain forecast, next 7 days', v: w?.rainNext7 != null ? `${w.rainNext7} mm` : b ? wk(b.week1) : '—', src: w?.rainNext7 != null ? local : b ? `${county} · ensemble median (20–80%)` : 'loads with signal' },
    ...(b ? [{ k: 'Rain forecast, week 2', v: wk(b.week2), src: `${county} · ensemble median (20–80%)` }] : []),
    ...(b && b.pDrySpell != null ? [{ k: 'Dry spell chance (7 days in next 15)', v: `${r0(b.pDrySpell * 100)} %`, src: wetDays.length ? `wet days likely: ${wetDays.join(', ')}` : county }] : []),
    { k: 'Rain, last 30 days', v: rain30.v != null ? `${r0(rain30.v)} mm` : '—', src: `${rain30.src}${rain30.src === county && b?.rain30PctNormal != null ? ` · ${r0(b.rain30PctNormal)}% of normal` : ''}` },
    { k: 'Evaporation, last 30 days', v: et30.v != null ? `${r0(et30.v)} mm` : '—', src: et30.src },
    { k: 'Water balance, 30 days', v: wb.v != null ? `${wb.v >= 0 ? '+' : '−'}${Math.abs(r0(wb.v))} mm` : '—', src: `${wb.src}${wb.v != null ? ' · rain − evaporation' : ''}` },
    { k: 'Temperature today', v: w?.tmax != null ? `${w.tmax} °C / ${w.tmin} °C` : w ? `${w.temp} °C` : '—', src: local || 'loads with signal' },
    { k: 'Soil moisture, root zone', v: soil != null ? `${soil.toFixed(2)} m³/m³ · ${soilWord(soil)}` : '—', src: soil == null ? 'loads with signal (Earth Engine)' : sat?.soil != null ? `SMAP via Earth Engine, within ${sat.radiusKm} km of you` : p?.gee.soilMoisture != null ? 'SMAP via Earth Engine, data‑source radius' : `${county}${b?.soilClass ? ` · ${b.soilClass}` : ''}${b?.soilDeficit != null ? `, ${r0(b.soilDeficit)} mm below median` : ''}` },
    { k: 'Satellite flood extent', v: flood != null ? `${flood} % of area` : '—', src: flood != null ? (sat?.floodPct != null ? `maximum flood extent map, within ${sat.radiusKm} km of you` : 'maximum flood extent map, data‑source radius') : 'loads with signal (Earth Engine)' },
    { k: 'Runoff, last 30 days', v: runoff.v, src: runoff.src },
    { k: 'River, nearest station', v: near ? `${near.lastLevel?.toFixed(2) ?? '—'} m · ${near.levelClass || near.floodStatus}` : '—', src: near ? `${near.name}, ${near.km} km${p!.stations.fallback ? ' (none within radius)' : ''}${near.lastDate ? `, ${dateOf(near.lastDate)}` : ''}` : 'pull data sources to load' }
  ];
}

// One line saying which readings the water depth rests on.
function basisText(m: Model, where: string) {
  const u = m.used;
  if (!m.measured || !u) return `No depth reading or crop check within ${u?.radiusKm ?? 2} km of ${where} in the last 3 weeks, so the depth is the design example, not a measurement. Record one under Map, Water depth.`;
  const plots = u.plots.slice(0, 4).join(', ') + (u.plots.length > 4 ? ` and ${u.plots.length - 4} more` : '');
  return `Fitted from ${u.readings} reading${u.readings === 1 ? '' : 's'} (crop checks and depth readings from every phone) at ${plots || 'nearby plots'}, within ${u.radiusKm} km of ${where}, last 3 weeks. The deepest recent reading starts the model; it is brought forward to today at the fall rate.`;
}
const Src = ({ children }: { children: string }) => <div style={{ fontSize: 11, color: 'var(--color-neutral-600)', lineHeight: 1.45, marginTop: 4 }}>{children}</div>;

// Surveyed mound crest heights: group leads and admins enter the measured height of each row.
function MoundSurvey({ onDone }: { onDone: () => void }) {
  const s = useApp(), cur = useMounds();
  const [rows, setRows] = useState(cur.rows.map(([id, h]) => ({ id, h: String(h) })));
  const [err, setErr] = useState('');
  const save = () => {
    const bad = rows.find(r => !r.id.trim() || !(Number(r.h) > 0 && Number(r.h) <= 3));
    if (bad) return setErr(`${bad.id || 'A row'} needs a name and a crest height between 0 and 3 m.`);
    if (new Set(rows.map(r => r.id.trim())).size !== rows.length) return setErr('Each mound row needs its own name.');
    const day = new Date().toISOString().slice(0, 10);
    const old = new Map((s.farm.mounds ?? []).map(m => [m.id, m]));
    farmChange(
      ...(s.farm.mounds ?? []).filter(m => !rows.some(r => r.id.trim() === m.id)).map(m => ({ op: 'remove' as const, kind: 'mound' as const, id: m.id })),
      ...rows.map(r => ({ op: 'upsert' as const, kind: 'mound' as const, item: { id: r.id.trim(), crest: Number(r.h), note: old.get(r.id.trim())?.note ?? '', surveyedAt: old.get(r.id.trim())?.crest === Number(r.h) && old.get(r.id.trim())?.surveyedAt ? old.get(r.id.trim())!.surveyedAt : day, by: old.get(r.id.trim())?.crest === Number(r.h) ? old.get(r.id.trim())!.by : s.session?.user.name ?? '' } }))
    );
    onDone();
  };
  return (
    <div className="box col g8" style={{ padding: 12 }}>
      <div className="kick sm">Mound survey · crest height above the basin floor (m)</div>
      {rows.map((r, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 6, alignItems: 'center' }}>
          <input className="input" style={{ minHeight: 40 }} value={r.id} aria-label="Mound row name" onChange={e => { setRows(rows.map((x, j) => (j === i ? { ...x, id: e.target.value } : x))); setErr(''); }} />
          <input className="input num" style={{ minHeight: 40 }} type="number" inputMode="decimal" step="0.01" value={r.h} aria-label={`Crest height of ${r.id}`} onChange={e => { setRows(rows.map((x, j) => (j === i ? { ...x, h: e.target.value } : x))); setErr(''); }} />
          <button className="btn plain sm" aria-label={`Remove ${r.id}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
        </div>
      ))}
      <button className="btn plain sm" onClick={() => setRows([...rows, { id: `B‑${String(rows.length + 1).padStart(2, '0')}`, h: '1.00' }])}>+ Add a mound row</button>
      {err && <div className="msg">{err}</div>}
      <div className="grid2"><button className="btn plain" onClick={onDone}>Cancel</button><button className="btn" onClick={save}>Save survey</button></div>
    </div>
  );
}

export function Flood() {
  const s = useApp(), online = useOnline(), place = usePlace();
  const [editing, setEditing] = useState(false);
  const mounds = useMounds();
  const can = !!s.session && !s.session.demo && editAllowed(s.session.user.role);
  const [day, setDay] = useState(0);
  const model = useModel(), { weather, sat } = useHereData();
  const bd = basinDepth(day, model), sd = slopeDepth(day, model), total = recessDays(model), rise = nextRise(model);
  const b = s.lastPull?.bulletin, bi = b ? bulletinInputs(b.values) : null;

  return (
    <div className="pad">
      <div>
        <div className="kick muted num">Projected for {dayLabel(day)} · day +{day}</div>
        <h1 className="h1" style={{ margin: '4px 0 0', fontSize: 30, lineHeight: 1.05 }}>{headline(bd)}</h1>
      </div>
      <div className="card accent" style={{ gap: 6 }}>
        <div className="between"><span className="kick sm">{b?.county || place.county} county bulletin · {b ? `data to ${dateOf(b.issued)}` : 'not loaded'}</span>{b?.alert && <span style={{ fontSize: 11, padding: '1px 6px', border: '1px solid var(--color-accent)', borderRadius: 'var(--radius-sm)', color: 'var(--color-accent-800)' }}>{b.alert}</span>}</div>
        {b ? <>
          <div style={{ fontSize: 14, lineHeight: 1.4 }}>{b.headline || bi?.summary || 'No alert for this county in the latest bulletin.'}</div>
          {bi?.summary && bi.summary !== b.headline && <div className="sub" style={{ lineHeight: 1.45 }}>{bi.summary}</div>}
          {bi?.runUtc && <div className="sub num">Forecast run {bi.runUtc.replace(/ (\d{2})$/, ' $1:00 UTC')}{s.lastPull ? ` · downloaded ${ago(s.lastPull.at)}` : ''}</div>}
        </>
          : <div style={{ fontSize: 14, lineHeight: 1.4 }}>No bulletin loaded yet. Open Data sources and tap Pull now.</div>}
      </div>
      <div>
        <input type="range" min={0} max={45} step={1} value={day} onChange={e => setDay(Number(e.target.value))} style={{ width: '100%', accentColor: 'var(--color-accent)', height: 28 }} aria-label="Days ahead" />
        <div className="between num" style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}><span>Today</span><span>+15</span><span>+30</span><span>+45 days</span></div>
      </div>
      <div>
        <h2 className="h2 h20 rule" style={{ marginBottom: 6 }}>Water depth by zone</h2>
        {([['Ridge', 0], ['Slope', sd], ['Basin', bd]] as const).map(([n, v]) => (
          <div key={n} style={{ display: 'grid', gridTemplateColumns: '64px 1fr 56px', gap: 10, alignItems: 'center', padding: '7px 0' }}>
            <span style={{ fontSize: 13 }}>{n}</span>
            <div className="box" style={{ position: 'relative', height: 16, borderRadius: 'var(--radius-sm)' }}>
              <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: Math.min(100, v / 1.2 * 100) + '%', background: 'repeating-linear-gradient(135deg,var(--color-neutral-500) 0 1.5px,transparent 1.5px 5px)' }} />
              <div style={{ position: 'absolute', top: -3, bottom: -3, left: '83.3%', borderLeft: '1.5px solid var(--color-accent)' }} />
            </div>
            <span className="num" style={{ fontSize: 13, textAlign: 'right' }}>{v.toFixed(2)} m</span>
          </div>
        ))}
        <div style={{ fontSize: 11, color: 'var(--color-accent-800)' }}>│ gold line = 1.0 m mound crest</div>
        <Src>{`${basisText(model, place.payam)} Slope = basin depth minus ${SLOPE_STEP.toFixed(2)} m (the farm survey's height of the slope above the basin floor, not measured separately). The ridge is taken as dry in a normal year.`}</Src>
      </div>
      <div className="grid2" style={{ gap: 0, borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)' }}>
        <div style={{ padding: '10px 0' }}><div className="lbl">Basin dry in</div><div className="head num" style={{ fontSize: 28 }}>{total == null ? 'not falling' : `${Math.max(0, total - day)} days`}</div><div className="sub">basin depth ÷ fall rate · {model.rateSrc}</div></div>
        <div style={{ padding: '10px 0 10px 12px', borderLeft: '1px solid var(--color-divider)' }}><div className="lbl">Next flood rise</div><div className="head" style={{ fontSize: 28 }}>{rise.when}</div><div className="sub">{rise.src}</div></div>
      </div>
      <div className="card accent" style={{ gap: 4 }}>
        <div className="kick">Planting window</div>
        <div style={{ fontSize: 14, lineHeight: 1.45 }}>{plantAlert(bd, model)}</div>
        <Src>Worked out from the basin dry-in date above (3 days before it for the basin edge) and the slope step. The crops named are the project's recession crops; the dates move whenever a new depth reading or gauge reading arrives.</Src>
      </div>
      <div>
        <H2plain>Balanites mound rows</H2plain>
        {moundRows(bd, model, mounds.rows).map(m => (
          <div key={m.id} style={{ display: 'grid', gridTemplateColumns: '48px 1fr auto', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--color-divider)', fontSize: 13, alignItems: 'baseline' }}>
            <span className="num">{m.id}</span>
            <span className="num" style={{ color: 'var(--color-neutral-700)' }}>crest {m.h.toFixed(2)} m</span>
            <span className="it" style={{ color: m.state === 'submerged' ? 'var(--color-text)' : m.state === 'risk' ? 'var(--color-accent-800)' : 'var(--color-neutral-600)' }}>{m.status}</span>
          </div>
        ))}
        <Src>{`${mounds.note} A row is under water when its crest is lower than the basin depth, and at risk with under 8 cm to spare; it clears once the falling basin depth drops to its crest.`}</Src>
        {can && !editing && <button className="btn plain sm" style={{ marginTop: 8 }} onClick={() => setEditing(true)}>Enter the measured crest heights</button>}
        {editing && <div style={{ marginTop: 8 }}><MoundSurvey onDone={() => setEditing(false)} /></div>}
      </div>
      <div>
        <div className="between rule-b"><h2 className="h2 h20">Model inputs</h2><button className="link" onClick={() => go('sources')}>Data sources</button></div>
        {inputs(s.lastPull, model, weather, sat, bi).map(i => (
          <div key={i.k} className="rowg" style={{ padding: '8px 0' }}>
            <span><span style={{ display: 'block', fontSize: 13.5 }}>{i.k}</span><span style={{ fontSize: 11, color: 'var(--color-neutral-600)' }}>{i.src}</span></span>
            <span className="num" style={{ fontSize: 13.5, textAlign: 'right' }}>{i.v}</span>
          </div>
        ))}
        <p className="body note" style={{ marginTop: 10 }}>How it works: the water depth and how fast it falls are fitted to depth readings and crop checks within 2 km of you (any worker's phone), else the Bor gauge trend; mound heights come from the survey entered above and the slope step from the farm survey. Rain, evaporation, soil moisture and flood extent are shown alongside to judge whether the fall will hold. {s.autoPull?.state === 'ok' || s.lastPull ? `Data downloaded ${ago((s.autoPull?.state === 'ok' ? s.autoPull.at : s.lastPull!.at))}; refreshes by itself once a day with signal.` : online ? 'Downloading data for your location…' : 'Data downloads by itself once the phone has signal.'}</p>
      </div>
    </div>
  );
}

const H2plain = ({ children }: { children: string }) => <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>{children}</h2>;
