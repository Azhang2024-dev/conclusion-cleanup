# -*- coding: utf-8 -*-
"""probe_oa_hosts.py - split OA pdf links into publisher-hosted vs repository-hosted.

The distinction decides how they can be fetched: repository copies answer a plain
GET, publisher copies answer 403 unless a browser session or campus entitlement
is behind the request.
"""
import json, time, urllib.request, urllib.parse, csv, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", line_buffering=True)
MAIL = "corpus@example.org"
PUB = ("sciencedirect", "wiley", "oup.com", "cambridge", "degruyter", "jbe-platform",
       "tandfonline", "springer", "elsevier", "brill", "sagepub", "benjamins")
J = [("Journal of Pragmatics","0378-2166"),("Language Learning","0023-8333"),
     ("Applied Linguistics","0142-6001"),("Cognitive Linguistics","0936-5907"),
     ("IJCL","1384-6655"),("JEAP","1475-1585"),("English for Specific Purposes","0889-4906"),
     ("Journal of Semantics","0167-5133"),("Language Teaching","0261-4448"),("TESOL Quarterly","0039-8322")]

def get(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url + ("&" if "?" in url else "?") + "mailto=" + MAIL,
                                         headers={"User-Agent": "probe/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == 2: raise
            time.sleep(2)

rows = []
for name, issn in J:
    sid = get("https://api.openalex.org/sources/issn:" + issn)["id"].rsplit("/", 1)[-1]
    page = get("https://api.openalex.org/works?filter=primary_location.source.id:%s,"
               "from_publication_date:2016-01-01,to_publication_date:2026-12-31,"
               "open_access.is_oa:true&per-page=200&select=doi,best_oa_location" % sid)
    pub = repo = 0
    for w in page["results"]:
        loc = w.get("best_oa_location") or {}
        u = loc.get("pdf_url")
        if not u: continue
        if any(k in u for k in PUB): pub += 1
        else: repo += 1
    n = pub + repo
    rows.append(dict(journal=name, issn=issn, with_pdf=n, publisher_hosted=pub, repository=repo,
                     repo_pct=round(repo/n*100,1) if n else 0))
    print("%-40s pdf=%3d publisher=%3d repo=%3d (%.0f%% repo)" % (name, n, pub, repo, rows[-1]["repo_pct"]))
    time.sleep(0.3)

out = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "R10_取源", "oa_host_split.csv"))
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("wrote", out)
print("TOTAL pdf=%d publisher=%d repo=%d" % (sum(r["with_pdf"] for r in rows),
      sum(r["publisher_hosted"] for r in rows), sum(r["repository"] for r in rows)))
