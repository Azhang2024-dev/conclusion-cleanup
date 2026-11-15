# -*- coding: utf-8 -*-
"""Stage 3: read every splice. For each mark, print the line before and the
line after, and flag the four risky combinations.

    prev-end-terminated   previous line ends a sentence  -> safe
    prev-open             previous line runs on         -> must join with next
    next-lower            next line continues lowercase -> sentence continues
    next-punct            next line starts with , ; . ) -> dangling comma

A mark is DANGEROUS when prev-open and not next-lower: the sentence was cut in
the middle and the following line does not continue it.

Usage:
    python tools/splice_check.py --stage PATH --ledger marks.csv [--out CSV]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

TERM = re.compile(r"[.!?:;\"”’)\]]\s*$")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default=None)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--manifest", default=None, help="map no -> sha1 when ledger has no sha1")
    ap.add_argument("--texts", default=None, help="defaults to <stage>/C_conclusions")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    stage = lib.Stage(a.stage)
    texts = a.texts or stage.texts
    no2sha = {}
    if a.manifest:
        for r in lib.read_csv(a.manifest):
            no2sha[r["no"]] = r["pdf_sha1"]
    marks = {}
    for r in lib.read_csv(a.ledger):
        sha = r.get("sha1") or no2sha.get(r.get("no", ""))
        if not sha:
            continue
        marks.setdefault(sha, []).append((int(r["k_from"]), int(r["k_to"]), r.get("reason", "")))

    rows = []
    for sha, items in marks.items():
        p = os.path.join(texts, sha + ".txt")
        if not os.path.exists(p):
            continue
        lines = lib.lines_of(lib.read_text(p))
        for k0, k1, reason in sorted(items):
            if k0 >= len(lines):
                continue
            k1 = min(k1, len(lines) - 1)
            prev = lines[k0 - 1].rstrip() if k0 > 0 else ""
            nxt = lines[k1 + 1].lstrip() if k1 + 1 < len(lines) else ""
            flags = []
            if not prev:
                flags.append("at-start")
            elif TERM.search(prev):
                flags.append("prev-term")
            else:
                flags.append("prev-open")
            if not nxt:
                flags.append("at-end")
            else:
                if nxt[:1].islower():
                    flags.append("next-lower")
                if re.match(r"^[\s,;.)\]]", nxt):
                    flags.append("next-punct")
            dangerous = ("prev-open" in flags) and ("next-lower" not in flags) and ("at-end" not in flags)
            rows.append({
                "sha1": sha[:12], "k_from": k0, "k_to": k1, "reason": reason,
                "flags": ",".join(flags), "verdict": "DANGEROUS" if dangerous else "ok",
                "prev_tail": prev[-60:], "next_head": nxt[:60],
            })

    out = a.out or os.path.join(stage.reports, "splice_check.csv")
    lib.write_csv(out, rows)
    bad = [r for r in rows if r["verdict"] == "DANGEROUS"]
    print("marks %d | dangerous %d" % (len(rows), len(bad)))
    for r in bad[:10]:
        print("  %s k=%d %s | ...%s || %s..." % (r["sha1"], r["k_from"], r["reason"], r["prev_tail"], r["next_head"]))
    print("wrote", out)


if __name__ == "__main__":
    main()
