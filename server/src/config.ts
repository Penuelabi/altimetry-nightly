// Every secret comes from the environment. Integrations whose variables are
// missing report `not_configured` instead of failing at startup, so the app
// can run (and the PWA can show which parts are live) before all keys exist.
const env = (k: string) => (process.env[k] ?? '').trim();

export const GROUPS = {
  session: ['SESSION_SECRET'],
  google: ['GOOGLE_SERVICE_ACCOUNT_JSON', 'DRIVE_FOLDER_ID'],
  sheets: ['GOOGLE_SERVICE_ACCOUNT_JSON', 'SHEET_ID'],
  gee: ['GOOGLE_SERVICE_ACCOUNT_JSON', 'GEE_PROJECT'],
  github: ['GITHUB_ACCESS_REPO', 'GITHUB_TOKEN'],
  sms: ['SMS_PROVIDER', 'SMS_API_KEY', 'SMS_USERNAME'],
  smsInbound: ['SMS_WEBHOOK_SECRET']
} as const;
export type Group = keyof typeof GROUPS;

export const cfg = {
  get port() { return Number(env('PORT')) || 8787; },
  get allowedOrigin() { return env('ALLOWED_ORIGIN') || '*'; },
  get sessionSecret() { return env('SESSION_SECRET'); },
  get serviceAccount() { return env('GOOGLE_SERVICE_ACCOUNT_JSON'); },
  get driveFolder() { return env('DRIVE_FOLDER_ID') || '1EyYopiOghPmHyJyBuH8DCp9PJv1zvCzV'; },
  get sheetId() { return env('SHEET_ID'); },
  get geeProject() { return env('GEE_PROJECT'); },
  get soilAsset() { return env('GEE_SOIL_MOISTURE_ASSET'); },
  get soilBand() { return env('GEE_SOIL_MOISTURE_BAND'); },
  get floodAsset() { return env('GEE_FLOOD_EXTENT_ASSET'); },
  get ghRepo() { return env('GITHUB_ACCESS_REPO'); },
  get ghToken() { return env('GITHUB_TOKEN'); },
  get ghBranch() { return env('GITHUB_BRANCH') || 'main'; },
  get smsProvider() { return env('SMS_PROVIDER').toLowerCase(); },
  get smsKey() { return env('SMS_API_KEY'); },
  get smsUser() { return env('SMS_USERNAME'); },
  get smsSender() { return env('SMS_SENDER_ID'); },
  get smsWebhookSecret() { return env('SMS_WEBHOOK_SECRET'); }
};

export const missing = (g: Group) => GROUPS[g].filter(k => !env(k) && !(k === 'DRIVE_FOLDER_ID'));

export class NotConfigured extends Error {
  constructor(public group: Group, public keys: string[]) { super(`${group} is not configured: set ${keys.join(', ')}`); }
}
export function need(g: Group) {
  const m = missing(g);
  if (m.length) throw new NotConfigured(g, m);
}

export const health = () => Object.fromEntries((Object.keys(GROUPS) as Group[]).map(g => [g, { configured: missing(g).length === 0, missing: missing(g) }]));
