#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""game-harness 제거. uninstall.bat 이 부른다.

  python uninstall.py [프로젝트 폴더 ...] [--project-only] [--purge] [--yes] [--dry-run]

머신에서 (--project-only 가 아니면):
  ~/.claude/skills/game-*      링크는 링크만 끊고, 복사본은 폴더를 지운다 (이 저장소에 있는 이름만)
  ~/.claude/hooks/<훅>.py      이 저장소가 설치한 훅 파일 (harness_events.py 포함)
  ~/.claude/mods/<mod>         하네스 모니터 mod (링크는 링크만 끊는다)
  ~/.claude/settings.json      그 훅을 가리키는 항목과 env.CLAUDE_CODE_PLUGIN_DIRS 의 mod 경로만 뺀다. 원본은 settings.json.bak
  ~/.claude/cache/stuck        매몰 카운터 상태
  ~/.claude/cache/game-harness 하네스 이벤트 로그
  --purge 면 ~/.claude/cache/ue_index (엔진 인덱스 — 정규식·clangd, 다시 만들려면 몇 분~) 도 지운다

프로젝트 폴더를 주면:
  CLAUDE.local.md              → CLAUDE.local.md.removed 로 이름만 바꾼다 (직접 고친 내용이 있을 수 있어 지우지 않는다)
  .claude/session_start.json   gq.py 인덱스 선언일 때만 지운다
  .claude/handoff.md, handoff.used.md, stuck_watch.json
  Saved/ClaudeIndex, Library/ClaudeIndex (프로젝트 인덱스)
CLAUDE.md (--team 으로 만든 것 포함) 와 .git/info/exclude 는 건드리지 않는다.
이 저장소 폴더 자체는 남는다. 다시 쓰려면 setup.bat.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

REPO = Path(__file__).resolve().parent
CLAUDE = Path.home() / ".claude"
sys.path.insert(0, str(REPO))
from install import HOOKS, LIBS, PLUGIN_DIRS_ENV, mod_dirs, mod_paths, rules_block_span  # noqa: E402


def is_link(p):
    return p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) or \
        (p.exists() and os.path.normcase(str(p.resolve())) != os.path.normcase(os.path.abspath(p)))


def remove_skills(dry):
    for src in sorted((REPO / "skills").glob("game-*")):
        dst = CLAUDE / "skills" / src.name
        if not (dst.exists() or dst.is_symlink()):
            continue
        if is_link(dst):
            print(f"  - {dst} (링크 해제)")
            if not dry:
                try:
                    os.rmdir(dst)
                except OSError:
                    os.unlink(dst)
        elif (dst / "SKILL.md").is_file():
            print(f"  - {dst} (복사본 삭제)")
            if not dry:
                shutil.rmtree(dst)


def remove_mods(dry):
    for src in mod_dirs():
        dst = CLAUDE / "mods" / src.name
        if not (dst.exists() or dst.is_symlink()):
            continue
        if is_link(dst):
            print(f"  - {dst} (링크 해제)")
            if not dry:
                try:
                    os.rmdir(dst)
                except OSError:
                    os.unlink(dst)
        elif (dst / ".claude-plugin" / "plugin.json").is_file():
            print(f"  - {dst} (복사본 삭제)")
            if not dry:
                shutil.rmtree(dst)


def remove_hooks(dry):
    for name in HOOKS + LIBS:
        p = CLAUDE / "hooks" / name
        if p.is_file():
            print(f"  - {p}")
            if not dry:
                p.unlink()


def clean_settings(dry):
    path = CLAUDE / "settings.json"
    if not path.is_file():
        return
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"  ! settings.json 을 읽지 못했다 ({e}). 직접 hooks 에서 {', '.join(HOOKS)} 항목을 지운다.")
        return

    def ours(h):
        blob = " ".join([str(h.get("command", ""))] + [str(x) for x in h.get("args", [])])
        return any(("hooks" in blob and name in blob) for name in HOOKS)

    removed = []
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        groups = []
        for g in hooks[event]:
            keep = [h for h in g.get("hooks", []) if not ours(h)]
            removed += [f"{event}:{os.path.basename(h['args'][0]) if h.get('args') else '?'}"
                        for h in g.get("hooks", []) if ours(h)]
            if keep:
                groups.append({**g, "hooks": keep})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if "hooks" in settings and not hooks:
        del settings["hooks"]
    env = settings.get("env") or {}
    if PLUGIN_DIRS_ENV in env:
        ours_dirs = set(mod_paths())
        cur = [x for x in str(env[PLUGIN_DIRS_ENV]).split(os.pathsep) if x]
        keep = [x for x in cur if x not in ours_dirs]
        if len(keep) != len(cur):
            removed.append(f"env.{PLUGIN_DIRS_ENV}(mod)")
            if keep:
                env[PLUGIN_DIRS_ENV] = os.pathsep.join(keep)
            else:
                del env[PLUGIN_DIRS_ENV]
            if not env:
                settings.pop("env", None)
    if not removed:
        print("  = settings.json 에 등록된 훅·mod 없음")
        return
    print("  - settings.json 훅 해제:", ", ".join(removed), "(원본: settings.json.bak)")
    if not dry:
        shutil.copy2(path, str(path) + ".bak")
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remove_rules(dry):
    path = CLAUDE / "CLAUDE.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    span = rules_block_span(text)
    if not span:
        return
    rest = (text[:span[0]].rstrip() + "\n" + text[span[1]:].lstrip()).strip()
    print(f"  - {path} 공용 규칙 구간" + (" (남는 내용이 없어 파일도 지운다)" if not rest else ""))
    if not dry:
        if rest:
            path.write_text(rest + "\n", encoding="utf-8")
        else:
            path.unlink()


def remove_tree(p, dry, note=""):
    if p.is_dir() and not is_link(p):
        print(f"  - {p}{note}")
        if not dry:
            shutil.rmtree(p, ignore_errors=True)


def remove_project(root, dry):
    root = Path(root.strip().strip('"')).resolve()
    print(f"프로젝트 → {root}")
    if not root.is_dir():
        print("  ! 폴더가 없다")
        return
    local = root / "CLAUDE.local.md"
    if local.is_file():
        print(f"  - {local.name} → {local.name}.removed (이름만 바꿈. 필요 없으면 직접 지운다)")
        if not dry:
            os.replace(local, str(local) + ".removed")
    decl = root / ".claude" / "session_start.json"
    if decl.is_file():
        if "gq.py" in decl.read_text(encoding="utf-8", errors="replace"):
            print(f"  - {decl}")
            if not dry:
                decl.unlink()
        else:
            print(f"  = {decl} 는 남긴다 (이 하네스가 만든 선언이 아니다)")
    for name in ("handoff.md", "handoff.used.md", "stuck_watch.json"):
        p = root / ".claude" / name
        if p.is_file():
            print(f"  - {p}")
            if not dry:
                p.unlink()
    for rel in ("Saved/ClaudeIndex", "Library/ClaudeIndex"):
        remove_tree(root / rel, dry)
    if (root / "CLAUDE.md").is_file():
        print("  = CLAUDE.md 는 건드리지 않는다. 스킬 라우팅 절이 있으면 직접 지운다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projects", nargs="*")
    ap.add_argument("--project-only", action="store_true", help="머신 설치는 두고 프로젝트에서만 뺀다")
    ap.add_argument("--purge", action="store_true", help="엔진 인덱스 캐시도 지운다")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    tty = bool(sys.stdin and sys.stdin.isatty())

    if a.project_only and not a.projects:
        raise SystemExit("--project-only 에는 프로젝트 폴더가 필요하다.")
    if not a.projects and tty and not a.yes:
        print("세팅했던 프로젝트 폴더가 있으면 입력한다 (끌어다 놓아도 된다). 비워 두면 머신 설치만 제거한다.")
        try:
            p = input("프로젝트 폴더: ").strip().strip('"').strip()
        except EOFError:
            p = ""
        if p:
            a.projects = [p]

    what = "프로젝트 세팅만" if a.project_only else "game-harness 스킬·훅·설정" + (" + 프로젝트 세팅" if a.projects else "")
    if tty and not a.yes and not a.dry_run:
        try:
            if input(f"{what} 을(를) 제거한다. 계속하려면 y: ").strip().lower() != "y":
                print("취소했다.")
                return 0
        except EOFError:
            return 0

    if not a.project_only:
        print("스킬 →", CLAUDE / "skills")
        remove_skills(a.dry_run)
        print("훅 →", CLAUDE / "hooks")
        remove_hooks(a.dry_run)
        print("mod →", CLAUDE / "mods")
        remove_mods(a.dry_run)
        print("설정 →", CLAUDE / "settings.json")
        clean_settings(a.dry_run)
        remove_rules(a.dry_run)
        remove_tree(CLAUDE / "cache" / "stuck", a.dry_run)
        remove_tree(CLAUDE / "cache" / "game-harness", a.dry_run, " (하네스 이벤트 로그)")
        ue = CLAUDE / "cache" / "ue_index"
        if a.purge:
            remove_tree(ue, a.dry_run)
        elif ue.is_dir():
            print(f"  = {ue} 는 남긴다 (엔진 인덱스. 지우려면 --purge)")
    for p in a.projects:
        remove_project(p, a.dry_run)

    print("\n(미리보기 — 아무것도 바꾸지 않았다)" if a.dry_run else
          "\n제거 끝. 열려 있는 Claude Code 세션은 닫고 새로 연다. 다시 쓰려면 setup.bat.")
    if tty and not a.yes:
        try:
            input("\n엔터를 누르면 닫힌다.")
        except EOFError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
