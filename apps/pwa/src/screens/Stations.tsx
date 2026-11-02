// Water level graph for the station nearest to any payam: pick state, county and payam, see its last observations.
import { useEffect, useMemo, useState } from 'react';
import { countiesOf, countText, distanceNote, levelSummary, listPayams, payamAt, payamByCode, payamCentre, payamsOf, riskShare, statesList, type Count, type ExposureResult, type Obs, type StationLevels, type StationSeries } from '@abuk/core';
import { api, explain } from '../api';
import { useOnline, usePlace } from '../net';
import { getState, setState, useApp } from '../store';
import { Field, Seg } from '../ui';

interface Sel { state: string; county: string; payam: string }
const mmdd = (d: string) => d.slice(5);
const dayLabel = (d: string) => new Date(d + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const m = (v: number, dp = 2) => v.toFixed(dp);

// Line chart in the style of the project's station charts: blue line, a point per observation, the highest and lowest labelled.
function LevelChart({ title, obs }: { title: string; obs: Obs[] }) {
  const sum = levelSummary(obs);
  if (!sum) return null;
  const W = 360, H = 250, L = 56, R = 14, T = 20, B = 58;
  const lo = sum.min.v, hi = sum.max.v, pad = Math.max((hi - lo) * 0.18, 0.02);
  const y0 = lo - pad, y1 = hi + pad;
  const x = (i: number) => L + (obs.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (obs.length - 1));
  const y = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const pts = obs.map((o, i) => `${x(i).toFixed(1)},${y(o.v).toFixed(1)}`).join(' ');
  const iMax = obs.indexOf(sum.max), iMin = obs.indexOf(sum.min);
  const tag = (i: number, o: Obs, kind: 'max' | 'min') => {
    const cx = x(i), cy = y(o.v), end = cx > W * 0.6, dy = kind === 'max' ? -22 : 24;
    return (
      <g key={kind}>
        <line x1={cx} x2={cx} y1={cy} y2={cy + dy * 0.55} stroke="currentColor" strokeOpacity=".5" />
        <text x={end ? cx + 4 : cx - 4} y={cy + dy} textAnchor={end ? 'end' : 'start'} fontSize="12" fill="var(--color-accent-700)">{kind} {m(o.v)}</text>
      </g>
    );
  };
  return (
    <figure style={{ margin: 0 }} aria-label={`${title}: line chart of the last ${obs.length} observations`}>
      <div style={{ fontWeight: 700, fontSize: 14, margin: '0 0 4px' }}>{title}, last {obs.length} observations (m)</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" style={{ width: '100%', height: 'auto', display: 'block', color: 'var(--color-neutral-700)' }}>
        {[hi, lo].map(v => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="currentColor" strokeOpacity=".28" />
            <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="currentColor">{m(v)}</text>
          </g>
        ))}
        <polyline points={pts} fill="none" stroke="var(--color-accent)" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        {obs.map((o, i) => <circle key={o.d} cx={x(i)} cy={y(o.v)} r="3.6" fill="var(--color-accent)" />)}
        {tag(iMax, sum.max, 'max')}
        {iMin !== iMax && tag(iMin, sum.min, 'min')}
        {obs.map((o, i) => <text key={o.d} transform={`translate(${x(i) + 3},${H - B + 12}) rotate(-45)`} textAnchor="end" fontSize="10.5" fill="currentColor">{mmdd(o.d)}</text>)}
      </svg>
    </figure>
  );
}

// What sits inside the payam and how much of it is at risk, from payam_exposure.csv in the Drive folder.
function ExposureCard({ payam, res }: { payam: string; res: ExposureResult }) {
  const row = res.row;
  if (!row) return <div className="note">{res.fileFound ? `payam_exposure.csv has no row for ${payam}.` : 'The at-risk counts for this payam are not available yet: payam_exposure.csv is not in the project Drive folder.'}</div>;
  const items: [string, Count][] = [['Population', row.population], ['Buildings', row.buildings], ['Schools', row.schools], ['Health facilities', row.health]];
  return (
    <div className="box col g8" style={{ padding: 12 }}>
      <div className="kick sm">Within {payam}</div>
      {items.map(([label, c]) => {
        const pct = riskShare(c);
        return (
          <div key={label} className="rowg" style={{ padding: '6px 0', borderBottom: '1px solid var(--color-divider)' }}>
            <span>{label}<span className="sub"> {countText(c.total)} in all</span></span>
            <span className="num"><b>{countText(c.risk)}</b> at risk{pct != null ? <span className="sub"> {pct}%</span> : null}</span>
          </div>
        );
      })}
      <p className="note">{row.hazard ? `At risk means: ${row.hazard}. ` : ''}{row.asOf ? `As of ${row.asOf}. ` : ''}{res.stale ? 'The server could not refresh these just now, so these are the last it had.' : ''}</p>
    </div>
  );
}

export function Stations() {
  const s = useApp(), online = useOnline(), place = usePlace();
  const gpsArea = useMemo(() => payamAt(place.lat, place.lon), [place.lat, place.lon]);
  const [pick, setPick] = useState<Sel | null>(null);
  const sel: Sel = pick ?? { state: gpsArea?.state ?? '', county: gpsArea?.county ?? '', payam: gpsArea?.payam ?? '' };
  const area = useMemo(() => {
    if (!pick) return gpsArea;
    const p = listPayams().find(x => x.state === pick.state && x.county === pick.county && x.payam === pick.payam);
    return p ? payamByCode(p.pcode) : null;
  }, [pick?.state, pick?.county, pick?.payam, gpsArea?.pcode]); // eslint-disable-line react-hooks/exhaustive-deps
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [which, setWhich] = useState(0);
  const key = area?.pcode ?? '';
  const data: StationLevels | undefined = key ? s.stationLevels[key] : undefined;
  const exposure: ExposureResult | undefined = key ? s.exposure[key] : undefined;
  const live = !!s.session && !s.session.demo;

  const load = async () => {
    if (!area) return setErr('Choose a state, county and payam first.');
    if (!live) return setErr('Sign in to see station readings. Demo mode has no station data.');
    if (!online) return setErr(data ? 'No signal: showing the readings saved on this phone.' : 'No signal, and nothing saved for this place yet.');
    setBusy(true); setErr('');
    const c = payamCentre(area);
    // Two separate lookups: a missing station file must not hide the at-risk counts, and the other way round.
    const q = `pcode=${encodeURIComponent(area.pcode)}&payam=${encodeURIComponent(area.payam)}&county=${encodeURIComponent(area.county)}`;
    const [r, x] = await Promise.allSettled([
      api<StationLevels>(`/api/stations/near?lat=${c.lat.toFixed(4)}&lon=${c.lon.toFixed(4)}&n=3&obs=10`),
      api<ExposureResult>(`/api/exposure?${q}`),
    ]);
    if (x.status === 'fulfilled') setState(st => ({ exposure: { ...st.exposure, [area.pcode]: x.value } }));
    if (r.status === 'fulfilled') { setState(st => ({ stationLevels: { ...st.stationLevels, [area.pcode]: r.value } })); setWhich(0); }
    else setErr(explain(r.reason));
    setBusy(false);
  };
  // Fetch when the place changes, unless it was fetched in the last hour.
  useEffect(() => {
    setWhich(0);
    if (!area || !live || !online) return;
    const have = getState().stationLevels[area.pcode];
    if (!have || !getState().exposure[area.pcode] || Date.now() - Date.parse(have.at) > 3_600_000) load();
  }, [key, live, online]); // eslint-disable-line react-hooks/exhaustive-deps

  const states = statesList(), counties = sel.state ? countiesOf(sel.state) : [], payams = sel.state && sel.county ? payamsOf(sel.state, sel.county) : [];
  const choose = (next: Sel) => { setPick(next); setErr(''); };
  const st: StationSeries | undefined = data?.stations[Math.min(which, (data?.stations.length ?? 1) - 1)];
  const sum = st ? levelSummary(st.obs) : null;

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13.5 }}>Water level at the river or lake station nearest to a place. Choose a state, county and payam to see its last 10 observations.</p>
      <div className="box col g8" style={{ padding: 12 }}>
        <div className="between"><span className="kick sm">{pick ? 'Place you are looking at' : 'Payam at your GPS position'}</span>{pick && <button className="btn plain sm" onClick={() => { setPick(null); setErr(''); }}>Back to my location</button>}</div>
        <div className="grid2" style={{ gap: 8 }}>
          <Field label="State">
            <select className="input" value={sel.state} onChange={e => choose({ state: e.target.value, county: '', payam: '' })}>
              <option value="" disabled>Choose…</option>{states.map(x => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="County">
            <select className="input" value={sel.county} disabled={!sel.state} onChange={e => choose({ ...sel, county: e.target.value, payam: '' })}>
              <option value="" disabled>Choose…</option>{counties.map(x => <option key={x}>{x}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Payam">
          <select className="input" value={sel.payam} disabled={!sel.county} onChange={e => choose({ ...sel, payam: e.target.value })}>
            <option value="" disabled>Choose…</option>{payams.map(x => <option key={x}>{x}</option>)}
          </select>
        </Field>
      </div>

      {busy && !data && <div className="note">Looking for the nearest station…</div>}
      {err && <div className="msg">{err}</div>}

      {data && st && sum && (
        <>
          {data.stations.length > 1 && <Seg items={data.stations.map((x, i) => [i, `${x.name.split(',')[0]} · ${Math.round(x.km)} km`] as [number, string])} value={Math.min(which, data.stations.length - 1)} onPick={setWhich} fontSize={11.5} />}
          <LevelChart title={st.name} obs={st.obs} />
          <div className="grid3" style={{ gap: 0, borderTop: '1px solid var(--color-divider)' }}>
            {[['Latest', `${m(sum.last.v)} m`, dayLabel(sum.last.d)], ['Change', sum.change == null ? '—' : `${sum.change > 0 ? '+' : ''}${m(sum.change, 2)} m`, 'since the one before'], ['Distance', `${Math.round(st.km)} km`, `from ${area?.payam ?? 'the payam'}`]].map(([k, v, sub], i) => (
              <div key={k} style={{ padding: '9px 8px', borderBottom: '1px solid var(--color-divider)', borderLeft: i ? '1px solid var(--color-divider)' : undefined }}><div className="lbl">{k}</div><div className="head num" style={{ fontSize: 20 }}>{v}</div><div className="sub">{sub}</div></div>
            ))}
          </div>
          <div className="sub" style={{ lineHeight: 1.45 }}>{st.name}{st.type ? ` (${st.type})` : ''} is {Math.round(st.km)} km from the middle of {area?.payam}: {distanceNote(st.km)}.</div>
          <div>
            <div className="kick sm" style={{ borderBottom: '1px solid var(--color-divider)', paddingBottom: 4 }}>Observations</div>
            {[...st.obs].reverse().map((o, i, a) => {
              const prev = a[i + 1];
              return <div key={o.d} className="rowg" style={{ padding: '7px 0', borderBottom: '1px solid var(--color-divider)' }}><span>{dayLabel(o.d)}</span><span className="num">{m(o.v, 3)} m{prev ? <span className="sub"> {o.v - prev.v >= 0 ? '+' : ''}{m(o.v - prev.v, 2)}</span> : null}</span></div>;
            })}
          </div>
          <p className="note">{data.stale ? 'The server could not refresh the readings just now, so these are the last ones it had. ' : ''}Readings come from the project's satellite water-level file in Drive (merged_altimetry_stations), refreshed each night. Height is metres above the sea-level reference, so only the rise and fall matter, not the number itself. Saved on this phone, last updated {new Date(data.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}.</p>
          <button className="btn plain" onClick={load} disabled={busy}>{busy ? 'Updating…' : 'Update now'}</button>
        </>
      )}
      {data && !st && <div className="note">No station in the data has readings.</div>}
      {area && exposure && <ExposureCard payam={area.payam} res={exposure} />}
      {!data && !busy && !err && <button className="btn" onClick={load} disabled={!area}>Show the nearest station</button>}
    </div>
  );
}
