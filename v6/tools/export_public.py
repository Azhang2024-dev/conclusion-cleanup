# -*- coding: utf-8 -*-
"""export_public.py - turn the internal per-document record into a public table.

The internal record (R4_llm_all/gate.jsonl) carries source text: the per-line
ledger, the cut samples, the reviewer notes. None of that belongs in a public
repository that ships a method, not a corpus. This script drops exactly those
fields and keeps the decision, so every published number stays recomputable
from the record while no article text leaves the machine.

    python export_public.py --gate PATH/gate.jsonl --out-dir v6/results
"""
import os, sys, io, json, csv, argparse
from collections import Counter

DROP = {"ledger", "cut_sample", "overshoot_head_text", "gate_silent_lines",
        "gate_viol", "review_note", "read_note", "review_why", "rel_path",
        "code_text_chars", "llm_text_chars"}

KEEP = ["id", "sha1", "sha8", "journal", "year", "pages", "n_lines",
        "code_heading", "code_start", "code_end", "code_words",
        "code_nkept", "code_ndrop", "code_reasons", "code_end_reason",
        "llm_start", "llm_end", "llm_words", "llm_confidence", "llm_ndropped",
        "llm_reasons", "gate_status", "gate_survived", "gate_nsilent",
        "gate_nbad", "gate_allowed", "silent_kinds", "fail_class",
        "start_delta", "end_delta", "word_delta", "sim_llm_vs_code",
        "latency_s", "in_tokens", "out_tokens", "span_match", "need_review",
        "boundary_class", "n_cut", "cut_words", "overshoot_kind",
        "overshoot_heading", "overshoot_words", "llm_words_restored",
        "llm_in_window", "code_in_window", "in_window_if_restored",
        "review_verdict", "review_B1", "review_B2", "review_B3", "review_B4",
        "review_B5", "read_verdict", "in_corpus", "dup_of", "shape_flags",
        "cite_n"]


def cell(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return v


# A swallowed heading is diagnosed by its opening words; two of them are whole
# sentences in the source paper. Cut at 40 characters so the table stays a
# decision record and not an excerpt.
CUT = {"overshoot_heading"}


def trunc(k, v):
    if k in CUT and isinstance(v, str) and len(v) > 40:
        return v[:40] + "..."
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    recs = [json.loads(l) for l in open(a.gate, encoding="utf-8") if l.strip()]
    os.makedirs(a.out_dir, exist_ok=True)

    cols = list(KEEP)
    cols += [k for k in recs[0] if k not in KEEP and k not in DROP]
    with open(os.path.join(a.out_dir, "逐篇判定.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow({k: trunc(k, cell(r.get(k, ""))) for k in cols})

    def count(key, pred=lambda r: True):
        return Counter(r.get(key, "") for r in recs if pred(r))

    rows = []
    rows.append(["文档数", len(recs), ""])
    rows.append(["输入 token 合计", sum(int(r["in_tokens"] or 0) for r in recs), "pass 1"])
    rows.append(["输出 token 合计", sum(int(r["out_tokens"] or 0) for r in recs), "pass 1"])
    for k, v in count("gate_status").most_common():
        rows.append(["闸门状态", k, v])
    for k, v in count("fail_class").most_common():
        rows.append(["失败类别", k, v])
    for k, v in count("boundary_class").most_common():
        rows.append(["边界分类", k, v])
    for k, v in count("overshoot_kind").most_common():
        if k:
            rows.append(["越界类型", k, v])
    for k, v in count("review_verdict").most_common():
        rows.append(["人工/agent 复核", k, v])
    for k, v in count("read_verdict").most_common():
        rows.append(["逐篇亲读", k or "(未读)", v])
    rows.append(["入册", sum(1 for r in recs if r.get("in_corpus")), "闸门+窗+去重+亲读"])
    rows.append(["入册总词数", sum(int(r["llm_words"] or 0) for r in recs if r.get("in_corpus")), ""])
    with open(os.path.join(a.out_dir, "统计汇总.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["指标", "值", "备注"])
        w.writerows(rows)

    allowed = Counter()
    for r in recs:
        try:
            for k, v in json.loads(r.get("gate_allowed") or "{}").items():
                allowed[k] += v
        except ValueError:
            pass
    with open(os.path.join(a.out_dir, "允许修复分类.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["类别", "处数"])
        for k, v in allowed.most_common():
            w.writerow([k, v])
    print("records", len(recs), "| in_corpus", sum(1 for r in recs if r.get("in_corpus")))
    print("allowed", dict(allowed))


if __name__ == "__main__":
    sys.exit(main())
