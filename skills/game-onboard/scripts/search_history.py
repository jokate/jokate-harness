#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세션별 코드 탐색 이력 — Claude Code 대화 기록(~/.claude/projects/<프로젝트>/*.jsonl)에서
코드를 무엇으로 찾았는지 센다: 인덱스(gq · clangd · 위키 · ue_q) 대 직접(grep · 파일 찾기 · 파일 읽기).

  python search_history.py <프로젝트 폴더> [--home <홈>]

출력: JSON 목록 — {id, project, started, updated, hasClangd, counts} (game-harness-monitor mod 의 SessionSummary 와 같은 모양).
mod 의 /harness-history 가 불러 지난 세션까지 이력 페이지에 넣는다. 분류 규칙은 mod 의 classify 와 같다.
결과는 파일 크기 · 시각으로 캐시한다(~/.claude/cache/game-harness/search_history.json). 읽기만 한다.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

INDEX = re.compile(r"(cindex|gq|wq|ue_q)\.py")
KIND = {"cindex": "clangd", "gq": "gq", "wq": "wiki", "ue_q": "ue_q"}
GREP = re.compile(r"(^|[\s|;&(])(rg|grep|egrep|findstr|Select-String|sls)(\s|$)")
FIND = re.compile(r"(^|[\s|;&(])(find|fd|Get-ChildItem|gci|dir|ls)(\s|$)")
KINDS = ("gq", "clangd", "wiki", "ue_q", "grep", "glob", "read")


def classify(name, inp):
    if name in ("Bash", "PowerShell"):
        cmd = str(inp.get("command", ""))
        m = INDEX.search(cmd)
        if m:
            return KIND[m.group(1)]
        if GREP.search(cmd):
            return "grep"
        if FIND.search(cmd):
            return "glob"
        return None
    if name == "Grep":
        return "grep"
    if name == "Glob":
        return "glob"
    if name == "Read":
        return "wiki" if re.search(r"[\\/]\.jokate-wiki[\\/]", str(inp.get("file_path", ""))) else "read"
    return None


def ms(stamp):
    try:
        return int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, AttributeError):
        return 0


def summarize(path):
    counts = dict.fromkeys(KINDS, 0)
    first = last = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            t = ms(d.get("timestamp", ""))
            if t:
                first = first or t
                last = t
            msg = d.get("message") or {}
            if d.get("type") != "assistant" or not isinstance(msg.get("content"), list):
                continue
            for b in msg["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    k = classify(b.get("name", ""), b.get("input") or {})
                    if k:
                        counts[k] += 1
    return first, last, counts


def transcripts(root, home):
    key = re.sub(r"[^A-Za-z0-9]", "-", str(Path(root).resolve()))
    d = Path(home) / ".claude" / "projects" / key
    return sorted(d.glob("*.jsonl")) if d.is_dir() else []


def history(root, home):
    root = Path(root).resolve()
    cache_p = Path(home) / ".claude" / "cache" / "game-harness" / "search_history.json"
    try:
        cache = json.loads(cache_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    has_clangd = (root / "Saved" / "ClaudeIndex" / "clangd.sqlite").is_file()
    out = []
    for p in transcripts(root, home):
        st = p.stat()
        sig = f"{st.st_size}:{int(st.st_mtime)}"
        hit = cache.get(str(p))
        if hit and hit.get("sig") == sig:
            first, last, counts = hit["first"], hit["last"], hit["counts"]
        else:
            first, last, counts = summarize(p)
            cache[str(p)] = {"sig": sig, "first": first, "last": last, "counts": counts}
        if sum(counts.values()):
            out.append({"id": p.stem, "project": str(root), "started": first, "updated": last,
                        "hasClangd": has_clangd, "counts": counts})
    try:
        cache_p.parent.mkdir(parents=True, exist_ok=True)
        cache_p.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return sorted(out, key=lambda s: s["started"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--home", default=str(Path.home()))
    a = ap.parse_args()
    print(json.dumps(history(a.project, a.home), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
