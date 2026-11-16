# -*- coding: utf-8 -*-
"""crawl_oa2.py - OA works with PDF links, offset pagination, progress to stdout."""
import json, time, urllib.request, urllib.parse, csv, os, sys
MAIL = os.environ.get("OPENALEX_MAILTO", "corpus@example.org")
J = [("TESOL Quarterly","0039-8322"),("Language teaching","0261-4448"),
     ("Journal of semantics","0167-5133"),("IJCL","1384-6655"),("Journal of ESP","0889-4906"),
     ("Journal of EAP","1475-1585"),("Cognitive linguistics","0936-5907"),
     ("Applied linguistics","0142-6001"),("Language learning","0023-8333"),
     ("Journal of Pragmatics","0378-2166")]

def get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url + ("&" if "?" in url else "?") + "mailto=" + MAIL,
                                         headers={"User-Agent": "corpus-crawl/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e; time.sleep(2 + 2 * i)
    raise last

rows = []
for label, issn in J:
    try:
        sid = get("https://api.openalex.org/sources/issn:" + issn)["id"].rsplit("/", 1)[-1]
        got = 0
        for page in range(1, 6):
            u = ("https://api.openalex.org/works?filter=primary_location.source.id:%s,"
                 "from_publication_date:2016-01-01,to_publication_date:2026-12-31,"
                 "open_access.is_oa:true&per-page=200&page=%d&sort=publication_date:desc"
                 % (sid, page))
            w = get(u)
            if not w["results"]:
                break
            for it in w["results"]:
                loc = it.get("best_oa_location") or {}
                pdf = loc.get("pdf_url")
                if not pdf:
                    continue
                auth = ""
                for a in (it.get("authorships") or []):
                    if a.get("author", {}).get("display_name"):
                        auth = a["author"]["display_name"]; break
                rows.append(dict(journal=label, issn=issn, year=it.get("publication_year") or "",
                                 title=(it.get("title") or "").replace("\n", " ")[:300],
                                 doi=(it.get("doi") or "").replace("https://doi.org/", "").lower(),
                                 type=it.get("type") or "", author=auth, pdf_url=pdf,
                                 version=loc.get("version") or "",
                                 host=urllib.parse.urlsplit(pdf).netloc))
                got += 1
            print("  page", page, "cum", got, flush=True)
            if len(w["results"]) < 200:
                break
            time.sleep(0.6)
        print(label, "->", got, flush=True)
    except Exception as e:
        print("FAIL", label, str(e)[:100], flush=True)
    time.sleep(0.5)

out = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "R10_取源", "oa_candidates_all.csv"))
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=["journal","issn","year","title","doi","type","author","pdf_url","version","host"])
    wr.writeheader(); wr.writerows(rows)
print("TOTAL", len(rows), out, flush=True)
