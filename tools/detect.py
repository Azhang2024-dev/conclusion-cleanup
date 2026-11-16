# -*- coding: utf-8 -*-
"""Stage 1: detect candidate foreign material inside conclusion texts.

Reads  <stage>/C_conclusions/{sha1}.txt  and the frozen line stream,
writes <stage>/E_reports/candidates.csv with line numbers and reason codes.
Never touches the text.

Usage:
    python tools/detect.py --stage PATH [--sha SHA1 ...] [--out CSV]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

TERM = re.compile(r"[.!?\"”’)\]]\s*$")


def compile_rules(rules):
    sig = rules.get("signals", {})
    rx = {
        "pagenum": [re.compile(p) for p in sig.get("pagenum", {}).get("patterns", [])],
        "pagenum_inline": re.compile(sig.get("pagenum", {}).get("inline_pattern", r"$^")),
        "caption_head": re.compile(sig.get("caption", {}).get("head_pattern", r"$^")),
        "caption_caps": re.compile(sig.get("caption", {}).get("head_caps_pattern", r"$^")),
        "caption_bare": re.compile(sig.get("caption", {}).get("bare_label_pattern", r"$^"), re.I),
        "footer_frag": re.compile(sig.get("footer_frag", {}).get("pattern", r"$^"), re.I),
        "footnote_line": re.compile(sig.get("footnote_line", {}).get("pattern", r"$^")),
        "caption_source": re.compile(sig.get("caption", {}).get("source_pattern", r"$^"), re.I),
        "caption_ts": re.compile(sig.get("caption", {}).get("timestamp_pattern", r"$^"), re.I),
        "caption_ext": re.compile(sig.get("caption", {}).get("extracted_pattern", r"$^"), re.I),
        "watermark": re.compile(sig.get("watermark", {}).get("pattern", r"$^"), re.I),
        "tail": re.compile(sig.get("tail_block", {}).get("label_pattern", r"$^"), re.I),
        "footcall": re.compile(sig.get("footnote_call", {}).get("pattern", r"$^")),
        "pipe": re.compile(r"[|¦]"),
    }
    return rx


def heading_hint(stage, sha1):
    """First frozen-stream index of the conclusion body (heading line + 1)."""
    cache = getattr(stage, '_hint', None)
    if cache is None:
        cache = stage._hint = {}
        p = os.path.join(stage.texts, 'index.csv')
        for r in lib.read_csv(p):
            try:
                cache[r['sha1']] = int(r['heading_line']) + 1
            except (TypeError, ValueError):
                continue
    return cache.get(sha1, 0)


def table_hit(rec, s, boxes, pad=6.0, max_chars=70):
    """Is this line table content?  Two independent conditions:

    - the line sits inside (or within `pad` of) a detected table box on its page
    - the line looks like a cell: short, and it does not close a sentence

    The second condition matters because find_tables can return a box that
    covers most of a page; without it, prose lines would be swallowed.
    """
    page, y0, y1 = rec.get("page"), rec.get("y0", 0), rec.get("y1", 0)
    if len(s.strip()) > max_chars:
        return False
    if TERM.search(s.strip()) and len(s.split()) >= 6:
        return False
    for (bp, x0, by0, x1, by1) in boxes:
        if bp == page and y0 >= by0 - pad and y1 <= by1 + pad:
            return True
    return False


def detect_doc(sha1, stage, rules, rx):
    text = lib.read_text(os.path.join(stage.texts, sha1 + ".txt"))
    lines = lib.lines_of(text)
    n = len(lines)
    conf = rules.get("signals", {})
    rh = conf.get("running_head", {})
    min_pages = rh.get("min_pages_seen", 2)
    rh_max = rh.get("max_chars", 90)
    band_ratio = rh.get("band_top_ratio", 0.05)
    band_max = rh.get("band_max_chars", 110)
    repeat_any_pages = rh.get("repeat_any_length_pages", 3)
    min_body_words = rh.get("min_body_words", 6)

    # geometry from the frozen stream
    bodytop = {}
    pcount = defaultdict(set)
    try:
        recs = stage.load_lines(sha1)
    except FileNotFoundError:
        recs = []
    for d in recs:
        t = d.get("text", "")
        if len(t) >= 60 and (d.get("y1", 0) - d.get("y0", 0)) < 40:
            p = d.get("page")
            bodytop[p] = min(bodytop.get(p, 1e9), d.get("y0", 0))
        k = lib.norm_num(t)
        if len(k) >= 10:
            pcount[k].add(d.get("page"))

    start = heading_hint(stage, sha1)
    geo = lib.map_lines_to_geo(lines, recs, start) if recs else [None] * n
    boxes = []
    for page, arr in (stage.load_tables(sha1) or {}).items():
        for b in arr or []:
            boxes.append((int(page), b[0], b[1], b[2], b[3]))

    hits = []
    tail_start = None
    for k, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        add = lambda reason, note="": hits.append({"sha1": sha1, "line": k, "reason": reason, "note": note})
        # tail block: label at head and previous line terminated
        prev = lines[k - 1].rstrip() if k else ""
        if k and rx["tail"].match(s) and (not conf.get("tail_block", {}).get("require_prev_terminated", True) or TERM.search(prev or "x")):
            tail_start = k
            add("TAIL_BLOCK", s[:60])
            continue
        if tail_start is not None:
            add("TAIL_BLOCK", s[:60])
            continue
        if any(p.match(s) for p in rx["pagenum"]):
            add("PAGENUM")
            continue
        # a page number spliced onto the tail of a body line.  The line stays;
        # only the token goes (apply.py action "strip"), so this mark is not a
        # deletion and must not be treated as one downstream.
        if len(s.split()) >= 3:
            mi = rx["pagenum_inline"].search(s)
            if mi:
                add("PAGENUM_INLINE", mi.group(1))
                continue
        # a printer footer / a stray numbered reference line.  Both are checked
        # before the running-head test: they are short, they repeat, and the
        # head test would otherwise claim them under the wrong reason code.
        if rx["footer_frag"].match(s):
            add("FOOTER_FRAG")
            continue
        if rx["footnote_line"].match(s):
            add("FOOTNOTES")
            continue
        if (rx["caption_head"].match(s) or rx["caption_caps"].match(s)
                or rx["caption_bare"].match(s) or rx["caption_source"].match(s)
                or rx["caption_ts"].match(s) or rx["caption_ext"].match(s)):
            add("CAPTION")
            continue
        if rx["watermark"].search(s):
            add("WATERMARK")
            continue
        # running head first: it often carries a leading "|" separator and
        # would otherwise be misclassified as a pipe artefact.
        #
        # Guards against body sentences that merely coincide with a repeated
        # phrase (e.g. a one-word closing line "communicative potential."):
        #   - a sentence-ending line with no digits is never furniture
        #   - drop nothing that closes the conclusion
        key = lib.norm_num(s)
        pages_seen = len(pcount.get(key, ()))
        ends_sentence = bool(TERM.search(s))
        has_digit = any(ch.isdigit() for ch in s)
        sentencish = ends_sentence and (not has_digit or len(s.split()) >= min_body_words)
        is_last = (k == len(lines) - 1) or not any(x.strip() for x in lines[k + 1:])
        if len(s) <= rh_max and not sentencish and not is_last and (
                (len(key) >= 10 and pages_seen >= min_pages)
                or pages_seen >= repeat_any_pages):
            add("RUNHEAD", "%d pages" % pages_seen)
            continue
        g = geo[k] if k < len(geo) else None
        if g and boxes and table_hit(g, s, boxes):
            add("TABLE", "bbox p%s" % g["page"])
            continue
        if rx["pipe"].search(s):
            add("PIPE" if s.strip(" |¦") == "" else "PIPE_PARTIAL")
            continue
        m = rx["footcall"].search(s)
        if m and not re.search(r"\b(19|20)\d\d$", s):
            add("FOOTNOTE_CALL", m.group(0)[-6:])
            continue
    return hits, n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default=None)
    ap.add_argument("--rules", default=None)
    ap.add_argument("--sha", nargs="*", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    stage = lib.Stage(a.stage)
    rules = lib.load_rules(a.rules)
    rx = compile_rules(rules)
    shas = a.sha or stage.sha_list()
    rows = []
    for sha in shas:
        hits, n = detect_doc(sha, stage, rules, rx)
        for h in hits:
            h["n_lines"] = n
            rows.append(h)
    out = a.out or os.path.join(stage.reports, "candidates.csv")
    lib.write_csv(out, rows, ["sha1", "line", "reason", "note", "n_lines"])
    c = Counter(h["reason"] for h in rows)
    print("docs %d | candidates %d | %s" % (len(shas), len(rows), dict(c)))
    print("wrote", out)


if __name__ == "__main__":
    main()
