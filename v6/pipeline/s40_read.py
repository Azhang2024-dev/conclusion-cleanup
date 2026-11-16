# -*- coding: utf-8 -*-
"""s40_read.py - print a slice of the candidate pool for a full read-through.

Order is fixed (by id) so a batch can be resumed, and every document comes with
one header line of context plus its conclusion text. Nothing else is printed:
the point is to read the text, not to re-read the machinery.

    python s40_read.py --start 0 --count 30
"""
import os, sys, io, json, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
OUT = os.path.join(STAGE, "R7_fullread")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--out", default="")
    ap.add_argument("--queue", default="")
    a = ap.parse_args()
    recs = [json.loads(l) for l in open(os.path.join(STAGE, "R4_llm_all", "gate.jsonl"), encoding="utf-8")]
    os.makedirs(OUT, exist_ok=True)
    done = set()
    dp = os.path.join(OUT, "read.txt")
    if os.path.exists(dp):
        done = set(x.strip() for x in open(dp, encoding="utf-8").read().split() if x.strip())
    def sortkey(r):
        i = r["id"]
        return (0, int(i)) if i.isdigit() else (1, i)
    q = sorted([r for r in recs if r.get("in_corpus")], key=sortkey)
    qp = os.path.join(OUT, "queue.tsv")
    with open(qp, "w", encoding="utf-8") as fh:
        fh.write("idx\tid\tsha8\tjournal\tyear\twords\tspan\tboundary\tgate\n")
        for k, r in enumerate(q):
            fh.write("%d\t%s\t%s\t%s\t%s\t%d\t%s-%s\t%s\t%s\n" % (
                k, r["id"], r["sha8"], r["journal"], r["year"], r["llm_words"],
                r["llm_start"], r["llm_end"], r["boundary_class"], r["gate_status"]))
    todo = [r for r in q if r["id"] not in done]
    print("queue=%d  already_read=%d  remaining=%d  this_batch=%d (idx %d..%d)" % (
        len(q), len(done), len(todo), min(a.count, len(todo)), a.start, a.start + min(a.count, len(todo)) - 1))
    batch = todo[a.start:a.start + a.count]
    buf = []
    for r in batch:
        t = json.load(open(os.path.join(STAGE, "R4_llm_all", r["sha1"], "cplx_t0p0_run1.json"),
                           encoding="utf-8"))["text"]
        note = ""
        if r.get("boundary_class") != "agree":
            note = " | 越界:%s" % (r.get("overshoot_heading") or r["boundary_class"])
        buf.append("@@@ %s|%s|%s|%d词%s" % (r["id"], r["sha8"], r["journal"], r["llm_words"], note))
        import textwrap
        for para in [p for p in t.split(chr(10)) if p.strip()]:
            buf.extend(textwrap.wrap(" ".join(para.split()), 108) or [""])
        buf.append("")
    body = "\n".join(buf)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(body)
        print("wrote %s  docs=%d  chars=%d" % (a.out, len(batch), len(body)))
    else:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
