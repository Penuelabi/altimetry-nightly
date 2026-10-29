// Satellite indices per payam: every value is the mean over all pixels inside the payam's boundary.
import { payamAt, payamByCode, type PayamArea, type SatelliteIndices } from '@abuk/core';
import { need } from './config';
import { arr, c, eeCompute, fn, loadImage, meanOver, polygonGeometry, type Node } from './adapters/google';

const CLIM_FROM = 1991, CLIM_TO = 2020; // WMO standard normal period
const SD_FLOOR_MM = 5; // keeps dry-season z-scores finite when a month's rainfall barely varies
const Z_LIMIT = 3;

const collection = (id: string) => fn('ImageCollection.load', { id: c(id) });
const calendar = (coll: Node, field: 'year' | 'month', from: number, to = from) =>
  fn('Collection.filter', { collection: coll, filter: fn('Filter.calendarRange', { start: c(from), end: c(to), field: c(field) }) });
const latest = (coll: Node, n: number) => fn('Collection.limit', { collection: coll, limit: c(n), key: c('system:time_start'), ascending: c(false) });
const reduce = (coll: Node, reducer: string) => fn('ImageCollection.reduce', { collection: coll, reducer: fn(reducer, {}) });
const select = (input: Node, ...bands: string[]) => fn('Image.select', { input, bandSelectors: c(bands) });
const rename = (input: Node, name: string) => fn('Image.rename', { input, names: c([name]) });
const constant = (value: number) => fn('Image.constant', { value: c(value) });
const op = (name: 'subtract' | 'multiply' | 'divide' | 'max', a: Node, b: Node) => fn(`Image.${name}`, { image1: a, image2: b });

const chirps = () => collection('UCSB-CHG/CHIRPS/DAILY');
const terra = () => collection('IDAHO_EPSCOR/TERRACLIMATE');

const rainLast30 = () => rename(reduce(latest(chirps(), 30), 'Reducer.sum'), 'v');
const rainOf = (year: number, month: number) => rename(reduce(calendar(calendar(chirps(), 'year', year), 'month', month), 'Reducer.sum'), 'v');
// TerraClimate pet is stored in tenths of a millimetre per month.
const petOf = (year: number, to: number, month: number) =>
  rename(op('multiply', select(reduce(calendar(calendar(terra(), 'year', year, to), 'month', month), 'Reducer.mean'), 'pet_mean'), constant(0.1)), 'v');

const years = () => Array.from({ length: CLIM_TO - CLIM_FROM + 1 }, (_, i) => CLIM_FROM + i);

// (value now - mean of the 30 years) / standard deviation of the 30 years, pixel by pixel.
function zScore(history: Node[], now: Node, name: string): Node {
  const coll = fn('ImageCollection.fromImages', { images: arr(history) });
  const mean = rename(reduce(coll, 'Reducer.mean'), 'v');
  const sd = op('max', rename(reduce(coll, 'Reducer.sampleStdDev'), 'v'), constant(SD_FLOOR_MM));
  return rename(op('divide', op('subtract', now, mean), sd), name);
}

const spiExpr = (month: number) => zScore(years().map(y => rainOf(y, month)), rainLast30(), 'spi');
// SPEI: rainfall minus evaporation. The current month's evaporation is its 1991-2020 average, because
// TerraClimate publishes months late; years in the history use their own evaporation.
const speiExpr = (month: number) => zScore(
  years().map(y => op('subtract', rainOf(y, month), petOf(y, y, month))),
  op('subtract', rainLast30(), petOf(CLIM_FROM, CLIM_TO, month)),
  'spei'
);

const num = (r: Record<string, number | null>, key: string) => (typeof r[key] === 'number' ? r[key] as number : null);
const round = (v: number, places: number) => Math.round(v * 10 ** places) / 10 ** places;
const clampZ = (v: number | null) => (v === null ? null : round(Math.max(-Z_LIMIT, Math.min(Z_LIMIT, v)), 2));

async function compute(area: PayamArea): Promise<SatelliteIndices> {
  const errors: string[] = [];
  const asOf = new Date().toISOString().slice(0, 10);
  const head = { payam: area.payam, county: area.county, pcode: area.pcode, areaKm2: area.areaKm2, asOf };
  try { need('gee'); } catch (e) { return { ...head, ndvi: null, vci: null, spi: null, spei: null, precipMm: null, errors: [(e as Error).message] }; }

  const geometry = polygonGeometry(area.polygons);
  const over = (expr: Node, scale: number) => eeCompute(meanOver(expr, geometry, scale));
  const guard = async <T>(label: string, f: () => Promise<T>, fallback: T): Promise<T> => {
    try { return await f(); } catch (e) { errors.push(`${label}: ${(e as Error).message}`); return fallback; }
  };
  // The 30 days of rain ending at the latest CHIRPS image, which lags a few days; its calendar month picks the climatology.
  const month = new Date(Date.now() - 15 * 86400_000).getUTCMonth() + 1;

  const [ndviRaw, hist, precipMm, spi, spei] = await Promise.all([
    guard('NDVI', async () => num(await over(select(loadImage('ic:MODIS/061/MOD13A2'), 'NDVI'), 1000), 'NDVI'), null as number | null),
    guard('VCI', async () => {
      const range = reduce(calendar(collection('MODIS/061/MOD13A2'), 'month', month), 'Reducer.minMax');
      const r = await over(select(range, 'NDVI_min', 'NDVI_max'), 1000);
      return { min: num(r, 'NDVI_min'), max: num(r, 'NDVI_max') };
    }, { min: null as number | null, max: null as number | null }),
    guard('Rain', async () => { const v = num(await over(rainLast30(), 5566), 'v'); return v === null ? null : round(v, 1); }, null as number | null),
    guard('SPI', async () => clampZ(num(await over(spiExpr(month), 5566), 'spi')), null as number | null),
    guard('SPEI', async () => clampZ(num(await over(speiExpr(month), 5566), 'spei')), null as number | null)
  ]);

  const ndvi = ndviRaw === null ? null : round(ndviRaw * 0.0001, 3);
  const vci = ndviRaw !== null && hist.min !== null && hist.max !== null && hist.max > hist.min
    ? Math.max(0, Math.min(100, Math.round((ndviRaw - hist.min) / (hist.max - hist.min) * 100))) : null;
  return { ...head, ndvi, vci, spi, spei, precipMm, errors };
}

const HOURS_6 = 6 * 3600_000;
const cache = new Map<string, { at: number; v: SatelliteIndices }>();
const inflight = new Map<string, Promise<SatelliteIndices>>();

export function satelliteForPayam(area: PayamArea): Promise<SatelliteIndices> {
  const hit = cache.get(area.pcode);
  if (hit && Date.now() - hit.at < HOURS_6) return Promise.resolve(hit.v);
  const running = inflight.get(area.pcode);
  if (running) return running;
  const p = compute(area).then(v => { if (!v.errors.length) cache.set(area.pcode, { at: Date.now(), v }); return v; }).finally(() => inflight.delete(area.pcode));
  inflight.set(area.pcode, p);
  return p;
}

// A payam code, or the point a phone is at (any payam in South Sudan).
export function resolvePayam(q: { pcode?: string; lat?: number; lon?: number }): PayamArea | null {
  if (q.pcode) return payamByCode(q.pcode);
  return q.lat !== undefined && q.lon !== undefined ? payamAt(q.lat, q.lon) : null;
}
