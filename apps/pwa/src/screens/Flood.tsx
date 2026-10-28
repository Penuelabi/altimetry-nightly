import { useState } from 'react';
import { basinDepth, dayLabel, headline, moundRows, plantAlert, recessDays, slopeDepth, type PullResult } from '@abuk/core';
import { go, useApp } from '../store';
import { useOnline, usePlace } from '../net';

const ago = (iso: string) => {
  const m = Math.round((Date.now() - Date.parse(iso)) / 60000);
  return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};

// Model inputs: live values from the last pull where we have them, otherwise the
// figures from the 27 Oct Duk bulletin that the design was built on (labelled as such).
function inputs(p: PullResult | null) {
  const near = p?.stations.rows[0];
  const ifs = p?.ifs[0]?.values ?? {};
  const pick = (re: RegExp) => { const k = Object.keys(ifs).find(x => re.test(x)); return k ? ifs[k] : null; };
  const t = pick(/t2m|temp/i);
  return [
    { k: 'Rain forecast, week 1', v: '10.9 mm', src: '50‑member ensemble, 6–15 mm range' },
    { k: 'Rain, last 30 days', v: '85 mm · 91%', src: 'GSMaP, of normal' },
    { k: 'Soil moisture, root zone', v: p?.gee.soilMoisture != null ? p.gee.soilMoisture.toFixed(3) + ' m³/m³' : 'dry · 27th pct', src: p?.gee.soilMoisture != null ? 'Earth Engine, mean within radius' : 'SMAP via Earth Engine · 52 mm deficit' },
    { k: 'Runoff, 30 days', v: pick(/runoff|^ro$/i)?.toFixed(1) ?? 'dry', src: pick(/runoff|^ro$/i) != null ? 'ECMWF IFS, nearest station' : 'SPL4SMGP' },
    { k: 'Evapotranspiration, 30 d', v: '107 mm', src: 'water balance −26 mm' },
    { k: 'Temperature', v: t != null ? `${Math.round(t)}°` : '34° / 22°', src: 'ECMWF IFS daily' },
    { k: 'River level, nearest stations', v: near ? `${near.lastLevel?.toFixed(2) ?? '—'} m · ${near.levelClass || near.floodStatus}` : 'status file', src: near ? `${near.name}, ${near.km} km${p!.stations.fallback ? ' (none within radius)' : ''}` : 'station_status.csv, DAHITI/Hydroweb' },
    { k: 'Satellite flood extent', v: p?.gee.floodExtentPct != null ? `${p.gee.floodExtentPct} % of radius` : '61 % of basin', src: p?.gee.floodExtentPct != null ? 'Earth Engine asset, clipped to radius' : 'sample value until the asset is connected' }
  ];
}

export function Flood() {
  const s = useApp(), online = useOnline(), place = usePlace();
  const [day, setDay] = useState(0);
  const bd = basinDepth(day), sd = slopeDepth(day), total = recessDays();
  const b = s.lastPull?.bulletin;

  return (
    <div className="pad">
      <div>
        <div className="kick muted num">Projected for {dayLabel(day)} · day +{day}</div>
        <h1 className="h1" style={{ margin: '4px 0 0', fontSize: 30, lineHeight: 1.05 }}>{headline(bd)}</h1>
      </div>
      <div className="card accent" style={{ gap: 6 }}>
        <div className="between"><span className="kick sm">{b?.county || place.county} county bulletin · {b?.issued || '27 Oct'}</span><span style={{ fontSize: 11, padding: '1px 6px', border: '1px solid var(--color-accent)', borderRadius: 'var(--radius-sm)', color: 'var(--color-accent-800)' }}>{b?.alert || 'orange'}</span></div>
        {b ? <div style={{ fontSize: 14, lineHeight: 1.4 }}>{b.headline || 'Bulletin row loaded; no headline column found.'}</div> : <>
          <div style={{ fontSize: 14, lineHeight: 1.4 }}><strong style={{ fontWeight: 600 }}>Dry spell possible (46%) on dry soils.</strong> Monitor crops and pasture.</div>
          <div style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--color-neutral-800)' }}>28 Oct likely dry · 30–31 Oct likely wet · 2–3 Nov likely dry · 6 Nov likely dry</div>
          <div style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}>5,015 people on flood‑prone ground of 206,545 in the county</div>
        </>}
        {!s.lastPull && <div className="sub it">Figures from the 27 Oct bulletin. Pull data sources to refresh.</div>}
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
        <div style={{ padding: '10px 0' }}><div className="lbl">Basin dry in</div><div className="head num" style={{ fontSize: 28 }}>{Math.max(0, total - day)} days</div></div>
        <div style={{ padding: '10px 0 10px 12px', borderLeft: '1px solid var(--color-divider)' }}><div className="lbl">Next flood rise</div><div className="head" style={{ fontSize: 28 }}>~Jul 2027</div></div>
      </div>
      <div className="card accent" style={{ gap: 4 }}>
        <div className="kick">Planting window</div>
        <div style={{ fontSize: 14, lineHeight: 1.45 }}>{plantAlert(bd)}</div>
      </div>
      <div>
        <H2plain>Balanites mound rows</H2plain>
        {moundRows(bd).map(m => (
          <div key={m.id} style={{ display: 'grid', gridTemplateColumns: '48px 1fr auto', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--color-divider)', fontSize: 13, alignItems: 'baseline' }}>
            <span className="num">{m.id}</span>
            <span className="num" style={{ color: 'var(--color-neutral-700)' }}>crest {m.h.toFixed(2)} m</span>
            <span className="it" style={{ color: m.state === 'submerged' ? 'var(--color-text)' : m.state === 'risk' ? 'var(--color-accent-800)' : 'var(--color-neutral-600)' }}>{m.status}</span>
          </div>
        ))}
      </div>
      <div>
        <div className="between rule-b"><h2 className="h2 h20">Model inputs</h2><button className="link" onClick={() => go('sources')}>Data sources</button></div>
        {inputs(s.lastPull).map(i => (
          <div key={i.k} className="rowg" style={{ padding: '8px 0' }}>
            <span><span style={{ display: 'block', fontSize: 13.5 }}>{i.k}</span><span style={{ fontSize: 11, color: 'var(--color-neutral-600)' }}>{i.src}</span></span>
            <span className="num" style={{ fontSize: 13.5, textAlign: 'right' }}>{i.v}</span>
          </div>
        ))}
        <p className="body note" style={{ marginTop: 10 }}>Water balance: rainfall + catchment runoff + river inflow − evaporation − soil infiltration, calibrated against satellite flood extent. {s.lastPull ? `Data pulled ${ago(s.lastPull.at)}.` : `${place.county} bulletin data to 24 Oct.`} {online ? 'Re-runs when you pull new data.' : 'Reruns automatically when online.'}</p>
      </div>
    </div>
  );
}

const H2plain = ({ children }: { children: string }) => <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>{children}</h2>;
