# -*- coding: utf-8 -*-
"""Stage 3: check every candidate against the old marks and explain the gap.

Compares a fresh candidates.csv with a reference mark ledger
(reason / doc / line-range) and writes a CSV of
    found / missed / extra, each with a short diagnosis.

Usage:
    python tools/compare.py --candidates new.csv --reference old.csv
                            [--manifest 02_清单_494篇.csv] [--out gap.csv]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def load_reference(path, no2sha):
    """Reference rows: no, k_from, k_to, reason -> (sha1, k0, k1, reason)."""
    out = []
    for r in lib.read_csv(path):
        sha = r.get("sha1") or no2sha.get(r.get("no", ""))
        if not sha:
            continue
        out.append({
            "sha1": sha,
            "k0": int(r.get("k_from", r.get("line", 0))),
            "k1": int(r.get("k_to", r.get("line", 0))),
            "reason": r.get("reason", ""),
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    no2sha = {}
    if a.manifest:
        for r in lib.read_csv(a.manifest):
            no2sha[r["no"]] = r["pdf_sha1"]

    cand = {}
    for r in lib.read_csv(a.candidates):
        cand.setdefault(r["sha1"], set()).add(int(r["line"]))

    ref = load_reference(a.reference, no2sha)
    ref_pairs = {(x["sha1"], k) for x in ref for k in range(x["k0"], x["k1"] + 1)}

    rows = []
    for x in ref:
        hit = [k for k in range(x["k0"], x["k1"] + 1) if k in cand.get(x["sha1"], ())]
        if hit:
            rows.append({"sha1": x["sha1"][:12], "k_from": x["k0"], "k_to": x["k1"],
                         "reason": x["reason"], "status": "found",
                         "new_lines": " ".join(map(str, hit[:5])), "note": ""})
        else:
            rows.append({"sha1": x["sha1"][:12], "k_from": x["k0"], "k_to": x["k1"],
                         "reason": x["reason"], "status": "MISSED",
                         "new_lines": "", "note": "detection gap"})

    for sha, lines in cand.items():
        for k in sorted(lines):
            if (sha, k) not in ref_pairs:
                rows.append({"sha1": sha[:12], "k_from": k, "k_to": k, "reason": "?",
                             "status": "extra", "new_lines": str(k), "note": "candidate not in reference"})

    out = a.out or os.path.splitext(a.candidates)[0] + "_gap.csv"
    lib.write_csv(out, rows)
    found = sum(1 for r in rows if r["status"] == "found")
    missed = sum(1 for r in rows if r["status"] == "MISSED")
    extra = sum(1 for r in rows if r["status"] == "extra")
    print("reference %d | found %d | missed %d | extra %d" % (len(ref), found, missed, extra))
    print("wrote", out)


if __name__ == "__main__":
    main()
