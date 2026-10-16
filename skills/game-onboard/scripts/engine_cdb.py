#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""런처 설치 엔진용 엔진 compile_commands.json 을 만든다. 표준 라이브러리만 쓴다.

  python engine_cdb.py --root <프로젝트> [--out <폴더>] [--modules A,B] [--no-generate]

런처 설치 엔진은 엔진 모듈이 미리 빌드돼 있어 UBT 의 GenerateClangDatabase 에도, VS Code 생성기의
`.vscode/compileCommands_<이름>.json` 에도 엔진 .cpp 항목이 없다 (UE 5.7 에서 확인 — 둘 다 엔진 항목 0개).
그런데 VS Code 생성기는 타깃이 쓰는 **모든 모듈의 응답 파일**(`.vscode/compileCommands_<이름>/<모듈>.<번호>.rsp`: /I 와 /FI)을 쓴다.
이 스크립트는 그 rsp 에 엔진 모듈 폴더의 .cpp 를 붙여 항목을 합성한다 — `cl.exe @<모듈>.rsp <파일>`.

순서:
  1. 프로젝트 뼈대(.uproject · Config · Source · Plugins 의 소스만)를 <out>/<이름> 에 복사한다 — 프로젝트 폴더에 .vscode 를 만들지 않으려고.
  2. 거기서 UBT `-projectfiles -VSCode -game -engine -rocket` 를 돌린다 (--no-generate 면 이미 있는 것을 쓴다).
  3. 엔진의 *.Build.cs 로 모듈 폴더를 찾고, rsp 가 있는 엔진 모듈의 .cpp 로 <out>/<이름>/engine/compile_commands.json 을 쓴다.
     항목마다 /std:c++20 (rsp 에 없다)과 빈 .gen.cpp 폴더(/I, gen_stubs 참고)를 붙인다.

그 뒤: cindex.py build --root <프로젝트> --scope engine --cdb <그 파일> --mode bg --unity 8 --keep-error-batches
(모듈 안에서는 플래그가 같아 --unity 로 묶인다. 오류 난 묶음을 풀면 시간이 몇 배가 된다 — references/cindex.md 2절.)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gq  # noqa: E402
import ue_q  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

SKIP_DIRS = {".git", ".vs", ".idea", "binaries", "intermediate", "content", "saved", "deriveddatacache", "node_modules"}
SRC_EXT = {".cs", ".cpp", ".h", ".hpp", ".inl", ".c", ".cc", ".ini", ".uplugin", ".uproject", ".json"}
# Win64 타깃에서 UBT 가 빼는 다른 플랫폼 폴더 (UEBuildPlatform 의 폴더 이름 규칙)
OTHER_PLATFORMS = {"android", "ios", "tvos", "visionos", "mac", "apple", "linux", "linuxarm64", "unix", "hololens",
                   "switch", "ps4", "ps5", "xboxone", "xsx", "xb1", "wingdk", "xboxonegdk"}
CACHE = Path.home() / ".claude" / "cache" / "game-harness" / "engine-cdb"


def skeleton(root, dst):
    """프로젝트 뼈대를 복사한다 — 모듈 그래프(.uproject · .uplugin · Build.cs · Target.cs)와 소스만. 애셋·빌드 산출물은 뺀다."""
    n = 0
    up = next(root.glob("*.uproject"))
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(up, dst / up.name)
    for top in ("Config", "Source", "Plugins"):
        for d, dirs, files in os.walk(root / top):
            dirs[:] = [x for x in dirs if x.lower() not in SKIP_DIRS]
            for f in files:
                if os.path.splitext(f)[1].lower() in SRC_EXT:
                    out = dst / os.path.relpath(os.path.join(d, f), root)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(os.path.join(d, f), out)
                    n += 1
    return dst / up.name, n


def generate(uproject, eng):
    exe = eng / "Binaries" / "DotNET" / "UnrealBuildTool" / ("UnrealBuildTool.exe" if os.name == "nt" else "UnrealBuildTool")
    cmd = [str(exe), "-projectfiles", f"-project={uproject}", "-game", "-engine", "-rocket", "-VSCode"]
    print("실행:", " ".join(cmd), flush=True)
    return subprocess.run(cmd, stdout=subprocess.DEVNULL).returncode


def module_dirs(eng):
    """엔진의 모듈 이름 → 폴더 (<이름>.Build.cs 가 있는 곳). 같은 이름이 둘이면 먼저 찾은 것."""
    out = {}
    for top in ("Source", "Plugins", "Platforms"):
        for d, dirs, files in os.walk(eng / top):
            dirs[:] = [x for x in dirs if x.lower() not in ("binaries", "intermediate", "content", "thirdparty")]
            for f in files:
                if f.endswith(".Build.cs"):
                    out.setdefault(f[:-len(".Build.cs")], Path(d))
    return out


def module_sources(mod_dir):
    """모듈 폴더의 .cpp. 다른 플랫폼 폴더와 안에 든 다른 모듈(자기 Build.cs 가 있는 하위 폴더)은 뺀다."""
    out = []
    for d, dirs, files in os.walk(mod_dir):
        if Path(d) != mod_dir and any(f.endswith(".Build.cs") for f in files):
            dirs[:] = []
            continue
        dirs[:] = [x for x in dirs if x.lower() not in OTHER_PLATFORMS]
        out += [os.path.join(d, f) for f in files if f.lower().endswith(".cpp")]
    return sorted(out)


def gen_stubs(eng, dst):
    """런처 설치 엔진은 .generated.h 만 싣고 .gen.cpp 는 안 싣는다 → `#include UE_INLINE_GENERATED_CPP_BY_NAME(X)` 가
    TU 마다 fatal error 가 되고, 유니티 묶음이 전부 '오류'로 잡혀 원래 TU 로 다시 돈다. .generated.h 마다 빈 X.gen.cpp 를 둔다
    (리플렉션 등록 코드라 색인에는 필요 없다). 반환: 만든 개수."""
    dst.mkdir(parents=True, exist_ok=True)
    have, n = {p.name for p in dst.iterdir()}, 0
    for top in (eng / "Intermediate" / "Build", eng / "Plugins", eng / "Platforms"):
        for d, dirs, files in os.walk(top):
            dirs[:] = [x for x in dirs if x.lower() not in ("binaries", "content", "source", "resources", "config")]
            if os.path.basename(d) != "UHT":
                continue
            for f in files:
                if f.endswith(".generated.h"):
                    name = f[:-len(".generated.h")] + ".gen.cpp"
                    if name not in have:
                        (dst / name).write_text("", encoding="utf-8")
                        have.add(name)
                        n += 1
    return n


def synthesize(vscode, eng, out, only=None, stubs=None):
    """(.vscode 폴더, 엔진 폴더) → out/compile_commands.json. 반환: (모듈 수, TU 수, rsp 는 있는데 폴더를 못 찾은 모듈 수)."""
    cc = next(iter(sorted(vscode.glob("compileCommands_*.json"))), None)
    if cc is None:
        raise FileNotFoundError(f"{vscode} 에 compileCommands_*.json 이 없다")
    first = json.loads(cc.read_text(encoding="utf-8"))[0]
    cl = first["arguments"][0] if "arguments" in first else first["command"].split(" @")[0].strip('"')
    rsp_dir = vscode / cc.stem
    dirs, entries, mods, missing = module_dirs(eng), [], 0, 0
    extra = ["/std:c++20"] + ([f"/I{stubs}"] if stubs else [])  # rsp 에는 /I 와 /FI 뿐이다
    for rsp in sorted(rsp_dir.glob("*.rsp")):
        name = rsp.name.rsplit(".", 2)[0]
        if only and name not in only:
            continue
        if name not in dirs:
            missing += 1  # 프로젝트·프로젝트 플러그인 모듈이거나 이름이 폴더와 다른 모듈
            continue
        files = module_sources(dirs[name])
        if files:
            mods += 1
            entries += [{"directory": str(eng / "Source"), "file": f, "arguments": [cl, f"@{rsp}", *extra, f]} for f in files]
    out.mkdir(parents=True, exist_ok=True)
    (out / "compile_commands.json").write_text(json.dumps(entries, indent=1), encoding="utf-8")
    return mods, len(entries), missing


def main():
    ap = argparse.ArgumentParser(description="런처 설치 엔진용 엔진 compile_commands.json 합성")
    ap.add_argument("--root", default=".", help="프로젝트 폴더")
    ap.add_argument("--out", default=None, help=f"작업 폴더 (기본 {CACHE})")
    ap.add_argument("--modules", default=None, help="이 모듈만 (쉼표로 구분) — 시험용")
    ap.add_argument("--no-generate", action="store_true", help="뼈대 복사와 UBT 를 건너뛰고 이미 만든 .vscode 를 쓴다")
    a = ap.parse_args()
    root, kind, _ = gq.detect(a.root)
    if root is None or kind != "ue":
        print("UE 프로젝트(.uproject)를 찾지 못했다.")
        return 2
    eng = ue_q.engine_root(root)
    if not eng or not (eng / "Source").is_dir():
        print("엔진 폴더를 못 찾았다 — index_all.py --engine-root 로 지정한다.")
        return 2
    work = (Path(a.out) if a.out else CACHE) / root.name
    if not a.no_generate:
        uproject, n = skeleton(root, work)
        print(f"뼈대 복사 {n}개 → {work}")
        rc = generate(uproject, eng)
        if rc != 0:
            print(f"UBT 프로젝트 파일 생성 실패 (종료 {rc})")
            return 1
    only = {m.strip() for m in a.modules.split(",") if m.strip()} if a.modules else None
    out = work / ("engine" if not only else "engine-" + "-".join(sorted(only))[:60])
    stubs = work / "gen-stubs"
    made = gen_stubs(eng, stubs)
    mods, tus, missing = synthesize(work / ".vscode", eng, out, only, stubs)
    print(f"엔진 모듈 {mods} · TU {tus} · 엔진 밖 모듈 {missing} · 빈 .gen.cpp {made}개 추가 → {out / 'compile_commands.json'}")
    return 0 if tus else 1


if __name__ == "__main__":
    sys.exit(main())
