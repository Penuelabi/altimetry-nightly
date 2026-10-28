// Common pests and diseases of the farm's crops in South Sudan, for the pest check dropdown.
// Each entry lists the crops (by name keyword) and plant parts where it shows, what to look for,
// and a first, low-cost action. An extension worker confirms before any treatment is advised.
// A crop added later is matched by keyword (e.g. "Maize" → cereals); names workers type in
// under "Other" are saved on the crop in the Farm register and offered next time.
import type { Crop } from './farm';

export type Part = 'leaf' | 'stem' | 'root' | 'flower' | 'fruit' | 'seed' | 'whole';
export const PARTS: [Part, string][] = [
  ['leaf', 'Leaf'], ['stem', 'Stem / trunk'], ['root', 'Root'], ['flower', 'Flower'], ['fruit', 'Fruit, pod or head'], ['seed', 'Seed / grain in store'], ['whole', 'Whole plant']
];

export interface PestInfo { name: string; type: 'insect' | 'disease' | 'weed' | 'animal' | 'other'; crops: string[]; parts: Part[]; signs: string; action: string }

const CEREAL = ['sorghum', 'feterita', 'millet', 'maize', 'rice', 'wheat'];
const LEGUME = ['cowpea', 'groundnut', 'bean', 'pea', 'soy', 'pigeon', 'lablab'];
const TREE = ['moringa', 'balanites', 'gum', 'acacia', 'shea', 'tamarind', 'mango', 'neem', 'baobab'];
const ALL = ['*'];

export const PEST_LIBRARY: PestInfo[] = [
  // cereals
  { name: 'Fall armyworm', type: 'insect', crops: [...CEREAL], parts: ['leaf', 'stem'], signs: 'Ragged holes and sawdust-like frass in the leaf whorl; green-brown caterpillars with a pale inverted Y on the head.', action: 'Hand-pick larvae at dawn; put sand, ash or neem-seed extract into the whorls; scout 20 plants per plot weekly.' },
  { name: 'Stem borer', type: 'insect', crops: [...CEREAL], parts: ['stem', 'leaf'], signs: 'Rows of small holes on unrolling leaves, dead heart in young plants, tunnels and frass inside stems.', action: 'Pull and destroy dead-heart plants; after harvest, cut stalks low and burn or feed them out.' },
  { name: 'Sorghum shoot fly', type: 'insect', crops: ['sorghum', 'feterita', 'millet'], parts: ['stem', 'whole'], signs: 'Central shoot of young seedlings dries (dead heart) 1–4 weeks after emergence.', action: 'Sow early with the first rains and evenly in the area; raise the seed rate slightly and thin later.' },
  { name: 'Sorghum midge', type: 'insect', crops: ['sorghum', 'feterita'], parts: ['flower', 'fruit'], signs: 'Small orange flies at flowering; empty, chaffy grains in the head.', action: 'Sow at the same time as neighbours so flowering is uniform; remove wild sorghum around plots.' },
  { name: 'Head bugs', type: 'insect', crops: ['sorghum', 'feterita', 'millet'], parts: ['fruit'], signs: 'Bugs on heads at milk stage; shrivelled, discoloured grain.', action: 'Shake heads into a bucket of soapy water in the morning; harvest promptly at maturity.' },
  { name: 'Millet head miner', type: 'insect', crops: ['millet'], parts: ['fruit', 'flower'], signs: 'Spiral tracks on the head where the larva has eaten flowers and grain.', action: 'Deep ploughing after harvest exposes pupae; report heavy damage to the extension worker.' },
  { name: 'Downy mildew', type: 'disease', crops: ['millet', 'sorghum', 'feterita', 'maize'], parts: ['leaf', 'whole'], signs: 'Yellow streaks on leaves with white down beneath in the morning; heads turn leafy ("green ear").', action: 'Pull and burn infected plants early; keep seed only from healthy plants.' },
  { name: 'Grain mould', type: 'disease', crops: [...CEREAL], parts: ['fruit', 'seed'], signs: 'Pink, black or white mould on grains when rain falls at maturity.', action: 'Harvest as soon as grain is hard; dry heads on a raised platform before threshing.' },
  { name: 'Anthracnose', type: 'disease', crops: ['sorghum', 'feterita'], parts: ['leaf', 'stem'], signs: 'Small round to oval red-purple spots with straw centres on leaves.', action: 'Rotate with legumes; remove crop residue after harvest.' },
  { name: 'Covered smut', type: 'disease', crops: ['sorghum', 'feterita'], parts: ['fruit'], signs: 'Grains replaced by grey-white sacs full of black powder.', action: 'Use clean seed; treat seed with ash or an approved fungicide before sowing.' },
  { name: 'Maize streak virus', type: 'disease', crops: ['maize'], parts: ['leaf'], signs: 'Broken yellow streaks along leaf veins; stunted plants.', action: 'Pull infected young plants; avoid late sowing next to older maize.' },
  { name: 'Striga (witchweed)', type: 'weed', crops: [...CEREAL, 'cowpea'], parts: ['root', 'whole'], signs: 'Pink-purple (or white) flowered weeds at the crop base; crop wilts and yellows as if dry.', action: 'Hand-pull before it flowers and burn; rotate with legumes; add manure.' },
  { name: 'Quelea and other birds', type: 'animal', crops: [...CEREAL], parts: ['fruit'], signs: 'Flocks on heads at milk to dough stage; grain stripped.', action: 'Scare at dawn and dusk; harvest promptly; report large flocks.' },
  // legumes
  { name: 'Cowpea aphid', type: 'insect', crops: [...LEGUME], parts: ['leaf', 'stem', 'flower'], signs: 'Clusters of small black insects on shoot tips and pods; curled leaves, sticky honeydew.', action: 'Spray neem-seed extract or soapy water; encourage ladybirds; remove heavily infested tips.' },
  { name: 'Legume pod borer (Maruca)', type: 'insect', crops: ['cowpea', 'bean', 'pigeon', 'lablab'], parts: ['flower', 'fruit'], signs: 'Webbed flowers and pods, holes in pods with frass.', action: 'Neem-seed extract at flowering; pick and destroy webbed flowers and pods.' },
  { name: 'Flower thrips', type: 'insect', crops: ['cowpea', 'bean', 'groundnut'], parts: ['flower'], signs: 'Flowers brown and drop; few pods set.', action: 'Neem-seed extract at flower bud stage; intercrop with sorghum.' },
  { name: 'Pod-sucking bugs', type: 'insect', crops: [...LEGUME], parts: ['fruit'], signs: 'Shrivelled pods and seeds with dark puncture marks.', action: 'Hand-collect bugs in the morning; harvest dry pods quickly.' },
  { name: 'Bruchid weevils (store)', type: 'insect', crops: [...LEGUME, 'balanites', 'tamarind'], parts: ['seed'], signs: 'Round exit holes in stored seed; powder in the bag.', action: 'Dry seed well; store in sealed hermetic bags or mix with ash.' },
  { name: 'Groundnut rosette', type: 'disease', crops: ['groundnut'], parts: ['leaf', 'whole'], signs: 'Stunted bushy plants with small yellow or dark green crinkled leaves; spread by aphids.', action: 'Sow early and at close spacing; pull infected plants; control aphids.' },
  { name: 'Groundnut leaf spot', type: 'disease', crops: ['groundnut'], parts: ['leaf'], signs: 'Brown (early) or black (late) round spots; leaves drop.', action: 'Rotate crops; remove volunteer plants; report if spreading fast.' },
  { name: 'Cowpea mosaic virus', type: 'disease', crops: ['cowpea', 'bean'], parts: ['leaf'], signs: 'Light and dark green mottled, puckered leaves.', action: 'Pull infected plants early; use seed from healthy plants; control aphids.' },
  { name: 'Aflatoxin mould (store)', type: 'disease', crops: ['groundnut', 'maize', 'sorghum', 'sesame'], parts: ['seed'], signs: 'Yellow-green powdery mould on kernels.', action: 'Do not eat or sell mouldy kernels; dry quickly to below 8% moisture; sort out damaged nuts.' },
  // sesame, vegetables
  { name: 'Sesame webworm', type: 'insect', crops: ['sesame'], parts: ['leaf', 'flower', 'fruit'], signs: 'Leaves webbed together at shoot tips; bored capsules.', action: 'Pick and destroy webbed tips; neem-seed extract early.' },
  { name: 'Sesame phyllody', type: 'disease', crops: ['sesame'], parts: ['flower', 'whole'], signs: 'Flowers turn into green leafy structures; no capsules.', action: 'Pull and burn infected plants; control leafhoppers.' },
  { name: 'Bacterial blight', type: 'disease', crops: ['sesame', 'cotton', 'bean'], parts: ['leaf', 'stem'], signs: 'Water-soaked angular spots turning brown; leaves fall.', action: 'Use clean seed; rotate; remove infected residue.' },
  { name: 'Flea beetles', type: 'insect', crops: ['okra', 'jute', 'mallow', 'kudra', 'amaranth', 'sesame'], parts: ['leaf'], signs: 'Many small round shot-holes in leaves; tiny jumping beetles.', action: 'Neem-seed extract or wood ash on leaves; sow at the start of the rains.' },
  { name: 'Cotton bollworm', type: 'insect', crops: ['okra', 'sorghum', 'cowpea', 'tomato', 'cotton'], parts: ['fruit', 'flower'], signs: 'Round holes in pods or fruits with a caterpillar inside.', action: 'Pick damaged pods; neem-seed extract; check twice a week.' },
  { name: 'Whitefly', type: 'insect', crops: ['okra', 'tomato', 'cassava', 'bean'], parts: ['leaf'], signs: 'Clouds of tiny white insects under leaves; yellowing, sticky leaves.', action: 'Yellow sticky traps; neem-seed extract under the leaves.' },
  { name: 'Okra leaf curl / yellow vein virus', type: 'disease', crops: ['okra'], parts: ['leaf'], signs: 'Leaves curl, veins yellow; plant stunted.', action: 'Pull infected plants early; control whitefly.' },
  { name: 'Root-knot nematodes', type: 'other', crops: ['okra', 'jute', 'mallow', 'kudra', 'tomato', 'moringa'], parts: ['root', 'whole'], signs: 'Swollen knots on roots; plants wilt at midday.', action: 'Rotate with cereals; add manure; uproot and burn infected roots.' },
  { name: 'Damping off', type: 'disease', crops: ['jute', 'mallow', 'kudra', 'moringa', 'tomato', 'okra'], parts: ['stem', 'whole'], signs: 'Seedlings collapse at soil level.', action: 'Sow in well-drained beds; avoid overwatering; thin crowded seedlings.' },
  // trees
  { name: 'Moringa caterpillar', type: 'insect', crops: ['moringa'], parts: ['leaf', 'flower'], signs: 'Leaflets eaten and webbed; small green caterpillars; trees can be stripped.', action: 'Prune and harvest heavily infested branches; neem-seed extract; check weekly in the rains.' },
  { name: 'Scale insects', type: 'insect', crops: ['moringa', 'mango', 'shea', 'tamarind'], parts: ['stem', 'leaf'], signs: 'Small fixed bumps on stems and leaves; sticky leaves and black sooty mould.', action: 'Prune infested shoots; scrub with soapy water.' },
  { name: 'Root rot (waterlogging)', type: 'disease', crops: ['moringa', 'groundnut', 'sesame', 'cowpea', 'okra'], parts: ['root', 'whole'], signs: 'Plants wilt and yellow after standing water; roots dark and soft.', action: 'Drain the plot; plant on ridges or mounds; replace dead plants after the water drops.' },
  { name: 'Balanites fruit beetle', type: 'insect', crops: ['balanites'], parts: ['fruit', 'seed'], signs: 'Round holes in fallen fruit and kernels.', action: 'Collect fruit soon after it falls; dry kernels well before storage.' },
  { name: 'Wood borers', type: 'insect', crops: [...TREE], parts: ['stem'], signs: 'Holes in the trunk or branches with sawdust; branch dies back.', action: 'Cut out and burn dead branches; report many trees with holes.' },
  { name: 'Mistletoe', type: 'weed', crops: [...TREE], parts: ['stem'], signs: 'Bushy green parasite plant growing from branches.', action: 'Cut the infected branch 30 cm below the mistletoe.' },
  { name: 'Leaf-eating caterpillars', type: 'insect', crops: [...TREE, 'jute', 'mallow', 'kudra'], parts: ['leaf'], signs: 'Leaves eaten from the edges; caterpillars on leaves.', action: 'Hand-pick; neem-seed extract if many.' },
  // everywhere
  { name: 'Termites', type: 'insect', crops: ALL, parts: ['root', 'stem', 'whole'], signs: 'Earth tunnels on stems; plants cut at the base or wilt; worse in dry spells.', action: 'Remove dry crop residue near plots; mulch with neem leaves; water seedlings in dry spells.' },
  { name: 'Grasshoppers', type: 'insect', crops: ALL, parts: ['leaf'], signs: 'Leaves eaten from the edges; many hoppers in the field.', action: 'Clear grassy borders; collect early in the morning; report swarms.' },
  { name: 'Desert locust', type: 'insect', crops: ALL, parts: ['leaf', 'whole'], signs: 'Swarms or bands of yellow or pink locusts.', action: 'Report to the county agriculture office at once; do not spray yourself.' },
  { name: 'Aphids', type: 'insect', crops: ALL, parts: ['leaf', 'stem', 'flower'], signs: 'Clusters of small soft insects on young shoots; curled, sticky leaves.', action: 'Soapy water or neem-seed extract; encourage ladybirds.' },
  { name: 'Leaf spot (fungal)', type: 'disease', crops: ALL, parts: ['leaf'], signs: 'Brown or black spots on leaves, often with a yellow ring.', action: 'Remove spotted leaves; space plants for air; rotate crops.' },
  { name: 'Rats', type: 'animal', crops: ALL, parts: ['seed', 'fruit', 'root'], signs: 'Gnawed pods, heads or roots; burrows near the plot.', action: 'Clear grass around plots and stores; store on raised platforms.' },
  { name: 'Livestock damage', type: 'animal', crops: ALL, parts: ['whole', 'leaf', 'stem'], signs: 'Plants grazed or trampled; hoof marks.', action: 'Repair fencing; agree grazing times with herders.' }
];

const has = (crop: string, keys: string[]) => keys.includes('*') || keys.some(k => crop.toLowerCase().includes(k));

// Dropdown for a crop and plant part: specific pests first, then general ones, then names
// workers added for this crop. Unknown new crops fall back to the general list.
export function pestOptions(crop: string, part: Part | '', cropRec?: Crop | null): { name: string; info: PestInfo | null }[] {
  const fit = PEST_LIBRARY.filter(p => has(crop, p.crops) && (!part || p.parts.includes(part)));
  const specific = fit.filter(p => !p.crops.includes('*')), general = fit.filter(p => p.crops.includes('*'));
  const added = (cropRec?.pests ?? []).filter(n => !fit.some(p => p.name.toLowerCase() === n.toLowerCase()));
  return [...specific, ...general].map(p => ({ name: p.name, info: p as PestInfo | null })).concat(added.map(name => ({ name, info: null })));
}

export const pestInfo = (name: string) => PEST_LIBRARY.find(p => p.name === name) ?? null;
