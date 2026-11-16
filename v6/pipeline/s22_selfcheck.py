# -*- coding: utf-8 -*-
"""s22_selfcheck.py - what the gate cannot see, checked by shape.

The gate compares the model text with the frozen lines inside the model's own
span. It cannot notice that the span itself starts mid-sentence, ends without a
full stop, or swallowed a section heading. These four shape tests can, and they
cost nothing.
"""
import os, sys, io, json, re
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)

ACK = re.compile(r"(acknowledg|data availability|conflict of interest|declaration of|"
                 r"credit author|author contribution|funding|ethical approval|"
                 r"about the author|correspondence)", re.I)
SECT = re.compile(r"(^|\n)\s*(\d+(\.\d+)*\.?\s+[A-Z][a-z])")
REFS = re.compile(r"\((?:[A-Z][A-Za-z\u00c0-\u024f]+,?\s*(?:&|and)?\s*[A-Z]?[a-z]*\s*,?\s*)?(19|20)\d\d[a-z]?(?:,\s*p\.?\s*\d+)?\)")


def main():
    gp = os.path.join(STAGE, "R4_llm_all", "gate.jsonl")
    recs = [json.loads(l) for l in open(gp, encoding="utf-8")]
    out = []
    for r in recs:
        if not r.get("in_corpus"):
            continue
        p = os.path.join(STAGE, "R4_llm_all", r["sha1"], "cplx_t0p0_run1.json")
        t = json.load(open(p, encoding="utf-8")).get("text", "")
        s = t.strip()
        flags = []
        if s and s[0].islower():
            flags.append("starts_lower")
        if s and s[-1] not in ".!?\"')\u201d\u2019":
            flags.append("no_end_punct")
        if SECT.search(s):
            flags.append("section_heading")
        if ACK.search(s):
            flags.append("ack_word")
        refs = len(REFS.findall(s))
        if refs >= 6:
            flags.append("many_citations")
        w = re.findall(r"[A-Za-z0-9]+(?:['\u2019\-][A-Za-z0-9]+)*", s)
        if len(w) > 12 and len(set(x.lower() for x in w)) / len(w) < 0.45:
            flags.append("repetitive")
        r["shape_flags"] = flags
        r["cite_n"] = refs
        out.append((r["id"], r["sha8"], r["llm_words"], flags, s[:70], s[-70:]))
    with open(gp, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    c = Counter()
    for _, _, _, f, _, _ in out:
        for x in f:
            c[x] += 1
    print("in_corpus=%d  clean=%d" % (len(out), sum(1 for o in out if not o[3])))
    print(dict(c))
    for f in c:
        print("== " + f)
        for o in [o for o in out if f in o[3]][:8]:
            print("   %-6s %s %5dw |%s| ... |%s|" % (o[0], o[1], o[2], o[4], o[5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
