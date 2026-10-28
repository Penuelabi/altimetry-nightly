import { describe, expect, it } from 'vitest';
import { basinDepth, recessDays, moundRows, headline, parseGauge, monitorError, harvestError, signinError, withinRadius, polygonHa, qrCells, normId } from '../src';

describe('flood model', () => {
  it('matches the design numbers', () => {
    expect(recessDays()).toBe(37);
    expect(basinDepth(0)).toBeCloseTo(0.92);
    expect(basinDepth(100)).toBe(0);
  });
  it('flags only B‑05 submerged and B‑08 at risk today', () => {
    const rows = moundRows(basinDepth(0));
    expect(rows.filter(r => r.state === 'submerged').map(r => r.id)).toEqual(['B‑05']);
    expect(rows.find(r => r.id === 'B‑08')!.state).toBe('risk');
    expect(headline(basinDepth(0))).toBe('One mound row still under water.');
    expect(headline(0)).toBe('Basin dry. Sow now.');
  });
});

describe('validation', () => {
  it('parses gauge texts', () => {
    expect(parseGauge('G 4.12', 4.15)).toEqual({ kind: 'ok', v: 4.12 });
    expect(parseGauge('g4.18', 4.15)).toEqual({ kind: 'ok', v: 4.18 });
    expect(parseGauge('G 41.2', 4.15)).toEqual({ kind: 'held', v: 41.2 });
    expect(parseGauge('hello', 4.15)).toEqual({ kind: 'bad' });
  });
  it('checks forms', () => {
    expect(monitorError({ ew: '', acts: [], date: '' })).toBe('Add extension worker ID like EW‑014, at least one activity, a date.');
    expect(monitorError({ ew: 'EW-014', acts: ['Weeding'], date: '2026-10-28' })).toBe('');
    expect(monitorError({ ew: 'EW-014', acts: ['Weeding'], date: '2026-10-28', photos: 1 })).toBe('Add at least 3 photos (1 so far).');
    expect(monitorError({ ew: 'EW-014', acts: ['Weeding'], date: '2026-10-28', photos: 3 })).toBe('');
    expect(harvestError(0)).toMatch(/weight/);
    expect(harvestError(6000)).toMatch(/truck/);
    expect(signinError('EW-014', 'abk_123456')).toBe('');
    expect(signinError('X', 'abk_123456')).toMatch(/EW‑014/);
    expect(normId('ew-014')).toBe('EW‑014');
  });
});

describe('geo', () => {
  it('falls back to nearest stations when none are in range', () => {
    const r = withinRadius([{ lat: 7.3975, lon: 30.6476 }, { lat: 9, lon: 33 }], { lat: 7.731, lon: 31.402 }, 20, 1);
    expect(r.fallback).toBe(true);
    expect(Math.round(r.rows[0].km)).toBe(91);
  });
  it('computes a 1 ha square', () => {
    const d = 100 / 111320;
    const ha = polygonHa([{ lat: 0, lon: 0 }, { lat: 0, lon: d }, { lat: d, lon: d }, { lat: d, lon: 0 }]);
    expect(ha).toBeCloseTo(1, 1);
  });
  it('draws QR finder squares', () => {
    expect(qrCells('BAL‑26‑03').some(c => c.x === 0 && c.y === 0)).toBe(true);
  });
});

import { whereIs } from '../src';
describe('payam lookup', () => {
  it('places the farm point in Duk county, Jonglei', () => {
    const p = whereIs(7.731, 31.402);
    expect(p).toMatchObject({ county: 'Duk', state: 'Jonglei' });
  });
  it('places Juba in Central Equatoria', () => {
    expect(whereIs(4.85, 31.58)?.state).toBe('Central Equatoria');
  });
  it('returns null outside South Sudan', () => {
    expect(whereIs(0, 0)).toBeNull();
  });
});
