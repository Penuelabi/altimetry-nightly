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
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive']

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
    'forecast_reliability.csv',
    'forecast_verification_by_county.csv',
    'forecast_obs_cache.csv',
    'county_exposure_cache.csv',
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
        with open(path, 'wb') as fh:
            dl = MediaIoBaseDownload(fh, svc.files().get_media(fileId=f['id'], supportsAllDrives=True),
                                     chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()
        print(f"  pulled {name} ({os.path.getsize(path) / 1e6:.1f} MB)")


def push(svc, folder_id, local_dir, sync_files=None):
    sync_files = SYNC_FILES if sync_files is None else sync_files
    remote = folder_files(svc, folder_id)
    missing = []
    for name in sync_files:
        path = os.path.join(local_dir, name)
        if not os.path.exists(path):
            continue
        f = remote.get(name)
        if f is not None and f.get('md5Checksum') == md5(path):
            print(f"  = {name}: unchanged")
            continue
        media = MediaFileUpload(path, resumable=True)
        try:
            if f is not None:
                svc.files().update(fileId=f['id'], media_body=media, supportsAllDrives=True).execute()
                print(f"  pushed {name} ({os.path.getsize(path) / 1e6:.1f} MB)")
            else:
                svc.files().create(body={'name': name, 'parents': [folder_id]}, media_body=media,
                                   fields='id', supportsAllDrives=True).execute()
                print(f"  created {name}")
        except HttpError as e:
            if 'storageQuotaExceeded' in str(e) or 'storage quota' in str(e).lower():
                missing.append(name)
            else:
                raise
    if missing:
        print("\nThese files don't exist in your Drive folder yet, and a service account "
              "can't create files in a personal Drive:\n  " + "\n  ".join(missing) +
              "\nCreate them once: run the pipeline in Colab, or upload an empty file with "
              "each name to the folder. Later runs will then update them.")
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
