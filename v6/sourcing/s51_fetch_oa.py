# -*- coding: utf-8 -*-
r"""s51_fetch_oa.py - pull open-access PDFs for a journal into the download pool.

Only touches openly available copies that a metadata API points at; nothing here
guesses URLs. Two rules learned the hard way:

  * dedupe by sha1 AND by DOI, because the same paper can arrive as a typeset
    PDF and an accepted manuscript with different bytes (the 011/103 pair);
  * record the OA version (published / accepted / submitted) next to the file,
    because an accepted manuscript has different wording and different line
    breaks -- it will break the "typeset page header" assumptions downstream.

    python s51_fetch_oa.py --issn 0378-2166 --limit 20 --dry-run
    python s51_fetch_oa.py --issn 0378-2166 --limit 200 --out ..\..\05_语料库\新增_OA
"""
import os, sys, io, json, csv, time, hashlib, argparse, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", line_buffering=True)
MAIL = os.environ.get("OPENALEX_MAILTO", "corpus@example.org")


def api(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url + ("&" if "?" in url else "?") + "mailto=" + MAIL,
                                         headers={"User-Agent": "corpus-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2)


def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def known_hashes(roots):
    seen = set()
    for root in roots:
        for dp, _, fs in os.walk(root):
            for f in fs:
                if f.lower().endswith(".pdf"):
                    try:
                        seen.add(sha1_of(os.path.join(dp, f)))
                    except OSError:
                        pass
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issn", required=True)
    ap.add_argument("--year-from", default="2016-01-01")
    ap.add_argument("--year-to", default="2026-12-31")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "R10_取源", "downloads"))
    ap.add_argument("--pool", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    seen_sha = known_hashes([os.path.abspath(p) for p in a.pool]) if a.pool else set()
    seen_doi = set()
    ledger_p = os.path.join(a.out, "download_ledger.csv")
    if os.path.exists(ledger_p):
        for row in csv.DictReader(open(ledger_p, encoding="utf-8-sig")):
            seen_doi.add(row["doi"].lower())

    src = api("https://api.openalex.org/sources/issn:" + a.issn)
    sid = src["id"].rsplit("/", 1)[-1]
    print("journal:", src["display_name"], "| issn", a.issn)

    rows, got = [], 0
    cursor = "*"
    while got < a.limit:
        page = api("https://api.openalex.org/works?filter=primary_location.source.id:%s,"
                   "from_publication_date:%s,to_publication_date:%s,open_access.is_oa:true"
                   "&per-page=200&cursor=%s&select=id,doi,title,publication_year,best_oa_location"
                   % (sid, a.year_from, a.year_to, urllib.parse.quote(cursor)))
        if not page["results"]:
            break
        for w in page["results"]:
            if got >= a.limit:
                break
            loc = w.get("best_oa_location") or {}
            pdf = loc.get("pdf_url")
            doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            if not pdf or not doi or doi in seen_doi:
                continue
            tag = "%s_%s" % ((w.get("publication_year") or "na"), doi.replace("/", "_"))
            dst = os.path.join(a.out, tag + ".pdf")
            row = dict(doi=doi, year=w.get("publication_year"), title=(w.get("title") or "")[:120],
                       pdf_url=pdf, version=loc.get("version") or "", host=urllib.parse.urlsplit(pdf).netloc,
                       file="" if a.dry_run else dst, sha1="", words="", status="")
            if a.dry_run:
                row["status"] = "dry"
                rows.append(row); got += 1
                print("  [dry] %-6s %-40s %s" % (row["year"], doi, row["host"]))
                continue
            try:
                req = urllib.request.Request(pdf, headers={"User-Agent": "Mozilla/5.0 corpus-fetch"})
                # 25 s, not 60: publisher links that need a session cookie hang, and
                # one hung host must not stall a 200-document run.
                with urllib.request.urlopen(req, timeout=25) as r, open(dst, "wb") as f:
                    f.write(r.read())
                h = sha1_of(dst)
                if h in seen_sha:
                    os.remove(dst); row["status"] = "dup_sha1"; rows.append(row); continue
                with open(dst, "rb") as f:
                    if not f.read(5).startswith(b"%PDF"):
                        os.remove(dst); row["status"] = "not_pdf"; rows.append(row); continue
                seen_sha.add(h); seen_doi.add(doi)
                row["sha1"] = h; row["status"] = "ok"
                rows.append(row); got += 1
                print("  ok %-6s %-40s %s" % (row["year"], doi, h[:8]))
            except Exception as e:
                row["status"] = "download_fail: " + str(e)[:60]
                rows.append(row)
                print("  fail %-6s %-40s %s" % (row["year"], doi, str(e)[:50]))
            time.sleep(0.3)
        cursor = page["meta"].get("next_cursor")
        if not cursor:
            break

    write_head = not os.path.exists(ledger_p)
    with open(ledger_p, "a", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["doi", "year", "title", "pdf_url", "version", "host", "file", "sha1", "words", "status"])
        if write_head:
            wr.writeheader()
        wr.writerows(rows)
    print("rows", len(rows), "| ledger", ledger_p)


if __name__ == "__main__":
    sys.exit(main())
