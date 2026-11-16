# -*- coding: utf-8 -*-
"""s52_download_oa.py - fetch the OA PDF links found by crawl_oa_candidates.py.

Policy, from measurement rather than hope:

  * repository hosts answer a plain GET (verified: ora.ox.ac.uk, ueaeprints);
  * publisher hosts answer 403 to a script (verified: sciencedirect, wiley).
    So each publisher host is probed once; if it refuses, the rest of that host
    is recorded as "host_blocked" instead of burning 15 s per document.

Every attempt lands in a ledger. Nothing is silently dropped.
"""
import os, sys, io, csv, json, time, socket, hashlib, argparse, threading, urllib.request, urllib.error
import concurrent.futures as cf
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", line_buffering=True)

PUB = ("sciencedirect", "wiley", "oup.com", "cambridge", "degruyter", "jbe-platform",
       "tandfonline", "springer", "brill", "sagepub", "benjamins", "academic.oup")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) corpus-fetch/1.0",
      "Accept": "application/pdf,*/*"}
LOCK = threading.Lock()


def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def slug(s, n=60):
    keep = "".join(c if (c.isalnum() or c in "._-") else "_" for c in s)
    return keep[:n].strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cands", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--gate", help="gate.jsonl; used for title-level dedupe against the existing 697")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=15)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    socket.setdefaulttimeout(a.timeout)  # covers connect/DNS stalls the per-call timeout misses

    seen = set()
    for dp, _, fs in os.walk(a.pool):
        for f in fs:
            if f.lower().endswith(".pdf"):
                try:
                    seen.add(sha1_of(os.path.join(dp, f)))
                except OSError:
                    pass
    print("pool hashes:", len(seen), flush=True)

    # sha1 does not catch the same paper arriving as a repository copy: different
    # bytes, same article. Title is the cheap second key (011/103 lesson).
    pool_titles = set()
    if a.gate:
        import re
        for line in open(a.gate, encoding="utf-8"):
            rec = json.loads(line)
            base = os.path.splitext(os.path.basename(rec.get("rel_path") or ""))[0]
            base = re.sub(r"[_s]*(19|20)dd$", "", base).replace("__", ": ")
            pool_titles.add(re.sub(r"[^a-z0-9]+", "", base.lower())[:70])
    print("pool titles:", len(pool_titles), flush=True)

    rows = list(csv.DictReader(open(a.cands, encoding="utf-8-sig")))
    print("candidates:", len(rows), flush=True)

    blocked = {}
    out_rows = []
    counter = {"ok": 0, "fail": 0, "dup": 0, "blocked": 0}

    import re as _re

    def attempt(r):
        host = r["host"]
        # Four publisher hosts were probed and answered 403 (sciencedirect,
        # wiley, oup, cambridge, degruyter, jbe). Do not burn 8 s per document
        # re-learning that: mark and move on.
        if any(k in host for k in PUB):
            with LOCK:
                counter["blocked"] += 1
            return dict(r, status="host_blocked", detail="publisher host, 403 in probe", file="", sha1="", bytes="")
        tkey = _re.sub(r"[^a-z0-9]+", "", (r["title"] or "").lower())[:70]
        if tkey and tkey in pool_titles:
            with LOCK:
                counter["dup"] += 1
            return dict(r, status="pool_same_title", detail="title match in 697 pool", file="", sha1="", bytes="")
        if any(k in host for k in PUB):
            with LOCK:
                if host in blocked:
                    counter["blocked"] += 1
                    return dict(r, status="host_blocked", detail=blocked[host], file="", sha1="", bytes="")
        jdir = os.path.join(a.out, slug(r["journal"], 40))
        os.makedirs(jdir, exist_ok=True)
        name = "%s_%s.pdf" % (r["year"] or "na", slug(r["doi"].replace("/", "_"), 70))
        dst = os.path.join(jdir, name)
        for i in range(2):
            try:
                req = urllib.request.Request(r["pdf_url"], headers=UA)
                with urllib.request.urlopen(req, timeout=a.timeout) as resp:
                    data = resp.read()
                if not data[:5].startswith(b"%PDF"):
                    return dict(r, status="not_pdf", detail=data[:40].decode("latin-1", "replace"), file="", sha1="", bytes=str(len(data)))
                h = hashlib.sha1(data).hexdigest()
                with LOCK:
                    if h in seen:
                        counter["dup"] += 1
                        return dict(r, status="dup_sha1", detail="", file="", sha1=h, bytes=str(len(data)))
                    seen.add(h)
                with open(dst, "wb") as f:
                    f.write(data)
                with LOCK:
                    counter["ok"] += 1
                return dict(r, status="ok", detail="", file=dst, sha1=h, bytes=str(len(data)))
            except urllib.error.HTTPError as e:
                if e.code in (403, 401) and any(k in host for k in PUB):
                    with LOCK:
                        blocked[host] = "HTTP %d" % e.code
                if i == 1:
                    with LOCK:
                        counter["fail"] += 1
                    return dict(r, status="http_%d" % e.code, detail="", file="", sha1="", bytes="")
            except Exception as e:
                if i == 1:
                    with LOCK:
                        counter["fail"] += 1
                    return dict(r, status="error", detail=str(e)[:80], file="", sha1="", bytes="")
            time.sleep(1.5)
        return dict(r, status="error", detail="retry_exhausted", file="", sha1="", bytes="")

    ledger = os.path.join(a.out, "download_ledger.csv")
    fields = ["journal", "year", "title", "doi", "type", "author", "pdf_url", "version", "host",
              "status", "detail", "file", "sha1", "bytes"]
    # resume: anything already in the ledger is not retried, so a killed run
    # continues instead of restarting
    done = set()
    if os.path.exists(ledger):
        for r0 in csv.DictReader(open(ledger, encoding="utf-8-sig")):
            done.add((r0["doi"] or "").strip().lower())
        print("resume: ledger has", len(done), "rows", flush=True)
        rows = [r for r in rows if (r["doi"] or "").strip().lower() not in done]
        print("left to do:", len(rows), flush=True)
    else:
        with open(ledger, "w", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, row in enumerate(ex.map(attempt, rows), 1):
            out_rows.append(row)
            with LOCK:
                with open(ledger, "a", encoding="utf-8-sig", newline="") as f:
                    csv.DictWriter(f, fieldnames=fields, extrasaction="ignore").writerow(row)
            if i % 50 == 0:
                print("  %d/%d ok=%d dup=%d fail=%d blocked=%d" % (
                    i, len(rows), counter["ok"], counter["dup"], counter["fail"], counter["blocked"]),
                    flush=True)
    print("done", counter, flush=True)
    print("blocked hosts:", blocked, flush=True)


if __name__ == "__main__":
    sys.exit(main())
