#!/usr/bin/env python3
"""Translate English text into Nuer, Dinka and Swahili with Meta's NLLB-200 via the Hugging Face API.

NLLB-200 language codes used:
    nus_Latn  Nuer
    dik_Latn  Dinka (NLLB's single "Southwestern Dinka" code; dialect coverage is limited)
    swh_Latn  Swahili

The token is read from the GitHub secret exposed as HUGGINGFACE (falls back to HF_TOKEN).

Usage:
    python translate_hf.py                      # translates the built-in Juba County text
    python translate_hf.py --file input.txt     # translate your own text (one paragraph per line)
    python translate_hf.py --local              # run the model locally with transformers instead of the API
"""
import argparse
import os
import re
import sys

MODEL = "facebook/nllb-200-distilled-600M"
LANGS = {"Nuer": "nus_Latn", "Dinka": "dik_Latn", "Swahili": "swh_Latn"}

DEFAULT_TEXT = """PICTORIAL: The Caretaker Commissioner of Juba County, Kalisto Lado, on Friday, 9 October 2026, launched the completion project of the County Headquarters Building.
The project, undertaken by Hatay Holding Company Ltd., is expected to be completed within four months, with construction scheduled to run 24 hours a day.
The Commissioner also announced plans to construct headquarters for all 13 Payams and the Bomas of Juba County."""


def split_sentences(paragraph: str):
    # NLLB is trained on sentence-level data, so translate sentence by sentence.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", paragraph.strip())
    return [p for p in parts if p]


def make_api_translator(token):
    from huggingface_hub import InferenceClient

    client = InferenceClient(token=token)

    def translate(text, tgt):
        out = client.translation(text, model=MODEL, src_lang="eng_Latn", tgt_lang=tgt)
        return out.translation_text

    return translate


def make_local_translator():
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL, src_lang="eng_Latn")
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL)
    model.eval()

    def translate(text, tgt):
        inputs = tok(text, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(
                **inputs,
                forced_bos_token_id=tok.convert_tokens_to_ids(tgt),
                max_new_tokens=300,
                num_beams=4,
            )
        return tok.batch_decode(out, skip_special_tokens=True)[0]

    return translate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="text file to translate (one paragraph per line)")
    ap.add_argument("--local", action="store_true", help="run the model locally instead of the HF API")
    ap.add_argument("--out", default="translations.md")
    args = ap.parse_args()

    text = open(args.file, encoding="utf-8").read() if args.file else DEFAULT_TEXT
    paragraphs = [p for p in text.splitlines() if p.strip()]

    if args.local:
        translate = make_local_translator()
    else:
        token = os.environ.get("HUGGINGFACE") or os.environ.get("HF_TOKEN")
        if not token:
            sys.exit("No token found: set the HUGGINGFACE secret/env var (or HF_TOKEN).")
        api_translate = make_api_translator(token)
        state = {"fn": api_translate}

        def translate(text, tgt):
            try:
                return state["fn"](text, tgt)
            except Exception as e:  # API unavailable for this model: fall back to running it locally
                if state["fn"] is not api_translate:
                    raise
                print(f"HF API failed ({type(e).__name__}: {str(e)[:200]}); falling back to local model ...")
                state["fn"] = make_local_translator()
                return state["fn"](text, tgt)

    lines = ["# Translations", "", "Machine translation (NLLB-200). Have a native speaker review before publishing.", ""]
    lines += ["## English (source)", ""] + [p + "\n" for p in paragraphs]

    for name, code in LANGS.items():
        print(f"Translating to {name} ({code}) ...")
        lines += [f"## {name} ({code})", ""]
        for p in paragraphs:
            translated = " ".join(translate(s, code) for s in split_sentences(p))
            lines += [translated, ""]

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
