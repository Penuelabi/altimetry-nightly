import { useEffect, useState, useSyncExternalStore } from 'react';
import { CapacitorUpdater } from '@capgo/capacitor-updater';

// Two kinds of update, both published by CI to GitHub releases:
// - screens (web bundle, release abuk-web-latest): downloaded silently and switched in the next
//   time the app is closed or put in the background; a bundle that fails to start rolls back.
// - Android shell (APK, release abuk-apk-latest): only needed when the native part changes
//   (NATIVE below); Android requires the person to tap Install for those.
const REPO = 'Penuelabi/altimetry-nightly';
export const BUILD = ((import.meta.env.VITE_BUILD_SHA as string | undefined) || 'dev').slice(0, 7);
export const NATIVE = Number(import.meta.env.VITE_NATIVE_VERSION || 1);
export const APK_URL = `https://github.com/${REPO}/releases/download/abuk-apk-latest/abuk-project-latest.apk`;
const BUNDLE = /^abuk-web-([0-9a-f]{7})-n(\d+)\.zip$/;
export const isNative = () => !!(window as { Capacitor?: { isNativePlatform(): boolean } }).Capacitor?.isNativePlatform();

interface Status {
  state: 'idle' | 'checking' | 'current' | 'downloading' | 'ready' | 'needs-apk' | 'error';
  latest?: string; date?: string; msg?: string;
}
let status: Status = { state: 'idle' };
const subs = new Set<() => void>();
const set = (s: Status) => { status = s; subs.forEach(f => f()); };
export const useUpdate = () => useSyncExternalStore(cb => { subs.add(cb); return () => subs.delete(cb); }, () => status);

// Must run on every start: tells the updater this bundle loaded fine, so it is not rolled back.
export function confirmStarted() {
  if (isNative()) CapacitorUpdater.notifyAppReady().catch(() => {});
}

let running = false;
export async function checkForUpdate() {
  if (running) return;
  if (!navigator.onLine) return set({ state: 'error', msg: 'No signal. Updates download when the phone is online.' });
  running = true;
  set({ ...status, state: 'checking' });
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/releases/tags/abuk-web-latest`, { headers: { accept: 'application/vnd.github+json' } });
    if (!r.ok) throw new Error(`GitHub ${r.status}`);
    const j = await r.json() as { published_at: string; assets: { name: string; browser_download_url: string }[] };
    const asset = j.assets.map(a => ({ a, m: a.name.match(BUNDLE) })).find(x => x.m);
    if (!asset?.m) throw new Error('no update package found');
    const latest = asset.m[1], needs = Number(asset.m[2]);
    const date = new Date(j.published_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    if (BUILD === 'dev' || latest === BUILD) return set({ state: 'current', latest, date });
    // Newer screens need a newer Android shell: that one must be installed by hand.
    if (needs > NATIVE) return set({ state: 'needs-apk', latest, date });
    if (!isNative()) return set({ state: 'current', latest, date });
    set({ state: 'downloading', latest, date });
    const done = (await CapacitorUpdater.list()).bundles.find(b => b.version === latest && b.status !== 'error');
    const bundle = done ?? await CapacitorUpdater.download({ url: asset.a.browser_download_url, version: latest });
    await CapacitorUpdater.next({ id: bundle.id });
    set({ state: 'ready', latest, date });
  } catch (e) { set({ state: 'error', msg: `Could not check for updates: ${(e as Error).message}` }); }
  finally { running = false; }
}

// Restart now instead of waiting for the next time the app is closed.
export const applyNow = () => CapacitorUpdater.reload().catch(() => {});

// Opens the APK link in the phone's browser, which downloads it; Android then offers to install over this version.
export const installApk = () => window.open(APK_URL, '_blank');

// Quiet: checks at start and every 6 h. Only speaks up when the Android shell itself must be reinstalled.
export function UpdateBanner() {
  const u = useUpdate();
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if (!isNative()) return;
    checkForUpdate();
    const iv = setInterval(checkForUpdate, 6 * 3600_000);
    return () => clearInterval(iv);
  }, []);
  if (u.state !== 'needs-apk' || hidden) return null;
  return (
    <div className="banner" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ flex: 1 }}>A new version needs a one-time install ({u.date}).</span>
      <button className="btn sm" style={{ minHeight: 30, fontSize: 12.5 }} onClick={installApk}>Install</button>
      <button className="link" style={{ fontSize: 12, padding: 0 }} onClick={() => setHidden(true)} aria-label="Later">Later</button>
    </div>
  );
}
