# -*- coding: utf-8 -*-
"""
Copy the pipeline's working files between your Google Drive folder and the
GitHub runner, using the service account.

    python drive_sync.py pull     # Drive folder  -> local data folder (before the run)
    python drive_sync.py push     # local data folder -> Drive folder (after the run)

Environment variables (GitHub secrets):
    GEE_SERVICE_ACCOUNT_KEY   the service account's JSON key (full text)
    DRIVE_FOLDER_ID           ID of your colab_waterlevel folder (from its Drive URL)
    ALTIMETRY_OUT_DIR         local folder the pipeline reads/writes (set in the workflow)

A service account has no Drive storage of its own, so in a personal Drive it can
UPDATE files you already own but cannot CREATE new ones. All files below already
exist after a normal Colab run; if one is missing, push says which, and you
create it once (by running the pipeline in Colab, or uploading an empty file
with that exact name).
"""
import hashlib
import json
import os
import socket
import ssl
import sys
import time

import httplib2

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive']

# Network hiccups (e.g. ssl.SSLEOFError "EOF occurred in violation of protocol") happen on GitHub runners.
# One dropped connection must not lose a whole nightly run, so every transfer is retried.
ATTEMPTS = 4
CHUNK_BYTES = 8 * 1024 * 1024
RETRY_STATUS = (429, 500, 502, 503, 504)
NETWORK_ERRORS = (ssl.SSLError, ConnectionError, TimeoutError, socket.timeout, OSError,
                  httplib2.HttpLib2Error)

# Files the pipeline reads and/or writes in the Drive folder
SYNC_FILES = [
    'merged_altimetry_stations.csv',
    'merged_altimetry_stations.xlsx',
    'gee_uploaded_keys.csv',
    'dahiti_water_levels_raw.xlsx',
    'dahiti_seed_check.csv',
    'hydroweb_water_levels_raw.xlsx',
    'Theia_Hydroweb_Operational_Rivers.zip',
    'HYDROWEB_LAKES_OPE.zip',
    'cache_climate_15d_v2.csv',
    'cache_elevation.csv',
    'cache_station_catchments.csv',
    'nightly_run_log.txt',
    'station_status.csv',
]
# Read-only inputs: pulled, never pushed back
PULL_ONLY = [
    'station_lookup.xlsx',
]
# County bulletin folder (Drive subfolder county_bulletin, ID in BULLETIN_FOLDER_ID)
BULLETIN_FILES = [
    'county_bulletin_latest.csv',
    'county_bulletin_latest.xlsx',
    'forecast_log_ens.csv',
    'counties_dissolved.geojson',
    'county_bulletin_latest.json',
    'county_bulletin_latest.pdf',
    'forecast_verification.csv',
    'subscribers.csv',
    'forecast_reliability.csv',
    'forecast_verification_by_county.csv',
    'forecast_obs_cache.csv',
    'county_exposure_cache.csv',
    'sudd_trigger_log.csv',
]


def drive_service():
    key = os.environ['GEE_SERVICE_ACCOUNT_KEY'].strip()
    info = json.loads(key if key.startswith('{') else open(key, encoding='utf-8').read())
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    print(f"Drive: service account {info['client_email']}")
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def folder_files(svc, folder_id):
    """name -> newest file record in the folder."""
    out, token = {}, None
    while True:
        resp = svc.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields='nextPageToken, files(id, name, md5Checksum, modifiedTime, size)',
            pageSize=1000, pageToken=token,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        for f in resp.get('files', []):
            if f['name'] not in out or f['modifiedTime'] > out[f['name']]['modifiedTime']:
                out[f['name']] = f
        token = resp.get('nextPageToken')
        if not token:
            return out


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _is_retryable(e):
    if isinstance(e, HttpError):
        status = getattr(e.resp, 'status', 0)
        return status in RETRY_STATUS or 'rateLimitExceeded' in str(e) or 'userRateLimitExceeded' in str(e)
    return isinstance(e, NETWORK_ERRORS)


def with_retries(fn, what):
    """Run fn(); on a network error or HTTP 429/5xx wait and try again (ATTEMPTS tries in all)."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:
            if not _is_retryable(e) or attempt == ATTEMPTS:
                raise
            wait = 5 * attempt
            print(f"    {what}: {type(e).__name__}: {str(e)[:100]} - retry {attempt}/{ATTEMPTS - 1} in {wait} s")
            time.sleep(wait)


def _download_file(svc, file_id, path):
    with open(path, 'wb') as fh:
        dl = MediaIoBaseDownload(fh, svc.files().get_media(fileId=file_id, supportsAllDrives=True),
                                 chunksize=CHUNK_BYTES)
        done = False
        while not done:
            _, done = dl.next_chunk(num_retries=5)


def _upload_file(svc, folder_id, name, path, record):
    """Resumable upload in chunks; a fresh request is made on every retry."""
    media = MediaFileUpload(path, resumable=True, chunksize=CHUNK_BYTES)
    if record is not None:
        req = svc.files().update(fileId=record['id'], media_body=media, supportsAllDrives=True)
    else:
        req = svc.files().create(body={'name': name, 'parents': [folder_id]}, media_body=media,
                                 fields='id', supportsAllDrives=True)
    resp = None
    while resp is None:
        _, resp = req.next_chunk(num_retries=5)
    return resp


def pull(svc, folder_id, local_dir, sync_files=None, pull_only=None):
    sync_files = SYNC_FILES if sync_files is None else sync_files
    pull_only = PULL_ONLY if pull_only is None else pull_only
    os.makedirs(local_dir, exist_ok=True)
    remote = folder_files(svc, folder_id)
    for name in sync_files + pull_only:
        f = remote.get(name)
        if f is None:
            print(f"  - {name}: not in the Drive folder (will be created locally if needed)")
            continue
        if str(f.get('size', '')) == '0':
            print(f"  - {name}: empty placeholder on Drive (filled in by push after the run)")
            continue
        path = os.path.join(local_dir, name)
        with_retries(lambda f=f, path=path: _download_file(svc, f['id'], path), f"pull {name}")
        print(f"  pulled {name} ({os.path.getsize(path) / 1e6:.1f} MB)")


def push(svc, folder_id, local_dir, sync_files=None):
    """Upload every changed file. A file that still fails after the retries is reported and the
    rest are still uploaded; the command exits with an error at the end if anything was not saved."""
    sync_files = SYNC_FILES if sync_files is None else sync_files
    remote = folder_files(svc, folder_id)
    missing, failed = [], []
    for name in sync_files:
        path = os.path.join(local_dir, name)
        if not os.path.exists(path):
            continue
        f = remote.get(name)
        if f is not None and f.get('md5Checksum') == md5(path):
            print(f"  = {name}: unchanged")
            continue
        try:
            with_retries(lambda name=name, path=path, f=f: _upload_file(svc, folder_id, name, path, f),
                         f"push {name}")
            print(f"  {'pushed' if f is not None else 'created'} {name} "
                  f"({os.path.getsize(path) / 1e6:.1f} MB)")
        except HttpError as e:
            if 'storageQuotaExceeded' in str(e) or 'storage quota' in str(e).lower():
                missing.append(name)
            else:
                print(f"  !! {name}: NOT saved to Drive ({type(e).__name__}: {str(e)[:160]})")
                failed.append(name)
        except Exception as e:
            print(f"  !! {name}: NOT saved to Drive ({type(e).__name__}: {str(e)[:160]})")
            failed.append(name)
    if missing:
        print("\nThese files don't exist in your Drive folder yet, and a service account "
              "can't create files in a personal Drive:\n  " + "\n  ".join(missing) +
              "\nCreate them once: run the pipeline in Colab, or upload an empty file with "
              "each name to the folder. Later runs will then update them.")
    if failed:
        print("\n" + "!" * 70 + "\nThese files were NOT saved to Drive (network errors after "
              f"{ATTEMPTS} tries):\n  " + "\n  ".join(failed) +
              "\nDrive still holds their previous versions, so the next run starts from the old state.\n"
              + "!" * 70)
        for name in failed:
            print(f"::error title=Drive push failed::{name} was not saved to Drive")
    if missing or failed:
        sys.exit(1)


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or args[0] not in ('pull', 'push') or (len(args) > 1 and args[1] != 'bulletin'):
        sys.exit("usage: python drive_sync.py pull|push [bulletin]")
    service = drive_service()
    if len(args) > 1:
        folder = os.environ['BULLETIN_FOLDER_ID'].strip()
        local = os.environ.get('BULLETIN_OUT_DIR', 'bulletin')
        files, only = BULLETIN_FILES, []
    else:
        folder = os.environ['DRIVE_FOLDER_ID'].strip()
        local = os.environ.get('ALTIMETRY_OUT_DIR', 'data')
        files, only = SYNC_FILES, PULL_ONLY
    print(f"{args[0]}: Drive folder {folder} <-> {local}")
    if args[0] == 'pull':
        pull(service, folder, local, files, only)
    else:
        push(service, folder, local, files)
