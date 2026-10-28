import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export interface LatLon { lat: number; lon: number }

// Satellite basemap (Esri World Imagery, no key needed) with place labels on top.
// Without signal the tiles stay blank but GPS, the buffer and plots still draw.
const IMAGERY = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const LABELS = 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}';
const ACCENT = '#b68235';

// onTap: when given, tapping the map reports the point (used to draw a plot boundary by hand).
export function LiveMap({ here, gps, acc, bufferM = 150, plots, track, closed, height = 330, onTap }: {
  here: LatLon; gps: boolean; acc: number | null; bufferM?: number; plots: LatLon[][]; track: LatLon[]; closed: boolean; height?: number; onTap?: (p: LatLon) => void;
}) {
  const tap = useRef(onTap);
  tap.current = onTap;
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layers = useRef<L.LayerGroup | null>(null);
  const fitted = useRef<'none' | 'farm' | 'gps'>('none');

  useEffect(() => {
    const m = L.map(el.current!, { zoomControl: true, attributionControl: true }).setView([here.lat, here.lon], 17);
    L.tileLayer(IMAGERY, { maxZoom: 19, attribution: 'Imagery © Esri, Maxar, Earthstar' }).addTo(m);
    L.tileLayer(LABELS, { maxZoom: 19 }).addTo(m);
    layers.current = L.layerGroup().addTo(m);
    m.on('click', e => tap.current?.({ lat: e.latlng.lat, lon: e.latlng.lng }));
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const m = map.current, g = layers.current;
    if (!m || !g) return;
    g.clearLayers();
    const c: L.LatLngExpression = [here.lat, here.lon];
    const buffer = L.circle(c, { radius: bufferM, color: ACCENT, weight: 2, fillColor: ACCENT, fillOpacity: 0.12, dashArray: '6 4' }).addTo(g);
    if (acc) L.circle(c, { radius: acc, stroke: false, fillColor: '#4a90d9', fillOpacity: 0.2 }).addTo(g);
    L.circleMarker(c, { radius: 7, color: '#fff', weight: 2, fillColor: '#4a90d9', fillOpacity: 1 }).addTo(g).bindTooltip('You are here');
    for (const p of plots) {
      if (p.length > 1) L.polygon(p.map(q => [q.lat, q.lon] as L.LatLngTuple), { color: '#fff', weight: 1.5, dashArray: '3 3', fillOpacity: 0.08 }).addTo(g);
      else if (p[0]) L.circleMarker([p[0].lat, p[0].lon], { radius: 4, color: '#fff', fillColor: ACCENT, fillOpacity: 1 }).addTo(g);
    }
    if (track.length) {
      const pts = track.map(q => [q.lat, q.lon] as L.LatLngTuple);
      (closed && pts.length > 2 ? L.polygon(pts, { color: ACCENT, weight: 2.5, fillOpacity: 0.2 }) : L.polyline(pts, { color: ACCENT, weight: 2.5 })).addTo(g);
      pts.forEach(p => L.circleMarker(p, { radius: 3, color: ACCENT, fillColor: ACCENT, fillOpacity: 1 }).addTo(g));
    }
    // Fit the 150 m buffer once, and again when the first real GPS fix replaces the farm point;
    // after that the worker controls the zoom.
    const want = gps ? 'gps' : 'farm';
    if (fitted.current !== want && fitted.current !== 'gps') { m.fitBounds(buffer.getBounds(), { padding: [12, 12] }); fitted.current = want; }
  }, [here.lat, here.lon, gps, acc, bufferM, plots, track, closed]);

  return <div ref={el} style={{ height, width: '100%', background: 'var(--color-neutral-300)' }} />;
}
