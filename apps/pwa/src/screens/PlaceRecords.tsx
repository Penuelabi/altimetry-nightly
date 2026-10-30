// What is recorded in one place (state, county or payam): flood risk of its plots, crop checks, land assessments and
// the registers. Everything comes from data already on the phone (the shared farm register and every phone's recent
// crop checks), so it works offline for any place in the country.
import { useMemo, useState } from 'react';
import { FARM, adminLabel, fitModel, herdCount, payamsIn, recessDays, whereIs, zoneDepths, type AdminLoc, type PayamArea } from '@abuk/core';
import { useApp } from '../store';
import { allChecks } from './common';

export interface Sel { state: string; county: string; payam: string }

const home = (() => { const p = whereIs(FARM.lat, FARM.lon); return { state: p?.state ?? 'Jonglei', county: p?.county ?? 'Duk', payam: p?.payam ?? 'Duk Padiet', village: '' } as AdminLoc; })();
// Records made before admin levels existed belong to the project's home payam.
const adminOf = (a?: AdminLoc | null): AdminLoc => a && a.state ? a : home;
const inSel = (a: AdminLoc | null | undefined, s: Sel) => !!a && (!s.state || a.state === s.state) && (!s.county || a.county === s.county) && (!s.payam || a.payam === s.payam);
const centroid = (a: PayamArea) => { const r = a.polygons[0]?.[0] ?? []; return r.length ? { lat: r.reduce((n, p) => n + p[1], 0) / r.length, lon: r.reduce((n, p) => n + p[0], 0) / r.length } : null; };
const fmtDay = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

function Block({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return <div><div className="section">{title}{count != null ? ` · ${count}` : ''}</div>{children}</div>;
}

export function PlaceRecords({ sel, area, floodPct }: { sel: Sel; area: PayamArea | null; floodPct?: number | null }) {
  const s = useApp();
  const reg = s.farm;
  const [more, setMore] = useState({ checks: false, assess: false });
  const place = [sel.payam, sel.county && `${sel.county} county`, sel.state].filter(Boolean).join(', ');

  const plots = reg.plots.filter(p => inSel(p.admin ?? (p.boundary.length ? whereIs(p.boundary.reduce((n, b) => n + b.lat, 0) / p.boundary.length, p.boundary.reduce((n, b) => n + b.lon, 0) / p.boundary.length) : null) ?? home, sel));
  const plotAdmin = (code: string) => { const p = reg.plots.find(x => x.code === code); return p ? p.admin ?? home : null; };

  const checks = useMemo(() => allChecks(s)
    .map(c => ({ c, at: (c.lat != null && c.lon != null ? whereIs(c.lat, c.lon) : null) ?? plotAdmin(c.plot) }))
    .filter(x => inSel(x.at, sel))
    .sort((a, b) => b.c.at.localeCompare(a.c.at)), [s.monLog, s.checksAll, reg.plots, sel.state, sel.county, sel.payam]);
  const assess = (reg.degradations ?? []).filter(a => inSel(a.admin ?? (a.plotId ? reg.plots.find(p => p.id === a.plotId)?.admin : null) ?? home, sel)).sort((a, b) => b.date.localeCompare(a.date));

  // A flood model for this place, fitted only from depth readings and crop checks made within reach of it.
  const model = useMemo(() => {
    const centre = area ? centroid(area) : (() => { const a = sel.county ? payamsIn(sel.county, sel.state) : []; const cs = a.map(centroid).filter((x): x is { lat: number; lon: number } => !!x); return cs.length ? { lat: cs.reduce((n, p) => n + p.lat, 0) / cs.length, lon: cs.reduce((n, p) => n + p.lon, 0) / cs.length } : null; })();
    if (!centre) return null;
    const radius = area ? Math.min(60, Math.max(5, Math.sqrt(area.areaKm2 / Math.PI) + 2)) : 40;
    const obs = allChecks(s).flatMap(c => (c.lat != null && c.lon != null && c.water ? [{ at: c.at, plot: c.plot, lat: c.lat, lon: c.lon, depthCm: c.depthCm, water: c.water }] : []));
    const gauge = (s.gauge ?? []).filter(g => g.status === 'ok' && g.v != null).map(g => ({ at: g.at, v: g.v as number }));
    return fitModel(obs, gauge, centre, new Date(), radius);
  }, [s.monLog, s.checksAll, s.gauge, area?.pcode, sel.county, sel.state]);

  // Numbers are shown only where depth readings back them; a place with none says so instead of showing the design example.
  const z = model?.measured ? zoneDepths(model) : null;
  const risk = (zone: 'ridge' | 'slope' | 'basin') => {
    if (!model || !z) return 'no depth reading yet';
    const d = z[zone];
    if (d <= 0) return 'dry';
    const days = recessDays({ d0: d, rate: model.rate });
    return `${d.toFixed(2)} m of water${days == null ? ', not falling' : `, dry in about ${days} days`}`;
  };

  const counts: [string, number][] = [
    ['Groups', reg.groups.filter(g => inSel(adminOf(g.admin), sel)).length],
    ['People', (reg.people ?? []).filter(p => inSel(adminOf(p.admin), sel)).length],
    ['VSLA groups', (reg.vslaGroups ?? []).filter(v => inSel(adminOf(v.admin), sel)).length],
    ['Stores', (reg.stores ?? []).filter(x => inSel(adminOf(x.admin), sel)).length],
    ['Herds', (reg.herds ?? []).filter(h => inSel(adminOf(h.admin), sel)).length],
    ['Containers', (reg.containers ?? []).filter(x => inSel(adminOf(x.admin), sel)).length],
    ['Batches', reg.batches.filter(b => inSel(adminOf(b.admin), sel)).length],
  ];
  const livestock = (reg.herds ?? []).filter(h => inSel(adminOf(h.admin), sel)).reduce((n, h) => n + herdCount(reg, h.id), 0);

  return (
    <div className="col g14">
      <div className="kick sm" style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 12 }}>Recorded in {place || 'South Sudan'}</div>

      <Block title="Flood risk of plots" count={plots.length}>
        {z ? (
          <div className="box col g6" style={{ padding: '10px 12px', marginBottom: 8 }}>
            <div className="between"><span style={{ fontSize: 13 }}>Basin {z.basin.toFixed(2)} m · slope {z.slope.toFixed(2)} m · ridge dry</span><span className="it" style={{ fontSize: 12, color: 'var(--color-accent-800)' }}>measured nearby</span></div>
            <div className="sub">{model!.d0Src}. Falling {(model!.rate * 100).toFixed(1)} cm a day.{floodPct != null ? ` Satellite: ${floodPct}% of the payam is flooded.` : ''}</div>
          </div>
        ) : <div className="note" style={{ marginBottom: 8 }}>{model ? 'No depth readings within reach of this place yet, so no flood depth is shown. Record one under Map, Water depth.' : 'Choose a county or a payam to see flood-risk numbers.'}{floodPct != null ? ` Satellite: ${floodPct}% of the payam is flooded.` : ''}</div>}
        {plots.map(p => (
          <div key={p.id} className="rowg" style={{ padding: '7px 0' }}>
            <span><span style={{ display: 'block', fontSize: 13.5 }}>{p.code} · {p.crop}</span><span className="sub">{p.zone} zone{p.admin ? ` · ${adminLabel(p.admin)}` : ''}{p.areaHa ? ` · ${p.areaHa} ha` : ''}</span></span>
            <span className="it" style={{ fontSize: 12.5, textAlign: 'right', color: risk(p.zone).startsWith('dry') ? 'var(--color-neutral-700)' : 'var(--color-accent-800)' }}>{risk(p.zone)}</span>
          </div>
        ))}
        {!plots.length && <div className="note">No plots registered here yet.</div>}
      </Block>

      <Block title="Crop checks, last 3 weeks" count={checks.length}>
        {(more.checks ? checks : checks.slice(0, 6)).map(({ c, at }, i) => (
          <div key={i} className="rowg" style={{ padding: '7px 0' }}>
            <span><span style={{ display: 'block', fontSize: 13.5 }}>{c.plot}{reg.plots.find(p => p.code === c.plot)?.crop ? ` · ${reg.plots.find(p => p.code === c.plot)!.crop}` : ''}</span><span className="sub">{fmtDay(c.at)}{at ? ` · ${at.payam}` : ''}{c.trend ? ` · ${c.trend}` : ''}</span></span>
            <span className="it" style={{ fontSize: 12.5, textAlign: 'right' }}>{c.water || '—'}{c.depthCm != null && c.water ? ` · ${c.depthCm} cm` : ''}</span>
          </div>
        ))}
        {checks.length > 6 && <button className="btn plain sm" onClick={() => setMore({ ...more, checks: !more.checks })}>{more.checks ? 'Show fewer' : `Show all ${checks.length}`}</button>}
        {!checks.length && <div className="note">No crop checks here in the last 3 weeks.</div>}
      </Block>

      <Block title="Land assessments" count={assess.length}>
        {(more.assess ? assess : assess.slice(0, 5)).map(a => {
          const vals = Object.values(a.scores), avg = vals.length ? vals.reduce((n, v) => n + v, 0) / vals.length : null;
          return (
            <div key={a.id} className="rowg" style={{ padding: '7px 0' }}>
              <span><span style={{ display: 'block', fontSize: 13.5 }}>{a.site}</span><span className="sub">{a.date}{a.admin ? ` · ${adminLabel(a.admin)}` : ''} · {vals.length} indicators</span></span>
              <span className="head num" style={{ fontSize: 18 }}>{avg == null ? '—' : avg.toFixed(1)}<span className="sub">/3</span></span>
            </div>
          );
        })}
        {assess.length > 5 && <button className="btn plain sm" onClick={() => setMore({ ...more, assess: !more.assess })}>{more.assess ? 'Show fewer' : `Show all ${assess.length}`}</button>}
        {!assess.length && <div className="note">No land assessments here yet.</div>}
      </Block>

      <Block title="Registered here">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px' }}>
          {counts.map(([k, n]) => <div key={k} className="rowg" style={{ padding: '4px 0' }}><span style={{ fontSize: 13 }}>{k}</span><span className="num" style={{ fontSize: 13.5 }}>{n}</span></div>)}
          <div className="rowg" style={{ padding: '4px 0' }}><span style={{ fontSize: 13 }}>Livestock (head)</span><span className="num" style={{ fontSize: 13.5 }}>{livestock}</span></div>
        </div>
      </Block>
    </div>
  );
}
