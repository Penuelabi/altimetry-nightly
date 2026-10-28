import type { ApiError } from '@abuk/core';
import { getState, setState } from './store';

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '';

export class ApiFail extends Error {
  constructor(public status: number, public body: ApiError) { super(body.message || body.error); }
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const s = getState().session;
  if (s?.demo) throw new ApiFail(0, { error: 'demo', message: 'Demo mode: not connected to the project server.' });
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      method: init.method || (init.body ? 'POST' : 'GET'),
      headers: { ...(s ? { authorization: `Bearer ${s.token}` } : {}), ...(init.body ? { 'content-type': 'application/json' } : {}) },
      body: init.body ? JSON.stringify(init.body) : undefined
    });
  } catch {
    throw new ApiFail(0, { error: 'offline', message: 'No connection to the project server.' });
  }
  const body = await res.json().catch(() => ({ error: 'bad_response' }));
  if (res.status === 401 && s) setState({ session: null });
  if (!res.ok) throw new ApiFail(res.status, body as ApiError);
  return body as T;
}

// Plain-language reason for the person holding the phone.
export function explain(e: unknown) {
  if (e instanceof ApiFail) {
    if (e.body.error === 'not_configured') return `The server isn't set up for this yet (missing ${e.body.missing?.join(', ')}). Ask the project admin.`;
    return e.message;
  }
  return (e as Error).message;
}
