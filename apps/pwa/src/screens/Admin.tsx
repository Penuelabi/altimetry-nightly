import { useEffect, useState } from 'react';
import { pinMessage, type NewKeyResponse, type PinIssued, type PublicUser, type Role, type SignupRequest } from '@abuk/core';
import { useApp } from '../store';
import { BASE, api, explain } from '../api';
import { copyText, gmailTo, mailTo, openLink, whatsappShare, whatsappTo } from '../sms';

// The Gmail account approval emails go from. Remembered on this phone.
const FROM_KEY = 'abuk-mail-from', DEFAULT_FROM = 'penuelabi@gmail.com';
const readFrom = () => { try { return localStorage.getItem(FROM_KEY) || DEFAULT_FROM; } catch { return DEFAULT_FROM; } };
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
  const [reqs, setReqs] = useState<SignupRequest[]>([]);
  const [issued, setIssued] = useState<(PinIssued & { reset: boolean }) | null>(null);
  const [pick, setPick] = useState<Record<string, { role: Role; exp: string }>>({});
  const [note, setNote] = useState('');
  const [from, setFrom] = useState(readFrom);

  useEffect(() => {
    if (!online || !isAdmin) return;
    api<PublicUser[]>('/api/admin/users').then(setUsers, e => setErr(explain(e)));
    api<SignupRequest[]>('/api/admin/signups').then(setReqs, () => {});
  }, [online, isAdmin]);

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

  const refresh = () => { api<PublicUser[]>('/api/admin/users').then(setUsers, () => {}); api<SignupRequest[]>('/api/admin/signups').then(setReqs, () => {}); };
  const approve = async (r: SignupRequest) => {
    const o = pick[r.id] ?? { role: 'Extension worker' as Role, exp: '90 days' };
    setErr(''); setNote('');
    try { setIssued({ ...(await api<PinIssued>(`/api/admin/signups/${encodeURIComponent(r.id)}/approve`, { body: o })), reset: false }); refresh(); }
    catch (e) { setErr(explain(e)); }
  };
  const reject = async (r: SignupRequest) => {
    try { await api(`/api/admin/signups/${encodeURIComponent(r.id)}/reject`, { method: 'POST' }); setNote(`Request from ${r.name} rejected.`); refresh(); }
    catch (e) { setErr(explain(e)); }
  };
  const resetPin = async (u: PublicUser) => {
    setErr(''); setNote('');
    try { setIssued({ ...(await api<PinIssued>(`/api/admin/users/${encodeURIComponent(u.id)}/reset-pin`, { method: 'POST' })), reset: true }); refresh(); }
    catch (e) { setErr(explain(e)); }
  };
  const pending = reqs.filter(r => r.status === 'pending');
  const joinUrl = `${BASE || location.origin}/join`;
  const text = issued ? pinMessage({ name: issued.user.name, id: issued.user.id, pin: issued.pin, url: BASE || location.origin, reset: issued.reset }) : '';
  const sendIssued = () => {
    if (!issued) return;
    if (issued.kind === 'email' && issued.contact) {
      try { localStorage.setItem(FROM_KEY, from.trim()); } catch { /* remembering is optional */ }
      openLink(/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(from.trim()) ? gmailTo(from.trim(), issued.contact, 'Your Abuk Project access', text) : mailTo(issued.contact, 'Your Abuk Project access', text));
    }
    else openLink(issued.contact ? whatsappTo(issued.contact, text) : whatsappShare(text));
  };

  return (
    <div className="pad" style={{ paddingTop: 14 }}>
      {issued && (
        <div className="card accent" style={{ padding: 14 }}>
          <div className="kick sm">{issued.reset ? 'New PIN' : 'Approved'} for {issued.user.name} · {issued.user.id} · shown once</div>
          <div className="head num" style={{ fontSize: 40, letterSpacing: '.2em' }}>{issued.pin}</div>
          <div className="sub">Send it now, from your own {issued.kind === 'email' ? 'Gmail' : 'WhatsApp'}{issued.contact ? ` to ${issued.contact}` : ''}. The worker is asked to choose their own PIN at first sign-in. The server keeps only a hash.</div>
          <div className="grid2" style={{ gap: 8 }}>
            <button className="btn md" onClick={sendIssued}>{issued.kind === 'email' && issued.contact ? 'Send from Gmail' : 'Send on WhatsApp'}</button>
            <button className="btn plain md" onClick={async () => setNote((await copyText(text)) ? 'Message copied.' : 'Could not copy. Select the PIN and send it by hand.')}>Copy message</button>
          </div>
          {issued.kind === 'email' && issued.contact && <>
            <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Send from this Gmail account (you press Send in Gmail)</div>
            <input className="input" style={{ minHeight: 40 }} type="email" inputMode="email" aria-label="Send from" value={from} onChange={e => setFrom(e.target.value)} />
            <button className="link" style={{ alignSelf: 'flex-start', fontSize: 12.5 }} onClick={() => openLink(mailTo(issued.contact, 'Your Abuk Project access', text))}>Use this phone's mail app instead</button>
          </>}
          <button className="link" style={{ alignSelf: 'flex-start' }} onClick={() => { setIssued(null); setNote(''); }}>Done, hide it</button>
        </div>
      )}
      {note && <div className="msg">{note}</div>}
      <div className="box col g6" style={{ padding: '10px 12px' }}>
        <div className="kick sm">Link for new workers</div>
        <div className="mono" style={{ fontSize: 12.5, wordBreak: 'break-all' }}>{joinUrl}</div>
        <div className="sub">It opens the form to ask for access. Send it to people who want to join; their requests appear below.</div>
        <div className="grid2" style={{ gap: 8 }}>
          <button className="btn plain md" onClick={async () => setNote((await copyText(joinUrl)) ? 'Link copied.' : 'Could not copy. Select the link and copy it by hand.')}>Copy link</button>
          <button className="btn plain md" onClick={() => openLink(whatsappShare(`Ask for access to the Abuk Project app: ${joinUrl}`))}>Share on WhatsApp</button>
        </div>
      </div>
      {pending.length > 0 && (
        <div>
          <div className="between rule-b"><h2 className="h2 h20">Sign-up requests</h2><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{pending.length} waiting</span></div>
          {pending.map(r => {
            const o = pick[r.id] ?? { role: 'Extension worker' as Role, exp: '90 days' };
            return (
              <div key={r.id} className="col g8" style={{ padding: '10px 0', borderBottom: '1px solid var(--color-divider)' }}>
                <div><span style={{ display: 'block', fontSize: 14 }}>{r.name}</span><span className="sub">{r.kind === 'email' ? 'Email' : 'WhatsApp'} {r.contact} · {new Date(r.at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}{r.note ? ` · ${r.note}` : ''}</span></div>
                <div className="grid2" style={{ gap: 8 }}>
                  <select className="input" aria-label="Role" style={{ minHeight: 40 }} value={o.role} onChange={e => setPick({ ...pick, [r.id]: { ...o, role: e.target.value as Role } })}><option>Extension worker</option><option>Group lead</option><option>Admin</option></select>
                  <select className="input" aria-label="Access lasts" style={{ minHeight: 40 }} value={o.exp} onChange={e => setPick({ ...pick, [r.id]: { ...o, exp: e.target.value } })}><option value="30 days">30 days</option><option value="90 days">90 days</option><option value="1 year">1 year</option></select>
                </div>
                <div className="grid2" style={{ gap: 8 }}>
                  <button className="btn md" onClick={() => approve(r)}>Approve and get PIN</button>
                  <button className="btn plain md" onClick={() => reject(r)}>Reject</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
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
            <span style={{ display: 'flex', gap: 6 }}>{u.on && <button className="btn plain sm" onClick={() => resetPin(u)}>Reset PIN</button>}{u.id !== s.session?.user.id && <button className="btn plain sm" onClick={() => toggle(u.id)}>{u.on ? 'Revoke' : 'Restore'}</button>}</span>
          </div>
        ))}
      </div>
      <div className="note" style={{ lineHeight: 1.55 }}>The GitHub token and Google service account live only on the project server, never on phones or in the repository. Revoked keys stop working at the next sign‑in check.</div>
    </div>
  );
}
