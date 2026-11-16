# -*- coding: utf-8 -*-
"""s53_oa_into_book.py - merge the OA harvest into the 2026-11-02 checklist workbook.

Marking rules (the point of the exercise):
  J 来源      "2026-11-16 OA补录" for every added row, so old and new never mix;
  K PDF落点   the host the link pointed at;
  L 尝试结果  ok / 重复件 / 需 access·出版社 / 链接失效 / 非PDF / 下载失败

The original workbook is never overwritten: output is a new file.
"""
import os, sys, io, csv, argparse, collections
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")

SRC = r"D:\毕业论文-短语框架人机对比\06_分析与结果\_语料体检\可下载文章清单_核对版_2026-11-02.xlsx"
TAG = "2026-11-16 OA补录"

TYPE_MAP = {"article": "研究论文", "review": "综述", "editorial": "编者按（慎选）",
            "erratum": "勘误（剔除）", "paratext": "其他", "letter": "通讯（慎选）",
            "book-chapter": "其他"}
STATUS_MAP = {"ok": "已下载·OA", "dup_sha1": "重复件·池中已有", "pool_same_title": "重复件·池中已有(同题)",
              "host_blocked": "需 access·出版社403", "untried_publisher": "需 access·出版社（未尝试）",
              "untried": "未尝试",
              "not_pdf": "链接非PDF", "error": "下载失败"}
HDR = ["序", "年份", "标题", "类型", "DOI", "通讯作者", "状态", "下载PDF", "打开DOI", "来源", "PDF落点", "尝试结果"]


def status_of(row):
    s = row["status"]
    if s in STATUS_MAP:
        return STATUS_MAP[s]
    if s.startswith("http_"):
        return "链接失效" if s == "http_404" else "需 access·" + s[5:]
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--cands", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    PUB = ("sciencedirect", "wiley", "oup.com", "cambridge", "degruyter", "jbe-platform",
           "tandfonline", "springer", "brill", "sagepub", "benjamins", "academic.oup")
    led = list(csv.DictReader(open(a.ledger, encoding="utf-8-sig")))
    by_doi = {(r["doi"] or "").lower(): r for r in led}
    print("ledger rows:", len(led), collections.Counter(r["status"] for r in led))
    # rows we never got to: keep them, marked, so the sheet is the full inventory
    rows = []
    for c in csv.DictReader(open(a.cands, encoding="utf-8-sig")):
        doi = (c["doi"] or "").lower()
        if doi in by_doi:
            rows.append(by_doi[doi])
        else:
            st = "untried_publisher" if any(k in c["host"] for k in PUB) else "untried"
            rows.append(dict(c, status=st, detail="", file="", sha1="", bytes=""))
    print("inventory rows:", len(rows), collections.Counter(r["status"] for r in rows))

    wb = openpyxl.load_workbook(SRC)
    sheets = {ws.title.replace("✓ ", "").strip(): ws for ws in wb.worksheets if ws.title.startswith("✓")}

    existing = set()
    for ws in wb.worksheets:
        hdr = [str(c.value).strip() if c.value else "" for c in ws[1]]
        if "DOI" not in hdr:
            continue
        col = hdr.index("DOI") + 1
        for r in range(2, ws.max_row + 1):
            v = ws.cell(row=r, column=col).value
            if v:
                existing.add(str(v).strip().lower())
    print("existing DOIs:", len(existing))

    added = collections.defaultdict(list)
    skipped = 0
    for r in rows:
        doi = (r["doi"] or "").strip().lower()
        if not doi or doi in existing:
            skipped += 1
            continue
        added[r["journal"]].append(r)

    total_add = 0
    for jname, ws in sheets.items():
        items = added.get(jname, [])
        if not items:
            print("  %-24s no new rows" % jname)
            continue
        for c in range(1, len(HDR) + 1):
            cell = ws.cell(row=1, column=c, value=HDR[c - 1])
            cell.font = Font(bold=True)
        n = ws.max_row
        for i, r in enumerate(sorted(items, key=lambda x: (x["year"], x["doi"])), 1):
            row = n + i
            typ = TYPE_MAP.get(r["type"], "其他")
            if r["title"].lower().startswith(("review of", "book review")):
                typ = "书评（慎选）"
            seq = ws.cell(row=n, column=1).value
            try:
                seq = int(seq) + i
            except (TypeError, ValueError):
                seq = i
            ws.cell(row=row, column=1, value=seq)
            ws.cell(row=row, column=2, value=r["year"])
            ws.cell(row=row, column=3, value=r["title"])
            ws.cell(row=row, column=4, value=typ)
            ws.cell(row=row, column=5, value=r["doi"])
            ws.cell(row=row, column=6, value=r["author"])
            ws.cell(row=row, column=7, value=status_of(r))
            if r["status"] == "ok" and r.get("file"):
                c = ws.cell(row=row, column=8, value="▶ PDF")
                c.hyperlink = r["file"]
                c.font = Font(color="0563C1", underline="single")
            c = ws.cell(row=row, column=9, value="▶ DOI")
            c.hyperlink = "https://doi.org/" + r["doi"]
            c.font = Font(color="0563C1", underline="single")
            ws.cell(row=row, column=10, value=TAG)
            ws.cell(row=row, column=11, value=r["host"])
            ws.cell(row=row, column=12, value=r["status"])
            if r["status"] == "ok":
                for c in range(1, 13):
                    ws.cell(row=row, column=c).fill = PatternFill("solid", fgColor="E8F5E9")
        total_add += len(items)
        print("  %-24s +%d rows" % (jname, len(items)))

    # 新增总表
    ws = wb.create_sheet("新增_OA_2026-11-16")
    head = ["期刊", "年份", "标题", "类型", "DOI", "通讯作者", "状态", "PDF落点", "尝试结果", "文件", "sha1", "bytes", "版本"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for jname in sorted(added):
        for r in sorted(added[jname], key=lambda x: (x["year"], x["doi"])):
            ws.append([jname, r["year"], r["title"], TYPE_MAP.get(r["type"], "其他"), r["doi"],
                       r["author"], status_of(r), r["host"], r["status"], r.get("file", ""),
                       r.get("sha1", ""), r.get("bytes", ""), r["version"]])
    for col, w in {"A": 22, "B": 7, "C": 70, "D": 14, "E": 34, "F": 22, "G": 18, "H": 28,
                   "I": 16, "J": 60, "K": 42, "L": 10, "M": 12}.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    # 总览追加
    ov = wb["总览"]
    base = ov.max_row + 2
    ov.cell(row=base, column=1, value="%s（新增一律标 J 列来源）" % TAG).font = Font(bold=True)
    ov.cell(row=base + 1, column=1, value="期刊")
    ov.cell(row=base + 1, column=2, value="新增候选")
    ov.cell(row=base + 1, column=3, value="已下载")
    ov.cell(row=base + 1, column=4, value="池中已有")
    ov.cell(row=base + 1, column=5, value="出版社403")
    ov.cell(row=base + 1, column=6, value="其他失败")
    for c in range(1, 7):
        ov.cell(row=base + 1, column=c).font = Font(bold=True)
    r0 = base + 2
    for i, jname in enumerate(sorted(added)):
        items = added[jname]
        st = collections.Counter(x["status"] for x in items)
        ov.cell(row=r0 + i, column=1, value=jname)
        ov.cell(row=r0 + i, column=2, value=len(items))
        ov.cell(row=r0 + i, column=3, value=st["ok"])
        ov.cell(row=r0 + i, column=4, value=st["dup_sha1"])
        ov.cell(row=r0 + i, column=5, value=st["host_blocked"])
        ov.cell(row=r0 + i, column=6, value=len(items) - st["ok"] - st["dup_sha1"] - st["host_blocked"])
    tail = r0 + len(added)
    ov.cell(row=tail, column=1, value="合计")
    for c in range(2, 7):
        ov.cell(row=tail, column=c, value=sum(ov.cell(row=r0 + i, column=c).value or 0 for i in range(len(added))))
    ov.cell(row=tail + 2, column=1, value="说明：新增行状态为 2026-11-16 的实测结果；旧行未改动。")

    wb.save(a.out)
    print("added rows:", total_add, "| skipped (already listed):", skipped, "| wrote", a.out)


if __name__ == "__main__":
    sys.exit(main())
