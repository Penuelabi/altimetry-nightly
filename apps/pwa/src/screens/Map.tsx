import { useEffect, useRef, useState } from 'react';
import { basinDepth, editAllowed, haversineKm, newId, polygonHa, whereIs, zoneDepths, type Plot as FarmPlot, type Terrain, type Zone } from '@abuk/core';
import { useModel } from './common';
import { farmChange, go, record, setState, useApp, type Plot } from '../store';
import { api, explain } from '../api';
import { useOnline, usePlace } from '../net';
import { LiveMap } from '../LiveMap';
import { Field, Icon, Seg } from '../ui';

interface Pt { lat: number; lon: number; acc: number; alt: number | null }
interface Capture { mode: 'walk' | 'pin'; pts: Pt[]; done: boolean; err: string }

export function MapScreen() {
  const s = useApp(), online = useOnline(), place = usePlace();
  const [cap, setCap] = useState<Capture | null>(null);
  const [terrain, setTerrain] = useState<Terrain | null>(null);
  const [terrErr, setTerrErr] = useState('');
  const watch = useRef<number | null>(null);
  // The basin depth the flood model holds today: from depth readings near the phone when there are any.
  const model = useModel(), depth = basinDepth(0, model);
  const depthSrc = model.measured ? model.d0Src : 'design example, not measured';

  const stop = () => { if (watch.current !== null) navigator.geolocation.clearWatch(watch.current); watch.current = null; };
  useEffect(() => stop, []);

  // Follow the phone while the map is open (the app-wide check runs only every 2 minutes).
  useEffect(() => {
    if (!('geolocation' in navigator)) return;
    const id = navigator.geolocation.watchPosition(p => {
      const { latitude: lat, longitude: lon, accuracy } = p.coords, w = whereIs(lat, lon);
      setState({ where: { lat, lon, acc: accuracy, payam: w?.payam ?? 'Outside South Sudan', county: w?.county ?? '', state: w?.state ?? '', at: new Date().toISOString() } });
    }, () => {}, { enableHighAccuracy: true, maximumAge: 5000 });
    return () => navigator.geolocation.clearWatch(id);
  }, []);

  const start = (mode: 'walk' | 'pin') => {
    stop(); setTerrain(null); setTerrErr('');
    if (!('geolocation' in navigator)) return setCap({ mode, pts: [], done: false, err: 'This phone has no GPS access in the browser.' });
    setCap({ mode, pts: [], done: false, err: '' });
    const t0 = Date.now();
    watch.current = navigator.geolocation.watchPosition(p => {
      const pt: Pt = { lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy, alt: p.coords.altitude };
      setCap(c => {
        if (!c || c.done) return c;
        // Walking: keep a vertex every 3 m. Pin: average fixes for 8 s.
        if (c.mode === 'walk') {
          const last = c.pts[c.pts.length - 1];
          return !last || haversineKm(last, pt) * 1000 >= 3 ? { ...c, pts: [...c.pts, pt] } : c;
        }
        const pts = [...c.pts, pt];
        if (Date.now() - t0 > 8000 && pts.length >= 3) { stop(); return { ...c, pts, done: true }; }
        return { ...c, pts };
      });
    }, e => setCap(c => c && { ...c, err: e.code === 1 ? 'Location permission is off. Allow it in the browser settings.' : 'Waiting for a GPS fix…' }),
    { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 });
  };

  const finish = () => { stop(); setCap(c => c && { ...c, done: c.pts.length >= 3 || c.mode === 'pin', err: c.pts.length < 3 && c.mode === 'walk' ? 'Walk at least three corners first.' : '' }); };

  const centre = cap?.pts.length ? { lat: cap.pts.reduce((a, p) => a + p.lat, 0) / cap.pts.length, lon: cap.pts.reduce((a, p) => a + p.lon, 0) / cap.pts.length } : null;
  const acc = cap?.pts.length ? Math.min(...cap.pts.map(p => p.acc)) : null;
  const gpsAlt = cap?.pts.find(p => p.alt !== null)?.alt ?? null;

  useEffect(() => {
    if (!cap?.done || !centre || !online || terrain) return;
    api<Terrain>(`/api/terrain?lat=${centre.lat}&lon=${centre.lon}`).then(setTerrain, e => setTerrErr(explain(e)));
  }, [cap?.done, online]); // eslint-disable-line react-hooks/exhaustive-deps

  // Where the capture goes: an existing plot in the farm register, or a new one.
  const canEdit = editAllowed(s.session?.user.role ?? '');
  const [target, setTarget] = useState('new');
  const [np, setNp] = useState({ code: '', zone: 'basin' as Zone, crop: s.farm.crops[0]?.name ?? '', groupId: '' });
  const [saveErr, setSaveErr] = useState('');
  const [savedMsg, setSavedMsg] = useState('');

  const save = () => {
    if (!cap || !centre) return;
    const pts = cap.mode === 'walk' ? cap.pts.map(({ lat, lon }) => ({ lat, lon })) : [centre];
    const ha = cap.mode === 'walk' ? Math.round(polygonHa(cap.pts) * 100) / 100 : null;
    const capture: Plot = { id: `P‑${Date.now().toString(36)}`, mode: cap.mode, pts, ha: ha ?? 0, elevation: terrain?.elevation ?? gpsAlt, slopePct: terrain?.slopePct ?? null, at: new Date().toISOString() };
    let code = '';
    if (canEdit) {
      if (target === 'new') {
        if (!np.code.trim()) return setSaveErr('Give the new plot a code, e.g. B‑13.');
        if (s.farm.plots.some(p => p.code.toLowerCase() === np.code.trim().toLowerCase())) return setSaveErr('A plot with that code exists; pick it under "Save to".');
        const plot: FarmPlot = { id: newId('plot'), code: np.code.trim(), zone: np.zone, crop: np.crop, groupId: np.groupId, holder: '', areaHa: ha, boundary: pts, notes: '' };
        farmChange({ op: 'upsert', kind: 'plot', item: plot }); code = plot.code;
      } else {
        const old = s.farm.plots.find(p => p.id === target)!;
        farmChange({ op: 'upsert', kind: 'plot', item: { ...old, boundary: pts, areaHa: ha ?? old.areaHa } }); code = old.code;
      }
    }
    // The raw capture is also recorded, so extension workers' mapping reaches the office too.
    setState(st => ({ plots: [...st.plots, capture] }));
    record('plot', { ...capture, plot: code || null });
    setSavedMsg(code ? `Saved to plot ${code}.` : 'Saved. An admin or group lead will attach it to a plot.');
    setCap(null); setSaveErr(''); setNp({ ...np, code: '' }); setTarget('new');
  };

  const readouts = cap && centre ? [
    { k: 'Latitude', v: centre.lat.toFixed(5) + '° N', src: 'phone GPS' },
    { k: 'Longitude', v: centre.lon.toFixed(5) + '° E', src: 'phone GPS' },
    { k: 'Elevation', v: terrain?.elevation != null ? `${terrain.elevation} m` : gpsAlt != null ? `${Math.round(gpsAlt)} m (GPS)` : '—', src: terrain ? 'terrain model' : terrErr ? 'terrain model unavailable' : 'refines when online' },
    { k: 'Slope', v: terrain?.slopePct != null ? `${terrain.slopePct} %` : '—', src: terrain ? 'terrain model' : 'needs connection' },
    cap.mode === 'walk' ? { k: 'Area', v: polygonHa(cap.pts).toFixed(2) + ' ha', src: cap.done ? 'closed boundary' : 'closes on finish' } : { k: 'Fixes', v: String(cap.pts.length), src: 'averaged' },
    { k: 'Flood depth', v: `${np.zone[0].toUpperCase()}${np.zone.slice(1)} · ${zoneDepths(model)[np.zone].toFixed(2)} m`, src: model.measured ? 'from depth readings' : 'design example' }
  ] : [];

  return (
    <div className="col">
      <div style={{ position: 'relative', borderBottom: '1px solid var(--color-divider)' }}>
        <LiveMap here={place} gps={place.gps} acc={place.acc} plots={[...s.farm.plots.filter(p => p.boundary.length).map(p => p.boundary), ...s.plots.map(p => p.pts)]} track={cap?.pts ?? []} closed={!!cap?.done} />
        <div style={{ position: 'absolute', left: 10, bottom: 10, zIndex: 500, display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-start' }}>
          <span className="num" style={{ fontSize: 11, background: 'var(--color-bg)', border: '1px solid var(--color-divider)', borderRadius: 'var(--radius-sm)', padding: '3px 6px' }}>{place.payam} · {place.county} · {place.state}</span>
          <span className="num" style={{ fontSize: 11, background: 'var(--color-bg)', border: '1px solid var(--color-divider)', borderRadius: 'var(--radius-sm)', padding: '3px 6px' }}>{place.gps ? `${place.lat.toFixed(5)}° N, ${place.lon.toFixed(5)}° E${place.acc ? ` ±${Math.round(place.acc)} m` : ''}` : 'Waiting for GPS… showing the farm'} · 150 m buffer</span>
        </div>
        <div style={{ position: 'absolute', right: 10, top: 10, zIndex: 500 }}>
          <button onClick={() => go('depth')} title={depthSrc} style={{ fontSize: 11, background: 'var(--color-bg)', border: '1px solid var(--color-divider)', borderRadius: 'var(--radius-sm)', padding: '4px 7px', textAlign: 'left' }}>
            Basin water {depth.toFixed(2)} m<span style={{ display: 'block', fontSize: 9.5, color: model.measured ? 'var(--color-accent-800)' : '#856404' }}>{model.measured ? 'measured · tap to add a reading' : 'example · tap to record depth'}</span>
          </button>
        </div>
        {!online && <div style={{ position: 'absolute', left: 0, right: 0, top: 0, zIndex: 500, fontSize: 11, padding: '4px 8px', background: 'color-mix(in srgb, var(--color-bg) 85%, transparent)' }}>No signal: satellite imagery appears when online. GPS and plots still work.</div>}
      </div>
      {!cap ? (
        <div className="pad g12">
          <h2 className="h2">Map a new plot</h2>
          <p className="body" style={{ fontSize: 13.5, color: 'var(--color-neutral-800)' }}>GPS works offline. Elevation and slope are read from the terrain model as soon as the phone reconnects.</p>
          <div className="grid2">
            <button className="btn col" style={{ minHeight: 64, alignItems: 'center', justifyContent: 'center', gap: 4 }} onClick={() => start('walk')}>
              <Icon d="M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z M16 17h4 M4 13h4" size={20} sw={1.6} />Walk boundary
            </button>
            <button className="btn col" style={{ minHeight: 64, alignItems: 'center', justifyContent: 'center', gap: 4 }} onClick={() => start('pin')}>
              <Icon d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0 M12 7a3 3 0 1 0 0 6a3 3 0 1 0 0-6" size={20} sw={1.6} />Drop a pin
            </button>
          </div>
          {savedMsg && <div className="msg">{savedMsg}</div>}
          <div className="note" style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 10 }}>{s.farm.plots.length} plots in the farm register · {s.farm.plots.filter(p => p.boundary.length > 2).length} with a mapped boundary</div>
        </div>
      ) : (
        <div className="pad g12" style={{ paddingTop: 14 }}>
          <div className="between">
            <h2 className="h2">{cap.mode === 'walk' ? 'Walking boundary' : 'Dropping pin'}</h2>
            <span className="it" style={{ fontSize: 12, color: 'var(--color-accent-700)' }}>{cap.done ? `Fix locked ±${acc?.toFixed(1)} m` : cap.mode === 'walk' ? `${cap.pts.length} points…` : 'Averaging GPS…'}</span>
          </div>
          {cap.err && <div className="msg">{cap.err}</div>}
          {readouts.length > 0 && (
            <div className="grid2" style={{ gap: 0, borderTop: '1px solid var(--color-divider)' }}>
              {readouts.map(r => <div key={r.k} style={{ padding: '8px 0', borderBottom: '1px solid var(--color-divider)' }}><div className="lbl">{r.k}</div><div className="head num" style={{ fontSize: 19 }}>{r.v}</div><div style={{ fontSize: 10.5, color: 'var(--color-neutral-600)' }}>{r.src}</div></div>)}
            </div>
          )}
          {cap.done && canEdit && (
            <div className="box col g10" style={{ padding: 12 }}>
              <Field label="Save to"><select className="input" value={target} onChange={e => { setTarget(e.target.value); setSaveErr(''); }}>
                <option value="new">New plot…</option>
                {s.farm.plots.map(p => <option key={p.id} value={p.id}>{p.code} · {p.crop}{p.boundary.length > 2 ? ' (replace boundary)' : ''}</option>)}
              </select></Field>
              {target === 'new' && <>
                <div className="grid2">
                  <Field label="Plot code"><input className="input" value={np.code} placeholder="B‑13" onChange={e => { setNp({ ...np, code: e.target.value.toUpperCase() }); setSaveErr(''); }} /></Field>
                  <Field label="Main crop"><select className="input" value={np.crop} onChange={e => setNp({ ...np, crop: e.target.value })}>{s.farm.crops.map(c => <option key={c.id}>{c.name}</option>)}</select></Field>
                </div>
                <Seg items={[['ridge', 'Ridge'], ['slope', 'Slope'], ['basin', 'Basin']]} value={np.zone} onPick={z => setNp({ ...np, zone: z })} />
                <Field label="Group"><select className="input" value={np.groupId} onChange={e => setNp({ ...np, groupId: e.target.value })}><option value="">Individual</option>{s.farm.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
              </>}
              {saveErr && <div className="msg">{saveErr}</div>}
            </div>
          )}
          <div className="grid2">
            <button className="btn plain" onClick={() => { stop(); setCap(null); }}>Cancel</button>
            {cap.mode === 'walk' && !cap.done
              ? <button className="btn" onClick={finish}>Finish boundary</button>
              : <button className="btn" disabled={!cap.done} onClick={save}>Save plot</button>}
          </div>
        </div>
      )}
    </div>
  );
}
