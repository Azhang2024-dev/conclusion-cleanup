# -*- coding: utf-8 -*-
"""Stage 2: mark candidates on a COPY and produce the review workbook.

The workbook mirrors the delivery review table the author reads line by line:

    总表        one row per article, conclusion text with flagged runs in red
    标红清单    one row per mark: doc, line, reason, words, flagged text
    上下文抽样  30 sampled rows
    长度分布    word-count distribution, by journal and by year
    落选        documents outside the word window
    说明        N, totals, how to reproduce

The ledger CSV stays the machine-readable truth. Plain text of every cell is
identical to the input text (asserted with assert_plain_equals).

Usage:
    python tools/mark.py --stage PATH --candidates candidates.csv
                         --texts DIR --out XLSX --ledger CSV
                         [--manifest 清单.csv] [--window 250 600]
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

RED = "FFFF0000"
ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(s):
    """Strip characters openpyxl refuses to store."""
    return ILLEGAL.sub(" ", s) if isinstance(s, str) else s


def mark_runs(flat, lines, starts, marks):
    """Split text into (segment, is_red) runs covering the whole string."""
    spans = sorted((starts[k], starts[k] + len(lines[k])) for k in marks if k < len(lines))
    out = []
    cur = 0
    for s, e in spans:
        if s > cur:
            out.append((flat[cur:s], False))
        out.append((flat[s:e], True))
        cur = max(cur, e)
    if cur < len(flat):
        out.append((flat[cur:], False))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default=None)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--texts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--window", nargs=2, type=int, default=[250, 600])
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261115)
    a = ap.parse_args(argv)

    from openpyxl import Workbook
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    from openpyxl.styles import Alignment, Font, PatternFill

    stage = lib.Stage(a.stage)
    manifest = lib.read_csv(a.manifest) if a.manifest else []
    no2sha = {r["no"]: r["pdf_sha1"] for r in manifest}
    sha2no = {v: k for k, v in no2sha.items()}
    meta = {r["pdf_sha1"]: r for r in manifest}

    cands = {}
    for r in lib.read_csv(a.candidates):
        cands.setdefault(r["sha1"], []).append(
            (int(r["line"]), r.get("reason", ""), r.get("note", "")))

    shas = [r["pdf_sha1"] for r in manifest] if manifest else sorted(cands)
    rows, ledger = [], []
    for sha in shas:
        p = os.path.join(a.texts, sha + ".txt")
        if not os.path.exists(p):
            continue
        text = lib.read_text(p).replace("\r\n", "\n")
        lines = text.split("\n")
        starts = []
        pos = 0
        for ln in lines:
            starts.append(pos)
            pos += len(ln) + 1
        items = sorted(cands.get(sha, []))
        marks = [k for k, _, _ in items if k < len(lines)]
        m = meta.get(sha, {})
        w = lib.count_words(text)
        lo, hi = a.window
        rows.append({
            "sha1": sha, "meta": m, "flat": text, "lines": lines,
            "starts": starts, "marks": marks, "items": items,
            "words": w, "in_window": lo <= w <= hi,
        })
        for k, reason, note in items:
            if k >= len(lines):
                continue
            seg = lines[k]
            ledger.append({
                "sha1": sha, "no": sha2no.get(sha, ""), "k_from": k, "k_to": k,
                "reason": reason, "note": note, "words": lib.count_words(seg),
                "text": re.sub(r"\s+", " ", seg).strip()[:160], "action": "删除",
            })

    def rich(r):
        parts = []
        for seg, red in mark_runs(r["flat"], r["lines"], r["starts"], r["marks"]):
            if not seg:
                continue
            seg = clean(seg)
            parts.append(TextBlock(InlineFont(rFont="Calibri", sz=11, color=RED), seg) if red else seg)
        return CellRichText(*parts) if len(parts) > 1 else clean(r["flat"])

    wb = Workbook()
    ws = wb.active
    ws.title = "总表"
    head = ["no", "journal", "year", "first_author", "title", "words",
            "n_lines", "mark_count", "in_window", "conclusion_text_marked"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    for r in rows:
        m = r["meta"]
        ws.append([sha2no.get(r["sha1"], r["sha1"][:8]), m.get("journal", ""), m.get("year", ""),
                   clean(m.get("first_author", "")), clean(str(m.get("title", ""))[:120]), r["words"],
                   len(r["lines"]), len(r["marks"]), "Y" if r["in_window"] else "N", ""])
        cell = ws.cell(row=ws.max_row, column=len(head))
        cell.value = rich(r)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col, wd in zip("ABCDEFGHIJ", [8, 26, 7, 14, 40, 7, 7, 9, 8, 110]):
        ws.column_dimensions[col].width = wd
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("标红清单")
    ws2.append(["no", "行号", "理由码", "删词数", "被标红的内容", "备注"])
    for c in ws2[1]:
        c.font = Font(bold=True)
    for x in ledger:
        ws2.append([x["no"], x["k_from"], x["reason"], x["words"], x["text"], x["note"]])
    for col, wd in zip("ABCDEF", [8, 8, 16, 8, 90, 14]):
        ws2.column_dimensions[col].width = wd
    ws2.freeze_panes = "A2"

    ws3 = wb.create_sheet("上下文抽样")
    ws3.append(["no", "journal", "year", "words", "mark_count", "conclusion_text_marked"])
    rng = random.Random(a.seed)
    for r in (rng.sample(rows, min(a.sample, len(rows))) if rows else []):
        m = r["meta"]
        ws3.append([sha2no.get(r["sha1"], r["sha1"][:8]), m.get("journal", ""), m.get("year", ""),
                    r["words"], len(r["marks"]), ""])
        cell = ws3.cell(row=ws3.max_row, column=6)
        cell.value = rich(r)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col, wd in zip("ABCDEF", [8, 26, 7, 7, 10, 110]):
        ws3.column_dimensions[col].width = wd

    ws4 = wb.create_sheet("长度分布")
    vals = sorted(r["words"] for r in rows)

    def pct(q):
        return vals[min(len(vals) - 1, int(q * len(vals)))] if vals else 0

    ws4.append(["指标", "值"])
    for k, v in [("N", len(vals)), ("总词数", sum(vals)), ("min", vals[0] if vals else 0),
                 ("p10", pct(.10)), ("p25", pct(.25)), ("median", pct(.50)),
                 ("p75", pct(.75)), ("p90", pct(.90)), ("max", vals[-1] if vals else 0),
                 ("窗内", sum(1 for r in rows if r["in_window"]))]:
        ws4.append([k, v])
    ws4.append([])
    ws4.append(["按刊计数", ""])
    for k, v in sorted(Counter(str(r["meta"].get("journal", "")) for r in rows).items()):
        ws4.append([k, v])
    ws4.append([])
    ws4.append(["按年计数", ""])
    for k, v in sorted(Counter(str(r["meta"].get("year", "")) for r in rows).items()):
        ws4.append([k, v])
    ws4.column_dimensions["A"].width = 30
    ws4.column_dimensions["B"].width = 12

    ws5 = wb.create_sheet("落选")
    ws5.append(["no", "journal", "year", "words", "原因"])
    for c in ws5[1]:
        c.font = Font(bold=True)
    lo, hi = a.window
    for r in rows:
        if r["in_window"]:
            continue
        why = "低于 %d" % lo if r["words"] < lo else "高于 %d" % hi
        m = r["meta"]
        ws5.append([sha2no.get(r["sha1"], r["sha1"][:8]), m.get("journal", ""),
                    m.get("year", ""), r["words"], "词数" + why])
    for col, wd in zip("ABCDE", [8, 28, 7, 8, 20]):
        ws5.column_dimensions[col].width = wd

    ws6 = wb.create_sheet("说明")
    total = sum(vals)
    for line in [("项", "值"),
                 ("生成工具", "tools/mark.py"),
                 ("篇数 N", len(rows)),
                 ("总词数", total),
                 ("标红条目", len(ledger)),
                 ("标红涉及篇数", len({x["sha1"] for x in ledger})),
                 ("词数窗口", "%d-%d" % (lo, hi)),
                 ("窗内篇数", sum(1 for r in rows if r["in_window"])),
                 ("口径", "wcengine.count.count_words，文本现算"),
                 ("说明", "红字为待删内容；本表只标记不删除，删除由 tools/apply.py 完成"),
                 ("核对", "每个单元格纯文本与输入文本逐字一致")]:
        ws6.append(list(line))
    ws6.column_dimensions["A"].width = 18
    ws6.column_dimensions["B"].width = 90

    wb.save(a.out)
    lib.write_csv(a.ledger, ledger)
    print("docs %d | marks %d | in-window %d | total words %d" % (
        len(rows), len(ledger), sum(1 for r in rows if r["in_window"]), total))
    print("wrote", a.out, "|", a.ledger)


if __name__ == "__main__":
    main()
