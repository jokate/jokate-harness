#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""game-harness 설치. 스킬을 ~/.claude/skills 로, 훅을 ~/.claude/hooks 로 옮기고 settings 조각을 출력한다.

  python install.py            # 복사
  python install.py --link     # 스킬을 저장소로 링크 (Windows 정션 / 그 외 심볼릭 링크)
  python install.py --dry-run  # 무엇을 할지만 출력

settings.json 은 고치지 않는다. 출력된 조각을 직접 합친다.
같은 이름이 이미 있으면 건너뛴다 (--force 로 덮어쓰기, 기존 것은 .bak 로 남긴다).
"""
import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

REPO = Path(__file__).resolve().parent
CLAUDE = Path.home() / ".claude"
HOOKS = ["session_start.py", "game_context.py", "mcp_guard.py", "mcp_log.py"]


def link(src, dst):
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)], check=True, capture_output=True)
    else:
        dst.symlink_to(src, target_is_directory=True)


def install_skills(a):
    dst_root = CLAUDE / "skills"
    dst_root.mkdir(parents=True, exist_ok=True)
    for src in sorted((REPO / "skills").glob("game-*")):
        dst = dst_root / src.name
        if dst.exists() or dst.is_symlink():
            if dst.resolve() == src.resolve():
                print(f"  = {src.name} (이미 저장소를 가리킴)")
                continue
            if not a.force:
                print(f"  - {src.name} 건너뜀 (이미 있음, --force)")
                continue
            if not a.dry_run:
                shutil.move(str(dst), str(dst) + ".bak")
        print(f"  + {src.name} ({'링크' if a.link else '복사'})")
        if a.dry_run:
            continue
        if a.link:
            link(src, dst)
        else:
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))


def install_hooks(a):
    dst_root = CLAUDE / "hooks"
    dst_root.mkdir(parents=True, exist_ok=True)
    for name in HOOKS:
        src = REPO / "skills" / "game-bootstrap" / "harness" / name
        dst = dst_root / name
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            print(f"  = {name}")
            continue
        if dst.exists() and not a.force:
            print(f"  - {name} 건너뜀 (내용이 다름, --force)")
            continue
        print(f"  + {name}")
        if not a.dry_run:
            if dst.exists():
                shutil.copy2(dst, str(dst) + ".bak")
            shutil.copy2(src, dst)


def settings_snippet():
    py = sys.executable
    h = str(CLAUDE / "hooks")

    def cmd(name, timeout, extra=None):
        d = {"type": "command", "command": py, "args": [os.path.join(h, name)], "timeout": timeout}
        d.update(extra or {})
        return d

    mcp_log = cmd("mcp_log.py", 10, {"async": True})
    return {"hooks": {
        "SessionStart": [{"hooks": [cmd("session_start.py", 60), cmd("game_context.py", 15)]}],
        "PreToolUse": [{"matcher": "mcp__.*", "hooks": [cmd("mcp_guard.py", 5)]}],
        "PostToolUse": [{"matcher": "mcp__.*", "hooks": [mcp_log]}],
        "PostToolUseFailure": [{"matcher": "mcp__.*", "hooks": [mcp_log]}],
    }}


def check_settings():
    try:
        s = (CLAUDE / "settings.json").read_text(encoding="utf-8")
    except OSError:
        return []
    return [n for n in HOOKS if n not in s]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print("스킬 →", CLAUDE / "skills")
    install_skills(a)
    print("훅 →", CLAUDE / "hooks")
    install_hooks(a)
    missing = check_settings()
    if missing:
        print("\n~/.claude/settings.json 에 등록 안 된 훅:", ", ".join(missing))
        print("아래 조각을 hooks 에 합친다 (이미 있는 이벤트 배열에는 항목만 추가):\n")
        print(json.dumps(settings_snippet(), ensure_ascii=False, indent=2))
    else:
        print("\nsettings.json 훅 등록 확인됨.")
    print("\n다음: 프로젝트에서 Claude Code 를 열고 /game-bootstrap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
