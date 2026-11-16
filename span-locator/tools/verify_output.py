# -*- coding: utf-8 -*-
"""verify_output.py - the gate. The model may clean; it may not rewrite.

Three questions, in this order:

  A  line coverage   every body line of the claimed span must survive in the
                     output. A line that is furniture (caption, running head,
                     page number, watermark, footnote) may be dropped without a
                     declaration; a body line may not.
  B  residue         whatever survives is compared character by character with
                     the frozen text; each difference must fall in one of the
                     allowed repair classes (footnote number, broken glyph,
                     typographic quote, dash, lost space)
  C  declaration     a line declared dropped but actually present is reported
                     separately from a line silently dropped

The comparison ignores whitespace, every hyphen and Word proofing marks, because
both joining a split word and dropping a stray hyphen are legitimate cleaning.
It does not ignore letters: a changed word is a FAIL.

    python verify_output.py --stage PATH --result out.json [--json]
"""
import os, sys, io, json, re, argparse, difflib
from collections import Counter

FURN_CAPTION = re.compile(r"^(fig(ure)?s?\.?|table|plate|box|scheme|chart)\s*\d", re.I)
FURN_HEAD = re.compile(r"^(references?|bibliography|acknowledge?ments?|appendix|appendices|"
                       r"notes?|footnotes?|endnotes?|funding|credits?)\s*[0-9.:]*$", re.I)
FURN_MARK = re.compile(r"^(downloadedfrom|broughttoyou|termsandconditions|"
                       r"journalpreproof|acceptedmanuscript|thisarticleis|copyright|"
                       r"\u00a9|allrightsreserved|authenticated)", re.I)
NOISE = re.compile(r"\[[0-9]{1,3}_TD\$DIF\]|\[[0-9]{1,3}\]|[\u0001-\u0003\ufffd\u00ac\u00ad]")
DASH = "\u2014\u2013"
QUOTE = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}


def norm(s):
    """Whitespace, hyphens and proofing marks are not evidence."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = NOISE.sub("", s)
    s = re.sub(r"[\s\-]", "", s)
    return s


def cover(line, out):
    """Fraction of the line's characters that reappear, in order, in the output.

    A line the model repaired (dash glyph, footnote number, a lost space) is
    still the same line; an exact substring test would call it deleted.
    """
    if not line:
        return 1.0
    sm = difflib.SequenceMatcher(None, line, out, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(line)


def furniture(n, reps=None):
    if not n:
        return True
    if re.fullmatch(r"[0-9]{1,4}", n):
        return True
    # "Fig. 1 below provides an overview ..." is a sentence, not a caption. A
    # caption is short; body prose that happens to open with a figure reference
    # runs long. Length is the only thing that separates them.
    if FURN_CAPTION.match(n[:24]) and len(n) <= 80:
        return True
    if FURN_HEAD.match(n[:24]) or FURN_MARK.match(n[:30]):
        return True
    if reps is not None and reps.get(n, 0) >= 3:
        return True
    return False


def load_lines(stage, sha):
    p = os.path.join(stage, "A_lines", sha + ".jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    st = a.stage
    res = json.load(open(a.result, encoding="utf-8"))
    sha = res["sha1"]
    alog = load_lines(st, sha)
    sl, el = int(res["start_line"]), int(res["end_line"])
    if not (0 <= sl <= el < len(alog)):
        print("FAIL out of range %s..%s / %d" % (sl, el, len(alog)))
        return 1
    reps = Counter(norm(o["text"]) for o in alog)

    declared = {}
    for d in res.get("dropped", []) or []:
        try:
            declared[int(d["line"])] = str(d.get("why", ""))[:20]
        except (TypeError, ValueError):
            pass
    out = norm(res.get("text", ""))

    # ---- A: line coverage, and who owns each character of the reference ----
    survived, silent, furn, lied = [], [], [], []
    owner = []
    for i in range(sl, el + 1):
        n = norm(alog[i]["text"])
        if not n:
            continue
        fur = furniture(n, reps)
        present = (n in out) or cover(n, out) >= 0.90
        if fur and not present:
            furn.append(i)
            continue
        if i in declared:
            lied.append(i)
            continue
        if present:
            survived.append(i)
            owner.extend([i] * len(n))
        else:
            silent.append(i)
    expect = "".join(norm(alog[i]["text"]) for i in survived)
    fur_set = set(furn) | set(i for i in range(sl, el + 1)
                              if furniture(norm(alog[i]["text"]), reps))

    # ---- B: residue -------------------------------------------------------
    allowed, bad = [], []
    sm = difflib.SequenceMatcher(None, expect, out, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        s, o = expect[i1:i2], out[j1:j2]
        ctx = expect[max(0, i1 - 24):i1]
        owners = set(owner[i1:i2]) if i1 < len(owner) else set()
        if tag == "delete" and owners and owners <= fur_set:
            allowed.append(("delete_furniture", s, ctx))
        elif tag == "delete":
            if re.fullmatch(r"[0-9.,;:\[\]()]{1,10}", s):
                allowed.append(("delete_footnote_no", s, ctx))
            elif len(s) <= 3 and s.isalpha():
                allowed.append(("delete_stray_letter", s, ctx))
            else:
                bad.append(("delete", s, ctx))
        elif tag == "insert":
            if set(o) <= set(DASH):
                allowed.append(("add_dash", o, ctx))
            else:
                bad.append(("insert", o, ctx))
        else:
            if len(s) == 1 and len(o) == 1 and QUOTE.get(s) == o:
                allowed.append(("quote_norm", s + "->" + o, ctx))
            elif len(o) == 1 and ord(o) > 127 and len(s) <= 2:
                allowed.append(("glyph_fix", s + "->" + o, ctx))
            elif set(o) <= set(DASH) and len(o) <= len(s) + 1:
                allowed.append(("dash_expand", s + "->" + o, ctx))
            else:
                bad.append(("rewrite", s + "->" + o, ctx))

    cnt = Counter(k for k, _, _ in allowed)
    status = "PASS" if (not bad and not silent) else "FAIL"
    if a.json:
        print(json.dumps({"sha1": sha, "status": status, "survived": len(survived),
                          "silent_drops": silent, "allowed": dict(cnt),
                          "declared_but_kept": lied, "n_furniture": len(furn),
                          "violations": [{"kind": k, "text": s[:60], "ctx": c[-30:]} for k, s, c in bad]},
                         ensure_ascii=False))
    else:
        print("%s %s | kept %d lines | allowed %d %s | silent %d | bad %d | declared-but-kept %d" % (
            status, sha[:8], len(survived), len(allowed), dict(cnt), len(silent), len(bad), len(lied)))
        for i in silent[:8]:
            print("   [silent drop] L%d %r" % (i, alog[i]["text"][:70]))
        for k, s, c in bad[:8]:
            print("   [%s] ...%s << %r >>" % (k, c[-22:], s[:50]))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
