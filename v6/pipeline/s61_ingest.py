# -*- coding: utf-8 -*-
"""s61_ingest.py - triage the new batch, then merge the eligible documents into the corpus.

Triage classes (why a document does not enter):
  non_article_pdf  the file is front matter / editorial policy, not the paper
  empty_span       the model returned no conclusion at all (same symptom)
  gate_fail        the gate found a silent drop or a rewrite -> text not trustworthy
  out_of_window    conclusion outside 251-599 words
"""
import os, sys, io, csv, json, re, shutil, collections

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
sys.path.insert(0, r"D:\conclusion-wordcount\src")
from wcengine.count import count_words

OLD = os.path.join(STAGE, "定稿_人类语料483篇_2026-11-16", "结论段_txt")
OUT = os.path.join(STAGE, "定稿_人类语料_合并_2026-11-16")
TXT = os.path.join(OUT, "结论段_txt")
ACK = re.compile(r"(acknowledg|data availability|conflict of interest|declaration of|credit author)", re.I)
SECT = re.compile(r"(^|\n)\s*\d+(\.\d+)*\.?\s+[A-Z][a-z]")


def shape(t):
    flags = []
    if not t:
        return ["empty"]
    if t[0].islower():
        flags.append("lower_first")
    if t[-1] not in ".?!":
        flags.append("no_end_punct")
    if ACK.search(t[:400]):
        flags.append("ack_inside")
    if SECT.search(t):
        flags.append("section_heading")
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    if len(sents) > 6 and len(set(sents)) < len(sents) * 0.8:
        flags.append("repetitive")
    return flags


# Conclusions that the corpus already holds under another file. The dedupe gate
# found them by 8-gram overlap after their titles failed to match (repository
# versions carry different titles and line breaks).
DROP_SHA = {
    "7583deb0f397d2d456c966c1624e4b138dcd0bfd",   # X138 ~ 323, Applied linguistics J8 0.839
    "beedcef33bdcebe1f6b64619ba83e86c8acaf5be",   # X238 ~ 269, IJCL J8 1.000
    "c5f7f988e784efa5a4d38202285d7ee6c34b2f7b",   # X251 ~ 083, Cognitive linguistics J8 1.000
    "e6153702b2b9fb3c676440a516627899ad3d84ff",   # X299 ~ 090, Applied linguistics J8 0.766
    "36fb5239d70fc25247b7e56c290aebd5e65b444c",   # X051 ~ 497, IJCL J8 1.000
}


def main():
    gate_n = [json.loads(l) for l in open(os.path.join(STAGE, "R12_new_batch", "gate.jsonl"), encoding="utf-8")]
    led = {r["sha1"]: r for r in csv.DictReader(
        open(os.path.join(STAGE, "R11_新增PDF_OA_2026-11-16", "download_ledger.csv"), encoding="utf-8-sig"))}
    os.makedirs(TXT, exist_ok=True)

    verdict = {}
    for r in gate_n:
        if r["sha1"] in DROP_SHA:
            verdict[r["sha1"]] = "dup_of_existing"
            continue
        t = (led.get(r["sha1"], {}).get("type") or "")
        w = r.get("llm_words") or 0
        if t not in ("article", "review"):
            verdict[r["sha1"]] = "non_article_pdf"
        elif r.get("gate_status") != "PASS":
            verdict[r["sha1"]] = "gate_fail:" + str(r.get("fail_class"))
        elif w == 0:
            verdict[r["sha1"]] = "empty_span"
        elif not (251 <= w <= 599):
            verdict[r["sha1"]] = "out_of_window"
        else:
            verdict[r["sha1"]] = "keep"
    print("triage:", collections.Counter(v.split(":")[0] for v in verdict.values()), flush=True)
    print("gate_fail detail:", collections.Counter(v for v in verdict.values() if v.startswith("gate_fail")), flush=True)

    rows = []
    # keep the existing 483 first
    old_index = list(csv.DictReader(open(os.path.join(STAGE, "定稿_人类语料483篇_2026-11-16", "00_清单_483篇.csv"), encoding="utf-8-sig")))
    for r in old_index:
        src = os.path.join(OLD, r["sha1"] + ".txt")
        dst = os.path.join(TXT, r["sha1"] + ".txt")
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        rows.append(dict(id=r["id"], sha1=r["sha1"], journal=r["journal"], year=r["year"],
                         words=r["words"], source="v6_2026-11-16_主体483",
                         start_line=r["start_line"], end_line=r["end_line"], txt="结论段_txt/" + r["sha1"] + ".txt"))

    n_new, shape_flags = 0, []
    for r in gate_n:
        if verdict[r["sha1"]] != "keep":
            continue
        res = json.load(open(os.path.join(STAGE, "R4_llm_all", r["sha1"], "cplx_t0p0_run1.json"), encoding="utf-8"))
        text = (res.get("text") or "").strip()
        body = text.replace("\r\n", "\n").replace("\n", "\r\n")
        p = os.path.join(TXT, r["sha1"] + ".txt")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(body)
        w = count_words(text)
        fl = shape(text)
        if fl:
            shape_flags.append((r["sha8"], r["journal"], w, fl))
        lr = led.get(r["sha1"], {})
        rows.append(dict(id=r.get("id", ""), sha1=r["sha1"], journal=r["journal"], year=r["year"],
                         words=w, source="OA新增_2026-11-16", start_line=r["llm_start"],
                         end_line=r["llm_end"], txt="结论段_txt/" + r["sha1"] + ".txt"))
        n_new += 1

    rows.sort(key=lambda x: (x["source"], str(x["id"])))
    with open(os.path.join(OUT, "00_清单_合并.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    total = sum(int(r["words"]) for r in rows)
    print("\nmerged docs:", len(rows), "| new:", n_new, "| words:", total, flush=True)
    print("min/median/max:", min(int(r["words"]) for r in rows),
          sorted(int(r["words"]) for r in rows)[len(rows)//2], max(int(r["words"]) for r in rows), flush=True)
    print("shape flags on new docs:", len(shape_flags), flush=True)
    for s in shape_flags:
        print("   ", s, flush=True)


if __name__ == "__main__":
    sys.exit(main())
