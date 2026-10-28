// Current weather at a point from Open-Meteo (free, no key). The last reading is kept so an
// offline crop check still starts from something recent; the worker can always edit it.
export interface Weather { temp: number; rain24: number; sky: 'Sunny' | 'Cloudy' | 'Rain' | 'Windy'; at: string }
const KEY = 'abuk-last-weather';

// WMO weather codes → the form's four sky choices.
const skyFor = (code: number, wind: number): Weather['sky'] =>
  code >= 51 ? 'Rain' : wind >= 30 ? 'Windy' : code >= 2 ? 'Cloudy' : 'Sunny';

export async function fetchWeather(lat: number, lon: number): Promise<Weather> {
  const u = `https://api.open-meteo.com/v1/forecast?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}&current=temperature_2m,weather_code,wind_speed_10m&hourly=precipitation&past_days=1&forecast_days=1&timezone=auto`;
  const r = await fetch(u);
  if (!r.ok) throw new Error(`weather service ${r.status}`);
  const j = await r.json() as { current: { time: string; temperature_2m: number; weather_code: number; wind_speed_10m: number }; hourly: { time: string[]; precipitation: number[] } };
  const nowIdx = j.hourly.time.findIndex(t => t >= j.current.time);
  const end = nowIdx < 0 ? j.hourly.time.length : nowIdx;
  const rain24 = j.hourly.precipitation.slice(Math.max(0, end - 24), end).reduce((a, b) => a + (b || 0), 0);
  const w: Weather = { temp: Math.round(j.current.temperature_2m), rain24: Math.round(rain24 * 10) / 10, sky: skyFor(j.current.weather_code, j.current.wind_speed_10m), at: new Date().toISOString() };
  try { localStorage.setItem(KEY, JSON.stringify(w)); } catch { /* storage off */ }
  return w;
}

export function lastWeather(): Weather | null {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; }
}
