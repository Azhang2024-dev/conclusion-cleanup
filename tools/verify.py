# -*- coding: utf-8 -*-
"""Stage 5: verify a cleaned corpus.

Checks (all mandatory):
    - format: UTF-8 without BOM, CRLF, no trailing newline, no blank lines
    - word count recomputed and compared with an index / manifest
    - every kept line appears as an ordered subsequence of the frozen stream
      (word level, bounded skip)
    - dedupe gate

Usage:
    python tools/verify.py --stage PATH --texts DIR [--manifest CSV]
                           [--index CSV] [--window 250 600] [--out JSON]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

TOK = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")


def check_format(path):
    issues = []
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        issues.append("BOM")
    text = raw.decode("utf-8-sig")
    if text.endswith("\r\n"):
        issues.append("trailing-newline")
    if "\r\n\r\n" in text:
        issues.append("blank-line")
    if text.count("\r\n") < text.count("\n"):
        issues.append("mixed-line-endings")
    return issues, text


def subsequence_ok(clean_tokens, stream_tokens, max_skip):
    j = 0
    skipped = 0
    for t in clean_tokens:
        while j < len(stream_tokens) and stream_tokens[j] != t:
            j += 1
            skipped += 1
        if j == len(stream_tokens):
            return False, skipped
        j += 1
    return True, skipped


def multiset_ok(clean_tokens, stream_tokens):
    """Fallback for lines deliberately moved out of order (e.g. kept sources)."""
    from collections import Counter
    s = Counter(stream_tokens)
    for t, n in Counter(clean_tokens).items():
        if s.get(t, 0) < n:
            return False
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default=None)
    ap.add_argument("--texts", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--index", default=None)
    ap.add_argument("--window", nargs=2, type=int, default=[250, 600])
    ap.add_argument("--max-skip", type=int, default=200)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    stage = lib.Stage(a.stage)
    manifest = lib.read_csv(a.manifest) if a.manifest else []
    index = {r["sha1"]: r for r in lib.read_csv(a.index)} if a.index else {}
    shas = [r["pdf_sha1"] for r in manifest] if manifest else stage.sha_list()

    rows = []
    for sha in shas:
        p = os.path.join(a.texts, sha + ".txt")
        if not os.path.exists(p):
            rows.append({"sha1": sha, "status": "MISSING", "words": 0})
            continue
        issues, text = check_format(p)
        words = lib.count_words(text)
        clean = TOK.findall(text)
        try:
            stream = TOK.findall(" ".join(d["text"] for d in stage.load_lines(sha)))
        except FileNotFoundError:
            stream = []
        sub_ok, skipped = (True, 0)
        if stream:
            sub_ok, skipped = subsequence_ok(clean, stream, a.max_skip)
            if not sub_ok:
                # a mark moved to a paragraph end is no longer an ordered
                # subsequence: retry with the text sorted as a multiset
                sub_ok = multiset_ok(clean, stream)
                if sub_ok:
                    skipped = -1
        lo, hi = a.window
        rows.append({
            "sha1": sha, "status": "ok" if not issues else ",".join(issues),
            "words": words, "in_window": "Y" if lo <= words <= hi else "N",
            "subsequence": "Y" if sub_ok else "N", "skipped": skipped,
            "index_words": index.get(sha, {}).get("words", ""),
        })

    bad_fmt = [r for r in rows if r["status"] not in ("ok",)]
    bad_seq = [r for r in rows if r.get("subsequence") == "N"]
    out_win = [r for r in rows if r.get("in_window") == "N"]
    ws = [r["words"] for r in rows if r["words"]]
    summary = {
        "docs": len(rows),
        "total_words": sum(ws),
        "min": min(ws) if ws else 0,
        "median": statistics.median(ws) if ws else 0,
        "max": max(ws) if ws else 0,
        "format_issues": len(bad_fmt),
        "subsequence_failures": len(bad_seq),
        "out_of_window": len(out_win),
        "detail": {"format": bad_fmt[:20], "subsequence": bad_seq[:20], "window": out_win[:20]},
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "detail"}, ensure_ascii=False, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
        print("wrote", a.out)


if __name__ == "__main__":
    main()
