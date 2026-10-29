// Starter dataset taken from the Claude Design prototype (AbukApp.dc.html).
// It seeds a fresh phone so every screen has content before the first sync.
// Live data from the server replaces these records as it arrives.

export type Lang = 'en' | 'ar' | 'din';
export type Screen =
  | 'home' | 'tools' | 'alerts' | 'gauge' | 'voice' | 'pest' | 'payout' | 'store' | 'trace' | 'p2p'
  | 'signin' | 'admin' | 'map' | 'flood' | 'season' | 'tasks' | 'plot' | 'harvest' | 'monitor'
  | 'sources' | 'process' | 'market' | 'guide' | 'species' | 'register' | 'herd'
  | 'vsla' | 'degradation' | 'container' | 'satellite' | 'readiness' | 'depth';
export type NavKey = 'home' | 'map' | 'season' | 'guide' | 'market';
export type HomeLayout = 'ledger' | 'almanac' | 'field';

export const ICONS: Record<NavKey, string> = {
  home: 'M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8 M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  map: 'M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z M15 5.764v15 M9 3.236v15',
  season: 'M8 2v4 M16 2v4 M3 10h18 M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
  guide: 'M12 7v14 M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z',
  market: 'M2 7l4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7 M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8 M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4 M2 7h20 M22 7v3a2 2 0 0 1-2 2 2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 16 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 12 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 8 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 4 12a2 2 0 0 1-2-2V7'
};

export const T = {
  en: { home: 'Home', map: 'Map', season: 'Season', guide: 'Guide', market: 'Market', greet: 'Good morning', tasks: "Today's work", zones: 'Zones', seeAll: 'All tasks', offline: 'Offline', online: 'Online', queued: 'to sync', synced: 'Synced' },
  ar: { home: 'الرئيسية', map: 'الخريطة', season: 'الموسم', guide: 'الدليل', market: 'السوق', greet: 'صباح الخير', tasks: 'أعمال اليوم', zones: 'المناطق', seeAll: 'كل المهام', offline: 'غير متصل', online: 'متصل', queued: 'للمزامنة', synced: 'تمت المزامنة' }
};

export const TITLES: Record<'en' | 'ar', Record<Exclude<Screen, 'species'>, string>> = {
  en: { home: 'Abuk Project', map: 'Farm map', flood: 'Flood model', season: 'Crop calendar', tasks: 'Tasks', plot: 'Plot B‑07', harvest: 'Harvest log', process: 'Processing', market: 'Market', guide: 'Species guide', monitor: 'Crop check', sources: 'Data sources', signin: 'Sign in', admin: 'Access & keys', tools: 'Field tools', alerts: 'Flood SMS alerts', gauge: 'River gauge', voice: 'Pictures & voice', pest: 'Pest photo check', payout: 'Work days & payout', store: 'Seed & input store', trace: 'Traceable batches', p2p: 'Phone‑to‑phone sync', register: 'Farm register', herd: 'Livestock, forest & fish', vsla: 'VSLA savings & loans', degradation: 'Land assessment', container: 'Container farming', satellite: 'Satellite indices', readiness: 'Finance readiness', depth: 'Water depth' },
  ar: { home: 'مشروع أبوك', map: 'خريطة المزرعة', flood: 'نموذج الفيضان', season: 'تقويم المحاصيل', tasks: 'المهام', plot: 'القطعة B‑07', harvest: 'سجل الحصاد', process: 'المعالجة', market: 'السوق', guide: 'دليل الأنواع', monitor: 'فحص المحصول', sources: 'مصادر البيانات', signin: 'تسجيل الدخول', admin: 'الوصول والمفاتيح', tools: 'أدوات الحقل', alerts: 'تنبيهات الفيضان', gauge: 'قراءة المقياس', voice: 'صور وصوت', pest: 'فحص الآفات', payout: 'أيام العمل والأجور', store: 'مخزن البذور', trace: 'تتبع الزجاجات', p2p: 'مزامنة الهواتف', register: 'سجل المزرعة', herd: 'الثروة الحيوانية والغابات والأسماك', vsla: 'الادخار والقروض', degradation: 'تقييم الأرض', container: 'الزراعة في الحاويات', satellite: 'مؤشرات الأقمار الصناعية', readiness: 'الجاهزية المالية', depth: 'عمق المياه' }
};

export interface Task { id: number; t: string; zone: string; who: string; due: 'today' | 'week'; done: boolean }
export const TASKS: Task[] = [
  { id: 1, t: 'Check mound B‑05 for erosion as water drops', zone: 'Basin', who: 'Group 4', due: 'today', done: false },
  { id: 2, t: 'Cut Moringa leaf block R‑02 (40‑day cycle)', zone: 'Ridge', who: 'Group 1', due: 'today', done: false },
  { id: 3, t: 'Send Bor river gauge reading by SMS', zone: 'All', who: 'Garang Mabior', due: 'today', done: true },
  { id: 4, t: 'Turn shade‑drying trays, leaf batch 27 Oct', zone: 'Shed', who: 'Nyandeng Ajak', due: 'today', done: false },
  { id: 5, t: 'Tap gum arabic trees, boundary row R‑05', zone: 'Ridge', who: 'Group 2', due: 'today', done: false },
  { id: 6, t: 'Count cowpea & Feterita seed for recession sowing', zone: 'Store', who: 'Group 4', due: 'week', done: false },
  { id: 7, t: 'Clear groundnut stubble, slope S‑04', zone: 'Slope', who: 'Group 3', due: 'week', done: false },
  { id: 8, t: 'Re-pin 6 Balanites trees missing GPS, row B‑07', zone: 'Basin', who: 'Group 4', due: 'week', done: false }
];

export interface Harvest { crop: string; plot: string; kg: number; who: string; date: string; synced: boolean; rid?: string }
export const HARV: Harvest[] = [
  { crop: 'Moringa leaf (fresh)', plot: 'R‑02', kg: 186, who: 'Group 1', date: '27 Oct', synced: true },
  { crop: 'Okra', plot: 'S‑04', kg: 42, who: 'Group 3', date: '26 Oct', synced: true },
  { crop: 'Sesame', plot: 'S‑01', kg: 310, who: 'Group 5', date: '22 Oct', synced: true },
  { crop: 'Jute mallow (kudra)', plot: 'B‑03', kg: 64, who: 'Ayen Kuol', date: '21 Oct', synced: true }
];

export interface Species { key: string; g: 'trees' | 'field'; name: string; sci: string; ar: string; local: string; zone: string; season: string; notes: string; uses: string; chain: string }
export const SPECIES: Species[] = [
  { key: 'balanites', g: 'trees', name: 'Desert date', sci: 'Balanites aegyptiaca', ar: 'هجليج', local: 'Thou (Dinka) · lalob', zone: 'Basin, on 1 m mounds', season: 'Fruit Jan–Mar', notes: 'Grafted onto wild rootstock from elite mother trees, it fruits in 2–3 years. Plant on raised ridges 1 m high, 7 m apart, so the crown stays above the two‑month flood while deep taproots reach the water table through the dry season. Thin canopy lets recession crops grow beneath.', uses: 'Kernel oil for cosmetics and cooking; press cake is high‑protein livestock feed; pulp is eaten and sold; bark and fruit extracts are used against parasites; shells make good fuel.', chain: 'Collection & de‑pulping → cracking & kernel extraction → oil pressing → refining & packaging → retail / cosmetic buyers' },
  { key: 'moringa', g: 'trees', name: 'Moringa', sci: 'Moringa oleifera', ar: 'مورينجا', local: 'Ridge only', zone: 'Dry ridge', season: 'Leaf cut every 35–45 days', notes: 'Needs sandy, well‑drained soil; never plant in the basin. On heavy clay, work river sand, compost and gypsum into the top 30 cm. Leaf blocks at 1 × 1 m; pod rows wider.', uses: 'Leaf powder for nutrition, pods as vegetable, seed oil, seed cake for water clarifying.', chain: 'Pruning / harvest → shade‑drying → milling → local market & household use, feed' },
  { key: 'shea', g: 'trees', name: 'Shea', sci: 'Vitellaria paradoxa ssp. nilotica', ar: 'لولو', local: 'Lulu', zone: 'Ridge boundary', season: 'Fruit Apr–Jun', notes: 'The Nile subspecies gives a soft, liquid‑rich butter prized by buyers. Slow to bear from seed; protect existing wild trees and add grafted seedlings along the ridge edge.', uses: 'Shea butter and oil for cooking and cosmetics; fruit pulp eaten fresh.', chain: 'Fruit collection → de‑pulping → drying nuts → roasting & pounding → butter → market' },
  { key: 'tamarind', g: 'trees', name: 'Tamarind', sci: 'Tamarindus indica', ar: 'عرديب', local: 'Aradeib', zone: 'Ridge & slope', season: 'Pods Jan–Mar', notes: 'Tolerates drought and occasional waterlogging at its edges. Good windbreak and shade tree for the processing area.', uses: 'Pulp for drinks and sauces, sold dried; leaves and bark in home remedies; timber.', chain: 'Pod harvest → de‑shelling → pressed pulp blocks → market' },
  { key: 'gum', g: 'trees', name: 'Gum arabic', sci: 'Senegalia senegal', ar: 'هشاب', local: 'Hashab', zone: 'Dry ridge', season: 'Tap Nov–Feb', notes: 'Fixes nitrogen and holds sandy soil. Tap after the rains stop; collect nodules 4–6 weeks later.', uses: 'Gum for food and beverage industry export; pods as fodder; living fence.', chain: 'Tapping → collection → cleaning & grading → export traders' },
  { key: 'sorghum', g: 'field', name: 'Sorghum', sci: 'Sorghum bicolor (Feterita)', ar: 'ذرة', local: 'Feterita / local', zone: 'Basin, post‑flood', season: 'Sow Dec · harvest Mar', notes: 'Choose tall local recession varieties that finish on stored soil moisture with no irrigation. Roots bind cracking vertisol clay.', uses: 'Staple grain, brewing, stalks for fodder and building.', chain: 'Harvest → threshing → household store & local market' },
  { key: 'cowpea', g: 'field', name: 'Cowpea', sci: 'Vigna unguiculata', ar: 'لوبيا', local: '', zone: 'Basin, post‑flood', season: 'Dec–Feb', notes: 'Broadcast straight into the wet silt as the water drops. Fixes nitrogen for the Balanites rows.', uses: 'Grain and leaves for food; haulms for livestock.', chain: 'Harvest → drying → market' },
  { key: 'jute', g: 'field', name: 'Jute mallow', sci: 'Corchorus olitorius', ar: 'ملوخية', local: 'Kudra', zone: 'Basin, post‑flood', season: 'Dec–Mar', notes: 'Cut tender tops every 2–3 weeks to keep plants bushy and delay seeding.', uses: 'Leaf vegetable, fresh or dried.', chain: 'Cutting → fresh market or sun‑drying' },
  { key: 'groundnut', g: 'field', name: 'Groundnut', sci: 'Arachis hypogaea', ar: 'فول سوداني', local: '', zone: 'Slope', season: 'May–Aug', notes: 'Needs the lighter, better‑drained slope soils; lift before the flood reaches the slope.', uses: 'Nuts, paste and oil; haulms for fodder.', chain: 'Lifting → drying → shelling → paste / oil → market' },
  { key: 'sesame', g: 'field', name: 'Sesame', sci: 'Sesamum indicum', ar: 'سمسم', local: '', zone: 'Slope', season: 'Jun–Sep', notes: 'Drought‑hardy; harvest stalks before pods shatter and dry them upright.', uses: 'Oil seed, paste; strong cash crop.', chain: 'Cutting → stooking → threshing → traders' },
  { key: 'millet', g: 'field', name: 'Bulrush millet', sci: 'Pennisetum glaucum', ar: 'دخن', local: 'Dukhn', zone: 'Slope & ridge', season: 'Jun–Sep', notes: 'Earliest grain of the year; fills the hunger gap before sorghum.', uses: 'Porridge and flour; stalks for fencing.', chain: 'Harvest → threshing → household & market' },
  { key: 'okra', g: 'field', name: 'Okra', sci: 'Abelmoschus esculentus', ar: 'بامية', local: '', zone: 'Slope, under Moringa', season: 'May–Aug', notes: 'Early rainfed or irrigated understory crop; pick every 2–3 days.', uses: 'Fresh and dried pods.', chain: 'Picking → fresh or sun‑dried → market' }
];

// [name, species key, bars as [startMonth, endMonth, 'g'rowing | 'h'arvest]]
export const SEASON: { zone: string; rows: [string, string, [number, number, 'g' | 'h'][]][] }[] = [
  { zone: 'Zone 1 · Dry ridge', rows: [['Moringa', 'moringa', [[0, 11, 'g']]], ['Gum arabic', 'gum', [[10, 11, 'h'], [0, 1, 'h']]], ['Shea', 'shea', [[3, 5, 'h']]], ['Tamarind', 'tamarind', [[0, 2, 'h']]]] },
  { zone: 'Zone 2 · Slope', rows: [['Groundnut', 'groundnut', [[4, 6, 'g'], [7, 7, 'h']]], ['Sesame', 'sesame', [[5, 7, 'g'], [8, 8, 'h']]], ['Bulrush millet', 'millet', [[5, 7, 'g'], [8, 8, 'h']]], ['Okra', 'okra', [[4, 7, 'h']]]] },
  { zone: 'Zone 3 · Basin', rows: [['Balanites', 'balanites', [[0, 2, 'h']]], ['Sorghum', 'sorghum', [[11, 11, 'g'], [0, 1, 'g'], [2, 2, 'h']]], ['Cowpea', 'cowpea', [[11, 11, 'g'], [0, 1, 'h']]], ['Jute mallow', 'jute', [[11, 11, 'g'], [0, 2, 'h']]]] }
];

export interface Source { id: string; kind: 'Drive' | 'GEE' | 'GitHub'; name: string; path: string; size: string; last: string; feeds: string; on: boolean }
export const SOURCES: Source[] = [
  { id: 'bull', kind: 'Drive', name: 'County bulletin, row for your county', path: 'county_bulletin › county_bulletin_latest.xlsx', size: '1 row of 79', last: 'not pulled yet', feeds: 'soil, rain, alert', on: true },
  { id: 'ens', kind: 'Drive', name: 'Rain ensemble, 50 members, 15 days', path: 'county_bulletin › forecast_log_ens.csv', size: 'your county only', last: 'not pulled yet', feeds: 'rainfall forecast', on: true },
  { id: 'stat', kind: 'Drive', name: 'Altimetry station status', path: 'station_status.csv · stations within radius', size: 'filtered', last: 'not pulled yet', feeds: 'river level, flood status', on: true },
  { id: 'alt', kind: 'Drive', name: 'Water-level series (DAHITI + Hydroweb)', path: 'merged_altimetry_stations.csv · nearby rows only', size: '41.8 MB → ~60 KB', last: 'not pulled yet', feeds: 'river inflow trend', on: true },
  { id: 'ifs', kind: 'Drive', name: 'ECMWF IFS daily: temp, soil water, runoff', path: 'cache_ecmwf_ifs_daily.csv', size: 'nearby stations', last: 'not pulled yet', feeds: 'temperature, runoff', on: true },
  { id: 'sm', kind: 'GEE', name: 'Soil moisture (SMAP SPL4SMGP)', path: 'Earth Engine asset · clipped to radius', size: '9 km grid', last: 'not pulled yet', feeds: 'soil moisture', on: true },
  { id: 'fx', kind: 'GEE', name: 'Flood extent', path: 'Earth Engine asset · clipped to radius', size: 'raster tile', last: 'not pulled yet', feeds: 'flood extent', on: true },
  { id: 'payam', kind: 'GitHub', name: 'Payam, county and state boundaries', path: 'South-Sudan-Admin-Geojson › ssd_A3.json (517 payams)', size: '340 KB, in the app', last: 'works offline', feeds: 'payam / county / state from GPS', on: true }
];

// Location and water fields are kept on the phone so the home briefing and flood model can use nearby checks.
export interface MonRecord { plot: string; crop: string; acts: string; ew: string; date: string; cond: number; synced: boolean; rid?: string; field?: string; at?: string; lat?: number; lon?: number; water?: string; depthCm?: number | null; around?: string; aroundDepthCm?: number | null; trend?: string }
export const MON: MonRecord[] = [
  { plot: 'B‑03', crop: 'Jute mallow', acts: 'Weeding', ew: 'EW‑014', date: '27 Oct', cond: 4, synced: true },
  { plot: 'S‑04', crop: 'Groundnut', acts: 'Harvest, Pest scouting', ew: 'EW‑014', date: '25 Oct', cond: 3, synced: true },
  { plot: 'R‑02', crop: 'Moringa', acts: 'Pruning', ew: 'EW‑022', date: '24 Oct', cond: 5, synced: true }
];

export const TOOLS: [string, Screen, string, string][] = [
  ['i', 'alerts', 'Flood SMS alerts', 'Text group leads from this phone before a crest is overtopped'],
  ['ii', 'gauge', 'River gauge reading', 'Type the Bor gauge level; it feeds the flood model'],
  ['iii', 'voice', 'Pictures & voice', 'Big icons and recorded Dinka prompts'],
  ['iv', 'pest', 'Pest photo check', 'Match a photo to the local library; worker confirms'],
  ['v', 'payout', 'Work days & payout', "Roll‑call, then each member's share of sales"],
  ['vi', 'store', 'Seed & input store', 'Stock reserved against planting windows'],
  ['vii', 'trace', 'Traceable batches', 'QR label on each product: crop, plot GPS, harvest, co‑op'],
  ['viii', 'p2p', 'Phone‑to‑phone sync', 'Swap records by Bluetooth in the field'],
  ['ix', 'herd', 'Livestock, forest & fish', 'Herd counts, forest collection and pond or catch records']
];

export const PICTO: [string, string, string][] = [
  ['plant', 'Planting', 'M7 20h10 M10 20c5.5-2.5.8-6.4 3-10 M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8z M14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2z'],
  ['weed', 'Weeding', 'M2 22v-5l5-5 5 5-5 5z M9.5 14.5 16 8 M17 2l5 5-.5.5a3.54 3.54 0 0 1-5 0a3.54 3.54 0 0 1 0-5L17 2'],
  ['harvest', 'Harvest', 'M2 22 16 8 M3.47 12.53 5 11l1.53 1.53a3.5 3.5 0 0 1 0 4.94L5 19l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z M7.47 8.53 9 7l1.53 1.53a3.5 3.5 0 0 1 0 4.94L9 15l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z M11.47 4.53 13 3l1.53 1.53a3.5 3.5 0 0 1 0 4.94L13 11l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z M20 2h2v2a4 4 0 0 1-4 4h-2V6a4 4 0 0 1 4-4Z'],
  ['water', 'Water rising', 'M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1 M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1 M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1'],
  ['pest', 'Pests seen', 'm8 2 1.88 1.88 M14.12 3.88 16 2 M9 7.13v-1a3.003 3.003 0 1 1 6 0v1 M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6 M12 20v-9 M6.53 9C4.6 8.8 3 7.1 3 5 M6 13H2 M3 21c0-2.1 1.7-3.9 3.8-4 M20.97 5c0 2.1-1.6 3.8-3.5 4 M22 13h-4 M17.2 17c2.1.1 3.8 1.9 3.8 4'],
  ['help', 'Call the lead', 'M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z']
];

export const MEMBERS: [string, number][] = [['Achol Deng', 41], ['Nyibol Garang', 38], ['Majok Ater', 36], ['Akuol Chol', 40], ['Bol Mayen', 29], ['Adut Kuol', 33], ['Ajak Deng', 27], ['Nyankiir Malual', 39], ['Kuol Arok', 22], ['Achan Majak', 35], ['Thon Akec', 31], ['Abuk Ayuel', 37]];

// [name, unit, inStock, needed, used for, issue step]
export const STORE: [string, string, number, number, string, number][] = [
  ['Cowpea seed', 'kg', 180, 240, 'Recession sowing · ~4 Dec', 10], ['Feterita sorghum seed', 'kg', 260, 225, 'Recession sowing · ~4 Dec', 10], ['Jute mallow (kudra) seed', 'kg', 4, 6, 'Recession sowing · ~4 Dec', 1],
  ['Balanites scions, elite trees', 'pcs', 320, 280, 'Grafting · Jan', 20], ['Gypsum', 'kg', 900, 1200, 'Ridge soil prep · Feb', 50], ['Sacks, 50 kg', 'pcs', 140, 120, 'Sorghum harvest · Mar', 10], ['Amber bottles, 1 L', 'pcs', 60, 150, 'Oil pressing · Mar', 10]
];

export interface Batch { id: string; plot: string; fruit: string; pressed: string; bottles: string; place: string }
export const BATCHES: Batch[] = [
  { id: 'BAL‑26‑03', plot: 'B‑07 · Group 4 (12 farmers)', fruit: 'Jan–Feb 2026', pressed: '12 Mar 2026, cold‑pressed', bottles: '132 × 1 L', place: 'Duk County, Jonglei · 7.73° N 31.40° E' },
  { id: 'BAL‑26‑02', plot: 'B‑03 · Ayen Kuol (individual)', fruit: 'Feb 2026', pressed: '28 Feb 2026, cold‑pressed', bottles: '41 × 1 L', place: 'Duk County, Jonglei · 7.73° N 31.40° E' },
  { id: 'BAL‑26‑01', plot: 'B‑12 · Group 6 (14 farmers)', fruit: 'Jan 2026', pressed: '9 Feb 2026, cold‑pressed', bottles: '88 × 1 L', place: 'Duk County, Jonglei · 7.73° N 31.40° E' }
];

export const MOUNDS: [string, number][] = [['B‑01', 1.00], ['B‑02', 1.00], ['B‑03', 0.98], ['B‑04', 0.95], ['B‑05', 0.82], ['B‑06', 1.00], ['B‑07', 1.00], ['B‑08', 0.94]];

export const ZONES = [
  { n: '1', key: 'ridge', name: 'Dry ridge', ha: '10 ha', crops: 'Moringa, gum arabic, shea, tamarind', status: 'cut due' },
  { n: '2', key: 'slope', name: 'Slope', ha: '8 ha', crops: 'Groundnut, sesame, millet, okra', status: 'drying' },
  { n: '3', key: 'basin', name: 'Floodplain basin', ha: '22 ha', crops: 'Balanites on mounds · recession crops', status: '0.92 m water' }
] as const;

export const PROC = {
  balanites: { label: 'Balanites oil', intro: 'Last season’s desert‑date fruit, Jan–Mar 2026. This season’s collection starts once fruit drops in January.', steps: [
    { name: 'Fruit collected', out: '2,400 kg', note: '7 groups, basin rows B‑01–B‑24' },
    { name: 'De‑pulped & dried nuts', out: '1,460 kg', note: '940 kg pulp sold as food and feed' },
    { name: 'Cracked → kernels', out: '390 kg', note: 'shells kept as fuel for the shed' },
    { name: 'Pressed', out: '148 L', note: '+ 220 kg protein feed cake' },
    { name: 'Refined & bottled', out: '132 × 1 L', note: '46 bottles still in store' }],
    foot: 'Yield: 6.2 L oil per 100 kg fruit. Target for 2027: 9 L with the new screw press.' },
  moringa: { label: 'Moringa powder', intro: 'Rolling leaf harvest from ridge blocks every 35–45 days.', steps: [
    { name: 'Fresh leaves cut', out: '1,120 kg', note: 'blocks R‑01–R‑04, last 3 cycles' },
    { name: 'Shade‑dried', out: '245 kg', note: '5 days on mesh trays, out of sun' },
    { name: 'Milled', out: '228 kg', note: 'hammer mill, sieved' },
    { name: 'Packed', out: '456 × 500 g', note: '120 packs in stock' }],
    foot: 'Drying ratio 4.6 : 1. Keep powder sealed: it loses colour in light.' }
};

export const LISTINGS = [
  { name: 'Balanites oil, cold‑pressed', unit: 'per 1 L', price: '$14', stock: '46 bottles', offers: '3 offers' },
  { name: 'Moringa leaf powder', unit: 'per 500 g', price: '$6', stock: '120 packs', offers: '5 offers' },
  { name: 'Balanites feed cake', unit: 'per 50 kg', price: '$9', stock: '4 sacks', offers: '1 offer' },
  { name: 'Gum arabic, grade 2', unit: 'per kg', price: '$3.20', stock: '85 kg', offers: 'none yet' },
  { name: 'Sesame seed', unit: 'per 50 kg', price: '$38', stock: '6 sacks', offers: '2 offers' }
];

export const LEADS = [['Achol Deng', 'Group 4', 'B‑01–B‑08'], ['Deng Bol', 'Group 6', 'B‑09–B‑16'], ['Kuol Arok', 'Group 2', 'B‑17–B‑24'], ['Nyandeng Ajak', 'EW‑022', 'all rows']] as const;

export const P2P_PEERS: [string, string, number][] = [['Deng Bol · Group 6', '12 m', 52], ['Nyandeng Ajak · EW‑022', '40 m', 71], ['Kuol Arok · Group 2', '85 m', 19], ['Akuol Chol · Group 4', '6 m', 8]];

export const CROP_OPTIONS = ['Moringa leaf (fresh)', 'Balanites fruit', 'Gum arabic', 'Shea fruit', 'Tamarind pods', 'Sorghum', 'Cowpea', 'Groundnut', 'Sesame', 'Bulrush millet', 'Okra', 'Jute mallow (kudra)'];
export const PLOT_OPTIONS = ['R‑02', 'R‑05', 'S‑01', 'S‑04', 'B‑03', 'B‑07'];
export const MON_PLOTS = ['B‑07 · Group 4', 'B‑03 · Ayen Kuol', 'B‑12 · Group 6', 'S‑04 · Group 3', 'S‑01 · Group 5', 'R‑02 · Group 1', 'R‑05 · Group 2'];
export const MON_CROPS = ['Cowpea', 'Sorghum (Feterita)', 'Jute mallow', 'Groundnut', 'Sesame', 'Bulrush millet', 'Okra', 'Moringa', 'Balanites', 'Gum arabic', 'Shea', 'Tamarind'];
export const ACTIVITIES = ['Land prep', 'Planting', 'Weeding', 'Thinning', 'Fertilising', 'Pest scouting', 'Spraying', 'Pruning', 'Grafting', 'Harvest'];
export const PESTS = ['None', 'Aphids', 'Fall armyworm', 'Striga weed', 'Leaf blight', 'Termites', 'Birds', 'Livestock damage'];
export const STAGES = ['Seedbed', 'Vegetative', 'Flowering', 'Mature'];
export const SKIES = ['Sunny', 'Cloudy', 'Rain', 'Windy'];

// Approximate farm centroid used until a plot is mapped on site.
export const FARM = { lat: 7.731, lon: 31.402, county: 'Duk', state: 'Jonglei' };
