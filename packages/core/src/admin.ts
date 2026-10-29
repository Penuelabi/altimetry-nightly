import { feature } from 'topojson-client';
import type { Topology, GeometryCollection } from 'topojson-specification';
import topo from '../data/ssd_payams.topo.json';

// Payam / county / state from GPS, offline. Boundaries: Penuelabi/South-Sudan-Admin-Geojson ssd_A3.json (517 payams).
export interface Place { payam: string; county: string; state: string; pcode: string }
type Props = { Payam_Name: string; ADM2_EN: string; ADM1_EN: string; Payam_MT_P: string };

export function inPolygon(lon: number, lat: number, rings: number[][][]) {
  let inside = false;
  for (const ring of rings) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

let index: { p: Place; polys: number[][][][]; box: [number, number, number, number] }[] | null = null;
function build() {
  const t = topo as unknown as Topology<{ ssd_A3: GeometryCollection<Props> }>;
  const fc = feature(t, t.objects.ssd_A3);
  // 138 of the 517 payams have no state or county in the boundary file. A payam code is SS + state (2) + county (2) + payam (2),
  // so a blank is filled with the most common name among payams sharing the same code prefix.
  const nameBy = (key: (p: Props) => string, name: (p: Props) => string) => {
    const counts = new Map<string, Map<string, number>>();
    for (const f of fc.features) {
      const pr = f.properties as Props, n = name(pr);
      if (!n) continue;
      const m = counts.get(key(pr)) ?? new Map<string, number>();
      m.set(n, (m.get(n) ?? 0) + 1);
      counts.set(key(pr), m);
    }
    return (k: string) => [...(counts.get(k) ?? new Map<string, number>()).entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '';
  };
  const stateByCode = nameBy(p => p.Payam_MT_P.slice(0, 4), p => p.ADM1_EN);
  const countyByCode = nameBy(p => p.Payam_MT_P.slice(0, 6), p => p.ADM2_EN);
  return fc.features.flatMap(f => {
    const g = f.geometry as { type: string; coordinates: unknown } | null;
    if (!g) return [];
    const polys = (g.type === 'MultiPolygon' ? g.coordinates : [g.coordinates]) as number[][][][];
    const xs = polys.flat(2).map(c => c[0]), ys = polys.flat(2).map(c => c[1]);
    const pr = f.properties as Props;
    const code = pr.Payam_MT_P;
    const county = pr.ADM2_EN || countyByCode(code.slice(0, 6)) || `Unnamed county (${code.slice(0, 6)})`;
    const state = pr.ADM1_EN || stateByCode(code.slice(0, 4)) || 'Unknown state';
    return [{ p: { payam: pr.Payam_Name, county, state, pcode: code }, polys, box: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] as [number, number, number, number] }];
  });
}

function entryAt(lat: number, lon: number) {
  index ??= build();
  for (const e of index) {
    const [x0, y0, x1, y1] = e.box;
    if (lon < x0 || lon > x1 || lat < y0 || lat > y1) continue;
    if (e.polys.some(poly => inPolygon(lon, lat, poly))) return e;
  }
  return null;
}

export function whereIs(lat: number, lon: number): Place | null {
  return entryAt(lat, lon)?.p ?? null;
}

// A payam with its boundary: polygons[i] is a list of rings (outer ring first, then holes) of [lon, lat].
export interface PayamArea extends Place { polygons: number[][][][]; areaKm2: number }

// Planar approximation around the polygon's own latitude; good to a few percent at payam size.
export function polygonAreaKm2(polys: number[][][][]): number {
  let total = 0;
  for (const poly of polys) {
    poly.forEach((ring, i) => {
      const lat0 = ring.reduce((n, p) => n + p[1], 0) / ring.length;
      const kx = 111.32 * Math.cos(lat0 * Math.PI / 180), ky = 110.57;
      let a = 0;
      for (let k = 0, j = ring.length - 1; k < ring.length; j = k++) a += (ring[j][0] * ring[k][1] - ring[k][0] * ring[j][1]);
      total += (i === 0 ? 1 : -1) * Math.abs(a) / 2 * kx * ky;
    });
  }
  return Math.round(total);
}

const toArea = (e: NonNullable<typeof index>[number]): PayamArea => ({ ...e.p, polygons: e.polys, areaKm2: polygonAreaKm2(e.polys) });

export function payamsIn(county: string, state?: string): PayamArea[] {
  index ??= build();
  return index.filter(e => e.p.county === county && (!state || e.p.state === state)).map(toArea);
}

// All payams, light (no boundaries), sorted by state, county, then name.
export function listPayams(): Place[] {
  index ??= build();
  return index.map(e => e.p).sort((a, b) => a.state.localeCompare(b.state) || a.county.localeCompare(b.county) || a.payam.localeCompare(b.payam));
}

// Cascading choices for forms: state → county → payam (names, sorted).
const uniq = (xs: string[]) => [...new Set(xs)].sort((a, b) => a.localeCompare(b));
export const statesList = () => uniq(listPayams().map(p => p.state));
export const countiesOf = (state: string) => uniq(listPayams().filter(p => p.state === state).map(p => p.county));
export const payamsOf = (state: string, county: string) => uniq(listPayams().filter(p => p.state === state && p.county === county).map(p => p.payam));

export function payamByCode(pcode: string): PayamArea | null {
  index ??= build();
  const e = index.find(x => x.p.pcode === pcode);
  return e ? toArea(e) : null;
}

export function payamAt(lat: number, lon: number): PayamArea | null {
  const e = entryAt(lat, lon);
  return e ? toArea(e) : null;
}
