// Weather at a point from Open-Meteo (free, no key): one small request gives today's conditions,
// the last 30 days' rain and evaporation, and the next 7 days' rain. The last reading is kept so an
// offline crop check or flood model still starts from something recent; workers can edit it.
export interface Weather {
  temp: number; rain24: number; sky: 'Sunny' | 'Cloudy' | 'Rain' | 'Windy'; at: string;
  tmax?: number; tmin?: number; rain30?: number; et30?: number; rainNext7?: number;
}
const KEY = 'abuk-last-weather';

// WMO weather codes → the form's four sky choices.
const skyFor = (code: number, wind: number): Weather['sky'] =>
  code >= 51 ? 'Rain' : wind >= 30 ? 'Windy' : code >= 2 ? 'Cloudy' : 'Sunny';
const sum = (xs: (number | null)[]) => Math.round(xs.reduce<number>((a, b) => a + (b ?? 0), 0) * 10) / 10;

export async function fetchWeather(lat: number, lon: number): Promise<Weather> {
  const u = `https://api.open-meteo.com/v1/forecast?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}`
    + '&current=temperature_2m,weather_code,wind_speed_10m&hourly=precipitation'
    + '&daily=precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max,temperature_2m_min'
    + '&past_days=30&forecast_days=8&timezone=auto';
  const r = await fetch(u);
  if (!r.ok) throw new Error(`weather service ${r.status}`);
  const j = await r.json() as {
    current: { time: string; temperature_2m: number; weather_code: number; wind_speed_10m: number };
    hourly: { time: string[]; precipitation: (number | null)[] };
    daily: { time: string[]; precipitation_sum: (number | null)[]; et0_fao_evapotranspiration: (number | null)[]; temperature_2m_max: (number | null)[]; temperature_2m_min: (number | null)[] };
  };
  const nowIdx = j.hourly.time.findIndex(t => t >= j.current.time);
  const end = nowIdx < 0 ? j.hourly.time.length : nowIdx;
  const today = j.current.time.slice(0, 10), ti = j.daily.time.indexOf(today);
  const w: Weather = {
    temp: Math.round(j.current.temperature_2m), rain24: sum(j.hourly.precipitation.slice(Math.max(0, end - 24), end)),
    sky: skyFor(j.current.weather_code, j.current.wind_speed_10m), at: new Date().toISOString(),
    ...(ti >= 0 ? {
      tmax: Math.round(j.daily.temperature_2m_max[ti] ?? NaN), tmin: Math.round(j.daily.temperature_2m_min[ti] ?? NaN),
      rain30: sum(j.daily.precipitation_sum.slice(Math.max(0, ti - 30), ti)), et30: sum(j.daily.et0_fao_evapotranspiration.slice(Math.max(0, ti - 30), ti)),
      rainNext7: sum(j.daily.precipitation_sum.slice(ti + 1, ti + 8))
    } : {})
  };
  try { localStorage.setItem(KEY, JSON.stringify(w)); } catch { /* storage off */ }
  return w;
}

export function lastWeather(): Weather | null {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; }
}
