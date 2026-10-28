import { useState } from 'react';
import { CONTAINER_TYPES, newId, type ContainerLog, type ContainerType, type ContainerUnit } from '@abuk/core';
import { farmChange, useApp } from '../store';
import { Field } from '../ui';

const ACTIONS = [
  { id: 'water' as const, label: 'Watering' },
  { id: 'fertilize' as const, label: 'Fertilize' },
  { id: 'pest-check' as const, label: 'Pest check' },
  { id: 'harvest' as const, label: 'Harvest' },
  { id: 'note' as const, label: 'Note' },
];

const VEGETABLES = ['Tomato', 'Okra', 'Kale', 'Spinach', 'Onion', 'Pepper', 'Eggplant', 'Amaranth', 'Jute mallow', 'Moringa leaf'];

export function Container() {
  const s = useApp();
  const units = s.farm.containers ?? [];
  const logs = s.farm.containerLogs ?? [];
  const [sel, setSel] = useState(units[0]?.id ?? '');
  const [addUnit, setAddUnit] = useState(false);
  const [addLog, setAddLog] = useState(false);
  const [uf, setUf] = useState({ code: '', type: 'sack' as ContainerType, crop: VEGETABLES[0], location: '', note: '' });
  const [lf, setLf] = useState({ action: 'water' as ContainerLog['action'], qty: '', unit: '', pest: '', note: '' });
  const [err, setErr] = useState('');

  const unit = units.find(u => u.id === sel);
  const history = logs.filter(l => l.unitId === sel).sort((a, b) => b.date.localeCompare(a.date));
  const totalHarvest = history.filter(l => l.action === 'harvest').reduce((s, l) => s + (l.qty ?? 0), 0);

  const saveUnit = () => {
    if (!uf.code.trim() || !uf.crop.trim()) return setErr('Enter a code and crop.');
    const u: ContainerUnit = { id: newId('ctn'), code: uf.code, type: uf.type, crop: uf.crop, plantedDate: new Date().toISOString().slice(0, 10), location: uf.location, ownerId: s.session?.user.id ?? '', ownerName: s.session?.user.name ?? '', note: uf.note };
    farmChange({ op: 'upsert', kind: 'container', item: u });
    setSel(u.id); setAddUnit(false); setErr('');
  };

  const saveLog = () => {
    if (!unit) return;
    const l: ContainerLog = { id: newId('cl'), unitId: unit.id, date: new Date().toISOString().slice(0, 10), action: lf.action, qty: lf.qty ? Number(lf.qty) : null, unit: lf.unit || (lf.action === 'harvest' ? 'g' : 'L'), pest: lf.pest, photo: '', by: s.session?.user.id ?? '', note: lf.note };
    farmChange({ op: 'upsert', kind: 'containerLog', item: l });
    setLf({ action: 'water', qty: '', unit: '', pest: '', note: '' }); setAddLog(false); setErr('');
  };

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>Track container and bag farming: register each unit, log watering, pest checks and harvests. Designed for the vegetable pilot to improve nutrition for fishing communities.</p>

      {units.length > 0 && (
        <Field label="Container">
          <select className="input" value={sel} onChange={e => setSel(e.target.value)}>
            {units.map(u => <option key={u.id} value={u.id}>{u.code} · {u.crop} ({u.type})</option>)}
          </select>
        </Field>
      )}

      {unit && (
        <div className="box" style={{ padding: '12px 14px' }}>
          <div className="between">
            <span><span className="kick sm" style={{ display: 'block' }}>{unit.code} · {unit.type}</span><span style={{ fontSize: 14 }}>{unit.crop}</span></span>
            <span style={{ textAlign: 'right' }}><span className="head num" style={{ display: 'block', fontSize: 24 }}>{totalHarvest > 0 ? `${totalHarvest} g` : '—'}</span><span className="it" style={{ fontSize: 11 }}>total harvest</span></span>
          </div>
          <div className="sub" style={{ marginTop: 4 }}>Planted {unit.plantedDate} · {unit.ownerName}{unit.location ? ` · ${unit.location}` : ''}</div>
        </div>
      )}

      {unit && !addLog && <button className="btn" onClick={() => setAddLog(true)}>+ Log activity</button>}

      {addLog && unit && (
        <div className="box col g10" style={{ padding: 14 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {ACTIONS.map(a => <button key={a.id} className={'chip' + (lf.action === a.id ? ' on' : '')} onClick={() => setLf({ ...lf, action: a.id })}>{lf.action === a.id ? '✓ ' : ''}{a.label}</button>)}
          </div>
          {(lf.action === 'water' || lf.action === 'fertilize' || lf.action === 'harvest') && (
            <Field label={lf.action === 'harvest' ? 'Amount (g)' : 'Amount (L)'}><input className="input num" type="number" inputMode="decimal" value={lf.qty} onChange={e => setLf({ ...lf, qty: e.target.value })} /></Field>
          )}
          {lf.action === 'pest-check' && <Field label="Pest or disease"><input className="input" value={lf.pest} placeholder="e.g. aphids, whitefly" onChange={e => setLf({ ...lf, pest: e.target.value })} /></Field>}
          <textarea className="input" rows={2} placeholder="Note (optional)" value={lf.note} onChange={e => setLf({ ...lf, note: e.target.value })} />
          {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}
          <div className="grid2">
            <button className="btn plain" onClick={() => { setAddLog(false); setErr(''); }}>Cancel</button>
            <button className="btn" onClick={saveLog}>Save</button>
          </div>
        </div>
      )}

      {unit && history.length > 0 && (
        <div>
          <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Activity log</h2>
          {history.map(l => (
            <div key={l.id} className="rowg">
              <span><span style={{ display: 'block', fontSize: 14 }}>{ACTIONS.find(a => a.id === l.action)?.label ?? l.action}</span><span className="sub">{l.date}{l.pest ? ` · ${l.pest}` : ''}{l.note ? ` · ${l.note}` : ''}</span></span>
              {l.qty != null && <span className="head num" style={{ fontSize: 18 }}>{l.qty} {l.unit}</span>}
            </div>
          ))}
        </div>
      )}

      {!addUnit && <button className="btn plain" onClick={() => setAddUnit(true)}>+ Register new container</button>}

      {addUnit && (
        <div className="box col g10" style={{ padding: 14 }}>
          <h2 className="h2 h20">New container</h2>
          <div className="grid2">
            <Field label="Code"><input className="input" value={uf.code} placeholder="e.g. S-01" onChange={e => { setUf({ ...uf, code: e.target.value }); setErr(''); }} /></Field>
            <Field label="Type">
              <select className="input" value={uf.type} onChange={e => setUf({ ...uf, type: e.target.value as ContainerType })}>
                {CONTAINER_TYPES.map(t => <option key={t}>{t}</option>)}
              </select>
            </Field>
          </div>
          <div className="grid2">
            <Field label="Crop">
              <select className="input" value={uf.crop} onChange={e => setUf({ ...uf, crop: e.target.value })}>
                {VEGETABLES.map(v => <option key={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Location"><input className="input" value={uf.location} placeholder="e.g. behind house" onChange={e => setUf({ ...uf, location: e.target.value })} /></Field>
          </div>
          {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}
          <div className="grid2">
            <button className="btn plain" onClick={() => { setAddUnit(false); setErr(''); }}>Cancel</button>
            <button className="btn" onClick={saveUnit}>Register</button>
          </div>
        </div>
      )}
    </div>
  );
}
