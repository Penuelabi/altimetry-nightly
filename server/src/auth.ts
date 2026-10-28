import { randomBytes, randomInt, scryptSync, timingSafeEqual } from 'node:crypto';
import { SignJWT, jwtVerify } from 'jose';
import type { PublicUser, Role } from '@abuk/core';
import { normId } from '@abuk/core';
import { cfg, need } from './config';
import { readJson, updateJson } from './adapters/github';

// users.json in the private GitHub repo. Only scrypt hashes of keys are stored.
export interface StoredUser { id: string; name: string; role: Role; salt: string; hash: string; on: boolean; created: string; expires: string; lastSeen?: string; note?: string }
export interface UsersFile { users: StoredUser[] }
export const USERS_PATH = 'users.json';

const KEY_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
export const newKey = () => 'abk_' + Array.from({ length: 24 }, () => KEY_CHARS[randomInt(KEY_CHARS.length)]).join('');
export const hashKey = (key: string, salt: string) => scryptSync(key, salt, 32).toString('hex');
export function keyMatches(key: string, u: Pick<StoredUser, 'salt' | 'hash'>) {
  const a = Buffer.from(hashKey(key, u.salt), 'hex'), b = Buffer.from(u.hash, 'hex');
  return a.length === b.length && timingSafeEqual(a, b);
}

export const EXPIRY_DAYS: Record<string, number> = { '30 days': 30, '90 days': 90, '1 year': 365 };

export function nextId(users: StoredUser[], role: Role) {
  const pre = role === 'Admin' ? 'AD' : 'EW';
  const used = users.filter(u => u.id.startsWith(pre)).map(u => Number(u.id.slice(3)) || 0);
  return `${pre}‑${String(Math.max(0, ...used) + 1).padStart(3, '0')}`;
}

export function makeUser(users: StoredUser[], name: string, role: Role, days: number, now = new Date()) {
  const key = newKey(), salt = randomBytes(16).toString('hex');
  const user: StoredUser = { id: nextId(users, role), name, role, salt, hash: hashKey(key, salt), on: true, created: now.toISOString(), expires: new Date(now.getTime() + days * 864e5).toISOString() };
  return { user, key };
}

const fmt = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
export function toPublic(u: StoredUser): PublicUser {
  const meta = !u.on ? (u.note || 'revoked') : `key exp. ${fmt(u.expires)}` + (u.lastSeen ? ` · seen ${fmt(u.lastSeen)}` : ' · not signed in');
  return { id: u.id, name: u.name, role: u.role, meta, on: u.on, expires: u.expires };
}

let usersCache: { at: number; data: UsersFile } | null = null;
export async function loadUsers(fresh = false): Promise<UsersFile> {
  if (!fresh && usersCache && Date.now() - usersCache.at < 60_000) return usersCache.data;
  const { data } = await readJson<UsersFile>(USERS_PATH, { users: [] });
  usersCache = { at: Date.now(), data };
  return data;
}
export async function changeUsers(message: string, change: (f: UsersFile) => UsersFile) {
  const r = await updateJson<UsersFile>(USERS_PATH, { users: [] }, message, change);
  usersCache = { at: Date.now(), data: r.data };
  return r;
}

export type Verdict = { ok: true; user: StoredUser } | { ok: false; error: string };
export function checkKey(file: UsersFile, rawId: string, key: string, now = new Date()): Verdict {
  const u = file.users.find(x => x.id === normId(rawId));
  if (!u || !keyMatches(key, u)) return { ok: false, error: 'Worker ID or key is wrong. Ask your admin.' };
  if (!u.on) return { ok: false, error: 'This key was revoked. Ask your admin for a new one.' };
  if (new Date(u.expires) < now) return { ok: false, error: 'This key has expired. Ask your admin for a new one.' };
  return { ok: true, user: u };
}

const secret = () => { need('session'); return new TextEncoder().encode(cfg.sessionSecret); };
export async function issueSession(u: StoredUser) {
  const exp = Math.min(Date.parse(u.expires), Date.now() + 30 * 864e5);
  const token = await new SignJWT({ role: u.role, name: u.name }).setProtectedHeader({ alg: 'HS256' }).setSubject(u.id).setIssuedAt().setExpirationTime(Math.floor(exp / 1000)).sign(secret());
  return { token, expires: new Date(exp).toISOString() };
}
export interface Session { id: string; role: Role; name: string }
export async function readSession(token: string): Promise<Session> {
  const { payload } = await jwtVerify(token, secret());
  return { id: payload.sub as string, role: payload.role as Role, name: payload.name as string };
}
