#!/usr/bin/env python3
"""Draft Dinka / Nuer translations of the English alert templates for native-speaker review.

Standalone add-on in the spirit of the aa_*.py scripts: it only READS aa_config/message_templates.csv and never
edits it. Drafts go to aa_out/template_translation_drafts.csv (same columns as the template file plus checks).

How it connects to the anticipatory-action chain:
  aa_config/message_templates.csv (English master rows)
      -> this script (NLLB-200 machine draft, placeholders protected)
      -> aa_out/template_translation_drafts.csv   (DRAFT, not used by anything)
      -> a native speaker corrects the text and the TWG-AA pastes it into message_templates.csv
         with validated_by / validated_date filled
      -> aa_p5_dissemination.py starts using that language (it ignores any row without validated_by).

Machine drafts are NEVER marked validated here. Nothing is sent automatically.

Usage:
    python hf_tools/draft_template_translations.py                 # din + nus, all situations
    python hf_tools/draft_template_translations.py --langs din,nus,swa
    python hf_tools/draft_template_translations.py --selftest      # no model download, stub translator
"""
import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

AA_CONFIG = os.environ.get("AA_CONFIG_DIR", os.path.join(os.path.dirname(HERE), "aa_config"))
AA_OUT = os.environ.get("AA_OUT_DIR", os.path.join(os.path.dirname(HERE), "aa_out"))

# platform language code -> (NLLB code, display name). NLLB-200 has no Juba Arabic, Shilluk or Bari.
NLLB = {
    "din": ("dik_Latn", "Dinka (NLLB: Southwestern Dinka)"),
    "nus": ("nus_Latn", "Nuer"),
    "swa": ("swh_Latn", "Swahili"),
}
PLACEHOLDER = re.compile(r"\{[A-Za-z_]+\}")


def protect(text):
    """Swap {county}-style placeholders for [1], [2]... so the model leaves them alone."""
    found = []

    def sub(m):
        found.append(m.group(0))
        return f"[{len(found)}]"

    return PLACEHOLDER.sub(sub, text), found


def restore(text, found):
    ok = True
    for i, ph in enumerate(found, 1):
        if f"[{i}]" in text:
            text = text.replace(f"[{i}]", ph)
        else:
            ok = False
    return text, ok


def english_masters(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r["language"] == "en" and r["text"].strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="din,nus")
    ap.add_argument("--out", default=os.path.join(AA_OUT, "template_translation_drafts.csv"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    bad = [l for l in langs if l not in NLLB]
    if bad:
        sys.exit(f"Unsupported language code(s) {bad}; NLLB covers {sorted(NLLB)} here.")

    if args.selftest:
        import tempfile
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, "message_templates.csv")
        with open(src, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["situation", "channel", "language", "language_name", "text", "validated_by", "validated_date", "notes"])
            w.writerow(["flood_red", "sms", "en", "English", "{LEVEL} FLOOD ALERT {county}: move to high ground. {source}", "platform (English master)", "", ""])
            w.writerow(["flood_red", "sms", "din", "Dinka", "", "", "", ""])
        masters = english_masters(src)
        translate = lambda text, tgt: text.upper()  # stub keeps [n] markers intact
        args.out = os.path.join(tmp, "drafts.csv")
    else:
        src = os.path.join(AA_CONFIG, "message_templates.csv")
        if not os.path.exists(src):
            sys.exit(f"{src} not found; run aa_p5_dissemination.py once to write the templates.")
        masters = english_masters(src)
        from translate_hf import make_local_translator
        translate = make_local_translator()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out_rows = []
    for m in masters:
        protected, found = protect(m["text"])
        for code in langs:
            nllb, name = NLLB[code]
            print(f"{m['situation']}/{m['channel']} -> {code}")
            raw = translate(protected, nllb)
            text, ok = restore(raw, found)
            out_rows.append({
                "situation": m["situation"], "channel": m["channel"], "language": code, "language_name": name,
                "draft_text": text, "chars": len(text),
                "over_160_chars": "yes" if m["channel"] == "sms" and len(text) > 160 else "",
                "placeholders_ok": "yes" if ok else "NO - fix {county}/{LEVEL}/{source} by hand",
                "status": "DRAFT machine translation - not validated; do not publish",
                "english_master": m["text"],
            })

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"Saved {len(out_rows)} drafts to {args.out}")
    if args.selftest:
        print(open(args.out, encoding="utf-8").read())


if __name__ == "__main__":
    main()
