import { useEffect, useSyncExternalStore } from 'react';
import { FARM, applyOps, whereIs, type Register, type SyncRecord } from '@abuk/core';
import { api, ApiFail } from './api';
import { getState, setState, useApp } from './store';
import { uploadPhotos } from './photos';

const sub = (cb: () => void) => { addEventListener('online', cb); addEventListener('offline', cb); return () => { removeEventListener('online', cb); removeEventListener('offline', cb); }; };
export const useOnline = () => useSyncExternalStore(sub, () => navigator.onLine);

let busy = false;
export let farmRejected = '';
export async function syncNow() {
  const s = getState();
  if (busy || !navigator.onLine || !s.session || s.session.demo) return;
  busy = true;
  try {
    // Farm register: send queued edits (server applies them in order), then take the shared copy.
    const ops = s.farmOps;
    let farm: Register;
    try { farm = ops.length ? await api<Register>('/api/farm/ops', { body: { ops } }) : await api<Register>('/api/farm'); }
    catch (e) {
      // Refused (no permission / invalid): drop those edits and take the server's copy instead of retrying forever.
      if (!(e instanceof ApiFail) || (e.status !== 400 && e.status !== 403)) throw e;
      farmRejected = e.message;
      farm = await api<Register>('/api/farm');
    }
    setState(st => ({ farm: applyOps(farm, st.farmOps.slice(ops.length)), farmOps: st.farmOps.slice(ops.length) }));
  } catch { /* stays queued; retried on the next tick */ }
  try {
    if (!getState().outbox.length) return;
    const batch: SyncRecord[] = s.outbox.slice(0, 200);
    const { accepted } = await api<{ accepted: string[] }>('/api/sync', { body: { records: batch } });
    const ok = new Set(accepted);
    setState(st => ({
      outbox: st.outbox.filter(r => !ok.has(r.id)), lastSync: new Date().toISOString(),
      harvests: st.harvests.map(h => (h.rid && ok.has(h.rid) ? { ...h, synced: true } : h)),
      monLog: st.monLog.map(m => (m.rid && ok.has(m.rid) ? { ...m, synced: true } : m))
    }));
  } catch { /* stays queued; retried on the next tick */ }
  finally { busy = false; uploadPhotos().catch(() => {}); }
}

// Flush the outbox when signal returns and every minute while online.
export function useAutoSync() {
  const online = useOnline();
  useEffect(() => {
    if (!online) return;
    syncNow();
    const iv = setInterval(syncNow, 60_000);
    return () => clearInterval(iv);
  }, [online]);
}

export interface Fix { lat: number; lon: number; acc: number; alt: number | null }
export function oneFix(timeout = 15000): Promise<Fix> {
  return new Promise((res, rej) => {
    if (!('geolocation' in navigator)) return rej(new Error('This phone has no GPS access in the browser.'));
    navigator.geolocation.getCurrentPosition(
      p => res({ lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy, alt: p.coords.altitude }),
      e => rej(new Error(e.code === 1 ? 'Location permission is off. Allow it in the browser settings.' : 'No GPS fix yet. Step into the open and try again.')),
      { enableHighAccuracy: true, timeout, maximumAge: 10_000 });
  });
}

// Where the phone is: GPS every 2 minutes while the app is open, named offline from the bundled payam boundaries.
export function useLocationWatch() {
  useEffect(() => {
    let live = true;
    const tick = () => oneFix(20000).then(f => {
      const p = whereIs(f.lat, f.lon);
      if (live) setState({ where: { lat: f.lat, lon: f.lon, acc: f.acc, payam: p?.payam ?? 'Outside South Sudan', county: p?.county ?? '', state: p?.state ?? '', at: new Date().toISOString() } });
    }, () => {});
    tick();
    const iv = setInterval(tick, 120_000);
    return () => { live = false; clearInterval(iv); };
  }, []);
}

// The current place, or the farm point until the first GPS fix.
export function usePlace() {
  const w = useApp().where;
  if (w) return { ...w, gps: true };
  const p = whereIs(FARM.lat, FARM.lon);
  return { lat: FARM.lat, lon: FARM.lon, acc: null, payam: p?.payam ?? 'Duk Padiet', county: p?.county ?? 'Duk', state: p?.state ?? 'Jonglei', at: '', gps: false };
}
