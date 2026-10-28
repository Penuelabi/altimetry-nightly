import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Plot } from '@abuk/core';

export interface CheckPoint { lat: number; lon: number; label: string; text: string; flag: boolean }
const ACCENT = '#a06f24';
const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!));

// Satellite base with plot outlines and crop-check points; fits whatever is present.
export function DashMap({ plots, points }: { plots: Plot[]; points: CheckPoint[] }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  useEffect(() => {
    const m = L.map(el.current!).setView([7.731, 31.402], 13);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Imagery © Esri, Maxar, Earthstar' }).addTo(m);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 }).addTo(m);
    layer.current = L.layerGroup().addTo(m); map.current = m;
    return () => { m.remove(); };
  }, []);
  useEffect(() => {
    const m = map.current, g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    const bounds: L.LatLngTuple[] = [];
    for (const p of plots) {
      if (p.boundary.length > 2) {
        const pts = p.boundary.map(q => [q.lat, q.lon] as L.LatLngTuple); bounds.push(...pts);
        L.polygon(pts, { color: '#fff', weight: 1.5, fillOpacity: 0.1 }).addTo(g).bindTooltip(`${esc(p.code)} · ${esc(p.crop)}`);
      } else if (p.boundary[0]) bounds.push([p.boundary[0].lat, p.boundary[0].lon]);
    }
    for (const c of points) {
      bounds.push([c.lat, c.lon]);
      L.circleMarker([c.lat, c.lon], { radius: c.flag ? 7 : 5, color: c.flag ? '#fff' : ACCENT, weight: c.flag ? 3 : 2, fillColor: ACCENT, fillOpacity: 1 })
        .addTo(g).bindPopup(`<strong>${esc(c.label)}</strong><br>${esc(c.text)}${c.flag ? '<br>⚠ needs attention' : ''}`);
    }
    if (bounds.length) m.fitBounds(bounds, { padding: [20, 20], maxZoom: 17 });
  }, [plots, points]);
  return <div ref={el} style={{ height: 380, borderRadius: 'var(--radius-md)', background: 'var(--color-neutral-300)' }} />;
}
