# Abuk Project app: setup

This repo implements the Claude Design handoff in `project/AbukApp.dc.html`, the Duk County · Abuk Project field app. The handoff notes are in `README.md` and `chats/`.

| Path | What it is |
| --- | --- |
| `packages/core` | Shared by every client: seed data from the design, the flood recession model, form validation, geo helpers, API types. |
| `server` | Node API (Hono). It holds every secret and talks to GitHub, Google Drive / Sheets / Earth Engine, and the SMS gateway. |
| `apps/pwa` | Installable, offline-first web app (React + Vite). It covers all 24 screens and the three home layouts (pick one under the header logo → Home screen). |

React Native and Kotlin/Compose ports come next. They will reuse `packages/core` (RN) and the same server API.

## Run locally

```sh
npm install
cp server/.env.example server/.env      # fill in what you have
npm run dev:server                      # :8787; logs which integrations are missing
npm run dev:pwa                         # :5173; proxies /api to the server
npm test
```

The development build has an "Open demo with sample data" link on the sign-in screen. Production builds don't include it.

## Configuration (server environment)

Missing values don't crash the server. The affected endpoint returns `503 not_configured` with the missing variable names, and the app shows that message. `GET /api/health` lists what is set.

| Variable | Used for |
| --- | --- |
| `SESSION_SECRET` | Signs 30-day session tokens. Any long random string. |
| `GITHUB_ACCESS_REPO`, `GITHUB_TOKEN`, `GITHUB_BRANCH` | Private repo with `users.json` (scrypt hashes of access keys only), `data/gauge.json` and `config/*.json`. Use a fine-grained token with *Contents: read & write* on that one repo. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | One service account for Drive, Sheets and Earth Engine. Share the Drive folder and the records sheet with its email, and register it for Earth Engine. |
| `DRIVE_FOLDER_ID` | Defaults to the colab_waterlevel folder `1EyYopiOghPmHyJyBuH8DCp9PJv1zvCzV`. |
| `SHEET_ID` | Google Sheet that receives synced records ("Abuk Project records" in the colab_waterlevel folder). The server adds one tab per record kind the first time it is used. |
| `GEE_PROJECT`, `GEE_SOIL_MOISTURE_ASSET`, `GEE_SOIL_MOISTURE_BAND`, `GEE_FLOOD_EXTENT_ASSET` | Earth Engine assets. Prefix an ImageCollection with `ic:` to use its newest image. The flood asset should be a 0/1 water mask. |
| `SMS_PROVIDER` (`smsgate`, `africastalking` or `twilio`), `SMS_API_URL`, `SMS_API_KEY`, `SMS_USERNAME`, `SMS_SENDER_ID` | Flood alerts and gauge replies. For SMSGate (as in altimetry-nightly), use the username and password from the gateway app. For Twilio, `SMS_USERNAME` is the account SID. |
| `SMS_WEBHOOK_SECRET` | Point the provider's inbound-SMS webhook at `/api/sms/inbound?secret=…`. |
| `ALLOWED_ORIGIN` | The PWA's origin, for CORS. |

The PWA reads `VITE_API_URL` at build time when the API runs on a different origin.

### First admin

```sh
npm run add-admin -w server -- "Garang Mabior"
```

This commits the hash to `users.json` and prints the key once. Admins then create other users in the app (Access & keys). Each key is shown once.

### Group-lead phone numbers

Phone numbers never ship in the app. Add them to `config/leads.json` in the access repo:

```json
[{ "id": "achol", "name": "Achol Deng", "group": "Group 4", "rows": "B‑01–B‑08", "phone": "+211920000214", "lang": "en" }]
```

## What is live vs. sample

**Live once configured:**
- sign-in, users and keys
- data pull: `station_status.csv` filtered by radius, the county bulletin row, ECMWF IFS, payam lookup from `ssd_payam`, Earth Engine soil moisture and flood extent
- terrain elevation and slope (SRTM) for mapped plots
- record sync to Sheets
- SMS alerts and inbound gauge readings
- real phone GPS for plot mapping and crop checks
- the offline outbox

**Still sample or preview:**
- the basin-depth recession model: a linear 0.92 m at 2.5 cm/day, as in the design; not yet fitted to gauge data
- the bulletin text and model inputs until the first pull
- zone, plot, processing, market and payout figures
- the pest matcher (no reference library yet)
- the QR pattern (placeholder)
- Bluetooth phone-to-phone swap: browsers can't do it, so it's left for the Android builds
- Dinka strings: these need a community translator

**Data finding:** `station_status.csv` has no altimetry station within 20 km, or even 50 km, of the farm point (7.731° N, 31.402° E). The nearest is White Nile km 4500 at about 91 km. The server falls back to the three nearest stations and the app says so.

## Deploying

- **Server, on Cloud Run:** run the workflow `.github/workflows/abuk-server-deploy.yml` by hand. Push to the `abuk-deploy` branch to run it. It copies GitHub secrets into Secret Manager, generates the session and webhook secrets once, and deploys `Dockerfile`. The service URL and `/api/health` appear in the run summary. Any other Node 22 host works too: `npm start -w server`.
- **Android APK:** `.github/workflows/abuk-apk.yml` builds on every push to `abuk-app` and attaches the APK to the `abuk-apk-latest` release. To point it at the server, set the repository variable `ABUK_API_URL`.
- **PWA:** `npm run build -w apps/pwa` produces static files in `apps/pwa/dist`. Serve them over HTTPS so the service worker and GPS work.
