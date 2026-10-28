export interface LatLon { lat: number; lon: number }

export function haversineKm(a: LatLon, b: LatLon) {
  const p = Math.PI / 180;
  const x = Math.sin((b.lat - a.lat) * p / 2) ** 2 + Math.cos(a.lat * p) * Math.cos(b.lat * p) * Math.sin((b.lon - a.lon) * p / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(x));
}

// Rows within radiusKm; if none, the `fallback` nearest rows, flagged so the UI can say so.
export function withinRadius<T extends LatLon>(rows: T[], at: LatLon, radiusKm: number, fallback = 3) {
  const ranked = rows.map(r => ({ row: r, km: haversineKm(at, r) })).sort((a, b) => a.km - b.km);
  const inside = ranked.filter(r => r.km <= radiusKm);
  return inside.length ? { rows: inside, fallback: false } : { rows: ranked.slice(0, fallback), fallback: true };
}

// Area of a walked boundary in hectares (equirectangular projection; fine at plot scale).
export function polygonHa(pts: LatLon[]) {
  if (pts.length < 3) return 0;
  const lat0 = pts[0].lat * Math.PI / 180, R = 6371000;
  const xy = pts.map(p => [p.lon * Math.PI / 180 * R * Math.cos(lat0), p.lat * Math.PI / 180 * R]);
  let s = 0;
  for (let i = 0; i < xy.length; i++) { const [x1, y1] = xy[i], [x2, y2] = xy[(i + 1) % xy.length]; s += x1 * y2 - x2 * y1; }
  return Math.abs(s) / 2 / 10000;
}

// Ray-casting point-in-polygon test.
export function pointInPolygon(pt: LatLon, poly: LatLon[]): boolean {
  if (poly.length < 3) return false;
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    if ((poly[i].lon > pt.lon) !== (poly[j].lon > pt.lon) &&
        pt.lat < (poly[j].lat - poly[i].lat) * (pt.lon - poly[i].lon) / (poly[j].lon - poly[i].lon) + poly[i].lat)
      inside = !inside;
  }
  return inside;
}

// Distance from a point to the centroid of a polygon, in km.
function centroidKm(pt: LatLon, poly: LatLon[]): number {
  if (!poly.length) return Infinity;
  const c: LatLon = { lat: poly.reduce((a, p) => a + p.lat, 0) / poly.length, lon: poly.reduce((a, p) => a + p.lon, 0) / poly.length };
  return haversineKm(pt, c);
}

export interface PlotMatch { id: string; code: string; inside: boolean; distKm: number }

// Find which plot a GPS point falls in. Returns the best match:
// 1. Inside a boundary → that plot (inside=true, distKm=0).
// 2. Not inside any, but within toleranceKm of a centroid → nearest (inside=false).
// 3. No mapped boundary within range → null.
export function plotForGps(pt: LatLon, plots: { id: string; code: string; boundary: LatLon[] }[], toleranceKm = 0.15): PlotMatch | null {
  for (const p of plots) {
    if (p.boundary.length > 2 && pointInPolygon(pt, p.boundary))
      return { id: p.id, code: p.code, inside: true, distKm: 0 };
  }
  const mapped = plots.filter(p => p.boundary.length > 2).map(p => ({ ...p, km: centroidKm(pt, p.boundary) })).sort((a, b) => a.km - b.km);
  if (mapped.length && mapped[0].km <= toleranceKm)
    return { id: mapped[0].id, code: mapped[0].code, inside: false, distKm: mapped[0].km };
  const pinned = plots.filter(p => p.boundary.length === 1).map(p => ({ ...p, km: haversineKm(pt, p.boundary[0]) })).sort((a, b) => a.km - b.km);
  if (pinned.length && pinned[0].km <= toleranceKm)
    return { id: pinned[0].id, code: pinned[0].code, inside: false, distKm: pinned[0].km };
  return null;
}
