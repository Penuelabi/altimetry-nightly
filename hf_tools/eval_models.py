#!/usr/bin/env python3
"""Score open translation models on the English -> Nuer / Dinka / Swahili corpus sample.

Reference = the translations in hf_tools/hf_output.json (the dayomtechnologies corpus). Those references are NOT
independently validated, so a score here means "agrees with the corpus", not "is correct". Use it to RANK models and to
decide which to take to a native-speaker review; never treat a number as publishable quality.

Models (all run locally on CPU, nothing is sent to an API):
    nllb-600m   facebook/nllb-200-distilled-600M
    nllb-1.3b   facebook/nllb-200-distilled-1.3B
    madlad-3b   google/madlad400-3b-mt

Usage:
    python hf_tools/eval_models.py --model nllb-600m --n 30
    python hf_tools/eval_models.py --selftest
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "eval_results")

MODELS = {
    "nllb-600m": dict(name="facebook/nllb-200-distilled-600M", kind="nllb", beams=4),
    "nllb-1.3b": dict(name="facebook/nllb-200-distilled-1.3B", kind="nllb", beams=4),
    "madlad-3b": dict(name="google/madlad400-3b-mt", kind="madlad", beams=4),
}
# corpus column -> (NLLB code, MADLAD code)
LANGS = {
    "nuer": ("nus_Latn", "nus"),
    "dinka": ("dik_Latn", "din"),
    "swahili": ("swh_Latn", "sw"),
}
GEN = dict(no_repeat_ngram_size=3, repetition_penalty=1.2)  # identical for every model


def load(model_key):
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    cfg = MODELS[model_key]
    if cfg["kind"] == "nllb":
        tok = AutoTokenizer.from_pretrained(cfg["name"], src_lang="eng_Latn")
        model = AutoModelForSeq2SeqLM.from_pretrained(cfg["name"])
    else:
        tok = AutoTokenizer.from_pretrained(cfg["name"])
        try:
            model = AutoModelForSeq2SeqLM.from_pretrained(cfg["name"], dtype=torch.bfloat16)
        except TypeError:
            model = AutoModelForSeq2SeqLM.from_pretrained(cfg["name"], torch_dtype=torch.bfloat16)
    model.eval()

    def translate(texts, lang, batch=8):
        out = []
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            if cfg["kind"] == "nllb":
                inputs = tok(chunk, return_tensors="pt", padding=True)
                kw = dict(forced_bos_token_id=tok.convert_tokens_to_ids(LANGS[lang][0]))
            else:
                inputs = tok([f"<2{LANGS[lang][1]}> {t}" for t in chunk], return_tensors="pt", padding=True)
                kw = {}
            with torch.no_grad():
                gen = model.generate(**inputs, max_new_tokens=int(inputs["input_ids"].shape[1] * 2) + 10,
                                     num_beams=cfg["beams"], **GEN, **kw)
            out += tok.batch_decode(gen, skip_special_tokens=True)
        return out

    return translate


def score(hyps, refs):
    import sacrebleu
    return round(sacrebleu.corpus_chrf(hyps, [refs]).score, 1), round(sacrebleu.corpus_bleu(hyps, [refs]).score, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(MODELS))
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--data", default=os.path.join(HERE, "hf_output.json"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    rows = json.load(open(args.data, encoding="utf-8"))[: args.n]
    src = [r["english"] for r in rows]
    result = {"model": args.model, "n_sentences": len(rows), "scores": {}, "samples": {},
              "note": "chrF/BLEU vs unvalidated corpus references; ranks models, does not prove correctness"}

    if args.selftest:
        translate = lambda texts, lang: list(texts)  # copy-source stub
        args.model = result["model"] = "selftest"
    else:
        translate = load(args.model)

    t0 = time.time()
    for lang in LANGS:
        refs = [r[lang] for r in rows]
        hyps = translate(src, lang)
        chrf, bleu = score(hyps, refs)
        base_chrf, base_bleu = score(src, refs)  # trivial baseline: copy the English
        result["scores"][lang] = {"chrF": chrf, "BLEU": bleu, "copy_English_chrF": base_chrf}
        result["samples"][lang] = [{"en": src[i], "ref": refs[i], "hyp": hyps[i]} for i in range(min(4, len(rows)))]
        print(f"{args.model} {lang}: chrF {chrf} BLEU {bleu} (copy-English chrF {base_chrf})", flush=True)
    result["seconds"] = round(time.time() - t0)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{args.model}.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Saved", path)


if __name__ == "__main__":
    main()
