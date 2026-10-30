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
// Where something is, by admin level: State > County > Payam, then a village or town typed by the worker.
export interface AdminLoc { state: string; county: string; payam: string; village?: string }
export const NO_ADMIN: AdminLoc = { state: '', county: '', payam: '', village: '' };
export const adminLabel = (a?: AdminLoc | null) => a ? [a.village, a.payam, a.county, a.state].filter(Boolean).join(', ') : '';
// A person on the register: group members, store keepers, VSLA members, SMS recipients. Phones and
// next of kin live here once and every form that picks the person reads them from here.
export interface NextOfKin { name: string; name2: string; phone: string; relation: string; village: string }
export const BLANK_KIN: NextOfKin = { name: '', name2: '', phone: '', relation: '', village: '' };
export interface Person { id: string; name: string; name2: string; phone: string; phone2: string; admin: AdminLoc; kin: NextOfKin[]; note: string }
export const personName = (p?: Pick<Person, 'name' | 'name2'> | null) => p ? [p.name, p.name2].filter(Boolean).join(' ') : '';
export const blankPerson = (id: string, admin: AdminLoc = NO_ADMIN): Person => ({ id, name: '', name2: '', phone: '', phone2: '', admin, kin: [{ ...BLANK_KIN }, { ...BLANK_KIN }], note: '' });
// A South Sudan mobile number: +211 then nine digits; spaces, dashes and a leading 0 are tolerated.
export function normPhone(raw: string): string {
  const d = raw.replace(/[^\d+]/g, '');
  if (/^\+211\d{9}$/.test(d)) return d;
  if (/^211\d{9}$/.test(d)) return `+${d}`;
  if (/^0\d{9}$/.test(d)) return `+211${d.slice(1)}`;
  if (/^\d{9}$/.test(d)) return `+211${d}`;
  return '';
}
// What is missing from a person before saving; '' when complete.
export function personError(p: Person): string {
  const miss: string[] = [];
  if (!p.name.trim()) miss.push('first name');
  if (!p.name2.trim()) miss.push('second name');
  if (!normPhone(p.phone)) miss.push('phone number (like +211 912 345 678)');
  if (p.phone2.trim() && !normPhone(p.phone2)) miss.push('second phone in the same format, or leave it empty');
  if (!p.admin.state || !p.admin.county || !p.admin.payam) miss.push('state, county and payam');
  p.kin.forEach((k, i) => { if (!k.name.trim() || !normPhone(k.phone) || !k.relation.trim()) miss.push(`next of kin ${i + 1}: name, relation and phone`); });
  return miss.length ? 'Add ' + miss.join(', ') + '.' : '';
}

export interface Member { id: string; name: string; workDays: number; personId?: string }
// lastRoll is the date (YYYY-MM-DD) of the last roll-call added to work days, so one day is never counted twice.
export interface Group { id: string; name: string; lead: string; members: Member[]; admin?: AdminLoc; lastRoll?: string }
// crops: other crops grown on the plot besides the main one (intercrops, borders).
export interface Plot { id: string; code: string; zone: Zone; crop: string; crops?: string[]; groupId: string; holder: string; areaHa: number | null; boundary: { lat: number; lon: number }[]; notes: string; admin?: AdminLoc }
// A traceable batch of any processed product. `bottles` is the number of units (bottles, packs, sacks).
export interface OilBatch {
  id: string; code: string; plotId: string; fruit: string; pressed: string; bottles: number; place: string;
  crop?: string; product?: string; unit?: string; lat?: number | null; lon?: number | null;
  runId?: string; storeId?: string; quality?: string; packedBy?: string; notes?: string;
  admin?: AdminLoc; // `place` holds its text form
}
// chain: 'balanites' | 'moringa' in older runs; otherwise the product name (see chainFor).
export interface ProcessRun { id: string; chain: string; crop?: string; product?: string; plotIds?: string[]; date: string; steps: { name: string; out: string }[]; note: string }
// Seed & input store: stores, items, every movement in or out, and orders with their status trail.
// place and keeper stay as text for older records; admin, plotId, groupId and keeperId (a Person) are the structured form.
export interface Store { id: string; code: string; name: string; place: string; keeper: string; admin?: AdminLoc; plotId?: string; groupId?: string; keeperId?: string }
export const STOCK_KINDS = ['seed', 'input', 'tool', 'packaging', 'product', 'other'] as const;
// 'product' is something the project sells (livestock, honey, fish, oil); price is per unit.
export interface StockItem { id: string; code: string; name: string; unit: string; kind: typeof STOCK_KINDS[number]; reorder: number | null; price?: number | null }
export interface StockMove { id: string; storeId: string; itemId: string; date: string; dir: 'in' | 'out'; qty: number; party: string; orderId: string; by: string; note: string }
export const ORDER_STATUS = ['requested', 'approved', 'ordered', 'in transit', 'received', 'cancelled'] as const;
export type OrderStatus = typeof ORDER_STATUS[number];
export interface OrderStep { at: string; status: OrderStatus; where: string; by: string; note: string }
export interface Order { id: string; code: string; itemId: string; qty: number; storeId: string; supplier: string; created: string; by: string; status: OrderStatus; where: string; history: OrderStep[]; admin?: AdminLoc }
// Herd & pond register: livestock, forest products and fish. Each lives in the same shared
// register and syncs the same way as the farm register and the seed & input store.
export const LIVESTOCK_SPECIES = ['cow', 'goat', 'sheep', 'pig', 'chicken', 'rabbit'] as const;
export type LivestockSpecies = typeof LIVESTOCK_SPECIES[number];
// Events that move the head count: opening count, birth and purchase add; death and sale remove.
// Vaccination and treatment record care without changing the count; milk and eggs record yield.
export const LIVESTOCK_EVENTS = ['opening', 'birth', 'purchase', 'death', 'sale', 'vaccination', 'treatment', 'milk', 'eggs'] as const;
export type LivestockEventKind = typeof LIVESTOCK_EVENTS[number];
const HERD_ADDS: readonly LivestockEventKind[] = ['opening', 'birth', 'purchase'];
const HERD_REMOVES: readonly LivestockEventKind[] = ['death', 'sale'];
// One herd per species per owner or group; its head count is the running total of its events
// (like the store balance), not a stored number, so it can never drift from the log.
// ownerId is a Person id for 'member'; groupId is the group the herd belongs to or the owner's group.
export interface Herd { id: string; species: LivestockSpecies; ownerType: 'member' | 'group'; ownerId: string; ownerName: string; admin?: AdminLoc; groupId?: string }
// qty is head count for opening/birth/purchase/death/sale/vaccination/treatment, litres for milk, count for eggs.
// time is HH:MM. storeMoveId is set when the output was put into the store for sale (see productToStore).
export interface LivestockEvent { id: string; herdId: string; kind: LivestockEventKind; date: string; qty: number; note: string; by: string; time?: string; storeMoveId?: string }

export const FOREST_PRODUCTS = ['honey', 'resin', 'gum', 'firewood', 'charcoal', 'shea'] as const;
export type ForestProduct = typeof FOREST_PRODUCTS[number];
// What was collected, from where (GPS) and by whom.
export interface ForestLog { id: string; product: ForestProduct; date: string; qty: number; unit: string; lat: number | null; lon: number | null; by: string; note: string; admin?: AdminLoc; groupId?: string; memberId?: string; time?: string; storeMoveId?: string }

export const FISH_SPECIES = ['tilapia', 'nile perch', 'catfish', 'other'] as const;
export type FishSpecies = typeof FISH_SPECIES[number];
export const FISH_EVENTS = ['stocking', 'catch', 'harvest'] as const;
export type FishEventKind = typeof FISH_EVENTS[number];
export const FISH_PROCESSED = ['none', 'smoked', 'dried'] as const;
export type FishProcessed = typeof FISH_PROCESSED[number];
// Catch or pond stocking, harvest weight, and whether it was smoked or dried.
export interface FishLog { id: string; species: FishSpecies; kind: FishEventKind; date: string; weightKg: number | null; qty: number | null; processed: FishProcessed; pond: string; by: string; note: string; admin?: AdminLoc; groupId?: string; memberId?: string; time?: string; storeMoveId?: string }

// VSLA: Village Savings and Loan Associations — the evidence trail from savings to microfinance.
export const VSLA_TX_TYPES = ['savings', 'loan', 'repayment', 'interest', 'fine', 'social-fund', 'share-out'] as const;
export type VslaTxType = typeof VSLA_TX_TYPES[number];
// members is the head count; memberIds (Person ids) is the list when members were added from the person register.
export interface VslaGroup { id: string; name: string; cycle: string; members: number; meetDay: string; shareValue: number; currency: string; admin?: AdminLoc; memberIds?: string[] }
export interface VslaTx { id: string; vslaId: string; date: string; type: VslaTxType; memberId: string; memberName: string; amount: number; balance: number; by: string; note: string }

// Micro-finance readiness tollgates — 5 gates from savings group to cooperative credit.
export const TOLLGATES = [
  { gate: 1, name: 'Learn', short: 'Group formed, saving, money controls in place',
    programChecks: ['Group formed with elected leaders', 'Members saving regularly', 'Two keyholders for funds', 'Group records started'],
    financeChecks: ['Opening savings recorded', 'Meeting schedule established', 'Share value agreed'] },
  { gate: 2, name: 'Prove', short: 'Internal loans repaid, season records kept',
    programChecks: ['Internal loans issued and tracked', 'All internal loans repaid on schedule', 'Season records complete', 'Loss records kept for flood/drought'],
    financeChecks: ['Savings and repayment records for several seasons', 'Season scorecards completed', 'Loan purpose plans documented'] },
  { gate: 3, name: 'Grow', short: 'Referred to lender, first micro-loan',
    programChecks: ['Group referred to lender', 'Lender assessment completed', 'First loan purpose agreed by group', 'Climate-adapted practices in place'],
    financeChecks: ['Savings buffers demonstrated', 'Reinvestment checked at season review', 'First loan disbursed'] },
  { gate: 4, name: 'Lead', short: 'First loan repaid, graduates train new groups',
    programChecks: ['First loan fully repaid', 'Graduates training new groups', 'Larger loan amounts available', 'Group governance strong'],
    financeChecks: ['Full repayment record', 'Reinvestment verified', 'Second loan cycle started'] },
  { gate: 5, name: 'Own', short: 'Cooperative-level credit, community-run',
    programChecks: ['Cooperative formally registered', 'Community-run governance', 'Multiple loan cycles completed', 'Training programme self-sustaining'],
    financeChecks: ['Cooperative credit facility', 'Independent financial management', 'Audit trail complete'] },
] as const;

export type TollgateGate = 1 | 2 | 3 | 4 | 5;

export interface TollgateCheck {
  check: string;
  kind: 'program' | 'finance';
  done: boolean;
  date: string;
  by: string;
  note: string;
}

export interface TollgateRecord {
  id: string;
  vslaId: string;
  gate: TollgateGate;
  checks: TollgateCheck[];
  passed: boolean;
  passedDate: string;
  by: string;
  note: string;
}

// Land degradation assessment — the 8 indicators from the UoJ survey, scored per site visit.
export const DEGRADATION_INDICATORS = [
  { id: 'topsoil', label: 'Loss of topsoil' },
  { id: 'waterlog', label: 'Waterlogging of farmland' },
  { id: 'gullies', label: 'Gullies or deep erosion channels' },
  { id: 'trees', label: 'Loss of trees' },
  { id: 'grass', label: 'Reduced grass cover' },
  { id: 'compact', label: 'Soil hard, compacted or cracked' },
  { id: 'herder', label: 'Increased herder movement' },
  { id: 'drying', label: 'Drying of water sources in dry season' },
] as const;
export type DegradationId = typeof DEGRADATION_INDICATORS[number]['id'];
export interface DegradationAssessment { id: string; date: string; site: string; plotId: string; by: string; scores: Record<string, number>; photos: string[]; note: string; admin?: AdminLoc }

// Container/bag farming — vegetable pilot for fishing communities.
export const CONTAINER_TYPES = ['sack', 'bag', 'bucket', 'tire', 'raised-bed'] as const;
export type ContainerType = typeof CONTAINER_TYPES[number];
// ownerId is the Person id of the member who looks after the unit; groupId and plotId say which group and plot it belongs to.
export interface ContainerUnit { id: string; code: string; type: ContainerType; crop: string; plantedDate: string; location: string; ownerId: string; ownerName: string; note: string; groupId?: string; plotId?: string; admin?: AdminLoc }
export interface ContainerLog { id: string; unitId: string; date: string; action: 'water' | 'fertilize' | 'pest-check' | 'harvest' | 'note'; qty: number | null; unit: string; pest: string; photo: string; by: string; note: string }

// A word for the pictures & voice screen in the three project languages (name = the English word, for lists).
export interface Word { id: string; name: string; ar: string; din: string; icon: string; by: string }
// Who gets flood alerts besides phones: an email list and WhatsApp groups (joined by invite link).
export interface Subscriber { id: string; name: string; email: string; on: boolean }
export interface WaGroup { id: string; name: string; link: string }

// A job on the shared task list (it syncs to every phone and is copied to the Drive sheet). due is a date, YYYY-MM-DD;
// zone is Ridge, Slope, Basin, All or a place such as Store.
export interface FarmTask { id: string; title: string; zone: string; who: string; groupId?: string; due: string; done: boolean; doneAt?: string; doneBy?: string; by: string; at: string; admin?: AdminLoc }
// A surveyed row of Balanites mounds: crest height above the basin floor, in metres.
export interface Mound { id: string; crest: number; plotId?: string; note: string; surveyedAt: string; by: string }

// Market: what the cooperative has for sale, and the offers buyers make (prices in US dollars per unit).
export const LISTING_STATUS = ['open', 'sold out', 'withdrawn'] as const;
export interface Listing { id: string; name: string; storeId?: string; itemId?: string; qty: number; unit: string; price: number; groupId?: string; admin?: AdminLoc; status: typeof LISTING_STATUS[number]; note: string; by: string; at: string }
export const OFFER_STATUS_MARKET = ['open', 'accepted', 'countered', 'declined', 'delivered'] as const;
export interface Offer { id: string; listingId?: string; buyer: string; phone: string; product: string; qty: number; unit: string; price: number; status: typeof OFFER_STATUS_MARKET[number]; counterPrice?: number; pickup: string; moveId?: string; note: string; by: string; at: string; answeredAt?: string }

export interface Register {
  version: number; updated: string; crops: Crop[]; groups: Group[]; plots: Plot[]; batches: OilBatch[]; runs: ProcessRun[];
  people?: Person[]; words?: Word[]; subscribers?: Subscriber[]; waGroups?: WaGroup[];
  stores?: Store[]; items?: StockItem[]; moves?: StockMove[]; orders?: Order[];
  herds?: Herd[]; livestockEvents?: LivestockEvent[]; forestLogs?: ForestLog[]; fishLogs?: FishLog[];
  vslaGroups?: VslaGroup[]; vslaTxs?: VslaTx[];
  degradations?: DegradationAssessment[];
  containers?: ContainerUnit[]; containerLogs?: ContainerLog[];
  tollgates?: TollgateRecord[];
  tasks?: FarmTask[]; mounds?: Mound[]; listings?: Listing[]; offers?: Offer[];
}

export type Kind = 'crop' | 'group' | 'plot' | 'batch' | 'run' | 'store' | 'item' | 'move' | 'order' | 'herd' | 'livestockEvent' | 'forestLog' | 'fishLog' | 'vslaGroup' | 'vslaTx' | 'degradation' | 'container' | 'containerLog' | 'tollgate' | 'person' | 'word' | 'subscriber' | 'waGroup' | 'task' | 'mound' | 'listing' | 'offer';
export type FarmOp =
  | { op: 'upsert'; kind: 'crop'; item: Crop } | { op: 'upsert'; kind: 'group'; item: Group } | { op: 'upsert'; kind: 'plot'; item: Plot }
  | { op: 'upsert'; kind: 'batch'; item: OilBatch } | { op: 'upsert'; kind: 'run'; item: ProcessRun }
  | { op: 'upsert'; kind: 'store'; item: Store } | { op: 'upsert'; kind: 'item'; item: StockItem }
  | { op: 'upsert'; kind: 'move'; item: StockMove } | { op: 'upsert'; kind: 'order'; item: Order }
  | { op: 'upsert'; kind: 'herd'; item: Herd } | { op: 'upsert'; kind: 'livestockEvent'; item: LivestockEvent }
  | { op: 'upsert'; kind: 'forestLog'; item: ForestLog } | { op: 'upsert'; kind: 'fishLog'; item: FishLog }
  | { op: 'upsert'; kind: 'vslaGroup'; item: VslaGroup } | { op: 'upsert'; kind: 'vslaTx'; item: VslaTx }
  | { op: 'upsert'; kind: 'degradation'; item: DegradationAssessment }
  | { op: 'upsert'; kind: 'container'; item: ContainerUnit } | { op: 'upsert'; kind: 'containerLog'; item: ContainerLog }
  | { op: 'upsert'; kind: 'tollgate'; item: TollgateRecord }
  | { op: 'upsert'; kind: 'person'; item: Person } | { op: 'upsert'; kind: 'word'; item: Word }
  | { op: 'upsert'; kind: 'subscriber'; item: Subscriber } | { op: 'upsert'; kind: 'waGroup'; item: WaGroup }
  | { op: 'upsert'; kind: 'task'; item: FarmTask } | { op: 'upsert'; kind: 'mound'; item: Mound }
  | { op: 'upsert'; kind: 'listing'; item: Listing } | { op: 'upsert'; kind: 'offer'; item: Offer }
  | { op: 'remove'; kind: Kind; id: string }
  | { op: 'workdays'; groupId: string; memberIds: string[]; date?: string };

type ListKey = 'crops' | 'groups' | 'plots' | 'batches' | 'runs' | 'stores' | 'items' | 'moves' | 'orders' | 'herds' | 'livestockEvents' | 'forestLogs' | 'fishLogs' | 'vslaGroups' | 'vslaTxs' | 'degradations' | 'containers' | 'containerLogs' | 'tollgates' | 'people' | 'words' | 'subscribers' | 'waGroups' | 'tasks' | 'mounds' | 'listings' | 'offers';
const LIST: Record<Kind, ListKey> = {
  crop: 'crops', group: 'groups', plot: 'plots', batch: 'batches', run: 'runs', store: 'stores', item: 'items', move: 'moves', order: 'orders',
  herd: 'herds', livestockEvent: 'livestockEvents', forestLog: 'forestLogs', fishLog: 'fishLogs',
  vslaGroup: 'vslaGroups', vslaTx: 'vslaTxs', degradation: 'degradations', container: 'containers', containerLog: 'containerLogs', tollgate: 'tollgates',
  person: 'people', word: 'words', subscriber: 'subscribers', waGroup: 'waGroups', task: 'tasks', mound: 'mounds', listing: 'listings', offer: 'offers'
};

export const newId = (prefix: string) => `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export function applyOps(reg: Register, ops: FarmOp[], at = new Date().toISOString()): Register {
  let r = reg;
  for (const o of ops) {
    if (o.op === 'workdays') {
      r = { ...r, groups: r.groups.map(g => g.id !== o.groupId || (o.date && g.lastRoll === o.date) ? g : { ...g, ...(o.date ? { lastRoll: o.date } : {}), members: g.members.map(m => o.memberIds.includes(m.id) ? { ...m, workDays: m.workDays + 1 } : m) }) };
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

// Who may send an op. Anyone signed in records store movements and orders, livestock/forest/fish
// log entries, and may add a pest name to a crop (the server checks nothing else on the crop
// changed); the rest (including defining a herd) needs an admin or group lead.
export function opAllowed(role: string, o: FarmOp, reg: Register): boolean {
  if (o.op === 'remove') return removeAllowed(role);
  if (editAllowed(role)) return true;
  if (o.op === 'upsert' && (o.kind === 'move' || o.kind === 'order' || o.kind === 'livestockEvent' || o.kind === 'forestLog' || o.kind === 'fishLog' || o.kind === 'vslaTx' || o.kind === 'degradation' || o.kind === 'containerLog' || o.kind === 'tollgate' || o.kind === 'person' || o.kind === 'word' || o.kind === 'task')) return true;
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
  if (o.op === 'upsert' && o.kind === 'herd') return (LIVESTOCK_SPECIES as readonly string[]).includes(o.item.species) && o.item.ownerId ? '' : 'a species and owner are required';
  if (o.op === 'upsert' && o.kind === 'livestockEvent') return o.item.herdId && o.item.qty > 0 && (LIVESTOCK_EVENTS as readonly string[]).includes(o.item.kind) ? '' : 'a herd, quantity above 0 and valid event type are required';
  if (o.op === 'upsert' && o.kind === 'forestLog') return (FOREST_PRODUCTS as readonly string[]).includes(o.item.product) && o.item.qty > 0 ? '' : 'a product and quantity above 0 are required';
  if (o.op === 'upsert' && o.kind === 'fishLog') return (FISH_SPECIES as readonly string[]).includes(o.item.species) && (FISH_EVENTS as readonly string[]).includes(o.item.kind) ? '' : 'a species and valid event type are required';
  if (o.op === 'upsert' && o.kind === 'vslaGroup') return (o.item as VslaGroup).name?.trim() ? '' : 'a VSLA name is required';
  if (o.op === 'upsert' && o.kind === 'vslaTx') return (o.item as VslaTx).vslaId && (o.item as VslaTx).amount > 0 && (VSLA_TX_TYPES as readonly string[]).includes((o.item as VslaTx).type) ? '' : 'a VSLA group, amount and valid type are required';
  if (o.op === 'upsert' && o.kind === 'degradation') return (o.item as DegradationAssessment).site?.trim() && Object.keys((o.item as DegradationAssessment).scores).length > 0 ? '' : 'a site and at least one indicator score are required';
  if (o.op === 'upsert' && o.kind === 'container') return (o.item as ContainerUnit).code?.trim() && (o.item as ContainerUnit).crop?.trim() ? '' : 'a code and crop are required';
  if (o.op === 'upsert' && o.kind === 'containerLog') return (o.item as ContainerLog).unitId?.trim() ? '' : 'a container unit is required';
  if (o.op === 'upsert' && o.kind === 'tollgate') return (o.item as TollgateRecord).vslaId?.trim() && (o.item as TollgateRecord).gate >= 1 && (o.item as TollgateRecord).gate <= 5 ? '' : 'a VSLA group and valid gate (1-5) are required';
  if (o.op === 'upsert' && o.kind === 'person') return personError(o.item) ? 'a person needs two names, a valid phone, an admin location and two next of kin' : '';
  if (o.op === 'upsert' && o.kind === 'task') return o.item.title?.trim() && /^d{4}-d{2}-d{2}$/.test(o.item.due) ? '' : 'a task needs a title and a due date';
  if (o.op === 'upsert' && o.kind === 'mound') return o.item.crest > 0 && o.item.crest <= 3 && o.item.id?.trim() ? '' : 'a mound needs a name and a crest height between 0 and 3 m';
  if (o.op === 'upsert' && o.kind === 'listing') return o.item.name?.trim() && o.item.qty > 0 && o.item.price >= 0 && (LISTING_STATUS as readonly string[]).includes(o.item.status) ? '' : 'a listing needs a name, a quantity above 0 and a price';
  if (o.op === 'upsert' && o.kind === 'offer') return o.item.buyer?.trim() && o.item.qty > 0 && o.item.price > 0 && (OFFER_STATUS_MARKET as readonly string[]).includes(o.item.status) ? '' : 'an offer needs a buyer, a quantity and a price above 0';
  if (o.op === 'upsert' && o.kind === 'subscriber') return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(o.item.email) ? '' : 'a valid email address is required';
  if (o.op === 'upsert' && o.kind === 'waGroup') return /^https:\/\/chat\.whatsapp\.com\/[A-Za-z0-9]+/.test(o.item.link) && o.item.name?.trim() ? '' : 'a name and a WhatsApp invite link (https://chat.whatsapp.com/…) are required';
  if (o.kind === 'plot' || o.kind === 'batch' || o.kind === 'store' || o.kind === 'item') return it.code?.trim() ? '' : 'a code is required';
  return it.name?.trim() ? '' : 'a name is required';
}

// Balance of each item in each store: everything in minus everything out.
export function balances(reg: Register) {
  const m = new Map<string, number>();
  for (const v of reg.moves ?? []) { const k = `${v.storeId}|${v.itemId}`; m.set(k, (m.get(k) ?? 0) + (v.dir === 'in' ? v.qty : -v.qty)); }
  return (storeId: string, itemId: string) => m.get(`${storeId}|${itemId}`) ?? 0;
}

// Current head count for a herd: opening + births + purchases − deaths − sales.
// Vaccination, treatment, milk and eggs are recorded but don't change the count.
export function herdCount(reg: Register, herdId: string): number {
  return (reg.livestockEvents ?? []).filter(e => e.herdId === herdId)
    .reduce((n, e) => n + (HERD_ADDS.includes(e.kind) ? e.qty : HERD_REMOVES.includes(e.kind) ? -e.qty : 0), 0);
}
export const herdLabel = (h: Herd) => `${h.species[0].toUpperCase()}${h.species.slice(1)} · ${h.ownerName}`;

// VSLA fund balance: savings + interest + fines + social-fund − loans − share-outs + repayments.
export function vslaBalance(reg: Register, vslaId: string): number {
  const adds: VslaTxType[] = ['savings', 'repayment', 'interest', 'fine', 'social-fund'];
  const subs: VslaTxType[] = ['loan', 'share-out'];
  return (reg.vslaTxs ?? []).filter(t => t.vslaId === vslaId)
    .reduce((n, t) => n + (adds.includes(t.type) ? t.amount : subs.includes(t.type) ? -t.amount : 0), 0);
}

export const personById = (reg: Register, id?: string) => id ? (reg.people ?? []).find(p => p.id === id) : undefined;
// The people in a group who are on the person register (members added before the register have no details).
export const groupPeople = (reg: Register, groupId: string): Person[] =>
  (reg.groups.find(g => g.id === groupId)?.members ?? []).flatMap(m => { const p = personById(reg, m.personId); return p ? [p] : []; });
// Group members as plain names, with the person id when there is one.
export const groupMembers = (reg: Register, groupId: string) => (reg.groups.find(g => g.id === groupId)?.members ?? []);

// Puts something the project produced (a goat, honey, fish) into a store as a sellable product:
// creates the item the first time and records an 'in' movement. Returns the ops and the movement id.
export function productToStore(reg: Register, a: { storeId: string; name: string; unit: string; qty: number; by: string; note: string; date: string; price?: number | null }): { ops: FarmOp[]; moveId: string } {
  const code = a.name.toUpperCase().replace(/[^A-Z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 16) || 'PRODUCT';
  const have = (reg.items ?? []).find(i => i.code === code);
  const ops: FarmOp[] = [];
  if (!have) ops.push({ op: 'upsert', kind: 'item', item: { id: code, code, name: a.name, unit: a.unit, kind: 'product', reorder: null, price: a.price ?? null } });
  const moveId = newId('mv');
  ops.push({ op: 'upsert', kind: 'move', item: { id: moveId, storeId: a.storeId, itemId: have?.id ?? code, date: a.date, dir: 'in', qty: a.qty, party: 'own production', orderId: '', by: a.by, note: a.note } });
  return { ops, moveId };
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

// ---- Home screen: zones and today's work come from the register and from what has been recorded ----
export type ZoneKey = 'ridge' | 'slope' | 'basin';
export interface ZoneSummary { plots: number; ha: number; mapped: number; crops: string[]; groups: number }
// What the register holds for a zone: plots, area of those with a measured area, crops, groups.
export function zoneSummary(reg: Register, zone: ZoneKey): ZoneSummary {
  const ps = reg.plots.filter(p => p.zone === zone);
  const crops = [...new Set(ps.flatMap(p => [p.crop, ...(p.crops ?? [])]).filter(Boolean))];
  return { plots: ps.length, ha: Math.round(ps.reduce((n, p) => n + (p.areaHa ?? 0), 0) * 100) / 100, mapped: ps.filter(p => p.areaHa != null).length, crops, groups: new Set(ps.map(p => p.groupId).filter(Boolean)).size };
}

export interface AutoTask { id: string; title: string; zone: string; why: string }
const DAY = 864e5;
const daysAgo = (iso: string | undefined, now: Date) => (iso ? Math.floor((now.getTime() - Date.parse(iso)) / DAY) : null);
// Jobs the app can see are due because nothing has been recorded lately. They are not saved: they go away once the record is made.
export function autoTasks(i: { now: Date; plots: Plot[]; checks: { at: string; plot: string }[]; gauge: { at: string }[]; depthMeasured: boolean }): AutoTask[] {
  const out: AutoTask[] = [];
  const g = daysAgo([...i.gauge].sort((a, b) => b.at.localeCompare(a.at))[0]?.at, i.now);
  if (g == null || g >= 3) out.push({ id: 'auto-gauge', title: 'Send the Bor river gauge reading', zone: 'All', why: g == null ? 'no gauge reading recorded yet' : `last gauge reading ${g} days ago` });
  if (!i.depthMeasured) out.push({ id: 'auto-depth', title: 'Record the water depth in the basin', zone: 'Basin', why: 'no depth reading in the last 2 weeks, so the flood model shows the design example' });
  const last = new Map<string, string>();
  for (const c of i.checks) if (!last.has(c.plot) || c.at > last.get(c.plot)!) last.set(c.plot, c.at);
  const due = i.plots.map(p => ({ p, d: daysAgo(last.get(p.code), i.now) })).filter(x => x.d == null || x.d >= 14).sort((a, b) => (b.d ?? 999) - (a.d ?? 999)).slice(0, 3);
  for (const { p, d } of due) out.push({ id: `auto-check-${p.id}`, title: `Crop check on ${p.code} (${p.crop})`, zone: p.zone[0].toUpperCase() + p.zone.slice(1), why: d == null ? 'never checked' : `last checked ${d} days ago` });
  return out;
}

// ---- Market ----
// Quantity of a listing not yet promised to a buyer: what was listed minus accepted and delivered offers.
export function listingLeft(reg: Register, l: Listing): number {
  const taken = (reg.offers ?? []).filter(o => o.listingId === l.id && (o.status === 'accepted' || o.status === 'delivered')).reduce((n, o) => n + o.qty, 0);
  return Math.max(0, l.qty - taken);
}
// Sales agreed in a year (accepted or delivered offers) in US dollars, and how many offers that was.
export function salesTotal(reg: Register, year: number): { usd: number; offers: number } {
  const done = (reg.offers ?? []).filter(o => (o.status === 'accepted' || o.status === 'delivered') && (o.answeredAt ?? o.at).startsWith(String(year)));
  return { usd: Math.round(done.reduce((n, o) => n + o.qty * o.price, 0) * 100) / 100, offers: done.length };
}
