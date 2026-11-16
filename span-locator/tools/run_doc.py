# -*- coding: utf-8 -*-
"""run_doc.py — one article, N runs, temperature under your control.

Direct HTTP is the primary path: only it can carry a temperature parameter.
The dsh headless profile cannot (its provider declares supportsTemperature:
false), so it is kept as a fallback that always runs at the server default.

Every run records what it was: prompt fingerprint, model, temperature, token
usage, latency. A run that fails on balance or network writes an .error file and
the loop moves on, so a top-up resumes instead of restarting.

    python tools/run_doc.py --stage PATH --sha SHA --runs 2 --temperature 0
    python tools/run_doc.py --stage PATH --sha SHA --dry
"""
import os, sys, io, json, re, time, hashlib, argparse, subprocess, urllib.request, urllib.error
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTDIR = os.path.dirname(HERE)
def load_prompt(name):
    return open(os.path.join(PROMPTDIR, name), encoding="utf-8").read()
API = "https://api.deepseek.com/chat/completions"

def build_input(stage, sha):
    alog = [json.loads(l) for l in open(os.path.join(stage, "A_lines", sha + ".jsonl"), encoding="utf-8") if l.strip()]
    return "\n".join("L%d | %s" % (o["i"], o["text"]) for o in alog), len(alog)

def fingerprint(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def post(body, key, timeout=1800):
    req = urllib.request.Request(API, json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.loads(r.read().decode("utf-8"))
    return raw, round(time.time() - t0, 1)

def ask_dsh(prompt, workdir):
    """Fallback path.

    Two constraints force a file-based task: Windows caps a command line at
    32,767 characters and a full-article prompt is roughly twice that, and
    Python cannot execute the dsh.ps1 shim directly. So the prompt is written
    to disk and a one-line ASCII task points at it. This runs an agent loop, not
    a single completion, so its variance is higher than the HTTP path.
    """
    os.makedirs(workdir, exist_ok=True)
    pf = os.path.join(workdir, "prompt.txt")
    open(pf, "w", encoding="utf-8").write(prompt)
    task = ("Read the task file at %s and carry it out exactly. "
            "It contains the instructions and the article. Reply with only the JSON "
            "it asks for, no explanation." % pf.replace("\\", "\\\\"))
    launcher = os.path.join(workdir, "launch.ps1")
    open(launcher, "w", encoding="utf-8-sig").write(
        "$env:NO_COLOR='1'\ndsh --profile headless \"%s\" *>&1 | Out-String\n" % task)
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", launcher],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    return (p.stdout or ""), {}

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

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--backend", default="http", choices=["http", "dsh"])
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--prompt-file", default="prompt.md")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)

    text, n = build_input(a.stage, a.sha)
    prompt = load_prompt(a.prompt_file) + "\n\n[文章行流，共 %d 行]\n%s\n\n只输出 JSON。" % (n, text)
    fp = fingerprint(prompt)
    body = {"model": a.model, "temperature": a.temperature, "max_tokens": a.max_tokens,
            "stream": False, "messages": [{"role": "user", "content": prompt}]}
    if a.seed is not None:
        body["seed"] = a.seed

    if a.dry:
        slim = dict(body)
        slim["messages"] = [{"role": "user", "content": prompt[:160] + " ...(%d chars)" % len(prompt)}]
        print(json.dumps(slim, ensure_ascii=False, indent=1))
        print("prompt_sha256=%s chars=%d lines=%d" % (fp, len(prompt), n))
        return 0

    outdir = os.path.join(a.stage, "R3_spanlocator", a.sha)
    os.makedirs(outdir, exist_ok=True)
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    spans = []
    for k in range(1, a.runs + 1):
        tag = os.path.splitext(a.prompt_file)[0]
        stem = os.path.join(outdir, "%s_t%s_run%d" % (tag, str(a.temperature).replace(".", "p"), k))
        try:
            if a.backend == "http":
                if not key:
                    raise RuntimeError("没有 DEEPSEEK_API_KEY")
                raw, secs = post(body, key)
                content = raw["choices"][0]["message"]["content"]
                usage = raw.get("usage") or {}
            else:
                content, usage = ask_dsh(prompt, outdir)
                secs = None
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            open(stem + ".error.txt", "w", encoding="utf-8").write("HTTP %s %s" % (e.code, msg))
            print("run%d HTTP %s %s" % (k, e.code, msg[:120]))
            continue
        except Exception as e:
            open(stem + ".error.txt", "w", encoding="utf-8").write(str(e)[:400])
            print("run%d 失败 %s" % (k, e))
            continue
        res = parse_json(content)
        if not res:
            open(stem + ".error.txt", "w", encoding="utf-8").write((content or "")[-600:])
            print("run%d 解析失败" % k)
            continue
        res.update({"sha1": a.sha, "prompt_sha256": fp, "backend": a.backend, "model": a.model,
                    "temperature": a.temperature, "seed": a.seed, "usage": usage,
                    "prompt_file": a.prompt_file,
                    "latency_s": secs, "run": k})
        p = stem + ".json"
        json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        v = subprocess.run([sys.executable, os.path.join(HERE, "verify_output.py"), "--stage", a.stage,
                            "--result", p], capture_output=True, text=True, encoding="utf-8", errors="replace")
        open(stem + ".verify.txt", "w", encoding="utf-8").write(v.stdout + v.stderr)
        head = (v.stdout or "").splitlines()[0] if v.stdout else "?"
        print("run%d start=%s end=%s %s" % (k, res.get("start_line"), res.get("end_line"), head))
        spans.append((res.get("start_line"), res.get("end_line")))
    if spans:
        print("T=%s 一致=%s %s" % (a.temperature, "是" if len(set(spans)) == 1 else "否", spans))
    return 0

if __name__ == "__main__":
    sys.exit(main())
