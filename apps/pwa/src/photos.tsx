import { useEffect, useState } from 'react';
import { get as idbGet, set as idbSet } from 'idb-keyval';
import { BASE } from './api';
import { getState, setState } from './store';

// Photos: shrunk on the phone (longest side 1600 px, JPEG), kept in IndexedDB so they work offline,
// queued, and uploaded to the project's private photo store when there is signal. Any phone can
// then show them by key; fetched photos are cached locally too.
const MAX = 1600;

async function shrink(b: Blob): Promise<Blob> {
  try {
    const img = await createImageBitmap(b);
    const k = Math.min(1, MAX / Math.max(img.width, img.height));
    if (k === 1 && b.type === 'image/jpeg' && b.size < 900_000) return b;
    const c = document.createElement('canvas');
    c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
    c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height);
    return await new Promise<Blob>((res) => c.toBlob(x => res(x ?? b), 'image/jpeg', 0.8));
  } catch { return b; }
}

// prefix: what the photo belongs to, e.g. "check", "pest", "crop". Returns the key to store on the record.
export async function savePhoto(b: Blob, prefix: string): Promise<string> {
  const key = `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const small = await shrink(b);
  await idbSet(key, small).catch(() => {});
  setState(st => ({ photoQueue: [...st.photoQueue, key] }));
  return key;
}

let uploading = false;
export async function uploadPhotos() {
  const s = getState();
  if (uploading || !navigator.onLine || !s.session || s.session.demo || !s.photoQueue.length) return;
  uploading = true;
  try {
    for (const key of s.photoQueue.slice(0, 20)) {
      const blob = await idbGet<Blob>(key).catch(() => undefined);
      let done = !blob; // nothing left to send
      if (blob) {
        const r = await fetch(`${BASE}/api/photos/${key}`, { method: 'PUT', headers: { authorization: `Bearer ${s.session.token}`, 'content-type': blob.type || 'image/jpeg' }, body: blob }).catch(() => null);
        if (!r) break; // signal dropped: try later
        done = r.ok || r.status === 400 || r.status === 413; // rejected photos are not retried
        if (r.status === 503) break; // photo storage not set up yet: keep the queue
      }
      if (done) setState(st => ({ photoQueue: st.photoQueue.filter(k => k !== key) }));
    }
  } finally { uploading = false; }
}

// Object URL for a photo: from this phone if saved here, else downloaded once and kept.
export function usePhoto(key: string | undefined) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    if (!key) return;
    let u = '', live = true;
    (async () => {
      let b = await idbGet<Blob>(key).catch(() => undefined);
      const s = getState();
      if (!b && navigator.onLine && s.session && !s.session.demo) {
        const r = await fetch(`${BASE}/api/photos/${key}`, { headers: { authorization: `Bearer ${s.session.token}` } }).catch(() => null);
        if (r?.ok) { b = await r.blob(); idbSet(key, b).catch(() => {}); }
      }
      if (b && live) { u = URL.createObjectURL(b); setUrl(u); }
    })();
    return () => { live = false; if (u) URL.revokeObjectURL(u); };
  }, [key]);
  return url;
}

export function Photo({ k, alt, style }: { k: string; alt: string; style?: React.CSSProperties }) {
  const url = usePhoto(k);
  return url ? <img src={url} alt={alt} style={style} /> : <div className="photo" style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11 }}>photo</div>;
}
