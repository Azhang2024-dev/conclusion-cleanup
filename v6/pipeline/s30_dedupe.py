# -*- coding: utf-8 -*-
"""s30_dedupe.py - build a manifest for the candidate pool and run the identity gate.

A corpus of 485 must not contain the same article twice. The library has been
bitten by this before: two PDF versions of one paper, registered separately.
"""
import os, sys, io, json, csv, re, subprocess

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
ROOT = os.path.dirname(STAGE)
OUT = os.path.join(STAGE, "R6_corpus_check")
TXT = os.path.join(OUT, "txt")


def title_from_rel(rel):
    base = os.path.splitext(os.path.basename(rel))[0]
    base = re.sub(r"[_\s]*(19|20)\d\d$", "", base)
    base = base.replace("__", ": ").replace("_", " ").strip()
    return re.sub(r"\s+", " ", base)


def main():
    os.makedirs(TXT, exist_ok=True)
    recs = [json.loads(l) for l in open(os.path.join(STAGE, "R4_llm_all", "gate.jsonl"), encoding="utf-8")]
    old = {}
    p = os.path.join(STAGE, "R1_packets", "index.csv")
    if os.path.exists(p):
        for row in csv.DictReader(open(p, encoding="utf-8-sig")):
            old[row["sha1"]] = row
    cand = [r for r in recs if r.get("in_corpus")]
    man = os.path.join(OUT, "manifest_485.csv")
    with open(man, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["no", "code", "year", "title", "doi", "sha1", "first_author", "words", "pdf", "txt"])
        for r in cand:
            o = old.get(r["sha1"], {})
            t = (o.get("title") or "").strip() or title_from_rel(r["rel_path"])
            src = os.path.join(STAGE, "R4_llm_all", r["sha1"], "cplx_t0p0_run1.json")
            txt = json.load(open(src, encoding="utf-8")).get("text", "")
            rel = "txt/%s.txt" % r["sha1"]
            open(os.path.join(OUT, rel), "w", encoding="utf-8").write(txt)
            w.writerow([r["id"], r["journal"], r["year"], t, "", r["sha1"], "", r["llm_words"],
                        r["rel_path"], rel])
    print("manifest rows=%d -> %s" % (len(cand), man))
    dg = os.path.join(ROOT, "08_语料库流水线", "dedupe_gate.py")
    res = subprocess.run([sys.executable, dg, "check", "--manifest", man, "--txt-root", OUT],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(res.stdout[-4000:])
    print("exit", res.returncode)
    # keep the clusters on disk so the corpus rule can exclude them
    clusters = re.findall(r"CLUSTER \['([^']+)', '([^']+)'\]", res.stdout or "")
    keep_drop = {"011": "103", "068": "X291"}
    dups = {}
    for a, b in clusters:
        if a in keep_drop and keep_drop[a] == b:
            dups[b] = a
        elif b in keep_drop and keep_drop[b] == a:
            dups[a] = b
        else:
            dups[b] = a
    json.dump(dups, open(os.path.join(OUT, "dups.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("duplicates to drop:", dups)
    if res.stderr.strip():
        print("ERR", res.stderr[-800:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
