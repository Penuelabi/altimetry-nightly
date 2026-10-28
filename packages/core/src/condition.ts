// Plot condition terms for the crop check. Moisture, crack-width and erosion classes follow the
// FAO Guidelines for Soil Description (4th ed., 2006); water-on-surface states are the field terms
// used for flood-recession farming. Each has a short description shown to the worker.
export interface Term { id: string; label: string; desc: string }

export const SOIL_MOISTURE: Term[] = [
  { id: 'very-dry', label: 'Very dry', desc: 'Dusty or hard; no moisture felt; soil does not darken when wetted' },
  { id: 'dry', label: 'Dry', desc: 'Feels dry; darkens a little when wetted; crumbles' },
  { id: 'slightly-moist', label: 'Slightly moist', desc: 'Cool to the touch; darkens only slightly when wetted' },
  { id: 'moist', label: 'Moist', desc: 'Feels damp, holds shape when squeezed; no free water' },
  { id: 'wet', label: 'Wet', desc: 'Water glistens or wets the hand when squeezed; sticky' }
];

export const WATER_STATE: Term[] = [
  { id: 'none', label: 'No standing water', desc: 'Surface drained' },
  { id: 'ponding', label: 'Ponding', desc: 'Puddles in low spots after rain; drains within a day or two' },
  { id: 'waterlogged', label: 'Waterlogged', desc: 'Soil saturated to the surface; water seeps into footprints; roots short of air' },
  { id: 'flooded', label: 'Flooded', desc: 'Standing water over most of the plot (enter depth)' },
  { id: 'receding', label: 'Flood receding', desc: 'Water withdrawing; wet silt exposed at the edges' }
];

export const SURFACE: Term[] = [
  { id: 'cracking', label: 'Cracking', desc: 'Shrink cracks as clay dries (enter width)' },
  { id: 'crusting', label: 'Crusting / sealing', desc: 'Hard thin crust on the surface that seedlings struggle to push through' },
  { id: 'erosion-sheet', label: 'Sheet erosion', desc: 'Thin even layer of topsoil washed off; roots or stones exposed' },
  { id: 'erosion-rill', label: 'Rill erosion', desc: 'Small channels a few cm deep, can be ploughed out' },
  { id: 'erosion-gully', label: 'Gully erosion', desc: 'Deep channels that cannot be crossed by a plough' },
  { id: 'silt', label: 'Silt deposited', desc: 'Fresh layer of fine sediment left by flood water' },
  { id: 'salt', label: 'Salt crust', desc: 'White powdery or crystalline crust on the surface' },
  { id: 'mound-damage', label: 'Mound / ridge damaged', desc: 'Slumping or breach on a planting mound or bund' }
];

// Water around the plot, from the plot edge outwards.
export const WATER_AROUND: Term[] = [
  { id: 'dry', label: 'Dry around', desc: 'No standing water within about 100 m' },
  { id: 'nearby', label: 'Water nearby', desc: 'Pools, swamp or channel within about 100 m, not touching the plot' },
  { id: 'edge', label: 'At the plot edge', desc: 'Water touching one side of the plot' },
  { id: 'surrounding', label: 'Surrounding', desc: 'Water on most sides; plot is an island or ridge' },
  { id: 'cut-off', label: 'Cut off', desc: 'Plot cannot be reached on foot without wading' }
];

export const WATER_TREND: Term[] = [
  { id: 'rising', label: 'Rising', desc: 'Higher than at the last visit' },
  { id: 'steady', label: 'Steady', desc: 'About the same as the last visit' },
  { id: 'falling', label: 'Falling', desc: 'Lower than at the last visit' },
  { id: 'unknown', label: 'Not sure', desc: 'No earlier reading to compare' }
];

// FAO 2006 surface crack width classes.
export const CRACK_WIDTH: Term[] = [
  { id: 'fine', label: 'Fine', desc: '< 1 cm' },
  { id: 'medium', label: 'Medium', desc: '1–2 cm' },
  { id: 'wide', label: 'Wide', desc: '2–5 cm' },
  { id: 'very-wide', label: 'Very wide', desc: '5–10 cm' },
  { id: 'extremely-wide', label: 'Extremely wide', desc: '> 10 cm' }
];

// Depths in cm measured with a marked stick at the deepest point; distance in metres to the nearest standing water.
export interface PlotCondition { moisture: string; water: string; floodDepthCm: string; around: string; aroundDepthCm: string; aroundDistanceM: string; trend: string; surface: string[]; crackWidth: string }

export function conditionError(c: PlotCondition): string {
  if (!c.moisture) return 'soil moisture';
  if (!c.water) return 'water on the plot';
  if (['ponding', 'waterlogged', 'flooded', 'receding'].includes(c.water) && c.water !== 'waterlogged' && !(Number(c.floodDepthCm) > 0)) return 'the water depth on the plot in cm';
  if (!c.around) return 'water around the plot';
  if (c.around !== 'dry' && !(Number(c.aroundDepthCm) > 0)) return 'the depth of the water around the plot in cm';
  if (c.around === 'nearby' && !(Number(c.aroundDistanceM) > 0)) return 'how far away the nearest water is in metres';
  if ((c.water !== 'none' || c.around !== 'dry') && !c.trend) return 'whether the water is rising or falling';
  if (c.surface.includes('cracking') && !c.crackWidth) return 'the crack width';
  return '';
}

export const termLabel = (list: Term[], id: string) => list.find(t => t.id === id)?.label ?? id;

export function conditionSummary(c: PlotCondition) {
  const onPlot = c.water === 'none' ? '' : `${termLabel(WATER_STATE, c.water).toLowerCase()}${Number(c.floodDepthCm) > 0 ? ` ${c.floodDepthCm} cm` : ''}`;
  const around = !c.around || c.around === 'dry' ? '' : `water ${termLabel(WATER_AROUND, c.around).toLowerCase().replace('water ', '')} ${c.aroundDepthCm} cm${c.around === 'nearby' && c.aroundDistanceM ? ` at ${c.aroundDistanceM} m` : ''}`;
  const trend = c.trend && c.trend !== 'unknown' ? termLabel(WATER_TREND, c.trend).toLowerCase() : '';
  const parts = [termLabel(SOIL_MOISTURE, c.moisture), onPlot, around, trend];
  for (const s of c.surface) parts.push(s === 'cracking' && c.crackWidth ? `${termLabel(CRACK_WIDTH, c.crackWidth).toLowerCase()} cracks` : termLabel(SURFACE, s).toLowerCase());
  return parts.filter(Boolean).join(', ');
}
