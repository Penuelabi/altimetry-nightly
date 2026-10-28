import { useState } from 'react';
import { basinDepth, bulletinInputs, dayLabel, headline, moundRows, nextRise, plantAlert, recessDays, slopeDepth, soilWord, type BulletinInputs, type Model, type PullResult } from '@abuk/core';
import { useHereData, useModel } from './common';
import type { Weather } from '../weather';
import { go, useApp } from '../store';
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

export function Flood() {
  const s = useApp(), online = useOnline(), place = usePlace();
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
      </div>
      <div className="grid2" style={{ gap: 0, borderTop: '1px solid var(--color-divider)', borderBottom: '1px solid var(--color-divider)' }}>
        <div style={{ padding: '10px 0' }}><div className="lbl">Basin dry in</div><div className="head num" style={{ fontSize: 28 }}>{total == null ? 'not falling' : `${Math.max(0, total - day)} days`}</div></div>
        <div style={{ padding: '10px 0 10px 12px', borderLeft: '1px solid var(--color-divider)' }}><div className="lbl">Next flood rise</div><div className="head" style={{ fontSize: 28 }}>{rise.when}</div><div className="sub">{rise.src}</div></div>
      </div>
      <div className="card accent" style={{ gap: 4 }}>
        <div className="kick">Planting window</div>
        <div style={{ fontSize: 14, lineHeight: 1.45 }}>{plantAlert(bd, model)}</div>
      </div>
      <div>
        <H2plain>Balanites mound rows</H2plain>
        {moundRows(bd, model).map(m => (
          <div key={m.id} style={{ display: 'grid', gridTemplateColumns: '48px 1fr auto', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--color-divider)', fontSize: 13, alignItems: 'baseline' }}>
            <span className="num">{m.id}</span>
            <span className="num" style={{ color: 'var(--color-neutral-700)' }}>crest {m.h.toFixed(2)} m</span>
            <span className="it" style={{ color: m.state === 'submerged' ? 'var(--color-text)' : m.state === 'risk' ? 'var(--color-accent-800)' : 'var(--color-neutral-600)' }}>{m.status}</span>
          </div>
        ))}
      </div>
      <div>
        <div className="between rule-b"><h2 className="h2 h20">Model inputs</h2><button className="link" onClick={() => go('sources')}>Data sources</button></div>
        {inputs(s.lastPull, model, weather, sat, bi).map(i => (
          <div key={i.k} className="rowg" style={{ padding: '8px 0' }}>
            <span><span style={{ display: 'block', fontSize: 13.5 }}>{i.k}</span><span style={{ fontSize: 11, color: 'var(--color-neutral-600)' }}>{i.src}</span></span>
            <span className="num" style={{ fontSize: 13.5, textAlign: 'right' }}>{i.v}</span>
          </div>
        ))}
        <p className="body note" style={{ marginTop: 10 }}>How it works: the water depth and how fast it falls are fitted to crop‑check depth readings within 2 km of you, else the Bor gauge trend; mound and slope heights come from the farm survey. Rain, evaporation, soil moisture and flood extent are shown alongside to judge whether the fall will hold. {s.autoPull?.state === 'ok' || s.lastPull ? `Data downloaded ${ago((s.autoPull?.state === 'ok' ? s.autoPull.at : s.lastPull!.at))}; refreshes by itself once a day with signal.` : online ? 'Downloading data for your location…' : 'Data downloads by itself once the phone has signal.'}</p>
      </div>
    </div>
  );
}

const H2plain = ({ children }: { children: string }) => <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>{children}</h2>;
