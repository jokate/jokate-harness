#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""인덱스를 지금 한 번에 만든다 (저장소의 index_build.bat 이 부른다). 표준 라이브러리만 쓴다.

  python index_all.py [프로젝트 폴더] [--engine-root <엔진 폴더>] [--no-clangd] [--cdb] [--engine]

프로젝트 폴더를 안 주면: 지금 폴더가 프로젝트면 그것, 아니면 하네스 이벤트 로그의 가장 최근 프로젝트 (index_view.py 와 같다).

순서 — 빨리 끝나고 자주 쓰는 것부터:
  1. 프로젝트 좌표     gq.py index                                  몇 초
  2. 엔진 좌표         ue_q.py index                                처음 한 번 오래, 그 뒤 바뀐 파일만 (UE)
  3. compile_commands  cindex.py cdb                                없을 때만, --cdb 면 다시 (UE, 에디터 빌드를 한 번 한 뒤)
  4. clangd 프로젝트   cindex.py build --mode bg                    두 번째부터 바뀐 것만 (clangd 가 없고 clangd-indexer 만 있으면 전체 색인)
  5. clangd 엔진       cindex.py build --scope engine --unity 8     엔진 clangd 인덱스가 없을 때만, --engine 이면 다시. 엔진 버전당 한 번, 오래 걸린다
  6. clangd 조회 정리  cindex.py optimize                           옛 모양 인덱스를 조회용으로 다시 쓰고(색인은 그대로) 소유권 표시를 맞춘다
  --no-clangd 면 1·2 만.

각 단계는 따로 돈다 — 하나가 실패해도 다음 단계로 간다. 앞 단계의 결과가 필요한 단계는 이유를 적고 건너뛴다.
끝에 단계별 결과를 낸다. 실패가 하나라도 있으면 종료 코드 1, 프로젝트를 못 찾으면 2.
엔진 위치는 ue_q.py 와 같다: 환경 변수 UE_ROOT > 이 프로젝트용으로 저장한 경로 > .uproject EngineAssociation + 레지스트리
> C:/Unreal/UE_5.7/Engine. --engine-root 를 주면 이번 실행에 쓰고 이 프로젝트용으로 저장한다 — 다음 실행과 조회 도구(ue_q·cindex·웹뷰)도
그 엔진을 쓴다. 못 찾았는데 대화형 창(더블클릭한 bat)이면 경로를 묻는다. 소스 빌드 엔진(EngineAssociation 이 GUID)처럼 레지스트리로
못 찾는 엔진에 쓴다.
"""
import argparse
import os
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cindex  # noqa: E402
import cindex_speed  # noqa: E402
import gq  # noqa: E402
import ue_q  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

DONE, SKIP, FAIL = "완료", "건너뜀", "실패"


def resolve_project(arg):
    """(루트, 종류, 안내). 프로젝트(.uproject / Unity)가 아니면 루트 None — 엉뚱한 폴더에 인덱스를 만들지 않는다."""
    note = None
    if arg:
        start = arg
    else:
        from index_view import _harness_events, resolve_root
        start, note = resolve_root(None, _harness_events())
    root, kind, _ = gq.detect(start)
    return root, kind, note


def cols(s):
    """터미널 칸 수 — 한글은 두 칸이다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s, width):
    return s + " " * max(0, width - cols(s))


def ask_engine():
    """엔진 폴더를 묻는다. 비우면 None (엔진 없이 진행)."""
    print("\n엔진 폴더를 못 찾았다. 엔진 폴더 경로를 넣는다 (예: D:\\UE_5.7 또는 D:\\UE_5.7\\Engine — 탐색기에서 폴더를 이 창에 "
          "끌어다 놓아도 된다). 이 프로젝트용으로 저장한다. 비우고 Enter 면 엔진 없이 진행:", flush=True)
    while True:
        try:
            text = input("> ")
        except EOFError:
            return None
        if not text.strip():
            return None
        eng = ue_q.as_engine_dir(text)
        if eng:
            return eng
        print(f"엔진 폴더가 아니다 (Source/Runtime 이 없다): {text.strip()} — 다시 넣거나 비운다", flush=True)


def set_engine(root, eng):
    """이번 실행의 하위 단계가 이 엔진을 쓰게 하고(UE_ROOT), 이 프로젝트용으로 저장한다."""
    other = os.environ.get("UE_ROOT")
    if other and ue_q.as_engine_dir(other) != eng:
        print(f"[참고] 환경 변수 UE_ROOT={other} 가 있다 — 조회 도구는 UE_ROOT 를 저장값보다 먼저 쓴다. 이번 실행만 {eng} 로 한다.")
    ue_q.save_engine_root(root, eng)
    os.environ["UE_ROOT"] = str(eng)
    ue_q.engine_source.cache_clear()
    print(f"엔진 폴더 저장: {root.name} → {eng} ({ue_q.engine_roots_path()})")


def run(title, script, args, root):
    """하위 스크립트를 같은 파이썬으로 돌리고 출력은 그대로 흘린다. (상태, 걸린 초, 메모)"""
    cmd = [sys.executable, str(HERE / script), *args]
    print(f"\n=== {title} ===\n> {script} {' '.join(args)}", flush=True)
    t0 = time.time()
    try:
        rc = subprocess.run(cmd, cwd=str(root)).returncode
    except OSError as e:
        return FAIL, time.time() - t0, str(e)
    return (DONE if rc == 0 else FAIL), time.time() - t0, "" if rc == 0 else f"종료 코드 {rc}"


def engine_tus(cdb, root, eng):
    """compile_commands.json 에서 엔진 폴더 아래 번역 단위 수. 런처 설치 엔진이면 0 이다 (엔진 모듈이 미리 빌드돼 있어서)."""
    try:
        return len(cindex_speed.filter_entries(cindex_speed.entries_of(cdb), cindex.default_filter("engine", root, eng)))
    except (OSError, ValueError, KeyError) as e:
        print(f"  compile_commands.json 을 읽지 못했다: {e}")
        return 0


def main():
    ap = argparse.ArgumentParser(description="인덱스를 지금 한 번에 만든다 (gq → ue_q → clangd)")
    ap.add_argument("root", nargs="?", default=None, help="프로젝트 폴더 (없으면 지금 폴더 또는 최근 프로젝트)")
    ap.add_argument("--engine-root", default=None, help="엔진 폴더 (UE_5.7 또는 UE_5.7/Engine). 이 프로젝트용으로 저장한다")
    ap.add_argument("--no-clangd", action="store_true", help="정규식 인덱스(gq·ue_q)만 만든다")
    ap.add_argument("--cdb", action="store_true", help="compile_commands.json 이 있어도 다시 만든다 (모듈·파일을 더했을 때)")
    ap.add_argument("--engine", action="store_true", help="엔진 clangd 인덱스가 있어도 다시 만든다 (오래 걸린다)")
    a = ap.parse_args()

    root, kind, note = resolve_project(a.root)
    if note:
        print(note)
    if root is None:
        print("프로젝트(.uproject 또는 Unity 프로젝트)를 찾지 못했다 — 프로젝트 폴더를 index_build.bat 위에 끌어다 놓거나 "
              "`index_all.py <프로젝트 폴더>` 로 준다.")
        return 2
    eng, how = (ue_q.engine_source(root) if kind == "ue" else (None, ""))
    if kind == "ue" and a.engine_root:
        eng = ue_q.as_engine_dir(a.engine_root)
        if not eng:
            print(f"엔진 폴더가 아니다 (Source/Runtime 이 없다): {a.engine_root}")
            return 2
        set_engine(root, eng)
        how = "--engine-root"
    eng_ok = bool(eng and (eng / "Source").is_dir())
    if kind == "ue" and not eng_ok:
        print("엔진 폴더를 못 찾았다. 찾아본 곳:\n  " + "\n  ".join(ue_q.engine_report(root)), flush=True)
    if kind == "ue" and not eng_ok and sys.stdin.isatty():
        try:
            given = ask_engine()
        except KeyboardInterrupt:
            print("\n중단")
            return 1
        if given:
            set_engine(root, given)
            eng, how, eng_ok = given, "입력", True
    print(f"프로젝트 {root} · {kind}" + (f" · 엔진 {eng} ({how if eng_ok else '없음 — --engine-root 로 지정'})"
                                        if kind == "ue" else ""))
    r = str(root)
    steps = []  # (제목, 상태, 초, 메모)
    current = [None]

    def step(title, script, args):
        current[0] = title
        st, sec, memo = run(title, script, args, root)
        steps.append((title, st, sec, memo))
        current[0] = None
        return st

    def skip(title, why):
        steps.append((title, SKIP, 0.0, why))

    t_all = time.time()
    try:
        step("1 프로젝트 좌표 (gq)", "gq.py", ["index", "--root", r])
        if kind == "ue":
            step("2 엔진 좌표 (ue_q)", "ue_q.py", ["index", "--root", r])
        else:
            skip("2 엔진 좌표 (ue_q)", "UE 프로젝트가 아니다")

        titles = ("3 compile_commands.json", "4 clangd 프로젝트", "5 clangd 엔진", "6 clangd 조회 정리")
        clangd, indexer = cindex.find_clangd(None), cindex.find_indexer(None)
        if a.no_clangd:
            for t in titles:
                skip(t, "--no-clangd")
        elif kind != "ue":
            for t in titles:
                skip(t, "UE 프로젝트가 아니다")
        elif not (clangd or indexer):
            for t in titles:
                skip(t, "clangd·clangd-indexer 를 못 찾았다 — setup.bat 을 다시 돌리면 설치한다 (clangd_tools.py install)")
        else:
            cdb = cindex.resolve_cdb(None, root, eng)
            if cdb and not a.cdb:
                skip(titles[0], f"있음 {cdb} (다시 만들려면 --cdb)")
            else:
                step(titles[0], "cindex.py", ["cdb", "--root", r])
                cdb = cindex.resolve_cdb(None, root, eng)
            if not cdb:
                skip(titles[1], "compile_commands.json 이 없다 (3단계 출력을 본다)")
                skip(titles[2], "compile_commands.json 이 없다 (3단계 출력을 본다)")
                skip(titles[3], "compile_commands.json 이 없다 (3단계 출력을 본다)")
            else:
                if clangd:
                    step(titles[1], "cindex.py", ["build", "--root", r, "--mode", "bg"])
                else:
                    step(titles[1], "cindex.py", ["build", "--root", r])
                edb = cindex.db_for("engine", root, kind)
                if not eng_ok:
                    skip(titles[2], "엔진 폴더를 못 찾았다 — --engine-root 로 지정")
                elif edb and edb.exists() and not a.engine:
                    skip(titles[2], f"있음 {edb} (엔진 버전당 한 번 — 다시 만들려면 --engine)")
                elif engine_tus(cdb, root, eng) == 0:
                    skip(titles[2], f"{cdb.name} 에 엔진 번역 단위가 없다 — 런처 설치 엔진이면 references/cindex.md 2절대로 "
                                    "cindex.py build --scope engine --cdb <.vscode/compileCommands_이름.json> --extra-arg=/std:c++20")
                else:
                    mode = [] if indexer else ["--mode", "bg"]
                    print("\n엔진 clangd 색인은 엔진 버전당 한 번이고 오래 걸린다." +
                          (" clangd-indexer 는 중간에 멈추면 처음부터 다시 한다." if indexer else ""), flush=True)
                    step(titles[2], "cindex.py", ["build", "--root", r, "--scope", "engine", "--unity", "8", *mode])
                if any(d and d.exists() for d in (cindex.db_for("project", root, kind), edb)):
                    step(titles[3], "cindex.py", ["optimize", "--root", r])
                else:
                    skip(titles[3], "clangd 인덱스가 없다")
    except KeyboardInterrupt:
        steps.append((current[0] or "(중단)", FAIL, 0.0, "Ctrl+C 로 중단 — 다시 돌린다"))

    print(f"\n=== 결과 · {root.name} · {time.time() - t_all:.0f}s ===")
    w = max(cols(t) for t, *_ in steps)
    for t, st, sec, memo in steps:
        took = f"{sec:6.1f}s" if st != SKIP else " " * 7
        print(f"  {pad(t, w)}  {pad(st, 6)}  {took}  {memo}".rstrip())
    return 1 if any(st == FAIL for _, st, _, _ in steps) else 0


if __name__ == "__main__":
    sys.exit(main())
