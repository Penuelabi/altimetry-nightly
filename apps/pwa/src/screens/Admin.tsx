import { useEffect, useState } from 'react';
import type { NewKeyResponse, PublicUser, Role } from '@abuk/core';
import { useApp } from '../store';
import { api, explain } from '../api';
import { useOnline } from '../net';
import { Field, Seg } from '../ui';

export function Admin() {
  const s = useApp(), online = useOnline();
  const [users, setUsers] = useState<PublicUser[] | null>(null);
  const [name, setName] = useState('');
  const [role, setRole] = useState<Role>('Extension worker');
  const [exp, setExp] = useState('90 days');
  const [err, setErr] = useState('');
  const [made, setMade] = useState<NewKeyResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const isAdmin = s.session?.user.role === 'Admin';

  useEffect(() => { if (online && isAdmin) api<PublicUser[]>('/api/admin/users').then(setUsers, e => setErr(explain(e))); }, [online, isAdmin]);

  if (!isAdmin) return <div className="pad"><p className="body">Only admins can manage users and access keys.</p></div>;

  const gen = async () => {
    if (name.trim().split(/\s+/).length < 2) return setErr('Enter first and last name.');
    if (!online) return setErr('Creating a key needs signal: it is committed to GitHub straight away.');
    setBusy(true); setErr('');
    try {
      const r = await api<NewKeyResponse>('/api/admin/users', { body: { name: name.trim(), role, exp } });
      setMade(r); setCopied(false); setName('');
      setUsers(u => [r.user, ...(u ?? [])]);
    } catch (e) { setErr(explain(e)); }
    finally { setBusy(false); }
  };
  const toggle = async (id: string) => {
    try { setUsers(await api<PublicUser[]>(`/api/admin/users/${encodeURIComponent(id)}/toggle`, { method: 'POST' })); }
    catch (e) { setErr(explain(e)); }
  };

  return (
    <div className="pad" style={{ paddingTop: 14 }}>
      <p className="body" style={{ fontSize: 13.5 }}>Only admins see this. A new key is shown once. GitHub stores a salted hash of it, never the key itself, in the private access repository <span className="mono" style={{ fontSize: 12 }}>users.json</span>.</p>
      <div className="box col g10" style={{ padding: 14 }}>
        <h2 className="h2 h20">New user</h2>
        <Field label="Full name"><input className="input" style={{ minHeight: 42 }} placeholder="e.g. Nyibol Garang" value={name} onChange={e => { setName(e.target.value); setErr(''); }} /></Field>
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Role</div>
        <Seg items={[['Extension worker', 'Ext. worker'], ['Group lead', 'Group lead'], ['Admin', 'Admin']]} value={role} onPick={setRole} fontSize={12.5} />
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Key expires after</div>
        <Seg items={[['30 days', '30 days'], ['90 days', '90 days'], ['1 year', '1 year']]} value={exp} onPick={setExp} fontSize={12.5} />
        {err && <div className="msg">{err}</div>}
        <button className="btn" onClick={gen} disabled={busy}>{busy ? 'Committing…' : 'Generate access key'}</button>
      </div>
      {made && (
        <div className="card accent" style={{ padding: 14 }}>
          <div className="kick sm">Key for {made.user.id} · shown once</div>
          <div className="mono" style={{ fontSize: 14, wordBreak: 'break-all', padding: 10, border: '1px dashed var(--color-accent)', borderRadius: 'var(--radius-sm)', background: 'var(--color-accent-100)' }}>{made.key}</div>
          <div className="grid2" style={{ gap: 8 }}>
            <button className="btn md" onClick={() => { navigator.clipboard?.writeText(made.key).catch(() => {}); setCopied(true); }}>{copied ? 'Copied ✓' : 'Copy key'}</button>
            <button className="btn plain md" onClick={() => setMade(null)}>Done, hide it</button>
          </div>
          <div className="num" style={{ fontSize: 11.5, lineHeight: 1.5, color: 'var(--color-neutral-800)' }}>Committed to the access repo ({made.commit}): "add {made.user.id} (hash only)". Live for sign‑in now.</div>
        </div>
      )}
      <div>
        <div className="between rule-b"><h2 className="h2 h20">Users</h2><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{users ? `${users.filter(u => u.on).length} active · ${users.filter(u => !u.on).length} revoked` : !online ? 'needs signal' : err ? 'not loaded' : 'loading…'}</span></div>
        {users?.map(u => (
          <div key={u.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, padding: '10px 0', borderBottom: '1px solid var(--color-divider)', alignItems: 'center', opacity: u.on ? 1 : 0.5 }}>
            <span><span style={{ display: 'block', fontSize: 14 }}>{u.name} <span className="mono" style={{ fontSize: 11.5, color: 'var(--color-neutral-700)' }}>{u.id}</span></span><span className="sub">{u.role} · {u.meta}</span></span>
            {u.id !== s.session?.user.id && <button className="btn plain sm" onClick={() => toggle(u.id)}>{u.on ? 'Revoke' : 'Restore'}</button>}
          </div>
        ))}
      </div>
      <div className="note" style={{ lineHeight: 1.55 }}>The GitHub token and Google service account live only on the project server, never on phones or in the repository. Revoked keys stop working at the next sign‑in check.</div>
    </div>
  );
}
