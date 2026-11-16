# -*- coding: utf-8 -*-
"""s50_deliver.py - write the 483-document corpus to txt.

The corpus text is the model's own text field: that decision stands (rules do
not beat the model at this, and rebuilding from lines shifts 377/483 word
counts). What the gate guarantees is that this text is the frozen lines, letter
for letter. So the delivery step only has to do three things: take run1, write
it in the house format, and recompute the word count from the file that ships.

    python s50_deliver.py --out ../定稿_人类语料483篇_2026-11-16
"""
import os, sys, io, json, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
sys.path.insert(0, r"D:\conclusion-wordcount\src")
from wcengine.count import count_words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    txt_dir = os.path.join(a.out, "结论段_txt")
    os.makedirs(txt_dir, exist_ok=True)
    recs = [json.loads(l) for l in open(os.path.join(STAGE, "R4_llm_all", "gate.jsonl"), encoding="utf-8")]
    pool = [r for r in recs if r.get("in_corpus")]
    rows, bad = [], []
    for r in pool:
        sha = r["sha1"]
        res = json.load(open(os.path.join(STAGE, "R4_llm_all", sha, "cplx_t0p0_run1.json"), encoding="utf-8"))
        text = (res.get("text") or "").strip()
        # house format: no BOM, CRLF, no trailing blank line
        body = text.replace("\r\n", "\n").replace("\n", "\r\n")
        p = os.path.join(txt_dir, sha + ".txt")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(body)
        raw = open(p, "rb").read()
        assert not raw.startswith(b"\xef\xbb\xbf"), sha
        assert raw.count(b"\r\n") == body.count("\r\n"), sha
        assert not raw.endswith(b"\r\n"), sha
        w = count_words(raw.decode("utf-8").replace("\r\n", "\n"))
        if w != r["llm_words"]:
            bad.append((r["id"], r["llm_words"], w))
        rows.append({"id": r["id"], "sha1": sha, "journal": r["journal"], "year": r.get("year", ""),
                     "words": w, "llm_words_recorded": r["llm_words"],
                     "start_line": r["llm_start"], "end_line": r["llm_end"],
                     "rel_path": r.get("rel_path", ""),
                     "txt": "结论段_txt/" + sha + ".txt"})
    rows.sort(key=lambda x: x["id"])
    with open(os.path.join(a.out, "00_清单_483篇.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    total = sum(x["words"] for x in rows)
    print("docs", len(rows), "| words", total, "| count mismatch vs record:", len(bad))
    for b in bad[:10]:
        print("   ", b)
    print("min/median/max:", min(x["words"] for x in rows),
          sorted(x["words"] for x in rows)[len(rows)//2], max(x["words"] for x in rows))


if __name__ == "__main__":
    sys.exit(main())
