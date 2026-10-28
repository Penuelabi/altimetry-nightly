#!/usr/bin/env bash
# Google Cloud deployment for the SMSGate add-on (free-tier design: database on the Always Free VM). NOT tested against a live project: read each step, run them one
# at a time (./deploy_gcp.sh <step>), and check the Cloud Console as you go.
#
#   ./deploy_gcp.sh setup     enable APIs, Artifact Registry repo, bucket for the send log, service account
#   ./deploy_gcp.sh vm        free e2-micro VM: SMSGate private server + MariaDB + Caddy (HTTPS), no Cloud SQL
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
  $G services enable run.googleapis.com secretmanager.googleapis.com \
    cloudscheduler.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
    compute.googleapis.com storage.googleapis.com
  $G artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
    $G artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"
  $G storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
    $G storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access
  $G iam service-accounts describe "$SA" >/dev/null 2>&1 || $G iam service-accounts create "$SA_NAME" \
    --display-name="Anticipatory action SMS job"
  $G storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin
  echo "setup done"
  ;;

vm)
  # One Always Free e2-micro VM running SMSGate + MariaDB + Caddy (HTTPS). Free-tier VMs must be in a US region
  # (us-west1, us-central1 or us-east1) - confirm current limits on Google's Free Tier page before running.
  VM_REGION="${VM_REGION:-us-central1}"; ZONE="${GCP_ZONE:-${VM_REGION}-a}"; VM="smsgate-vm"
  $G compute addresses describe smsgate-ip --region="$VM_REGION" >/dev/null 2>&1 || \
    $G compute addresses create smsgate-ip --region="$VM_REGION"
  IP="$($G compute addresses describe smsgate-ip --region="$VM_REGION" --format='value(address)')"
  DOMAIN="${SMSGATE_DOMAIN:-${IP//./-}.sslip.io}"      # sslip.io = free wildcard DNS for an IP; set your own domain if you have one
  $G compute firewall-rules describe smsgate-web >/dev/null 2>&1 || \
    $G compute firewall-rules create smsgate-web --allow=tcp:80,tcp:443 --target-tags=smsgate
  $G compute instances describe "$VM" --zone="$ZONE" >/dev/null 2>&1 || \
    $G compute instances create "$VM" --zone="$ZONE" --machine-type=e2-micro --image-family=debian-12 \
      --image-project=debian-cloud --boot-disk-size=30GB --boot-disk-type=pd-standard --address=smsgate-ip \
      --tags=smsgate --metadata-from-file=startup-script="$(dirname "$0")/vm/startup.sh"
  SSH="$G compute ssh $VM --zone=$ZONE --quiet"
  echo "waiting for the VM to finish installing Docker (a few minutes)..."
  until $SSH --command='test -f /var/lib/smsgate-ready' 2>/dev/null; do sleep 15; done
  if $SSH --command='sudo test -f /opt/smsgate/.env' 2>/dev/null; then
    echo "SMSGate is already installed on the VM; leaving its secrets untouched."
  else
    W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
    DB_PASS="$(openssl rand -hex 16)"; TOKEN="$(openssl rand -hex 24)"
    printf 'DB_ROOT_PASSWORD=%s\nDB_PASSWORD=%s\nSMSGATE_DOMAIN=%s\nPRIVATE_TOKEN=%s\n' \
      "$(openssl rand -hex 16)" "$DB_PASS" "$DOMAIN" "$TOKEN" > "$W/.env"
    sed -e "s|<PRIVATE_TOKEN>|$TOKEN|" -e "s|<DB_PASSWORD>|$DB_PASS|" "$(dirname "$0")/smsgate_config.example.yml" > "$W/config.yml"
    cp "$(dirname "$0")/vm/docker-compose.yml" "$(dirname "$0")/vm/Caddyfile" "$W/"
    $G compute scp --zone="$ZONE" --quiet --recurse "$W" "$VM:~/smsgate-setup"
    $SSH --command='sudo mkdir -p /opt/smsgate && sudo cp -a ~/smsgate-setup/. /opt/smsgate/ && sudo chmod 600 /opt/smsgate/.env /opt/smsgate/config.yml && rm -rf ~/smsgate-setup && cd /opt/smsgate && sudo docker compose up -d'
    echo "Private token (type it into the Android app): $TOKEN"
  fi
  echo
  echo "Server URL:   https://$DOMAIN   (allow a minute for the certificate)"
  echo "Android app:  Settings > Cloud Server > API URL = https://$DOMAIN/api/mobile/v1 and the private token"
  echo "Then switch on 'Cloud server' on the Home tab and note the username and password the app shows."
  echo "$DOMAIN" > "$(dirname "$0")/.server_domain"
  ;;

recipients)
  FILE="${2:?usage: deploy_gcp.sh recipients <file.csv>}"
  secret_put aa-sms-recipients < "$FILE"
  echo "stored recipients as secret aa-sms-recipients (never commit this file)"
  ;;

job)
  DOMAIN="$(cat "$(dirname "$0")/.server_domain" 2>/dev/null || true)"
  [ -n "$DOMAIN" ] || read -r -p "SMSGate server domain (from the vm step): " DOMAIN
  URL="https://$DOMAIN"
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
