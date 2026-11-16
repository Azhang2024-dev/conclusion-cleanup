# -*- coding: utf-8 -*-
"""probe_openalex2.py - lean version: counts + one-page pdf-link sample per journal."""
import json, time, urllib.request, urllib.parse, csv, os, sys, io, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace", line_buffering=True)
MAIL = "corpus@example.org"
J = [("Journal of Pragmatics","0378-2166"),("Language Learning","0023-8333"),
     ("Applied Linguistics","0142-6001"),("Cognitive Linguistics","0936-5907"),
     ("International Journal of Corpus Linguistics","1384-6655"),
     ("Journal of English for Academic Purposes","1475-1585"),
     ("English for Specific Purposes","0889-4906"),("Journal of Semantics","0167-5133"),
     ("Language Teaching","0261-4448"),("TESOL Quarterly","0039-8322")]

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url + ("&" if "?" in url else "?") + "mailto=" + MAIL,
                                         headers={"User-Agent": "corpus-probe/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2)

rows = []
for name, issn in J:
    try:
        src = get("https://api.openalex.org/sources/issn:" + issn)
        sid = src["id"].rsplit("/", 1)[-1]
        w = get("https://api.openalex.org/works?filter=primary_location.source.id:%s,from_publication_date:2016-01-01,to_publication_date:2026-12-31&per-page=1" % sid)["meta"]["count"]
        oa = get("https://api.openalex.org/works?filter=primary_location.source.id:%s,from_publication_date:2016-01-01,to_publication_date:2026-12-31,open_access.is_oa:true&per-page=1" % sid)["meta"]["count"]
        page = get("https://api.openalex.org/works?filter=primary_location.source.id:%s,from_publication_date:2016-01-01,to_publication_date:2026-12-31,open_access.is_oa:true&per-page=200&select=doi,best_oa_location,publication_year" % sid)
        n = len(page["results"]); pdf = 0; hosts = collections.Counter()
        for r0 in page["results"]:
            loc = r0.get("best_oa_location") or {}
            if loc.get("pdf_url"):
                pdf += 1
                hosts[urllib.parse.urlsplit(loc["pdf_url"]).netloc] += 1
        rows.append(dict(journal=name, issn=issn, works=w, oa=oa, oa_pct=round(oa/w*100,1) if w else 0,
                         sampled=n, pdf_in_sample=pdf,
                         pdf_pct_of_sample=round(pdf/n*100,1) if n else 0,
                         top_hosts="; ".join("%s(%d)"%(h,c) for h,c in hosts.most_common(3))))
        print("OK %-42s works=%5d oa=%4d (%4.1f%%) pdf %d/%d" % (name, w, oa, rows[-1]["oa_pct"], pdf, n))
    except Exception as e:
        rows.append(dict(journal=name, issn=issn, works=0, oa=0, oa_pct=0, sampled=0, pdf_in_sample=0, pdf_pct_of_sample=0, top_hosts="ERR " + str(e)[:80]))
        print("FAIL", name, str(e)[:90])
    time.sleep(0.4)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "R10_取源", "openalex_oa_probe.csv")
out = os.path.abspath(out)
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
print("wrote", out)
