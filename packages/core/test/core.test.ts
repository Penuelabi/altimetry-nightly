import { describe, expect, it } from 'vitest';
import { blankPerson, normPhone, personError, productToStore, zoneDepths, basinDepth, recessDays, moundRows, headline, parseGauge, monitorError, harvestError, signinError, withinRadius, polygonHa, pointInPolygon, plotForGps, qrCells, normId } from '../src';

describe('flood model', () => {
  it('matches the design numbers', () => {
    expect(recessDays()).toBe(37);
    expect(recessDays({ d0: 0.5, rate: -0.01 })).toBeNull();
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
  it('detects point inside polygon', () => {
    const square = [{ lat: 0, lon: 0 }, { lat: 0, lon: 1 }, { lat: 1, lon: 1 }, { lat: 1, lon: 0 }];
    expect(pointInPolygon({ lat: 0.5, lon: 0.5 }, square)).toBe(true);
    expect(pointInPolygon({ lat: 2, lon: 2 }, square)).toBe(false);
    expect(pointInPolygon({ lat: 0.5, lon: 0.5 }, [])).toBe(false);
  });
  it('finds the right plot for a GPS point', () => {
    const plots = [
      { id: 'p1', code: 'A-01', boundary: [{ lat: 7.73, lon: 31.40 }, { lat: 7.73, lon: 31.41 }, { lat: 7.74, lon: 31.41 }, { lat: 7.74, lon: 31.40 }] },
      { id: 'p2', code: 'A-02', boundary: [{ lat: 7.75, lon: 31.40 }, { lat: 7.75, lon: 31.41 }, { lat: 7.76, lon: 31.41 }, { lat: 7.76, lon: 31.40 }] },
    ];
    const m1 = plotForGps({ lat: 7.735, lon: 31.405 }, plots);
    expect(m1).toMatchObject({ id: 'p1', code: 'A-01', inside: true });
    const m2 = plotForGps({ lat: 7.755, lon: 31.405 }, plots);
    expect(m2).toMatchObject({ id: 'p2', code: 'A-02', inside: true });
    expect(plotForGps({ lat: 0, lon: 0 }, plots)).toBeNull();
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

import { listPayams, payamAt, payamByCode, payamsIn, polygonAreaKm2 } from '../src';
describe('payam boundaries for satellite averaging', () => {
  it('finds the payam a GPS point falls in, with its boundary and area', () => {
    const a = payamAt(7.731, 31.402);
    expect(a?.county).toBe('Duk');
    expect(a?.polygons.length).toBeGreaterThan(0);
    expect(a!.areaKm2).toBeGreaterThan(100);
    expect(a!.areaKm2).toBeLessThan(1200);
  });
  it('looks the same payam up by its code', () => {
    const a = payamAt(7.731, 31.402)!;
    expect(payamByCode(a.pcode)?.payam).toBe(a.payam);
    expect(payamByCode('nope')).toBeNull();
  });
  it('lists every payam and the six in Duk county (Ageer and Dongchak have no county in the source file)', () => {
    expect(listPayams().length).toBe(517);
    expect(payamsIn('Duk', 'Jonglei').map(p => p.payam).sort()).toEqual(['Ageer', 'Dongchak', 'Duk Padiet', 'Duk Payuel', 'Pagak', 'Panyang']);
  });
  it('fills a blank state and county from the payam code, so the pickers can group every payam', () => {
    const all = listPayams();
    expect(all.every(p => p.state && p.county)).toBe(true);
    expect(all.every(p => p.state !== 'Unknown state')).toBe(true);
    expect(payamByCode('SS070502')).toMatchObject({ payam: 'Buny', state: 'Upper Nile' });
    expect(payamByCode('SS070502')!.county).not.toMatch(/^Unnamed/);
    expect(payamByCode('SS060401')).toMatchObject({ payam: 'Adok', state: 'Unity' });
    expect(payamByCode('SS060401')!.county).not.toMatch(/^Unnamed/);
    expect(payamByCode('SS070802')).toMatchObject({ payam: 'Kaka', state: 'Upper Nile', county: 'Unnamed county (SS0708)' });
  });
  it('keeps payam codes unique, since the server looks payams up by code', () => {
    const codes = listPayams().map(p => p.pcode);
    expect(new Set(codes).size).toBe(codes.length);
    expect(codes.every(c => /^SS\d{6}$/.test(c))).toBe(true);
  });
  it('measures area on the ground and subtracts holes', () => {
    const square = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]];
    const hole = [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75], [0.25, 0.25]];
    const full = polygonAreaKm2([[square]]);
    expect(full).toBeGreaterThan(12000);
    expect(full).toBeLessThan(12500);
    expect(polygonAreaKm2([[square, hole]])).toBeCloseTo(full * 0.75, -2);
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

import { herdCount, herdLabel, opAllowed, type Herd, type LivestockEvent } from '../src';
describe('livestock, forest & fish register', () => {
  const herd: Herd = { id: 'hd1', species: 'goat', ownerType: 'group', ownerId: 'g4', ownerName: 'Group 4' };
  it('labels a herd', () => expect(herdLabel(herd)).toBe('Goat · Group 4'));
  it('derives head count from the event log, not a stored number', () => {
    let r = seedRegister();
    r = applyOps(r, [
      { op: 'upsert', kind: 'herd', item: herd },
      { op: 'upsert', kind: 'livestockEvent', item: { id: 'e1', herdId: 'hd1', kind: 'opening', date: '2026-10-01', qty: 10, note: '', by: 'w1' } },
      { op: 'upsert', kind: 'livestockEvent', item: { id: 'e2', herdId: 'hd1', kind: 'birth', date: '2026-10-10', qty: 2, note: '', by: 'w1' } },
      { op: 'upsert', kind: 'livestockEvent', item: { id: 'e3', herdId: 'hd1', kind: 'death', date: '2026-10-15', qty: 1, note: 'disease', by: 'w1' } },
      { op: 'upsert', kind: 'livestockEvent', item: { id: 'e4', herdId: 'hd1', kind: 'milk', date: '2026-10-20', qty: 3, note: 'litres', by: 'w1' } as LivestockEvent }
    ]);
    expect(herdCount(r, 'hd1')).toBe(11); // 10 + 2 - 1, milk doesn't change the count
  });
  it('lets any signed-in worker log events but not define a herd', () => {
    const reg = seedRegister();
    const ev = { op: 'upsert' as const, kind: 'livestockEvent' as const, item: { id: 'e5', herdId: 'hd1', kind: 'birth' as const, date: '2026-10-01', qty: 1, note: '', by: 'w1' } };
    expect(opAllowed('Field worker', ev, reg)).toBe(true);
    expect(opAllowed('Field worker', { op: 'upsert', kind: 'herd', item: herd }, reg)).toBe(false);
    expect(opAllowed('Group lead', { op: 'upsert', kind: 'herd', item: herd }, reg)).toBe(true);
  });
  it('validates the new kinds', () => {
    expect(opError({ op: 'upsert', kind: 'herd', item: { id: 'hd2', species: 'camel' as Herd['species'], ownerType: 'group', ownerId: 'g1', ownerName: 'Group 1' } })).toMatch(/species/);
    expect(opError({ op: 'upsert', kind: 'livestockEvent', item: { id: 'e6', herdId: '', kind: 'birth', date: '', qty: 0, note: '', by: '' } })).toMatch(/herd/);
    expect(opError({ op: 'upsert', kind: 'forestLog', item: { id: 'f1', product: 'honey', date: '2026-10-01', qty: 2, unit: 'kg', lat: null, lon: null, by: 'w1', note: '' } })).toBe('');
    expect(opError({ op: 'upsert', kind: 'forestLog', item: { id: 'f2', product: 'honey', date: '2026-10-01', qty: 0, unit: 'kg', lat: null, lon: null, by: 'w1', note: '' } })).toMatch(/quantity/);
    expect(opError({ op: 'upsert', kind: 'fishLog', item: { id: 'p1', species: 'tilapia', kind: 'catch', date: '2026-10-01', weightKg: 4, qty: null, processed: 'none', pond: '', by: 'w1', note: '' } })).toBe('');
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


import { fitModel, briefing, season, DEFAULT_MODEL } from '../src';
describe('fitting the flood model to measurements', () => {
  const now = new Date('2026-10-28T12:00:00Z'), here = { lat: 7.731, lon: 31.402 };
  const obs = (plot: string, daysAgo: number, cm: number | null, water = 'flooded', dLat = 0) => ({ at: new Date(now.getTime() - daysAgo * 864e5).toISOString(), plot, lat: here.lat + dLat, lon: here.lon, depthCm: cm, water });
  it('falls back to the design figures, labelled, when nothing is measured', () => {
    expect(fitModel([], [], here, now)).toEqual({ ...DEFAULT_MODEL, used: { plots: [], readings: 0, radiusKm: 2, gauge: false } });
  });
  it('uses repeat readings of a plot for the rate and brings depth forward to today', () => {
    const m = fitModel([obs('B‑07', 4, 60), obs('B‑07', 2, 54)], [], here, now);
    expect(m.rate).toBeCloseTo(0.03);
    expect(m.d0).toBeCloseTo(0.48);
    expect(m.measured).toBe(true);
    expect(m.rateSrc).toMatch(/repeat depth reading/);
  });
  it('uses the Bor gauge trend when there is only one depth reading', () => {
    const m = fitModel([obs('B‑07', 0, 40)], [{ at: new Date(now.getTime() - 4 * 864e5).toISOString(), v: 4.2 }, { at: now.toISOString(), v: 4.12 }], here, now);
    expect(m.rate).toBeCloseTo(0.02);
    expect(m.rateSrc).toMatch(/Bor gauge/);
    expect(m.d0).toBeCloseTo(0.4);
  });
  it('ignores plots far from the phone', () => {
    expect(fitModel([obs('X', 1, 80, 'flooded', 0.5)], [], here, now).measured).toBe(false);
  });
});

describe('home briefing', () => {
  const now = new Date('2026-10-28T08:00:00Z');
  const base = { now, name: 'Achol Deng', place: { lat: 7.731, lon: 31.402, payam: 'Duk Padiet' }, gauge: [], station: null, checks: [], weather: null };
  it('says plainly when there is no data', () => {
    const b = briefing(base);
    expect(b.headline).toMatch(/No field reports nearby yet/);
    expect(b.tiles.map(t => t.v)).toEqual(['—', '—', '—']);
    expect(b.kicker).toMatch(/Flood season, week \d+ · Duk Padiet/);
  });
  it('reports the gauge change and nearby wet plots', () => {
    const b = briefing({ ...base,
      gauge: [{ at: '2026-10-27T07:00:00Z', v: 4.15 }, { at: '2026-10-28T07:00:00Z', v: 4.12 }],
      checks: [{ at: '2026-10-27T09:00:00Z', plot: 'B‑07', lat: 7.731, lon: 31.402, water: 'flooded', depthCm: 25, around: 'surrounding', aroundDepthCm: 50, trend: 'falling' }],
      weather: { temp: 33.6, rain24: 0, sky: 'Sunny', at: '' }, satellite: { floodPct: 12.5, soil: 0.34, radiusKm: 2 } });
    expect(b.tiles[0]).toMatchObject({ v: '4.12 m', s: '↓ 3 cm since last' });
    expect(b.headline).toMatch(/The plots are draining/);
    expect(b.body.join(' ')).toMatch(/B‑07 25 cm/);
    expect(b.body.join(' ')).toMatch(/12.5% of the land within 2 km .* \(wet\)/);
    expect(b.tiles[2].v).toBe('34°');
  });
  it('knows the season', () => {
    expect(season(new Date('2026-03-10')).name).toBe('Dry season');
    expect(season(new Date('2026-12-20')).name).toBe('Recession');
  });
});

import { leadAlert, bulletinInputs } from '../src';
describe('lead SMS alerts', () => {
  const now = new Date('2026-10-28T08:00:00Z');
  const base = { reg: seedRegister(), bulletin: null, rainNext7: 11, days: 5, payam: 'Padiet', now };
  it('names the lead group plots with their latest check and warns when water rises', () => {
    const a = leadAlert({ ...base, lead: { id: 'L1', name: 'Achol Deng', rows: '' }, model: { d0: 0.6, rate: 0.015, d0Src: '', rateSrc: '', measured: true },
      checks: [{ at: '2026-10-27T09:00:00Z', plot: 'B‑07', water: 'flooded', depthCm: 40, around: 'edge', trend: 'rising' }, { at: '2026-10-20T09:00:00Z', plot: 'B‑07', water: 'none', depthCm: null, around: 'dry', trend: '' }] });
    expect(a.group).toBe('Group 4');
    expect(a.level).toBe('warn');
    expect(a.en).toContain('B-07 flooded 40cm rising');
    expect(a.en).toMatch(/^[\x00-\x7F]*$/);
  });
  it('forecasts mound rows topped when the basin is rising', () => {
    const a = leadAlert({ ...base, lead: { id: 'L2', name: 'Deng Bol', rows: '' }, checks: [], model: { d0: 0.8, rate: -0.02, d0Src: '', rateSrc: '', measured: true } });
    expect(a.en).toContain('RISING');
    expect(a.en).toContain('B-05');
    expect(a.level).toBe('warn');
  });
  it('carries the county bulletin alert', () => {
    const b = bulletinInputs({ alert_level: 'orange', alert_hazard: 'drought / dry spell', p_dry_spell_7d_in_15d: '0.46', week1_rain_median_mm: '10.9' });
    const a = leadAlert({ ...base, bulletin: b, rainNext7: null, lead: { id: 'L3', name: 'Kuol Arok', rows: '' }, checks: [], model: { d0: 0, rate: 0.02, d0Src: '', rateSrc: '', measured: true } });
    expect(a.en).toContain('County: ORANGE drought / dry spell');
    expect(a.en).toContain('Rain next 7d 11mm');
    expect(a.level).toBe('watch');
  });
});

describe('people register, store and roll-call', () => {
  const admin = { state: 'Jonglei', county: 'Duk', payam: 'Pagak', village: '' };
  const kin = { name: 'Nyadak', name2: 'Deng', relation: 'wife', phone: '0912345678', village: '' };
  const person = { ...blankPerson('p1', admin), name: 'Achol', name2: 'Deng', phone: '0912345678', kin: [kin, { ...kin, name: 'Kuol' }] };
  it('normalises South Sudan phone numbers', () => {
    expect(normPhone('0912 345 678')).toBe('+211912345678');
    expect(normPhone('211912345678')).toBe('+211912345678');
    expect(normPhone('+211 912-345-678')).toBe('+211912345678');
    expect(normPhone('12345')).toBe('');
  });
  it('asks for two names, a phone, the admin level and two next of kin', () => {
    expect(personError(person)).toBe('');
    expect(personError({ ...person, name2: '' })).toContain('second name');
    expect(personError({ ...person, admin: { ...admin, payam: '' } })).toContain('payam');
    expect(personError({ ...person, kin: [kin, { ...kin, phone: '' }] })).toContain('next of kin 2');
  });
  it('puts a product in the store as an incoming movement, creating the item once', () => {
    const reg = seedRegister();
    const a = productToStore(reg, { storeId: 'ST-01', name: 'Goat (live)', unit: 'head', qty: 3, by: 'u1', note: '', date: '2026-10-29' });
    expect(a.ops.map(o => (o as { kind: string }).kind)).toEqual(['item', 'move']);
    const reg2 = applyOps(reg, a.ops);
    const b = productToStore(reg2, { storeId: 'ST-01', name: 'Goat (live)', unit: 'head', qty: 2, by: 'u1', note: '', date: '2026-10-30' });
    expect(b.ops.map(o => (o as { kind: string }).kind)).toEqual(['move']);
  });
  it('counts a roll-call day only once', () => {
    const reg = seedRegister();
    const g = reg.groups[3], m = g.members[0];
    const op = { op: 'workdays' as const, groupId: g.id, memberIds: [m.id], date: '2026-10-29' };
    const once = applyOps(reg, [op]), twice = applyOps(once, [op]);
    expect(once.groups[3].members[0].workDays).toBe(m.workDays + 1);
    expect(twice.groups[3].members[0].workDays).toBe(m.workDays + 1);
  });
  it('gives zone depths from the model: ridge dry, slope 0.70 m shallower than the basin', () => {
    const z = zoneDepths({ d0: 0.92, rate: 0.025 });
    expect(z.ridge).toBe(0);
    expect(z.basin).toBeCloseTo(0.92);
    expect(z.slope).toBeCloseTo(0.22);
  });
});

import { autoTasks, listingLeft, salesTotal, zoneSummary, type Listing, type Offer, type Register } from '../src';

describe('register helpers for Home, tasks and the Market', () => {
  const day = (n: number) => new Date(Date.UTC(2026, 9, 30) - n * 864e5).toISOString();
  const now = new Date(Date.UTC(2026, 9, 30, 12));
  const listing: Listing = { id: 'ls1', name: 'Balanites oil', qty: 100, unit: 'L', price: 14, status: 'open', note: '', by: 'x', at: day(5) };
  const offer = (o: Partial<Offer>): Offer => ({ id: 'of', listingId: 'ls1', buyer: 'Nile Botanicals', phone: '', product: 'Balanites oil', qty: 40, unit: 'L', price: 13.5, status: 'open', pickup: '', note: '', by: 'x', at: '2026-10-20T08:00:00.000Z', ...o });

  it('counts plots, area and groups for a zone from the register', () => {
    const reg = seedRegister();
    const z = zoneSummary(reg, 'basin');
    expect(z.plots).toBe(reg.plots.filter(p => p.zone === 'basin').length);
    expect(z.ha).toBeCloseTo(reg.plots.filter(p => p.zone === 'basin').reduce((n, p) => n + (p.areaHa ?? 0), 0), 2);
  });
  it('adds automatic jobs only when nothing has been recorded lately', () => {
    const reg = seedRegister();
    const none = autoTasks({ now, plots: [], checks: [], gauge: [], depthMeasured: false }).map(t => t.id);
    expect(none).toEqual(['auto-gauge', 'auto-depth']);
    const fresh = autoTasks({ now, plots: [], checks: [], gauge: [{ at: day(1) }], depthMeasured: true });
    expect(fresh).toEqual([]);
    const p = reg.plots[0];
    const stale = autoTasks({ now, plots: [p], checks: [{ at: day(20), plot: p.code }], gauge: [{ at: day(1) }], depthMeasured: true });
    expect(stale.map(t => t.id)).toEqual([`auto-check-${p.id}`]);
    expect(autoTasks({ now, plots: [p], checks: [{ at: day(2), plot: p.code }], gauge: [{ at: day(1) }], depthMeasured: true })).toEqual([]);
  });
  it('takes accepted and delivered offers out of what is left, and totals them in dollars', () => {
    const reg: Register = { ...seedRegister(), listings: [listing], offers: [offer({ id: 'a', status: 'accepted', qty: 40 }), offer({ id: 'b', status: 'delivered', qty: 10, price: 14 }), offer({ id: 'c', status: 'open', qty: 30 }), offer({ id: 'd', status: 'declined', qty: 20 })] };
    expect(listingLeft(reg, listing)).toBe(50);
    expect(salesTotal(reg, 2026)).toEqual({ usd: 680, offers: 2 });
    expect(salesTotal(reg, 2025)).toEqual({ usd: 0, offers: 0 });
  });
  it('rejects incomplete tasks, mounds, listings and offers', () => {
    expect(opError({ op: 'upsert', kind: 'listing', item: { ...listing, qty: 0 } })).not.toBe('');
    expect(opError({ op: 'upsert', kind: 'listing', item: listing })).toBe('');
    expect(opError({ op: 'upsert', kind: 'offer', item: offer({ buyer: ' ' }) })).not.toBe('');
    expect(opError({ op: 'upsert', kind: 'offer', item: offer({ price: 0 }) })).not.toBe('');
    expect(opError({ op: 'upsert', kind: 'offer', item: offer({}) })).toBe('');
    expect(opError({ op: 'upsert', kind: 'mound', item: { id: 'B-01', crest: 4, note: '', surveyedAt: '2026-10-30', by: 'x' } })).not.toBe('');
    expect(opError({ op: 'upsert', kind: 'mound', item: { id: 'B-01', crest: 1.1, note: '', surveyedAt: '2026-10-30', by: 'x' } })).toBe('');
  });
});

import { normContact, pinMessage, signupError, weakPin } from '../src';

describe('self sign-up', () => {
  it('accepts a South Sudan or international WhatsApp number and tidies it', () => {
    expect(normContact('whatsapp', '0912 345 678')).toBe('+211912345678');
    expect(normContact('whatsapp', '+211 912-345-678')).toBe('+211912345678');
    expect(normContact('whatsapp', '00256 700 123 456')).toBe('+256700123456');
    expect(normContact('whatsapp', '12345')).toBe('');
    expect(normContact('whatsapp', 'abc')).toBe('');
  });
  it('accepts an email in any case and rejects the malformed', () => {
    expect(normContact('email', ' Nyibol@Example.org ')).toBe('nyibol@example.org');
    expect(normContact('email', 'nyibol@')).toBe('');
    expect(normContact('email', 'no spaces@x.org')).toBe('');
  });
  it('says what is missing from a request', () => {
    const ok = { name: 'Nyibol Garang', kind: 'email', contact: 'n@x.org' };
    expect(signupError(ok)).toBe('');
    expect(signupError({ ...ok, name: 'Nyibol' })).toContain('first and last name');
    expect(signupError({ ...ok, kind: 'sms' })).toContain('email or WhatsApp');
    expect(signupError({ ...ok, contact: 'x' })).toContain('email');
    expect(signupError({ ...ok, note: 'x'.repeat(201) })).toContain('note');
  });
  it('treats easy PINs as weak and others as fine', () => {
    for (const p of ['1111', '0000', '1234', '4321', '0123', '9876']) expect(weakPin(p)).toBe(true);
    for (const p of ['4821', '7305', '1357']) expect(weakPin(p)).toBe(false);
  });
  it('writes the message the admin sends', () => {
    const m = pinMessage({ name: 'Nyibol Garang', id: 'EW‑012', pin: '4821', url: 'https://x.test' });
    expect(m).toContain('Hello Nyibol');
    expect(m).toContain('EW‑012');
    expect(m).toContain('4821');
    expect(m).toContain('https://x.test');
    expect(pinMessage({ name: 'A B', id: 'EW‑001', pin: '4821', url: 'u', reset: true })).toContain('reset');
    expect(pinMessage({ name: 'A B', id: 'EW‑001', pin: '4821', url: 'u', reply: '+211917939818' })).toContain('WhatsApp +211917939818');
    expect(m).not.toContain('Questions');
  });
});
