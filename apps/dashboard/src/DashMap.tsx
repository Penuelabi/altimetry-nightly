import { useEffect, useImperativeHandle, useRef, forwardRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Plot } from '@abuk/core';

export interface CheckPoint { lat: number; lon: number; label: string; text: string; flag: boolean }
export interface DashMapHandle { focusPlot: (plotId: string) => void }
const ACCENT = '#a06f24';
const HIGHLIGHT = '#e8c840';
const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!));

export const DashMap = forwardRef<DashMapHandle, { plots: Plot[]; points: CheckPoint[] }>(function DashMap({ plots, points }, ref) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const polygons = useRef<Map<string, L.Polygon>>(new Map());
  const highlight = useRef<L.Polygon | null>(null);

  useImperativeHandle(ref, () => ({
    focusPlot(plotId: string) {
      const m = map.current;
      const poly = polygons.current.get(plotId);
      if (highlight.current) { highlight.current.setStyle({ color: '#fff', weight: 1.5 }); highlight.current = null; }
      if (!m) return;
      const p = plots.find(p => p.id === plotId);
      if (poly) {
        poly.setStyle({ color: HIGHLIGHT, weight: 3 });
        highlight.current = poly;
        m.fitBounds(poly.getBounds(), { padding: [40, 40], maxZoom: 17 });
        poly.openTooltip();
      } else if (p?.boundary[0]) {
        m.setView([p.boundary[0].lat, p.boundary[0].lon], 16);
      }
    }
  }));

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
    polygons.current.clear();
    highlight.current = null;
    const bounds: L.LatLngTuple[] = [];
    for (const p of plots) {
      if (p.boundary.length > 2) {
        const pts = p.boundary.map(q => [q.lat, q.lon] as L.LatLngTuple); bounds.push(...pts);
        const poly = L.polygon(pts, { color: '#fff', weight: 1.5, fillOpacity: 0.1 }).addTo(g).bindTooltip(`${esc(p.code)} · ${esc(p.crop)}`);
        polygons.current.set(p.id, poly);
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
});
