#!/usr/bin/env python3
"""Score Google Cloud Translation (Basic, v2) on the same corpus sample as eval_models.py.

Credentials: the service-account JSON in the GEE_SERVICE_ACCOUNT_KEY secret (project sudan-1575919084043).
The service account needs the "Cloud Translation API User" role (roles/cloudtranslate.user) and the Cloud
Translation API must be enabled on the project. Errors are recorded per language, never swallowed silently.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eval_models as em  # reuses LANGS, score, OUT_DIR (heavy imports are inside em.load only)

URL = "https://translation.googleapis.com/language/translate/v2"
CODES = {"nuer": "nus", "dinka": "din", "swahili": "sw"}


def get_token():
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    raw = os.environ.get("GEE_SERVICE_ACCOUNT_KEY")
    if not raw:
        sys.exit("GEE_SERVICE_ACCOUNT_KEY is not set")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/cloud-translation"])
    creds.refresh(Request())
    return creds.token


def google_translate(token, texts, target):
    import requests

    out = []
    for i in range(0, len(texts), 50):
        r = requests.post(URL, headers={"Authorization": f"Bearer {token}"}, timeout=60,
                          json={"q": texts[i:i + 50], "source": "en", "target": target, "format": "text"})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
        out += [t["translatedText"] for t in r.json()["data"]["translations"]]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--data", default=os.path.join(HERE, "hf_output.json"))
    args = ap.parse_args()

    rows = json.load(open(args.data, encoding="utf-8"))[: args.n]
    src = [r["english"] for r in rows]
    result = {"model": "google-translate-v2", "n_sentences": len(rows), "scores": {}, "samples": {}, "errors": {},
              "note": "chrF/BLEU vs unvalidated corpus references; ranks models, does not prove correctness"}
    token = get_token()
    t0 = time.time()
    for lang, code in CODES.items():
        refs = [r[lang] for r in rows]
        try:
            hyps = google_translate(token, src, code)
        except Exception as e:
            result["errors"][lang] = str(e)
            print(f"google {lang} ({code}): FAILED {e}", flush=True)
            continue
        chrf, bleu = em.score(hyps, refs)
        base, _ = em.score(src, refs)
        result["scores"][lang] = {"chrF": chrf, "BLEU": bleu, "copy_English_chrF": base}
        result["samples"][lang] = [{"en": src[i], "ref": refs[i], "hyp": hyps[i]} for i in range(min(4, len(rows)))]
        print(f"google {lang} ({code}): chrF {chrf} BLEU {bleu} (copy-English chrF {base})", flush=True)
    result["seconds"] = round(time.time() - t0)
    os.makedirs(em.OUT_DIR, exist_ok=True)
    path = os.path.join(em.OUT_DIR, "google-translate-v2.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Saved", path)


if __name__ == "__main__":
    main()
