# -*- coding: utf-8 -*-
"""append_missing_journal.py - fetch one journal's OA links and append to the crawl CSV."""
import json, csv, sys, os, time, urllib.request, urllib.parse
MAIL = os.environ.get("OPENALEX_MAILTO", "corpus@example.org")
label, issn = "Cognitive linguistics", "0936-5907"
CSV = r"D:\毕业论文-短语框架人机对比\11_语料重建_2026-11\R10_取源\oa_candidates_all.csv"

def get(u, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(u + "&mailto=" + MAIL, headers={"User-Agent": "corpus-crawl/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(3 + 3 * i)

sid = get("https://api.openalex.org/sources/issn:%s?" % issn)["id"].rsplit("/", 1)[-1]
rows = []
for page in (1, 2, 3):
    w = get("https://api.openalex.org/works?filter=primary_location.source.id:%s,"
            "from_publication_date:2016-01-01,to_publication_date:2026-12-31,"
            "open_access.is_oa:true&per-page=200&page=%d&sort=publication_date:desc" % (sid, page))
    if not w["results"]: break
    for it in w["results"]:
        loc = it.get("best_oa_location") or {}
        if not loc.get("pdf_url"): continue
        auth = ""
        for a in (it.get("authorships") or []):
            if a.get("author", {}).get("display_name"):
                auth = a["author"]["display_name"]; break
        rows.append(dict(journal=label, issn=issn, year=it.get("publication_year") or "",
                         title=(it.get("title") or "").replace("\n"," ")[:300],
                         doi=(it.get("doi") or "").replace("https://doi.org/","").lower(),
                         type=it.get("type") or "", author=auth, pdf_url=loc["pdf_url"],
                         version=loc.get("version") or "", host=urllib.parse.urlsplit(loc["pdf_url"]).netloc))
    if len(w["results"]) < 200: break
    time.sleep(1)

existing = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
seen = {r["doi"] for r in existing}
new = [r for r in rows if r["doi"] not in seen]
with open(CSV, "a", encoding="utf-8-sig", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(existing[0].keys()))
    wr.writerows(new)
print("CL rows", len(rows), "appended", len(new), "| total now", len(existing) + len(new))
