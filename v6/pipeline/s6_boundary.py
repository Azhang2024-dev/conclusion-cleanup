# -*- coding: utf-8 -*-
"""s6_boundary.py - who is right where the two engines disagree on the boundary.

The gate only inspects the model's own claimed span, so a model that simply
stops early still passes it. This asks the opposite question: of the lines the
rules call conclusion body, which ones did the model leave out? Those are the
only boundary disagreements that cost content.

A conclusion cannot continue past a References / Appendix / Acknowledgements
heading, so a heading between the two ends means the rules overshot.

    python s6_boundary.py
"""
import os, sys, io, json, re
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
sys.path.insert(0, r"D:\conclusion-wordcount\src")
from wcengine.count import count_words

HEAD = re.compile(r"^(references?|bibliography|works?cited|literaturecited|appendix|appendices|"
                  r"acknowledge?ments?|notes?|endnotes?|footnotes?|funding|declarationof|"
                  r"conflictofinterest|dataavailability|abouttheauthors?|authorbiograph\w*|"
                  r"supplementary|authorstatement|creditauthor|authorcontributions?|index)"
                  r"([^a-z]|$)")
DROP_FIELDS = ("head_cut", "tail_cut", "head_extra", "tail_extra", "n_head_cut", "n_tail_cut",
               "boundary_class", "cut_words", "tail_heading_line", "cut_sample",
               "llm_words_if_restored", "would_be_in_window")


def norm(s):
    return re.sub(r"[\s\-]", "", s or "").lower()


HEADWORD = re.compile(r"^(limitations?|futureresearch|futuredirections|furtherresearch|implications?|"
                      r"conclusionw*|concluding|discussion|ethicalw*|authorw*|appendixw*|"
                      r"acknowledgw*|notes?|funding|declarations?|conflictofinterest|"
                      r"dataavailability|abouttheauthors?|references?|bibliography|transcription|"
                      r"abbreviations?|credits?|keywords)", re.I)


def looks_heading(txt):
    """A short line that opens a new section, not a sentence of prose."""
    t = (txt or "").strip()
    if not t or len(t) > 90:
        return False
    n = norm(t)
    if re.match(r"^[0-9]+(\.[0-9]+)*\.?", n) and len(n) <= 60:
        return True
    if t.isupper() and len(t) >= 4:
        return True
    if HEADWORD.match(n):
        return True
    if t.endswith(":") and len(t) <= 60:
        return True
    return False


def main():
    gp = os.path.join(STAGE, "R4_llm_all", "gate.jsonl")
    recs = [json.loads(l) for l in open(gp, encoding="utf-8")]
    stat = Counter()
    for r in recs:
        for k in DROP_FIELDS:
            r.pop(k, None)
        b = json.load(open(os.path.join(STAGE, "B_spans", r["sha1"] + ".json"), encoding="utf-8"))
        kept = sorted(set(b.get("kept_lines") or []))
        cs, ce = r.get("code_start") or 0, r.get("code_end") or 0
        ls, le = r.get("llm_start") or 0, r.get("llm_end") or 0
        alog = [json.loads(l) for l in open(os.path.join(STAGE, "A_lines", r["sha1"] + ".jsonl"),
                                            encoding="utf-8") if l.strip()]
        overlap = bool(cs and le >= cs and ls <= ce)
        if not cs or not le:
            cls = "no_code_span" if not cs else "no_llm_span"
            head_cut = tail_cut = []
        elif not overlap:
            cls = "disjoint"
            head_cut = tail_cut = []
        else:
            head_cut = [i for i in kept if ls > i >= cs]
            tail_cut = [i for i in kept if ce >= i > le]
            cut = head_cut + tail_cut
            hit = None
            if cut:
                lo, hi = (le, ce) if le < ce else (ce, le)
                for i in range(lo + 1, min(hi, len(alog) - 1) + 1):
                    if HEAD.match(norm(alog[i]["text"])[:60]):
                        hit = i
                        break
            head_edge = bool(head_cut) and looks_heading(alog[head_cut[-1]]["text"])
            tail_edge = bool(tail_cut) and looks_heading(alog[tail_cut[0]]["text"])
            if not cut:
                cls = "agree"
            elif hit is not None or head_edge or tail_edge:
                cls = "code_overshot"
            else:
                w = count_words(" ".join(alog[i]["text"] for i in cut))
                cls = "model_cut_small" if w <= 25 else "model_cut_body"
        cut = (head_cut or []) + (tail_cut or [])
        r["head_cut"] = head_cut
        r["tail_cut"] = tail_cut
        r["n_cut"] = len(cut)
        r["cut_words"] = count_words(" ".join(alog[i]["text"] for i in cut)) if cut else 0
        r["boundary_class"] = cls
        r["cut_sample"] = [alog[i]["text"][:110] for i in cut[:3]]
        r["llm_words_restored"] = (r.get("llm_words") or 0) + r["cut_words"]
        r["in_window_if_restored"] = 1 if 250 <= r["llm_words_restored"] <= 600 else 0
        stat[cls] += 1
    with open(gp, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(dict(stat))
    for cls in ("model_cut_body", "disjoint", "model_cut_small", "code_overshot"):
        rows = [r for r in recs if r["boundary_class"] == cls]
        if not rows:
            continue
        print("== %s n=%d total cut words=%d median=%d" % (
            cls, len(rows), sum(r["cut_words"] for r in rows),
            sorted(r["cut_words"] for r in rows)[len(rows) // 2]))
        for r in sorted(rows, key=lambda x: -x["cut_words"])[:5]:
            print("   %-6s %s cut=%d lc=%d span %s-%s code %s-%s" % (
                r["id"], r["sha8"], r["cut_words"], r["llm_words"], r["llm_start"], r["llm_end"],
                r["code_start"], r["code_end"]))
            for s in r["cut_sample"]:
                print("        | " + s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
