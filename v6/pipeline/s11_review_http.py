# -*- coding: utf-8 -*-
"""s11_review_http.py - run a review packet as one completion instead of an agent.

The headless agent path needs its own credential; the direct API key does not.
For a structured verdict over a fixed packet, one call is enough and it is
cheaper, so this is the fallback when the agent path runs out of balance.

    set DEEPSEEK_API_KEY=... ; python s11_review_http.py --tags C03 C04
"""
import os, sys, io, json, time, argparse, urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
REV = os.path.join(STAGE, "R5_review")
API = "https://api.deepseek.com/chat/completions"

SYS = "You are a meticulous corpus-linguistics reviewer. Follow the task file exactly and output only the TSV."


def post(body, key, timeout=900):
    req = urllib.request.Request(API, json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--max-tokens", type=int, default=4000)
    a = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SystemExit("no key")
    for tag in a.tags:
        task = open(os.path.join(REV, "tasks", "task_%s.txt" % tag), encoding="utf-8-sig").read()
        pkt = open(os.path.join(REV, "tasks", "packet_%s.md" % tag), encoding="utf-8").read()
        prompt = task + "\n\n" + pkt + "\n\nNow output only the TSV rows (header + one row per article), tab separated."
        body = {"model": a.model, "temperature": 0, "max_tokens": a.max_tokens, "stream": False,
                "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]}
        for attempt in range(3):
            try:
                raw = post(body, key)
                txt = raw["choices"][0]["message"]["content"]
                break
            except Exception as e:
                print(tag, "retry", repr(e)[:120], flush=True)
                txt = None
                time.sleep(3)
        if not txt:
            print(tag, "FAILED", flush=True)
            continue
        lines = [l for l in txt.splitlines() if "\t" in l]
        if not lines or "id" not in lines[0]:
            lines = ["id\tB1\u8d77\u70b9\tB2\u7ec8\u70b9\tB3\u4e22\u5931\tB4\u6df7\u5165\tB5\u6539\u5b57\t\u7ed3\u8bba\t\u8bf4\u660e"] + lines
        out = os.path.join(REV, "out", "%s.tsv" % tag)
        open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print(tag, "rows=%d" % (len(lines) - 1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
