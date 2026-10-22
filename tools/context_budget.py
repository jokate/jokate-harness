#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세션마다 항상 들어가는 글(always-on)의 크기 — 하네스 몫과 그 밖을 나눠 잰다.

Harness²(arXiv 2610.14224) 부록: 항상 들어가는 글은 가장 비싼 선택이다 — 모든 토큰이 답의 몫과 다툰다. 부를 때만
들어가는 것(스킬 본문 · 스크립트 · 훅)을 먼저 쓰고, 항상 글을 더하면 다른 것을 뺀다. 그 실험에서 항상 글을 떼어도
−1.5점으로 가장 작았고 스킬(−5.3) · 스크립트(−3.7)가 컸다. 이 스크립트는 그 예산을 지키려고 잰다.

  python tools/context_budget.py [<프로젝트>] [--budget 7000] [--json]

하네스 몫: 하네스 스킬(game-*)의 description · 세션 시작 안내(game_context.py 출력) · 전역 CLAUDE.md 의 하네스 절 ·
프로젝트 CLAUDE.local.md(bootstrap 이 쓴다). 그 밖: 다른 스킬의 description · 프로젝트 CLAUDE.md · 전역 CLAUDE.md 의 나머지.
하네스 몫이 --budget(바이트)을 넘으면 종료 코드 1.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

REPO = Path(__file__).resolve().parent.parent
BLOCK = re.compile(r"<!-- game-harness:begin.*?<!-- game-harness:end -->", re.S)  # install.py 의 RULES_BEGIN · RULES_END


def description(skill_md: Path) -> str:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    head = m.group(1) if m else ""
    d = re.search(r"^description:\s*(.+)$", head, re.M)
    return d.group(1).strip() if d else ""


def game_context_output(project: Path, home: Path) -> str:
    hook = home / ".claude" / "hooks" / "game_context.py"
    if not hook.is_file():
        hook = REPO / "skills" / "game-bootstrap" / "harness" / "game_context.py"
    r = subprocess.run([sys.executable, str(hook)], input=json.dumps({"cwd": str(project)}).encode(),
                       capture_output=True, cwd=str(project), env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)})
    return r.stdout.decode("utf-8", "replace")


def measure(project: Path | None, home: Path) -> dict:
    rows = []  # (몫, 이름, 바이트)
    for sk in sorted((home / ".claude" / "skills").glob("*/SKILL.md")):
        d = description(sk)
        rows.append(("하네스" if sk.parent.name.startswith("game-") else "그 밖", f"스킬 설명 {sk.parent.name}",
                     len(d.encode("utf-8"))))
    glob_md = home / ".claude" / "CLAUDE.md"
    if glob_md.is_file():
        text = glob_md.read_text(encoding="utf-8", errors="replace")
        mine = sum(len(m.group(0).encode("utf-8")) for m in BLOCK.finditer(text))
        rows.append(("하네스", "전역 CLAUDE.md 하네스 절", mine))
        rows.append(("그 밖", "전역 CLAUDE.md 나머지", len(text.encode("utf-8")) - mine))
    if project:
        rows.append(("하네스", "세션 시작 안내 (game_context)", len(game_context_output(project, home).encode("utf-8"))))
        for name, owner in (("CLAUDE.local.md", "하네스"), ("CLAUDE.md", "그 밖")):
            f = project / name
            if f.is_file():
                rows.append((owner, f"프로젝트 {name}", len(f.read_bytes())))
    mine = sum(n for o, _, n in rows if o == "하네스")
    return {"rows": rows, "harness": mine, "total": sum(n for _, _, n in rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", nargs="?")
    ap.add_argument("--home", default=str(Path.home()))
    ap.add_argument("--budget", type=int, default=7000, help="하네스 몫 한도 (바이트, 기본 7000 ≈ 한글 2,300자)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = measure(Path(a.project).resolve() if a.project else None, Path(a.home))
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for owner, name, n in sorted(res["rows"], key=lambda r: (r[0] != "하네스", -r[2])):
            print(f"{owner:<4} {n:>6} B  {name}")
        print(f"하네스 몫 {res['harness']} B / 한도 {a.budget} B · 전체 {res['total']} B")
    if res["harness"] > a.budget:
        print(f"[넘음] 하네스 몫이 한도를 {res['harness'] - a.budget} B 넘었다 — 항상 글을 더했으면 다른 것을 뺀다", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
