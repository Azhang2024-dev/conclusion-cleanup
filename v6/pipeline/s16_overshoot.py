# -*- coding: utf-8 -*-
"""s16_overshoot.py - name the heading that ended the conclusion.

For every document where the rules kept running past the model's end, find the
line that caused it. That turns "82 overshoots" into a list of causes, which is
what the Limitations decision actually turns on.
"""
import os, sys, io, json, re
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
sys.path.insert(0, r"D:\conclusion-wordcount\src")
from wcengine.count import count_words

REF = re.compile(r"^(references?|bibliography|works?cited|literaturecited)", re.I)
APP = re.compile(r"^(appendix|appendices|supplementary|annex)", re.I)
ACK = re.compile(r"^(acknowledge?ments?|funding|declaration|conflictofinterest|"
                 r"dataavailability|ethical|authorstatement|creditauthor|authorcontributions?|"
                 r"abouttheauthors?|authorbiograph|notes?|endnotes?|footnotes?)", re.I)
LIM = re.compile(r"^(limitations?|futureresearch|futuredirections|furtherresearch|"
                 r"implications?|caveats?)", re.I)


def norm(s):
    return re.sub(r"[\s\-]", "", s or "").lower()


def kind_of(t):
    n = norm(t)
    if REF.match(n):
        return "references"
    if APP.match(n):
        return "appendix"
    if ACK.match(n):
        return "ack_front"
    if LIM.match(n):
        return "limitations"
    if re.match(r"^[0-9]+(\.[0-9]+)*\.?", n):
        return "numbered"
    if (t or "").strip().isupper():
        return "caps"
    return "other"


def looks_heading(txt):
    t = (txt or "").strip()
    if not t or len(t) > 90:
        return False
    n = norm(t)
    if re.match(r"^[0-9]+(\.[0-9]+)*\.?", n) and len(n) <= 60:
        return True
    if t.isupper() and len(t) >= 4:
        return True
    if REF.match(n) or APP.match(n) or ACK.match(n) or LIM.match(n):
        return True
    if t.endswith(":") and len(t) <= 60:
        return True
    return False


def main():
    gp = os.path.join(STAGE, "R4_llm_all", "gate.jsonl")
    recs = [json.loads(l) for l in open(gp, encoding="utf-8")]
    stat = Counter()
    for r in recs:
        if r.get("boundary_class") != "code_overshot":
            r["overshoot_kind"] = ""
            r["overshoot_heading"] = ""
            r["overshoot_head_text"] = ""
            continue
        alog = [json.loads(l) for l in open(os.path.join(STAGE, "A_lines", r["sha1"] + ".jsonl"),
                                            encoding="utf-8") if l.strip()]
        cut = (r.get("head_cut") or []) + (r.get("tail_cut") or [])
        hit = ""
        for i in cut:
            if looks_heading(alog[i]["text"]):
                hit = alog[i]["text"].strip()[:60]
                break
        kind = kind_of(hit) if hit else "other"
        r["overshoot_kind"] = kind
        r["overshoot_heading"] = hit
        # words the rules added past that heading
        if hit:
            idx = next((i for i in cut if looks_heading(alog[i]["text"])), None)
            extra = [i for i in cut if idx is not None and i >= idx]
        else:
            extra = cut
        r["overshoot_words"] = count_words(" ".join(alog[i]["text"] for i in extra)) if extra else 0
        stat[kind] += 1
    with open(gp, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("code_overshot causes:", dict(stat))
    for k in stat:
        rows = [r for r in recs if r.get("overshoot_kind") == k]
        print("== %s n=%d  median extra words=%d" % (
            k, len(rows), sorted(r.get("overshoot_words", 0) for r in rows)[len(rows) // 2] if rows else 0))
        for r in rows[:8]:
            print("   %-6s %s |%s| +%d w  in_window=%s lc=%d" % (
                r["id"], r["sha8"], r["overshoot_heading"][:50], r.get("overshoot_words", 0),
                r.get("llm_in_window"), r.get("llm_words")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
