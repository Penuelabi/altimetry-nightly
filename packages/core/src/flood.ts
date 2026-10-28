import { MOUNDS } from './seed';

// Linear recession model from the design: basin depth falls RATE m/day from D0.
export const D0 = 0.92;
export const RATE = 0.025;
export const SLOPE_D0 = 0.22;
export const SLOPE_RATE = 0.03;
export const CREST = 1.0;
export const TODAY = new Date(2026, 9, 28);

export const basinDepth = (day: number, d0 = D0) => Math.max(0, d0 - RATE * day);
export const slopeDepth = (day: number) => Math.max(0, SLOPE_D0 - SLOPE_RATE * day);
export const recessDays = (d0 = D0) => Math.ceil(d0 / RATE);

export const dayLabel = (n: number, from = TODAY) => {
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + n);
  return d.getDate() + ' ' + d.toLocaleString('en', { month: 'short' });
};

export type MoundState = 'submerged' | 'risk' | 'clear';
export const moundState = (crest: number, depth: number): MoundState =>
  crest < depth ? 'submerged' : crest - depth < 0.08 ? 'risk' : 'clear';

export function moundRows(depth: number, d0 = D0) {
  return MOUNDS.map(([id, h]) => {
    const st = moundState(h, depth);
    return {
      id, h, state: st,
      status: st === 'submerged' ? `submerged · clear ${dayLabel(Math.ceil((d0 - h) / RATE))}` : st === 'risk' ? 'at risk · <8 cm freeboard' : 'clear'
    };
  });
}

export function headline(depth: number) {
  if (depth <= 0) return 'Basin dry. Sow now.';
  if (MOUNDS.some(([, h]) => h < depth)) return 'One mound row still under water.';
  if (depth < 0.25) return 'Silt exposed at the basin edges.';
  return 'All mound crests clear.';
}

export function plantAlert(depth: number, d0 = D0) {
  return depth > 0
    ? `Sow cowpea, Feterita sorghum and kudra into the wet silt from about ${dayLabel(recessDays(d0) - 3)}, as the basin edge dries. Slope plots can be sown from ${dayLabel(Math.ceil(SLOPE_D0 / SLOPE_RATE))}.`
    : 'Basin silt is exposed now: broadcast cowpea, sorghum and kudra seed within the next 10 days while moisture is high.';
}
