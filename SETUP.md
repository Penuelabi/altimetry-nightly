# Nightly altimetry update on GitHub Actions (00:00 Cairo time)

Every night GitHub starts a small Linux machine, copies your working files from
the `colab_waterlevel` Drive folder, runs the four steps (check merged → download
new DAHITI/Hydroweb → GEE climate for new rows → upload new rows to GEE), and
saves the updated files back to the same Drive folder. Nothing needs to be open
on your laptop.

```
.github/workflows/nightly-altimetry.yml   schedule + steps
cairo_midnight_check.py                   picks the trigger that is 00:00 in Cairo
drive_sync.py                             Drive folder <-> runner (service account)
merge_dahiti_hydroweb.py                  the pipeline (keys come from GitHub secrets)
requirements.txt
```

---

## 1. Service account in Google Cloud (project `ee-penuelabi`)

1. Open <https://console.cloud.google.com/iam-admin/serviceaccounts?project=ee-penuelabi>
   → **Create service account**. Name: `altimetry-nightly` → **Create and continue**.
2. Add two roles, then **Done**:
   - **Earth Engine Resource Writer** (read data, write your `altimetry` assets)
   - **Service Usage Consumer**
3. Click the new account → **Keys** → **Add key** → **Create new key** → **JSON**.
   A `.json` file downloads. Treat it like a password: never email it or commit it.
4. Enable the Drive API for the project:
   <https://console.cloud.google.com/apis/library/drive.googleapis.com?project=ee-penuelabi> → **Enable**.
   (The Earth Engine API is already enabled - your Colab runs use it.)

Copy the service account's email; it looks like
`altimetry-nightly@ee-penuelabi.iam.gserviceaccount.com`.

## 2. Share the Drive folder with it

1. In Google Drive, open `My Drive / colab_waterlevel` → **Share** → paste the
   service account email → role **Editor** → untick "Notify" → **Share**.
2. Copy the folder ID from the address bar:
   `https://drive.google.com/drive/folders/`**`1AbCdEf...`** ← that part.
3. Make sure these files already exist in the folder (a service account can update
   files you own, but can't create new ones in a personal Drive):

   | File | Created by |
   |---|---|
   | `merged_altimetry_stations.csv` / `.xlsx` | a Colab run of the latest script |
   | `gee_uploaded_keys.csv` | a Colab run that reaches Step 4 |
   | `dahiti_water_levels_raw.xlsx`, `hydroweb_water_levels_raw.xlsx` | a Colab run |
   | `HYDROWEB_RIVERS_OPE.zip`, `HYDROWEB_LAKES_OPE.zip` | a Colab run |
   | `cache_climate_15d.csv`, `cache_elevation.csv` | a Colab run |
   | `nightly_run_log.txt` | the Colab midnight cell - or upload an empty text file with this name |

   If one is missing, the workflow's last step lists it. Uploading an empty file
   with that exact name is enough; the next run fills it in.

## 3. GitHub repository

1. Create a **private** repository (e.g. `altimetry-nightly`) at <https://github.com/new>.
2. Upload the files from this folder. The workflow file must end up at
   `.github/workflows/nightly-altimetry.yml`. If drag-and-drop skips the hidden
   `.github` folder, use **Add file → Create new file**, type that path as the
   name, and paste the file's contents.
3. **Settings → Secrets and variables → Actions → New repository secret**, add four:

   | Name | Value |
   |---|---|
   | `GEE_SERVICE_ACCOUNT_KEY` | the whole contents of the `.json` key file |
   | `DRIVE_FOLDER_ID` | the folder ID from step 2 |
   | `DAHITI_API_KEY` | your DAHITI key |
   | `HYDROWEB_API_KEY` | your Hydroweb key |

## 4. Test it now

**Actions** tab → **Nightly altimetry update (00:00 Cairo)** → **Run workflow**.
A manual run skips the midnight check. Open the run to follow each step's log.
Afterwards, check that the files in your Drive folder have a new "modified" time
and that `altimetry/merged_observations` in the GEE Code Editor has the new rows.

From then on it runs by itself every night.

---

## Good to know

- **Timing.** GitHub schedules use UTC, so the workflow fires at 21:00 and 22:00 UTC
  and continues only on the one that is midnight in Cairo (21:00 in summer, 22:00
  in winter). On the night summer time starts, clocks jump from 23:59 to 01:00, so
  that night it runs at 01:00. GitHub often starts scheduled runs 5-30 minutes late.
- **Free minutes.** Private repositories get 2,000 free Actions minutes a month.
  A run with new data mostly waits for GEE exports; roughly 10-40 minutes, so a
  month of nightly runs should fit. Usage: Settings → Billing and plans.
- **Don't run both.** Stop the Colab midnight cell once this is working, so the two
  never write the same files at the same time.
- **Keys.** The copy of the script in this repository has no keys written in it;
  they come from the secrets. Your API keys have appeared in notebook outputs and
  chat, so consider issuing new ones and storing them only as secrets.
- **Stopping it.** Actions tab → the workflow → **⋯** → **Disable workflow**.
