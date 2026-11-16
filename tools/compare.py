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
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def load_reference(path, no2sha):
    """Reference rows: no, k_from, k_to, reason -> (sha1, k0, k1, reason, text)."""
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
            "text": r.get("text", ""),
        })
    return out


def locate(text, new_lines):
    """Where does the ledger's own text live in the fresh conclusion text?

    The ledger was recorded against the old-v6 extraction.  A re-extraction can
    move a line (different page-join) or dissolve it into a neighbour (a page
    number glued onto the closing body line).  Comparing line numbers alone
    would call both of those 'detection gaps', which they are not.

    Returns (kind, index):
        ("moved",  k)  the marked text is a standalone line at k
        ("inline", None)  it survives only inside a longer line
        ("stale",  None)  it is gone from the new text altogether
    """
    target = lib.norm_text(text)
    if not target:
        return ("stale", None)
    for k, ln in enumerate(new_lines):
        if lib.norm_text(ln) == target:
            return ("moved", k)
    for k in range(len(new_lines)):
        acc = ""
        for j in range(k, min(k + 6, len(new_lines))):
            acc = (acc + " " + lib.norm_text(new_lines[j])).strip()
            if acc == target:
                return ("moved", k)
            # the ledger truncates long cell text at 150 chars, so a prefix
            # match on the accumulated lines is the strongest available signal
            if acc.startswith(target):
                return ("moved", k)
            if not target.startswith(acc):
                break
    for k, ln in enumerate(new_lines):
        if target in lib.norm_text(ln):
            return ("inline", k)
    return ("stale", None)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--texts", default=None, help="dir holding {sha1}.txt (default: stage C_conclusions)")
    ap.add_argument("--stage", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    texts_dir = a.texts or os.path.join(lib.Stage(a.stage).texts)

    no2sha = {}
    if a.manifest:
        for r in lib.read_csv(a.manifest):
            # manifests come in two shapes: the delivery one uses pdf_sha1,
            # a hand-made one may use sha1
            sha = r.get("sha1") or r.get("pdf_sha1")
            if r.get("no") and sha:
                no2sha[r["no"]] = sha

    cand = {}
    for r in lib.read_csv(a.candidates):
        cand.setdefault(r["sha1"], set()).add(int(r["line"]))

    ref = load_reference(a.reference, no2sha)
    ref_pairs = {(x["sha1"], k) for x in ref for k in range(x["k0"], x["k1"] + 1)}

    def new_lines_of(sha):
        p = os.path.join(texts_dir, sha + ".txt")
        if not os.path.exists(p):
            return None
        return lib.lines_of(lib.read_text(p))

    rows = []
    for x in ref:
        base_row = {"sha1": x["sha1"][:12], "k_from": x["k0"], "k_to": x["k1"],
                    "reason": x["reason"]}
        hit = [k for k in range(x["k0"], x["k1"] + 1) if k in cand.get(x["sha1"], ())]
        if hit:
            rows.append(dict(base_row, status="found", new_lines=" ".join(map(str, hit[:5])),
                             note=""))
            continue
        # not flagged at the recorded index -- find out why before calling it a gap
        lines = new_lines_of(x["sha1"])
        kind, at = locate(x["text"], lines or [])
        if kind == "moved" and at is not None:
            moved_hit = at in cand.get(x["sha1"], ())
            rows.append(dict(
                base_row, status="moved_found" if moved_hit else "moved_missed",
                new_lines=str(at),
                note="re-extraction moved the line from k%s to k%d" % (x["k0"], at)))
        elif kind == "inline" and at is not None:
            inline_hit = at in cand.get(x["sha1"], ())
            rows.append(dict(
                base_row, status="inline_found" if inline_hit else "inline",
                new_lines=str(at),
                note="marked text survives only inside line k%d" % at))
        else:
            rows.append(dict(base_row, status="MISSED", new_lines="",
                             note="detection gap"))

    for sha, lines in cand.items():
        for k in sorted(lines):
            if (sha, k) not in ref_pairs:
                rows.append({"sha1": sha[:12], "k_from": k, "k_to": k, "reason": "?",
                             "status": "extra", "new_lines": str(k), "note": "candidate not in reference"})

    out = a.out or os.path.splitext(a.candidates)[0] + "_gap.csv"
    lib.write_csv(out, rows)
    c = Counter(r["status"] for r in rows)
    extra = c.pop("extra", 0)
    print("reference %d | %s | extra %d"
          % (len(ref), " ".join("%s %d" % kv for kv in sorted(c.items())), extra))
    gap = c.get("MISSED", 0) + c.get("moved_missed", 0)
    print("detection gap = %d (missed %d + moved_missed %d)"
          % (gap, c.get("MISSED", 0), c.get("moved_missed", 0)))
    print("wrote", out)


if __name__ == "__main__":
    main()
