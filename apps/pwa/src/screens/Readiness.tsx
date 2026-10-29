import { TOLLGATES, vslaBalance, type TollgateGate, type TollgateRecord } from '@abuk/core';
import { go, useApp } from '../store';

const GATE_COLORS = ['#c03020', '#c87830', '#b8a040', '#5a9a40', 'var(--color-accent)'];

function currentGate(tollgates: TollgateRecord[], vslaId: string): number {
  const passed = tollgates.filter(t => t.vslaId === vslaId && t.passed).map(t => t.gate);
  if (passed.length === 0) return 1;
  return Math.min(Math.max(...passed) + 1, 5);
}

function checksProgress(tollgates: TollgateRecord[], vslaId: string, gate: TollgateGate): { done: number; total: number } {
  const gateInfo = TOLLGATES.find(g => g.gate === gate)!;
  const total = gateInfo.programChecks.length + gateInfo.financeChecks.length;
  const rec = tollgates.find(t => t.vslaId === vslaId && t.gate === gate);
  const done = rec?.checks.filter(c => c.done).length ?? 0;
  return { done, total };
}

export function Readiness() {
  const s = useApp();
  const groups = s.farm.vslaGroups ?? [];
  const tollgates = s.farm.tollgates ?? [];

  const gateCounts = [0, 0, 0, 0, 0];
  for (const g of groups) {
    const cur = currentGate(tollgates, g.id);
    const passed = tollgates.filter(t => t.vslaId === g.id && t.passed);
    if (passed.some(p => p.gate === 5)) gateCounts[4]++;
    else gateCounts[cur - 1]++;
  }

  return (
    <div className="pad g14" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>
        Track every VSLA group's progress through the 5 tollgates from savings to cooperative credit.
        Based on the MGRA micro-finance readiness pathway.
      </p>

      <div className="box" style={{ padding: '14px 14px 10px' }}>
        <div className="kick sm" style={{ marginBottom: 8 }}>Groups at each gate</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {TOLLGATES.map((g, i) => (
            <div key={g.gate} style={{ flex: 1, textAlign: 'center' }}>
              <div style={{
                width: 36, height: 36, borderRadius: '50%', margin: '0 auto 4px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 16, fontWeight: 700, color: '#fff',
                background: gateCounts[i] > 0 ? GATE_COLORS[i] : 'var(--color-neutral-300)'
              }}>{gateCounts[i]}</div>
              <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--color-neutral-700)' }}>{g.name}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="box" style={{ padding: '12px 14px' }}>
        <div className="between">
          <span className="kick sm">Total groups</span>
          <span className="head num" style={{ fontSize: 24 }}>{groups.length}</span>
        </div>
        <div className="grid2" style={{ fontSize: 12.5, color: 'var(--color-neutral-700)', marginTop: 6 }}>
          <span>{groups.reduce((n, g) => n + g.members, 0)} members total</span>
          <span style={{ textAlign: 'right' }}>{gateCounts[4]} at Gate 5</span>
        </div>
      </div>

      {groups.length === 0 && (
        <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--color-neutral-600)' }}>
          <div style={{ fontSize: 14, marginBottom: 8 }}>No VSLA groups yet</div>
          <button className="btn" onClick={() => go('vsla')}>Create a VSLA group</button>
        </div>
      )}

      {groups.map(grp => {
        const cur = currentGate(tollgates, grp.id);
        const bal = vslaBalance(s.farm, grp.id);
        const passedGates = tollgates.filter(t => t.vslaId === grp.id && t.passed).length;
        const curProgress = checksProgress(tollgates, grp.id, cur as TollgateGate);

        return (
          <button key={grp.id} className="box" style={{ padding: '12px 14px', textAlign: 'left' }}
            onClick={() => go('vsla')}>
            <div className="between" style={{ marginBottom: 6 }}>
              <span style={{ fontSize: 15, fontWeight: 600 }}>{grp.name}</span>
              <span className="num" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{grp.cycle}</span>
            </div>

            <div style={{ display: 'flex', gap: 2, marginBottom: 8 }}>
              {TOLLGATES.map((g, i) => {
                const rec = tollgates.find(t => t.vslaId === grp.id && t.gate === g.gate);
                const passed = rec?.passed;
                const active = g.gate === cur && !passed;
                return (
                  <div key={g.gate} style={{
                    flex: 1, height: 6, borderRadius: 3,
                    background: passed ? GATE_COLORS[i] : active ? `${GATE_COLORS[i]}50` : 'var(--color-neutral-200)'
                  }} />
                );
              })}
            </div>

            <div className="grid2" style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>
              <span>Gate {cur}: {TOLLGATES[cur - 1].name} ({curProgress.done}/{curProgress.total})</span>
              <span style={{ textAlign: 'right' }}>{bal.toLocaleString('en')} {grp.currency}</span>
            </div>
            <div className="sub" style={{ marginTop: 2 }}>
              {grp.members} members · {passedGates} gate{passedGates !== 1 ? 's' : ''} passed
            </div>
          </button>
        );
      })}

      <div className="col g6" style={{ marginTop: 4 }}>
        <div className="section">About the tollgates</div>
        <div className="sub" style={{ lineHeight: 1.5 }}>
          {TOLLGATES.map(g => (
            <span key={g.gate}><strong>Gate {g.gate} · {g.name}:</strong> {g.short}.<br /></span>
          ))}
        </div>
        <div className="sub" style={{ fontSize: 11, fontStyle: 'italic' }}>
          A group passes a tollgate only when both programme checks and finance checks are met. Groups that are ready before a lender is identified keep saving, with records kept current.
        </div>
      </div>
    </div>
  );
}
