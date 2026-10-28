import { useState } from 'react';
import { signinError, type SigninResponse } from '@abuk/core';
import { go, setState, useApp } from '../store';
import { api, explain } from '../api';
import { useOnline } from '../net';
import { Field, Seg } from '../ui';

async function sha(text: string) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf), b => b.toString(16).padStart(2, '0')).join('');
}

function PinBoxes({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <div style={{ position: 'relative' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8 }}>
        {[0, 1, 2, 3].map(i => <div key={i} className={'pinbox' + (i === Math.min(value.length, 3) ? ' cur' : '')}>{value[i] ? '•' : ''}</div>)}
      </div>
      <input aria-label={label} inputMode="numeric" autoComplete="off" maxLength={4} value={value} onChange={e => onChange(e.target.value.replace(/\D/g, '').slice(0, 4))}
        style={{ position: 'absolute', inset: 0, opacity: 0, width: '100%', fontSize: 16 }} autoFocus />
    </div>
  );
}

const Lockup = () => <img src="/lockup.png" alt="South Sudan Hydro-Climate Watch" style={{ width: '100%', maxWidth: 300, display: 'block', margin: '0 auto 4px' }} />;

export function SignIn() {
  const online = useOnline();
  const [id, setId] = useState('');
  const [key, setKey] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const bad = signinError(id, key);
    if (bad) return setErr(bad);
    if (!online) return setErr('First sign‑in needs signal. Move to where the phone has network and try again.');
    setBusy(true);
    try {
      const r = await api<SigninResponse>('/api/auth/signin', { body: { id, key } });
      setState({ session: { token: r.token, user: r.user, expires: r.expires }, screen: 'signin', hist: [] });
    } catch (e) { setErr(explain(e)); }
    finally { setBusy(false); }
  };
  const demo = () => setState({ session: { token: 'demo', demo: true, expires: new Date(Date.now() + 864e5).toISOString(), user: { id: 'EW‑014', name: 'Achol Deng', role: 'Admin', meta: 'Group 4 · demo', on: true, expires: '' } } });
  return (
    <div className="pad" style={{ padding: '22px 18px 24px' }}>
      <Lockup />
      <div>
        <div className="kick">Duk County · Abuk Project</div>
        <h1 className="h1" style={{ margin: '4px 0 6px', fontSize: 34, lineHeight: 1.02 }}>Sign in with your access key.</h1>
        <p className="body" style={{ fontSize: 13.5 }}>Your project admin gives you a worker ID and a one‑time access key. Ask them for a new one if it is lost.</p>
      </div>
      <Field label="Worker ID"><input className="input" style={{ minHeight: 44, fontSize: 16, padding: '0 12px', textTransform: 'uppercase' }} placeholder="EW‑000" value={id} onChange={e => { setId(e.target.value.toUpperCase()); setErr(''); }} autoCapitalize="characters" /></Field>
      <Field label="Access key"><input className="input mono" type="password" style={{ minHeight: 44, padding: '0 12px' }} placeholder="abk_…" value={key} onChange={e => { setKey(e.target.value.trim()); setErr(''); }} autoComplete="current-password" /></Field>
      {err && <div className="msg">{err}</div>}
      <button className="btn lg" onClick={submit} disabled={busy}>{busy ? 'Checking…' : 'Sign in'}</button>
      <div className="note" style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 10 }}>First sign‑in needs signal. After that, a 4‑digit PIN unlocks the app offline for 30 days.</div>
      {(import.meta.env.DEV || import.meta.env.VITE_DEMO === '1') && <button className="link" onClick={demo}>Open demo with sample data (test build)</button>}
    </div>
  );
}

export function PinLock({ onUnlock }: { onUnlock: () => void }) {
  const s = useApp();
  const [pin, setPin] = useState('');
  const [err, setErr] = useState('');
  const [tries, setTries] = useState(0);
  const check = async (v: string) => {
    setPin(v); setErr('');
    if (v.length < 4 || !s.pin) return;
    if (await sha(s.pin.salt + v) === s.pin.hash) return onUnlock();
    const n = tries + 1; setTries(n); setPin('');
    if (n >= 5) { setState({ session: null, pin: null }); return; }
    setErr(`Wrong PIN. ${5 - n} tries left before you must sign in with your key again.`);
  };
  return (
    <div className="pad" style={{ padding: '22px 18px 24px' }}>
      <Lockup />
      <div>
        <div className="kick">Welcome back</div>
        <h1 className="h1" style={{ margin: '4px 0 0', fontSize: 34, lineHeight: 1.02 }}>{s.session?.user.name.split(' ')[0]}, enter your PIN.</h1>
      </div>
      <PinBoxes value={pin} onChange={check} label="PIN" />
      {err && <div className="msg">{err}</div>}
      <button className="link" style={{ alignSelf: 'flex-start' }} onClick={() => setState({ session: null, pin: null })}>Forgot PIN? Sign in with your key</button>
    </div>
  );
}

export function Account() {
  const s = useApp();
  const [pin, setPin] = useState('');
  const [pinMsg, setPinMsg] = useState('');
  const u = s.session!.user;
  const setNewPin = async (v: string) => {
    setPin(v); setPinMsg('');
    if (v.length < 4) return;
    const salt = crypto.getRandomValues(new Uint32Array(4)).join('-');
    setState({ pin: { salt, hash: await sha(salt + v) } });
    setPin(''); setPinMsg('PIN set. It unlocks the app without signal.');
  };
  const exp = new Date(s.session!.expires).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  return (
    <div className="pad" style={{ padding: '22px 18px 24px', gap: 14 }}>
      <div className="kick">Signed in</div>
      <h1 className="h1" style={{ margin: 0, fontSize: 34, lineHeight: 1.02 }}>Welcome, {u.name.split(' ')[0]}.</h1>
      <div className="grid2" style={{ gap: 0, borderTop: '1px solid var(--color-divider)' }}>
        {[['Worker ID', u.id], ['Role', u.role], ['Data scope', `Duk · ${s.radius} km`], ['Session until', exp]].map(([k, v]) => (
          <div key={k} style={{ padding: '9px 0', borderBottom: '1px solid var(--color-divider)' }}><div className="lbl">{k}</div><div style={{ fontSize: 14 }}>{v}</div></div>
        ))}
      </div>
      <div style={{ fontSize: 12.5, lineHeight: 1.5, color: 'var(--color-neutral-800)' }}>{s.pin ? 'Change your 4‑digit PIN for offline unlock.' : 'Set a 4‑digit PIN for offline unlock.'}</div>
      <PinBoxes value={pin} onChange={setNewPin} label="New PIN" />
      {pinMsg && <div className="msg">{pinMsg}</div>}
      <div className="col g6">
        <div style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>Home screen</div>
        <Seg items={[['ledger', 'Ledger'], ['almanac', 'Almanac'], ['field', 'Field map']]} value={s.homeLayout} onPick={v => setState({ homeLayout: v })} />
      </div>
      {u.role === 'Admin' && <button className="btn plain" onClick={() => go('admin')}>Manage users & access keys</button>}
      <button className="btn lg" onClick={() => setState({ screen: 'home', hist: [] })}>Continue</button>
      <button className="link" style={{ color: 'var(--color-neutral-700)', fontSize: 13 }} onClick={() => setState({ session: null, pin: null })}>Sign out{s.outbox.length ? ` (${s.outbox.length} records still waiting to sync stay on this phone)` : ''}</button>
    </div>
  );
}
