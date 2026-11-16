# -*- coding: utf-8 -*-
"""sweep.py — does temperature move the answer?

Two questions at once:
  1  at T=0, does the same prompt give the same span twice?
  2  at a higher T, does the span move?

If run-to-run at T=0 is identical and higher T agrees, one run per article is
enough. If T=0 is identical but higher T differs, the span has genuine ambiguity
in the source and that article needs a human look. If T=0 differs, the model is
not a reproducible instrument on this task and every article needs N runs.

    python tools/sweep.py --stage PATH --n 12 --temps 0 0.7 --runs 2
"""
import os, sys, io, json, csv, random, argparse, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--stage", required=True)
ap.add_argument("--n", type=int, default=12)
ap.add_argument("--runs", type=int, default=2)
ap.add_argument("--temps", nargs="+", type=float, default=[0.0, 0.7])
ap.add_argument("--backend", default="http")
ap.add_argument("--seed", type=int, default=None)
ap.add_argument("--gold", nargs="*", default=[])
a = ap.parse_args()

shas = sorted(f[:-6] for f in os.listdir(os.path.join(a.stage, "A_lines")) if f.endswith(".jsonl"))
random.seed(20261116)
sample = a.gold[:] + random.sample([s for s in shas if s not in set(a.gold)], max(0, a.n - len(a.gold)))
rows = []
for sha in sample:
    row = {"sha1": sha}
    for t in a.temps:
        cmd = [sys.executable, os.path.join(HERE, "run_doc.py"), "--stage", a.stage, "--sha", sha,
               "--runs", str(a.runs), "--backend", a.backend, "--temperature", str(t)]
        if a.seed is not None:
            cmd += ["--seed", str(a.seed)]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        spans = []
        for line in (p.stdout or "").splitlines():
            if line.startswith("run") and "start=" in line:
                try:
                    spans.append("%s-%s" % (line.split("start=")[1].split()[0],
                                            line.split("end=")[1].split()[0]))
                except IndexError:
                    pass
        row["T%s" % t] = "|".join(spans)
        row["T%s_ok" % t] = "Y" if len(spans) == a.runs and len(set(spans)) == 1 else "N"
    rows.append(row)
    print(sha[:8], {k: v for k, v in row.items() if k != "sha1"})

out = os.path.join(a.stage, "R3_spanlocator", "sweep.csv")
os.makedirs(os.path.dirname(out), exist_ok=True)
fields = ["sha1"] + [x for t in a.temps for x in ("T%s" % t, "T%s_ok" % t)]
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader(); w.writerows(rows)
ok = sum(1 for r in rows if all(r.get("T%s_ok" % t) == "Y" for t in a.temps))
print("篇数 %d | 全部温度点内一致的 %d | 输出 %s" % (len(rows), ok, out))
