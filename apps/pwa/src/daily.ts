import { useEffect } from 'react';
import { haversineKm, type PullResult } from '@abuk/core';
import { api } from './api';
import { useOnline } from './net';
import { getState, setState, useApp } from './store';
import { fetchWeather } from './weather';

// Daily refresh: whenever the phone has signal and the last pull is more than a day old (or the phone
// has moved more than half the radius since), pull every data source for where the phone is now.
// Runs at start, when signal returns, when the app comes back to the screen, and hourly while open.
// Everything lands in the offline store, so the screens keep working with no signal afterwards.
export const DAY_MS = 24 * 3600_000;
const SAT_KM = 2;

export interface PullAt { lat: number; lon: number; radius: number }

// The full pull (Drive bulletin, stations, IFS) plus Earth Engine for the radius. Earth Engine is
// slower, so its numbers drop in when ready. Shared with the Sources screen's "Pull now".
export async function pullSources(at: PullAt, onGee?: (busy: boolean) => void) {
  const q = `lat=${at.lat}&lon=${at.lon}&radius=${at.radius}`;
  onGee?.(true);
  const gee = api<PullResult['gee']>(`/api/sources/gee?${q}`)
    .then(g => setState(st => (st.lastPull ? { lastPull: { ...st.lastPull, gee: g } } : {})), () => {})
    .finally(() => onGee?.(false));
  const r = await api<PullResult>(`/api/sources/pull?${q}`);
  setState(st => ({ lastPull: { ...r, gee: st.lastPull?.gee.soilMoisture != null || st.lastPull?.gee.floodExtentPct != null ? st.lastPull.gee : r.gee } }));
  return { r, gee };
}

// The light "here" data: river gauge, satellite values within 2 km, weather.
async function pullHere(lat: number, lon: number) {
  await Promise.allSettled([
    api<NonNullable<ReturnType<typeof getState>['gauge']>>('/api/gauge').then(g => setState({ gauge: g })),
    loadChecks(),
    api<PullResult['gee']>(`/api/sources/gee?lat=${lat}&lon=${lon}&radius=${SAT_KM}`)
      .then(g => setState({ satHere: { lat, lon, at: new Date().toISOString(), floodPct: g.floodExtentPct, soil: g.soilMoisture, radiusKm: SAT_KM } })),
    fetchWeather(lat, lon)
  ]);
}

export const loadChecks = () => api<ReturnType<typeof getState>['checksAll']>('/api/checks/recent').then(c => setState({ checksAll: c }));

let running = false;
export async function dailyRefresh(force = false) {
  const s = getState();
  if (running || !navigator.onLine || !s.session || s.session.demo) return;
  const w = s.where;
  if (!w) return; // wait for a GPS fix so the pull is for where the phone really is
  const last = s.lastPull, age = last ? Date.now() - Date.parse(last.at) : Infinity;
  const moved = last ? haversineKm(last.location, w) > s.radius / 2 : true;
  if (!force && age < DAY_MS && !moved) return;
  running = true;
  setState({ autoPull: { state: 'running', at: new Date().toISOString() } });
  try {
    const [{ gee }] = await Promise.all([pullSources({ lat: w.lat, lon: w.lon, radius: s.radius }), pullHere(w.lat, w.lon)]);
    await gee;
    setState({ autoPull: { state: 'ok', at: new Date().toISOString() } });
  } catch (e) {
    setState({ autoPull: { state: 'error', at: new Date().toISOString(), msg: (e as Error).message } });
  } finally { running = false; }
}

export function useDailyRefresh() {
  const online = useOnline(), s = useApp();
  const signedIn = !!s.session && !s.session.demo, gps = !!s.where;
  useEffect(() => {
    if (!online || !signedIn || !gps) return;
    dailyRefresh();
    const iv = setInterval(() => dailyRefresh(), 3600_000);
    const onShow = () => { if (document.visibilityState === 'visible') dailyRefresh(); };
    document.addEventListener('visibilitychange', onShow);
    return () => { clearInterval(iv); document.removeEventListener('visibilitychange', onShow); };
  }, [online, signedIn, gps]);
}
