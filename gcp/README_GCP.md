# SMS delivery on Google Cloud

Three pieces, all optional and all off until you run them:

| Piece | Google Cloud service | Purpose |
|---|---|---|
| SMSGate private server | One Always Free `e2-micro` VM (Docker: SMSGate, MariaDB, Caddy for HTTPS) | Your own endpoint instead of `api.sms-gate.app`; the Android phone registers here. MariaDB on the VM replaces Cloud SQL, which has no permanent free tier |
| Dispatcher job | Cloud Run job + Cloud Scheduler | Runs `aa_p5_sms_gateway.py` twice a day (UTC 03:30 and 15:30, edit `SCHEDULE`) |
| Secrets and state | Secret Manager + a Cloud Storage bucket | Gateway credentials, recipients list, and the send log (so a message is never sent twice in a day) |

The job reads `messages.csv` and `aa_config/sms_release.csv` from the public repository (`SMS_INPUT_BASE_URL`), so
the GitHub workflow keeps producing the drafts and the TWG-AA keeps approving them in `sms_release.csv`; Google Cloud only
delivers. Phone numbers live only in Secret Manager.

## Steps
```
export GCP_PROJECT=<your project id>      # optional: GCP_REGION (default europe-west1)
gcloud auth login && gcloud config set project $GCP_PROJECT
cd gcp
./deploy_gcp.sh setup
./deploy_gcp.sh vm           # creates the VM, installs everything, prints the app settings (API URL, private token)
```
1. In the SMSGate Android app: Settings > Cloud Server, set the API URL and private token printed above, switch on
   **Cloud server**, tap the Offline button until it says Online, then note the username and password on the Home tab.
2. `./deploy_gcp.sh recipients my_recipients.csv` (columns `phone,county,language,group_id`; keep the file out of git).
3. `./deploy_gcp.sh job` (asks for the app username and password; creates the job in **dry run**).
4. `gcloud run jobs execute smsgate-dispatch --region=$GCP_REGION --wait`, then read the log with
   `gcloud storage cat gs://$GCP_PROJECT-aa-sms-state/sms_send_log.csv`.
5. Only when the dry run looks right and `aa_config/sms_release.csv` has `approved_by` / `approved_date` filled in for the
   messages you want released: `./deploy_gcp.sh live`. `./deploy_gcp.sh dry` switches back.

## Things to know
- **Not tested on a live project.** Run the steps one at a time and check the Console. SMSGate's config key names should be
  checked against `config.example.yml` in the SMSGate server repository before step `vm`.
- **Cost.** Designed to stay inside Google's free allowances: one `e2-micro` with a 30 GB standard disk in `us-west1`,
  `us-central1` or `us-east1` (confirm the current limits on Google's Free Tier page; a second VM, an SSD disk or an unused
  reserved IP is billed). Cloud Run, Scheduler, Secret Manager and the bucket are small at this volume. Cloud SQL is not
  used: it has only a 30-day trial instance.
- **HTTPS name.** The Android app needs HTTPS. The script uses `<ip>.sslip.io` (a free wildcard DNS service) and Caddy gets a
  Let's Encrypt certificate. To use your own domain, point an A record at the VM's IP and set `SMSGATE_DOMAIN` before step `vm`.
- **Memory.** The VM has 1 GB RAM, so MariaDB is limited and a 2 GB swap file is added. The optional SMSGate worker and web
  dashboard are not deployed. Back up with `sudo docker exec` + `mariadb-dump` if you need the data kept.
- The server is public (the phone needs it); the REST API still requires the username and password.
- The job's indicator rows are not written to the repository ledger (the container is stateless); count sent messages from
  `sms_send_log.csv` for the TWG-AA indicator report.
