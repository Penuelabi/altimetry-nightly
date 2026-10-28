// Typed view of one county row of county_bulletin_latest (written by the nightly workflow).
// Column names are the workflow's own; any that are missing come back null.
type Values = Record<string, string | number>;

const n = (v: Values, k: string) => { const x = v[k]; if (x === undefined || x === '') return null; const f = Number(x); return isNaN(f) ? null : f; };
const s = (v: Values, k: string) => { const x = v[k]; return x === undefined || x === null ? '' : String(x).trim(); };

export interface BulletinInputs {
  dataEnd: string; runUtc: string; source: string;
  rain7: number | null; rain15: number | null; rain30: number | null; rain30PctNormal: number | null; rain30Class: string;
  et30: number | null; runoff30: number | null; runoff30Class: string; wb30: number | null;
  smSurface: number | null; smRoot: number | null; smRootZ: number | null; soilClass: string; soilDeficit: number | null;
  week1: { median: number | null; p20: number | null; p80: number | null };
  week2: { median: number | null; p20: number | null; p80: number | null };
  pDrySpell: number | null; pWetSpell: number | null; pHeavy: number | null;
  spellWindows: string; summary: string; advisory: string;
  alertLevel: string; alertHazard: string; alertText: string; alertStage: string;
  pWetByDay: { day: string; p: number }[];
}

export function bulletinInputs(v: Values): BulletinInputs {
  const pWetByDay = Object.keys(v).flatMap(k => {
    const m = k.match(/^p_wet_(\d{2})(\d{2})$/);
    const p = n(v, k);
    return m && p != null ? [{ day: `${Number(m[2])} ${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m[1]) - 1]}`, p }] : [];
  });
  return {
    dataEnd: s(v, 'data_end_date'), runUtc: s(v, 'run_utc'), source: s(v, 'data_source'),
    rain7: n(v, 'rain_7d_mm'), rain15: n(v, 'rain_15d_mm'), rain30: n(v, 'rain_30d_mm'), rain30PctNormal: n(v, 'rain_30d_pct_of_normal'), rain30Class: s(v, 'rain_30d_class'),
    et30: n(v, 'et_30d_mm'), runoff30: n(v, 'runoff_30d_mm'), runoff30Class: s(v, 'runoff_30d_class'), wb30: n(v, 'wb_30d_mm'),
    smSurface: n(v, 'sm_surface'), smRoot: n(v, 'sm_rootzone'), smRootZ: n(v, 'sm_rootzone_z'), soilClass: s(v, 'soil_rootzone_class'), soilDeficit: n(v, 'soil_deficit_mm'),
    week1: { median: n(v, 'week1_rain_median_mm'), p20: n(v, 'week1_rain_p20_mm'), p80: n(v, 'week1_rain_p80_mm') },
    week2: { median: n(v, 'week2_rain_median_mm'), p20: n(v, 'week2_rain_p20_mm'), p80: n(v, 'week2_rain_p80_mm') },
    pDrySpell: n(v, 'p_dry_spell_7d_in_15d'), pWetSpell: n(v, 'p_wet_spell_3d_week1'), pHeavy: n(v, 'p_heavy_50mm_week1'),
    spellWindows: s(v, 'spell_windows'), summary: s(v, 'antecedent_summary'), advisory: s(v, 'advisory_flags'),
    alertLevel: s(v, 'alert_level'), alertHazard: s(v, 'alert_hazard'), alertText: s(v, 'alert_text'), alertStage: s(v, 'alert_stage'),
    pWetByDay
  };
}

// The headline a worker reads first: the alert text, else the advisory, else the soil/rain summary.
export const bulletinHeadline = (v: Values) => {
  const b = bulletinInputs(v);
  return b.alertText || b.advisory.split('|')[0].trim() || b.summary;
};
