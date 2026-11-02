// What a flood could reach inside one payam: people, buildings, schools and health facilities, with how many are at risk.
// The numbers come from payam_exposure.csv in the project Drive folder; nothing is worked out in the app.

// total or risk is null when the file leaves that cell empty.
export interface Count { total: number | null; risk: number | null }
export interface Exposure {
  pcode: string;
  payam: string;
  county: string;
  // What "at risk" means in this file, e.g. "flooded at least twice in 2019-2025". Shown so nobody has to guess.
  hazard: string;
  asOf: string;
  population: Count;
  buildings: Count;
  schools: Count;
  health: Count;
}
export interface ExposureResult {
  at: string;
  // False when payam_exposure.csv is not in the Drive folder at all.
  fileFound: boolean;
  row: Exposure | null;
  stale?: boolean;
}

// Percent of the total that is at risk, to the nearest whole number; null when either figure is missing or the total is 0.
export function riskShare(c: Count): number | null {
  if (c.total == null || c.risk == null || c.total <= 0) return null;
  return Math.round(Math.min(100, (c.risk / c.total) * 100));
}

// "1,200" for 1200, "—" when unknown.
export const countText = (n: number | null): string => (n == null ? '—' : n.toLocaleString('en-GB'));
