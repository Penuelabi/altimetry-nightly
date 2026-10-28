import { useEffect, useState } from 'react';
import { basinDepth, fitModel, greeting, haversineKm, MOUNDS, T, type Model, type PullResult } from '@abuk/core';
import { api } from '../api';
import { useOnline, usePlace } from '../net';
import { fetchWeather, lastWeather, type Weather } from '../weather';
import { getState, record, setState, useApp, type State } from '../store';

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
export const moundLines = (ys: number[], depth = basinDepth(0)) =>
  ys.map((y, i) => ({ y, c: MOUNDS[i][1] < depth ? 'var(--color-neutral-600)' : 'var(--color-accent)' }));

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
