// Water-level stations (river gauges and lakes from satellite altimetry): their latest readings, nearest to a place.
import { haversineKm, type LatLon } from './geo';
import type { PayamArea } from './admin';

export interface Obs { d: string; v: number }
// Where a station sits on the river network compared with the place asked about (from the HydroBASINS network):
// upstream of it, on the same stretch (mid-stream), or downstream of it. Absent when the station is not on its river network.
export type StreamRelation = 'upstream' | 'local' | 'downstream';
export interface StationSeries { uid: string; name: string; type: string; lat: number; lon: number; km: number; obs: Obs[]; relation?: StreamRelation }
export interface StationLevels {
  at: string;
  from: LatLon;
  // Date of the newest observation among the stations returned.
  asOf: string;
  stations: StationSeries[];
  // True when the server could not refresh the data and sent what it had.
  stale?: boolean;
}

// The middle of a payam: the average of the corners of its largest piece. Good enough to ask "which station is nearest".
export function payamCentre(a: Pick<PayamArea, 'polygons'>): LatLon {
  const ring = a.polygons.map(p => p[0]).filter(Boolean).sort((x, y) => y.length - x.length)[0] ?? [];
  if (!ring.length) return { lat: 0, lon: 0 };
  return { lon: ring.reduce((n, p) => n + p[0], 0) / ring.length, lat: ring.reduce((n, p) => n + p[1], 0) / ring.length };
}

// The middle of a county: the average of its payams' middles.
export function countyCentre(payams: Pick<PayamArea, 'polygons'>[]): LatLon {
  const cs = payams.map(payamCentre).filter(c => c.lat || c.lon);
  if (!cs.length) return { lat: 0, lon: 0 };
  return { lat: cs.reduce((n, c) => n + c.lat, 0) / cs.length, lon: cs.reduce((n, c) => n + c.lon, 0) / cs.length };
}

export const RELATION_LABEL: Record<StreamRelation, string> = { upstream: 'Upstream', local: 'Mid-stream', downstream: 'Downstream' };
// One sentence on what the relation means for the place.
export function relationNote(rel: StreamRelation, place: string): string {
  if (rel === 'upstream') return `Upstream of ${place}: water that passes this station flows on toward ${place}, so a rise here is an early warning.`;
  if (rel === 'local') return `Mid-stream: this station is on the river reach that drains ${place}, so it shows what the water is doing there.`;
  return `Downstream of ${place}: water here has already passed ${place}; a high level here can back water up toward it.`;
}

// The n stations nearest to a point, each with its newest `obs` observations (oldest first).
export function nearestStations<T extends LatLon & { obs: Obs[] }>(list: T[], at: LatLon, n = 3, obs = 10): (T & { km: number })[] {
  return list.filter(s => s.obs.length)
    .map(s => ({ ...s, km: Math.round(haversineKm(at, s) * 10) / 10, obs: s.obs.slice(-obs) }))
    .sort((a, b) => a.km - b.km)
    .slice(0, n);
}

export interface ChartSummary { min: Obs; max: Obs; last: Obs; change: number | null }
// What the chart labels: lowest and highest observation, the latest, and how far it moved from the one before.
export function levelSummary(obs: Obs[]): ChartSummary | null {
  if (!obs.length) return null;
  let min = obs[0], max = obs[0];
  for (const o of obs) { if (o.v < min.v) min = o; if (o.v > max.v) max = o; }
  const last = obs[obs.length - 1];
  return { min, max, last, change: obs.length > 1 ? Math.round((last.v - obs[obs.length - 2].v) * 1000) / 1000 : null };
}

// How a station's distance should be described: close enough to stand for the place, or only the nearest there is.
export function distanceNote(km: number): string {
  if (km <= 25) return 'close enough to show what the water is doing here';
  if (km <= 80) return 'some way off; it shows the wider river, not this place';
  return 'far away; it is only the nearest station in the data, so read it as the wider river or lake';
}
