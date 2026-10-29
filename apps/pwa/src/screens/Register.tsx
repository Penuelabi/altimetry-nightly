import { useRef, useState, type ReactNode } from 'react';
import { BLANK_KIN, NO_ADMIN, adminLabel, blankPerson, normPhone, personError, type Person, chainFor, editAllowed, newId, personById, personName, plotLabel, polygonHa, removeAllowed, type Crop, type CropCategory, type CropSeason, type Group, type OilBatch, type Plot, type ProcessRun, type Register, type Zone } from '@abuk/core';
import { farmChange, getState, useApp } from '../store';
import { useOnline, usePlace } from '../net';
import { AdminPicker, MultiPick, NewPerson, PersonFields, PersonSelect, useHereAdmin } from '../pickers';
import { LiveMap } from '../LiveMap';
import { Photo, savePhoto } from '../photos';
import { Chevron, Field, Seg } from '../ui';

type Tab = 'plots' | 'crops' | 'groups' | 'people' | 'batches' | 'runs';
const ZONES: [Zone, string][] = [['ridge', 'Ridge'], ['slope', 'Slope'], ['basin', 'Basin']];

export function RegisterScreen() {
  const s = useApp(), online = useOnline();
  const [tab, setTab] = useState<Tab>(s.regTab);
  const [open, setOpen] = useState<string | null>(null); // id being edited, or 'new'
  const role = s.session?.user.role ?? '';
  const can = editAllowed(role), canDel = removeAllowed(role);
  const reg = s.farm;
  const pick = (t: Tab) => { setTab(t); setOpen(null); };
  const close = () => setOpen(null);

  const rows: { id: string; title: string; sub: string }[] =
    tab === 'plots' ? reg.plots.map(p => ({ id: p.id, title: p.code, sub: `${p.zone} · ${[p.crop, ...(p.crops ?? [])].join(', ')}${p.areaHa ? ` · ${p.areaHa} ha` : ''} · ${groupName(reg, p.groupId) || p.holder || 'no group'}${p.boundary.length > 2 ? ' · mapped' : ''}` }))
    : tab === 'crops' ? reg.crops.map(c => ({ id: c.id, title: c.name, sub: [c.localName, c.category, c.season, c.photos?.length ? `${c.photos.length} photos` : ''].filter(Boolean).join(' · ') }))
    : tab === 'groups' ? reg.groups.map(g => ({ id: g.id, title: g.name, sub: `${g.members.length} members${g.lead ? ` · lead ${g.lead}` : ''}` }))
    : tab === 'people' ? (reg.people ?? []).map(p => ({ id: p.id, title: personName(p), sub: `${p.phone}${p.phone2 ? ` · ${p.phone2}` : ''} · ${adminLabel(p.admin)}${reg.groups.filter(g => g.members.some(m => m.personId === p.id)).map(g => ` · ${g.name}`).join('')}` }))
    : tab === 'batches' ? reg.batches.map(b => ({ id: b.id, title: b.code, sub: `${b.product ?? 'Balanites oil'} · ${b.bottles} × ${b.unit ?? '1 L'} · plot ${reg.plots.find(p => p.id === b.plotId)?.code ?? '—'} · ${b.pressed}` }))
    : reg.runs.map(r => ({ id: r.id, title: `${runProduct(r)} · ${r.date}`, sub: r.steps.map(x => x.out).filter(Boolean).join(' → ') }));

  const form = (id: string) => {
    const isNew = id === 'new';
    const remove = !isNew && canDel ? () => { farmChange({ op: 'remove', kind: tab === 'plots' ? 'plot' : tab === 'crops' ? 'crop' : tab === 'groups' ? 'group' : tab === 'people' ? 'person' : tab === 'batches' ? 'batch' : 'run', id }); close(); } : undefined;
    if (tab === 'plots') return <PlotForm reg={reg} item={reg.plots.find(p => p.id === id)} onSave={p => { farmChange({ op: 'upsert', kind: 'plot', item: p }); close(); }} onCancel={close} onRemove={remove} />;
    if (tab === 'crops') return <CropForm reg={reg} item={reg.crops.find(c => c.id === id)} onSave={c => { farmChange({ op: 'upsert', kind: 'crop', item: c }); close(); }} onCancel={close} onRemove={remove} />;
    if (tab === 'groups') return <GroupForm item={reg.groups.find(g => g.id === id)} onSave={g => { farmChange({ op: 'upsert', kind: 'group', item: g }); close(); }} onCancel={close} onRemove={remove} />;
    if (tab === 'people') return <PersonForm item={reg.people?.find(p => p.id === id)} onSave={p => { farmChange({ op: 'upsert', kind: 'person', item: p }); close(); }} onCancel={close} onRemove={remove} />;
    if (tab === 'batches') return <BatchForm reg={reg} item={reg.batches.find(b => b.id === id)} onSave={b => { farmChange({ op: 'upsert', kind: 'batch', item: b }); close(); }} onCancel={close} onRemove={remove} />;
    return <RunForm reg={reg} item={reg.runs.find(r => r.id === id)} onSave={r => { farmChange({ op: 'upsert', kind: 'run', item: r }); close(); }} onCancel={close} onRemove={remove} />;
  };

  const LABEL: Record<Tab, string> = { plots: 'plot', crops: 'crop', groups: 'group', people: 'person', batches: 'product batch', runs: 'processing run' };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13 }}>The project's shared list of plots, crops, groups, oil batches and processing runs. Changes show on every phone after it syncs.{can ? '' : ' Only admins and group leads can change it.'}</p>
      <div style={{ overflowX: 'auto' }}>
        <Seg items={[['plots', 'Plots'], ['crops', 'Crops'], ['groups', 'Groups'], ['people', 'People'], ['batches', 'Batches'], ['runs', 'Processing']]} value={tab} onPick={pick} fontSize={12} />
      </div>
      {s.farmOps.length > 0 && <div className="msg">{s.farmOps.length} change{s.farmOps.length > 1 ? 's' : ''} on this phone, {s.session?.demo ? 'kept here only (demo mode)' : online ? 'syncing…' : 'will sync when online'}.</div>}
      {can && open !== 'new' && <button className="btn" onClick={() => setOpen('new')}>+ Add {LABEL[tab]}</button>}
      {open === 'new' && form('new')}
      <div>
        {rows.map(r => open === r.id ? <div key={r.id} style={{ padding: '8px 0' }}>{form(r.id)}</div> : (
          <button key={r.id} className="row hov" disabled={!can} onClick={() => setOpen(r.id)} style={{ display: 'grid', gridTemplateColumns: '1fr 16px', alignItems: 'center', padding: '10px 0' }}>
            <span><span style={{ display: 'block', fontSize: 14.5 }}>{r.title}</span>{r.sub && <span className="sub">{r.sub}</span>}</span>
            {can && <Chevron />}
          </button>
        ))}
        {!rows.length && <div className="note" style={{ padding: '10px 0' }}>Nothing here yet.</div>}
      </div>
    </div>
  );
}

const groupName = (reg: Register, id: string) => reg.groups.find(g => g.id === id)?.name ?? '';

function Shell({ title, children, onSave, onCancel, onRemove, err }: { title: string; children: ReactNode; onSave: () => void; onCancel: () => void; onRemove?: () => void; err: string }) {
  const [sure, setSure] = useState(false);
  return (
    <div className="box col g10" style={{ padding: 12, background: 'var(--color-surface)' }}>
      <h2 className="h2 h20">{title}</h2>
      {children}
      {err && <div className="msg">{err}</div>}
      <div className="grid2" style={{ gap: 8 }}>
        <button className="btn plain md" onClick={onCancel}>Cancel</button>
        <button className="btn md" onClick={onSave}>Save</button>
      </div>
      {onRemove && (sure
        ? <button className="btn plain md" style={{ color: 'var(--color-accent-800)' }} onClick={onRemove}>Yes, delete it</button>
        : <button className="link" style={{ alignSelf: 'flex-start', color: 'var(--color-neutral-700)' }} onClick={() => setSure(true)}>Delete…</button>)}
    </div>
  );
}

function PlotForm({ reg, item, onSave, onCancel, onRemove }: { reg: Register; item?: Plot; onSave: (p: Plot) => void; onCancel: () => void; onRemove?: () => void }) {
  const place = usePlace(), hereAdmin = useHereAdmin();
  const [p, setP] = useState<Plot>(item ?? { id: newId('plot'), code: '', zone: 'basin', crop: reg.crops[0]?.name ?? '', crops: [], groupId: '', holder: '', areaHa: null, boundary: [], notes: '', admin: hereAdmin });
  const [err, setErr] = useState('');
  const [cropForm, setCropForm] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const set = <K extends keyof Plot>(k: K, v: Plot[K]) => { setP({ ...p, [k]: v }); setErr(''); };
  const others = p.crops ?? [];
  const toggleOther = (n: string) => set('crops', others.includes(n) ? others.filter(x => x !== n) : [...others, n]);
  // A new crop (with its details and photos) goes into the register for everyone, and onto this plot.
  if (cropForm) return <CropForm reg={reg} onCancel={() => setCropForm(false)} onSave={c => { farmChange({ op: 'upsert', kind: 'crop', item: c }); if (c.name !== p.crop) set('crops', [...others, c.name]); setCropForm(false); }} />;
  // Boundary drawn by tapping corners on the satellite map; the area fills in from it.
  const setBoundary = (b: Plot['boundary']) => setP(x => ({ ...x, boundary: b, areaHa: b.length > 2 ? Math.round(polygonHa(b) * 100) / 100 : x.areaHa }));
  const save = () => {
    if (!p.code.trim()) return setErr('Give the plot a code, e.g. B‑13.');
    if (reg.plots.some(x => x.code.trim().toLowerCase() === p.code.trim().toLowerCase() && x.id !== p.id)) return setErr('Another plot already has that code.');
    if (p.boundary.length > 0 && p.boundary.length < 3) return setErr('A boundary needs at least three corners, or clear it.');
    onSave({ ...p, code: p.code.trim(), crops: others.filter(n => n !== p.crop) });
  };
  const centre = p.boundary[0] ? { lat: p.boundary.reduce((a, b) => a + b.lat, 0) / p.boundary.length, lon: p.boundary.reduce((a, b) => a + b.lon, 0) / p.boundary.length } : place;
  return (
    <Shell title={item ? `Edit plot ${item.code}` : 'New plot'} onSave={save} onCancel={onCancel} onRemove={onRemove} err={err}>
      <div className="grid2">
        <Field label="Plot code"><input className="input" value={p.code} placeholder="B‑13" onChange={e => set('code', e.target.value.toUpperCase())} /></Field>
        <Field label={`Area (ha)${p.boundary.length > 2 ? ' · from map' : ''}`}><input className="input num" type="number" inputMode="decimal" value={p.areaHa ?? ''} onChange={e => set('areaHa', e.target.value === '' ? null : Number(e.target.value))} /></Field>
      </div>
      <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Zone</div>
      <Seg items={ZONES} value={p.zone} onPick={z => set('zone', z)} />
      <Field label="Main crop"><select className="input" value={p.crop} onChange={e => setP({ ...p, crop: e.target.value, crops: others.filter(n => n !== e.target.value) })}>{reg.crops.map(c => <option key={c.id}>{c.name}</option>)}</select></Field>
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Other crops on this plot</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {reg.crops.filter(c => c.name !== p.crop).map(c => <button key={c.id} className={'chip' + (others.includes(c.name) ? ' on' : '')} style={{ minHeight: 34, padding: '0 10px', fontSize: 12.5 }} onClick={() => toggleOther(c.name)}>{others.includes(c.name) ? '✓ ' : ''}{c.name}</button>)}
        </div>
        <button className="btn plain sm" onClick={() => setCropForm(true)}>+ A crop not in the list</button>
      </div>
      <div className="grid2">
        <Field label="Group"><select className="input" value={p.groupId} onChange={e => set('groupId', e.target.value)}><option value="">Individual</option>{reg.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
        <Field label="Holder (individual plots)"><input className="input" value={p.holder} disabled={!!p.groupId} onChange={e => set('holder', e.target.value)} /></Field>
      </div>
      <AdminPicker value={p.admin ?? hereAdmin} onChange={admin => set('admin', admin)} label="Plot is in" />
      <Field label="Notes"><input className="input" value={p.notes} onChange={e => set('notes', e.target.value)} /></Field>
      <div className="col g6">
        <div className="between"><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Boundary</span><span className="sub num">{p.boundary.length > 2 ? `${p.boundary.length} corners · ${polygonHa(p.boundary).toFixed(2)} ha` : p.boundary.length ? `${p.boundary.length} corner${p.boundary.length > 1 ? 's' : ''}, need 3+` : 'not mapped'}</span></div>
        {drawing ? <>
          <div className="sub">Tap each corner of the plot on the map, in order around the edge.</div>
          <LiveMap here={centre} gps={place.gps} acc={null} bufferM={150} plots={reg.plots.filter(x => x.id !== p.id && x.boundary.length > 2).map(x => x.boundary)} track={p.boundary} closed={p.boundary.length > 2} height={300} onTap={pt => setBoundary([...p.boundary, pt])} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 6 }}>
            <button className="btn plain sm" disabled={!p.boundary.length} onClick={() => setBoundary(p.boundary.slice(0, -1))}>Undo corner</button>
            <button className="btn plain sm" disabled={!place.gps} onClick={() => setBoundary([...p.boundary, { lat: place.lat, lon: place.lon }])}>Add my GPS</button>
            <button className="btn plain sm" disabled={!p.boundary.length} onClick={() => setBoundary([])}>Clear</button>
          </div>
          <button className="btn sm" onClick={() => setDrawing(false)}>Done drawing</button>
        </> : <button className="btn plain" onClick={() => setDrawing(true)}>{p.boundary.length > 2 ? 'Redraw boundary on map' : 'Draw boundary on map'}</button>}
        <div className="sub">Or walk it with GPS: Map → Walk boundary, then save it to this plot.</div>
      </div>
    </Shell>
  );
}

const CATS: CropCategory[] = ['cereal', 'legume', 'vegetable', 'oilseed', 'tree', 'root', 'fibre', 'fruit', 'other'];
const SEASONS: [CropSeason, string][] = [['rainfed', 'Rainfed'], ['recession', 'Flood recession'], ['perennial', 'Perennial'], ['irrigated', 'Irrigated']];
const CROP_PHOTOS = 3;

// A crop with what others need to know about it, and three photos (whole plant, leaf, fruit or grain).
export function CropForm({ reg, item, onSave, onCancel, onRemove }: { reg: Register; item?: Crop; onSave: (c: Crop) => void; onCancel: () => void; onRemove?: () => void }) {
  const [c, setC] = useState<Crop>(item ?? { id: newId('crop'), name: '', localName: '', scientific: '', variety: '', category: 'cereal', season: 'rainfed', daysToHarvest: null, spacing: '', seedRate: '', uses: '', photos: [] });
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const set = <K extends keyof Crop>(k: K, v: Crop[K]) => { setC(x => ({ ...x, [k]: v })); setErr(''); };
  const photos = c.photos ?? [];
  const save = () => {
    const name = c.name.trim();
    if (!name) return setErr('Enter the crop name.');
    if (reg.crops.some(x => x.name.toLowerCase() === name.toLowerCase() && x.id !== c.id)) return setErr('That crop is already in the list.');
    if (!item && photos.length < CROP_PHOTOS) return setErr(`Add ${CROP_PHOTOS} photos: whole plant, leaf, and fruit or grain.`);
    onSave({ ...c, name });
  };
  return (
    <Shell title={item ? `Edit ${item.name}` : 'New crop'} onSave={save} onCancel={onCancel} onRemove={onRemove} err={err}>
      <div className="grid2">
        <Field label="Crop name"><input className="input" value={c.name} placeholder="e.g. Pumpkin" onChange={e => set('name', e.target.value)} /></Field>
        <Field label="Local name"><input className="input" value={c.localName ?? ''} placeholder="Dinka / Arabic" onChange={e => set('localName', e.target.value)} /></Field>
      </div>
      <div className="grid2">
        <Field label="Scientific name"><input className="input" value={c.scientific ?? ''} placeholder="Cucurbita maxima" onChange={e => set('scientific', e.target.value)} /></Field>
        <Field label="Variety"><input className="input" value={c.variety ?? ''} placeholder="local, improved…" onChange={e => set('variety', e.target.value)} /></Field>
      </div>
      <div className="grid2">
        <Field label="Type"><select className="input" value={c.category ?? 'other'} onChange={e => set('category', e.target.value as CropCategory)}>{CATS.map(k => <option key={k}>{k}</option>)}</select></Field>
        <Field label="Grown"><select className="input" value={c.season ?? 'rainfed'} onChange={e => set('season', e.target.value as CropSeason)}>{SEASONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
      </div>
      <div className="grid2">
        <Field label="Days to harvest"><input className="input num" type="number" inputMode="numeric" value={c.daysToHarvest ?? ''} onChange={e => set('daysToHarvest', e.target.value === '' ? null : Number(e.target.value))} /></Field>
        <Field label="Spacing"><input className="input" value={c.spacing ?? ''} placeholder="75 × 20 cm" onChange={e => set('spacing', e.target.value)} /></Field>
      </div>
      <Field label="Seed rate"><input className="input" value={c.seedRate ?? ''} placeholder="e.g. 8 kg/ha" onChange={e => set('seedRate', e.target.value)} /></Field>
      <Field label="Uses"><input className="input" value={c.uses ?? ''} placeholder="food, sale, feed, oil…" onChange={e => set('uses', e.target.value)} /></Field>
      <div className="between"><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Photos: whole plant, leaf, fruit or grain</span><span className="num" style={{ fontSize: 12.5 }}>{photos.length} / {CROP_PHOTOS}{photos.length >= CROP_PHOTOS ? ' ✓' : ''}</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 6 }}>
        {photos.map((k, i) => <div key={k} style={{ position: 'relative' }}><Photo k={k} alt={`Crop photo ${i + 1}`} style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', borderRadius: 8 }} /><button aria-label={`Remove photo ${i + 1}`} onClick={() => set('photos', photos.filter(x => x !== k))} style={{ position: 'absolute', top: 4, right: 4, width: 24, height: 24, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,.55)', color: '#fff', fontSize: 14, lineHeight: '24px', padding: 0 }}>×</button></div>)}
        {photos.length < 6 && <button className="photo" style={{ aspectRatio: '1', minHeight: 0 }} disabled={busy} onClick={() => file.current?.click()}>{busy ? 'Saving…' : '+ Photo'}</button>}
      </div>
      <input ref={file} type="file" accept="image/*" capture="environment" hidden onChange={async e => { const f = e.target.files?.[0]; e.target.value = ''; if (!f) return; setBusy(true); const k = await savePhoto(f, 'crop'); setBusy(false); set('photos', [...(c.photos ?? []), k]); }} />
    </Shell>
  );
}

// One person's details, edited in place (the same record every group, store, VSLA and alert reads from).
function PersonForm({ item, onSave, onCancel, onRemove }: { item?: Person; onSave: (p: Person) => void; onCancel: () => void; onRemove?: () => void }) {
  const here = useHereAdmin();
  const [p, setP] = useState<Person>(item ? { ...item, kin: [...item.kin, BLANK_KIN, BLANK_KIN].slice(0, Math.max(2, item.kin.length)) } : blankPerson(newId('per'), here));
  const [err, setErr] = useState('');
  const save = () => { const bad = personError(p); if (bad) return setErr(bad); onSave({ ...p, phone: normPhone(p.phone), phone2: normPhone(p.phone2), kin: p.kin.map(k => ({ ...k, phone: normPhone(k.phone) })) }); };
  return (
    <Shell title={item ? `Edit ${personName(item)}` : 'New person'} onSave={save} onCancel={onCancel} onRemove={onRemove} err={err}>
      <PersonFields value={p} onChange={x => { setP(x); setErr(''); }} />
    </Shell>
  );
}

function GroupForm({ item, onSave, onCancel, onRemove }: { item?: Group; onSave: (g: Group) => void; onCancel: () => void; onRemove?: () => void }) {
  const s = useApp(), here = useHereAdmin();
  const [g, setG] = useState<Group>(item ?? { id: newId('group'), name: '', lead: '', members: [], admin: here });
  const [err, setErr] = useState('');
  const [detail, setDetail] = useState<string | null>(null); // member id getting details
  const people = s.farm.people ?? [];
  const inGroup = g.members.flatMap(m => (m.personId ? [m.personId] : []));
  // Members come from the person register (the full details are kept there); a new person is added on the spot.
  const add = (id: string) => {
    const p = getState().farm.people?.find(x => x.id === id);
    if (p && !inGroup.includes(p.id)) setG(x => ({ ...x, members: [...x.members, { id: newId('m'), name: personName(p), workDays: 0, personId: p.id }] }));
  };
  const withDetails = detail ? g.members.find(m => m.id === detail) : null;
  return (
    <Shell title={item ? `Edit ${item.name}` : 'New group'} onSave={() => (g.name.trim() ? onSave({ ...g, name: g.name.trim() }) : setErr('Enter the group name.'))} onCancel={onCancel} onRemove={onRemove} err={err}>
      <div className="grid2">
        <Field label="Group name"><input className="input" value={g.name} placeholder="Group 7" onChange={e => { setG({ ...g, name: e.target.value }); setErr(''); }} /></Field>
        <Field label="Group lead"><select className="input" value={g.lead} onChange={e => setG({ ...g, lead: e.target.value })}>
          <option value="">—</option>{g.lead && !g.members.some(m => m.name === g.lead) && <option>{g.lead}</option>}{g.members.map(m => <option key={m.id}>{m.name}</option>)}
        </select></Field>
      </div>
      <AdminPicker value={g.admin ?? NO_ADMIN} onChange={admin => setG({ ...g, admin })} label="Group is based in" />
      <div className="section">Members · {g.members.length}</div>
      {g.members.map(m => {
        const p = personById(s.farm, m.personId);
        return (
          <div key={m.id} className="rowg" style={{ alignItems: 'center', padding: '6px 0' }}>
            <span><span style={{ display: 'block', fontSize: 14 }}>{m.name}</span><span className="sub">{p ? `${p.phone}${p.phone2 ? ` · ${p.phone2}` : ''} · ${adminLabel(p.admin)}` : 'no personal details yet'}</span></span>
            <span style={{ display: 'flex', gap: 6 }}>
              {!p && <button className="btn plain sm" onClick={() => setDetail(m.id)}>Add details</button>}
              <button className="btn plain sm" onClick={() => setG({ ...g, members: g.members.filter(x => x.id !== m.id) })} aria-label={`Remove ${m.name}`}>Remove</button>
            </span>
          </div>
        );
      })}
      {withDetails
        ? <NewPerson initial={{ name: withDetails.name.split(' ')[0], name2: withDetails.name.split(' ').slice(1).join(' '), admin: g.admin ?? here }} onCancel={() => setDetail(null)}
            onSaved={p => { setG(x => ({ ...x, members: x.members.map(m => (m.id === detail ? { ...m, personId: p.id, name: personName(p) } : m)) })); setDetail(null); }} />
        : <PersonSelect label="Add a member" value="" empty={people.length ? 'Pick from the list, or add a new person…' : 'Add the first person…'} only={people.filter(p => !inGroup.includes(p.id)).map(p => p.id)} onChange={id => id && add(id)} />}
    </Shell>
  );
}

const centroid = (b: { lat: number; lon: number }[]) => (b.length ? { lat: b.reduce((a, x) => a + x.lat, 0) / b.length, lon: b.reduce((a, x) => a + x.lon, 0) / b.length } : null);
const prefix = (s: string) => (s.replace(/[^A-Za-z]/g, '').slice(0, 3).toUpperCase() || 'BAT');

// A traceable batch of any product: crop and product, source plot with its GPS, the processing run,
// quantity and unit, quality, store and who packed it.
function BatchForm({ reg, item, onSave, onCancel, onRemove }: { reg: Register; item?: OilBatch; onSave: (b: OilBatch) => void; onCancel: () => void; onRemove?: () => void }) {
  const s = useApp(), place = usePlace(), hereAdmin = useHereAdmin();
  const yy = new Date().getFullYear() % 100;
  const firstPlot = reg.plots.find(p => p.zone === 'basin') ?? reg.plots[0];
  const crop0 = firstPlot?.crop ?? reg.crops[0]?.name ?? '';
  const nextCode = (crop: string) => { const pre = `${prefix(crop)}‑${yy}‑`; return `${pre}${String(reg.batches.filter(b => b.code.startsWith(pre)).length + 1).padStart(2, '0')}`; };
  const at = (plotId: string) => { const p = reg.plots.find(x => x.id === plotId); const c = p && centroid(p.boundary); return c ?? (place.gps ? { lat: place.lat, lon: place.lon } : { lat: null, lon: null }); };
  const [b, setB] = useState<OilBatch>(item ?? { id: newId('batch'), code: nextCode(crop0), plotId: firstPlot?.id ?? '', crop: crop0, product: chainFor(crop0).product, unit: chainFor(crop0).unit, fruit: '', pressed: new Date().toISOString().slice(0, 10), bottles: 0, place: adminLabel(hereAdmin), admin: hereAdmin, ...at(firstPlot?.id ?? ''), runId: '', storeId: reg.stores?.[0]?.id ?? '', quality: '', packedBy: s.session?.user.id ?? '', notes: '' });
  const [err, setErr] = useState('');
  const set = (patch: Partial<OilBatch>) => { setB(x => ({ ...x, ...patch })); setErr(''); };
  const pickPlot = (plotId: string) => { const p = reg.plots.find(x => x.id === plotId); set({ plotId, ...at(plotId), ...(p && !item ? { crop: p.crop, product: chainFor(p.crop).product, unit: chainFor(p.crop).unit, code: nextCode(p.crop) } : {}) }); };
  const pickCrop = (crop: string) => set({ crop, ...(!item ? { product: chainFor(crop).product, unit: chainFor(crop).unit, code: nextCode(crop) } : {}) });
  const runs = reg.runs.filter(r => !b.crop || (r.crop ?? '') === b.crop || chainFor(b.crop).product === runProduct(r));
  const save = () => {
    if (!b.code.trim()) return setErr('Enter a batch code.');
    if (!(b.bottles > 0)) return setErr('Enter how many units were packed.');
    if (reg.batches.some(x => x.code === b.code.trim() && x.id !== b.id)) return setErr('Another batch has that code.');
    onSave({ ...b, code: b.code.trim() });
  };
  return (
    <Shell title={item ? `Edit batch ${item.code}` : 'New product batch'} onSave={save} onCancel={onCancel} onRemove={onRemove} err={err}>
      <Field label="From plot"><select className="input" value={b.plotId} onChange={e => pickPlot(e.target.value)}>{reg.plots.map(p => <option key={p.id} value={p.id}>{plotLabel(p, reg)}</option>)}</select></Field>
      <div className="sub num">GPS {b.lat != null && b.lon != null ? `${b.lat.toFixed(5)}° N, ${b.lon.toFixed(5)}° E (${reg.plots.find(p => p.id === b.plotId)?.boundary.length ? 'plot centre' : 'your position'})` : 'not available: map the plot boundary'}</div>
      <div className="grid2">
        <Field label="Crop"><select className="input" value={b.crop ?? ''} onChange={e => pickCrop(e.target.value)}>{reg.crops.map(c => <option key={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Product"><input className="input" value={b.product ?? ''} onChange={e => set({ product: e.target.value })} /></Field>
      </div>
      <div className="grid2">
        <Field label="Batch code"><input className="input mono" value={b.code} onChange={e => set({ code: e.target.value.toUpperCase() })} /></Field>
        <Field label="Quantity"><input className="input num" type="number" inputMode="numeric" value={b.bottles || ''} onChange={e => set({ bottles: Number(e.target.value) })} /></Field>
      </div>
      <div className="grid2">
        <Field label="Unit"><input className="input" value={b.unit ?? ''} placeholder="1 L bottle" onChange={e => set({ unit: e.target.value })} /></Field>
        <Field label="Quality / grade"><input className="input" value={b.quality ?? ''} placeholder="A, B, export…" onChange={e => set({ quality: e.target.value })} /></Field>
      </div>
      <div className="grid2">
        <Field label="Harvested"><input className="input" value={b.fruit} placeholder="Jan–Feb 2027" onChange={e => set({ fruit: e.target.value })} /></Field>
        <Field label="Packed on"><input className="input" type="date" value={b.pressed} onChange={e => set({ pressed: e.target.value })} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
      </div>
      <Field label="Processing run"><select className="input" value={b.runId ?? ''} onChange={e => set({ runId: e.target.value })}><option value="">—</option>{runs.map(r => <option key={r.id} value={r.id}>{runProduct(r)} · {r.date}</option>)}</select></Field>
      <div className="grid2">
        <Field label="Kept in store"><select className="input" value={b.storeId ?? ''} onChange={e => set({ storeId: e.target.value })}><option value="">—</option>{(reg.stores ?? []).map(x => <option key={x.id} value={x.id}>{x.code}</option>)}</select></Field>
        <Field label="Packed by"><input className="input" value={b.packedBy ?? ''} onChange={e => set({ packedBy: e.target.value })} /></Field>
      </div>
      <AdminPicker value={b.admin ?? hereAdmin} onChange={admin => set({ admin, place: adminLabel(admin) })} label="Place" />
      <Field label="Notes"><input className="input" value={b.notes ?? ''} onChange={e => set({ notes: e.target.value })} /></Field>
    </Shell>
  );
}

export const runProduct = (r: ProcessRun) => r.product ?? (r.chain === 'balanites' ? 'Balanites oil' : r.chain === 'moringa' ? 'Moringa powder' : r.chain);

// A processing run for any crop: starts from the crop's usual steps (renamable, add or remove).
function RunForm({ reg, item, onSave, onCancel, onRemove }: { reg: Register; item?: ProcessRun; onSave: (r: ProcessRun) => void; onCancel: () => void; onRemove?: () => void }) {
  const blank = (crop: string): ProcessRun => { const c = chainFor(crop); return { id: newId('run'), chain: c.product, crop, product: c.product, plotIds: [], date: new Date().toISOString().slice(0, 10), steps: c.steps.map(name => ({ name, out: '' })), note: '' }; };
  const [r, setR] = useState<ProcessRun>(item ?? blank(reg.crops[0]?.name ?? ''));
  const [err, setErr] = useState('');
  const step = (i: number, patch: Partial<ProcessRun['steps'][number]>) => { setR({ ...r, steps: r.steps.map((x, j) => (j === i ? { ...x, ...patch } : x)) }); setErr(''); };
  const save = () => {
    if (!(r.plotIds ?? []).length) return setErr('Choose at least one plot the produce came from.');
    if (!r.steps.some(s => s.out.trim())) return setErr('Fill in at least one step, e.g. "2,400 kg".');
    onSave({ ...r, chain: r.product || r.chain, steps: r.steps.filter(s => s.name.trim()) });
  };
  // Every plot can be chosen; the ones growing this crop come first.
  const matches = (p: Plot) => !r.crop || p.crop === r.crop || (p.crops ?? []).includes(r.crop);
  const plots = [...reg.plots].sort((a, b) => Number(matches(b)) - Number(matches(a)));
  const matching = plots.filter(matches).map(p => p.id);
  return (
    <Shell title={item ? 'Edit processing run' : 'New processing run'} onSave={save} onCancel={onCancel} onRemove={onRemove} err={err}>
      <div className="grid2">
        <Field label="Crop"><select className="input" value={r.crop ?? ''} onChange={e => setR(item ? { ...r, crop: e.target.value } : { ...blank(e.target.value), id: r.id, date: r.date })}>{!r.crop && <option value="">—</option>}{reg.crops.map(c => <option key={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Product"><input className="input" value={runProduct(r)} onChange={e => setR({ ...r, product: e.target.value })} /></Field>
      </div>
      <Field label="Date"><input className="input" type="date" value={r.date} onChange={e => setR({ ...r, date: e.target.value })} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
      <MultiPick label={`From plots (${(r.plotIds ?? []).length} chosen; ${r.crop || 'any crop'} plots first)`} items={plots.map(p => ({ id: p.id, label: p.code + (matches(p) ? '' : ' ·other crop') }))} value={r.plotIds ?? []} onChange={plotIds => { setR({ ...r, plotIds }); setErr(''); }} />
      {matching.length > 0 && <div className="grid2">
        <button className="btn plain sm" onClick={() => setR({ ...r, plotIds: [...new Set([...(r.plotIds ?? []), ...matching])] })}>Select all {r.crop || ''} plots</button>
        <button className="btn plain sm" onClick={() => setR({ ...r, plotIds: [] })}>Clear</button>
      </div>}
      <div className="section">Steps</div>
      {r.steps.map((s, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 6, alignItems: 'center' }}>
          <input className="input" style={{ minHeight: 40, fontSize: 13.5 }} value={s.name} aria-label={`Step ${i + 1} name`} onChange={e => step(i, { name: e.target.value })} />
          <input className="input" style={{ minHeight: 40, fontSize: 13.5 }} value={s.out} placeholder="amount, e.g. 390 kg" aria-label={`Step ${i + 1} amount`} onChange={e => step(i, { out: e.target.value })} />
          <button className="btn plain sm" aria-label={`Remove step ${i + 1}`} onClick={() => setR({ ...r, steps: r.steps.filter((_, j) => j !== i) })}>×</button>
        </div>
      ))}
      <button className="btn plain sm" onClick={() => setR({ ...r, steps: [...r.steps, { name: '', out: '' }] })}>+ Add step</button>
      <Field label="Notes"><input className="input" value={r.note} placeholder="yield, problems, machine used" onChange={e => setR({ ...r, note: e.target.value })} /></Field>
    </Shell>
  );
}
