import { useSyncExternalStore } from 'react';
import { get, set } from 'idb-keyval';
import type { GaugeReading, HomeLayout, Lang, PublicUser, PullResult, SatelliteIndices, Screen, SyncKind, SyncRecord } from '@abuk/core';
import { HARV, LEADS, MEMBERS, MON, SOURCES, STORE, TASKS, applyOps, seedRegister, type FarmOp, type Harvest, type MonRecord, type Register, type Task } from '@abuk/core';

export interface Session { token: string; user: PublicUser; expires: string; demo?: boolean }
export interface Plot { id: string; mode: 'walk' | 'pin'; pts: { lat: number; lon: number }[]; ha: number; elevation: number | null; slopePct: number | null; at: string }
// Workers who have signed in on this phone: their session and a local PIN hash, so the PIN
// works offline and signing out does not forget them.
export interface Account { user: PublicUser; token: string; expires: string; pin: { salt: string; hash: string } | null }
export interface RosterEntry { id: string; name: string; hasPin: boolean }
export interface Where { lat: number; lon: number; acc: number | null; payam: string; county: string; state: string; at: string }
export interface Lead { id: string; name: string; group?: string; rows: string; phone: string; lang?: 'en' | 'ar'; on: boolean }

// Everything a worker records lives here and on the phone (IndexedDB) until it syncs.
export interface State {
  lang: Lang; homeLayout: HomeLayout;
  session: Session | null; pin: { salt: string; hash: string } | null;
  screen: Screen; hist: Screen[]; species: string; zone: 'ridge' | 'slope' | 'basin';
  tasks: Task[]; harvests: Harvest[]; monLog: MonRecord[]; plots: Plot[];
  sourcesOn: Record<string, boolean>; radius: number; lastPull: PullResult | null;
  outbox: SyncRecord[]; lastSync: string | null;
  photoQueue: string[]; // photo keys saved on this phone, waiting to upload
  present: boolean[]; stock: number[]; doneP: string[];
  offer: 'open' | 'accepted' | 'countered';
  leads: Lead[]; alertLog: string[]; gauge: GaugeReading[] | null;
  where: Where | null;
  accounts: Account[]; roster: RosterEntry[];
  // Satellite values for a small circle around where the phone last asked (light: two numbers).
  satHere: { lat: number; lon: number; at: string; floodPct: number | null; soil: number | null; radiusKm: number } | null;
  satIndices: SatelliteIndices | null;
  autoPull: { state: 'running' | 'ok' | 'error'; at: string; msg?: string } | null;
  // Crop checks from every phone (server, last 3 weeks), for the flood model and SMS alerts.
  checksAll: { id: string; at: string; by: string; plot: string; crop: string; lat: number | null; lon: number | null; water: string; depthCm: number | null; around: string; aroundDepthCm: number | null; trend: string }[];
  farm: Register; farmOps: FarmOp[]; regTab: 'plots' | 'crops' | 'groups' | 'people' | 'batches' | 'runs';
  // Records received from another phone (ids, so the same file is not added twice) and a short log of transfers.
  carried: string[]; p2pLog: { at: string; who: string; n: number; dir: 'in' | 'out' }[];
}

const initial: State = {
  lang: 'en', homeLayout: 'ledger', session: null, pin: null,
  screen: 'home', hist: [], species: 'balanites', zone: 'basin',
  tasks: TASKS, harvests: HARV, monLog: MON, plots: [],
  sourcesOn: Object.fromEntries(SOURCES.map(s => [s.id, true])), radius: 20, lastPull: null,
  outbox: [], lastSync: null, photoQueue: [],
  present: MEMBERS.map((_, i) => i !== 4 && i !== 8), stock: STORE.map(s => s[2]), doneP: [],
  offer: 'open',
  leads: LEADS.map(([name, g, rows]) => ({ id: name, name: `${name} · ${g}`, rows, phone: 'number on server', on: true })),
  alertLog: [], gauge: null, where: null,
  accounts: [], roster: [], satHere: null, satIndices: null, autoPull: null, checksAll: [],
  farm: seedRegister(), farmOps: [], regTab: 'plots', carried: [], p2pLog: []
};

// Navigation is per session; the rest survives restarts.
const TRANSIENT: (keyof State)[] = ['screen', 'hist', 'regTab'];
const KEY = 'abuk-state-v1';

let state: State = initial;
let ready = false;
const subs = new Set<() => void>();
let saveTimer: ReturnType<typeof setTimeout> | undefined;

export function setState(patch: Partial<State> | ((s: State) => Partial<State>)) {
  state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) };
  subs.forEach(f => f());
  if (ready) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      const keep = { ...state } as Partial<State>;
      TRANSIENT.forEach(k => delete keep[k]);
      set(KEY, keep).catch(() => {});
    }, 250);
  }
}
export const getState = () => state;

export async function hydrate() {
  try {
    const saved = await get<Partial<State>>(KEY);
    if (saved) state = { ...initial, ...saved, screen: 'home', hist: [] };
  } catch { /* private mode: run from memory */ }
  ready = true;
  subs.forEach(f => f());
}

export function useApp(): State {
  return useSyncExternalStore(cb => { subs.add(cb); return () => subs.delete(cb); }, () => state);
}

// ---- navigation ----
export const go = (s: Screen) => setState(st => ({ screen: s, hist: [...st.hist, st.screen] }));
export const tab = (s: Screen) => setState({ screen: s, hist: [] });
export const back = () => setState(st => st.hist.length ? { screen: st.hist[st.hist.length - 1], hist: st.hist.slice(0, -1) } : {});
export const openRegister = (t: State['regTab']) => { setState({ regTab: t }); go('register'); };
export const openSpecies = (key: string) => { setState({ species: key }); go('species'); };

// ---- outbox ----
let seq = 0;
export function record(kind: SyncKind, data: Record<string, unknown>) {
  const s = getState();
  const rec: SyncRecord = { id: `${Date.now().toString(36)}-${(seq++).toString(36)}-${Math.random().toString(36).slice(2, 6)}`, kind, at: new Date().toISOString(), by: s.session?.user.id ?? 'unknown', data };
  setState(st => ({ outbox: [...st.outbox, rec] }));
  return rec.id;
}

export const today = () => new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

// Farm register edits apply on the phone at once and queue for the server (see net.ts syncNow).
export function farmChange(...ops: FarmOp[]) {
  setState(st => ({ farm: applyOps(st.farm, ops), farmOps: [...st.farmOps, ...ops] }));
}

// Signs a worker in on this phone and remembers them for next time.
export function startSession(a: Omit<Account, 'pin'> & { pin?: Account['pin'] }) {
  setState(st => {
    const old = st.accounts.find(x => x.user.id === a.user.id);
    const acc: Account = { user: a.user, token: a.token, expires: a.expires, pin: a.pin ?? old?.pin ?? null };
    return { session: { token: acc.token, user: acc.user, expires: acc.expires }, pin: acc.pin, accounts: [acc, ...st.accounts.filter(x => x.user.id !== acc.user.id)], screen: 'home', hist: [] };
  });
}
export const signOut = () => setState({ session: null, pin: null });
