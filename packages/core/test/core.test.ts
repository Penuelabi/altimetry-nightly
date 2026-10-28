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

import { applyOps, seedRegister, opError, plotLabel } from '../src';
describe('farm register', () => {
  it('seeds the design farm', () => {
    const r = seedRegister();
    expect(r.plots.map(p => p.code)).toContain('B‑07');
    expect(r.groups.find(g => g.id === 'g4')!.members).toHaveLength(12);
  });
  it('applies upserts, removes and work days in order', () => {
    let r = seedRegister();
    r = applyOps(r, [
      { op: 'upsert', kind: 'crop', item: { id: 'shea-nuts', name: 'Shea nuts' } },
      { op: 'upsert', kind: 'plot', item: { ...r.plots[0], code: 'R‑02a' } },
      { op: 'remove', kind: 'plot', id: 'S‑01' },
      { op: 'workdays', groupId: 'g4', memberIds: ['g4m1'] }
    ]);
    expect(r.crops.at(-1)!.name).toBe('Shea nuts');
    expect(r.plots[0].code).toBe('R‑02a');
    expect(r.plots.some(p => p.id === 'S‑01')).toBe(false);
    expect(r.groups.find(g => g.id === 'g4')!.members[0].workDays).toBe(42);
    expect(r.version).toBe(5);
    expect(plotLabel(r.plots.find(p => p.id === 'B‑07')!, r)).toBe('B‑07 · Group 4');
  });
  it('validates ops', () => {
    expect(opError({ op: 'upsert', kind: 'crop', item: { id: 'x', name: ' ' } })).toMatch(/name/);
    expect(opError({ op: 'remove', kind: 'plot', id: '' })).toMatch(/id/);
  });
});

import { conditionSummary } from '../src';
describe('plot condition', () => {
  const base = { moisture: 'wet', water: 'none', floodDepthCm: '', around: 'dry', aroundDepthCm: '', aroundDistanceM: '', trend: '', surface: [] as string[], crackWidth: '' };
  it('asks for what is missing', () => {
    expect(monitorError({ ew: 'EW-014', acts: ['Weeding'], date: 'x', condition: { ...base, moisture: '' } })).toBe('Add soil moisture.');
    expect(monitorError({ ew: 'EW-014', acts: ['Weeding'], date: 'x', condition: { ...base, water: 'flooded' } })).toBe('Add the water depth on the plot in cm.');
    expect(monitorError({ ew: 'EW-014', acts: ['Weeding'], date: 'x', condition: { ...base, around: 'nearby', aroundDepthCm: '40' } })).toBe('Add how far away the nearest water is in metres.');
    expect(monitorError({ ew: 'EW-014', acts: ['Weeding'], date: 'x', condition: { ...base, around: 'edge', aroundDepthCm: '40' } })).toBe('Add whether the water is rising or falling.');
    expect(monitorError({ ew: 'EW-014', acts: ['Weeding'], date: 'x', condition: { ...base, surface: ['cracking'] } })).toBe('Add the crack width.');
  });
  it('summarises in plain words', () => {
    expect(conditionSummary({ ...base, moisture: 'dry', surface: ['cracking', 'silt'], crackWidth: 'wide' })).toBe('Dry, wide cracks, silt deposited');
    expect(conditionSummary({ ...base, water: 'flooded', floodDepthCm: '30', around: 'surrounding', aroundDepthCm: '60', trend: 'falling' })).toBe('Wet, flooded 30 cm, water surrounding 60 cm, falling');
  });
});
