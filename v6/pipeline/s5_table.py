# -*- coding: utf-8 -*-
"""s5_table.py - the delivery workbook.

One row per article. Both engines side by side: the span each one chose, the text
each one produced, what each one threw away, and every automated check that ran
on the pair.

    python s5_table.py            # writes 汇总表_697篇.xlsx + .csv
"""
import os, sys, io, json, csv, re, argparse
from collections import Counter

ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(v):
    """Excel refuses C0 control bytes; the PDF text layer carries a few."""
    return ILLEGAL.sub("", v) if isinstance(v, str) else v


def app(ws, row):
    ws.append([clean(x) for x in row])

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
sys.path.insert(0, r"D:\conclusion-wordcount\src")
from wcengine.count import count_words

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


def load_recs():
    p = os.path.join(STAGE, "R4_llm_all", "gate.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def load_repeat():
    p = os.path.join(STAGE, "R4_llm_all", "r1_vs_r2.jsonl")
    if not os.path.exists(p):
        return {}
    return {json.loads(l)["sha1"]: json.loads(l) for l in open(p, encoding="utf-8")}


def ledger_summary(rec):
    led = rec.get("ledger") or []
    c_drop = [x for x in led if x["code"].startswith("drop")]
    l_drop = [x for x in led if x["llm"].startswith("drop")]
    only_c = [x for x in led if x["code"].startswith("drop") and x["llm"] == "keep"]
    only_l = [x for x in led if x["llm"].startswith("drop") and x["code"] == "keep"]
    both = [x for x in led if x["code"].startswith("drop") and x["llm"].startswith("drop")]
    return {"c_drop": len(c_drop), "l_drop": len(l_drop), "both": len(both),
            "only_c": len(only_c), "only_l": len(only_l),
            "only_c_lines": ",".join(str(x["line"]) for x in only_c[:8]),
            "only_l_lines": ",".join(str(x["line"]) for x in only_l[:8])}


def deletion_text(rec):
    led = rec.get("ledger") or []
    parts = []
    leds = [x for x in led if x["code"].startswith("drop")]
    if leds:
        parts.append("[code] " + "; ".join("%d:%s" % (x["line"], x["code"][5:]) for x in leds[:14]))
    leds = [x for x in led if x["llm"].startswith("drop")]
    if leds:
        parts.append("[llm] " + "; ".join("%d:%s" % (x["line"], x["llm"][5:]) for x in leds[:14]))
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(STAGE, "R4_llm_all", "汇总表_697篇.xlsx"))
    a = ap.parse_args()
    recs = load_recs()
    rep = load_repeat()

    llm_txt, code_txt = {}, {}
    for r in recs:
        p = os.path.join(STAGE, "R4_llm_all", r["sha1"], "cplx_t0p0_run1.json")
        if os.path.exists(p):
            llm_txt[r["sha1"]] = json.load(open(p, encoding="utf-8")).get("text", "")
        cp = os.path.join(STAGE, "C_conclusions_clean", r["sha1"] + ".txt")
        if not os.path.exists(cp):
            cp = os.path.join(STAGE, "C_conclusions", r["sha1"] + ".txt")
        code_txt[r["sha1"]] = open(cp, encoding="utf-8").read() if os.path.exists(cp) else ""

    HEAD = ["序号", "sha8", "期刊", "年份", "页数", "冻结行数",
            "代码_标题行", "代码_起止行", "代码_词数", "代码_在窗",
            "LLM_起止行", "LLM_词数", "LLM_在窗",
            "起点差", "终点差", "跨度全同", "词数差", "文本相似度",
            "闸门", "失败性质", "未申报删除行数", "改写处数", "允许改动",
            "边界裁定", "越界原因", "越界标题行", "代码版多算行", "多算词数", "补回后词数", "补回后在窗",
            "LLM申报删除数", "LLM删除理由", "代码删除数", "代码删除理由",
            "需人工看", "原因",
            "两次跨度同", "两次文本同",
            "代码删/LLM删/同删", "仅代码删", "仅LLM删", "仅代码删行", "仅LLM删行",
            "删除对照",
            "LLM_结论段", "代码_结论段",
            "复核结论", "复核B1起点", "复核B2终点", "复核B3丢失", "复核B4混入", "复核B5改字",
            "复核说明", "入册", "重复件", "形状自检", "亲读判定", "亲读依据"]

    wb = Workbook()
    ws = wb.active
    ws.title = "01_主表"
    app(ws, HEAD)
    for r in recs:
        led = ledger_summary(r)
        rp = rep.get(r["sha1"], {})
        app(ws, [
            r["id"], r["sha8"], r["journal"], r["year"], r.get("pages", ""), r["n_lines"],
            r.get("code_heading", ""), "%s-%s" % (r.get("code_start"), r.get("code_end")),
            r.get("code_words", 0), r.get("code_in_window", ""),
            "%s-%s" % (r.get("llm_start"), r.get("llm_end")), r.get("llm_words", 0), r.get("llm_in_window", ""),
            r.get("start_delta", ""), r.get("end_delta", ""), r.get("span_match", ""),
            r.get("word_delta", ""), r.get("sim_llm_vs_code", ""),
            r.get("gate_status", ""), r.get("fail_class", ""),
            r.get("gate_nsilent", ""), r.get("gate_nbad", ""), r.get("gate_allowed", ""),
            r.get("boundary_class", ""), r.get("overshoot_kind", ""), r.get("overshoot_heading", ""),
            r.get("n_cut", ""), r.get("cut_words", ""),
            r.get("llm_words_restored", ""), r.get("in_window_if_restored", ""),
            r.get("llm_ndropped", ""), r.get("llm_reasons", ""), r.get("code_ndrop", ""), r.get("code_reasons", ""),
            r.get("need_review", ""), r.get("review_why", ""),
            rp.get("span_same", ""), rp.get("text_same", ""),
            "%d/%d/%d" % (led["c_drop"], led["l_drop"], led["both"]), led["only_c"], led["only_l"],
            led["only_c_lines"], led["only_l_lines"],
            deletion_text(r),
            llm_txt.get(r["sha1"], ""), code_txt.get(r["sha1"], ""),
            r.get("review_verdict", ""), r.get("review_B1", ""), r.get("review_B2", ""),
            r.get("review_B3", ""), r.get("review_B4", ""), r.get("review_B5", ""),
            r.get("review_note", ""), r.get("in_corpus", ""), r.get("dup_of", ""),
            ";".join(r.get("shape_flags") or []),
            r.get("read_verdict", ""), r.get("read_note", ""),
        ])

    # width + freeze
    widths = {"A": 7, "B": 11, "C": 30, "D": 7, "E": 6, "F": 8, "G": 9, "H": 12, "I": 8, "J": 7,
              "K": 12, "L": 8, "M": 7, "N": 7, "O": 7, "P": 8, "Q": 7, "R": 9,
              "S": 8, "T": 16, "U": 10, "V": 8, "W": 30, "X": 10, "Y": 26, "Z": 9,
              "AA": 8, "AB": 20, "AC": 9, "AD": 9, "AE": 9, "AF": 7, "AG": 7, "AH": 18, "AI": 18,
              "AJ": 14, "AK": 11, "AL": 26, "AM": 10, "AN": 10, "AO": 12, "AP": 10,
              "AO": 10, "AP": 26, "AQ": 9, "AR": 26,
              "AS": 8, "AT": 20, "AU": 9, "AV": 9, "AW": 9, "AX": 7, "AY": 7, "AZ": 18, "BA": 18,
              "BB": 60, "BC": 60,
              "BD": 10, "BE": 9, "BF": 9, "BG": 9, "BH": 9, "BI": 9, "BJ": 44, "BK": 6}
    for k, v in widths.items():
        ws.column_dimensions[k].width = v
    ws.freeze_panes = "C2"
    hdr_fill = PatternFill("solid", fgColor="DDEBF7")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = hdr_fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=False)
    c1 = HEAD.index("LLM_结论段") + 1
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=c1, max_col=c1 + 1):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    # ---- sheet 2: deletion ledger ----------------------------------------
    ws2 = wb.create_sheet("02_删除明细")
    app(ws2, ["序号", "sha8", "行号", "原文行", "代码判定", "LLM判定", "一致"])
    for r in recs:
        for x in (r.get("ledger") or []):
            same = "both" if (x["code"].startswith("drop") and x["llm"].startswith("drop")) else (
                "only_code" if x["code"].startswith("drop") else "only_llm")
            app(ws2, [r["id"], r["sha8"], x["line"], x["text"], x["code"], x["llm"], same])
    for k, v in {"A": 7, "B": 11, "C": 7, "D": 100, "E": 24, "F": 24, "G": 11}.items():
        ws2.column_dimensions[k].width = v
    ws2.freeze_panes = "A2"

    # ---- sheet 3: statistics ---------------------------------------------
    ws3 = wb.create_sheet("03_统计")
    n = len(recs)
    gate = Counter(r.get("gate_status") for r in recs)
    rows = [["项目", "数值", "说明"],
            ["文章总数", n, "下载池 697 个 PDF 全部重跑"],
            ["闸门 PASS", gate.get("PASS", 0), "%.1f%%" % (100.0 * gate.get("PASS", 0) / n)],
            ["闸门 FAIL", gate.get("FAIL", 0), "%.1f%%" % (100.0 * gate.get("FAIL", 0) / n)],
            ["\u5931\u8d25\u6027\u8d28 silent_body", sum(1 for r in recs if r.get("fail_class") == "silent_body"),
             "\u672a\u7533\u62a5\u5220\u6b63\u6587"],
            ["\u5931\u8d25\u6027\u8d28 insert_outside",
             sum(1 for r in recs if r.get("fail_class") == "insert_outside"), "\u6587\u672c\u8d85\u51fa\u7533\u62a5\u533a\u95f4"],
            ["\u5931\u8d25\u6027\u8d28 rewrite_or_insert",
             sum(1 for r in recs if r.get("fail_class") == "rewrite_or_insert"), "\u6539\u5b57\u6216\u63d2\u5165"],
            ["\u5931\u8d25\u6027\u8d28 silent_footnote",
             sum(1 for r in recs if r.get("fail_class") == "silent_footnote"), "\u672a\u7533\u62a5\u5220\u811a\u6ce8"],
            ["跨度与代码全同", sum(1 for r in recs if r.get("span_match")),
             "%.1f%%" % (100.0 * sum(1 for r in recs if r.get("span_match")) / n)],
            ["起点相同", sum(1 for r in recs if r.get("start_delta") == 0),
             "%.1f%%" % (100.0 * sum(1 for r in recs if r.get("start_delta") == 0) / n)],
            ["终点相同", sum(1 for r in recs if r.get("end_delta") == 0),
             "%.1f%%" % (100.0 * sum(1 for r in recs if r.get("end_delta") == 0) / n)],
            ["LLM 词数在 250-600", sum(r.get("llm_in_window", 0) for r in recs), ""],
            ["代码 词数在 250-600", sum(r.get("code_in_window", 0) for r in recs), ""],
            ["需人工看", sum(1 for r in recs if r.get("need_review")), ""],
            ["入册（自动+复核）", sum(1 for r in recs if r.get("in_corpus")), "闸门PASS + 250-600词 + 边界非截断 + 复审非fix"],
            ["入册总词数", sum(r.get("llm_words") or 0 for r in recs if r.get("in_corpus")), ""],
            ["\u91cd\u590d\u4ef6\uff08\u5df2\u5254\uff09", sum(1 for r in recs if r.get("dup_of")),
             "\u8eab\u4efd\u95f8\u95e8 dedupe_gate.py \u68c0\u51fa\u540c\u4e00\u7bc7\u4e24\u4e2a PDF"],
            ["复核已判", sum(1 for r in recs if r.get("review_verdict") in ("ok", "fix", "drop")), "142 篇"],
            ["复核判 ok", sum(1 for r in recs if r.get("review_verdict") == "ok"), ""],
            ["复核判 fix", sum(1 for r in recs if r.get("review_verdict") == "fix"), ""],
            ["亲读已读", sum(1 for r in recs if r.get("read_verdict")), "入册件全量通读"],
            ["亲读判 ok", sum(1 for r in recs if r.get("read_verdict") == "ok"), ""],
            ["亲读判 fix", sum(1 for r in recs if r.get("read_verdict") == "fix"), ""],
            ["两次跨度一致", sum(1 for v in rep.values() if v.get("span_same")), "T=0 重跑"],
            ["两次文本一致", sum(1 for v in rep.values() if v.get("text_same")), "归一化后"],
            ["两次字节一致", sum(1 for v in rep.values() if v.get("bytes_same")), "原始字符串"],
            ]
    for row in rows:
        ws3.append(row)
    ws3.column_dimensions["A"].width = 26
    ws3.column_dimensions["B"].width = 14
    ws3.column_dimensions["C"].width = 44
    for c in ws3[1]:
        c.font = Font(bold=True)

    ws3.append([])
    ws3.append(["LLM 词数分布", "篇数", ""])
    buckets = [(0, 0), (1, 249), (250, 349), (350, 449), (450, 549), (550, 600), (601, 800), (801, 99999)]
    for lo, hi in buckets:
        c = sum(1 for r in recs if lo <= (r.get("llm_words") or 0) <= hi)
        ws3.append(["%d-%d" % (lo, hi) if hi < 99999 else ">800", c, ""])
    ws3.append([])
    ws3.append(["代码 词数分布", "篇数", ""])
    for lo, hi in buckets:
        c = sum(1 for r in recs if lo <= (r.get("code_words") or 0) <= hi)
        ws3.append(["%d-%d" % (lo, hi) if hi < 99999 else ">800", c, ""])
    ws3.append([])
    ws3.append(["期刊", "篇数", "LLM 在窗"])
    for j, c in Counter(r["journal"] for r in recs).most_common():
        ws3.append([j, c, sum(1 for r in recs if r["journal"] == j and r.get("llm_in_window"))])

    # ---- sheet 4: candidate pool ------------------------------------------
    ws5 = wb.create_sheet("04_候选池")
    pick = [r for r in recs if r.get("in_corpus")]
    app(ws5, ["序号", "sha8", "期刊", "年份", "起止行", "词数", "闸门", "边界裁定",
              "复核结论", "两次跨度同", "代码词数", "相似度"])
    for r in pick:
        app(ws5, [r["id"], r["sha8"], r["journal"], r["year"],
                  "%s-%s" % (r["llm_start"], r["llm_end"]), r["llm_words"],
                  r["gate_status"], r["boundary_class"], r.get("review_verdict", ""),
                  (rep.get(r["sha1"], {}) or {}).get("span_same", ""),
                  r.get("code_words"), r.get("sim_llm_vs_code")])
    for k, v in {"A": 7, "B": 11, "C": 30, "D": 7, "E": 12, "F": 7, "G": 8,
                 "H": 14, "I": 10, "J": 10, "K": 9, "L": 9}.items():
        ws5.column_dimensions[k].width = v
    ws5.freeze_panes = "A2"

    # ---- sheet 5: everything that did not come out clean ------------------
    ws6 = wb.create_sheet("05_分歧与问题")
    bad = [r for r in recs if (r["gate_status"] != "PASS" or r["boundary_class"] != "agree"
                               or r.get("review_verdict") == "fix" or r.get("review_verdict") == "drop")]
    app(ws6, ["序号", "sha8", "期刊", "代码起止", "LLM起止", "LLM词数", "闸门", "边界裁定",
              "复核结论", "复核说明", "未申报删除行", "改写处", "被切掉的行", "多算词数",
              "代码删除理由", "LLM删除理由"])
    for r in bad:
        app(ws6, [r["id"], r["sha8"], r["journal"],
                  "%s-%s" % (r["code_start"], r["code_end"]),
                  "%s-%s" % (r["llm_start"], r["llm_end"]), r["llm_words"],
                  r["gate_status"], r["boundary_class"], r.get("review_verdict", ""),
                  r.get("review_note", ""), r.get("gate_silent_lines", ""), r.get("gate_nbad", ""),
                  r.get("n_cut", ""), r.get("cut_words", ""),
                  r["code_reasons"], r["llm_reasons"]])
    for k, v in {"A": 7, "B": 11, "C": 28, "D": 13, "E": 13, "F": 8, "G": 8, "H": 14,
                 "I": 9, "J": 52, "K": 18, "L": 7, "M": 9, "N": 8, "O": 26, "P": 26}.items():
        ws6.column_dimensions[k].width = v
    ws6.freeze_panes = "A2"
    print("candidates=%d  flagged=%d" % (len(pick), len(bad)))

    # ---- sheet 6: the Limitations question ---------------------------------
    ws7 = wb.create_sheet("06_口径_Limitations")
    lim = [r for r in recs
           if r.get("boundary_class") == "code_overshot"
           and r.get("overshoot_kind") in ("limitations", "numbered")
           and re.search(r"limitation|implication|coda|summary", (r.get("overshoot_heading") or ""), re.I)]
    app(ws7, ["序号", "sha8", "期刊", "越界标题行", "模型词数", "该节词数", "合并后词数",
              "合并后在窗", "不合并入册", "合并后入册", "复核说明"])
    for r in lim:
        merged = r.get("llm_words_restored", 0)
        ok_merge = 1 if 250 <= merged <= 600 else 0
        app(ws7, [r["id"], r["sha8"], r["journal"], r.get("overshoot_heading", ""),
                  r.get("llm_words"), r.get("cut_words"), merged,
                  1 if 250 <= merged <= 600 else 0, r.get("in_corpus", 0),
                  1 if (r.get("in_corpus") or ok_merge) else ok_merge,
                  r.get("review_note", "")])
    app(ws7, [])
    app(ws7, ["口径 A（不算结论，维持现状）", "%d 篇入册" % sum(r.get("in_corpus", 0) for r in recs), ""])
    app(ws7, ["口径 B（算结论，并入正文）", "本表 %d 篇中只有 %d 篇合并后仍在 250-600" % (
        len(lim), sum(1 for r in lim if 250 <= r.get("llm_words_restored", 0) <= 600)), ""])
    for k, v in {"A": 7, "B": 11, "C": 28, "D": 46, "E": 9, "F": 9, "G": 11,
                 "H": 10, "I": 10, "J": 10, "K": 60}.items():
        ws7.column_dimensions[k].width = v
    ws7.freeze_panes = "A2"
    print("limitations cluster=%d" % len(lim))

    # ---- sheet 7: notes ---------------------------------------------------
    ws4 = wb.create_sheet("00_说明")
    notes = [
        ["列", "含义"],
        ["代码_起止行", "规则引擎 B_spans 认定的结论段：heading_line+1 到 end_line，逐行按封闭理由码删留"],
        ["LLM_起止行", "模型返回的 start_line / end_line，行号指向 A_lines 冻结行流"],
        ["起点差 / 终点差", "LLM 减代码；0 表示两个引擎选了同一行"],
        ["文本相似度", "difflib 比率，两边文本按闸门归一化（去空白、去连字符、去校对标记）后比较"],
        ["闸门", "verify_output.py 的判定：区间内每一行正文必须原样出现或申报删除；残留差异必须是可列的修复类"],
        ["允许改动", "删脚注号 / 删孤立字母 / 字形修复 / 引号归一 / 补破折号 / 破折号展开 / 删装饰行的计数"],
        ["删除对照", "[code] 代码删掉的行号:理由；[llm] 模型删掉的行号:理由"],
        ["两次跨度同 / 两次文本同", "同一篇在 temperature=0 下跑两次的结果是否一致"],
        ["", ""],
        ["语料指纹", "697 篇；A_lines 冻结行流；清单 sha256 见 _logs/index_s*.csv"],
        ["词数口径", "wcengine.count.count_words，唯一合法计数方式"],
        ["生成", "s5_table.py；数据源 R4_llm_all/gate.jsonl + cplx_t0p0_run1.json + C_conclusions(_clean)"],
    ]
    for row in notes:
        ws4.append(row)
    ws4.column_dimensions["A"].width = 24
    ws4.column_dimensions["B"].width = 110
    for c in ws4[1]:
        c.font = Font(bold=True)

    wb.save(a.out)
    print("wrote " + a.out)

    # csv mirror of the main sheet
    csvp = os.path.splitext(a.out)[0] + ".csv"
    with open(csvp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEAD)
        for row in ws.iter_rows(min_row=2, values_only=True):
            w.writerow(row)
    print("wrote " + csvp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
