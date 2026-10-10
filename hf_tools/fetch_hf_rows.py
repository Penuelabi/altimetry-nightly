#!/usr/bin/env python3
"""Fetch rows from the Hugging Face datasets-server API.

Python equivalent of:
    curl -X GET -H "Authorization: Bearer $HF_TOKEN" \
      "https://datasets-server.huggingface.co/rows?dataset=dayomtechnologies%2Fmultilingual-english-nuer-dinka-swahili-corpus&config=default&split=train&offset=0&length=100"

The token is read from the GitHub secret exposed as the environment variable
HUGGINGFACE (falls back to HF_TOKEN for local use).

Usage:
    python fetch_hf_rows.py                    # first 100 rows
    python fetch_hf_rows.py --all              # page through the whole split
    python fetch_hf_rows.py --offset 200 --length 50
"""
import argparse
import csv
import json
import os
import sys
import time

import requests

API_URL = "https://datasets-server.huggingface.co/rows"
DATASET = "dayomtechnologies/multilingual-english-nuer-dinka-swahili-corpus"
MAX_PAGE = 100  # datasets-server caps length at 100 per request


def get_token() -> str:
    token = os.environ.get("HUGGINGFACE") or os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("No token found: set the HUGGINGFACE secret/env var (or HF_TOKEN).")
    return token


def fetch_page(token, dataset, config, split, offset, length, retries=3):
    params = {
        "dataset": dataset,
        "config": config,
        "split": split,
        "offset": offset,
        "length": length,
    }
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(1, retries + 1):
        r = requests.get(API_URL, headers=headers, params=params, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            time.sleep(2 * attempt)
            continue
        sys.exit(f"HTTP {r.status_code}: {r.text[:500]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--config", default="default")
    ap.add_argument("--split", default="train")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--length", type=int, default=100)
    ap.add_argument("--all", action="store_true", help="page through the entire split")
    ap.add_argument("--out", default="hf_output", help="output file prefix")
    args = ap.parse_args()

    token = get_token()
    rows, offset = [], args.offset
    total = None

    while True:
        length = min(args.length, MAX_PAGE)
        data = fetch_page(token, args.dataset, args.config, args.split, offset, length)
        total = data.get("num_rows_total", total)
        page = [item["row"] for item in data.get("rows", [])]
        rows.extend(page)
        print(f"Fetched {len(page)} rows (offset {offset}, total in split: {total})")
        offset += len(page)
        if not args.all or not page or (total is not None and offset >= total):
            break
        time.sleep(0.2)  # be polite to the API

    with open(f"{args.out}.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    if rows:
        fields = list(rows[0].keys())
        with open(f"{args.out}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    print(f"Saved {len(rows)} rows to {args.out}.json and {args.out}.csv")


if __name__ == "__main__":
    main()
