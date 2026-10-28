import { conditionError, type PlotCondition } from './condition';

export const EW_ID = /^EW[‑-]?\d{3}$/;
export const WORKER_ID = /^(EW|AD)[‑-]\d{3}$/;
export const ACCESS_KEY = /^abk_[A-Za-z0-9]{6,}$/;

// The design writes IDs with a non-breaking hyphen (U+2011); accept both.
export const normId = (id: string) => id.trim().toUpperCase().replace('-', '‑');

export function harvestError(kg: number): string {
  if (!(kg > 0)) return 'Enter the weight in kilograms.';
  if (kg > 5000) return 'That is more than a full truck. Check the number.';
  return '';
}

export const MIN_PHOTOS = 3;
export function monitorError(m: { ew: string; acts: string[]; date: string; photos?: number; condition?: PlotCondition }): string {
  const errs: string[] = [];
  if (!EW_ID.test(m.ew)) errs.push('extension worker ID like EW‑014');
  if (!m.acts.length) errs.push('at least one activity');
  if (!m.date) errs.push('a date');
  if (m.condition) { const c = conditionError(m.condition); if (c) errs.push(c); }
  if (m.photos !== undefined && m.photos < MIN_PHOTOS) errs.push(`at least ${MIN_PHOTOS} photos (${m.photos} so far)`);
  return errs.length ? 'Add ' + errs.join(', ') + '.' : '';
}

export function signinError(id: string, key: string): string {
  if (!WORKER_ID.test(id)) return 'Worker ID looks like EW‑014.';
  if (!key.startsWith('abk_') || key.length < 10) return 'That key is not valid. Keys start with abk_.';
  return '';
}

export type GaugeVerdict = { kind: 'bad' } | { kind: 'held'; v: number } | { kind: 'ok'; v: number };
export const GAUGE_MAX_JUMP = 0.3;

// "G 4.12", "g4.12" → metres. Jumps over 30 cm from the last reading wait for an admin.
export function parseGauge(text: string, last: number | null): GaugeVerdict {
  const m = text.trim().match(/^g\s*(\d+(?:\.\d+)?)$/i);
  if (!m) return { kind: 'bad' };
  const v = Number(m[1]);
  if (last !== null && Math.abs(v - last) > GAUGE_MAX_JUMP) return { kind: 'held', v };
  return { kind: 'ok', v };
}
