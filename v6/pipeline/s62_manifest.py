# -*- coding: utf-8 -*-
"""s62_manifest.py - manifest in the shape dedupe_gate.py expects."""
import csv, json, os, re
S = r"D:\毕业论文-短语框架人机对比\11_语料重建_2026-11"
M = os.path.join(S, "定稿_人类语料_合并_2026-11-16")

gate = {json.loads(l)["sha1"]: json.loads(l) for l in open(os.path.join(S, "R4_llm_all", "gate.jsonl"), encoding="utf-8")}
led = {r["sha1"]: r for r in csv.DictReader(open(os.path.join(S, "R11_新增PDF_OA_2026-11-16", "download_ledger.csv"), encoding="utf-8-sig"))}
rows = list(csv.DictReader(open(os.path.join(M, "00_清单_合并.csv"), encoding="utf-8-sig")))

def title_from_rel(rel):
    base = os.path.splitext(os.path.basename(rel))[0]
    base = re.sub(r"[_\s]*(19|20)\d\d$", "", base)
    base = base.replace("__", ": ").replace("_", " ").strip()
    return re.sub(r"\s+", " ", base)

out = []
for r in rows:
    sha = r["sha1"]
    g = gate.get(sha, {})
    l = led.get(sha, {})
    out.append(dict(no=r["id"], code=r["journal"], year=r["year"],
                    title=l.get("title") or title_from_rel(g.get("rel_path", "")),
                    doi=l.get("doi", ""), sha1=sha, first_author=l.get("author", ""),
                    words=r["words"], pdf=(l.get("file") or g.get("rel_path", "")), txt=r["txt"]))
p = os.path.join(M, "manifest_merge.csv")
with open(p, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
print("wrote", p, len(out))
