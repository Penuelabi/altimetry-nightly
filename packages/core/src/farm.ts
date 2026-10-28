// The farm register: plots, crops, groups and members, oil batches and processing runs.
// One JSON document shared by every phone (server keeps it in the access repo); phones apply
// edits locally first and send the same ops to the server, which applies them in order.
import { BATCHES, MEMBERS, MON_CROPS, PROC } from './seed';

export type Zone = 'ridge' | 'slope' | 'basin';
export interface Crop { id: string; name: string }
export interface Member { id: string; name: string; workDays: number }
export interface Group { id: string; name: string; lead: string; members: Member[] }
export interface Plot { id: string; code: string; zone: Zone; crop: string; groupId: string; holder: string; areaHa: number | null; boundary: { lat: number; lon: number }[]; notes: string }
export interface OilBatch { id: string; code: string; plotId: string; fruit: string; pressed: string; bottles: number; place: string }
export interface ProcessRun { id: string; chain: 'balanites' | 'moringa'; date: string; steps: { name: string; out: string }[]; note: string }
export interface Register { version: number; updated: string; crops: Crop[]; groups: Group[]; plots: Plot[]; batches: OilBatch[]; runs: ProcessRun[] }

export type Kind = 'crop' | 'group' | 'plot' | 'batch' | 'run';
export type FarmOp =
  | { op: 'upsert'; kind: 'crop'; item: Crop } | { op: 'upsert'; kind: 'group'; item: Group } | { op: 'upsert'; kind: 'plot'; item: Plot }
  | { op: 'upsert'; kind: 'batch'; item: OilBatch } | { op: 'upsert'; kind: 'run'; item: ProcessRun }
  | { op: 'remove'; kind: Kind; id: string }
  | { op: 'workdays'; groupId: string; memberIds: string[] };

const LIST: Record<Kind, keyof Pick<Register, 'crops' | 'groups' | 'plots' | 'batches' | 'runs'>> = { crop: 'crops', group: 'groups', plot: 'plots', batch: 'batches', run: 'runs' };

export const newId = (prefix: string) => `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export function applyOps(reg: Register, ops: FarmOp[], at = new Date().toISOString()): Register {
  let r = reg;
  for (const o of ops) {
    if (o.op === 'workdays') {
      r = { ...r, groups: r.groups.map(g => g.id !== o.groupId ? g : { ...g, members: g.members.map(m => o.memberIds.includes(m.id) ? { ...m, workDays: m.workDays + 1 } : m) }) };
      continue;
    }
    const key = LIST[o.kind];
    const list = r[key] as { id: string }[];
    const next = o.op === 'remove' ? list.filter(x => x.id !== o.id)
      : list.some(x => x.id === o.item.id) ? list.map(x => (x.id === o.item.id ? o.item : x)) : [...list, o.item];
    r = { ...r, [key]: next };
  }
  return ops.length ? { ...r, version: r.version + ops.length, updated: at } : r;
}

export const removeAllowed = (role: string) => role === 'Admin';
export const editAllowed = (role: string) => role === 'Admin' || role === 'Group lead';

export function opError(o: FarmOp): string {
  if (o.op === 'workdays') return o.groupId ? '' : 'group missing';
  if (o.op === 'remove') return o.id ? '' : 'id missing';
  const it = o.item as { id?: string; name?: string; code?: string };
  if (!it.id) return 'id missing';
  if (o.kind === 'plot' || o.kind === 'batch') return it.code?.trim() ? '' : 'a code is required';
  return it.name?.trim() ? '' : 'a name is required';
}

export const plotLabel = (p: Plot, reg: Register) => {
  const g = reg.groups.find(x => x.id === p.groupId);
  return `${p.code} · ${g ? g.name : p.holder || p.crop}`;
};

// Starting register built from the design's sample farm, so a fresh project is not empty.
export function seedRegister(): Register {
  const g = (n: number, lead: string, members: string[] = []): Group => ({ id: `g${n}`, name: `Group ${n}`, lead, members: members.map((m, i) => ({ id: `g${n}m${i + 1}`, name: m, workDays: 0 })) });
  const g4 = { ...g(4, 'Achol Deng'), members: MEMBERS.map(([name, days], i) => ({ id: `g4m${i + 1}`, name, workDays: days })) };
  const groups = [g(1, ''), g(2, 'Kuol Arok'), g(3, ''), g4, g(5, ''), g(6, 'Deng Bol')];
  const P = (code: string, zone: Zone, crop: string, groupId: string, holder = '', areaHa: number | null = null): Plot => ({ id: code, code, zone, crop, groupId, holder, areaHa, boundary: [], notes: '' });
  const plots = [P('R‑02', 'ridge', 'Moringa', 'g1'), P('R‑05', 'ridge', 'Gum arabic', 'g2'), P('S‑01', 'slope', 'Sesame', 'g5'), P('S‑04', 'slope', 'Groundnut', 'g3'),
    P('B‑03', 'basin', 'Balanites', '', 'Ayen Kuol'), P('B‑07', 'basin', 'Balanites', 'g4', '', 0.62), P('B‑12', 'basin', 'Balanites', 'g6')];
  const batches: OilBatch[] = BATCHES.map((b, i) => ({ id: b.id, code: b.id, plotId: ['B‑07', 'B‑03', 'B‑12'][i], fruit: b.fruit, pressed: b.pressed, bottles: parseInt(b.bottles, 10), place: b.place }));
  const runs: ProcessRun[] = (['balanites', 'moringa'] as const).map(c => ({ id: `run-${c}-2026`, chain: c, date: c === 'balanites' ? '2026-03-12' : '2026-10-20', steps: PROC[c].steps.map(s => ({ name: s.name, out: s.out })), note: PROC[c].foot }));
  return { version: 1, updated: '2026-10-28T00:00:00Z', crops: MON_CROPS.map(n => ({ id: n.toLowerCase().replace(/[^a-z]+/g, '-'), name: n })), groups, plots, batches, runs };
}
