#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""프로젝트 최소 세팅 (비대화식). /game-bootstrap 스킬의 생성 단계이자 단독 실행용.

  python bootstrap.py [프로젝트경로] [--team] [--modules 답변 형식,가설 우선] [--dry-run]

만드는 것 (이미 있으면 건너뛴다 — 덮어쓰지 않는다):
  CLAUDE.local.md (기본, VCS 에 안 올라감) 또는 CLAUDE.md (--team)
      references/claude-md-template.md 의 [필수]·[선택: 권장] 모듈 + --modules 로 고른 [선택] 모듈.
      엔진·버전·VCS·소스 저장소는 감지해서 채운다.
  .claude/session_start.json   세션 시작 때 gq.py index

평가에서 프로젝트 규칙 파일이 스킬 호출의 실질적인 스위치였다 (훅 안내로는 대체 안 됨).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent
TEMPLATE = HERE.parent / "references" / "claude-md-template.md"
sys.path.insert(0, str(SKILLS / "game-onboard" / "scripts"))
sys.path.insert(0, str(SKILLS / "game-architecture" / "scripts"))
from gq import detect, engine_version  # noqa: E402
from evidence import vcs_roots  # noqa: E402


def template_sections():
    text = TEMPLATE.read_text(encoding="utf-8")
    body = re.search(r"```markdown\n(.*?)\n```", text, re.S).group(1)
    title, *parts = re.split(r"\n(?=## )", body)
    out = []
    for p in parts:
        m = re.match(r"## (.+?) \[(필수|선택[^\]]*)\]\n", p)
        out.append((m.group(1), m.group(2), p[m.end():].rstrip()))
    return title, out


def describe_vcs(root):
    roots = vcs_roots(root)
    if not roots:
        return "없음. 변경 이력 신호(evidence.py)를 쓸 수 없다."
    k, d, n, src = max(roots, key=lambda r: ((r[3] or 0), (r[2] or 0)))
    rel = os.path.relpath(d, root).replace("\\", "/")
    where = "루트" if rel == "." else f"`{rel}` (루트와 별도 저장소 — evidence.py 는 `--path {rel}`)"
    return f"{k}. 소스 저장소: {where}. 커밋·푸시는 요청받을 때만."


def render(root, kind, marker, modules):
    title, sections = template_sections()
    engine = {"ue": "Unreal Engine", "unity": "Unity"}.get(kind, "미감지")
    ver = engine_version(kind, marker) if marker else "?"
    lines = [title.replace("<프로젝트>", root.name), ""]
    for name, tag, body in sections:
        if not (tag == "필수" or tag == "선택: 권장" or name in modules):
            continue
        body = body.replace("<사람/팀>", "사용자")  # 템플릿: "<사람/팀>다"
        body = re.sub(r"- 엔진: <[^>]+>", f"- 엔진: {engine} {ver}", body)
        body = re.sub(r"- VCS: <[^>]+>\. 커밋·푸시는 요청받을 때만\.", f"- VCS: {describe_vcs(root)}", body)
        body = re.sub(r"- 빌드·실행: .*", "- 빌드·실행·테스트 명령: 미정 — 알게 되면 이 줄을 채운다.", body)
        lines += [f"## {name}", body, ""]
    return "\n".join(lines).rstrip() + "\n"


def write(path, text, dry):
    if path.exists():
        print(f"  - {path.name} 이미 있음 — 건너뜀")
        return
    print(f"  + {path}")
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--team", action="store_true", help="CLAUDE.md 로 만든다 (VCS 에 커밋할 팀 규칙)")
    ap.add_argument("--modules", default="", help="추가할 [선택] 모듈 이름, 쉼표 구분 (예: 답변 형식,가설 우선)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    root, kind, marker = detect(a.project)
    if root is None:
        raise SystemExit(f"게임 프로젝트가 아니다 (*.uproject / ProjectSettings+Assets 없음): {Path(a.project).resolve()}")
    modules = {m.strip() for m in a.modules.split(",") if m.strip()}
    print(f"프로젝트 {root} · {kind} {engine_version(kind, marker)}")

    rules = root / ("CLAUDE.md" if a.team else "CLAUDE.local.md")
    other = root / ("CLAUDE.local.md" if a.team else "CLAUDE.md")
    if other.exists():
        print(f"  참고: {other.name} 가 이미 있다. 두 파일은 합쳐서 로드된다 — 중복 규칙이 없는지 확인.")
    text = render(root, kind, marker, modules)
    write(rules, text, a.dry_run)
    decl = {"commands": [{"run": ["~/.claude/skills/game-onboard/scripts/gq.py", "index", "--quiet"], "timeout": 60}]}
    write(root / ".claude" / "session_start.json", json.dumps(decl, ensure_ascii=False, indent=2) + "\n", a.dry_run)

    if a.dry_run:
        print("\n--- 미리보기 ---\n" + text)
        return 0
    if not a.team and (root / ".git").exists():
        print("  참고: git 이면 .git/info/exclude 에 CLAUDE.local.md 를 넣으면 실수로 커밋되지 않는다.")
    if not a.team and (root / ".svn").is_dir():
        print("  참고: svn 이면 `svn propset svn:ignore CLAUDE.local.md .` (VCS 변경이라 직접 실행)")
    print("\n다음: 이 프로젝트에서 Claude Code 를 새로 연다 (세션 시작 때 인덱스가 만들어진다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
