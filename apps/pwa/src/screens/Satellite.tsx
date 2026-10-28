import { useState } from 'react';
import type { SatelliteIndices } from '@abuk/core';
import { api } from '../api';
import { usePlace } from '../net';
import { setState, useApp } from '../store';

const INDICES = [
  { key: 'ndvi' as const, label: 'NDVI', sub: 'Vegetation greenness', unit: '', src: 'Sentinel-2 via MODIS',
    ranges: [
      { max: 0.15, label: 'Bare / water', color: '#c03020' },
      { max: 0.25, label: 'Very sparse', color: '#c87830' },
      { max: 0.4, label: 'Sparse', color: '#b8a040' },
      { max: 0.6, label: 'Moderate', color: '#7ba840' },
      { max: 1, label: 'Dense', color: 'var(--color-accent)' },
    ] },
  { key: 'vci' as const, label: 'VCI', sub: 'Vegetation condition vs historical', unit: '%', src: 'MODIS 16-day',
    ranges: [
      { max: 10, label: 'Extreme drought', color: '#c03020' },
      { max: 20, label: 'Severe drought', color: '#c87830' },
      { max: 35, label: 'Moderate drought', color: '#b8a040' },
      { max: 50, label: 'Mild stress', color: '#7ba840' },
      { max: 100, label: 'No stress', color: 'var(--color-accent)' },
    ] },
  { key: 'spi' as const, label: 'SPI', sub: 'Rainfall anomaly (CHIRPS)', unit: '', src: 'CHIRPS daily',
    ranges: [
      { max: -1.5, label: 'Severe deficit', color: '#c03020' },
      { max: -1, label: 'Moderate deficit', color: '#c87830' },
      { max: 1, label: 'Near normal', color: 'var(--color-accent)' },
      { max: 1.5, label: 'Moderately wet', color: '#4080c0' },
      { max: 99, label: 'Very wet', color: '#2060a0' },
    ] },
  { key: 'spei' as const, label: 'SPEI', sub: 'Drought severity (precip + temp)', unit: '', src: 'TerraClimate PDSI',
    ranges: [
      { max: -3, label: 'Extreme drought', color: '#c03020' },
      { max: -2, label: 'Severe drought', color: '#c87830' },
      { max: -1, label: 'Moderate drought', color: '#b8a040' },
      { max: 1, label: 'Near normal', color: 'var(--color-accent)' },
      { max: 10, label: 'Wet', color: '#4080c0' },
    ] },
] as const;

function classify(key: string, v: number | null) {
  if (v === null) return { label: '—', color: 'var(--color-neutral-600)' };
  const idx = INDICES.find(i => i.key === key);
  if (!idx) return { label: '—', color: 'var(--color-neutral-600)' };
  for (const r of idx.ranges) if (v <= r.max) return r;
  return idx.ranges[idx.ranges.length - 1];
}

function fmtVal(key: string, v: number | null, unit: string) {
  if (v === null) return '—';
  if (key === 'vci') return `${v}${unit}`;
  return `${v > 0 && key !== 'ndvi' ? '+' : ''}${v}`;
}

export function Satellite() {
  const s = useApp();
  const place = usePlace();
  const sat = s.satIndices;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const refresh = async () => {
    if (!s.session || s.session.demo) return setErr('Sign in to fetch live satellite data.');
    setBusy(true); setErr('');
    try {
      const r = await api<SatelliteIndices>(`/api/sources/satellite?lat=${place.lat}&lon=${place.lon}&radius=20`);
      setState({ satIndices: r });
      if (r.errors.length) setErr(r.errors.join('; '));
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>
        Live satellite indices from Google Earth Engine for the area around registered plots.
        NDVI and VCI from Sentinel-2 / MODIS; SPI from CHIRPS rainfall; SPEI from TerraClimate.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {INDICES.map(idx => {
          const v = sat?.[idx.key] ?? null;
          const cls = classify(idx.key, v);
          return (
            <div key={idx.key} className="box" style={{ padding: '14px 12px', position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: cls.color }} />
              <div className="kick sm" style={{ letterSpacing: '.12em', marginBottom: 2 }}>{idx.label}</div>
              <div className="head num" style={{ fontSize: 28, color: cls.color }}>{fmtVal(idx.key, v, idx.unit)}</div>
              <div style={{ fontSize: 12, color: cls.color, fontWeight: 600, marginBottom: 4 }}>{cls.label}</div>
              <div className="sub" style={{ fontSize: 11 }}>{idx.sub}</div>
            </div>
          );
        })}
      </div>

      {sat?.precipMm != null && (
        <div className="box" style={{ padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 13 }}>30-day rainfall</span>
          <span className="head num" style={{ fontSize: 20 }}>{sat.precipMm} mm</span>
        </div>
      )}

      {sat?.asOf && (
        <div className="sub" style={{ textAlign: 'center' }}>
          Data as of {sat.asOf} · {place.payam}, {place.county}
        </div>
      )}

      {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}

      <button className="btn lg" onClick={refresh} disabled={busy}>
        {busy ? 'Fetching from GEE…' : sat ? 'Refresh indices' : 'Fetch satellite data'}
      </button>

      <div className="col g6" style={{ marginTop: 4 }}>
        <div className="section">About these indices</div>
        <div className="sub" style={{ lineHeight: 1.5 }}>
          <strong>NDVI</strong> measures vegetation greenness from satellite imagery. Values above 0.4 indicate healthy crop cover.<br />
          <strong>VCI</strong> compares current vegetation to the historical range for this time of year. Below 35% signals drought stress.<br />
          <strong>SPI</strong> standardises recent rainfall against historical norms. Below -1 indicates significant rainfall deficit.<br />
          <strong>SPEI</strong> combines precipitation and temperature effects. Below -1 indicates drought conditions accounting for evapotranspiration.
        </div>
        <div className="sub" style={{ fontSize: 11, fontStyle: 'italic' }}>
          Requires GEE_PROJECT and GOOGLE_SERVICE_ACCOUNT_JSON in server environment. Indices are cached for 6 hours per location.
        </div>
      </div>
    </div>
  );
}
