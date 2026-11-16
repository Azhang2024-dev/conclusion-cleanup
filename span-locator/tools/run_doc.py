# -*- coding: utf-8 -*-
"""run_doc.py — one article, N runs, one verdict per run.

    python tools/run_doc.py --stage PATH --sha SHA1 --runs 3 [--backend http|dsh]
                            [--temperature 0] [--model deepseek-chat]

Writes <stage>/R3_spanlocator/<sha>/run{1..N}.json and .verify.txt, then prints the
agreement across runs. Nothing is decided here; the gate decides.
"""
import os, sys, io, json, re, argparse, subprocess, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="backslashreplace")
HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT = open(os.path.join(os.path.dirname(HERE), "prompt.md"), encoding="utf-8").read()

def build_input(stage, sha):
    alog = [json.loads(l) for l in open(os.path.join(stage, "A_lines", sha + ".jsonl"), encoding="utf-8") if l.strip()]
    return "\n".join("L%d | %s" % (o["i"], o["text"]) for o in alog), len(alog)

def ask_http(prompt, model, temperature):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("没有 DEEPSEEK_API_KEY，改用 --backend dsh")
    body = json.dumps({"model": model, "temperature": temperature, "stream": False,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", body,
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]

def ask_dsh(prompt):
    p = subprocess.run(["dsh", "--profile", "headless", prompt], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800, env=dict(os.environ, NO_COLOR="1"))
    return (p.stdout or "")

def parse_json(s):
    m = re.findall(r"\{.*\"end_line\".*\}", s, re.S)
    for cand in reversed(m or []):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None

ap = argparse.ArgumentParser()
ap.add_argument("--stage", required=True)
ap.add_argument("--sha", required=True)
ap.add_argument("--runs", type=int, default=1)
ap.add_argument("--backend", default="dsh", choices=["http", "dsh"])
ap.add_argument("--temperature", type=float, default=0.0)
ap.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
a = ap.parse_args()

text, n = build_input(a.stage, a.sha)
outdir = os.path.join(a.stage, "R3_spanlocator", a.sha)
os.makedirs(outdir, exist_ok=True)
prompt = PROMPT + "\n\n[文章行流，共 %d 行]\n%s\n\n只输出 JSON。" % (n, text)

spans = []
for k in range(1, a.runs + 1):
    raw = ask_http(prompt, a.model, a.temperature) if a.backend == "http" else ask_dsh(prompt)
    res = parse_json(raw)
    if not res:
        print("run%d 解析失败: %r" % (k, raw[-200:]))
        continue
    res["sha1"] = a.sha
    res["_backend"] = a.backend
    res["_model"] = a.model if a.backend == "http" else "dsh-headless"
    res["_temperature"] = a.temperature
    p = os.path.join(outdir, "run%d.json" % k)
    json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    v = subprocess.run([sys.executable, os.path.join(HERE, "verify_output.py"),
                        "--stage", a.stage, "--result", p], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    open(os.path.join(outdir, "run%d.verify.txt" % k), "w", encoding="utf-8").write(v.stdout + v.stderr)
    print("run%d start=%s end=%s  %s" % (k, res.get("start_line"), res.get("end_line"),
                                         (v.stdout or "").splitlines()[0] if v.stdout else "?"))
    spans.append((res.get("start_line"), res.get("end_line")))

if spans:
    same = len(set(spans)) == 1
    print("一致: %s  %s" % ("是" if same else "否", spans))
