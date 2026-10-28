import { useState } from 'react';
import { useApp } from '../store';
import { Check, Seg } from '../ui';
import { toggleTask } from './common';

export function Tasks() {
  const s = useApp();
  const [f, setF] = useState<'today' | 'week' | 'mine'>('today');
  const group = s.session?.user.meta.match(/Group \d+/)?.[0] ?? 'Group 4';
  const list = f === 'today' ? s.tasks.filter(t => t.due === 'today') : f === 'mine' ? s.tasks.filter(t => t.who === group) : s.tasks;
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <Seg items={[['today', 'Today'], ['week', 'This week'], ['mine', group]]} value={f} onPick={setF} />
      <div>
        {list.map(t => (
          <button key={t.id} className="row" style={{ padding: '12px 0', minHeight: 48 }} onClick={() => toggleTask(t.id)}>
            <Check on={t.done} size={22} />
            <span style={{ flex: 1 }}><span style={{ display: 'block', fontSize: 14, lineHeight: 1.35, textDecoration: t.done ? 'line-through' : 'none' }}>{t.t}</span><span className="sub">{t.zone} · {t.who} · {t.due === 'today' ? 'today' : 'this week'}</span></span>
          </button>
        ))}
      </div>
      <p className="note">Ticks are saved on the phone and sent to the cooperative office when signal returns. Group leads can tick on behalf of members without phones.</p>
    </div>
  );
}
