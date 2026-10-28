import { useState } from 'react';
import {
  editAllowed, herdCount, herdLabel, newId,
  FISH_EVENTS, FISH_PROCESSED, FISH_SPECIES, FOREST_PRODUCTS, LIVESTOCK_EVENTS, LIVESTOCK_SPECIES,
  type FishEventKind, type FishLog, type FishProcessed, type FishSpecies,
  type ForestLog, type ForestProduct, type Herd as HerdT, type LivestockEvent, type LivestockEventKind, type LivestockSpecies
} from '@abuk/core';
import { farmChange, useApp } from '../store';
import { usePlace } from '../net';
import { Field, Seg } from '../ui';

// Livestock, forest products and fish: a herd/pond register living in the same shared farm
// register as plots and the seed store, so it works offline and syncs the same way.
const today = () => new Date().toISOString().slice(0, 10);
const fmt = (d: string) => new Date(d.length === 10 ? d + 'T12:00:00' : d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' });
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const unitFor = (k: LivestockEventKind) => (k === 'milk' ? 'litres' : k === 'eggs' ? 'count' : 'head');

type Form =
  | { kind: 'herd' } | { kind: 'event'; herdId: string }
  | { kind: 'forest' } | { kind: 'fish' };

export function Herd() {
  const s = useApp();
  const [tab, setTab] = useState<'livestock' | 'forest' | 'fish'>('livestock');
  const [form, setForm] = useState<Form | null>(null);
  const [msg, setMsg] = useState('');
  const can = editAllowed(s.session?.user.role ?? '');
  const herds = s.farm.herds ?? [], events = s.farm.livestockEvents ?? [], forestLogs = s.farm.forestLogs ?? [], fishLogs = s.farm.fishLogs ?? [];
  const done = (m: string) => { setForm(null); setMsg(m); };

  if (form?.kind === 'herd') return <HerdForm onCancel={() => setForm(null)} onSaved={done} />;
  if (form?.kind === 'event') return <EventForm herd={herds.find(h => h.id === form.herdId)!} onCancel={() => setForm(null)} onSaved={done} />;
  if (form?.kind === 'forest') return <ForestForm onCancel={() => setForm(null)} onSaved={done} />;
  if (form?.kind === 'fish') return <FishForm onCancel={() => setForm(null)} onSaved={done} />;

  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <Seg items={[['livestock', 'Livestock'], ['forest', 'Forest'], ['fish', 'Fish']]} value={tab} onPick={v => { setTab(v as typeof tab); setMsg(''); }} fontSize={12.5} />
      {msg && <div className="msg">{msg}</div>}

      {tab === 'livestock' && <>
        <div style={{ borderTop: '1px solid var(--color-divider)' }}>
          {herds.map(h => {
            const n = herdCount(s.farm, h.id);
            const last = events.filter(e => e.herdId === h.id).sort((a, b) => b.date.localeCompare(a.date))[0];
            return (
              <div key={h.id} className="col" style={{ padding: '10px 0', borderBottom: '1px solid var(--color-divider)', gap: 5 }}>
                <div className="between"><span style={{ fontSize: 14 }}>{herdLabel(h)}</span><span className="head num" style={{ fontSize: 19 }}>{n}</span></div>
                <div className="between" style={{ alignItems: 'center' }}>
                  <span className="sub">{last ? `last: ${last.kind} ${fmt(last.date)}` : 'no events yet'}</span>
                  <button className="btn plain" style={{ minHeight: 30, padding: '0 10px', fontSize: 12 }} onClick={() => setForm({ kind: 'event', herdId: h.id })}>+ Record</button>
                </div>
              </div>
            );
          })}
          {!herds.length && <div className="note" style={{ padding: '8px 0' }}>No herds yet.</div>}
        </div>
        {can && <button className="btn plain" onClick={() => setForm({ kind: 'herd' })}>+ New herd</button>}
      </>}

      {tab === 'forest' && <>
        <button className="btn" onClick={() => setForm({ kind: 'forest' })}>+ New collection</button>
        <div style={{ borderTop: '1px solid var(--color-divider)' }}>
          {[...forestLogs].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 60).map(l => (
            <div key={l.id} className="rowg" style={{ padding: '8px 0' }}>
              <span><span style={{ display: 'block', fontSize: 13.5 }}>{cap(l.product)}</span><span className="sub num">{fmt(l.date)} · {l.by}{l.lat != null ? ` · ${l.lat.toFixed(3)}, ${l.lon!.toFixed(3)}` : ''}{l.note ? ` · ${l.note}` : ''}</span></span>
              <span className="num" style={{ fontSize: 14 }}>{l.qty.toLocaleString('en')} {l.unit}</span>
            </div>
          ))}
          {!forestLogs.length && <div className="note" style={{ padding: '8px 0' }}>No collections recorded yet.</div>}
        </div>
      </>}

      {tab === 'fish' && <>
        <button className="btn" onClick={() => setForm({ kind: 'fish' })}>+ New record</button>
        <div style={{ borderTop: '1px solid var(--color-divider)' }}>
          {[...fishLogs].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 60).map(l => (
            <div key={l.id} className="rowg" style={{ padding: '8px 0' }}>
              <span><span style={{ display: 'block', fontSize: 13.5 }}>{cap(l.species)} · {l.kind}{l.pond ? ` · ${l.pond}` : ''}</span><span className="sub num">{fmt(l.date)} · {l.by}{l.processed !== 'none' ? ` · ${l.processed}` : ''}{l.note ? ` · ${l.note}` : ''}</span></span>
              <span className="num" style={{ fontSize: 14 }}>{l.weightKg != null ? `${l.weightKg} kg` : l.qty != null ? `${l.qty}` : '—'}</span>
            </div>
          ))}
          {!fishLogs.length && <div className="note" style={{ padding: '8px 0' }}>No catch or pond records yet.</div>}
        </div>
      </>}
    </div>
  );
}

const Buttons = ({ onCancel, onSave, label }: { onCancel: () => void; onSave: () => void; label: string }) => (
  <div className="grid2" style={{ gap: 8 }}><button className="btn plain" onClick={onCancel}>Cancel</button><button className="btn" onClick={onSave}>{label}</button></div>
);

function HerdForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp();
  const groups = s.farm.groups.filter(g => g.name);
  const [f, setF] = useState<{ species: LivestockSpecies; ownerType: 'member' | 'group'; ownerId: string; ownerName: string }>({ species: 'goat', ownerType: 'group', ownerId: groups[0]?.id ?? '', ownerName: groups[0]?.name ?? '' });
  const [err, setErr] = useState('');
  const members = groups.flatMap(g => g.members);
  const save = () => {
    if (!f.ownerId || !f.ownerName.trim()) return setErr('Choose an owner or group.');
    const h: HerdT = { id: newId('hd'), species: f.species, ownerType: f.ownerType, ownerId: f.ownerId, ownerName: f.ownerName.trim() };
    farmChange({ op: 'upsert', kind: 'herd', item: h });
    onSaved(`${herdLabel(h)} added. Record an opening count to start the head count.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New herd</h2>
      <Field label="Species"><select className="input" value={f.species} onChange={e => setF({ ...f, species: e.target.value as LivestockSpecies })}>{LIVESTOCK_SPECIES.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      <Seg items={[['group', 'Group'], ['member', 'Member']]} value={f.ownerType} onPick={v => setF({ ...f, ownerType: v as 'member' | 'group', ownerId: '', ownerName: '' })} />
      {f.ownerType === 'group'
        ? <Field label="Group"><select className="input" value={f.ownerId} onChange={e => { const g = groups.find(x => x.id === e.target.value); setF({ ...f, ownerId: e.target.value, ownerName: g?.name ?? '' }); }}>{groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
        : <Field label="Member"><select className="input" value={f.ownerId} onChange={e => { const m = members.find(x => x.id === e.target.value); setF({ ...f, ownerId: e.target.value, ownerName: m?.name ?? '' }); }}><option value="">Choose…</option>{members.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>}
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Add herd" />
    </div>
  );
}

function EventForm({ herd, onCancel, onSaved }: { herd: HerdT; onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp();
  const [f, setF] = useState({ kind: 'opening' as LivestockEventKind, date: today(), qty: '', note: '' });
  const [err, setErr] = useState('');
  const save = () => {
    const qty = Number(f.qty);
    if (!(qty > 0)) return setErr('Enter a quantity above 0.');
    const ev: LivestockEvent = { id: newId('lv'), herdId: herd.id, kind: f.kind, date: f.date, qty, note: f.note.trim(), by: s.session?.user.id ?? '' };
    farmChange({ op: 'upsert', kind: 'livestockEvent', item: ev });
    onSaved(`${cap(f.kind)} recorded for ${herdLabel(herd)}: ${qty} ${unitFor(f.kind)}.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">{herdLabel(herd)}</h2>
      <Field label="Event"><select className="input" value={f.kind} onChange={e => setF({ ...f, kind: e.target.value as LivestockEventKind })}>{LIVESTOCK_EVENTS.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      <div className="grid2">
        <Field label="Date"><input className="input" type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} /></Field>
        <Field label={`Quantity (${unitFor(f.kind)})`}><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} /></Field>
      </div>
      <Field label="Note"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Save" />
    </div>
  );
}

function ForestForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp(), place = usePlace();
  const [f, setF] = useState({ product: 'honey' as ForestProduct, date: today(), qty: '', unit: 'kg', note: '' });
  const [err, setErr] = useState('');
  const save = () => {
    const qty = Number(f.qty);
    if (!(qty > 0)) return setErr('Enter a quantity above 0.');
    const l: ForestLog = { id: newId('fl'), product: f.product, date: f.date, qty, unit: f.unit.trim() || 'kg', lat: place.gps ? place.lat : null, lon: place.gps ? place.lon : null, by: s.session?.user.id ?? '', note: f.note.trim() };
    farmChange({ op: 'upsert', kind: 'forestLog', item: l });
    onSaved(`${cap(f.product)} collection recorded: ${qty} ${l.unit}.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New collection</h2>
      <Field label="Product"><select className="input" value={f.product} onChange={e => setF({ ...f, product: e.target.value as ForestProduct })}>{FOREST_PRODUCTS.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      <div className="grid2">
        <Field label="Date"><input className="input" type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} /></Field>
        <Field label="Quantity"><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} /></Field>
      </div>
      <Field label="Unit"><input className="input" value={f.unit} onChange={e => setF({ ...f, unit: e.target.value })} /></Field>
      <div className="sub">{place.gps ? `From here: ${place.lat.toFixed(3)}, ${place.lon.toFixed(3)}` : 'No GPS fix yet; saved without a location.'}</div>
      <Field label="Note"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Save" />
    </div>
  );
}

function FishForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp();
  const [f, setF] = useState({ species: 'tilapia' as FishSpecies, kind: 'catch' as FishEventKind, date: today(), weightKg: '', qty: '', processed: 'none' as FishProcessed, pond: '', note: '' });
  const [err, setErr] = useState('');
  const save = () => {
    if (!f.weightKg && !f.qty) return setErr('Enter a weight or a count.');
    const l: FishLog = { id: newId('fh'), species: f.species, kind: f.kind, date: f.date, weightKg: f.weightKg ? Number(f.weightKg) : null, qty: f.qty ? Number(f.qty) : null, processed: f.processed, pond: f.pond.trim(), by: s.session?.user.id ?? '', note: f.note.trim() };
    farmChange({ op: 'upsert', kind: 'fishLog', item: l });
    onSaved(`${cap(f.species)} ${f.kind} recorded.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New fish record</h2>
      <div className="grid2">
        <Field label="Species"><select className="input" value={f.species} onChange={e => setF({ ...f, species: e.target.value as FishSpecies })}>{FISH_SPECIES.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
        <Field label="Event"><select className="input" value={f.kind} onChange={e => setF({ ...f, kind: e.target.value as FishEventKind })}>{FISH_EVENTS.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      </div>
      <div className="grid2">
        <Field label="Date"><input className="input" type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} /></Field>
        <Field label="Pond"><input className="input" value={f.pond} onChange={e => setF({ ...f, pond: e.target.value })} /></Field>
      </div>
      <div className="grid2">
        <Field label="Weight (kg)"><input className="input num" type="number" inputMode="decimal" value={f.weightKg} onChange={e => setF({ ...f, weightKg: e.target.value })} /></Field>
        <Field label="Count"><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} /></Field>
      </div>
      <Field label="Processed"><select className="input" value={f.processed} onChange={e => setF({ ...f, processed: e.target.value as FishProcessed })}>{FISH_PROCESSED.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      <Field label="Note"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Save" />
    </div>
  );
}
