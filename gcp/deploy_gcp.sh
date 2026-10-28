#!/usr/bin/env bash
# Google Cloud deployment for the SMSGate add-on. NOT tested against a live project: read each step, run them one
# at a time (./deploy_gcp.sh <step>), and check the Cloud Console as you go.
#
#   ./deploy_gcp.sh setup     enable APIs, Artifact Registry repo, bucket for the send log, service account
#   ./deploy_gcp.sh server    Cloud SQL (private IP) + SMSGate private server on Cloud Run
#   (then: register the phone - see README_GCP.md - and put its username/password in Secret Manager)
#   ./deploy_gcp.sh recipients <file.csv>   store the recipients list (phone,county,language,group_id) as a secret
#   ./deploy_gcp.sh job       build the dispatcher image, create the Cloud Run job (DRY RUN) and the scheduler
#   ./deploy_gcp.sh live      switch the job to real sending (it still sends only what sms_release.csv approves)
#   ./deploy_gcp.sh dry       switch it back to dry run
set -euo pipefail

PROJECT="${GCP_PROJECT:?set GCP_PROJECT}"
REGION="${GCP_REGION:-europe-west1}"
REPO="${AR_REPO:-aa-sms}"
BUCKET="${GCS_BUCKET:-${PROJECT}-aa-sms-state}"
SA_NAME="aa-sms-job"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
SQL_INSTANCE="${SQL_INSTANCE:-smsgate-db}"
SERVER="smsgate-server"
JOB="smsgate-dispatch"
SCHEDULE="${SCHEDULE:-30 3,15 * * *}"      # UTC, after the 00 and 12 UTC bulletin runs and the add-on workflow
INPUT_BASE="${SMS_INPUT_BASE_URL:-https://raw.githubusercontent.com/Penuelabi/altimetry-nightly/main}"
IMG="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}"
G="gcloud --project=${PROJECT}"

secret_put() {  # name, value from stdin; creates or adds a version
  if $G secrets describe "$1" >/dev/null 2>&1; then $G secrets versions add "$1" --data-file=-
  else $G secrets create "$1" --replication-policy=automatic --data-file=-; fi
}

case "${1:-}" in
setup)
  $G services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
    cloudscheduler.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
    compute.googleapis.com servicenetworking.googleapis.com storage.googleapis.com
  $G artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
    $G artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"
  $G storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
    $G storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access
  $G iam service-accounts describe "$SA" >/dev/null 2>&1 || $G iam service-accounts create "$SA_NAME" \
    --display-name="Anticipatory action SMS job"
  $G storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin
  echo "setup done"
  ;;

server)
  # 1. private services access so Cloud SQL can have a private IP only (no public database)
  $G compute addresses describe google-managed-services-default --global >/dev/null 2>&1 || \
    $G compute addresses create google-managed-services-default --global --purpose=VPC_PEERING \
      --prefix-length=16 --network=default
  $G services vpc-peerings connect --service=servicenetworking.googleapis.com \
    --ranges=google-managed-services-default --network=default || true
  # 2. Cloud SQL for MySQL (smallest tier; this is the main running cost)
  DB_PASS="$(openssl rand -hex 16)"
  if ! $G sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
    $G sql instances create "$SQL_INSTANCE" --database-version=MYSQL_8_0 --edition=ENTERPRISE --tier=db-f1-micro \
      --region="$REGION" --network=default --no-assign-ip --root-password="$(openssl rand -hex 16)"
    $G sql databases create smsgate --instance="$SQL_INSTANCE"
    $G sql users create smsgate --instance="$SQL_INSTANCE" --password="$DB_PASS"
  else
    echo "Cloud SQL instance exists; reset the smsgate password with:"
    echo "  gcloud sql users set-password smsgate --instance=$SQL_INSTANCE --password=<new>"
    read -r -s -p "smsgate database password: " DB_PASS; echo
  fi
  DB_IP="$($G sql instances describe "$SQL_INSTANCE" --format='value(ipAddresses[0].ipAddress)')"
  TOKEN="$(openssl rand -hex 24)"
  # 3. config file in Secret Manager, mounted into the container
  sed -e "s|<PRIVATE_TOKEN>|$TOKEN|" -e "s|<CLOUD_SQL_PRIVATE_IP>|$DB_IP|" -e "s|<DB_PASSWORD>|$DB_PASS|" \
    "$(dirname "$0")/smsgate_config.example.yml" | secret_put smsgate-config
  echo "$TOKEN" | secret_put smsgate-private-token
  $G secrets add-iam-policy-binding smsgate-config \
    --member="serviceAccount:$($G projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor
  # 4. image (copied into Artifact Registry) and Cloud Run service with Direct VPC egress to reach Cloud SQL
  CB="$(mktemp)"; cat > "$CB" <<YAML
steps:
- name: gcr.io/cloud-builders/docker
  args: ['build','-f','Dockerfile.server','-t','${IMG}/smsgate-server:latest','.']
images: ['${IMG}/smsgate-server:latest']
YAML
  $G builds submit "$(dirname "$0")" --region="$REGION" --config="$CB"
  $G run deploy "$SERVER" --image="${IMG}/smsgate-server:latest" --region="$REGION" --port=3000 \
    --allow-unauthenticated --min-instances=0 --max-instances=2 \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars=CONFIG_PATH=/config/config.yml --set-secrets=/config/config.yml=smsgate-config:latest
  URL="$($G run services describe "$SERVER" --region="$REGION" --format='value(status.url)')"
  echo
  echo "Server URL:        $URL"
  echo "Android app: Settings > Cloud Server > API URL = $URL/api/mobile/v1 , private token = see secret smsgate-private-token"
  echo "Then switch on 'Cloud server' on the Home tab and note the username and password the app shows."
  ;;

recipients)
  FILE="${2:?usage: deploy_gcp.sh recipients <file.csv>}"
  secret_put aa-sms-recipients < "$FILE"
  echo "stored recipients as secret aa-sms-recipients (never commit this file)"
  ;;

job)
  URL="$($G run services describe "$SERVER" --region="$REGION" --format='value(status.url)')"
  echo "Enter the SMSGate username and password shown in the phone app:"
  read -r -p "username: " U; read -r -s -p "password: " P; echo
  printf '%s' "$U" | secret_put smsgate-api-user
  printf '%s' "$P" | secret_put smsgate-api-password
  for s in smsgate-api-user smsgate-api-password aa-sms-recipients; do
    $G secrets add-iam-policy-binding "$s" --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
  done
  CB="$(mktemp)"; cat > "$CB" <<YAML
steps:
- name: gcr.io/cloud-builders/docker
  args: ['build','-f','gcp/Dockerfile.job','-t','${IMG}/dispatch:latest','.']
images: ['${IMG}/dispatch:latest']
YAML
  $G builds submit "$(dirname "$0")/.." --region="$REGION" --config="$CB"
  COMMON=(--image="${IMG}/dispatch:latest" --region="$REGION" --service-account="$SA" --max-retries=0 --task-timeout=15m
    --set-env-vars="SMS_GATE_URL=${URL}/api/3rdparty/v1,SMS_INPUT_BASE_URL=${INPUT_BASE},SMS_STATE_DIR=/state,SMS_GATE_ENABLED=no"
    --set-secrets="SMS_GATE_USER=smsgate-api-user:latest,SMS_GATE_PASSWORD=smsgate-api-password:latest,SMS_RECIPIENTS_CSV=aa-sms-recipients:latest"
    --add-volume="name=state,type=cloud-storage,bucket=${BUCKET}" --add-volume-mount="volume=state,mount-path=/state"
    --args=--send)
  if $G run jobs describe "$JOB" --region="$REGION" >/dev/null 2>&1; then $G run jobs update "$JOB" "${COMMON[@]}"
  else $G run jobs create "$JOB" "${COMMON[@]}"; fi
  $G run jobs add-iam-policy-binding "$JOB" --region="$REGION" --member="serviceAccount:$SA" --role=roles/run.invoker
  JOB_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB}:run"
  if $G scheduler jobs describe "${JOB}-schedule" --location="$REGION" >/dev/null 2>&1; then
    $G scheduler jobs update http "${JOB}-schedule" --location="$REGION" --schedule="$SCHEDULE" --time-zone=UTC \
      --uri="$JOB_URI" --http-method=POST --oauth-service-account-email="$SA"
  else
    $G scheduler jobs create http "${JOB}-schedule" --location="$REGION" --schedule="$SCHEDULE" --time-zone=UTC \
      --uri="$JOB_URI" --http-method=POST --oauth-service-account-email="$SA"
  fi
  echo "Job created in DRY RUN (SMS_GATE_ENABLED=no). Test: gcloud run jobs execute $JOB --region=$REGION --wait"
  echo "Read the log:  gcloud storage cat gs://$BUCKET/sms_send_log.csv"
  ;;

live) $G run jobs update "$JOB" --region="$REGION" --update-env-vars=SMS_GATE_ENABLED=yes; echo "LIVE: sends only messages approved in aa_config/sms_release.csv" ;;
dry)  $G run jobs update "$JOB" --region="$REGION" --update-env-vars=SMS_GATE_ENABLED=no;  echo "back to dry run" ;;
*) sed -n 2,14p "$0"; exit 1 ;;
esac
