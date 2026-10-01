#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""프로젝트 최소 세팅 (비대화식). /game-bootstrap 스킬의 생성 단계이자 단독 실행용.

  python bootstrap.py [프로젝트경로] [--team] [--modules 답변 형식,가설 우선] [--only 스킬 라우팅] [--dry-run]

기존 CLAUDE.md 가 있는 프로젝트는 --only 로 겹치지 않는 모듈만 넣는다 (최소: 스킬 라우팅).

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


def render(root, kind, marker, modules, only=None, fname="CLAUDE.md"):
    title, sections = template_sections()
    engine = {"ue": "Unreal Engine", "unity": "Unity"}.get(kind, "미감지")
    ver = engine_version(kind, marker) if marker else "?"
    title = title.replace("<프로젝트>", root.name).replace("CLAUDE.md", fname)
    if only is not None:
        title = title.replace("작업 규칙", "추가 규칙 (game-harness)")
    lines = [title, ""]
    for name, tag, body in sections:
        if only is not None:
            if name not in only:
                continue
        elif not (tag == "필수" or tag == "선택: 권장" or name in modules):
            continue
        body = body.replace("<사람/팀>", "사용자")  # 템플릿: "<사람/팀>다"
        body = re.sub(r"- 엔진: <[^>]+>", f"- 엔진: {engine} {ver}", body)
        body = re.sub(r"- VCS: <[^>]+>\. 커밋·푸시는 요청받을 때만\.", f"- VCS: {describe_vcs(root)}", body)
        body = re.sub(r"- 빌드·실행: .*", "- 빌드·실행·테스트 명령: 미정 — 알게 되면 이 줄을 채운다.", body)
        lines += [f"## {name}", body, ""]
    return "\n".join(lines).rstrip() + "\n"


HOWTO = """
==================== 세팅 끝. 이제 이렇게 쓴다 ====================
1. Claude Code 를 이 폴더에서 새로 연다
     터미널:      cd "{root}"  →  claude
     데스크톱 앱: 새 세션에서 이 폴더를 고른다
   (이미 열려 있던 세션에는 적용되지 않는다. 새로 연다.)

2. 평소처럼 말로 요청한다. 따로 실행할 명령은 없다.
     "이 프로젝트 구조 파악해줘"        → 인덱스로 좌표부터 찾는다
     "<기능> 추가하고 싶다"             → 코드 전에 구조 조사, 선택지 A/B/C + 그림, 고를 때까지 멈춘다
     "<문서> 기획을 사양 표로 뽑아줘"   → 사양 표, 구현 대조, 어긋남 보고
     "<엔진 클래스> 가 어떻게 동작하지" → 엔진 소스 인덱스로 조회

3. 답이 이상해지거나 [매몰 신호] 경고가 뜨면
     [RESET] 입력 → .claude/handoff.md 읽기 → /clear

잘 붙었는지 확인: 1번 뒤 "이 프로젝트 구조 파악해줘" 의 첫 행동이 game-onboard 스킬 호출이면 정상.
다른 프로젝트에도 쓰려면 그 폴더를 setup.bat 위에 끌어다 놓는다.
==================================================================="""


def git_exclude(root):
    """개인 파일을 .git/info/exclude 에 넣는다. 이 파일은 커밋되지 않는 로컬 무시 목록이다."""
    path = root / ".git" / "info" / "exclude"
    try:
        cur = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        add = [p for p in ("CLAUDE.local.md", ".claude/handoff.md", ".claude/handoff.used.md", ".claude/session_start.json")
               if p not in cur.split()]
        if not add:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cur + ("" if cur.endswith("\n") or not cur else "\n") + "\n".join(add) + "\n", encoding="utf-8")
        print(f"  + .git/info/exclude 에 등록 (커밋에서 제외): {', '.join(add)}")
    except OSError as e:
        print(f"  ! .git/info/exclude 를 고치지 못했다: {e}")


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
    ap.add_argument("--only", default=None, help="이 모듈만 넣는다, 쉼표 구분 (기존 규칙 파일이 있을 때. 예: 스킬 라우팅)")
    ap.add_argument("--routing-only", action="store_true", help="= --only 스킬 라우팅 (기존 규칙 파일이 있는 프로젝트용, bat 에서 쓰기 쉬운 ASCII 플래그)")
    ap.add_argument("--auto", action="store_true",
                    help="알아서: CLAUDE.md 가 있으면 --routing-only, git 이면 .git/info/exclude 에 개인 파일 등록, 끝에 사용법 출력")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    root, kind, marker = detect(a.project)
    if root is None:
        raise SystemExit(f"게임 프로젝트가 아니다 (*.uproject / ProjectSettings+Assets 없음): {Path(a.project).resolve()}")
    modules = {m.strip() for m in a.modules.split(",") if m.strip()}
    print(f"프로젝트 {root} · {kind} {engine_version(kind, marker)}")

    rules = root / ("CLAUDE.md" if a.team else "CLAUDE.local.md")
    other = root / ("CLAUDE.local.md" if a.team else "CLAUDE.md")
    if a.auto and not a.team and other.exists() and a.only is None:
        print(f"  {other.name} 가 이미 있다 → 스킬 라우팅 절만 넣는다 (기존 규칙과 겹치지 않게)")
        a.routing_only = True
    if a.routing_only:
        a.only = "스킬 라우팅"
    only = {m.strip() for m in a.only.split(",") if m.strip()} if a.only is not None else None
    names = [n for n, _, _ in template_sections()[1]]
    if only and (only - set(names)):
        raise SystemExit(f"없는 모듈: {', '.join(sorted(only - set(names)))}. 템플릿 모듈: {', '.join(names)}")
    if other.exists() and only is None:
        print(f"  참고: {other.name} 가 이미 있다. 두 파일은 합쳐서 로드된다 — 규칙이 겹치거나 충돌하면 "
              f"--only 로 필요한 모듈만 넣는다 (최소: --routing-only). 모듈: {', '.join(names)}")
    text = render(root, kind, marker, modules, only, rules.name)
    write(rules, text, a.dry_run)
    decl = {"commands": [{"run": ["~/.claude/skills/game-onboard/scripts/gq.py", "index", "--quiet"], "timeout": 60}]}
    write(root / ".claude" / "session_start.json", json.dumps(decl, ensure_ascii=False, indent=2) + "\n", a.dry_run)

    if a.dry_run:
        print("\n--- 미리보기 ---\n" + text)
        return 0
    if not a.team and a.auto and (root / ".git").is_dir():
        git_exclude(root)
    elif not a.team and (root / ".git").exists():
        print("  참고: git 이면 .git/info/exclude 에 CLAUDE.local.md 를 넣으면 실수로 커밋되지 않는다.")
    if not a.team and (root / ".svn").is_dir():
        print("  참고: svn 은 `svn add` 하지 않으면 올라가지 않는다. 커밋 창에서 CLAUDE.local.md 와 .claude 를 체크하지 않는다.")
    if a.auto:
        print(HOWTO.format(root=root))
    else:
        print("\n다음: 이 프로젝트에서 Claude Code 를 새로 연다 (세션 시작 때 인덱스가 만들어진다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
