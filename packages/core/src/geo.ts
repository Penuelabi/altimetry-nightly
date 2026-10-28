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
