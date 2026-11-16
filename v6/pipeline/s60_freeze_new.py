# -*- coding: utf-8 -*-
"""s60_freeze_new.py - stage the newly downloaded OA PDFs into the frozen line stream.

Reuses a_freeze.freeze_one so the new documents get byte-identical treatment to
the original 697. Three things happen in order, which is also the order the user
asked for:

  1  dedupe   sha1 against every existing A_lines file; normalised title against
              the existing pool and within the new batch; DOI against itself
  2  freeze   write A_lines/{sha1}.jsonl and A_lines/pages/{sha1}.json
  3  usability char count / line count / pages, and a text_layer flag

    python s60_freeze_new.py --ledger ../R11_新增PDF_OA_2026-11-16/download_ledger.csv
"""
import os, sys, io, csv, json, re, argparse, importlib.util
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)

spec = importlib.util.spec_from_file_location("a_freeze", os.path.join(HERE, "a_freeze.py"))
af = importlib.util.module_from_spec(spec)
spec.loader.exec_module(af)

CANON = {
    "Applied_linguistics": "Applied linguistics",
    "Cognitive_linguistics": "Cognitive linguistics",
    "IJCL": "IJCL",
    "Journal_of_EAP": "Journal of EAP",
    "Journal_of_ESP": "Journal of ESP",
    "Journal_of_Pragmatics": "Journal of Pragmatics",
    "Journal_of_semantics": "Journal of semantics",
    "Language_learning": "Language learning",
    "Language_teaching": "Language teaching",
    "TESOL_Quarterly": "TESOL Quarterly",
}


def norm_title(t):
    t = (t or "").lower()
    return re.sub(r"[^a-z0-9]+", "", t)[:70]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out-index", default=os.path.join(STAGE, "_logs", "index_new.csv"))
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(a.ledger, encoding="utf-8-sig")) if r["status"] == "ok"]
    print("ok rows in ledger:", len(rows), flush=True)

    # existing identity: sha1 files, titles from the 697 index
    A = os.path.join(STAGE, "A_lines")
    have_sha = {os.path.splitext(f)[0] for f in os.listdir(A) if f.endswith(".jsonl")}
    pool_titles = set()
    gate_p = os.path.join(STAGE, "R4_llm_all", "gate.jsonl")
    for line in open(gate_p, encoding="utf-8"):
        rec = json.loads(line)
        base = os.path.splitext(os.path.basename(rec.get("rel_path") or ""))[0]
        base = re.sub(r"[_\s]*(19|20)\d\d$", "", base)
        pool_titles.add(norm_title(base))
    print("existing A_lines:", len(have_sha), "| pool titles:", len(pool_titles), flush=True)

    seen_titles = set(pool_titles)
    out, dropped = [], []
    for r in rows:
        p = r["file"]
        if not p or not os.path.exists(p):
            dropped.append((r["doi"], "missing_file")); continue
        sha = af.sha1_file(p)
        if sha in have_sha:
            dropped.append((r["doi"], "dup_sha1")); continue
        t = norm_title(r["title"])
        if t and t in seen_titles:
            dropped.append((r["doi"], "dup_title")); continue
        seen_titles.add(t)
        journal = CANON.get(os.path.basename(os.path.dirname(p)), os.path.basename(os.path.dirname(p)))
        rel = "%s/%s/%s" % (journal, r["year"] or "na", os.path.basename(p))
        try:
            rec = af.freeze_one(rel, p)
        except Exception as e:
            dropped.append((r["doi"], "freeze_fail: " + str(e)[:50])); continue
        rec["doi"] = r["doi"]
        rec["version"] = r.get("version", "")
        rec["src_pdf"] = p
        out.append(rec)
        have_sha.add(rec["sha1"])
        if len(out) % 25 == 0:
            print("  frozen", len(out), flush=True)

    with open(a.out_index, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    print("\nfrozen:", len(out), "| dropped:", len(dropped), Counter(d[1].split(":")[0] for d in dropped), flush=True)
    bad = [r for r in out if r["text_layer_ok"] != "1"]
    print("text layer problems:", len(bad), [(r["doi"], r["chars"]) for r in bad][:10], flush=True)
    print("median chars:", sorted(r["chars"] for r in out)[len(out)//2] if out else 0, flush=True)
    print("index ->", a.out_index, flush=True)


if __name__ == "__main__":
    sys.exit(main())
