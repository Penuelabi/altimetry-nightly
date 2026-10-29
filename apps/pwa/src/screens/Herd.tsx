import { useState } from 'react';
import {
  adminLabel, editAllowed, herdCount, herdLabel, newId, personById, personName, productToStore, seedStore,
  FISH_EVENTS, FISH_PROCESSED, FISH_SPECIES, FOREST_PRODUCTS, LIVESTOCK_EVENTS, LIVESTOCK_SPECIES,
  type AdminLoc, type FarmOp, type FishEventKind, type FishLog, type FishProcessed, type FishSpecies,
  type ForestLog, type ForestProduct, type Herd as HerdT, type LivestockEvent, type LivestockEventKind, type LivestockSpecies
} from '@abuk/core';
import { farmChange, useApp } from '../store';
import { usePlace } from '../net';
import { AdminPicker, GroupMember, PersonSelect, StoreForSale, noSale, nowLocal, useHereAdmin, type SaleChoice } from '../pickers';
import { Field, Seg } from '../ui';

// Livestock, forest products and fish: a herd/pond register living in the same shared farm
// register as plots and the seed store, so it works offline and syncs the same way.
const fmt = (d: string) => new Date(d.length === 10 ? d + 'T12:00:00' : d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' });
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const unitFor = (k: LivestockEventKind) => (k === 'milk' ? 'litres' : k === 'eggs' ? 'count' : 'head');
// The date and time on the form are one local date-time field.
const split = (at: string) => ({ date: at.slice(0, 10), time: at.slice(11, 16) });
const badAt = (at: string) => { const t = Date.parse(at); return isNaN(t) ? 'Enter the date and time.' : t > Date.now() + 300_000 ? 'The date and time must not be in the future.' : ''; };
const noAdmin = (a: AdminLoc) => (!a.state || !a.county || !a.payam ? 'Choose the state, county and payam.' : '');
// Livestock events that can put something into the store for sale (animals added, milk, eggs).
const SELLABLE: LivestockEventKind[] = ['opening', 'birth', 'purchase', 'milk', 'eggs'];

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
  const who = (groupId?: string, memberId?: string) => [memberId && personName(personById(s.farm, memberId)), groupId && s.farm.groups.find(g => g.id === groupId)?.name].filter(Boolean).join(' · ');

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
                {(h.admin || h.groupId) && <div className="sub">{[h.admin && adminLabel(h.admin), h.groupId && s.farm.groups.find(g => g.id === h.groupId)?.name].filter(Boolean).join(' · ')}</div>}
                <div className="between" style={{ alignItems: 'center' }}>
                  <span className="sub">{last ? `last: ${last.kind} ${fmt(last.date)}${last.time ? ` ${last.time}` : ''}` : 'no events yet'}</span>
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
              <span><span style={{ display: 'block', fontSize: 13.5 }}>{cap(l.product)}{who(l.groupId, l.memberId) ? ` · ${who(l.groupId, l.memberId)}` : ''}</span><span className="sub num">{fmt(l.date)}{l.time ? ` ${l.time}` : ''} · {l.by}{l.admin ? ` · ${adminLabel(l.admin)}` : ''}{l.storeMoveId ? ' · in store' : ''}{l.note ? ` · ${l.note}` : ''}</span></span>
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
              <span><span style={{ display: 'block', fontSize: 13.5 }}>{cap(l.species)} · {l.kind}{l.pond ? ` · ${l.pond}` : ''}{who(l.groupId, l.memberId) ? ` · ${who(l.groupId, l.memberId)}` : ''}</span><span className="sub num">{fmt(l.date)}{l.time ? ` ${l.time}` : ''} · {l.by}{l.admin ? ` · ${adminLabel(l.admin)}` : ''}{l.processed !== 'none' ? ` · ${l.processed}` : ''}{l.storeMoveId ? ' · in store' : ''}{l.note ? ` · ${l.note}` : ''}</span></span>
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

// Puts a product into the chosen store as an 'in' movement (creating the item the first time); returns the ops to send and the movement id.
function sale(reg: Parameters<typeof productToStore>[0], c: SaleChoice, name: string, unit: string, qty: number, by: string, date: string, note: string) {
  if (!c.on) return null;
  return productToStore(reg, { storeId: c.storeId || (reg.stores ?? seedStore().stores)[0]?.id, name, unit, qty, by, note, date, price: c.price ? Number(c.price) : null });
}

function HerdForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp(), here = useHereAdmin();
  const [f, setF] = useState<{ species: LivestockSpecies; ownerType: 'member' | 'group'; groupId: string; personId: string; admin: AdminLoc }>({ species: 'goat', ownerType: 'group', groupId: s.farm.groups[0]?.id ?? '', personId: '', admin: here });
  const [err, setErr] = useState('');
  const save = () => {
    const bad = noAdmin(f.admin);
    if (bad) return setErr(bad);
    if (!f.groupId) return setErr('Choose the group.');
    const p = personById(s.farm, f.personId), g = s.farm.groups.find(x => x.id === f.groupId);
    if (f.ownerType === 'member' && !p) return setErr('Choose the member who owns the herd.');
    const h: HerdT = { id: newId('hd'), species: f.species, ownerType: f.ownerType, ownerId: f.ownerType === 'group' ? f.groupId : f.personId, ownerName: f.ownerType === 'group' ? g?.name ?? '' : personName(p), admin: f.admin, groupId: f.groupId };
    farmChange({ op: 'upsert', kind: 'herd', item: h });
    onSaved(`${herdLabel(h)} added. Record an opening count to start the head count.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New herd</h2>
      <Field label="Species"><select className="input" value={f.species} onChange={e => setF({ ...f, species: e.target.value as LivestockSpecies })}>{LIVESTOCK_SPECIES.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      <AdminPicker value={f.admin} onChange={admin => { setF({ ...f, admin }); setErr(''); }} label="Where the herd is kept" />
      <Seg items={[['group', 'Owned by the group'], ['member', 'Owned by a member']]} value={f.ownerType} onPick={v => setF({ ...f, ownerType: v as 'member' | 'group', personId: '' })} fontSize={12} />
      <GroupMember groupId={f.groupId} personId={f.ownerType === 'member' ? f.personId : ''} onChange={(groupId, personId) => { setF({ ...f, groupId, personId }); setErr(''); }} />
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Add herd" />
    </div>
  );
}

function EventForm({ herd, onCancel, onSaved }: { herd: HerdT; onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp(), here = useHereAdmin();
  const [f, setF] = useState({ kind: 'opening' as LivestockEventKind, at: nowLocal(), qty: '', note: '', admin: herd.admin ?? here, memberId: '' });
  const [sell, setSell] = useState<SaleChoice>(noSale());
  const [err, setErr] = useState('');
  const save = () => {
    const qty = Number(f.qty);
    if (!(qty > 0)) return setErr('Enter a quantity above 0.');
    const bad = badAt(f.at) || noAdmin(f.admin);
    if (bad) return setErr(bad);
    const { date, time } = split(f.at), by = s.session?.user.id ?? '';
    const name = f.kind === 'milk' ? `${cap(herd.species)} milk` : f.kind === 'eggs' ? `${cap(herd.species)} eggs` : `${cap(herd.species)} (live)`;
    const sold = SELLABLE.includes(f.kind) ? sale(s.farm, sell, name, unitFor(f.kind) === 'head' ? 'head' : unitFor(f.kind), qty, by, date, `${herdLabel(herd)} · ${f.kind}`) : null;
    const ev: LivestockEvent = { id: newId('lv'), herdId: herd.id, kind: f.kind, date, time, qty, note: f.note.trim(), by, ...(sold ? { storeMoveId: sold.moveId } : {}) };
    const ops: FarmOp[] = [...(sold?.ops ?? []), { op: 'upsert', kind: 'livestockEvent', item: ev }];
    farmChange(...ops);
    onSaved(`${cap(f.kind)} recorded for ${herdLabel(herd)}: ${qty} ${unitFor(f.kind)}${sold ? `, and put in the store for sale as ${name}` : ''}.`);
  };
  const canSell = SELLABLE.includes(f.kind);
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">{herdLabel(herd)}</h2>
      <Field label="Event"><select className="input" value={f.kind} onChange={e => setF({ ...f, kind: e.target.value as LivestockEventKind })}>{LIVESTOCK_EVENTS.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      <div className="grid2">
        <Field label="Date and time"><input className="input" type="datetime-local" value={f.at} max={nowLocal()} onChange={e => setF({ ...f, at: e.target.value })} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
        <Field label={`Quantity (${unitFor(f.kind)})`}><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} /></Field>
      </div>
      <AdminPicker value={f.admin} onChange={admin => setF({ ...f, admin })} label="Where" />
      {herd.groupId && <div className="sub">Group: {s.farm.groups.find(g => g.id === herd.groupId)?.name ?? ''}{herd.ownerType === 'member' ? ` · owner ${herd.ownerName}` : ''}</div>}
      {canSell && <StoreForSale value={sell} onChange={setSell} what={f.kind === 'milk' ? 'this milk' : f.kind === 'eggs' ? 'these eggs' : 'these animals'} />}
      <Field label="Note"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Save" />
    </div>
  );
}

function ForestForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp(), place = usePlace(), here = useHereAdmin();
  const [f, setF] = useState({ product: 'honey' as ForestProduct, at: nowLocal(), qty: '', unit: 'kg', note: '', admin: here, groupId: '', personId: '' });
  const [sell, setSell] = useState<SaleChoice>(noSale());
  const [err, setErr] = useState('');
  const save = () => {
    const qty = Number(f.qty);
    if (!(qty > 0)) return setErr('Enter a quantity above 0.');
    const bad = badAt(f.at) || noAdmin(f.admin) || (f.groupId ? '' : 'Choose the group.');
    if (bad) return setErr(bad);
    const { date, time } = split(f.at), by = s.session?.user.id ?? '', unit = f.unit.trim() || 'kg';
    const sold = sale(s.farm, sell, cap(f.product), unit, qty, by, date, `forest collection · ${s.farm.groups.find(g => g.id === f.groupId)?.name ?? ''}`);
    const l: ForestLog = { id: newId('fl'), product: f.product, date, time, qty, unit, lat: place.gps ? place.lat : null, lon: place.gps ? place.lon : null, by, note: f.note.trim(), admin: f.admin, groupId: f.groupId, ...(f.personId ? { memberId: f.personId } : {}), ...(sold ? { storeMoveId: sold.moveId } : {}) };
    farmChange(...[...(sold?.ops ?? []), { op: 'upsert', kind: 'forestLog', item: l } as FarmOp]);
    onSaved(`${cap(f.product)} collection recorded: ${qty} ${unit}${sold ? ', and put in the store for sale' : ''}.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New collection</h2>
      <Field label="Product"><select className="input" value={f.product} onChange={e => setF({ ...f, product: e.target.value as ForestProduct })}>{FOREST_PRODUCTS.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      <div className="grid2">
        <Field label="Date and time"><input className="input" type="datetime-local" value={f.at} max={nowLocal()} onChange={e => setF({ ...f, at: e.target.value })} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
        <Field label="Quantity"><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} /></Field>
      </div>
      <Field label="Unit"><input className="input" value={f.unit} onChange={e => setF({ ...f, unit: e.target.value })} /></Field>
      <AdminPicker value={f.admin} onChange={admin => { setF({ ...f, admin }); setErr(''); }} label="Collected in" />
      <GroupMember groupId={f.groupId} personId={f.personId} onChange={(groupId, personId) => { setF({ ...f, groupId, personId }); setErr(''); }} />
      <div className="sub">{place.gps ? `GPS: ${place.lat.toFixed(3)}, ${place.lon.toFixed(3)}` : 'No GPS fix yet; saved without a location.'}</div>
      <StoreForSale value={sell} onChange={setSell} what={`this ${f.product}`} />
      <Field label="Note"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Save" />
    </div>
  );
}

function FishForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp(), here = useHereAdmin();
  const [f, setF] = useState({ species: 'tilapia' as FishSpecies, kind: 'catch' as FishEventKind, at: nowLocal(), weightKg: '', qty: '', processed: 'none' as FishProcessed, pond: '', note: '', admin: here, groupId: '', personId: '' });
  const [sell, setSell] = useState<SaleChoice>(noSale());
  const [err, setErr] = useState('');
  const save = () => {
    if (!f.weightKg && !f.qty) return setErr('Enter a weight or a count.');
    const bad = badAt(f.at) || noAdmin(f.admin) || (f.groupId ? '' : 'Choose the group.');
    if (bad) return setErr(bad);
    const { date, time } = split(f.at), by = s.session?.user.id ?? '';
    const name = `${cap(f.species)}${f.processed !== 'none' ? ` (${f.processed})` : ' (fresh)'}`;
    const sold = f.kind === 'stocking' ? null : sale(s.farm, sell, name, f.weightKg ? 'kg' : 'pcs', Number(f.weightKg || f.qty), by, date, `${f.kind} · ${s.farm.groups.find(g => g.id === f.groupId)?.name ?? ''}`);
    const l: FishLog = { id: newId('fh'), species: f.species, kind: f.kind, date, time, weightKg: f.weightKg ? Number(f.weightKg) : null, qty: f.qty ? Number(f.qty) : null, processed: f.processed, pond: f.pond.trim(), by, note: f.note.trim(), admin: f.admin, groupId: f.groupId, ...(f.personId ? { memberId: f.personId } : {}), ...(sold ? { storeMoveId: sold.moveId } : {}) };
    farmChange(...[...(sold?.ops ?? []), { op: 'upsert', kind: 'fishLog', item: l } as FarmOp]);
    onSaved(`${cap(f.species)} ${f.kind} recorded${sold ? `, and put in the store for sale as ${name}` : ''}.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New fish record</h2>
      <div className="grid2">
        <Field label="Species"><select className="input" value={f.species} onChange={e => setF({ ...f, species: e.target.value as FishSpecies })}>{FISH_SPECIES.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
        <Field label="Event"><select className="input" value={f.kind} onChange={e => setF({ ...f, kind: e.target.value as FishEventKind })}>{FISH_EVENTS.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      </div>
      <div className="grid2">
        <Field label="Date and time"><input className="input" type="datetime-local" value={f.at} max={nowLocal()} onChange={e => setF({ ...f, at: e.target.value })} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
        <Field label="Pond"><input className="input" value={f.pond} onChange={e => setF({ ...f, pond: e.target.value })} /></Field>
      </div>
      <AdminPicker value={f.admin} onChange={admin => { setF({ ...f, admin }); setErr(''); }} label="Where" />
      <GroupMember groupId={f.groupId} personId={f.personId} onChange={(groupId, personId) => { setF({ ...f, groupId, personId }); setErr(''); }} />
      <div className="grid2">
        <Field label="Weight (kg)"><input className="input num" type="number" inputMode="decimal" value={f.weightKg} onChange={e => setF({ ...f, weightKg: e.target.value })} /></Field>
        <Field label="Count"><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} /></Field>
      </div>
      <Field label="Processed"><select className="input" value={f.processed} onChange={e => setF({ ...f, processed: e.target.value as FishProcessed })}>{FISH_PROCESSED.map(k => <option key={k} value={k}>{cap(k)}</option>)}</select></Field>
      {f.kind !== 'stocking' && <StoreForSale value={sell} onChange={setSell} what="this fish" />}
      <Field label="Note"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Save" />
    </div>
  );
}
