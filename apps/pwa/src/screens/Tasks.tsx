import { useState } from 'react';
import { editAllowed, newId, removeAllowed } from '@abuk/core';
import { farmChange, useApp } from '../store';
import { Check, Field, Seg } from '../ui';
import { useTasks } from './common';

const ZONES = ['All', 'Ridge', 'Slope', 'Basin', 'Store', 'Shed'];
const day = (d = 0) => { const x = new Date(); x.setDate(x.getDate() + d); return x.toISOString().slice(0, 10); };
const when = (due: string) => (!due ? '' : due < day() ? `overdue since ${due}` : due === day() ? 'today' : `due ${due}`);

export function Tasks() {
  const s = useApp(), { items } = useTasks();
  const live = !!s.session && !s.session.demo;
  const can = live && editAllowed(s.session?.user.role ?? '');
  const [f, setF] = useState<'today' | 'week' | 'mine'>('today');
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ title: '', zone: 'All', due: day(), groupId: '', who: '' });
  const [err, setErr] = useState('');
  const group = s.session?.user.meta.match(/Group \d+/)?.[0] ?? '';
  const shown = items.filter(t => f === 'today' ? (!t.due || t.due <= day()) : f === 'week' ? !t.due || t.due <= day(7) : t.who === group || t.who === s.session?.user.name);

  const add = () => {
    if (!form.title.trim()) return setErr('Say what has to be done.');
    if (form.due < day()) return setErr('The due date cannot be in the past.');
    const g = s.farm.groups.find(x => x.id === form.groupId);
    farmChange({ op: 'upsert', kind: 'task', item: { id: newId('tk'), title: form.title.trim(), zone: form.zone, who: g?.name ?? (form.who.trim() || 'anyone'), ...(g ? { groupId: g.id } : {}), due: form.due, done: false, by: s.session?.user.name ?? '', at: new Date().toISOString() } });
    setForm({ title: '', zone: 'All', due: day(), groupId: '', who: '' }); setAdding(false); setErr('');
  };

  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <Seg items={[['today', 'Today'], ['week', 'This week'], ['mine', group || 'Mine']]} value={f} onPick={setF} />
      {can && !adding && <button className="btn plain" onClick={() => setAdding(true)}>+ Add a task</button>}
      {adding && (
        <div className="box col g8" style={{ padding: 12 }}>
          <Field label="What has to be done"><input className="input" value={form.title} onChange={e => { setForm({ ...form, title: e.target.value }); setErr(''); }} /></Field>
          <div className="grid2">
            <Field label="Zone or place"><select className="input" value={form.zone} onChange={e => setForm({ ...form, zone: e.target.value })}>{ZONES.map(z => <option key={z}>{z}</option>)}</select></Field>
            <Field label="Due"><input className="input" type="date" min={day()} value={form.due} onChange={e => setForm({ ...form, due: e.target.value })} style={{ fontSize: 14, padding: '0 8px' }} /></Field>
          </div>
          <Field label="For group"><select className="input" value={form.groupId} onChange={e => setForm({ ...form, groupId: e.target.value })}><option value="">Anyone</option>{s.farm.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
          {!form.groupId && <Field label="Or a person's name (optional)"><input className="input" value={form.who} onChange={e => setForm({ ...form, who: e.target.value })} /></Field>}
          {err && <div className="msg">{err}</div>}
          <div className="grid2"><button className="btn plain" onClick={() => { setAdding(false); setErr(''); }}>Cancel</button><button className="btn" onClick={add}>Save task</button></div>
        </div>
      )}
      <div>
        {shown.map(t => (
          <div key={t.key} className="rowg" style={{ alignItems: 'center' }}>
            <button className="row" style={{ padding: '12px 0', minHeight: 48, flex: 1 }} onClick={t.tick}>
              <Check on={t.done} size={22} />
              <span style={{ flex: 1 }}><span style={{ display: 'block', fontSize: 14, lineHeight: 1.35, textDecoration: t.done ? 'line-through' : 'none' }}>{t.title}</span><span className="sub">{t.zone} · {t.who}{t.due ? ` · ${when(t.due)}` : ''}{t.auto ? ` · automatic: ${t.why}` : ''}</span></span>
            </button>
            {t.reg && removeAllowed(s.session?.user.role ?? '') && <button className="btn plain sm" aria-label={`Remove ${t.title}`} onClick={() => farmChange({ op: 'remove', kind: 'task', id: t.reg!.id })}>×</button>}
          </div>
        ))}
        {!shown.length && <div className="note" style={{ padding: '10px 0' }}>Nothing here.</div>}
      </div>
      <p className="note">{live
        ? 'Tasks are shared: a group lead or admin adds them, anyone can tick them, and they reach every phone and the Drive sheet (register_tasks) when there is signal. Tasks marked automatic appear when nothing has been recorded for a while (gauge reading, water depth, crop check) and disappear once you record it; tap one to open the form.'
        : 'Sample tasks for the demo. Sign in to use your project\'s shared task list.'}</p>
    </div>
  );
}
