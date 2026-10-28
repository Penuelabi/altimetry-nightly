# SMS delivery on Google Cloud

Three pieces, all optional and all off until you run them:

| Piece | Google Cloud service | Purpose |
|---|---|---|
| SMSGate private server | Cloud Run + Cloud SQL (MySQL, private IP) | Your own endpoint instead of `api.sms-gate.app`; the Android phone registers here |
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
./deploy_gcp.sh server       # prints the app settings (API URL, private token)
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
  checked against `config.example.yml` in the SMSGate server repository before step `server`.
- **Cost.** Cloud SQL (db-f1-micro) is billed all month even when idle, about 8-10 USD; Cloud Run, Scheduler, Secret Manager
  and the bucket are small at this volume. A single small VM running SMSGate with MariaDB in Docker is a cheaper alternative.
- The Cloud Run server URL is public (the phone needs it); the REST API still requires the username and password.
- The optional SMSGate background worker and web dashboard are not deployed.
- The job's indicator rows are not written to the repository ledger (the container is stateless); count sent messages from
  `sms_send_log.csv` for the TWG-AA indicator report.
