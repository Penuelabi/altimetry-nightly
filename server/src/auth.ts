import { randomBytes, randomInt, scryptSync, timingSafeEqual } from 'node:crypto';
import { SignJWT, jwtVerify } from 'jose';
import type { PublicUser, Role } from '@abuk/core';
import { normId, weakPin, type ContactKind, type SignupRequest } from '@abuk/core';
import { cfg, need } from './config';
import { readJson, updateJson } from './adapters/github';

// users.json in the private GitHub repo. Only scrypt hashes of keys are stored.
export interface StoredUser { id: string; name: string; role: Role; salt: string; hash: string; on: boolean; created: string; expires: string; lastSeen?: string; note?: string; pinSalt?: string; pinHash?: string; pinFails?: number; pinLockedUntil?: string; pinTemp?: boolean; contact?: string; contactKind?: ContactKind; signupId?: string }
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

export function makeUser(users: StoredUser[], name: string, role: Role, days: number, now = new Date(), extra: Partial<StoredUser> = {}) {
  const key = newKey(), salt = randomBytes(16).toString('hex');
  const user: StoredUser = { id: nextId(users, role), name, role, salt, hash: hashKey(key, salt), on: true, created: now.toISOString(), expires: new Date(now.getTime() + days * 864e5).toISOString(), ...extra };
  return { user, key };
}

const fmt = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
export function toPublic(u: StoredUser): PublicUser {
  const meta = !u.on ? (u.note || 'revoked') : `key exp. ${fmt(u.expires)}` + (u.lastSeen ? ` · seen ${fmt(u.lastSeen)}` : ' · not signed in');
  return { id: u.id, name: u.name, role: u.role, meta, on: u.on, expires: u.expires, ...(u.pinTemp ? { tempPin: true } : {}) };
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
// 4-digit PINs are guessable, so they lock after PIN_MAX_FAILS wrong tries; the access key still works.
export const PIN = /^\d{4}$/;
export const PIN_MAX_FAILS = 5, PIN_LOCK_MIN = 15;
export function pinFields(pin: string) { const pinSalt = randomBytes(16).toString('hex'); return { pinSalt, pinHash: hashKey(pin, pinSalt), pinFails: 0, pinLockedUntil: undefined, pinTemp: undefined }; }
// A PIN the admin hands out: random, not easy to guess, and the worker must replace it at first sign-in.
export function newPin() { for (;;) { const p = String(randomInt(10000)).padStart(4, '0'); if (!weakPin(p)) return p; } }
export const tempPinFields = (pin: string) => ({ ...pinFields(pin), pinTemp: true as const });

// signups.json in the same private repo: requests from people asking for access, until an admin decides.
export interface SignupsFile { requests: SignupRequest[] }
export const SIGNUPS_PATH = 'signups.json';
export const SIGNUP_MAX_PENDING = 200;
export async function loadSignups(): Promise<SignupsFile> { return (await readJson<SignupsFile>(SIGNUPS_PATH, { requests: [] })).data; }
export const changeSignups = (message: string, change: (f: SignupsFile) => SignupsFile) => updateJson<SignupsFile>(SIGNUPS_PATH, { requests: [] }, message, change);

export type PinVerdict = Verdict | { ok: false; error: string; fail: true };
export function checkPin(file: UsersFile, rawId: string, pin: string, now = new Date()): PinVerdict {
  const u = file.users.find(x => x.id === normId(rawId));
  if (!u || !u.on) return { ok: false, error: 'No active worker with that ID. Ask your admin.' };
  if (new Date(u.expires) < now) return { ok: false, error: 'Your access has expired. Ask your admin for a new key.' };
  if (!u.pinHash || !u.pinSalt) return { ok: false, error: 'No PIN set yet. Sign in once with your access key, then set a PIN.' };
  if (u.pinLockedUntil && new Date(u.pinLockedUntil) > now) return { ok: false, error: `Too many wrong PINs. Try again after ${new Date(u.pinLockedUntil).toTimeString().slice(0, 5)}, or use your access key.` };
  if (!keyMatches(pin, { salt: u.pinSalt, hash: u.pinHash })) return { ok: false, error: 'Wrong PIN.', fail: true };
  return { ok: true, user: u };
}

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
