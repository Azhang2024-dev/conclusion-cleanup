# -*- coding: utf-8 -*-
"""Shared helpers: workspace layout, rules loading, text IO, word counting.

Layout expected under --stage (defaults to this repo's parent):
    A_lines/{sha1}.jsonl         frozen PDF line stream (one JSON per line)
    A_lines/index.csv            line-stream index
    A_lines/pages_tables/{sha1}.json table bboxes per page
    C_conclusions/{sha1}.txt      conclusion text to clean
    E_reports/                    outputs
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STAGE = os.path.dirname(HERE)


# ---------------------------------------------------------------- rules
def load_rules(path=None):
    """Read rules.yaml (PyYAML)."""
    path = path or os.path.join(os.path.dirname(HERE), "rules.yaml")
    if not os.path.exists(path):
        path = os.path.join(os.getcwd(), "rules.yaml")
    import yaml
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _scalar(text):
    t = text.strip()
    if t.startswith("'") and t.endswith("'"):
        return t[1:-1]
    if t.startswith('"') and t.endswith('"'):
        return t[1:-1]
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        if not inner:
            return []
        parts = [p.strip() for p in inner.split(",")]
        return [_scalar(p) for p in parts]
    low = t.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none", "~"):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


# ---------------------------------------------------------------- io
def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fields=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not rows:
        return
    fields = fields or list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def read_text(path):
    with open(path, "rb") as fh:
        data = fh.read()
    return data.decode("utf-8-sig")


def write_text(path, text, crlf=True):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = text.replace("\r\n", "\n")
    if crlf:
        data = data.replace("\n", "\r\n")
    with open(path, "wb") as fh:
        fh.write(data.encode("utf-8"))


def lines_of(text):
    return text.replace("\r\n", "\n").split("\n")


def join_lines(lines):
    return "\n".join(lines)


# ---------------------------------------------------------------- counting
def count_words(text):
    """The only legal word count for this project."""
    try:
        sys.path.insert(0, r"D:\conclusion-wordcount\src")
        from wcengine.count import count_words as _cw
        return _cw(text)
    except Exception:
        return len(re.findall(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", text))


# ---------------------------------------------------------------- stage data
class Stage(object):
    def __init__(self, path=None):
        self.root = os.path.abspath(path or DEFAULT_STAGE)
        self.alines = os.path.join(self.root, "A_lines")
        self.tables = os.path.join(self.alines, "pages_tables")
        self.texts = os.path.join(self.root, "C_conclusions")
        self.reports = os.path.join(self.root, "E_reports")

    def sha_list(self):
        names = [f[:-4] for f in os.listdir(self.texts) if f.endswith(".txt")]
        return sorted(names)

    def load_lines(self, sha1):
        cache = getattr(self, "_cache", None)
        if cache is None:
            cache = self._cache = {}
        if sha1 not in cache:
            rows = []
            with open(os.path.join(self.alines, sha1 + ".jsonl"), encoding="utf-8") as fh:
                for raw in fh:
                    rows.append(json.loads(raw))
            cache[sha1] = rows
        return cache[sha1]

    def load_tables(self, sha1):
        p = os.path.join(self.tables, sha1 + ".json")
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as fh:
            return json.load(fh).get("pages", {})


def norm_text(t):
    t = re.sub(r"[^A-Za-z0-9\u00c0-\u024f]+", " ", t).strip().lower()
    return re.sub(r"\s+", " ", t)


def norm_num(t):
    return re.sub(r"\d+", "#", norm_text(t))


def base_of(reason):
    """'PIPE-PARTIAL' -> 'pipe'; 'RUNHEAD' -> 'runhead'."""
    return re.sub(r"[^a-z]", "", reason.lower())
