// Self sign-up: someone asks for access with an email address or a WhatsApp number, an admin approves,
// and the admin sends them their worker ID and a temporary 4-digit PIN from their own WhatsApp or mail.
import { normPhone } from './farm';

export type ContactKind = 'email' | 'whatsapp';
export const SIGNUP_STATUS = ['pending', 'approved', 'rejected'] as const;
export interface SignupRequest {
  id: string; name: string; kind: ContactKind; contact: string; note: string; at: string;
  status: typeof SIGNUP_STATUS[number]; decidedAt?: string; decidedBy?: string; userId?: string;
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
// A South Sudan number in any common form, or any other international number written with its country code.
export function normContact(kind: ContactKind, raw: string): string {
  const s = String(raw ?? '').trim();
  if (kind === 'email') return s.length <= 254 && EMAIL.test(s) ? s.toLowerCase() : '';
  const local = normPhone(s);
  if (local) return local;
  const d = s.replace(/[^\d+]/g, '').replace(/^00/, '+');
  return /^\+[1-9]\d{7,14}$/.test(d) ? d : '';
}

export const SIGNUP_NOTE_MAX = 200;
// What is missing before a request can be sent; '' when complete.
export function signupError(i: { name: string; kind: string; contact: string; note?: string }): string {
  if (i.name.trim().split(/\s+/).filter(Boolean).length < 2) return 'Enter your first and last name.';
  if (i.name.trim().length > 80) return 'That name is too long.';
  if (i.kind !== 'email' && i.kind !== 'whatsapp') return 'Choose email or WhatsApp.';
  if (!normContact(i.kind, i.contact)) return i.kind === 'email' ? 'Enter a valid email address.' : 'Enter your WhatsApp number with its country code, like +211 912 345 678.';
  if ((i.note ?? '').length > SIGNUP_NOTE_MAX) return `Keep the note under ${SIGNUP_NOTE_MAX} characters.`;
  return '';
}

// PINs that are too easy to guess: 1111, 1234, 4321 and the like.
export const weakPin = (pin: string) => /^(\d)\1{3}$/.test(pin) || '0123456789'.includes(pin) || '9876543210'.includes(pin);

// The text the admin sends with the worker ID and temporary PIN.
export function pinMessage(i: { name: string; id: string; pin: string; url: string; reset?: boolean }): string {
  const first = i.name.trim().split(/\s+/)[0];
  return [
    `Hello ${first},`,
    i.reset ? 'Your Abuk Project PIN has been reset.' : 'Your Abuk Project access is approved.',
    `Worker ID: ${i.id}`,
    `Temporary PIN: ${i.pin}`,
    `Open ${i.url}, choose your name, and enter the PIN. The app then asks you to choose your own 4-digit PIN. Keep it private.`
  ].join('\n');
}

// What the server returns when an admin approves a request or resets a PIN: the PIN is shown once.
export interface PinIssued { user: { id: string; name: string; role: string }; pin: string; contact: string; kind: ContactKind | null }
