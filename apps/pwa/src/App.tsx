import { useEffect, useRef, useState, type ReactElement } from 'react';
import { ICONS, SPECIES, T, TITLES, type NavKey, type Screen } from '@abuk/core';
import { back, setState, tab, useApp } from './store';
import { syncNow, useAutoSync, useLocationWatch, useOnline, usePlace } from './net';
import { UpdateBanner } from './update';
import { useDailyRefresh } from './daily';
import { Icon } from './ui';
import { Home } from './screens/Home';
import { MapScreen } from './screens/Map';
import { Flood } from './screens/Flood';
import { Season } from './screens/Season';
import { Tasks } from './screens/Tasks';
import { Plot } from './screens/Plot';
import { Harvest } from './screens/Harvest';
import { Process, Market } from './screens/Market';
import { Guide, Species } from './screens/Guide';
import { Monitor } from './screens/Monitor';
import { Sources } from './screens/Sources';
import { Account, PinLock, SignIn } from './screens/Account';
import { Admin } from './screens/Admin';
import { Tools, Alerts, Gauge, Voice, Pest, Payout, Store, Trace, P2p } from './screens/Tools';
import { RegisterScreen } from './screens/Register';
import { Herd } from './screens/Herd';
import { Vsla } from './screens/Vsla';
import { Degradation } from './screens/Degradation';
import { Container } from './screens/Container';

const SCREENS: Record<Screen, () => ReactElement> = {
  home: Home, map: MapScreen, flood: Flood, season: Season, tasks: Tasks, plot: Plot, harvest: Harvest, process: Process, market: Market,
  guide: Guide, species: Species, monitor: Monitor, sources: Sources, signin: Account, admin: Admin, tools: Tools, alerts: Alerts,
  gauge: Gauge, voice: Voice, pest: Pest, payout: Payout, store: Store, trace: Trace, p2p: P2p, register: RegisterScreen, herd: Herd,
  vsla: Vsla, degradation: Degradation, container: Container
};

// Which bottom tab lights up for screens reached from inside another tab (as in the design).
const navKeyFor = (s: Screen): NavKey => {
  if (['monitor', 'signin', 'admin', 'register', 'tools', 'alerts', 'gauge', 'voice', 'pest', 'payout', 'store', 'p2p', 'tasks', 'harvest', 'herd', 'vsla', 'degradation', 'container'].includes(s)) return 'home';
  if (['flood', 'plot', 'sources'].includes(s)) return 'map';
  if (['trace', 'process'].includes(s)) return 'market';
  if (s === 'species') return 'guide';
  return s as NavKey;
};

export function App() {
  const s = useApp();
  const online = useOnline();
  const [splash, setSplash] = useState(true);
  const [unlocked, setUnlocked] = useState(false);
  // The PIN lock is for opening the app with a saved session; someone who just signed in is already verified.
  const startToken = useRef(s.session?.token);
  useEffect(() => { if (s.session && s.session.token !== startToken.current) setUnlocked(true); }, [s.session]);
  useAutoSync();
  useLocationWatch();
  useDailyRefresh();
  const place = usePlace();
  useEffect(() => { const t = setTimeout(() => setSplash(false), 1100); return () => clearTimeout(t); }, []);

  const lang = s.lang === 'ar' ? 'ar' : 'en', L = T[lang];
  const gated = !s.session ? 'signin' : s.pin && !unlocked ? 'pin' : null;
  const scr: Screen = gated ? 'signin' : s.screen;
  const title = gated === 'pin' ? 'Unlock' : scr === 'species' ? (SPECIES.find(x => x.key === s.species)?.name ?? 'Abuk') : TITLES[lang][scr];
  const Body = SCREENS[scr];
  const navKey = navKeyFor(scr);
  const net = online ? (s.outbox.length + s.farmOps.length === 0 ? L.synced : L.online) : `${L.offline} · ${s.outbox.length + s.farmOps.length} ${L.queued}`;

  return (
    <div className="stage">
      <div className="phone" dir="ltr">
        <header className="hdr">
          {!gated && s.hist.length > 0 && (
            <button className="hdr-back" onClick={back} aria-label="Back"><Icon d="m15 18-6-6 6-6" sw={1.6} /></button>
          )}
          <button className="hdr-logo" onClick={() => !gated && setState(st => ({ screen: 'signin', hist: [...st.hist, st.screen] }))} aria-label="Account and settings">
            <img src="/icon.png" alt="Hydro-Climate Watch" />
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="kick sm" style={{ letterSpacing: '.14em' }}>{scr === 'home' ? `${place.payam} · ${place.county}` : 'Abuk Project'}</div>
            <div className="hdr-title">{title}</div>
          </div>
          <div className="col" style={{ alignItems: 'flex-end', gap: 4, flex: 'none' }}>
            <button className="hdr-lang" onClick={() => setState(st => ({ lang: ({ en: 'ar', ar: 'din', din: 'en' } as const)[st.lang] }))}>{{ en: 'EN', ar: 'عربي', din: 'DIN' }[s.lang]}</button>
            <button className="hdr-net" onClick={() => syncNow()} title="Sync now">
              <span className="dot" style={{ background: online ? 'var(--color-accent)' : 'transparent' }} />{net}
            </button>
          </div>
        </header>
        {s.lang === 'din' && <div className="banner">Thuɔŋjäŋ strings awaiting a community translator; showing English.</div>}
        <UpdateBanner />
        {s.session?.demo && <div className="banner">Demo mode: sample data only, nothing is sent to the project server.</div>}

        <main className="scroll" key={scr + s.species}>
          {gated === 'signin' ? <SignIn /> : gated === 'pin' ? <PinLock onUnlock={() => setUnlocked(true)} /> : <Body />}
        </main>

        {!gated && (
          <nav className="nav">
            {(['home', 'map', 'season', 'guide', 'market'] as NavKey[]).map(k => (
              <button key={k} className={navKey === k ? 'on' : ''} onClick={() => tab(k)}><Icon d={ICONS[k]} />{L[k]}</button>
            ))}
          </nav>
        )}

        {splash && (
          <div className="splash" onClick={() => setSplash(false)}>
            <img src="/lockup.png" alt="South Sudan Hydro-Climate Watch" />
            <div className="kick">{place.payam} · Abuk Project</div>
          </div>
        )}
      </div>
    </div>
  );
}
