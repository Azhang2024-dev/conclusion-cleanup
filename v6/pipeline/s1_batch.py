# -*- coding: utf-8 -*-
"""s1_batch.py - run the span-locator prompt over every frozen line log.

Direct HTTP is the only path that carries temperature, so this is the primary
engine. Each doc is independent; failures are recorded and the loop moves on so
a top-up or a network hiccup resumes instead of restarting.

    set DEEPSEEK_API_KEY=... ; python s1_batch.py --tag cplx --workers 8
"""
import os, sys, io, json, re, time, hashlib, argparse, threading, urllib.request, urllib.error
import concurrent.futures as cf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.dirname(HERE)
SKILL = os.path.join(STAGE, "_skill_repo", "span-locator")
API = "https://api.deepseek.com/chat/completions"
LOCK = threading.Lock()


def load_prompt(name):
    for base in (SKILL, STAGE):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return open(p, encoding="utf-8").read(), p
    raise SystemExit("prompt not found: " + name)


def build_input(sha):
    p = os.path.join(STAGE, "A_lines", sha + ".jsonl")
    objs = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    return "\n".join("L%d | %s" % (o["i"], o["text"]) for o in objs), len(objs)


def parse_json(s):
    pats = [r"\{[^{}]*\"end_line\"[^{}]*\}", r"\{.*\"end_line\".*\}", r"\{.*?\}"]
    for pat in pats:
        for cand in reversed(re.findall(pat, s or "", re.S)):
            try:
                o = json.loads(cand)
            except Exception:
                continue
            if isinstance(o, dict) and "end_line" in o:
                return o
    return None


def post(body, key, timeout=900):
    req = urllib.request.Request(
        API, json.dumps(body).encode("utf-8"),
        {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.loads(r.read().decode("utf-8"))
    return raw, round(time.time() - t0, 1)


def one(sha, args, prompt_text, key):
    outdir = os.path.join(args.out, sha)
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.join(outdir, "%s_t%s_run%d" % (args.tag, str(args.temperature).replace(".", "p"), args.run))
    if os.path.exists(stem + ".json") and not args.force:
        return sha, "skip", None
    text, n = build_input(sha)
    prompt = prompt_text + "\n\n[\u6587\u7ae0\u884c\u6d41\uff0c\u5171 %d \u884c]\n%s\n\n\u53ea\u8f93\u51fa JSON\u3002" % (n, text)
    fp = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    body = {"model": args.model, "temperature": args.temperature,
            "max_tokens": args.max_tokens, "stream": False,
            "messages": [{"role": "user", "content": prompt}]}
    last = ""
    for attempt in range(args.retries):
        try:
            raw, secs = post(body, key)
            content = raw["choices"][0]["message"]["content"]
            usage = raw.get("usage") or {}
            res = parse_json(content)
            if not res:
                last = "parse:" + (content or "")[-200:]
                time.sleep(2 * (attempt + 1))
                continue
            res.update({"sha1": sha, "prompt_sha256": fp, "backend": "http", "model": args.model,
                        "temperature": args.temperature, "seed": None, "usage": usage,
                        "prompt_file": args.prompt_file, "latency_s": secs,
                        "run": args.run, "tag": args.tag, "n_lines": n})
            with open(stem + ".json", "w", encoding="utf-8") as fh:
                json.dump(res, fh, ensure_ascii=False, indent=1)
            return sha, "ok", res
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            last = "http%d:%s" % (e.code, msg)
            if e.code in (400, 401, 402, 403):
                break
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            last = "exc:" + repr(e)[:200]
            time.sleep(3 * (attempt + 1))
    with open(stem + ".error.txt", "w", encoding="utf-8") as fh:
        fh.write(last)
    return sha, "fail", last


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(STAGE, "R4_llm_all"))
    ap.add_argument("--tag", default="cplx")
    ap.add_argument("--prompt-file", default="prompt.md")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shas", default="")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY missing")
    prompt_text, prompt_path = load_prompt(a.prompt_file)
    all_sha = sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(STAGE, "A_lines")) if f.endswith(".jsonl"))
    if a.shas:
        want = set(x.strip() for x in open(a.shas, encoding="utf-8").read().split() if x.strip())
        all_sha = [s for s in all_sha if s in want or s[:8] in want]
    if a.limit:
        all_sha = all_sha[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    print("prompt=%s docs=%d model=%s T=%s workers=%d run=%d" % (
        prompt_path, len(all_sha), a.model, a.temperature, a.workers, a.run), flush=True)

    t0 = time.time()
    done = {"ok": 0, "fail": 0, "skip": 0}
    tin = tout = 0
    fails = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(one, s, a, prompt_text, key): s for s in all_sha}
        for k, fut in enumerate(cf.as_completed(futs), 1):
            sha, status, info = fut.result()
            with LOCK:
                done[status] += 1
                if status == "fail":
                    fails.append((sha, info))
                if status == "ok" and info:
                    u = info.get("usage") or {}
                    tin += u.get("prompt_tokens", 0)
                    tout += u.get("completion_tokens", 0)
                    span = "%s..%s" % (info.get("start_line"), info.get("end_line"))
                else:
                    span = "-"
            if k % 25 == 0 or k == len(all_sha):
                el = time.time() - t0
                print("[%d/%d] %.1fs ok=%d fail=%d skip=%d in=%d out=%d last=%s %s" % (
                    k, len(all_sha), el, done["ok"], done["fail"], done["skip"], tin, tout, status, span), flush=True)
    print("DONE %.1fs %s" % (time.time() - t0, json.dumps(done, ensure_ascii=False)), flush=True)
    if fails:
        print("FAILED %d" % len(fails), flush=True)
        for sha, info in fails[:20]:
            print("  " + sha[:8] + " " + str(info)[:160], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
