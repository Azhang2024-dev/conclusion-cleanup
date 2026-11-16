# -*- coding: utf-8 -*-
"""s12_apply.py - attach the review verdicts to every record, then rebuild.

Documents whose packet was never run stay marked "未复核" instead of drifting
into a silent pass.
"""
import os, sys, io, json, glob

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
REV = os.path.join(STAGE, "R5_review")


def main():
    gp = os.path.join(STAGE, "R4_llm_all", "gate.jsonl")
    recs = [json.loads(l) for l in open(gp, encoding="utf-8")]
    got = {}
    for f in sorted(glob.glob(os.path.join(REV, "out", "*.tsv"))):
        rows = open(f, encoding="utf-8-sig").read().splitlines()
        if not rows:
            continue
        head = rows[0].split("\t")
        for line in rows[1:]:
            c = line.split("\t")
            if len(c) < 8:
                continue
            d = dict(zip(head, c))
            did = d.get("id", "").strip()
            got[did] = {"verdict": d.get("\u7ed3\u8bba", "").strip(),
                        "note": d.get("\u8bf4\u660e", "").strip(),
                        "B1": d.get("B1\u8d77\u70b9", "").strip(),
                        "B2": d.get("B2\u7ec8\u70b9", "").strip(),
                        "B3": d.get("B3\u4e22\u5931", "").strip(),
                        "B4": d.get("B4\u6df7\u5165", "").strip(),
                        "B5": d.get("B5\u6539\u5b57", "").strip()}
    dups = {}
    dp = os.path.join(STAGE, "R6_corpus_check", "dups.json")
    if os.path.exists(dp):
        dups = json.load(open(dp, encoding="utf-8"))
    for r in recs:
        v = got.get(r["id"])
        if v:
            r.update({"review_verdict": v["verdict"], "review_note": v["note"],
                      "review_B1": v["B1"], "review_B2": v["B2"], "review_B3": v["B3"],
                      "review_B4": v["B4"], "review_B5": v["B5"]})
        else:
            r.update({"review_verdict": "\u672a\u590d\u6838", "review_note": "", "review_B1": "",
                      "review_B2": "", "review_B3": "", "review_B4": "", "review_B5": ""})
        auto_ok = (r["gate_status"] == "PASS" and r.get("llm_in_window") == 1
                   and r.get("boundary_class") in ("agree", "code_overshot", "model_cut_small"))
        # a reviewed document is judged by the review; an unreviewed one keeps the
        # automated verdict but is flagged, never silently promoted
        r["dup_of"] = dups.get(r["id"], "")
        r["in_corpus"] = 1 if (auto_ok and r["review_verdict"] in ("ok", "未复核")
                               and not r["dup_of"]) else 0
    with open(gp, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print("verdicts applied:", sum(1 for r in recs if r["review_verdict"] != "\u672a\u590d\u6838"))
    print("verdict dist:", Counter(r["review_verdict"] for r in recs))
    print("in_corpus:", sum(r["in_corpus"] for r in recs))
    w = sorted(r["llm_words"] for r in recs if r["in_corpus"])
    print("corpus words: n=%d min=%d median=%d max=%d total=%d" % (
        len(w), w[0], w[len(w) // 2], w[-1], sum(w)))
    fx = [r for r in recs if r["review_verdict"] == "fix"]
    print("fix cases in window:", sum(1 for r in fx if r.get("llm_in_window")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
