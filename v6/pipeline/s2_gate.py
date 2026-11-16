# -*- coding: utf-8 -*-
"""s2_gate.py - gate every model result and line it up against the code path.

For each document it puts three things side by side:

  code path   B_spans/{sha}.json  heading / end / kept_lines / dropped+reason
              C_conclusions(_clean)/{sha}.txt   the text the rules produced
  model path  R4_llm_all/{sha}/cplx_t0p0_run1.json
  gate        verify_output.main(--json), imported from source so there is one
              implementation of the check

Output: R4_llm_all/gate.jsonl  (one record per document) and gate.csv.

    python s2_gate.py --out R4_llm_all --tag cplx --run 1
"""
import os, sys, io, json, csv, re, argparse, difflib, importlib.util

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
sys.path.insert(0, r"D:\conclusion-wordcount\src")
from wcengine.count import count_words

SKILL = os.path.join(STAGE, "_skill_repo", "span-locator", "tools", "verify_output.py")


def load_gate():
    """Exec verify_output source without its stdout wrapper side effect."""
    src = open(SKILL, encoding="utf-8").read()
    src = "\n".join(l for l in src.splitlines()
                    if not l.startswith("sys.stdout = io.TextIOWrapper"))
    mod = {"__name__": "gate_mod", "__file__": SKILL}
    exec(compile(src, SKILL, "exec"), mod)
    return mod


def run_gate(mod, stage, result_path):
    buf = io.StringIO()
    real = sys.stdout
    sys.stdout = buf
    try:
        mod["main"](["--stage", stage, "--result", result_path, "--json"])
    except SystemExit:
        pass
    finally:
        sys.stdout = real
    txt = buf.getvalue().strip()
    try:
        return json.loads(txt.splitlines()[-1])
    except Exception:
        return {"status": "ERROR", "raw": txt[:200]}


FOOT = re.compile(r"^([0-9]{1,2}\s+[A-Z]|\[[0-9]{1,2}\]|Cf\.|Sonar-id|[0-9]{1,4}$|"
                   r"[a-z]\s|I thank|We thank|.*thank an anonymous|Note that|\u2020)", re.S)


def classify_silent(alog, lines):
    """A dropped line that is a footnote, a cross-reference or a stray number is
    not lost content. Only prose counts."""
    kinds = []
    for i in lines:
        t = alog[i]["text"].strip()
        if FOOT.match(t):
            kinds.append("footnote")
        elif len(re.sub(r"[^A-Za-z]", "", t)) < 8:
            kinds.append("tiny")
        else:
            kinds.append("body")
    return kinds


def build_full(alog):
    """Whole-document normalised text plus the line that owns each character."""
    parts, owner = [], []
    for i, o in enumerate(alog):
        n = re.sub(r"[\s\-]", "", o["text"])
        parts.append(n)
        owner.extend([i] * len(n))
    return "".join(parts), owner


def find_outside(full, owner, text, sl, el):
    """Which line does the inserted text actually come from?

    Line breaks split a sentence, so the needle is searched in the whole
    document, not line by line.
    """
    needle = re.sub(r"[\s\-]", "", text or "")
    if len(needle) < 8:
        return None
    for k in (24, 16, 12, 8):
        p = full.find(needle[:k])
        if p >= 0:
            ln = owner[p]
            return ln if not (sl <= ln <= el) else -1
    return None


def read_json(p, default=None):
    if not os.path.exists(p):
        return default
    return json.load(open(p, encoding="utf-8"))


def read_txt(p):
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def sim(a, b):
    if not a or not b:
        return 0.0
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 4)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(STAGE, "R4_llm_all"))
    ap.add_argument("--tag", default="cplx")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.0)
    a = ap.parse_args(argv)

    mod = load_gate()
    norm = mod["norm"]

    # master index over all 697 shards
    idx = {}
    for i in range(4):
        p = os.path.join(STAGE, "_logs", "index_s%d.csv" % i)
        if not os.path.exists(p):
            continue
        for row in csv.DictReader(open(p, encoding="utf-8-sig")):
            idx[row["sha1"]] = row

    # ids from the 499 review index, so old references stay valid
    ids = {}
    ip = os.path.join(STAGE, "R1_packets", "index.csv")
    if os.path.exists(ip):
        for row in csv.DictReader(open(ip, encoding="utf-8-sig")):
            ids[row["sha1"]] = row["id"]

    all_sha = sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(STAGE, "A_lines"))
                     if f.endswith(".jsonl"))
    recs = []
    for k, sha in enumerate(all_sha, 1):
        tag = str(a.temperature).replace(".", "p")
        res_path = os.path.join(a.out, sha, "%s_t%s_run%d.json" % (a.tag, tag, a.run))
        res = read_json(res_path)
        b = read_json(os.path.join(STAGE, "B_spans", sha + ".json"), {}) or {}
        alog = [json.loads(l) for l in open(os.path.join(STAGE, "A_lines", sha + ".jsonl"),
                                            encoding="utf-8") if l.strip()]
        code_p = os.path.join(STAGE, "C_conclusions_clean", sha + ".txt")
        code_clean = os.path.exists(code_p)
        if not code_clean:
            code_p = os.path.join(STAGE, "C_conclusions", sha + ".txt")
        code_text = read_txt(code_p)
        info = idx.get(sha, {})

        code_start = (b.get("heading_line") or 0) + 1 if b.get("heading_line") is not None else 0
        code_end = b.get("end_line") or 0
        kept = set(b.get("kept_lines") or [])
        code_drop = {int(d["line"]): d.get("reason", "") for d in (b.get("dropped") or [])}

        rec = {
            "id": ids.get(sha, "X%03d" % k),
            "sha1": sha, "sha8": sha[:8],
            "journal": info.get("journal", ""), "year": info.get("year", ""),
            "rel_path": info.get("rel_path", ""), "pages": info.get("pages", ""),
            "n_lines": len(alog), "chars": info.get("chars", ""),
            "text_layer_ok": info.get("text_layer_ok", ""),
            "code_heading": b.get("heading_line", ""),
            "code_start": code_start, "code_end": code_end,
            "code_words": count_words(code_text) if code_text else 0,
            "code_nkept": len(kept), "code_ndrop": len(code_drop),
            "code_reasons": ";".join(sorted({v for v in code_drop.values() if v})),
            "code_text_chars": len(code_text),
            "code_end_reason": b.get("end_reason", ""),
        }

        if not res:
            rec.update({"status": "MISSING", "gate_status": "MISSING",
                        "llm_start": "", "llm_end": "", "llm_words": 0,
                        "need_review": "yes", "review_why": "no_result"})
            recs.append(rec)
            continue

        g = run_gate(mod, STAGE, res_path)
        llm_text = res.get("text", "") or ""
        sil_kinds = classify_silent(alog, g.get("silent_drops") or [])
        full, owner = build_full(alog)
        ins_hits = []
        for v in (g.get("violations") or []):
            if v.get("kind") == "insert":
                ins_hits.append(find_outside(full, owner, v.get("text", ""),
                                             int(res["start_line"]), int(res["end_line"])))
        if g.get("status") == "PASS":
            fclass = "clean"
        elif "body" in sil_kinds:
            fclass = "silent_body"
        elif any(h is not None for h in ins_hits):
            fclass = "insert_outside"
        elif sil_kinds:
            fclass = "silent_footnote"
        elif g.get("violations"):
            fclass = "rewrite_or_insert"
        else:
            fclass = "other"
        rec.update({
            "llm_start": res.get("start_line"), "llm_end": res.get("end_line"),
            "llm_words": count_words(llm_text), "llm_confidence": res.get("confidence", ""),
            "llm_ndropped": len(res.get("dropped") or []),
            "llm_reasons": ";".join(sorted({str(d.get("why", ""))[:20] for d in (res.get("dropped") or [])})),
            "llm_text_chars": len(llm_text),
            "gate_status": g.get("status", "ERROR"),
            "gate_survived": g.get("survived", 0),
            "gate_nsilent": len(g.get("silent_drops") or []),
            "gate_silent_lines": ",".join(str(x) for x in (g.get("silent_drops") or [])[:12]),
            "gate_nbad": len(g.get("violations") or []),
            "gate_allowed": json.dumps(g.get("allowed") or {}, ensure_ascii=False),
            "gate_viol": "; ".join("%s:%s" % (v.get("kind"), v.get("text")) for v in (g.get("violations") or [])[:4]),
            "silent_kinds": ",".join(sorted(set(sil_kinds))),
            "fail_class": fclass,
            "start_delta": (res.get("start_line", 0) - code_start) if code_start else "",
            "end_delta": (res.get("end_line", 0) - code_end) if code_end else "",
            "word_delta": count_words(llm_text) - (count_words(code_text) if code_text else 0),
            "sim_llm_vs_code": sim(norm(llm_text), norm(code_text)) if code_text else 0.0,
            "latency_s": res.get("latency_s"), "in_tokens": (res.get("usage") or {}).get("prompt_tokens"),
            "out_tokens": (res.get("usage") or {}).get("completion_tokens"),
        })
        rec["span_match"] = 1 if (rec["llm_start"] == code_start and rec["llm_end"] == code_end) else 0
        rec["llm_in_window"] = 1 if 250 <= rec["llm_words"] <= 600 else 0
        rec["code_in_window"] = 1 if 250 <= rec["code_words"] <= 600 else 0

        why = []
        if rec["gate_status"] != "PASS":
            why.append("gate_" + rec["gate_status"].lower())
        if code_start and abs(rec["llm_start"] - code_start) > 1:
            why.append("start_diff")
        if code_end and abs(rec["llm_end"] - code_end) > 1:
            why.append("end_diff")
        if not rec["llm_in_window"]:
            why.append("llm_out_of_window")
        if code_text and rec["sim_llm_vs_code"] < 0.97:
            why.append("text_diff")
        rec["need_review"] = "yes" if why else ""
        rec["review_why"] = ";".join(why)

        # line ledger for the union of both spans
        lo = min(x for x in (rec["llm_start"], code_start) if x)
        hi = max(rec["llm_end"], code_end)
        declared = {}
        for d in (res.get("dropped") or []):
            try:
                declared[int(d["line"])] = str(d.get("why", ""))[:24]
            except Exception:
                pass
        out_n = norm(llm_text)
        ledger = []
        for i in range(lo, hi + 1):
            if i < 0 or i >= len(alog):
                continue
            t = alog[i]["text"]
            in_llm = rec["llm_start"] <= i <= rec["llm_end"]
            in_code = code_start <= i <= code_end
            if in_code:
                cv = "keep" if i in kept else ("drop:" + (code_drop.get(i) or "?"))
            else:
                cv = "out"
            if in_llm:
                if i in declared:
                    lv = "drop:" + declared[i]
                else:
                    n = norm(t)
                    if n and (n in out_n or mod["cover"](n, out_n) >= 0.90):
                        lv = "keep"
                    elif not n:
                        lv = "keep"
                    else:
                        lv = "drop:silent"
            else:
                lv = "out"
            if cv != "keep" or lv != "keep":
                ledger.append({"line": i, "text": t, "code": cv, "llm": lv})
        rec["ledger"] = ledger
        recs.append(rec)

    # ---- write -----------------------------------------------------------
    jsonl = os.path.join(a.out, "gate.jsonl")
    with open(jsonl, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    flat = [{k: v for k, v in r.items() if k != "ledger"} for r in recs]
    cols = list(flat[0].keys())
    csvp = os.path.join(a.out, "gate.csv")
    with open(csvp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(flat)

    from collections import Counter
    st = Counter(r.get("gate_status") for r in recs)
    print("records=%d  gate=%s" % (len(recs), dict(st)))
    print("span_match=%d  need_review=%d" % (sum(r.get("span_match", 0) for r in recs),
                                             sum(1 for r in recs if r.get("need_review"))))
    print("wrote " + jsonl)
    print("wrote " + csvp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
