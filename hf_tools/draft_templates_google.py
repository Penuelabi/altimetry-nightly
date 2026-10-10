#!/usr/bin/env python3
"""Draft Dinka / Nuer / Swahili versions of the alert message templates with Google Cloud Translation.

Standalone add-on: READS aa_config/message_templates.csv, never edits it, and writes
aa_out/template_translation_drafts_google.csv. Drafts are never marked validated, so aa_p5_dissemination.py ignores
them until a native speaker corrects the text and the TWG-AA copies it into message_templates.csv with validated_by.

Placeholders ({county}, {LEVEL}, {source}) are wrapped in notranslate spans so Google leaves them untouched.
SMS check: Dinka and Nuer use letters outside the GSM-7 alphabet (e.g. e-open, o-open, diaeresis vowels), which makes a
phone send the message as Unicode (UCS-2): 70 characters per single SMS instead of 160. The sms_segments column
estimates how many SMS each draft needs.
"""
import argparse
import csv
import html
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from draft_template_translations import AA_CONFIG, AA_OUT, english_masters, PLACEHOLDER  # noqa: E402
from translate_google import google_translate  # noqa: E402

TARGETS = {"din": "Dinka", "nus": "Nuer", "swa": "Swahili"}
GOOGLE_CODE = {"din": "din", "nus": "nus", "swa": "sw"}
GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà^{}\\[~]|€")


def wrap(text):
    return PLACEHOLDER.sub(lambda m: f'<span class="notranslate">{m.group(0)}</span>', text)


def unwrap(text):
    text = re.sub(r'<span class="notranslate">(.*?)</span>', r"\1", text, flags=re.S)
    return html.unescape(text)


def sms_segments(text):
    if all(c in GSM7 for c in text):
        return "gsm7", 1 if len(text) <= 160 else math.ceil(len(text) / 153)
    return "unicode", 1 if len(text) <= 70 else math.ceil(len(text) / 67)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="din,nus,swa")
    ap.add_argument("--out", default=os.path.join(AA_OUT, "template_translation_drafts_google.csv"))
    args = ap.parse_args()

    from eval_google import get_token
    token = get_token()
    masters = english_masters(os.path.join(AA_CONFIG, "message_templates.csv"))
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    rows = []
    for code in langs:
        print(f"Translating {len(masters)} templates -> {code}")
        outs = google_translate(token, [wrap(m["text"]) for m in masters], GOOGLE_CODE[code], fmt="html")
        for m, raw in zip(masters, outs):
            text = unwrap(raw)
            ok = all(ph in text for ph in PLACEHOLDER.findall(m["text"]))
            enc, segs = sms_segments(text) if m["channel"] == "sms" else ("", "")
            rows.append({
                "situation": m["situation"], "channel": m["channel"], "language": code,
                "language_name": TARGETS[code], "draft_text": text, "chars": len(text),
                "sms_encoding": enc, "sms_segments": segs,
                "placeholders_ok": "yes" if ok else "NO - fix {county}/{LEVEL}/{source} by hand",
                "status": "DRAFT machine translation (Google) - not validated; do not publish",
                "english_master": m["text"],
            })
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} drafts to {args.out}")


if __name__ == "__main__":
    main()
