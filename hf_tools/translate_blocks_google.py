#!/usr/bin/env python3
"""Draft Dinka / Nuer / Swahili translations of the weekly-advisory blocks with Google Cloud Translation.

Reads and updates aa_config/weekly_blocks.csv (written by aa_p5_weekly_advisory.py --init):
  * fills `text` for a language row ONLY when it is empty, or when it is an unvalidated draft whose English has changed;
  * never touches a row that has `validated_by` (a native speaker's work is never overwritten; stale ones are listed);
  * leaves `validated_by` blank, so aa_p5_weekly_advisory.py will not use the draft until a reviewer corrects it and signs.
Placeholders such as {area} and {counties} are wrapped in notranslate spans; a draft that loses one is left blank.
"""
import argparse
import html
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

CODE = {"din": "din", "nus": "nus", "swa": "sw"}
PH = re.compile(r"\{[A-Za-z_]+\}")
NOTE = "DRAFT machine translation (Google Cloud Translation): needs native-speaker correction; fill validated_by when checked"


def wrap(t):
    return PH.sub(lambda m: f'<span class="notranslate">{m.group(0)}</span>', t)


def unwrap(t):
    return html.unescape(re.sub(r'<span class="notranslate">(.*?)</span>', r"\1", t, flags=re.S))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", default=os.path.join(os.environ.get("AA_CONFIG_DIR", os.path.join(ROOT, "aa_config")), "weekly_blocks.csv"))
    ap.add_argument("--langs", default="din,nus,swa")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(args.blocks, dtype=str, keep_default_na=False)
    en = df[df.language == "en"].set_index("block_id")
    if args.selftest:
        translate = lambda texts, code: ["[" + code + "] " + t for t in texts]
    else:
        from eval_google import get_token
        from translate_google import google_translate
        token = get_token()
        translate = lambda texts, code: google_translate(token, [wrap(t) for t in texts], code, fmt="html")

    stale_validated = []
    for lang in [l.strip() for l in args.langs.split(",") if l.strip()]:
        todo = []
        for i, r in df[df.language == lang].iterrows():
            if r.block_id not in en.index:
                continue
            cur = en.loc[r.block_id, "en_hash"]
            if r.validated_by.strip():
                if r.en_hash not in ("", cur):
                    stale_validated.append((r.block_id, lang))
                continue
            if not r.text.strip() or r.en_hash != cur:
                todo.append(i)
        print(f"{lang}: {len(todo)} blocks to draft")
        if not todo:
            continue
        src = [en.loc[df.at[i, "block_id"], "text"] for i in todo]
        out = translate(src, CODE[lang])
        lost = 0
        for i, s, t in zip(todo, src, out):
            t = t if args.selftest else unwrap(t)
            if sorted(PH.findall(s)) != sorted(PH.findall(t)):
                lost += 1
                df.at[i, "text"], df.at[i, "notes"] = "", "placeholder lost by the translator: translate this block by hand"
                continue
            df.at[i, "text"], df.at[i, "en_hash"], df.at[i, "notes"] = t, en.loc[df.at[i, "block_id"], "en_hash"], NOTE
        print(f"{lang}: drafted {len(todo) - lost}, placeholders lost in {lost}")
    if stale_validated:
        print(f"{len(stale_validated)} validated block(s) are stale (English changed) and need re-validation: {stale_validated[:5]}...")
    df.to_csv(args.blocks, index=False)
    print("Saved", args.blocks)


if __name__ == "__main__":
    main()
