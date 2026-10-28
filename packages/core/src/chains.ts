// Processing chains: the usual steps from raw harvest to a packed product. Any crop (or later,
// forest, fish and livestock product) can be processed; known ones start from a template, others
// from generic steps the worker renames. Matched by keyword on the crop or product name.
export interface ChainTemplate { product: string; match: string[]; unit: string; steps: string[] }

export const CHAIN_TEMPLATES: ChainTemplate[] = [
  { product: 'Balanites oil', match: ['balanites', 'desert date'], unit: '1 L bottle', steps: ['Fruit collected', 'De‑pulped & dried nuts', 'Cracked → kernels', 'Pressed', 'Refined & bottled'] },
  { product: 'Moringa powder', match: ['moringa'], unit: '500 g pack', steps: ['Fresh leaves cut', 'Shade‑dried', 'Milled', 'Packed'] },
  { product: 'Sorghum flour', match: ['sorghum', 'feterita'], unit: '50 kg sack', steps: ['Heads harvested', 'Dried', 'Threshed & winnowed', 'Milled', 'Bagged'] },
  { product: 'Millet flour', match: ['millet'], unit: '50 kg sack', steps: ['Heads harvested', 'Dried', 'Threshed & winnowed', 'Milled', 'Bagged'] },
  { product: 'Maize grain', match: ['maize'], unit: '50 kg sack', steps: ['Cobs harvested', 'Dried', 'Shelled', 'Cleaned & graded', 'Bagged'] },
  { product: 'Groundnut paste', match: ['groundnut', 'peanut'], unit: '1 kg jar', steps: ['Lifted & dried', 'Shelled', 'Sorted (mould removed)', 'Roasted', 'Ground & packed'] },
  { product: 'Sesame oil', match: ['sesame', 'simsim'], unit: '1 L bottle', steps: ['Cut & stooked', 'Threshed', 'Cleaned', 'Pressed', 'Filtered & bottled'] },
  { product: 'Cowpea grain', match: ['cowpea', 'bean'], unit: '50 kg sack', steps: ['Pods picked', 'Dried', 'Threshed', 'Cleaned & sorted', 'Hermetic bagged'] },
  { product: 'Dried kudra', match: ['jute', 'kudra', 'mallow'], unit: '250 g pack', steps: ['Leaves cut', 'Washed', 'Shade‑dried', 'Packed'] },
  { product: 'Dried okra', match: ['okra'], unit: '500 g pack', steps: ['Pods picked', 'Sliced', 'Sun‑dried', 'Packed'] },
  { product: 'Shea butter', match: ['shea', 'lulu'], unit: '1 kg tub', steps: ['Fruit collected', 'De‑pulped', 'Nuts dried', 'Roasted & pounded', 'Butter extracted', 'Packed'] },
  { product: 'Tamarind pulp', match: ['tamarind', 'aradeib'], unit: '1 kg block', steps: ['Pods harvested', 'De‑shelled', 'Seeds removed', 'Pressed into blocks'] },
  { product: 'Gum arabic', match: ['gum', 'hashab', 'acacia'], unit: '50 kg sack', steps: ['Trees tapped', 'Nodules collected', 'Cleaned', 'Graded', 'Bagged'] },
  { product: 'Honey', match: ['honey', 'bee'], unit: '1 kg jar', steps: ['Combs harvested', 'Crushed & strained', 'Settled', 'Bottled'] },
  { product: 'Dried / smoked fish', match: ['fish', 'tilapia', 'catfish', 'nile perch'], unit: 'kg', steps: ['Fish landed', 'Gutted & cleaned', 'Salted', 'Smoked or sun‑dried', 'Packed'] },
  { product: 'Ghee', match: ['milk', 'ghee', 'cow', 'goat'], unit: '1 kg tin', steps: ['Milk collected', 'Soured', 'Churned → butter', 'Boiled → ghee', 'Packed'] }
];

export const GENERIC_STEPS = ['Harvested', 'Dried', 'Cleaned & sorted', 'Processed', 'Packed'];

export function chainFor(name: string): ChainTemplate {
  const n = name.toLowerCase();
  return CHAIN_TEMPLATES.find(t => t.match.some(m => n.includes(m)) || t.product.toLowerCase() === n)
    ?? { product: `${name} (processed)`, match: [], unit: 'kg', steps: GENERIC_STEPS };
}
