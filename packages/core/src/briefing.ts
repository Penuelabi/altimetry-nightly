// The home-screen briefing, built only from data near the phone: weather at the GPS point,
// river gauge readings, and recent crop checks within RADIUS_KM. Nothing here is invented;
// missing data is said plainly. Pure so it can be tested.
import { haversineKm } from './geo';
import { RATE } from './flood';

export const RADIUS_KM = 2;
export const RECENT_DAYS = 7;

export interface BriefCheck { at: string; plot: string; lat: number; lon: number; water: string; depthCm: number | null; around: string; aroundDepthCm: number | null; trend: string }
export interface BriefGauge { at: string; v: number }
export interface BriefStation { name: string; km: number; level: number | null; vs2yr: number | null; ratePerDay: number | null; levelClass: string }
export interface BriefWeather { temp: number; rain24: number; sky: string; at: string }
// Earth Engine values for a small radius around the phone (flood extent % of area, SMAP root-zone m³/m³).
export interface BriefSatellite { floodPct: number | null; soil: number | null; radiusKm: number }
export interface BriefInput { now: Date; name: string; place: { lat: number; lon: number; payam: string }; gauge: BriefGauge[]; station: BriefStation | null; checks: BriefCheck[]; weather: BriefWeather | null; satellite?: BriefSatellite | null; rate?: { v: number; measured: boolean } }
export interface Tile { k: string; v: string; s: string }
export interface Briefing { kicker: string; headline: string; body: string[]; tiles: [Tile, Tile, Tile] }

// Seasons follow the farm calendar: recession Dec–Jan, dry Feb–Apr, rains May–Jul, flood Aug–Nov.
const SEASONS: { name: string; start: [number, number] }[] = [
  { name: 'Recession', start: [11, 1] }, { name: 'Dry season', start: [1, 1] }, { name: 'Rains', start: [4, 1] }, { name: 'Flood season', start: [7, 1] }
];
export function season(now: Date) {
  const m = now.getMonth();
  const name = m === 11 || m === 0 ? 'Recession' : m <= 3 ? 'Dry season' : m <= 6 ? 'Rains' : 'Flood season';
  const s = SEASONS.find(x => x.name === name)!;
  let start = new Date(now.getFullYear(), s.start[0], s.start[1]);
  if (start > now) start = new Date(now.getFullYear() - 1, s.start[0], s.start[1]);
  return { name, week: Math.floor((now.getTime() - start.getTime()) / (7 * 864e5)) + 1 };
}

export const greeting = (now: Date) => (now.getHours() < 12 ? 'Good morning' : now.getHours() < 17 ? 'Good afternoon' : 'Good evening');

export const soilWord = (v: number) => (v < 0.15 ? 'dry' : v < 0.3 ? 'moist' : 'wet');
const cm = (m: number) => `${Math.abs(Math.round(m * 100))} cm`;
const WET = ['flooded', 'waterlogged', 'ponding', 'receding'];

export function briefing(i: BriefInput): Briefing {
  const sea = season(i.now);
  const date = i.now.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).replace(',', '');
  const first = i.name.split(' ')[0];
  const body: string[] = [];

  // River: the project's own gauge first, else the nearest satellite station from the last pull.
  const g = [...i.gauge].sort((a, b) => b.at.localeCompare(a.at));
  let river: Tile = { k: 'River', v: '—', s: 'no gauge reading yet' };
  let trendWord = '';
  if (g[0]) {
    const prev = g[1], days = prev ? Math.max(1, Math.round((Date.parse(g[0].at) - Date.parse(prev.at)) / 864e5)) : 0;
    const d = prev ? g[0].v - prev.v : 0;
    trendWord = !prev ? '' : d < -0.005 ? 'falling' : d > 0.005 ? 'rising' : 'steady';
    river = { k: 'Bor gauge', v: `${g[0].v.toFixed(2)} m`, s: prev ? `${d < 0 ? '↓' : d > 0 ? '↑' : '→'} ${cm(d)}${days > 1 ? ` in ${days} days` : ' since last'}` : 'first reading' };
    body.push(prev ? `The river at Bor is ${trendWord}: ${g[0].v.toFixed(2)} m, ${d === 0 ? 'no change' : `${d < 0 ? 'down' : 'up'} ${cm(d)}`} since the reading before.` : `The river at Bor read ${g[0].v.toFixed(2)} m.`);
  } else if (i.station) {
    const st = i.station, r = st.ratePerDay;
    trendWord = r == null ? '' : r < -0.002 ? 'falling' : r > 0.002 ? 'rising' : 'steady';
    river = { k: 'River', v: st.vs2yr != null ? `${st.vs2yr > 0 ? '+' : '−'}${Math.abs(st.vs2yr).toFixed(2)} m` : st.levelClass || '—', s: `${st.name}, ${Math.round(st.km)} km${r != null ? ` · ${trendWord}` : ''}` };
    body.push(`Nearest river station (${st.name}, ${Math.round(st.km)} km away) is ${st.levelClass ? st.levelClass.toLowerCase() : 'reporting'}${r != null ? ` and ${trendWord}` : ''}. No Bor gauge reading yet.`);
  } else body.push('No river reading yet: enter the Bor gauge, or pull data sources.');

  // Plots near you, from this phone's recent crop checks.
  const since = i.now.getTime() - RECENT_DAYS * 864e5;
  const near = i.checks.filter(c => Date.parse(c.at) >= since && haversineKm(i.place, c) <= RADIUS_KM);
  const latest = new Map<string, BriefCheck>();
  for (const c of [...near].sort((a, b) => b.at.localeCompare(a.at))) if (!latest.has(c.plot)) latest.set(c.plot, c);
  const plots = [...latest.values()];
  const wet = plots.filter(c => WET.includes(c.water));
  const cut = plots.filter(c => c.around === 'cut-off' || c.around === 'surrounding');
  const rising = plots.filter(c => c.trend === 'rising').length, falling = plots.filter(c => c.trend === 'falling').length;
  const deepest = Math.max(0, ...wet.map(c => c.depthCm ?? 0));
  let water: Tile;
  let headline: string;
  if (!plots.length) {
    water = { k: 'Plots near you', v: '—', s: `no crop checks within ${RADIUS_KM} km this week` };
    headline = trendWord === 'rising' ? 'The river is rising.' : trendWord === 'falling' ? 'The river is falling.' : 'No field reports nearby yet.';
    body.push(`No crop checks within ${RADIUS_KM} km of you in the last ${RECENT_DAYS} days. A crop check here will fill this in.`);
  } else {
    water = { k: 'Water on plots', v: wet.length ? `${deepest} cm` : 'none', s: `${wet.length} of ${plots.length} plots wet${cut.length ? ` · ${cut.length} surrounded` : ''}` };
    headline = rising > falling && (wet.length || cut.length) ? 'Water is rising around plots.'
      : wet.length && falling >= rising ? 'The plots are draining.'
      : wet.length ? 'Some plots are under water.' : 'Plots near you are clear of water.';
    const named = wet.slice(0, 3).map(c => `${c.plot}${c.depthCm ? ` ${c.depthCm} cm` : ''}`).join(', ');
    body.push(wet.length ? `Under water or waterlogged: ${named}${wet.length > 3 ? ` and ${wet.length - 3} more` : ''}.` : `${plots.length} plot${plots.length > 1 ? 's' : ''} checked nearby this week, none under water.`);
    if (cut.length) body.push(`Water surrounds ${cut.map(c => c.plot).slice(0, 3).join(', ')}${cut.length > 3 ? ' and others' : ''}.`);
      const rate = i.rate && i.rate.v > 0 ? i.rate : { v: RATE, measured: false };
    if (wet.length && falling >= rising && deepest > 0) body.push(`At ${Math.round(rate.v * 1000) / 10} cm a day${rate.measured ? ' (measured)' : ' (design estimate)'}, the deepest plot could drain in roughly ${Math.ceil(deepest / (rate.v * 100))} days.`);
  }

  // Satellite view of the area around the phone. Soil classes are rough guides for clay soils.
  const sat = i.satellite;
  if (sat && (sat.floodPct != null || sat.soil != null)) {
    const parts: string[] = [];
    if (sat.floodPct != null) parts.push(`${sat.floodPct}% of the land within ${sat.radiusKm} km shows as flooded on the latest satellite flood map`);
    if (sat.soil != null) parts.push(`root-zone soil moisture is ${sat.soil.toFixed(2)} m³/m³ (${soilWord(sat.soil)})`);
    body.push(`Satellite: ${parts.join('; ')}.`);
  }

  const w = i.weather;
  const today: Tile = w ? { k: 'Today here', v: `${Math.round(w.temp)}°`, s: `${w.rain24 > 0 ? `${w.rain24} mm rain, 24 h` : 'no rain, 24 h'} · ${w.sky.toLowerCase()}` } : { k: 'Today here', v: '—', s: 'weather loads with signal' };

  return { kicker: `${date} · ${sea.name}, week ${sea.week} · ${i.place.payam}`, headline: `${greeting(i.now)}, ${first}. ${headline}`, body, tiles: [river, water, today] };
}
