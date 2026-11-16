# -*- coding: utf-8 -*-
"""s54_repo_pass.py - bounded pass over repository-hosted links only.

Publisher hosts answered 403 in probing, so they are excluded here rather than
retried 1,500 times. Everything attempted lands in the shared ledger; anything
not attempted stays out of it and is marked downstream as '未尝试'.
"""
import os, sys, io, csv, json, time, socket, hashlib, argparse, threading, urllib.request, urllib.error, re
import concurrent.futures as cf
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", line_buffering=True)

PUB = ("sciencedirect", "wiley", "oup.com", "cambridge", "degruyter", "jbe-platform",
       "tandfonline", "springer", "brill", "sagepub", "benjamins", "academic.oup")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) corpus-fetch/1.0", "Accept": "application/pdf,*/*"}
LOCK = threading.Lock()
FIELDS = ["journal", "year", "title", "doi", "type", "author", "pdf_url", "version", "host",
          "status", "detail", "file", "sha1", "bytes"]


def slug(s, n=60):
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in s)[:n].strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cands", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--timeout", type=int, default=8)
    ap.add_argument("--budget", type=int, default=3600)
    a = ap.parse_args()
    socket.setdefaulttimeout(a.timeout)
    os.makedirs(a.out, exist_ok=True)
    ledger = os.path.join(a.out, "download_ledger.csv")

    done = set()
    if os.path.exists(ledger):
        for r in csv.DictReader(open(ledger, encoding="utf-8-sig")):
            done.add((r["doi"] or "").strip().lower())
    pool_titles = set()
    for line in open(a.gate, encoding="utf-8"):
        rec = json.loads(line)
        base = os.path.splitext(os.path.basename(rec.get("rel_path") or ""))[0]
        base = re.sub(r"[_\s]*(19|20)\d\d$", "", base).replace("__", ": ")
        pool_titles.add(re.sub(r"[^a-z0-9]+", "", base.lower())[:70])

    rows = [r for r in csv.DictReader(open(a.cands, encoding="utf-8-sig"))
            if (r["doi"] or "").lower() not in done and not any(k in r["host"] for k in PUB)]
    print("repo candidates to try:", len(rows), flush=True)
    cnt = {"ok": 0, "dup": 0, "fail": 0}

    def attempt(r):
        tkey = re.sub(r"[^a-z0-9]+", "", (r["title"] or "").lower())[:70]
        if tkey and tkey in pool_titles:
            return dict(r, status="pool_same_title", detail="title match", file="", sha1="", bytes="")
        jdir = os.path.join(a.out, slug(r["journal"], 40))
        os.makedirs(jdir, exist_ok=True)
        dst = os.path.join(jdir, "%s_%s.pdf" % (r["year"] or "na", slug(r["doi"].replace("/", "_"), 70)))
        try:
            req = urllib.request.Request(r["pdf_url"], headers=UA)
            with urllib.request.urlopen(req, timeout=a.timeout) as resp:
                data = resp.read()
            if not data[:5].startswith(b"%PDF"):
                return dict(r, status="not_pdf", detail="", file="", sha1="", bytes=str(len(data)))
            h = hashlib.sha1(data).hexdigest()
            with open(dst, "wb") as f:
                f.write(data)
            with LOCK:
                cnt["ok"] += 1
            return dict(r, status="ok", detail="", file=dst, sha1=h, bytes=str(len(data)))
        except urllib.error.HTTPError as e:
            with LOCK:
                cnt["fail"] += 1
            return dict(r, status="http_%d" % e.code, detail="", file="", sha1="", bytes="")
        except Exception as e:
            with LOCK:
                cnt["fail"] += 1
            return dict(r, status="error", detail=str(e)[:60], file="", sha1="", bytes="")

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(attempt, r): r for r in rows}
        for i, fu in enumerate(cf.as_completed(futs, timeout=a.budget), 1):
            try:
                row = fu.result(timeout=1)
            except Exception:
                continue
            with open(ledger, "a", encoding="utf-8-sig", newline="") as f:
                csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore").writerow(row)
            if i % 20 == 0:
                print("  %d/%d ok=%d fail=%d  %.0fs" % (i, len(rows), cnt["ok"], cnt["fail"], time.time() - t0), flush=True)
    print("done", cnt, "%.0fs" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    sys.exit(main())
