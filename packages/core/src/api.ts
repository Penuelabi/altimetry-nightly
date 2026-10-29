// Shapes shared by the server and every client.
export type Role = 'Admin' | 'Group lead' | 'Extension worker';

export interface PublicUser { id: string; name: string; role: Role; meta: string; on: boolean; expires: string }
export interface SigninResponse { token: string; user: PublicUser; expires: string }
export interface NewKeyResponse { user: PublicUser; key: string; commit: string }

export interface Station { uid: string; name: string; type: string; lat: number; lon: number; km: number; lastDate: string; lastLevel: number | null; vs2yr: number | null; floodStatus: string; levelClass: string; ratePerDay: number | null }
export interface BulletinRow { county: string; issued: string; alert: string; headline: string; values: Record<string, string | number> }
export interface PullResult {
  at: string; radiusKm: number; location: { lat: number; lon: number; county: string; payam: string | null; state?: string | null };
  stations: { rows: Station[]; fallback: boolean };
  bulletin: BulletinRow | null;
  ifs: { station: string; date: string; values: Record<string, number> }[];
  gee: { soilMoisture: number | null; floodExtentPct: number | null; errors: string[] };
  errors: string[];
}
export interface Terrain { elevation: number | null; slopePct: number | null }

// Every value is the average over all pixels inside one payam's boundary.
export interface SatelliteIndices {
  payam: string; county: string; pcode: string; areaKm2: number;
  ndvi: number | null;
  vci: number | null;
  spi: number | null;
  spei: number | null;
  precipMm: number | null;
  // Share of the payam under flood water (seasonal) and under any water, from the newest MODIS 8-day composite.
  floodPct: number | null;
  waterPct: number | null;
  asOf: string;
  errors: string[];
}

export type SyncKind = 'task' | 'harvest' | 'monitor' | 'plot' | 'offer' | 'store' | 'payout' | 'voice' | 'pest' | 'alert';
export interface SyncRecord { id: string; kind: SyncKind; at: string; by: string; data: Record<string, unknown> }

export interface GaugeReading { from: string; text: string; at: string; v: number | null; status: 'ok' | 'held' | 'bad' }

export interface Health { [integration: string]: { configured: boolean; missing: string[] } }

export interface ApiError { error: string; missing?: string[]; message?: string }
