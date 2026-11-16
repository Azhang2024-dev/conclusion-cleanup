# -*- coding: utf-8 -*-
"""compare_prompts.py — simple prompt vs complex prompt, same articles, same temperature.

    python tools/compare_prompts.py --stage PATH --docs SHA1 SHA2 --prompts prompt_simple.md prompt.md
"""
import os, sys, io, json, csv, argparse, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--stage", required=True)
ap.add_argument("--docs", nargs="+", required=True)
ap.add_argument("--prompts", nargs="+", default=["prompt_simple.md", "prompt.md"])
ap.add_argument("--runs", type=int, default=2)
ap.add_argument("--temperature", type=float, default=0.0)
a = ap.parse_args()

rows = []
for sha in a.docs:
    for pf in a.prompts:
        cmd = [sys.executable, os.path.join(HERE, "run_doc.py"), "--stage", a.stage, "--sha", sha,
               "--runs", str(a.runs), "--temperature", str(a.temperature), "--backend", "http",
               "--prompt-file", pf]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        spans, gates = [], []
        for line in (p.stdout or "").splitlines():
            if line.startswith("run") and "start=" in line:
                try:
                    spans.append("%s-%s" % (line.split("start=")[1].split()[0], line.split("end=")[1].split()[0]))
                except IndexError:
                    pass
                gates.append("PASS" if " PASS " in line else ("FAIL" if " FAIL " in line else "?"))
        rows.append({"sha1": sha[:8], "prompt": os.path.splitext(pf)[0], "spans": "|".join(spans),
                     "identical": "Y" if len(set(spans)) == 1 and len(spans) == a.runs else "N",
                     "gates": "|".join(gates)})
        print(rows[-1])
        if not spans:
            print("   stderr:", (p.stderr or "")[-300:])

out = os.path.join(a.stage, "R3_spanlocator", "prompt_compare.csv")
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["sha1", "prompt", "spans", "identical", "gates"])
    w.writeheader(); w.writerows(rows)
print("wrote", out)
