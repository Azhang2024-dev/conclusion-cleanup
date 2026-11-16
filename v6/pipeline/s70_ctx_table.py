# -*- coding: utf-8 -*-
"""s70_ctx_table.py - the D-3 delivery workbook: conclusion + one paragraph either side.

D-3 (2026-11-14): the workbook carries ctx_before / conclusion_text / ctx_after;
the full body text stays out of it (Excel cell cap 32,767 chars).

Paragraph boundaries on the frozen line stream:
  * a page change ends a paragraph;
  * a vertical gap larger than 1.45x the document's median line gap ends one;
  * a short line (< 55% of the median line width) that ends a sentence also ends one.
Nothing is rewritten: the context paragraphs are the frozen lines, joined.
"""
import os, sys, io, csv, json, statistics, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
sys.path.insert(0, r"D:\conclusion-wordcount\src")
from wcengine.count import count_words
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

ILLEGAL = __import__("re").compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def load_lines(sha):
    p = os.path.join(STAGE, "A_lines", sha + ".jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def geometry(lines):
    gaps, widths = [], []
    for a, b in zip(lines, lines[1:]):
        if a["page"] == b["page"]:
            gaps.append(max(0.0, b["y0"] - a["y1"]))
    for l in lines:
        widths.append(l["x1"] - l["x0"])
    mg = statistics.median(gaps) if gaps else 0.0
    mw = statistics.median(widths) if widths else 0.0
    return mg, mw


def is_break(prev, cur, mg, mw):
    if prev is None:
        return True
    if prev["page"] != cur["page"]:
        return True
    if mg > 0 and (cur["y0"] - prev["y1"]) > 1.45 * mg:
        return True
    prev_w = prev["x1"] - prev["x0"]
    if mw and prev_w < 0.55 * mw and prev["text"].rstrip().endswith((".", "?", "!", ":")):
        return True
    return False


HEADING = __import__("re").compile(r"^(\d+(\.\d+)*\.?\s+)?[A-Z][^.!?]{0,60}$")
BLOCK = __import__("re").compile(r"^(references?|bibliography|appendix|appendices|acknowledge?ments?|"
                                 r"notes?|funding|declaration|data availability|about the authors?)", __import__("re").I)
# publisher watermarks sit inside the text block and would otherwise be quoted
# as if they were prose
MARK = __import__("re").compile(r"(published online by|cambridge university press|downloaded from|"
                                r"brought to you by|all rights reserved|terms and conditions|"
                                r"journals? permission|academic\.oup\.com|https?://\S+$)", __import__("re").I)


def _headingish(t):
    t = (t or "").strip()
    if not t or len(t) > 70:
        return False
    return bool(HEADING.match(t)) and not t.endswith((".", "?", "!"))


def para_before(lines, start, mg, mw, cap=18, skip=3):
    """Nearest prose paragraph before the span; headings are stepped over."""
    i = start - 1
    for _ in range(skip + 1):
        out = []
        while i >= 0 and len(out) < cap:
            if not MARK.search(lines[i]["text"]):
                out.append(lines[i]["text"])
            if is_break(lines[i - 1] if i > 0 else None, lines[i], mg, mw):
                break
            i -= 1
        seg = " ".join(reversed(out)).strip()
        if seg and not _headingish(seg):
            return seg
        if seg and BLOCK.match(seg):
            return "[前接 %s]" % seg[:40]
        i -= 1
    return ""


def para_after(lines, end, mg, mw, cap=18, skip=3):
    """Nearest prose paragraph after the span; a References block is named, not quoted."""
    i = end + 1
    for _ in range(skip + 1):
        out = []
        while i < len(lines) and len(out) < cap:
            if not MARK.search(lines[i]["text"]):
                out.append(lines[i]["text"])
            if is_break(lines[i], lines[i + 1] if i + 1 < len(lines) else None, mg, mw):
                break
            i += 1
        seg = " ".join(out).strip()
        if seg and BLOCK.match(seg):
            return "[后接 %s]" % seg.split(".")[0][:40].strip()
        if seg and not _headingish(seg):
            return seg
        i += 1
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(STAGE, "交付_人类语料527篇_2026-11-17.xlsx"))
    a = ap.parse_args()
    corpus = os.path.join(STAGE, "定稿_人类语料_合并_2026-11-16")
    rows = list(csv.DictReader(open(os.path.join(corpus, "00_清单_合并.csv"), encoding="utf-8-sig")))
    txtdir = os.path.join(corpus, "结论段_txt")

    wb = Workbook()
    ws = wb.active
    ws.title = "01_总表"
    head = ["序", "id", "来源", "期刊", "年份", "词数", "sha1",
            "起止行", "ctx_before", "conclusion_text", "ctx_after", "txt"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)

    empties = []
    for n, r in enumerate(rows, 1):
        sha = r["sha1"]
        lines = load_lines(sha)
        mg, mw = geometry(lines)
        s, e = int(r["start_line"]), int(r["end_line"])
        before = para_before(lines, s, mg, mw)
        after = para_after(lines, e, mg, mw)
        concl = open(os.path.join(txtdir, sha + ".txt"), encoding="utf-8").read().replace("\r\n", " ").strip()
        if not before:
            empties.append((r["id"], "no_before"))
        if not after:
            empties.append((r["id"], "no_after"))
        ws.append([n, r["id"], r["source"], r["journal"], r["year"], int(r["words"]), sha,
                   "%s-%s" % (s, e), ILLEGAL.sub("", before), ILLEGAL.sub("", concl), ILLEGAL.sub("", after),
                   r["txt"]])
    for col, w in {"A": 5, "B": 7, "C": 20, "D": 24, "E": 8, "F": 7, "G": 42,
                   "H": 11, "I": 60, "J": 90, "K": 60, "L": 34}.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "D2"
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    ws2 = wb.create_sheet("02_统计")
    ws2.append(["指标", "值"])
    ws2.append(["篇数", len(rows)])
    ws2.append(["总词数", sum(int(r["words"]) for r in rows)])
    ws2.append(["min / 中位 / max", "%s / %s / %s" % (
        min(int(r["words"]) for r in rows),
        sorted(int(r["words"]) for r in rows)[len(rows) // 2],
        max(int(r["words"]) for r in rows))])
    ws2.append(["来源", "主体 483 + OA 新增 44"])
    ws2.append(["上下文规则", "页内行距 > 1.45×中位行距、或短行结束、或跨页 = 段落边界"])
    ws2.append(["空上下文", "%d 处（篇首/篇末无段落可补）" % len(empties)])
    for c in ws2[1]:
        c.font = Font(bold=True)
    ws2.column_dimensions["A"].width = 22
    ws2.column_dimensions["B"].width = 60

    wb.save(a.out)
    print("rows", len(rows), "| words", sum(int(r["words"]) for r in rows), "| wrote", a.out)
    print("empty context:", len(empties), empties[:10])


if __name__ == "__main__":
    sys.exit(main())
