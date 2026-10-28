import { useEffect, useState } from 'react';
import { signinError, type SigninResponse } from '@abuk/core';
import { go, openRegister, setState, signOut, startSession, useApp, type RosterEntry } from '../store';
import { api, ApiFail, explain } from '../api';
import { useOnline, usePlace } from '../net';
import { Field, Seg } from '../ui';
import { BUILD, NATIVE, applyNow, checkForUpdate, installApk, useUpdate } from '../update';

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

const localPin = async (pin: string) => { const salt = crypto.getRandomValues(new Uint32Array(4)).join('-'); return { salt, hash: await sha(salt + pin) }; };
const OTHER = '__other__';

export function SignIn() {
  const s = useApp(), online = useOnline(), place = usePlace();
  // Everyone the phone knows: workers who signed in here before, plus the project roster when online.
  useEffect(() => { if (online) api<RosterEntry[]>('/api/auth/roster').then(r => setState({ roster: r }), () => {}); }, [online]);
  const people = [...s.accounts.map(a => ({ id: a.user.id, name: a.user.name, hasPin: !!a.pin })), ...s.roster.filter(r => !s.accounts.some(a => a.user.id === r.id))]
    .sort((a, b) => a.name.localeCompare(b.name));
  const [pick, setPick] = useState(s.accounts[0]?.user.id ?? '');
  const [typed, setTyped] = useState('');
  const id = pick === OTHER ? typed : pick;
  const acc = s.accounts.find(a => a.user.id === id);
  const hasPin = !!acc?.pin || !!s.roster.find(r => r.id === id)?.hasPin;
  const [method, setMethod] = useState<'pin' | 'key'>(hasPin ? 'pin' : 'key');
  useEffect(() => { setMethod(hasPin ? 'pin' : 'key'); setErr(''); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  const [key, setKey] = useState('');
  const [pin, setPin] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const withKey = async () => {
    const bad = signinError(id, key);
    if (bad) return setErr(bad);
    if (!online) return setErr('Signing in with the key needs signal. Move to where the phone has network, or use your PIN.');
    setBusy(true);
    try {
      const r = await api<SigninResponse>('/api/auth/signin', { body: { id, key } });
      startSession({ token: r.token, user: r.user, expires: r.expires });
      // First time with the key: open the account page so they can set a PIN.
      if (!acc?.pin) setState({ screen: 'signin', hist: [] });
    } catch (e) { setErr(explain(e)); }
    finally { setBusy(false); }
  };

  const withPin = async (v: string) => {
    setPin(v); setErr('');
    if (v.length < 4) return;
    // On a phone this worker used before, the PIN works offline against the stored session.
    if (acc?.pin && Date.parse(acc.expires) > Date.now() && await sha(acc.pin.salt + v) === acc.pin.hash) return startSession(acc);
    if (!online) { setPin(''); return setErr(acc?.pin ? 'Wrong PIN.' : 'This phone has not seen your PIN yet. Use it once with signal, or sign in with your access key.'); }
    setBusy(true);
    try {
      const r = await api<SigninResponse>('/api/auth/signin-pin', { body: { id, pin: v } });
      startSession({ token: r.token, user: r.user, expires: r.expires, pin: await localPin(v) });
    } catch (e) { setPin(''); setErr(explain(e)); }
    finally { setBusy(false); }
  };

  const demo = () => setState({ session: { token: 'demo', demo: true, expires: new Date(Date.now() + 864e5).toISOString(), user: { id: 'EW‑014', name: 'Achol Deng', role: 'Admin', meta: 'Group 4 · demo', on: true, expires: '' } } });
  return (
    <div className="pad" style={{ padding: '22px 18px 24px' }}>
      <Lockup />
      <div>
        <div className="kick">{place.payam} · Abuk Project</div>
        <h1 className="h1" style={{ margin: '4px 0 6px', fontSize: 34, lineHeight: 1.02 }}>Who is signing in?</h1>
      </div>
      <Field label="Worker">
        <select className="input" style={{ minHeight: 44, fontSize: 16 }} value={pick} onChange={e => { setPick(e.target.value); setPin(''); setKey(''); }}>
          <option value="" disabled>{people.length ? 'Choose your name' : online ? 'Loading names…' : 'Connect once to load names'}</option>
          {people.map(p => <option key={p.id} value={p.id}>{p.name} · {p.id}</option>)}
          <option value={OTHER}>My name is not listed: type my ID</option>
        </select>
      </Field>
      {pick === OTHER && <Field label="Worker ID"><input className="input" style={{ minHeight: 44, fontSize: 16, textTransform: 'uppercase' }} placeholder="EW‑000" value={typed} onChange={e => { setTyped(e.target.value.toUpperCase()); setErr(''); }} autoCapitalize="characters" /></Field>}
      {id && <>
        <Seg items={[['pin', '4‑digit PIN'], ['key', 'Access key']]} value={method} onPick={m => { setMethod(m); setErr(''); setPin(''); }} />
        {method === 'pin'
          ? <><PinBoxes value={pin} onChange={withPin} label="PIN" />{!hasPin && <div className="note">No PIN yet for {id}. Sign in once with your access key, then set a PIN.</div>}</>
          : <>
            <Field label="Access key"><input className="input mono" type="password" style={{ minHeight: 44, padding: '0 12px' }} placeholder="abk_…" value={key} onChange={e => { setKey(e.target.value.trim()); setErr(''); }} autoComplete="current-password" onKeyDown={e => e.key === 'Enter' && withKey()} /></Field>
            <button className="btn lg" onClick={withKey} disabled={busy}>{busy ? 'Checking…' : 'Sign in'}</button>
          </>}
      </>}
      {busy && method === 'pin' && <div className="note">Checking…</div>}
      {err && <div className="msg">{err}</div>}
      <div className="note" style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 10 }}>The access key from your admin is needed once. Then use your PIN: it works on any phone with signal, and offline on phones you have used before. 5 wrong PINs lock PIN sign‑in for 15 minutes.</div>
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
    if (n >= 5) { signOut(); return; }
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
      <button className="link" style={{ alignSelf: 'flex-start' }} onClick={signOut}>Forgot PIN? Sign in with your key</button>
    </div>
  );
}

export function Account() {
  const s = useApp(), place = usePlace();
  const [pin, setPin] = useState('');
  const [pinMsg, setPinMsg] = useState('');
  const u = s.session!.user;
  const setNewPin = async (v: string) => {
    setPin(v); setPinMsg('');
    if (v.length < 4) return;
    setPin('');
    if (!s.session?.demo) {
      try { await api('/api/auth/pin', { body: { pin: v } }); }
      catch (e) {
        if (!(e instanceof ApiFail) || e.status !== 0) return setPinMsg(explain(e));
        setPinMsg('Saved on this phone only (no signal). Set it again with signal to use it on other phones.');
      }
    }
    const p = await localPin(v);
    setState(st => ({ pin: p, accounts: st.accounts.map(a => (a.user.id === st.session?.user.id ? { ...a, pin: p } : a)) }));
    setPinMsg(m => m || 'PIN set. Use it to sign in next time, on this phone even without signal.');
  };
  const exp = new Date(s.session!.expires).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  return (
    <div className="pad" style={{ padding: '22px 18px 24px', gap: 14 }}>
      <div className="kick">Signed in</div>
      <h1 className="h1" style={{ margin: 0, fontSize: 34, lineHeight: 1.02 }}>Welcome, {u.name.split(' ')[0]}.</h1>
      <div className="grid2" style={{ gap: 0, borderTop: '1px solid var(--color-divider)' }}>
        {[['Worker ID', u.id], ['Role', u.role], ['Data scope', `${place.payam} · ${s.radius} km`], ['Session until', exp]].map(([k, v]) => (
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
      <button className="btn plain" onClick={() => openRegister('plots')}>Farm register · plots, crops, groups, batches</button>
      {u.role === 'Admin' && <button className="btn plain" onClick={() => go('admin')}>Manage users & access keys</button>}
      <AppVersion />
      <button className="btn lg" onClick={() => setState({ screen: 'home', hist: [] })}>Continue</button>
      <button className="link" style={{ color: 'var(--color-neutral-700)', fontSize: 13 }} onClick={signOut}>Sign out{s.outbox.length ? ` (${s.outbox.length} records still waiting to sync stay on this phone)` : ''}</button>
    </div>
  );
}

function AppVersion() {
  const u = useUpdate();
  const line = {
    idle: '', checking: 'Checking…', current: `Up to date (${u.date}).`, downloading: `Downloading version ${u.latest} in the background…`,
    ready: `Version ${u.latest} is downloaded. It starts the next time you close and reopen the app.`,
    'needs-apk': `Version ${u.latest} needs a one-time install of the new Android app.`, error: u.msg ?? ''
  }[u.state];
  return (
    <div className="col g6" style={{ borderTop: '1px solid var(--color-divider)', paddingTop: 10 }}>
      <div className="between"><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>App version</span><span className="mono" style={{ fontSize: 12 }}>{BUILD} · shell {NATIVE}</span></div>
      <div className="sub">Updates download by themselves when there is signal.</div>
      {line && <div className="msg">{line}</div>}
      {u.state === 'ready' ? <button className="btn" onClick={applyNow}>Restart now with the new version</button>
        : u.state === 'needs-apk' ? <button className="btn" onClick={installApk}>Download & install</button>
        : <button className="btn plain" onClick={checkForUpdate}>Check now</button>}
    </div>
  );
}
