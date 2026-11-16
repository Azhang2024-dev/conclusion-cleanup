# -*- coding: utf-8 -*-
"""verify_output.py — the gate. The model may clean; it may not rewrite.

Two questions, in this order:

  A  line coverage   every line of the claimed span must either survive in the
                     output or be declared in "dropped" (or be obvious furniture)
  B  residue         whatever survives is compared character by character with
                     the frozen text; each difference must fall in one of the
                     allowed repair classes

The comparison ignores case-preserving whitespace, every hyphen, and Word
proofing marks, because both joining a split word and dropping a stray hyphen
are legitimate cleaning. It does not ignore letters: a changed word is a FAIL.

    python tools/verify_output.py --stage PATH --result out.json [--json]
"""
import os, sys, io, json, re, argparse, difflib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")

FURN = re.compile(r"^(fig\.|figure|table|plate|box|scheme|chart|note|footnote|references|"
                  r"acknowledg|appendix|downloaded|broughttoyou|termsandconditions|"
                  r"journalpre-proof|acceptedmanuscript|thisarticleis|copyright|\u00a9)", re.I)
NOISE = re.compile(r"\[[0-9]{1,3}_TD\$DIF\]|\[[0-9]{1,3}\]|[\u0001-\u0003\ufffd\u00ac\u00ad]")
DASH = "\u2014\u2013"

def norm(s):
    """Whitespace, hyphens and proofing marks are not evidence."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = NOISE.sub("", s)
    s = re.sub(r"[\s\-]", "", s)
    return s

def furniture(n):
    return bool(FURN.match(n[:30])) or bool(re.fullmatch(r"\d{1,4}", n))

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    st = a.stage
    res = json.load(open(a.result, encoding="utf-8"))
    sha = res["sha1"]
    alog = [json.loads(l) for l in open(os.path.join(st, "A_lines", sha + ".jsonl"), encoding="utf-8") if l.strip()]
    sl, el = int(res["start_line"]), int(res["end_line"])
    if not (0 <= sl <= el < len(alog)):
        print("FAIL 行号越界 %s..%s / %d 行" % (sl, el, len(alog)))
        return 1
    declared = {}
    for d in res.get("dropped", []):
        try:
            declared[int(d["line"])] = str(d.get("why", ""))[:20]
        except (TypeError, ValueError):
            pass
    out = norm(res.get("text", ""))

    # ---- A: line coverage -------------------------------------------------
    survived, silent = [], []
    for i in range(sl, el + 1):
        n = norm(alog[i]["text"])
        if not n:
            continue
        if i in declared:
            continue
        if furniture(n):
            continue
        if n in out:
            survived.append(i)
        else:
            silent.append(i)
    expect = "".join(norm(alog[i]["text"]) for i in survived)

    # ---- B: residue -------------------------------------------------------
    allowed, bad = [], []
    sm = difflib.SequenceMatcher(None, expect, out, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        s, o = expect[i1:i2], out[j1:j2]
        ctx = expect[max(0, i1 - 24):i1]
        if tag == "delete":
            if re.fullmatch(r"\d{1,4}", s):
                allowed.append(("删脚注号", s, ctx))
            elif len(s) <= 3 and s.isalpha():
                allowed.append(("删孤立字母", s, ctx))
            else:
                bad.append(("删字", s, ctx))
        elif tag == "insert":
            if set(o) <= set(DASH):
                allowed.append(("补破折号", o, ctx))
            else:
                bad.append(("加字", o, ctx))
        else:
            if len(s) == 1 and len(o) == 1 and (s in "de\u00fe" or o in DASH):
                allowed.append(("破折号还原", s + "->" + o, ctx))
            elif set(o) <= set(DASH) and len(s) <= 3:
                allowed.append(("破折号展开", s + "->" + o, ctx))
            else:
                bad.append(("改写", s + "->" + o, ctx))

    from collections import Counter
    cnt = Counter(k for k, _, _ in allowed)
    status = "PASS" if (not bad and not silent) else "FAIL"
    if a.json:
        print(json.dumps({"sha1": sha, "status": status, "survived": len(survived),
                          "silent_drops": silent, "allowed": dict(cnt),
                          "violations": [{"kind": k, "text": s[:40], "ctx": c[-30:]} for k, s, c in bad]},
                         ensure_ascii=False))
    else:
        print("%s %s | 保留 %d 行 | 允许改动 %d %s | 未申报删除 %d | 改写 %d" % (
            status, sha[:8], len(survived), len(allowed), dict(cnt), len(silent), len(bad)))
        for i in silent[:8]:
            print("   [未申报删除] L%d %r" % (i, alog[i]["text"][:70]))
        for k, s, c in bad[:8]:
            print("   [%s] ...%s << %r >>" % (k, c[-22:], s[:50]))
    return 0 if status == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
