import { useEffect, useMemo, useState } from 'react';
import { payamAt, type SatelliteIndices } from '@abuk/core';
import { api } from '../api';
import { usePlace } from '../net';
import { setState, useApp } from '../store';

const Z_BANDS = (dry: string, wet: string) => [
  { max: -2, label: `Extreme ${dry}`, color: '#a02018' },
  { max: -1.5, label: `Severe ${dry}`, color: '#c03020' },
  { max: -1, label: `Moderate ${dry}`, color: '#c87830' },
  { max: 1, label: 'Near normal', color: 'var(--color-accent)' },
  { max: 1.5, label: 'Moderately wet', color: '#4080c0' },
  { max: 2, label: 'Very wet', color: '#2060a0' },
  { max: 99, label: `Extremely ${wet}`, color: '#104880' },
];

const INDICES = [
  { key: 'ndvi' as const, label: 'NDVI', sub: 'Vegetation greenness (MODIS)', unit: '',
    ranges: [
      { max: 0.15, label: 'Bare / water', color: '#c03020' },
      { max: 0.25, label: 'Very sparse', color: '#c87830' },
      { max: 0.4, label: 'Sparse', color: '#b8a040' },
      { max: 0.6, label: 'Moderate', color: '#7ba840' },
      { max: 1, label: 'Dense', color: 'var(--color-accent)' },
    ] },
  { key: 'vci' as const, label: 'VCI', sub: 'Vegetation condition vs same month, 2000 on', unit: '%',
    ranges: [
      { max: 10, label: 'Extreme drought', color: '#c03020' },
      { max: 20, label: 'Severe drought', color: '#c87830' },
      { max: 35, label: 'Moderate drought', color: '#b8a040' },
      { max: 50, label: 'Mild stress', color: '#7ba840' },
      { max: 100, label: 'No stress', color: 'var(--color-accent)' },
    ] },
  { key: 'spi' as const, label: 'SPI', sub: 'Rainfall vs 1991–2020 (CHIRPS)', unit: '', ranges: Z_BANDS('deficit', 'wet') },
  { key: 'spei' as const, label: 'SPEI', sub: 'Rain minus evaporation vs 1991–2020', unit: '', ranges: Z_BANDS('drought', 'wet') },
] as const;

type Band = { max: number; label: string; color: string };

function classify(key: string, v: number | null): Band {
  const none = { max: 0, label: '—', color: 'var(--color-neutral-600)' };
  if (v === null) return none;
  const idx = INDICES.find(i => i.key === key);
  if (!idx) return none;
  const ranges = idx.ranges as readonly Band[];
  return ranges.find(r => v <= r.max) ?? ranges[ranges.length - 1];
}

function fmtVal(key: string, v: number | null, unit: string) {
  if (v === null) return '—';
  if (key === 'vci') return `${v}${unit}`;
  return `${v > 0 && key !== 'ndvi' ? '+' : ''}${v}`;
}

export function Satellite() {
  const s = useApp();
  const place = usePlace();
  const area = useMemo(() => payamAt(place.lat, place.lon), [place.lat, place.lon]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const today = new Date().toISOString().slice(0, 10);
  const mine = s.satIndices && area && s.satIndices.pcode === area.pcode ? s.satIndices : null;

  const refresh = async () => {
    if (!area) return setErr('Your GPS position is outside the payam boundaries, so there is nothing to average over.');
    if (!s.session || s.session.demo) return setErr('Sign in to fetch live satellite data.');
    setBusy(true); setErr('');
    try {
      const r = await api<SatelliteIndices>(`/api/sources/satellite?pcode=${area.pcode}`);
      setState({ satIndices: r });
      if (r.errors.length) setErr(r.errors.join('; '));
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  // Fetch on opening, and again when the phone moves into another payam or the stored values are from an earlier day.
  useEffect(() => {
    if (area && s.session && !s.session.demo && (!mine || mine.asOf !== today)) void refresh();
  }, [area?.pcode, !!s.session]);

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <div className="box" style={{ padding: '10px 14px' }}>
        <div className="kick sm">Payam at your GPS position</div>
        <div className="head" style={{ fontSize: 22 }}>{area ? area.payam : 'Outside the boundaries'}</div>
        <div className="sub">{area ? `${area.county} county, ${area.state} · ${area.areaKm2.toLocaleString('en')} km²` : 'Move into a South Sudan payam to see values.'}</div>
      </div>

      <p className="body" style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>
        Every value below is the average over all satellite pixels inside this payam, from Google Earth Engine.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {INDICES.map(idx => {
          const v = mine?.[idx.key] ?? null;
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

      {mine?.precipMm != null && (
        <div className="box" style={{ padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 13 }}>Rain, last 30 days available</span>
          <span className="head num" style={{ fontSize: 20 }}>{mine.precipMm} mm</span>
        </div>
      )}

      {mine && <div className="sub" style={{ textAlign: 'center' }}>Data as of {mine.asOf} · {mine.payam} payam</div>}
      {!mine && s.satIndices && area && <div className="sub" style={{ textAlign: 'center' }}>Showing nothing for {area.payam} yet; the last fetch was for {s.satIndices.payam}.</div>}

      {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}

      <button className="btn lg" onClick={refresh} disabled={busy || !area}>
        {busy ? 'Fetching from Earth Engine…' : mine ? 'Refresh indices' : 'Fetch satellite data'}
      </button>

      <div className="col g6" style={{ marginTop: 4 }}>
        <div className="section">About these indices</div>
        <div className="sub" style={{ lineHeight: 1.5 }}>
          <strong>NDVI</strong> measures vegetation greenness. Above 0.4 means healthy crop cover.<br />
          <strong>VCI</strong> compares greenness now with the lowest and highest ever seen in this payam in this month since 2000. Below 35% signals drought stress.<br />
          <strong>SPI</strong> is how far the last 30 days of rain are above or below the 1991–2020 average for this time of year, in standard deviations. Below −1 is a significant deficit.<br />
          <strong>SPEI</strong> is the same for rain minus evaporation, which also counts hot, dry air. Below −1 means drought conditions.
        </div>
        <div className="sub" style={{ fontSize: 11, fontStyle: 'italic' }}>
          SPI and SPEI are standardised anomalies (z-scores), limited to −3 to +3. Rainfall data lags a few days; the current month's evaporation is its 1991–2020 average because that data is published months late. Values are kept 6 hours per payam.
        </div>
      </div>
    </div>
  );
}
