#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""game-harness 설치. 스킬을 ~/.claude/skills 로, 훅을 ~/.claude/hooks 로 옮기고 settings 조각을 출력한다.

  python install.py            # 복사
  python install.py --link     # 스킬을 저장소로 링크 (Windows 정션 / 그 외 심볼릭 링크)
  python install.py --dry-run  # 무엇을 할지만 출력

  python install.py --apply-settings  # settings.json 에 훅까지 등록 (setup.bat 이 쓰는 방식)

--apply-settings 없이는 settings.json 을 고치지 않는다. 출력된 조각을 직접 합친다.
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
HOOKS = ["session_start.py", "game_context.py", "mcp_guard.py", "mcp_log.py", "handoff.py", "stuck_watch.py"]


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
    stuck = cmd("stuck_watch.py", 5)
    return {"hooks": {
        "SessionStart": [{"hooks": [cmd("session_start.py", 60), cmd("game_context.py", 15), cmd("handoff.py", 10)]}],
        "UserPromptSubmit": [{"hooks": [cmd("handoff.py", 180)]}],
        "PreToolUse": [{"matcher": "mcp__.*", "hooks": [cmd("mcp_guard.py", 5)]}],
        "PostToolUse": [{"matcher": "mcp__.*", "hooks": [mcp_log]},
                        {"matcher": "Edit|Write|NotebookEdit|Bash|PowerShell", "hooks": [stuck]}],
        "PostToolUseFailure": [{"matcher": "mcp__.*", "hooks": [mcp_log]},
                               {"matcher": "Bash|PowerShell", "hooks": [stuck]}],
    }}


def apply_settings(dry):
    """settings.json 의 hooks 에 빠진 훅만 추가한다. 기존 항목은 건드리지 않는다. 원본은 settings.json.bak 으로 남긴다."""
    path = CLAUDE / "settings.json"
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError as e:
        print(f"  ! settings.json 을 읽지 못했다 ({e}). 고치지 않는다 — 아래 조각을 직접 합친다.")
        return False
    hooks = settings.setdefault("hooks", {})
    added = []
    for event, groups in settings_snippet()["hooks"].items():
        cur = hooks.setdefault(event, [])
        have = {os.path.basename(arg) for g in cur for h in g.get("hooks", []) for arg in h.get("args", [])}
        have |= {n for g in cur for h in g.get("hooks", []) for n in HOOKS if n in str(h.get("command", ""))}
        for g in groups:
            new = [h for h in g["hooks"] if os.path.basename(h["args"][0]) not in have]
            if not new:
                continue
            same = [c for c in cur if c.get("matcher") == g.get("matcher")]
            if same:
                same[0].setdefault("hooks", []).extend(new)
            else:
                cur.append({**g, "hooks": new})
            added += [f"{event}:{os.path.basename(h['args'][0])}" for h in new]
    if not added:
        print("  = settings.json 훅 이미 등록됨")
        return True
    print("  + settings.json 훅 등록:", ", ".join(added))
    if not dry:
        if path.exists():
            shutil.copy2(path, str(path) + ".bak")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


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
    ap.add_argument("--apply-settings", action="store_true", help="settings.json 에 훅을 직접 등록한다 (백업 후, 빠진 것만)")
    a = ap.parse_args()
    print("스킬 →", CLAUDE / "skills")
    install_skills(a)
    print("훅 →", CLAUDE / "hooks")
    install_hooks(a)
    if a.apply_settings:
        print("설정 →", CLAUDE / "settings.json")
        if apply_settings(a.dry_run):
            return 0
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
