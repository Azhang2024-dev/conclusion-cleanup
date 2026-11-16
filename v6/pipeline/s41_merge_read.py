# -*- coding: utf-8 -*-
"""s41_merge_read.py - collapse the per-batch verdict files into one ledger."""
import os, sys, io, glob, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
OUT = os.path.join(STAGE, "R7_fullread")
rows, seen = [], set()
for f in sorted(glob.glob(os.path.join(OUT, "b*.tsv"))):
    for line in open(f, encoding="utf-8").read().splitlines()[1:]:
        if not line.strip():
            continue
        c = line.split("\t")
        if c[0] in seen:
            continue
        seen.add(c[0])
        rows.append(c)
p = os.path.join(OUT, "fullread.tsv")
with open(p, "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh, delimiter="\t")
    w.writerow(["id", "verdict", "note"])
    w.writerows(rows)
from collections import Counter
print("ledger rows=%d  verdict=%s" % (len(rows), dict(Counter(r[1] for r in rows))))
print("remaining to read:", 483 - len(seen))
