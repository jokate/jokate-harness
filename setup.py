#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""game-harness 한 번에 세팅. setup.bat 이 부른다.

  python setup.py [프로젝트 폴더]

1) 스킬·훅 설치 + settings.json 훅 등록 (install.py --link --force --apply-settings)
2) 프로젝트 세팅 (bootstrap.py --auto). 폴더를 안 주면 물어본다.
3) 사용법 출력
다시 돌려도 된다. 이미 된 부분은 건너뛴다.
"""
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


def main():
    print("[1/2] 설치 — 스킬, 훅, 설정")
    rc = subprocess.run([sys.executable, str(REPO / "install.py"), "--link", "--force", "--apply-settings"]).returncode
    if rc != 0:
        print("\n[오류] 설치에 실패했다. 위 메시지를 확인한다.")
        wait()
        return rc

    print("\n[2/2] 프로젝트 세팅")
    target = sys.argv[1].strip().strip('"') if len(sys.argv) > 1 else ask_project()
    if not target:
        print("건너뛰었다. 나중에 프로젝트 폴더를 setup.bat 위에 끌어다 놓으면 된다.")
        wait()
        return 0
    rc = subprocess.run([sys.executable, str(BOOTSTRAP), target, "--auto"]).returncode
    if rc != 0:
        print("\n[오류] 프로젝트 세팅에 실패했다. 폴더 경로가 맞는지 확인한다.")
    else:
        print("\n인덱스 웹뷰: 이 폴더의 index_view.bat 을 더블클릭한다 (프로젝트 폴더를 끌어다 놓으면 그 프로젝트로 연다).")
    wait()
    return rc


if __name__ == "__main__":
    sys.exit(main())
