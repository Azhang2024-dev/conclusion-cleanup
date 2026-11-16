# -*- coding: utf-8 -*-
"""determinism.py — does the same prompt give the same span twice?

Runs every sampled article R times through the same prompt and reports, per
article, whether start_line and end_line are bit-identical across runs.

    python tools/determinism.py --stage PATH --n 40 --runs 3 --backend http
"""
import os, sys, io, json, csv, random, argparse, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--stage", required=True)
ap.add_argument("--n", type=int, default=40)
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("--backend", default="http", choices=["http", "dsh"])
ap.add_argument("--seed", type=int, default=20261116)
a = ap.parse_args()

shas = sorted(f[:-6] for f in os.listdir(os.path.join(a.stage, "A_lines")) if f.endswith(".jsonl"))
random.seed(a.seed)
sample = random.sample(shas, min(a.n, len(shas)))
rows = []
for sha in sample:
    p = subprocess.run([sys.executable, os.path.join(HERE, "run_doc.py"), "--stage", a.stage,
                        "--sha", sha, "--runs", str(a.runs), "--backend", a.backend],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    sp = []
    for line in (p.stdout or "").splitlines():
        if line.startswith("run") and "start=" in line:
            try:
                sp.append(line.split("start=")[1].split()[0] + "-" + line.split("end=")[1].split()[0])
            except IndexError:
                pass
    ok = len(set(sp)) == 1 and len(sp) == a.runs
    rows.append({"sha1": sha, "spans": "|".join(sp), "identical": "Y" if ok else "N"})
    print("%s %s %s" % (sha[:8], "一致" if ok else "不一致", sp))

with open(os.path.join(a.stage, "R3_spanlocator", "determinism.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["sha1", "spans", "identical"])
    w.writeheader(); w.writerows(rows)
good = sum(1 for r in rows if r["identical"] == "Y")
print("一致 %d / %d = %.1f%%" % (good, len(rows), 100.0 * good / max(1, len(rows))))
