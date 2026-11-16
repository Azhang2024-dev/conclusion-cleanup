# -*- coding: utf-8 -*-
"""s42_apply_read.py - fold the 483-document personal read into the records."""
import os, sys, io, json, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)

def main():
    rd = {}
    p = os.path.join(STAGE, "R7_fullread", "fullread.tsv")
    for row in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
        rd[row["id"]] = (row["verdict"].strip(), row["note"].strip())
    gp = os.path.join(STAGE, "R4_llm_all", "gate.jsonl")
    recs = [json.loads(l) for l in open(gp, encoding="utf-8")]
    n = 0
    for r in recs:
        v = rd.get(r["id"])
        if v:
            r["read_verdict"], r["read_note"] = v
            n += 1
        else:
            r["read_verdict"], r["read_note"] = "", ""
    with open(gp, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print("applied=%d  verdict=%s" % (n, dict(Counter(v[0] for v in rd.values()))))
    print("in_corpus=%d  all_read=%d" % (sum(1 for r in recs if r.get("in_corpus")),
                                         sum(1 for r in recs if r.get("read_verdict"))))
    return 0

if __name__ == "__main__":
    sys.exit(main())
