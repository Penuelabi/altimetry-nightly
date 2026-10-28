import { useState, type ReactNode } from 'react';
import { editAllowed, newId, removeAllowed, type Crop, type Group, type OilBatch, type Plot, type ProcessRun, type Register, type Zone } from '@abuk/core';
import { farmChange, useApp } from '../store';
import { useOnline } from '../net';
import { Chevron, Field, Seg } from '../ui';

type Tab = 'plots' | 'crops' | 'groups' | 'batches' | 'runs';
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
    tab === 'plots' ? reg.plots.map(p => ({ id: p.id, title: p.code, sub: `${p.zone} · ${p.crop}${p.areaHa ? ` · ${p.areaHa} ha` : ''} · ${groupName(reg, p.groupId) || p.holder || 'no group'}${p.boundary.length > 2 ? ' · mapped' : ''}` }))
    : tab === 'crops' ? reg.crops.map(c => ({ id: c.id, title: c.name, sub: '' }))
    : tab === 'groups' ? reg.groups.map(g => ({ id: g.id, title: g.name, sub: `${g.members.length} members${g.lead ? ` · lead ${g.lead}` : ''}` }))
    : tab === 'batches' ? reg.batches.map(b => ({ id: b.id, title: b.code, sub: `${b.bottles} × 1 L · plot ${reg.plots.find(p => p.id === b.plotId)?.code ?? '—'} · pressed ${b.pressed}` }))
    : reg.runs.map(r => ({ id: r.id, title: `${r.chain === 'balanites' ? 'Balanites oil' : 'Moringa powder'} · ${r.date}`, sub: r.steps.map(x => x.out).filter(Boolean).join(' → ') }));

  const form = (id: string) => {
    const isNew = id === 'new';
    const remove = !isNew && canDel ? () => { farmChange({ op: 'remove', kind: tab === 'plots' ? 'plot' : tab === 'crops' ? 'crop' : tab === 'groups' ? 'group' : tab === 'batches' ? 'batch' : 'run', id }); close(); } : undefined;
    if (tab === 'plots') return <PlotForm reg={reg} item={reg.plots.find(p => p.id === id)} onSave={p => { farmChange({ op: 'upsert', kind: 'plot', item: p }); close(); }} onCancel={close} onRemove={remove} />;
    if (tab === 'crops') return <CropForm item={reg.crops.find(c => c.id === id)} onSave={c => { farmChange({ op: 'upsert', kind: 'crop', item: c }); close(); }} onCancel={close} onRemove={remove} />;
    if (tab === 'groups') return <GroupForm item={reg.groups.find(g => g.id === id)} onSave={g => { farmChange({ op: 'upsert', kind: 'group', item: g }); close(); }} onCancel={close} onRemove={remove} />;
    if (tab === 'batches') return <BatchForm reg={reg} item={reg.batches.find(b => b.id === id)} onSave={b => { farmChange({ op: 'upsert', kind: 'batch', item: b }); close(); }} onCancel={close} onRemove={remove} />;
    return <RunForm item={reg.runs.find(r => r.id === id)} onSave={r => { farmChange({ op: 'upsert', kind: 'run', item: r }); close(); }} onCancel={close} onRemove={remove} />;
  };

  const LABEL: Record<Tab, string> = { plots: 'plot', crops: 'crop', groups: 'group', batches: 'bottle batch', runs: 'processing run' };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13 }}>The project's shared list of plots, crops, groups, oil batches and processing runs. Changes show on every phone after it syncs.{can ? '' : ' Only admins and group leads can change it.'}</p>
      <div style={{ overflowX: 'auto' }}>
        <Seg items={[['plots', 'Plots'], ['crops', 'Crops'], ['groups', 'Groups'], ['batches', 'Batches'], ['runs', 'Processing']]} value={tab} onPick={pick} fontSize={12} />
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
  const [p, setP] = useState<Plot>(item ?? { id: newId('plot'), code: '', zone: 'basin', crop: reg.crops[0]?.name ?? '', groupId: '', holder: '', areaHa: null, boundary: [], notes: '' });
  const [err, setErr] = useState('');
  const set = <K extends keyof Plot>(k: K, v: Plot[K]) => { setP({ ...p, [k]: v }); setErr(''); };
  const save = () => {
    if (!p.code.trim()) return setErr('Give the plot a code, e.g. B‑13.');
    if (reg.plots.some(x => x.code.trim().toLowerCase() === p.code.trim().toLowerCase() && x.id !== p.id)) return setErr('Another plot already has that code.');
    onSave({ ...p, code: p.code.trim() });
  };
  return (
    <Shell title={item ? `Edit plot ${item.code}` : 'New plot'} onSave={save} onCancel={onCancel} onRemove={onRemove} err={err}>
      <div className="grid2">
        <Field label="Plot code"><input className="input" value={p.code} placeholder="B‑13" onChange={e => set('code', e.target.value.toUpperCase())} /></Field>
        <Field label="Area (ha)"><input className="input num" type="number" inputMode="decimal" value={p.areaHa ?? ''} onChange={e => set('areaHa', e.target.value === '' ? null : Number(e.target.value))} /></Field>
      </div>
      <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Zone</div>
      <Seg items={ZONES} value={p.zone} onPick={z => set('zone', z)} />
      <Field label="Main crop"><select className="input" value={p.crop} onChange={e => set('crop', e.target.value)}>{reg.crops.map(c => <option key={c.id}>{c.name}</option>)}</select></Field>
      <div className="grid2">
        <Field label="Group"><select className="input" value={p.groupId} onChange={e => set('groupId', e.target.value)}><option value="">Individual</option>{reg.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
        <Field label="Holder (individual plots)"><input className="input" value={p.holder} disabled={!!p.groupId} onChange={e => set('holder', e.target.value)} /></Field>
      </div>
      <Field label="Notes"><input className="input" value={p.notes} onChange={e => set('notes', e.target.value)} /></Field>
      <div className="sub">{p.boundary.length > 2 ? `Boundary mapped: ${p.boundary.length} GPS points.` : 'To add a boundary, use Map → Walk boundary and save it to this plot.'}</div>
    </Shell>
  );
}

function CropForm({ item, onSave, onCancel, onRemove }: { item?: Crop; onSave: (c: Crop) => void; onCancel: () => void; onRemove?: () => void }) {
  const [name, setName] = useState(item?.name ?? '');
  const [err, setErr] = useState('');
  return (
    <Shell title={item ? `Edit ${item.name}` : 'New crop'} onSave={() => (name.trim() ? onSave({ id: item?.id ?? newId('crop'), name: name.trim() }) : setErr('Enter the crop name.'))} onCancel={onCancel} onRemove={onRemove} err={err}>
      <Field label="Crop name"><input className="input" value={name} placeholder="e.g. Pumpkin" onChange={e => { setName(e.target.value); setErr(''); }} /></Field>
    </Shell>
  );
}

function GroupForm({ item, onSave, onCancel, onRemove }: { item?: Group; onSave: (g: Group) => void; onCancel: () => void; onRemove?: () => void }) {
  const [g, setG] = useState<Group>(item ?? { id: newId('group'), name: '', lead: '', members: [] });
  const [who, setWho] = useState('');
  const [err, setErr] = useState('');
  const add = () => { if (!who.trim()) return; setG({ ...g, members: [...g.members, { id: newId('m'), name: who.trim(), workDays: 0 }] }); setWho(''); };
  return (
    <Shell title={item ? `Edit ${item.name}` : 'New group'} onSave={() => (g.name.trim() ? onSave({ ...g, name: g.name.trim() }) : setErr('Enter the group name.'))} onCancel={onCancel} onRemove={onRemove} err={err}>
      <div className="grid2">
        <Field label="Group name"><input className="input" value={g.name} placeholder="Group 7" onChange={e => { setG({ ...g, name: e.target.value }); setErr(''); }} /></Field>
        <Field label="Group lead"><input className="input" value={g.lead} onChange={e => setG({ ...g, lead: e.target.value })} /></Field>
      </div>
      <div className="section">Members · {g.members.length}</div>
      {g.members.map(m => (
        <div key={m.id} className="rowg" style={{ alignItems: 'center', padding: '6px 0' }}>
          <input className="input" style={{ minHeight: 36, fontSize: 14 }} value={m.name} onChange={e => setG({ ...g, members: g.members.map(x => x.id === m.id ? { ...x, name: e.target.value } : x) })} />
          <button className="btn plain sm" onClick={() => setG({ ...g, members: g.members.filter(x => x.id !== m.id) })} aria-label={`Remove ${m.name}`}>Remove</button>
        </div>
      ))}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8 }}>
        <input className="input" style={{ minHeight: 40 }} value={who} placeholder="New member's name" onChange={e => setWho(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()} />
        <button className="btn md" style={{ padding: '0 12px' }} onClick={add}>Add</button>
      </div>
    </Shell>
  );
}

function BatchForm({ reg, item, onSave, onCancel, onRemove }: { reg: Register; item?: OilBatch; onSave: (b: OilBatch) => void; onCancel: () => void; onRemove?: () => void }) {
  const yy = new Date().getFullYear() % 100;
  const nextCode = `BAL‑${yy}‑${String(reg.batches.filter(b => b.code.includes(`‑${yy}‑`)).length + 1).padStart(2, '0')}`;
  const [b, setB] = useState<OilBatch>(item ?? { id: newId('batch'), code: nextCode, plotId: reg.plots.find(p => p.zone === 'basin')?.id ?? '', fruit: '', pressed: new Date().toISOString().slice(0, 10), bottles: 0, place: '' });
  const [err, setErr] = useState('');
  const set = <K extends keyof OilBatch>(k: K, v: OilBatch[K]) => { setB({ ...b, [k]: v }); setErr(''); };
  const save = () => {
    if (!b.code.trim()) return setErr('Enter a batch code.');
    if (!(b.bottles > 0)) return setErr('Enter how many bottles were filled.');
    onSave(b);
  };
  return (
    <Shell title={item ? `Edit batch ${item.code}` : 'New bottle batch'} onSave={save} onCancel={onCancel} onRemove={onRemove} err={err}>
      <div className="grid2">
        <Field label="Batch code"><input className="input mono" value={b.code} onChange={e => set('code', e.target.value.toUpperCase())} /></Field>
        <Field label="Bottles (1 L)"><input className="input num" type="number" inputMode="numeric" value={b.bottles || ''} onChange={e => set('bottles', Number(e.target.value))} /></Field>
      </div>
      <Field label="From plot"><select className="input" value={b.plotId} onChange={e => set('plotId', e.target.value)}>{reg.plots.map(p => <option key={p.id} value={p.id}>{p.code}</option>)}</select></Field>
      <div className="grid2">
        <Field label="Fruit collected"><input className="input" value={b.fruit} placeholder="Jan–Feb 2027" onChange={e => set('fruit', e.target.value)} /></Field>
        <Field label="Pressed on"><input className="input" type="date" value={b.pressed} onChange={e => set('pressed', e.target.value)} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
      </div>
    </Shell>
  );
}

const CHAINS = {
  balanites: ['Fruit collected', 'De‑pulped & dried nuts', 'Cracked → kernels', 'Pressed', 'Refined & bottled'],
  moringa: ['Fresh leaves cut', 'Shade‑dried', 'Milled', 'Packed']
} as const;

function RunForm({ item, onSave, onCancel, onRemove }: { item?: ProcessRun; onSave: (r: ProcessRun) => void; onCancel: () => void; onRemove?: () => void }) {
  const blank = (chain: ProcessRun['chain']): ProcessRun => ({ id: newId('run'), chain, date: new Date().toISOString().slice(0, 10), steps: CHAINS[chain].map(name => ({ name, out: '' })), note: '' });
  const [r, setR] = useState<ProcessRun>(item ?? blank('balanites'));
  const [err, setErr] = useState('');
  const save = () => (r.steps.some(s => s.out.trim()) ? onSave(r) : setErr('Fill in at least one step, e.g. "2,400 kg".'));
  return (
    <Shell title={item ? 'Edit processing run' : 'New processing run'} onSave={save} onCancel={onCancel} onRemove={onRemove} err={err}>
      {!item && <Seg items={[['balanites', 'Balanites oil'], ['moringa', 'Moringa powder']]} value={r.chain} onPick={c => setR({ ...blank(c), id: r.id })} />}
      <Field label="Date"><input className="input" type="date" value={r.date} onChange={e => setR({ ...r, date: e.target.value })} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
      {r.steps.map((s, i) => (
        <Field key={s.name} label={s.name}><input className="input" value={s.out} placeholder="amount, e.g. 390 kg" onChange={e => { setR({ ...r, steps: r.steps.map((x, j) => (j === i ? { ...x, out: e.target.value } : x)) }); setErr(''); }} /></Field>
      ))}
      <Field label="Notes"><input className="input" value={r.note} placeholder="yield, problems, machine used" onChange={e => setR({ ...r, note: e.target.value })} /></Field>
    </Shell>
  );
}
