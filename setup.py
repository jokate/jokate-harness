#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""game-harness 한 번에 세팅. setup.bat 이 부른다.

  python setup.py [프로젝트 폴더] [--no-wiki] [--clangd | --no-clangd]

1) 스킬·훅 설치 + settings.json 훅 등록 + clangd 도구 (install.py --link --force --apply-settings)
   clangd·clangd-indexer 는 못 찾을 때만 ~/.claude/tools/clangd 에 내려받는다 (Windows 약 63MB). 실패해도 계속한다.
2) 위키 하네스(jokate-wiki) 설치 — 있을 때만. 찾는 곳: 환경변수 JOKATE_WIKI_DIR → 이 폴더 옆 jokate-wiki → 이 폴더 안 jokate-wiki.
3) 프로젝트 세팅 (bootstrap.py --auto). 폴더를 안 주면 물어본다.
   위키 하네스가 있으면 이어서 그 프로젝트의 위키까지 (wq.py setup — 면담 답 초안 · 위키 · 뼈대 · 세션 시작 훅, AI 없음).
   clangd 프로젝트 인덱스(호출 · 참조 · 영향 범위)가 없으면 처음 만들지 묻고(--clangd 면 묻지 않고, --no-clangd 면 안 함)
   백그라운드로 index_all.py --project-only 를 띄운다 — 처음 20–30분, 엔진 단계 없음. 그 뒤로는 세션 시작 때 바뀐 것만 갱신된다.
4) 사용법 출력
다시 돌려도 된다. 이미 된 부분은 건너뛴다.
"""
import os
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

REPO = Path(__file__).resolve().parent
BOOTSTRAP = REPO / "skills" / "game-bootstrap" / "scripts" / "bootstrap.py"
INDEX_ALL = REPO / "skills" / "game-onboard" / "scripts" / "index_all.py"


def wait():
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\n엔터를 누르면 닫힌다.")
        except EOFError:
            pass


def ask_project():
    if not (sys.stdin and sys.stdin.isatty()):
        return ""
    print("게임 프로젝트 폴더를 입력한다. 탐색기에서 폴더를 이 창에 끌어다 놓아도 된다.")
    print("(.uproject 가 있는 폴더, 또는 Assets + ProjectSettings 가 있는 폴더. 비워 두면 건너뛴다)")
    try:
        return input("프로젝트 폴더: ").strip().strip('"').strip()
    except EOFError:
        return ""


def find_wiki(env=None, repo=REPO):
    """위키 하네스(jokate-wiki) 저장소 폴더 또는 None. install.py 와 scripts/wq.py 가 있어야 한다."""
    env = os.environ if env is None else env
    cands = [env.get("JOKATE_WIKI_DIR"), repo.parent / "jokate-wiki", repo / "jokate-wiki"]
    for c in cands:
        if c and (Path(c) / "install.py").is_file() and (Path(c) / "scripts" / "wq.py").is_file():
            return Path(c).resolve()
    return None


def clangd_index(project: Path):
    p = Path(project) / "Saved" / "ClaudeIndex" / "clangd.sqlite"
    return p if p.is_file() else None


def ask_yes(question):
    if not (sys.stdin and sys.stdin.isatty()):
        return False
    try:
        return input(question + " [y/N] ").strip().lower() in ("y", "yes", "ㅇ", "네")
    except EOFError:
        return False


def start_clangd_bg(project: Path, home=None):
    """clangd 프로젝트 인덱스를 처음 만든다 — index_all.py --project-only 를 세션과 떨어진 백그라운드로, 로그를 남긴다."""
    home = Path(home) if home else Path.home()
    log = home / ".claude" / "cache" / "game-harness" / f"index_build_{Path(project).name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    kw = ({"creationflags": getattr(subprocess, "DETACHED_PROCESS", 8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512)}
          if os.name == "nt" else {"start_new_session": True})
    with open(log, "w", encoding="utf-8") as f:
        subprocess.Popen([sys.executable, str(INDEX_ALL), str(project), "--project-only"], stdin=subprocess.DEVNULL,
                         stdout=f, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONIOENCODING="utf-8"), **kw)
    return log


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    no_wiki = "--no-wiki" in argv
    want_clangd = "--clangd" in argv
    no_clangd = "--no-clangd" in argv
    args = [a for a in argv if a not in ("--no-wiki", "--clangd", "--no-clangd")]
    wiki = None if no_wiki else find_wiki()

    print("[1/3] 설치 — 스킬, 훅, 설정, clangd 도구")
    rc = subprocess.run([sys.executable, str(REPO / "install.py"), "--link", "--force", "--apply-settings"]).returncode
    if rc != 0:
        print("\n[오류] 설치에 실패했다. 위 메시지를 확인한다.")
        wait()
        return rc

    print("\n[2/3] 위키 하네스")
    if wiki:
        r = subprocess.run([sys.executable, str(wiki / "install.py"), "--no-setup"])
        if r.returncode != 0:
            print("[경고] 위키 하네스 설치에 실패했다. 하네스는 그대로 쓸 수 있다.")
            wiki = None
    elif no_wiki:
        print("건너뛰었다 (--no-wiki).")
    else:
        print("없음 — jokate-wiki 를 이 폴더 옆에 두거나 JOKATE_WIKI_DIR 로 알려 주면 위키까지 같이 세팅한다 (선택).")

    print("\n[3/3] 프로젝트 세팅")
    target = args[0].strip().strip('"') if args else ask_project()
    if not target:
        print("건너뛰었다. 나중에 프로젝트 폴더를 setup.bat 위에 끌어다 놓으면 된다.")
        wait()
        return 0
    rc = subprocess.run([sys.executable, str(BOOTSTRAP), target, "--auto"]).returncode
    if rc != 0:
        print("\n[오류] 프로젝트 세팅에 실패했다. 폴더 경로가 맞는지 확인한다.")
        wait()
        return rc
    if wiki:
        print("\n위키 세팅 (면담 답 초안 · 위키 · 뼈대 · 세션 시작 훅, AI 없음)")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, str(wiki / "scripts" / "wq.py"), "setup", "--project", target], env=env)
        if r.returncode != 0:
            print("[경고] 위키 세팅을 못 했다. 프로젝트 폴더에서 Claude Code 를 열고 /wiki-bootstrap 으로 해도 된다.")
    proj = Path(target)
    if any(proj.glob("*.uproject")):
        db = clangd_index(proj)
        if db:
            print(f"\nclangd 프로젝트 인덱스: 있음 — 세션 시작 때 바뀐 것만 갱신된다 ({db})")
        elif no_clangd:
            print("\nclangd 프로젝트 인덱스: 건너뜀 (--no-clangd)")
        elif want_clangd or ask_yes("\nclangd 프로젝트 인덱스(호출 · 참조 · 영향 범위)를 지금 만들까? "
                                    "백그라운드로 처음 20–30분, 에디터 빌드를 한 번 한 프로젝트여야 한다"):
            log = start_clangd_bg(proj)
            print(f"clangd 프로젝트 인덱스: 백그라운드로 시작했다 — 진행은 로그로 본다: {log}")
        else:
            print("\nclangd 프로젝트 인덱스: 아직 없음 — 나중에 setup.bat <프로젝트> --clangd 또는 index_build.bat 로 만든다")
    print("\n인덱스 지금 만들기: 이 폴더의 index_build.bat 에 프로젝트 폴더를 끌어다 놓는다.")
    print("인덱스 웹뷰: 이 폴더의 index_view.bat 을 더블클릭한다 (프로젝트 폴더를 끌어다 놓으면 그 프로젝트로 연다).")
    if wiki:
        print("위키 다듬기(선택): 프로젝트 폴더에서 Claude Code 를 열고 /wiki-bootstrap — 면담 빈 칸 · 파트 묶기 · 설명 미리 채우기.")
    wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
