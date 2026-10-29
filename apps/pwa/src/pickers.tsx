// Shared form pieces: cascading admin level (state > county > payam > village), the person form,
// and pickers that choose from the registers instead of typing names again.
import { useState } from 'react';
import { adminLabel, blankPerson, countiesOf, newId, normPhone, payamsOf, personError, personName, statesList, type AdminLoc, type Person } from '@abuk/core';
import { farmChange, useApp } from './store';
import { usePlace } from './net';
import { Field } from './ui';

// The admin level of where the phone is now, to start a form on.
export function useHereAdmin(): AdminLoc {
  const p = usePlace();
  return { state: p.state, county: p.county, payam: p.payam, village: '' };
}

// State > County > Payam as linked drop-downs, then a village or town (suggestions come from people already registered there).
export function AdminPicker({ value, onChange, village = true, label }: { value: AdminLoc; onChange: (a: AdminLoc) => void; village?: boolean; label?: string }) {
  const s = useApp();
  const states = statesList(), counties = value.state ? countiesOf(value.state) : [], payams = value.state && value.county ? payamsOf(value.state, value.county) : [];
  const seen = new Set<string>();
  for (const p of s.farm.people ?? []) if (p.admin.payam === value.payam && p.admin.county === value.county && p.admin.village) seen.add(p.admin.village);
  const listId = `vil-${value.payam}`;
  return (
    <div className="col g8">
      {label && <div className="kick sm">{label}</div>}
      <div className="grid2">
        <Field label="State">
          <select className="input" value={value.state} onChange={e => onChange({ state: e.target.value, county: '', payam: '', village: '' })}>
            <option value="">Choose…</option>{states.map(x => <option key={x}>{x}</option>)}
          </select>
        </Field>
        <Field label="County">
          <select className="input" value={value.county} disabled={!value.state} onChange={e => onChange({ ...value, county: e.target.value, payam: '', village: '' })}>
            <option value="">Choose…</option>{counties.map(x => <option key={x}>{x}</option>)}
          </select>
        </Field>
      </div>
      <div className={village ? 'grid2' : undefined}>
        <Field label="Payam">
          <select className="input" value={value.payam} disabled={!value.county} onChange={e => onChange({ ...value, payam: e.target.value, village: '' })}>
            <option value="">Choose…</option>{payams.map(x => <option key={x}>{x}</option>)}
          </select>
        </Field>
        {village && (
          <Field label="Village / town">
            <input className="input" list={listId} value={value.village ?? ''} disabled={!value.payam} placeholder="type or pick" onChange={e => onChange({ ...value, village: e.target.value })} />
            <datalist id={listId}>{[...seen].map(v => <option key={v} value={v} />)}</datalist>
          </Field>
        )}
      </div>
    </div>
  );
}

// Every detail the project holds about one person: two names, two phones, where they live, two next of kin.
export function PersonFields({ value, onChange }: { value: Person; onChange: (p: Person) => void }) {
  const set = (patch: Partial<Person>) => onChange({ ...value, ...patch });
  const kin = (i: number, patch: Partial<Person['kin'][number]>) => set({ kin: value.kin.map((k, j) => (j === i ? { ...k, ...patch } : k)) });
  return (
    <div className="col g10">
      <div className="grid2">
        <Field label="First name"><input className="input" value={value.name} onChange={e => set({ name: e.target.value })} /></Field>
        <Field label="Second name"><input className="input" value={value.name2} onChange={e => set({ name2: e.target.value })} /></Field>
      </div>
      <div className="grid2">
        <Field label="Phone"><input className="input num" inputMode="tel" placeholder="+211 912 345 678" value={value.phone} onChange={e => set({ phone: e.target.value })} /></Field>
        <Field label="Second phone"><input className="input num" inputMode="tel" placeholder="optional" value={value.phone2} onChange={e => set({ phone2: e.target.value })} /></Field>
      </div>
      <AdminPicker value={value.admin} onChange={admin => set({ admin })} label="Lives in" />
      {value.kin.map((k, i) => (
        <div key={i} className="col g8" style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 8 }}>
          <div className="kick sm">Next of kin {i + 1}</div>
          <div className="grid2">
            <Field label="First name"><input className="input" value={k.name} onChange={e => kin(i, { name: e.target.value })} /></Field>
            <Field label="Second name"><input className="input" value={k.name2} onChange={e => kin(i, { name2: e.target.value })} /></Field>
          </div>
          <div className="grid2">
            <Field label="Relation"><input className="input" placeholder="wife, brother…" value={k.relation} onChange={e => kin(i, { relation: e.target.value })} /></Field>
            <Field label="Phone"><input className="input num" inputMode="tel" value={k.phone} onChange={e => kin(i, { phone: e.target.value })} /></Field>
          </div>
          <Field label="Village / town"><input className="input" value={k.village} onChange={e => kin(i, { village: e.target.value })} /></Field>
        </div>
      ))}
    </div>
  );
}

// A new person: the full form, saved to the shared register. onSaved gets the new person.
export function NewPerson({ onSaved, onCancel, initial }: { onSaved: (p: Person) => void; onCancel: () => void; initial?: Partial<Person> }) {
  const here = useHereAdmin();
  const [p, setP] = useState<Person>(() => ({ ...blankPerson(newId('per'), here), ...initial }));
  const [err, setErr] = useState('');
  const save = () => {
    const bad = personError(p);
    if (bad) return setErr(bad);
    const done: Person = { ...p, phone: normPhone(p.phone), phone2: normPhone(p.phone2), kin: p.kin.map(k => ({ ...k, phone: normPhone(k.phone) })) };
    farmChange({ op: 'upsert', kind: 'person', item: done });
    onSaved(done);
  };
  return (
    <div className="box col g10" style={{ padding: 12 }}>
      <h2 className="h2 h20">New person</h2>
      <PersonFields value={p} onChange={x => { setP(x); setErr(''); }} />
      {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}
      <div className="grid2"><button className="btn plain" onClick={onCancel}>Cancel</button><button className="btn" onClick={save}>Save person</button></div>
    </div>
  );
}

// Pick one person from the register (optionally limited to `only`), or add a new one on the spot.
export function PersonSelect({ value, onChange, only, label = 'Person', empty = 'Choose…' }: { value: string; onChange: (id: string) => void; only?: string[]; label?: string; empty?: string }) {
  const s = useApp();
  const [adding, setAdding] = useState(false);
  const list = (s.farm.people ?? []).filter(p => !only || only.includes(p.id));
  if (adding) return <NewPerson onCancel={() => setAdding(false)} onSaved={p => { onChange(p.id); setAdding(false); }} />;
  return (
    <Field label={label}>
      <select className="input" value={value} onChange={e => (e.target.value === '+new' ? setAdding(true) : onChange(e.target.value))}>
        <option value="">{empty}</option>
        {list.map(p => <option key={p.id} value={p.id}>{personName(p)} · {p.phone}</option>)}
        <option value="+new">+ New person…</option>
      </select>
    </Field>
  );
}

// Several choices at once, as tick chips.
export function MultiPick({ items, value, onChange, label }: { items: { id: string; label: string }[]; value: string[]; onChange: (v: string[]) => void; label?: string }) {
  return (
    <div className="col g6">
      {label && <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{label}</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {items.map(i => { const on = value.includes(i.id); return (
          <button key={i.id} type="button" className={'chip' + (on ? ' on' : '')} style={{ minHeight: 36, padding: '0 10px', fontSize: 12.5 }}
            onClick={() => onChange(on ? value.filter(x => x !== i.id) : [...value, i.id])}>{on ? '✓ ' : ''}{i.label}</button>
        ); })}
        {!items.length && <span className="sub">Nothing to choose from yet.</span>}
      </div>
    </div>
  );
}

export const placeText = adminLabel;
// Now, in the form a datetime-local input wants (local time).
export const nowLocal = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
