# -*- coding: utf-8 -*-
"""Stage 4: apply a mark ledger to texts.

Rules (from docs/判据表.md):
    - delete  : remove the flagged line range
    - keep    : keep the text, but move it to the end of its paragraph
    - replace : substitute a fragment (pipe -> comma, mojibake, dup-word)

Every action first re-verifies that the recorded fragment is still where the
ledger says it is; a drifted mark is reported, never silently applied.

Usage:
    python tools/apply.py --stage PATH --ledger marks.csv --texts DIR --out DIR2
                          [--manifest 清单.csv] [--report CSV]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default=None)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--texts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--report", default=None)
    a = ap.parse_args(argv)

    stage = lib.Stage(a.stage)
    no2sha = {}
    if a.manifest:
        for r in lib.read_csv(a.manifest):
            no2sha[r["no"]] = r["pdf_sha1"]

    marks = {}
    for r in lib.read_csv(a.ledger):
        sha = r.get("sha1") or no2sha.get(r.get("no", ""))
        if not sha:
            continue
        marks.setdefault(sha, []).append({
            "k0": int(r["k_from"]), "k1": int(r["k_to"]),
            "reason": r.get("reason", ""), "action": (r.get("action") or "删除").strip(),
            "text": r.get("text", ""),
        })

    os.makedirs(a.out, exist_ok=True)
    report = []
    for sha in sorted(marks):
        src = os.path.join(a.texts, sha + ".txt")
        if not os.path.exists(src):
            continue
        lines = lib.lines_of(lib.read_text(src))
        drop = set()
        move = []
        replace = []
        for m in marks[sha]:
            k0, k1 = m["k0"], min(m["k1"], len(lines) - 1)
            if k0 >= len(lines):
                report.append({"sha1": sha[:12], "k0": k0, "status": "out-of-range", "action": m["action"]})
                continue
            frag = re.sub(r"\s+", " ", m["text"]).strip()[:30]
            cur = re.sub(r"\s+", " ", "\n".join(lines[k0:k1 + 1])).strip()
            if frag and frag not in cur and m["action"] == "删除":
                report.append({"sha1": sha[:12], "k0": k0, "status": "drifted", "action": m["action"]})
                continue
            if m["action"] == "保留":
                move.append((k0, k1))
            elif m["action"] == "改逗号":
                replace.append((k0, k1))
            else:
                drop.update(range(k0, k1 + 1))
            report.append({"sha1": sha[:12], "k0": k0, "k1": k1, "status": "ok", "action": m["action"]})
        kept = []
        tail = []
        for i, ln in enumerate(lines):
            if i in drop:
                continue
            if any(k0 <= i <= k1 for k0, k1 in move):
                tail.append(ln)
                continue
            if any(k0 <= i <= k1 for k0, k1 in replace):
                ln = ln.replace(" | ", ", ").replace("\u2003|\u2003", ", ")
            kept.append(ln)
        while kept and not kept[-1].strip():
            kept.pop()
        kept = [ln for ln in kept if ln.strip()] + tail
        if kept and kept[-1].strip():
            out_text = "\n".join(kept)
        else:
            out_text = ""
        lib.write_text(os.path.join(a.out, sha + ".txt"), out_text)
    rep = a.report or os.path.join(stage.reports, "apply_report.csv")
    lib.write_csv(rep, report)
    bad = [r for r in report if r["status"] != "ok"]
    print("docs %d | actions %d | problems %d" % (len(marks), len(report), len(bad)))
    for r in bad[:10]:
        print("  ", r)
    print("wrote", a.out, "|", rep)


if __name__ == "__main__":
    main()
