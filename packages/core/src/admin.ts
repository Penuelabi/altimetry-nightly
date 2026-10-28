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
  return fc.features.flatMap(f => {
    const g = f.geometry as { type: string; coordinates: unknown } | null;
    if (!g) return [];
    const polys = (g.type === 'MultiPolygon' ? g.coordinates : [g.coordinates]) as number[][][][];
    const xs = polys.flat(2).map(c => c[0]), ys = polys.flat(2).map(c => c[1]);
    const pr = f.properties as Props;
    return [{ p: { payam: pr.Payam_Name, county: pr.ADM2_EN, state: pr.ADM1_EN, pcode: pr.Payam_MT_P }, polys, box: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] as [number, number, number, number] }];
  });
}

export function whereIs(lat: number, lon: number): Place | null {
  index ??= build();
  for (const e of index) {
    const [x0, y0, x1, y1] = e.box;
    if (lon < x0 || lon > x1 || lat < y0 || lat > y1) continue;
    if (e.polys.some(poly => inPolygon(lon, lat, poly))) return e.p;
  }
  return null;
}
