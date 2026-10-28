import { useEffect, useState, useSyncExternalStore } from 'react';

// The Android app checks the GitHub release that CI publishes. Each build carries its commit
// (VITE_BUILD_SHA); a release built from a different commit means an update is waiting.
const REPO = 'Penuelabi/altimetry-nightly', TAG = 'abuk-apk-latest';
export const BUILD = ((import.meta.env.VITE_BUILD_SHA as string | undefined) || 'dev').slice(0, 7);
export const APK_URL = `https://github.com/${REPO}/releases/download/${TAG}/abuk-project-latest.apk`;
const native = () => !!(window as { Capacitor?: { isNativePlatform(): boolean } }).Capacitor?.isNativePlatform();

interface Status { state: 'idle' | 'checking' | 'current' | 'available' | 'error'; latest?: string; date?: string; msg?: string }
let status: Status = { state: 'idle' };
const subs = new Set<() => void>();
const set = (s: Status) => { status = s; subs.forEach(f => f()); };
export const useUpdate = () => useSyncExternalStore(cb => { subs.add(cb); return () => subs.delete(cb); }, () => status);

export async function checkForUpdate() {
  if (!navigator.onLine) return set({ state: 'error', msg: 'No signal. Try again when online.' });
  set({ ...status, state: 'checking' });
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/releases/tags/${TAG}`, { headers: { accept: 'application/vnd.github+json' } });
    if (!r.ok) throw new Error(`GitHub ${r.status}`);
    const j = await r.json() as { target_commitish: string; published_at: string };
    const latest = j.target_commitish.slice(0, 7);
    const date = new Date(j.published_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    set({ state: BUILD !== 'dev' && latest !== BUILD ? 'available' : 'current', latest, date });
  } catch (e) { set({ state: 'error', msg: `Could not check: ${(e as Error).message}` }); }
}

// Opens the APK link in the phone's browser, which downloads it; Android then offers to install over this version.
export const installUpdate = () => window.open(APK_URL, '_blank');

export function UpdateBanner() {
  const u = useUpdate();
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if (!native()) return;
    checkForUpdate();
    const iv = setInterval(checkForUpdate, 6 * 3600_000);
    return () => clearInterval(iv);
  }, []);
  if (u.state !== 'available' || hidden) return null;
  return (
    <div className="banner" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ flex: 1 }}>A new version of the app is ready ({u.date}).</span>
      <button className="btn sm" style={{ minHeight: 30, fontSize: 12.5 }} onClick={installUpdate}>Update</button>
      <button className="link" style={{ fontSize: 12, padding: 0 }} onClick={() => setHidden(true)} aria-label="Later">Later</button>
    </div>
  );
}
