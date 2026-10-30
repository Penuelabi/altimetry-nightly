import { useEffect, useState } from 'react';
import { ZONES, autoTasks, basinDepth, fitModel, greeting, haversineKm, MOUNDS, T, zoneDepths, zoneSummary, type FarmTask, type Model, type PullResult, type ZoneKey } from '@abuk/core';
import { api } from '../api';
import { useOnline, usePlace } from '../net';
import { fetchWeather, lastWeather, type Weather } from '../weather';
import { farmChange, getState, go, record, setState, useApp, type State } from '../store';

export function toggleTask(id: number) {
  let done = false;
  setState(st => ({ tasks: st.tasks.map(t => (t.id === id ? ((done = !t.done), { ...t, done }) : t)) }));
  record('task', { id, done });
}

export const useL = () => { const s = useApp(); return T[s.lang === 'ar' ? 'ar' : 'en']; };
export const useGreet = () => {
  const s = useApp(), L = useL();
  const first = s.session?.user.name.split(' ')[0];
  const g = s.lang === 'ar' ? L.greet : greeting(new Date());
  return first ? `${g}, ${first}` : g;
};

// Mound line colours on the map diagrams: grey when the crest is under water.
export const moundLines = (ys: number[], depth = basinDepth(0), mounds: [string, number][] = MOUNDS) =>
  ys.flatMap((y, i) => (mounds[i] ? [{ y, c: mounds[i][1] < depth ? 'var(--color-neutral-600)' : 'var(--color-accent)' }] : []));

// The mound rows the flood model checks: the surveyed rows in the shared register, else the design survey it started with.
export function useMounds(): { rows: [string, number][]; surveyed: boolean; note: string } {
  const m = useApp().farm.mounds ?? [];
  if (!m.length) return { rows: MOUNDS, surveyed: false, note: 'Crest heights are the design survey the app started with. A group lead or admin can enter the measured heights below.' };
  const latest = [...m].filter(x => x.surveyedAt).sort((a, b) => b.surveyedAt.localeCompare(a.surveyedAt))[0];
  return { rows: m.map(x => [x.id, x.crest] as [string, number]), surveyed: true, note: latest ? `Crest heights entered in the app, last updated ${latest.surveyedAt}${latest.by ? ` by ${latest.by}` : ''}.` : 'Crest heights from the shared register.' };
}

export const basinOpacity = (depth = basinDepth(0)) => (depth / 1.2 * 0.6).toFixed(2);

// The flood model fitted to crop checks near the phone and the Bor gauge (see fitModel).
export function useModel(): Model {
  const s = useApp(), place = usePlace();
  return fitModel(allChecks(s).flatMap(c => (c.lat != null && c.lon != null && c.water ? [{ at: c.at, plot: c.plot, lat: c.lat, lon: c.lon, depthCm: c.depthCm, water: c.water }] : [])), gaugeObs(s), place);
}
const gaugeObs = (s: State) => (s.gauge ?? []).filter(g => g.status === 'ok' && g.v != null).map(g => ({ at: g.at, v: g.v as number }));

// This phone's own checks (including ones not yet synced) plus every phone's from the server, without repeats.
export function allChecks(s: State) {
  const mine = s.monLog.flatMap(r => (r.at ? [{ at: r.at, plot: r.plot, lat: r.lat ?? null, lon: r.lon ?? null, water: r.water ?? '', depthCm: r.depthCm ?? null, around: r.around ?? '', aroundDepthCm: r.aroundDepthCm ?? null, trend: r.trend ?? '' }] : []));
  const key = (c: { at: string; plot: string }) => `${c.plot}|${c.at.slice(0, 16)}`;
  const seen = new Set(mine.map(key));
  return [...mine, ...s.checksAll.filter(c => !seen.has(key(c)))];
}

// Light data around the phone, refreshed only when stale: weather (1 h), gauge (1 h), satellite (6 h or after moving 1 km).
const SAT_KM = 2;
let lastGauge = 0;
export function useHereData() {
  const s = useApp(), online = useOnline(), place = usePlace();
  const [weather, setWeather] = useState<Weather | null>(lastWeather());
  useEffect(() => {
    if (!online || !place.gps) return;
    const w = lastWeather();
    if (!w || Date.now() - Date.parse(w.at) > 3600_000) fetchWeather(place.lat, place.lon).then(setWeather, () => {});
    if (s.session && !s.session.demo) {
      if (Date.now() - lastGauge > 3600_000) { lastGauge = Date.now(); api<NonNullable<typeof s.gauge>>('/api/gauge').then(g => setState({ gauge: g }), () => {}); }
      const sat = getState().satHere;
      if (!sat || Date.now() - Date.parse(sat.at) > 6 * 3600_000 || haversineKm(sat, place) > 1)
        api<PullResult['gee']>(`/api/sources/gee?lat=${place.lat}&lon=${place.lon}&radius=${SAT_KM}`)
          .then(g => setState({ satHere: { lat: place.lat, lon: place.lon, at: new Date().toISOString(), floodPct: g.floodExtentPct, soil: g.soilMoisture, radiusKm: SAT_KM } }), () => {});
    }
  }, [online, place.gps, Math.round(place.lat * 100), Math.round(place.lon * 100)]); // eslint-disable-line react-hooks/exhaustive-deps
  return { weather, sat: s.satHere };
}

// ---- Home: today's work and zones, built from the shared register and from what has been recorded ----
const todayStr = () => new Date().toISOString().slice(0, 10);
export interface TaskItem { key: string; title: string; zone: string; who: string; due: string; done: boolean; auto: boolean; why: string; tick: () => void; reg?: FarmTask }

// Live phones: the shared task list plus jobs that are due because nothing has been recorded lately. The demo keeps its sample list.
export function useTasks(): { items: TaskItem[]; today: TaskItem[]; open: number } {
  const s = useApp(), model = useModel();
  const day = todayStr();
  if (s.session?.demo || !s.session) {
    const items = s.tasks.map(x => ({ key: `demo-${x.id}`, title: x.t, zone: x.zone, who: x.who, due: x.due === 'today' ? day : '', done: x.done, auto: false, why: 'sample task', tick: () => toggleTask(x.id) }));
    return { items, today: items.filter(x => x.due === day), open: items.filter(x => !x.done).length };
  }
  const reg = (s.farm.tasks ?? []).map(x => ({
    key: x.id, title: x.title, zone: x.zone, who: x.who, due: x.due, done: x.done, auto: false, why: `added by ${x.by}`, reg: x,
    tick: () => farmChange({ op: 'upsert', kind: 'task', item: { ...x, done: !x.done, ...(x.done ? { doneAt: undefined, doneBy: undefined } : { doneAt: new Date().toISOString(), doneBy: s.session?.user.id ?? '' }) } })
  }));
  const go2 = (id: string) => (id === 'auto-gauge' ? () => go('gauge') : id === 'auto-depth' ? () => go('depth') : () => go('monitor'));
  const auto = autoTasks({ now: new Date(), plots: s.farm.plots, checks: allChecks(s), gauge: s.gauge ?? [], depthMeasured: model.measured })
    .map(a => ({ key: a.id, title: a.title, zone: a.zone, who: 'anyone', due: day, done: false, auto: true, why: a.why, tick: go2(a.id) }));
  const items: TaskItem[] = [...reg.sort((a, b) => a.due.localeCompare(b.due)), ...auto];
  // Today: everything due today or earlier that is open, and what was ticked today.
  const today = items.filter(x => (x.due <= day && !x.done) || (x.done && x.reg?.doneAt?.slice(0, 10) === day));
  return { items, today, open: items.filter(x => !x.done).length };
}

export interface ZoneRow { n: string; key: ZoneKey; name: string; ha: string; crops: string; status: string; source: string }
// The three zones as the register and the flood model describe them: plots and area registered in each, and the water depth now.
export function useZoneRows(): ZoneRow[] {
  const s = useApp(), model = useModel(), d = zoneDepths(model);
  return ZONES.map(z => {
    const sum = zoneSummary(s.farm, z.key);
    const ha = sum.mapped ? `${sum.ha} ha` : `${sum.plots} plot${sum.plots === 1 ? '' : 's'}`;
    const water = z.key === 'ridge' ? 'dry' : `${d[z.key].toFixed(2)} m water${model.measured ? '' : ' · example'}`;
    return { n: z.n, key: z.key, name: z.name, ha, crops: sum.crops.join(', ') || 'no plots registered', status: water, source: `${sum.plots} registered plot${sum.plots === 1 ? '' : 's'}${sum.mapped < sum.plots ? `, ${sum.mapped} with a mapped area` : ''}` };
  });
}
