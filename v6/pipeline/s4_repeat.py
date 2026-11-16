# -*- coding: utf-8 -*-
"""s4_repeat.py - run1 vs run2 at the same temperature: what actually repeats.

Three levels, because they fail for different reasons:
  span    identical start_line and end_line
  text    identical after the gate's normalisation (whitespace, hyphens, marks)
  bytes   identical raw string
"""
import os, sys, io, json, re, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STAGE, "_skill_repo", "span-locator", "tools"))
sys.path.insert(0, os.path.join(STAGE, "_tools"))


def loader():
    p = os.path.join(STAGE, "_skill_repo", "span-locator", "tools", "verify_output.py")
    src = open(p, encoding="utf-8").read()
    mod = {"__name__": "g"}
    exec(compile(src, p, "exec"), mod)
    return mod


def main():
    mod = loader()
    norm = mod["norm"]
    out = os.path.join(STAGE, "R4_llm_all")
    root = os.path.join(out, "r1_vs_r2.jsonl")
    rows = []
    for sha in sorted(os.listdir(os.path.join(STAGE, "A_lines"))):
        if not sha.endswith(".jsonl"):
            continue
        sha = sha[:-6]
        p1 = os.path.join(out, sha, "cplx_t0p0_run1.json")
        p2 = os.path.join(out, sha, "cplx_t0p0_run2.json")
        if not (os.path.exists(p1) and os.path.exists(p2)):
            rows.append({"sha1": sha, "state": "missing"})
            continue
        a = json.load(open(p1, encoding="utf-8"))
        b = json.load(open(p2, encoding="utf-8"))
        ta, tb = a.get("text", "") or "", b.get("text", "") or ""
        rows.append({
            "sha1": sha,
            "span1": "%s-%s" % (a.get("start_line"), a.get("end_line")),
            "span2": "%s-%s" % (b.get("start_line"), b.get("end_line")),
            "span_same": int(a.get("start_line") == b.get("start_line") and a.get("end_line") == b.get("end_line")),
            "text_same": int(norm(ta) == norm(tb)),
            "bytes_same": int(ta == tb),
            "len1": len(ta), "len2": len(tb),
            "d_words": 0,
        })
    with open(root, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ok = [r for r in rows if r.get("state") != "missing"]
    n = len(ok)
    print("pairs=%d" % n)
    for k in ("span_same", "text_same", "bytes_same"):
        s = sum(r[k] for r in ok)
        print("%-11s %d/%d  %.1f%%" % (k, s, n, 100.0 * s / n))
    diff = [r for r in ok if not r["text_same"]]
    print("text differs: %d" % len(diff))
    for r in diff[:15]:
        print("  %s %s | %s | len %d vs %d" % (r["sha1"][:8], r["span1"], r["span2"], r["len1"], r["len2"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
