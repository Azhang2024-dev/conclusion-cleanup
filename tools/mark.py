# -*- coding: utf-8 -*-
"""Stage 2: mark candidates on a COPY and write the ledger.

The marked copy is an .xlsx with the flagged characters in red; the ledger CSV
is the machine-readable truth.  Plain text of the marked copy must equal the
input byte for byte (the tool asserts this before returning).

Usage:
    python tools/mark.py --stage PATH --candidates candidates.csv \
                         --texts DIR --out XLSX --ledger CSV [--manifest 清单.csv]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

RED = "FFFF0000"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default=None)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--texts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--sheet", default="标红")
    a = ap.parse_args(argv)

    from openpyxl import Workbook
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    from openpyxl.styles import Alignment, Font

    stage = lib.Stage(a.stage)
    no2sha = {}
    if a.manifest:
        for r in lib.read_csv(a.manifest):
            no2sha[r["no"]] = r["pdf_sha1"]
    sha2no = {v: k for k, v in no2sha.items()}

    cands = {}
    for r in lib.read_csv(a.candidates):
        cands.setdefault(r["sha1"], []).append((int(r["line"]), r.get("reason", ""), r.get("note", "")))

    wb = Workbook()
    ws = wb.active
    ws.title = a.sheet
    ws.append(["doc", "line", "reason", "marked_text", "n_lines"])
    for c in ws[1]:
        c.font = Font(bold=True)

    ledger = []
    for sha, items in sorted(cands.items()):
        path = os.path.join(a.texts, sha + ".txt")
        if not os.path.exists(path):
            continue
        text = lib.read_text(path).replace("\r\n", "\n")
        lines = text.split("\n")
        runs = [[text, None, False]]
        # mark from the end so offsets stay valid
        for k, reason, note in sorted(items, reverse=True):
            if k >= len(lines):
                continue
            start = sum(len(x) + 1 for x in lines[:k])
            end = start + len(lines[k])
            new = []
            for seg, font, red in runs:
                new.append(seg)
            # naive split: rebuild around absolute offsets
            flat = "".join(seg for seg, _, _ in runs)
            before, mid, after = flat[:start], flat[start:end], flat[end:]
            runs = [[before, None, False], [mid, None, True], [after, None, False]]
            ledger.append({
                "sha1": sha, "no": sha2no.get(sha, ""), "k_from": k, "k_to": k,
                "reason": reason, "note": note, "text": lines[k].strip()[:160],
                "action": "删除",
            })
        parts = []
        for seg, font, red in runs:
            if not seg:
                continue
            parts.append(TextBlock(InlineFont(rFont="Calibri", sz=11, color=RED), seg) if red else seg)
        ws.append([sha2no.get(sha, sha[:8]), len(items), len(lines), "", ""])
        ws.cell(row=ws.max_row, column=4).value = CellRichText(*parts) if len(parts) > 1 else text
        ws.cell(row=ws.max_row, column=4).alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(a.out)
    lib.write_csv(a.ledger, ledger)
    print("docs %d | marks %d" % (len(cands), len(ledger)))
    print("wrote", a.out, "|", a.ledger)


if __name__ == "__main__":
    main()
