// Per-lead SMS alerts built from live data: the lead's own group and plots, the latest crop checks
// on those plots (from every phone), the fitted water model and the county bulletin. Pure so it can be tested.
// Plain ASCII in the English text keeps each SMS at 160 characters (one non-ASCII character halves that).
import { basinDepth, dayLabel, recessDays, type Model } from './flood';
import { MOUNDS } from './seed';
import type { BulletinInputs } from './bulletin';
import type { Register, Plot } from './farm';

export interface AlertCheck { at: string; plot: string; water: string; depthCm: number | null; around: string; trend: string }
export interface AlertLead { id: string; name: string; group?: string; rows: string }
export interface AlertInput {
  lead: AlertLead; reg: Register; checks: AlertCheck[]; model: Model; bulletin: BulletinInputs | null;
  rainNext7: number | null; days: number; payam: string; now: Date;
}
export type AlertLevel = 'warn' | 'watch' | 'clear';
export interface PlotLine { code: string; level: AlertLevel; en: string; ar: string }
export interface LeadAlert { level: AlertLevel; group: string; plots: PlotLine[]; reasons: string[]; en: string; ar: string }

const ascii = (s: string) => s.replace(/[‑–—]/g, '-');
const same = (a: string, b: string) => ascii(a).trim().toLowerCase() === ascii(b).trim().toLowerCase();
const WET = ['flooded', 'waterlogged', 'ponding', 'receding'];
const AR_WATER: Record<string, string> = { none: 'جاف', ponding: 'تجمع مياه', waterlogged: 'مشبع بالماء', flooded: 'مغمور', receding: 'الماء ينحسر' };
const AR_TREND: Record<string, string> = { rising: 'يرتفع', falling: 'ينخفض', steady: 'ثابت' };
const rank = (l: AlertLevel) => (l === 'warn' ? 2 : l === 'watch' ? 1 : 0);
const worst = (ls: AlertLevel[]) => ls.reduce<AlertLevel>((a, b) => (rank(b) > rank(a) ? b : a), 'clear');

// The lead's plots: their group's plots in the register, else plot codes written in the lead's "rows".
export function leadPlots(lead: AlertLead, reg: Register): { group: string; plots: Plot[]; codes: string[] } {
  const g = reg.groups.find(x => (lead.group && same(x.name, lead.group)) || same(x.lead, lead.name) || same(x.lead, lead.id));
  if (g) { const plots = reg.plots.filter(p => p.groupId === g.id); return { group: g.name, plots, codes: plots.map(p => ascii(p.code)) }; }
  const codes = (ascii(lead.rows).match(/[A-Z]{1,2}-?\d{1,3}/g) ?? []).map(c => c.replace(/^([A-Z]+)(\d)/, '$1-$2'));
  return { group: lead.group || lead.name, plots: reg.plots.filter(p => codes.some(c => same(c, p.code))), codes };
}

export function leadAlert(i: AlertInput): LeadAlert {
  const { group, plots, codes } = leadPlots(i.lead, i.reg);
  const since = i.now.getTime() - 14 * 864e5;
  const reasons: string[] = [];
  const lines: PlotLine[] = codes.map(code => {
    const c = i.checks.filter(x => same(x.plot, code) && Date.parse(x.at) >= since).sort((a, b) => b.at.localeCompare(a.at))[0];
    if (!c) return { code, level: 'clear', en: `${code} no check 2wk`, ar: `${code} لا فحص منذ أسبوعين` };
    const wet = WET.includes(c.water), cut = c.around === 'cut-off' || c.around === 'surrounding';
    const level: AlertLevel = (wet && c.trend === 'rising') || cut ? 'warn' : wet ? 'watch' : 'clear';
    const depth = wet && c.depthCm ? ` ${c.depthCm}cm` : '';
    const trend = wet && AR_TREND[c.trend] ? ` ${c.trend}` : '';
    const en = `${code} ${wet ? c.water : 'dry'}${depth}${trend}${cut ? ' cut off' : ''}`;
    const ar = `${code} ${AR_WATER[wet ? c.water : 'none']}${depth ? ` ${c.depthCm} سم` : ''}${trend ? ` ${AR_TREND[c.trend]}` : ''}${cut ? ' محاط بالماء' : ''}`;
    if (level === 'warn') reasons.push(cut ? `${code}: water all round` : `${code}: water rising on the plot`);
    return { code, level, en, ar };
  });

  // Basin forecast from the fitted model: mound crests the water reaches within the horizon.
  const m = i.model, d0 = basinDepth(0, m), dN = basinDepth(i.days, m);
  const hasBasin = plots.some(p => p.zone === 'basin') || codes.some(c => /^B-/.test(c));
  const topped = MOUNDS.filter(([, h]) => h >= d0 && h < dN).map(([id]) => ascii(id));
  let basinEn = '', basinAr = '', basinLevel: AlertLevel = 'clear';
  if (m.rate < 0) {
    basinLevel = topped.length && hasBasin ? 'warn' : 'watch';
    if (topped.length) reasons.push(`water to top mound rows ${topped.join(' ')} within ${i.days} days`);
    basinEn = `Basin water ${Math.round(d0 * 100)}cm RISING ${Math.abs(m.rate * 100).toFixed(1)}cm/day${topped.length ? `, tops rows ${topped.join(' ')} in <=${i.days}d` : ''}`;
    basinAr = `ماء الحوض ${Math.round(d0 * 100)} سم ويرتفع ${Math.abs(m.rate * 100).toFixed(1)} سم يومياً${topped.length ? `، سيغمر صفوف ${topped.join(' ')} خلال ${i.days} أيام` : ''}`;
  } else if (d0 > 0) {
    const dry = recessDays(m);
    basinEn = `Basin water ${Math.round(d0 * 100)}cm falling ${(m.rate * 100).toFixed(1)}cm/day${dry != null ? `, dry ~${dayLabel(dry, i.now)}` : ''}`;
    basinAr = `ماء الحوض ${Math.round(d0 * 100)} سم وينخفض ${(m.rate * 100).toFixed(1)} سم يومياً${dry != null ? `، يجف نحو ${dayLabel(dry, i.now)}` : ''}`;
  } else { basinEn = 'Basin dry'; basinAr = 'الحوض جاف'; }
  if (!m.measured) { basinEn += ' (est)'; basinAr += ' (تقدير)'; }

  // Rain and the county bulletin.
  const rain = i.rainNext7 ?? i.bulletin?.week1.median ?? null;
  const heavy = (i.bulletin?.pHeavy ?? 0) >= 0.3, drySpell = (i.bulletin?.pDrySpell ?? 0) >= 0.4;
  if (heavy) reasons.push(`heavy rain (50 mm) chance ${Math.round(i.bulletin!.pHeavy! * 100)}% this week`);
  const b = i.bulletin;
  const alert = b?.alertLevel ? `${b.alertLevel.toUpperCase()} ${b.alertHazard}`.trim() : '';
  const rainLevel: AlertLevel = heavy ? 'warn' : drySpell || (b?.alertLevel && b.alertLevel !== 'green') ? 'watch' : 'clear';

  const level = worst([...lines.map(l => l.level), basinLevel, rainLevel]);
  const floodRisk = reasons.some(r => /water|rows/.test(r));
  const actEn = floodRisk ? 'Lift seed & tools to ridge. Check mounds.' : heavy ? 'Clear drains; keep seed dry.' : drySpell ? 'Dry spell possible: mulch, water seedlings.' : '';
  const actAr = floodRisk ? 'انقلوا البذور والأدوات إلى المرتفع وافحصوا التلال.' : heavy ? 'نظفوا المصارف واحفظوا البذور جافة.' : drySpell ? 'جفاف محتمل: غطوا التربة واسقوا الشتلات.' : '';
  const date = i.now.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  const head = level === 'warn' ? 'ABUK WARNING' : level === 'watch' ? 'ABUK WATCH' : 'ABUK';
  const headAr = level === 'warn' ? 'أبوك - تحذير' : level === 'watch' ? 'أبوك - انتباه' : 'أبوك';
  const plotEn = lines.length ? lines.map(l => l.en).join('; ') : 'no plots linked';
  const plotAr = lines.length ? lines.map(l => l.ar).join('؛ ') : 'لا قطع مرتبطة';
  const en = ascii([
    `${head} ${i.payam} ${date}, ${group}: ${plotEn}.`, `${basinEn}.`,
    rain != null ? `Rain next 7d ${Math.round(rain)}mm.` : '', alert ? `County: ${alert}.` : '', actEn, 'Reply 1=OK -Abuk'
  ].filter(Boolean).join(' '));
  const ar = [
    `${headAr} ${i.payam} ${date}، ${group}: ${plotAr}.`, `${basinAr}.`,
    rain != null ? `المطر خلال 7 أيام ${Math.round(rain)} مم.` : '', alert ? `المقاطعة: ${alert}.` : '', actAr, 'ردّوا 1 للتأكيد -مشروع أبوك'
  ].filter(Boolean).join(' ');
  return { level, group, plots: lines, reasons, en, ar };
}
