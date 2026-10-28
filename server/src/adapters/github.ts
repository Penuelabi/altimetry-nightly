import { cfg, need } from '../config';

// Minimal GitHub contents API client for small JSON files in the private access repo.
async function gh(path: string, init: RequestInit = {}) {
  need('github');
  return fetch(`https://api.github.com/repos/${cfg.ghRepo}/contents/${path}`, {
    ...init,
    headers: { accept: 'application/vnd.github+json', authorization: `Bearer ${cfg.ghToken}`, 'x-github-api-version': '2022-11-28', 'user-agent': 'abuk-server', ...(init.headers || {}) }
  });
}

export async function readJson<T>(path: string, fallback: T): Promise<{ data: T; sha: string | null }> {
  const res = await gh(`${path}?ref=${encodeURIComponent(cfg.ghBranch)}`);
  if (res.status === 404) return { data: fallback, sha: null };
  if (!res.ok) throw new Error(`GitHub read ${path} → ${res.status}`);
  const j = await res.json() as { content: string; sha: string };
  return { data: JSON.parse(Buffer.from(j.content, 'base64').toString('utf8')) as T, sha: j.sha };
}

export async function writeJson(path: string, data: unknown, sha: string | null, message: string): Promise<string> {
  const res = await gh(path, {
    method: 'PUT', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ message, branch: cfg.ghBranch, content: Buffer.from(JSON.stringify(data, null, 2) + '\n').toString('base64'), ...(sha ? { sha } : {}) })
  });
  if (res.status === 409 || res.status === 422) throw new Conflict(path);
  if (!res.ok) throw new Error(`GitHub write ${path} → ${res.status} ${(await res.text()).slice(0, 200)}`);
  const j = await res.json() as { commit: { sha: string } };
  return j.commit.sha;
}

export class Conflict extends Error { constructor(path: string) { super(`${path} changed on GitHub; retry`); } }

// Read-modify-write with a retry when someone else committed in between.
export async function updateJson<T>(path: string, fallback: T, message: string, change: (d: T) => T): Promise<{ data: T; commit: string }> {
  for (let i = 0; i < 3; i++) {
    const { data, sha } = await readJson(path, fallback);
    const next = change(data);
    try { return { data: next, commit: await writeJson(path, next, sha, message) }; }
    catch (e) { if (!(e instanceof Conflict) || i === 2) throw e; }
  }
  throw new Error('unreachable');
}

// Recent commits touching a path: who changed the farm register or users, and when.
export async function commitsFor(path: string, perPage = 20): Promise<{ sha: string; message: string; date: string }[]> {
  need('github');
  const res = await fetch(`https://api.github.com/repos/${cfg.ghRepo}/commits?path=${encodeURIComponent(path)}&sha=${encodeURIComponent(cfg.ghBranch)}&per_page=${perPage}`, {
    headers: { accept: 'application/vnd.github+json', authorization: `Bearer ${cfg.ghToken}`, 'user-agent': 'abuk-server' }
  });
  if (!res.ok) throw new Error(`GitHub commits ${path} → ${res.status}`);
  const j = await res.json() as { sha: string; commit: { message: string; author: { date: string } } }[];
  return j.map(c => ({ sha: c.sha.slice(0, 7), message: c.commit.message.split('\n')[0], date: c.commit.author.date }));
}
