// The farm register: plots, crops, groups and members, oil batches and processing runs.
// One JSON document shared by every phone (server keeps it in the access repo); phones apply
// edits locally first and send the same ops to the server, which applies them in order.
import { BATCHES, MEMBERS, MON_CROPS, PROC, STORE } from './seed';

export type Zone = 'ridge' | 'slope' | 'basin';
// pests: names workers added under "Other" in the pest check, offered next time for this crop.
export type CropCategory = 'cereal' | 'legume' | 'vegetable' | 'oilseed' | 'tree' | 'root' | 'fibre' | 'fruit' | 'other';
export type CropSeason = 'rainfed' | 'recession' | 'perennial' | 'irrigated';
// The optional fields describe the crop for others; photos are photo keys (3 for a new crop).
export interface Crop {
  id: string; name: string; pests?: string[];
  localName?: string; scientific?: string; variety?: string; category?: CropCategory; season?: CropSeason;
  daysToHarvest?: number | null; spacing?: string; seedRate?: string; uses?: string; photos?: string[];
}
export interface Member { id: string; name: string; workDays: number }
export interface Group { id: string; name: string; lead: string; members: Member[] }
// crops: other crops grown on the plot besides the main one (intercrops, borders).
export interface Plot { id: string; code: string; zone: Zone; crop: string; crops?: string[]; groupId: string; holder: string; areaHa: number | null; boundary: { lat: number; lon: number }[]; notes: string }
// A traceable batch of any processed product. `bottles` is the number of units (bottles, packs, sacks).
export interface OilBatch {
  id: string; code: string; plotId: string; fruit: string; pressed: string; bottles: number; place: string;
  crop?: string; product?: string; unit?: string; lat?: number | null; lon?: number | null;
  runId?: string; storeId?: string; quality?: string; packedBy?: string; notes?: string;
}
// chain: 'balanites' | 'moringa' in older runs; otherwise the product name (see chainFor).
export interface ProcessRun { id: string; chain: string; crop?: string; product?: string; plotIds?: string[]; date: string; steps: { name: string; out: string }[]; note: string }
// Seed & input store: stores, items, every movement in or out, and orders with their status trail.
export interface Store { id: string; code: string; name: string; place: string; keeper: string }
export interface StockItem { id: string; code: string; name: string; unit: string; kind: 'seed' | 'input' | 'tool' | 'packaging' | 'other'; reorder: number | null }
export interface StockMove { id: string; storeId: string; itemId: string; date: string; dir: 'in' | 'out'; qty: number; party: string; orderId: string; by: string; note: string }
export const ORDER_STATUS = ['requested', 'approved', 'ordered', 'in transit', 'received', 'cancelled'] as const;
export type OrderStatus = typeof ORDER_STATUS[number];
export interface OrderStep { at: string; status: OrderStatus; where: string; by: string; note: string }
export interface Order { id: string; code: string; itemId: string; qty: number; storeId: string; supplier: string; created: string; by: string; status: OrderStatus; where: string; history: OrderStep[] }
export interface Register {
  version: number; updated: string; crops: Crop[]; groups: Group[]; plots: Plot[]; batches: OilBatch[]; runs: ProcessRun[];
  stores?: Store[]; items?: StockItem[]; moves?: StockMove[]; orders?: Order[];
}

export type Kind = 'crop' | 'group' | 'plot' | 'batch' | 'run' | 'store' | 'item' | 'move' | 'order';
export type FarmOp =
  | { op: 'upsert'; kind: 'crop'; item: Crop } | { op: 'upsert'; kind: 'group'; item: Group } | { op: 'upsert'; kind: 'plot'; item: Plot }
  | { op: 'upsert'; kind: 'batch'; item: OilBatch } | { op: 'upsert'; kind: 'run'; item: ProcessRun }
  | { op: 'upsert'; kind: 'store'; item: Store } | { op: 'upsert'; kind: 'item'; item: StockItem }
  | { op: 'upsert'; kind: 'move'; item: StockMove } | { op: 'upsert'; kind: 'order'; item: Order }
  | { op: 'remove'; kind: Kind; id: string }
  | { op: 'workdays'; groupId: string; memberIds: string[] };

type ListKey = 'crops' | 'groups' | 'plots' | 'batches' | 'runs' | 'stores' | 'items' | 'moves' | 'orders';
const LIST: Record<Kind, ListKey> = { crop: 'crops', group: 'groups', plot: 'plots', batch: 'batches', run: 'runs', store: 'stores', item: 'items', move: 'moves', order: 'orders' };

export const newId = (prefix: string) => `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export function applyOps(reg: Register, ops: FarmOp[], at = new Date().toISOString()): Register {
  let r = reg;
  for (const o of ops) {
    if (o.op === 'workdays') {
      r = { ...r, groups: r.groups.map(g => g.id !== o.groupId ? g : { ...g, members: g.members.map(m => o.memberIds.includes(m.id) ? { ...m, workDays: m.workDays + 1 } : m) }) };
      continue;
    }
    const key = LIST[o.kind];
    const list = (r[key] ?? []) as { id: string }[];
    const next = o.op === 'remove' ? list.filter(x => x.id !== o.id)
      : list.some(x => x.id === o.item.id) ? list.map(x => (x.id === o.item.id ? o.item : x)) : [...list, o.item];
    r = { ...r, [key]: next };
  }
  return ops.length ? { ...r, version: r.version + ops.length, updated: at } : r;
}

export const removeAllowed = (role: string) => role === 'Admin';
export const editAllowed = (role: string) => role === 'Admin' || role === 'Group lead';

// Who may send an op. Anyone signed in records store movements and orders, and may add a pest name
// to a crop (the server checks nothing else on the crop changed); the rest needs an admin or group lead.
export function opAllowed(role: string, o: FarmOp, reg: Register): boolean {
  if (o.op === 'remove') return removeAllowed(role);
  if (editAllowed(role)) return true;
  if (o.op === 'upsert' && (o.kind === 'move' || o.kind === 'order')) return true;
  if (o.op === 'upsert' && o.kind === 'crop') { const cur = reg.crops.find(c => c.id === o.item.id); return !!cur && cur.name === o.item.name; }
  return false;
}

export function opError(o: FarmOp): string {
  if (o.op === 'workdays') return o.groupId ? '' : 'group missing';
  if (o.op === 'remove') return o.id ? '' : 'id missing';
  const it = o.item as { id?: string; name?: string; code?: string };
  if (!it.id) return 'id missing';
  if (o.op === 'upsert' && o.kind === 'move') return o.item.storeId && o.item.itemId && o.item.qty > 0 && (o.item.dir === 'in' || o.item.dir === 'out') ? '' : 'a store, item and quantity above 0 are required';
  if (o.op === 'upsert' && o.kind === 'order') return o.item.itemId && o.item.qty > 0 && (ORDER_STATUS as readonly string[]).includes(o.item.status) ? '' : 'an item, quantity and valid status are required';
  if (o.kind === 'plot' || o.kind === 'batch' || o.kind === 'store' || o.kind === 'item') return it.code?.trim() ? '' : 'a code is required';
  return it.name?.trim() ? '' : 'a name is required';
}

// Balance of each item in each store: everything in minus everything out.
export function balances(reg: Register) {
  const m = new Map<string, number>();
  for (const v of reg.moves ?? []) { const k = `${v.storeId}|${v.itemId}`; m.set(k, (m.get(k) ?? 0) + (v.dir === 'in' ? v.qty : -v.qty)); }
  return (storeId: string, itemId: string) => m.get(`${storeId}|${itemId}`) ?? 0;
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
  return { version: 1, updated: '2026-10-28T00:00:00Z', crops: MON_CROPS.map(n => ({ id: n.toLowerCase().replace(/[^a-z]+/g, '-'), name: n })), groups, plots, batches, runs, ...seedStore() };
}

// A starting store and the usual items, with no stock: balances begin with a counted opening entry.
export function seedStore(): Required<Pick<Register, 'stores' | 'items' | 'moves' | 'orders'>> {
  const kind = (n: string): StockItem['kind'] => (/seed|scion/i.test(n) ? 'seed' : /sack|bottle/i.test(n) ? 'packaging' : 'input');
  const code = (n: string) => n.toUpperCase().replace(/[^A-Z]+/g, ' ').trim().split(' ').slice(0, 2).map(w => w.slice(0, 4)).join('-');
  return {
    stores: [{ id: 'ST-01', code: 'ST-01', name: 'Abuk main store', place: '', keeper: '' }],
    items: STORE.map(([name, unit, , need]) => ({ id: code(name), code: code(name), name, unit, kind: kind(name), reorder: need })),
    moves: [], orders: []
  };
}
