import { useState } from 'react';
import { TOLLGATES, VSLA_TX_TYPES, newId, vslaBalance, type TollgateCheck, type TollgateGate, type TollgateRecord, type VslaGroup, type VslaTx, type VslaTxType } from '@abuk/core';
import { farmChange, useApp } from '../store';
import { Check, Field } from '../ui';

const TX_LABELS: Record<VslaTxType, string> = { savings: 'Savings deposit', loan: 'Loan taken', repayment: 'Loan repayment', interest: 'Interest earned', fine: 'Fine', 'social-fund': 'Social fund', 'share-out': 'Share-out' };
const GATE_COLORS = ['#c03020', '#c87830', '#b8a040', '#5a9a40', 'var(--color-accent)'];

function currentGate(tollgates: TollgateRecord[], vslaId: string): number {
  const passed = tollgates.filter(t => t.vslaId === vslaId && t.passed).map(t => t.gate);
  if (passed.length === 0) return 1;
  const max = Math.max(...passed);
  return Math.min(max + 1, 5);
}

function gateRecord(tollgates: TollgateRecord[], vslaId: string, gate: TollgateGate): TollgateRecord | undefined {
  return tollgates.find(t => t.vslaId === vslaId && t.gate === gate);
}

function GateProgress({ tollgates, vslaId }: { tollgates: TollgateRecord[]; vslaId: string }) {
  const cur = currentGate(tollgates, vslaId);
  return (
    <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
      {TOLLGATES.map((g, i) => {
        const rec = gateRecord(tollgates, vslaId, g.gate as TollgateGate);
        const passed = rec?.passed;
        const active = g.gate === cur && !passed;
        return (
          <div key={g.gate} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <div style={{
              width: '100%', height: 6, borderRadius: 3,
              background: passed ? GATE_COLORS[i] : active ? `${GATE_COLORS[i]}60` : 'var(--color-neutral-200)',
              transition: 'background .3s'
            }} />
            <span style={{ fontSize: 10, fontWeight: passed || active ? 700 : 400, color: passed ? GATE_COLORS[i] : active ? 'var(--color-neutral-900)' : 'var(--color-neutral-500)' }}>
              {g.gate}. {g.name}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function TollgatePanel({ tollgates, vslaId, userId }: { tollgates: TollgateRecord[]; vslaId: string; userId: string }) {
  const [openGate, setOpenGate] = useState<TollgateGate | null>(null);
  const cur = currentGate(tollgates, vslaId);

  const toggleCheck = (gate: TollgateGate, checkText: string, kind: 'program' | 'finance') => {
    const existing = gateRecord(tollgates, vslaId, gate);
    const gateInfo = TOLLGATES.find(g => g.gate === gate)!;
    const allChecks = [
      ...gateInfo.programChecks.map(c => ({ check: c, kind: 'program' as const })),
      ...gateInfo.financeChecks.map(c => ({ check: c, kind: 'finance' as const })),
    ];

    let checks: TollgateCheck[];
    if (existing) {
      checks = allChecks.map(ac => {
        const prev = existing.checks.find(c => c.check === ac.check && c.kind === ac.kind);
        if (ac.check === checkText && ac.kind === kind) {
          return { check: ac.check, kind: ac.kind, done: !prev?.done, date: new Date().toISOString().slice(0, 10), by: userId, note: '' };
        }
        return prev ?? { check: ac.check, kind: ac.kind, done: false, date: '', by: '', note: '' };
      });
    } else {
      checks = allChecks.map(ac => ({
        check: ac.check, kind: ac.kind,
        done: ac.check === checkText && ac.kind === kind,
        date: ac.check === checkText && ac.kind === kind ? new Date().toISOString().slice(0, 10) : '',
        by: ac.check === checkText && ac.kind === kind ? userId : '', note: ''
      }));
    }

    const allDone = checks.every(c => c.done);
    const rec: TollgateRecord = {
      id: existing?.id ?? newId('tg'),
      vslaId, gate, checks,
      passed: allDone,
      passedDate: allDone ? new Date().toISOString().slice(0, 10) : '',
      by: userId, note: ''
    };
    farmChange({ op: 'upsert', kind: 'tollgate', item: rec });
  };

  return (
    <div className="col g10">
      <div className="between">
        <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Micro-finance readiness</h2>
        <span className="kick sm" style={{ color: 'var(--color-accent-800)' }}>Gate {cur} of 5</span>
      </div>
      <GateProgress tollgates={tollgates} vslaId={vslaId} />

      {TOLLGATES.map(g => {
        const rec = gateRecord(tollgates, vslaId, g.gate as TollgateGate);
        const passed = rec?.passed;
        const isOpen = openGate === g.gate;
        const doneCount = rec?.checks.filter(c => c.done).length ?? 0;
        const totalCount = g.programChecks.length + g.financeChecks.length;

        return (
          <div key={g.gate} className="box" style={{ padding: 0, textAlign: 'left', overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
              onClick={() => setOpenGate(isOpen ? null : g.gate as TollgateGate)}>
              <span style={{
                width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 13, fontWeight: 700, color: '#fff',
                background: passed ? GATE_COLORS[g.gate - 1] : 'var(--color-neutral-400)'
              }}>{passed ? '✓' : g.gate}</span>
              <span style={{ flex: 1 }}>
                <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>Gate {g.gate}: {g.name}</span>
                <span className="sub">{g.short}</span>
              </span>
              <span className="num" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{doneCount}/{totalCount}</span>
            </div>

            {isOpen && (
              <div style={{ padding: '0 14px 12px', borderTop: '1px solid var(--color-divider)' }}
                onClick={e => e.stopPropagation()}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-neutral-700)', margin: '10px 0 4px', letterSpacing: '.08em', textTransform: 'uppercase' }}>Programme checks</div>
                {g.programChecks.map(check => {
                  const done = rec?.checks.find(c => c.check === check && c.kind === 'program')?.done ?? false;
                  return (
                    <button key={check} className="row" style={{ padding: '6px 0', gap: 8 }}
                      onClick={() => toggleCheck(g.gate as TollgateGate, check, 'program')}>
                      <Check on={done} size={18} />
                      <span style={{ fontSize: 13, flex: 1, textDecoration: done ? 'line-through' : 'none', color: done ? 'var(--color-neutral-600)' : 'var(--color-neutral-900)' }}>{check}</span>
                    </button>
                  );
                })}
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-neutral-700)', margin: '10px 0 4px', letterSpacing: '.08em', textTransform: 'uppercase' }}>Finance checks</div>
                {g.financeChecks.map(check => {
                  const done = rec?.checks.find(c => c.check === check && c.kind === 'finance')?.done ?? false;
                  return (
                    <button key={check} className="row" style={{ padding: '6px 0', gap: 8 }}
                      onClick={() => toggleCheck(g.gate as TollgateGate, check, 'finance')}>
                      <Check on={done} size={18} />
                      <span style={{ fontSize: 13, flex: 1, textDecoration: done ? 'line-through' : 'none', color: done ? 'var(--color-neutral-600)' : 'var(--color-neutral-900)' }}>{check}</span>
                    </button>
                  );
                })}
                {passed && rec?.passedDate && (
                  <div style={{ marginTop: 8, fontSize: 12, color: GATE_COLORS[g.gate - 1], fontWeight: 600 }}>
                    Passed on {rec.passedDate}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function Vsla() {
  const s = useApp();
  const groups = s.farm.vslaGroups ?? [];
  const txs = s.farm.vslaTxs ?? [];
  const tollgates = s.farm.tollgates ?? [];
  const [sel, setSel] = useState(groups[0]?.id ?? '');
  const [adding, setAdding] = useState(false);
  const [newGroup, setNewGroup] = useState(false);
  const [view, setView] = useState<'savings' | 'readiness'>('savings');
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
        <div style={{ display: 'flex', gap: 0, borderRadius: 'var(--radius-sm)', overflow: 'hidden', border: '1px solid var(--color-divider)' }}>
          {(['savings', 'readiness'] as const).map(v => (
            <button key={v} style={{
              flex: 1, padding: '8px 0', fontSize: 13, fontWeight: view === v ? 700 : 400, border: 'none', cursor: 'pointer',
              background: view === v ? 'var(--color-accent)' : 'var(--color-bg)',
              color: view === v ? '#fff' : 'var(--color-neutral-700)'
            }} onClick={() => setView(v)}>
              {v === 'savings' ? 'Savings & loans' : 'Readiness'}
            </button>
          ))}
        </div>
      )}

      {grp && view === 'readiness' && (
        <TollgatePanel tollgates={tollgates} vslaId={grp.id} userId={s.session?.user.id ?? ''} />
      )}

      {grp && view === 'savings' && (
        <>
          <div className="box" style={{ padding: '12px 14px' }}>
            <div className="between"><span className="kick sm">Fund balance</span><span className="head num" style={{ fontSize: 28 }}>{bal.toLocaleString('en')} {grp.currency}</span></div>
            <div className="grid2" style={{ fontSize: 12.5, color: 'var(--color-neutral-700)', marginTop: 6 }}>
              <span>{grp.members} members · {grp.meetDay}s</span>
              <span style={{ textAlign: 'right' }}>Share: {grp.shareValue} {grp.currency}</span>
            </div>
          </div>

          {!adding && <button className="btn" onClick={() => setAdding(true)}>+ Record transaction</button>}

          {adding && (
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

          {history.length > 0 && (
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
        </>
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
