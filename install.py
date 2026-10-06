#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""game-harness 설치. 스킬을 ~/.claude/skills 로, 훅을 ~/.claude/hooks 로, mod 를 ~/.claude/mods 로 옮기고 settings 조각을 출력한다.

  python install.py            # 복사
  python install.py --link     # 스킬을 저장소로 링크 (Windows 정션 / 그 외 심볼릭 링크)
  python install.py --dry-run  # 무엇을 할지만 출력

  python install.py --apply-settings  # settings.json 에 훅까지 등록 (setup.bat 이 쓰는 방식)
  python install.py --no-tools        # clangd 도구(의미 인덱스용, 약 60MB~)를 내려받지 않는다
                                      # mod(하네스 모니터)는 settings.json 의 env.CLAUDE_CODE_PLUGIN_DIRS 에 폴더를 더해 켠다

--apply-settings 없이는 settings.json 을 고치지 않는다. 출력된 조각을 직접 합친다.
같은 이름이 이미 있으면 건너뛴다 (--force 로 덮어쓰기, 기존 것은 .bak 로 남긴다).
clangd 도구는 못 찾을 때만 ~/.claude/tools/clangd 에 받는다 (skills/game-onboard/scripts/clangd_tools.py). 실패해도 설치는 계속한다.
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
HOOKS = ["session_start.py", "game_context.py", "mcp_guard.py", "mcp_log.py", "handoff.py", "stuck_watch.py",
         "harness_trace.py"]
LIBS = ["harness_events.py"]  # 훅이 import 하는 모듈. settings 에는 등록하지 않는다
PLUGIN_DIRS_ENV = "CLAUDE_CODE_PLUGIN_DIRS"


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
    for name in HOOKS + LIBS:
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


def mod_dirs():
    return sorted(d for d in (REPO / "mods").glob("*") if (d / ".claude-plugin" / "plugin.json").is_file())


def install_mods(a):
    """Claude Code mod(함수 훅 플러그인)를 ~/.claude/mods/<이름> 으로. 등록은 apply_settings 가 env 로 한다."""
    dst_root = CLAUDE / "mods"
    for src in mod_dirs():
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
        dst_root.mkdir(parents=True, exist_ok=True)
        if a.link:
            link(src, dst)
        else:
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "types", "tests"))
            shutil.copytree(src / "types", dst / "types")


RULES_BEGIN = "<!-- game-harness:begin (install.py 가 관리한다. 고치려면 저장소의 rules/common.md) -->"
RULES_END = "<!-- game-harness:end -->"


def rules_block_span(text):
    i = text.find("<!-- game-harness:begin")
    j = text.find(RULES_END)
    return (i, j + len(RULES_END)) if i != -1 and j > i else None


def install_rules(a):
    """rules/common.md 를 ~/.claude/CLAUDE.md 의 표시 구간에 넣는다. 구간 밖의 내용은 건드리지 않는다."""
    src = REPO / "rules" / "common.md"
    if not src.is_file():
        return
    dst = CLAUDE / "CLAUDE.md"
    block = f"{RULES_BEGIN}\n{src.read_text(encoding='utf-8').strip()}\n{RULES_END}"
    cur = dst.read_text(encoding="utf-8") if dst.exists() else ""
    span = rules_block_span(cur)
    new = cur[:span[0]] + block + cur[span[1]:] if span else (cur.rstrip() + "\n\n" if cur.strip() else "") + block + "\n"
    if new == cur:
        print("  = CLAUDE.md 공용 규칙")
        return
    print(f"  + {dst} 공용 규칙 ({'갱신' if span else '추가'})")
    if not a.dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(new, encoding="utf-8")


def install_tools(a):
    script = REPO / "skills" / "game-onboard" / "scripts" / "clangd_tools.py"
    if a.dry_run:
        print(f"  (미리보기) {script.name} install — 못 찾는 clangd 도구만 내려받는다")
        return
    if subprocess.run([sys.executable, str(script), "install"]).returncode != 0:
        print("  [경고] clangd 도구를 설치하지 못했다 — 의미 인덱스(clangd) 단계만 빠지고 나머지는 동작한다.\n"
              f"         나중에 setup.bat 을 다시 돌리거나 python \"{script}\" install")


def settings_snippet():
    py = sys.executable
    h = str(CLAUDE / "hooks")

    def cmd(name, timeout, extra=None):
        d = {"type": "command", "command": py, "args": [os.path.join(h, name)], "timeout": timeout}
        d.update(extra or {})
        return d

    mcp_log = cmd("mcp_log.py", 10, {"async": True})
    stuck = cmd("stuck_watch.py", 5)
    trace = cmd("harness_trace.py", 10, {"async": True})
    return {"hooks": {
        "SessionStart": [{"hooks": [cmd("session_start.py", 60), cmd("game_context.py", 15), cmd("handoff.py", 10)]}],
        "UserPromptSubmit": [{"hooks": [cmd("handoff.py", 180)]}],
        "PreToolUse": [{"matcher": "mcp__.*", "hooks": [cmd("mcp_guard.py", 5)]}],
        "PostToolUse": [{"matcher": "mcp__.*", "hooks": [mcp_log]},
                        {"matcher": "Edit|Write|NotebookEdit|Bash|PowerShell", "hooks": [stuck]},
                        {"matcher": "Skill|Bash|PowerShell", "hooks": [trace]}],
        "PostToolUseFailure": [{"matcher": "mcp__.*", "hooks": [mcp_log]},
                               {"matcher": "Bash|PowerShell", "hooks": [stuck]},
                               {"matcher": "Skill|Bash|PowerShell", "hooks": [trace]}],
    }}


def mod_paths():
    return [str(CLAUDE / "mods" / d.name) for d in mod_dirs()]


def add_plugin_dirs(settings):
    """settings.env.CLAUDE_CODE_PLUGIN_DIRS 에 mod 폴더를 더한다 (경로 구분자는 OS 의 것). 있던 값은 그대로 둔다."""
    env = settings.setdefault("env", {})
    cur = [x for x in str(env.get(PLUGIN_DIRS_ENV, "")).split(os.pathsep) if x]
    new = [p for p in mod_paths() if p not in cur]
    if new:
        env[PLUGIN_DIRS_ENV] = os.pathsep.join(cur + new)
    return new


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
    added += [f"env.{PLUGIN_DIRS_ENV}+={p}" for p in add_plugin_dirs(settings)]
    if not added:
        print("  = settings.json 훅·mod 이미 등록됨")
        return True
    print("  + settings.json 등록:", ", ".join(added))
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
    ap.add_argument("--no-tools", action="store_true", help="clangd 도구를 내려받지 않는다")
    a = ap.parse_args()
    print("스킬 →", CLAUDE / "skills")
    install_skills(a)
    print("훅 →", CLAUDE / "hooks")
    install_hooks(a)
    print("mod →", CLAUDE / "mods", "(하네스 모니터: Claude Code 함수 훅 플러그인)")
    install_mods(a)
    print("공용 규칙 →", CLAUDE / "CLAUDE.md")
    install_rules(a)
    if not a.no_tools:
        print("clangd 도구 →", Path.home() / ".claude" / "tools" / "clangd", "(의미 인덱스용, 못 찾을 때만 내려받는다)",
              flush=True)  # 하위 프로세스 출력보다 먼저 보이게
        install_tools(a)
    if a.apply_settings:
        print("설정 →", CLAUDE / "settings.json")
        if apply_settings(a.dry_run):
            return 0
    missing = check_settings()
    if missing:
        print("\n~/.claude/settings.json 에 등록 안 된 훅:", ", ".join(missing))
        print("아래 조각을 hooks 에 합친다 (이미 있는 이벤트 배열에는 항목만 추가):\n")
        print(json.dumps(settings_snippet(), ensure_ascii=False, indent=2))
        print(f"\nmod 를 켜려면 settings.json 의 env.{PLUGIN_DIRS_ENV} 에 더한다 (구분자 '{os.pathsep}'):",
              os.pathsep.join(mod_paths()))
    else:
        print("\nsettings.json 훅 등록 확인됨.")
    print("\n다음: 프로젝트에서 Claude Code 를 열고 /game-bootstrap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
