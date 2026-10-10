#!/usr/bin/env python3
"""Translate English text to Dinka, Nuer and Swahili with Google Cloud Translation (Basic v2).

Credentials: service-account JSON in the GEE_SERVICE_ACCOUNT_KEY secret (see eval_google.py).
Output is a MACHINE draft: have a native speaker review it before anything is published.

    python hf_tools/translate_google.py                    # built-in Juba County news item
    python hf_tools/translate_google.py --file input.txt   # one paragraph per line
"""
import argparse
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

URL = "https://translation.googleapis.com/language/translate/v2"
TARGETS = {"Dinka": "din", "Nuer": "nus", "Swahili": "sw"}

DEFAULT_TEXT = """PICTORIAL: The Caretaker Commissioner of Juba County, Kalisto Lado, on Friday, 9 October 2026, launched the completion project of the County Headquarters Building.
The project, undertaken by Hatay Holding Company Ltd., is expected to be completed within four months, with construction scheduled to run 24 hours a day.
The Commissioner also announced plans to construct headquarters for all 13 Payams and the Bomas of Juba County."""


def google_translate(token, texts, target, fmt="text"):
    import requests

    out = []
    for i in range(0, len(texts), 50):
        r = requests.post(URL, headers={"Authorization": f"Bearer {token}"}, timeout=60,
                          json={"q": texts[i:i + 50], "source": "en", "target": target, "format": fmt})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
        out += [t["translatedText"] for t in r.json()["data"]["translations"]]
    return out


def main():
    from eval_google import get_token

    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--out", default=os.path.join(HERE, "translations_google.md"))
    args = ap.parse_args()

    text = open(args.file, encoding="utf-8").read() if args.file else DEFAULT_TEXT
    paras = [p for p in text.splitlines() if p.strip()]
    token = get_token()

    lines = ["# Translations (Google Cloud Translation v2)", "",
             "Machine translation. Have a native speaker review before publishing.", "",
             "## English (source)", ""] + [p + "\n" for p in paras]
    for name, code in TARGETS.items():
        print(f"Translating to {name} ({code})")
        try:
            res = google_translate(token, paras, code)
            lines += [f"## {name} ({code})", ""] + [html.unescape(t) + "\n" for t in res]
        except Exception as e:
            print(f"  FAILED: {e}")
            lines += [f"## {name} ({code})", "", f"FAILED: {e}", ""]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Saved", args.out)


if __name__ == "__main__":
    main()
