import { MOUNDS } from './seed';
import { haversineKm } from './geo';

// Linear recession model: basin water depth falls `rate` m/day from `d0` today.
// d0 and rate come from field measurements when there are any (fitModel); the design's
// figures are only the fallback and are labelled as such.
export const D0 = 0.92;
export const RATE = 0.025;
// The slope zone sits about 0.70 m above the basin floor (farm survey), so it holds water only
// when the basin is deeper than that.
export const SLOPE_STEP = 0.70;
export const CREST = 1.0;

// used says what the fit rests on: the plots read, how many readings, how near, and whether the river gauge set the fall rate.
export interface ModelBasis { plots: string[]; readings: number; radiusKm: number; gauge: boolean }
export interface Model { d0: number; rate: number; d0Src: string; rateSrc: string; measured: boolean; used?: ModelBasis }
export const DEFAULT_MODEL: Model = { d0: D0, rate: RATE, d0Src: 'design example (no depth measured nearby yet)', rateSrc: 'design assumption, 2.5 cm a day', measured: false };

export const basinDepth = (day: number, m: Pick<Model, 'd0' | 'rate'> = DEFAULT_MODEL) => Math.min(2, Math.max(0, m.d0 - m.rate * day));
export const slopeDepth = (day: number, m: Pick<Model, 'd0' | 'rate'> = DEFAULT_MODEL) => Math.max(0, basinDepth(day, m) - SLOPE_STEP);
// Water depth in each zone today. The ridge stays dry in a normal year; the slope sits SLOPE_STEP above the basin floor.
export const zoneDepths = (m: Pick<Model, 'd0' | 'rate'> = DEFAULT_MODEL, day = 0) => ({ ridge: 0, slope: slopeDepth(day, m), basin: basinDepth(day, m) });
// Days until the basin is dry; null when the water is not falling.
export const recessDays = (m: Pick<Model, 'd0' | 'rate'> = DEFAULT_MODEL) => (m.d0 <= 0 ? 0 : m.rate > 0 ? Math.ceil(m.d0 / m.rate) : null);

export const dayLabel = (n: number, from = new Date()) => {
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + n);
  return d.getDate() + ' ' + d.toLocaleString('en', { month: 'short' });
};

export type MoundState = 'submerged' | 'risk' | 'clear';
export const moundState = (crest: number, depth: number): MoundState =>
  crest < depth ? 'submerged' : crest - depth < 0.08 ? 'risk' : 'clear';

export function moundRows(depth: number, m: Pick<Model, 'd0' | 'rate'> = DEFAULT_MODEL, mounds: [string, number][] = MOUNDS) {
  return mounds.map(([id, h]) => {
    const st = moundState(h, depth);
    const clearIn = m.rate > 0 ? Math.ceil((m.d0 - h) / m.rate) : null;
    return {
      id, h, state: st,
      status: st === 'submerged' ? (clearIn != null ? `submerged · clear ${dayLabel(clearIn)}` : 'submerged · water not falling') : st === 'risk' ? 'at risk · <8 cm freeboard' : 'clear'
    };
  });
}

// When the water next rises: now, if the fitted level is rising; else the start of the flood season
// (river rise usually begins in July at Bor), labelled as seasonal.
export function nextRise(m: Pick<Model, 'rate'>, now = new Date()) {
  if (m.rate < 0) return { when: 'rising now', src: 'water level is going up' };
  const y = now.getMonth() >= 6 ? now.getFullYear() + 1 : now.getFullYear();
  return { when: `~Jul ${y}`, src: 'seasonal: the White Nile at Bor usually starts rising in July' };
}

export function headline(depth: number) {
  if (depth <= 0) return 'Basin dry. Sow now.';
  if (MOUNDS.some(([, h]) => h < depth)) return 'One mound row still under water.';
  if (depth < 0.25) return 'Silt exposed at the basin edges.';
  return 'All mound crests clear.';
}

export function plantAlert(depth: number, m: Pick<Model, 'd0' | 'rate'> = DEFAULT_MODEL) {
  const days = recessDays(m);
  if (depth <= 0) return 'Basin silt is exposed now: broadcast cowpea, sorghum and kudra seed within the next 10 days while moisture is high.';
  if (days == null) return 'The water is not falling yet, so no sowing date can be given. Check again after the next gauge reading or crop check.';
  const slope = m.d0 <= SLOPE_STEP ? 'Slope plots are already clear of water.' : `Slope plots can be sown from ${dayLabel(Math.ceil((m.d0 - SLOPE_STEP) / m.rate))}.`;
  return `Sow cowpea, Feterita sorghum and kudra into the wet silt from about ${dayLabel(Math.max(0, days - 3))}, as the basin edge dries. ${slope}`;
}

// ---- fitting the model to what has been measured near the phone ----
export interface DepthObs { at: string; plot: string; lat: number; lon: number; depthCm: number | null; water: string }
export interface GaugeObs { at: string; v: number }

const WET = ['flooded', 'waterlogged', 'ponding', 'receding'];
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };

export function fitModel(obs: DepthObs[], gauge: GaugeObs[], at: { lat: number; lon: number }, now = new Date(), radiusKm = 2): Model {
  const recent = obs.filter(o => Date.parse(o.at) >= now.getTime() - 21 * 864e5 && haversineKm(at, o) <= radiusKm);
  const days = (a: string, b: string) => (Date.parse(a) - Date.parse(b)) / 864e5;

  // Starting depth: the deepest latest reading per plot from the last two weeks; a dry plot counts as 0.
  const latest = new Map<string, DepthObs>();
  for (const o of [...recent].sort((a, b) => b.at.localeCompare(a.at))) if (!latest.has(o.plot)) latest.set(o.plot, o);
  const fresh = [...latest.values()].filter(o => days(now.toISOString(), o.at) <= 14);
  const depths = fresh.map(o => (WET.includes(o.water) ? (o.depthCm ?? 0) : 0) / 100);
  let d0 = D0, d0Src = DEFAULT_MODEL.d0Src, measured = false, d0At: string | null = null;
  if (fresh.length) {
    const deepest = fresh.reduce((a, b) => ((WET.includes(b.water) ? b.depthCm ?? 0 : 0) > (WET.includes(a.water) ? a.depthCm ?? 0 : 0) ? b : a));
    d0 = Math.max(...depths); measured = true; d0At = deepest.at;
    d0Src = `${Math.round(d0 * 100)} cm measured at ${deepest.plot}, ${new Date(deepest.at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`;
  }

  // Fall rate: repeated depth readings of the same plot, else the Bor gauge trend, else the design figure.
  const slopes: number[] = [];
  const byPlot = new Map<string, DepthObs[]>();
  for (const o of recent) if (o.depthCm != null && WET.includes(o.water)) byPlot.set(o.plot, [...(byPlot.get(o.plot) ?? []), o]);
  for (const list of byPlot.values()) {
    const s = list.sort((a, b) => a.at.localeCompare(b.at));
    for (let k = 1; k < s.length; k++) { const dt = days(s[k].at, s[k - 1].at); if (dt >= 0.5) slopes.push((s[k - 1].depthCm! - s[k].depthCm!) / 100 / dt); }
  }
  let rate = RATE, rateSrc = DEFAULT_MODEL.rateSrc;
  if (slopes.length) { rate = median(slopes); rateSrc = `${(rate * 100).toFixed(1)} cm a day ${rate >= 0 ? 'fall' : 'rise'}, from ${slopes.length} repeat depth reading${slopes.length > 1 ? 's' : ''}`; }
  else {
    const g = [...gauge].sort((a, b) => a.at.localeCompare(b.at)).filter(x => Date.parse(x.at) >= now.getTime() - 14 * 864e5);
    if (g.length >= 2) {
      const dt = days(g[g.length - 1].at, g[0].at);
      if (dt >= 1) { rate = (g[0].v - g[g.length - 1].v) / dt; rateSrc = `${(Math.abs(rate) * 100).toFixed(1)} cm a day ${rate >= 0 ? 'fall' : 'rise'} at the Bor gauge over ${Math.round(dt)} days (river used as a guide for the basin)`; }
    }
  }
  // Bring the measured depth forward from the day it was read to today.
  if (d0At) d0 = Math.max(0, d0 - rate * days(now.toISOString(), d0At));
  const gaugeUsed = !slopes.length && rateSrc !== DEFAULT_MODEL.rateSrc;
  return { d0, rate, d0Src, rateSrc, measured, used: { plots: [...new Set(recent.filter(o => o.depthCm != null || WET.includes(o.water) || o.water).map(o => o.plot))], readings: recent.length, radiusKm, gauge: gaugeUsed } };
}
