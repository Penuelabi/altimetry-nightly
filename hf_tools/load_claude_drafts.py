#!/usr/bin/env python3
"""Merge Claude-written drafts (hf_tools/<lang>_drafts.py, dict D) into aa_config/weekly_blocks.csv.
Only fills empty, unvalidated rows; never touches validated_by; placeholders must match the English or the row is skipped.
Drafts are NOT validated: the generator shows them only in preview_unvalidated/."""
import importlib, os, re, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
PH = re.compile(r"\{[A-Za-z_]+\}")
NOTE = {"pga": "DRAFT written by Claude from general knowledge of Juba Arabic: no native-speaker check, spelling not standardised; correct fully and fill validated_by"}
path = os.path.join(ROOT, "aa_config", "weekly_blocks.csv")
df = pd.read_csv(path, dtype=str, keep_default_na=False)
en = df[df.language == "en"].set_index("block_id")
for lang in sys.argv[1:] or ["pga"]:
    D = importlib.import_module(f"{lang}_drafts").D
    n = bad = 0
    for i, r in df[df.language == lang].iterrows():
        t = D.get(r.block_id)
        if not t or r.validated_by.strip() or (r.text.strip() and r.en_hash == en.loc[r.block_id, "en_hash"]):
            continue
        if sorted(PH.findall(t)) != sorted(PH.findall(en.loc[r.block_id, "text"])):
            bad += 1; print("placeholder mismatch:", r.block_id); continue
        df.at[i, "text"], df.at[i, "en_hash"], df.at[i, "notes"] = t, en.loc[r.block_id, "en_hash"], NOTE[lang]; n += 1
    print(f"{lang}: filled {n}, skipped {bad}, missing {sorted(set(en.index) - set(D))[:5]}")
df.to_csv(path, index=False)
