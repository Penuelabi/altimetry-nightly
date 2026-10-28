import { useState } from 'react';
import { VSLA_TX_TYPES, newId, vslaBalance, type VslaGroup, type VslaTx, type VslaTxType } from '@abuk/core';
import { farmChange, useApp } from '../store';
import { Field } from '../ui';

const TX_LABELS: Record<VslaTxType, string> = { savings: 'Savings deposit', loan: 'Loan taken', repayment: 'Loan repayment', interest: 'Interest earned', fine: 'Fine', 'social-fund': 'Social fund', 'share-out': 'Share-out' };

export function Vsla() {
  const s = useApp();
  const groups = s.farm.vslaGroups ?? [];
  const txs = s.farm.vslaTxs ?? [];
  const [sel, setSel] = useState(groups[0]?.id ?? '');
  const [adding, setAdding] = useState(false);
  const [newGroup, setNewGroup] = useState(false);
  const [form, setForm] = useState({ type: 'savings' as VslaTxType, memberName: '', amount: '', note: '' });
  const [gf, setGf] = useState({ name: '', cycle: '2026-S1', members: '', meetDay: 'Monday', shareValue: '', currency: 'SSP' });
  const [err, setErr] = useState('');

  const grp = groups.find(g => g.id === sel);
  const bal = grp ? vslaBalance(s.farm, grp.id) : 0;
  const history = txs.filter(t => t.vslaId === sel).sort((a, b) => b.date.localeCompare(a.date));

  const saveGroup = () => {
    if (!gf.name.trim() || !gf.members || Number(gf.shareValue) <= 0) return setErr('Enter a name, member count and share value.');
    const g: VslaGroup = { id: newId('vsla'), name: gf.name, cycle: gf.cycle, members: Number(gf.members), meetDay: gf.meetDay, shareValue: Number(gf.shareValue), currency: gf.currency };
    farmChange({ op: 'upsert', kind: 'vslaGroup', item: g });
    setSel(g.id); setNewGroup(false); setErr('');
  };

  const saveTx = () => {
    if (!form.memberName.trim() || Number(form.amount) <= 0) return setErr('Enter a member name and amount.');
    if (!grp) return;
    const tx: VslaTx = { id: newId('vtx'), vslaId: grp.id, date: new Date().toISOString().slice(0, 10), type: form.type, memberId: '', memberName: form.memberName, amount: Number(form.amount), balance: 0, by: s.session?.user.id ?? '', note: form.note };
    farmChange({ op: 'upsert', kind: 'vslaTx', item: tx });
    setForm({ ...form, amount: '', note: '' }); setAdding(false); setErr('');
  };

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>Track savings deposits, loans, repayments and share-outs. Each transaction builds the evidence trail for microfinance and insurance eligibility.</p>

      {groups.length > 0 && (
        <Field label="VSLA group">
          <select className="input" value={sel} onChange={e => setSel(e.target.value)}>
            {groups.map(g => <option key={g.id} value={g.id}>{g.name} · {g.cycle}</option>)}
          </select>
        </Field>
      )}

      {grp && (
        <div className="box" style={{ padding: '12px 14px' }}>
          <div className="between"><span className="kick sm">Fund balance</span><span className="head num" style={{ fontSize: 28 }}>{bal.toLocaleString('en')} {grp.currency}</span></div>
          <div className="grid2" style={{ fontSize: 12.5, color: 'var(--color-neutral-700)', marginTop: 6 }}>
            <span>{grp.members} members · {grp.meetDay}s</span>
            <span style={{ textAlign: 'right' }}>Share: {grp.shareValue} {grp.currency}</span>
          </div>
        </div>
      )}

      {grp && !adding && <button className="btn" onClick={() => setAdding(true)}>+ Record transaction</button>}

      {adding && grp && (
        <div className="box col g10" style={{ padding: 14 }}>
          <Field label="Type">
            <select className="input" value={form.type} onChange={e => { setForm({ ...form, type: e.target.value as VslaTxType }); setErr(''); }}>
              {VSLA_TX_TYPES.map(t => <option key={t} value={t}>{TX_LABELS[t]}</option>)}
            </select>
          </Field>
          <div className="grid2">
            <Field label="Member name"><input className="input" value={form.memberName} onChange={e => { setForm({ ...form, memberName: e.target.value }); setErr(''); }} /></Field>
            <Field label={`Amount (${grp.currency})`}><input className="input num" type="number" inputMode="decimal" value={form.amount} onChange={e => { setForm({ ...form, amount: e.target.value }); setErr(''); }} /></Field>
          </div>
          <textarea className="input" rows={2} placeholder="Note (optional)" value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} />
          {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}
          <div className="grid2">
            <button className="btn plain" onClick={() => { setAdding(false); setErr(''); }}>Cancel</button>
            <button className="btn" onClick={saveTx}>Save</button>
          </div>
        </div>
      )}

      {grp && history.length > 0 && (
        <div>
          <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Transaction history</h2>
          {history.map(t => (
            <div key={t.id} className="rowg">
              <span><span style={{ display: 'block', fontSize: 14 }}>{TX_LABELS[t.type]}</span><span className="sub">{t.memberName} · {t.date}</span></span>
              <span style={{ textAlign: 'right' }}><span className="head num" style={{ display: 'block', fontSize: 20, color: ['loan', 'share-out'].includes(t.type) ? 'var(--color-neutral-800)' : 'var(--color-accent-800)' }}>{['loan', 'share-out'].includes(t.type) ? '−' : '+'}{t.amount.toLocaleString('en')}</span></span>
            </div>
          ))}
        </div>
      )}

      {!newGroup && <button className="btn plain" onClick={() => setNewGroup(true)}>+ Create new VSLA group</button>}

      {newGroup && (
        <div className="box col g10" style={{ padding: 14 }}>
          <h2 className="h2 h20">New VSLA group</h2>
          <Field label="Group name"><input className="input" value={gf.name} placeholder="e.g. Duk Women's VSLA" onChange={e => { setGf({ ...gf, name: e.target.value }); setErr(''); }} /></Field>
          <div className="grid2">
            <Field label="Cycle"><input className="input" value={gf.cycle} placeholder="2026-S1" onChange={e => setGf({ ...gf, cycle: e.target.value })} /></Field>
            <Field label="Members"><input className="input num" type="number" value={gf.members} onChange={e => setGf({ ...gf, members: e.target.value })} /></Field>
          </div>
          <div className="grid2">
            <Field label="Meeting day">
              <select className="input" value={gf.meetDay} onChange={e => setGf({ ...gf, meetDay: e.target.value })}>
                {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(d => <option key={d}>{d}</option>)}
              </select>
            </Field>
            <Field label="Share value (SSP)"><input className="input num" type="number" value={gf.shareValue} onChange={e => setGf({ ...gf, shareValue: e.target.value })} /></Field>
          </div>
          {err && <div className="msg" style={{ fontSize: 12 }}>{err}</div>}
          <div className="grid2">
            <button className="btn plain" onClick={() => { setNewGroup(false); setErr(''); }}>Cancel</button>
            <button className="btn" onClick={saveGroup}>Create</button>
          </div>
        </div>
      )}
    </div>
  );
}
