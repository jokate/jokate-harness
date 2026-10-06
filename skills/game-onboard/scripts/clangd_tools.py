#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clangd 도구(clangd · clangd-indexer)를 ~/.claude/tools/clangd 에 내려받아 설치한다. install.py(setup)가 부른다. 표준 라이브러리만 쓴다.

  python clangd_tools.py install [--force]   # 못 찾는 것만 설치한다 (PATH·CLANGD 등에 이미 있으면 그것을 쓴다)
  python clangd_tools.py status
  python clangd_tools.py remove              # 이 스크립트가 설치한 파일만 지운다 (uninstall.py --purge 가 부른다)

받는 것: github.com/clangd/clangd 릴리스 23.1.0 의 clangd-<os>-23.1.0.zip · clangd_indexing_tools-<os>-23.1.0.zip.
  버전을 고정한다 — cindex 의 RIFF 리더(clangd_riff.py)와 시험이 이 버전 출력으로 검증됐다. 받은 zip 은 SHA-256 을 대조한다.
푸는 것: bin/clangd(.exe) · bin/clangd-indexer(.exe) · lib/clang/23/{include,share}
  (clang 내장 헤더 — 실행 파일이 ../lib/clang/<버전> 에서 찾는다). lib/clang/23/lib 는 링크용 컴파일러 런타임이라 색인에 안 쓰여 뺀다.
내려받는 양: Windows 약 63MB(설치 뒤 약 110MB), 리눅스 약 280MB, 맥 약 210MB.
프록시: 환경 변수 HTTPS_PROXY, Windows 는 인터넷 설정의 프록시도 따른다 (urllib 기본 동작).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

VERSION, MAJOR = "23.1.0", "23"
BASE = f"https://github.com/clangd/clangd/releases/download/{VERSION}/"
SHA256 = {  # 2026-10-06 에 받은 릴리스 자산
    "clangd-windows-23.1.0.zip": "23412a240756a162e7b98a282f36aa2a23a88db5ce16a0cbc4fef7253768c810",
    "clangd_indexing_tools-windows-23.1.0.zip": "af61d011d87bdf577db45c46f05a10a4f98842027be21c642a336b95f6149e71",
    "clangd-linux-23.1.0.zip": "e53b1a96196095faedb7642cf64964f7fb9ad4a0c1f00dd2c172a3d9dcbafdfd",
    "clangd_indexing_tools-linux-23.1.0.zip": "48259f33a0684760fdb363be036eb5c6f707fbeb0877e5fff58d1e6cc308a763",
    "clangd-mac-23.1.0.zip": "1082e6638223b785ca2daf0939f13afcd0bb95c84ee9a4bbaff4745365159253",
    "clangd_indexing_tools-mac-23.1.0.zip": "cb1097ba1178d03a7759c94dc8e0e62ef4f8b06d5f4d87f0043b2fb6730755ee",
}
EXE = ".exe" if os.name == "nt" else ""
# 도구 이름 → 릴리스 zip 접두사 (cindex.find_clangd / find_indexer 가 찾는 이름과 같다)
PARTS = {"clangd": "clangd", "clangd-indexer": "clangd_indexing_tools"}


def tools_dir():
    return Path.home() / ".claude" / "tools" / "clangd"


def marker_path():
    return tools_dir() / "game-harness-tools.json"


def platform_tag():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("linux"):
        return "linux"
    return None


def found():
    """{도구: 경로|None} — cindex 가 실제로 쓸 것과 같은 순서로 찾는다."""
    import cindex
    return {"clangd": cindex.find_clangd(None), "clangd-indexer": cindex.find_indexer(None)}


def version_of(exe):
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    line = next((ln.strip() for ln in (r.stdout + r.stderr).splitlines() if "version" in ln.lower()), "")
    return (line or None), (None if r.returncode == 0 else f"종료 코드 {r.returncode}")


def load_marker():
    try:
        return json.loads(marker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def download(name, dst):
    """받으면서 SHA-256 을 계산하고 고정값과 대조한다. 다르면 ValueError."""
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "game-harness"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        total, done, shown = int(r.headers.get("Content-Length") or 0), 0, -1
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            step = done * 10 // total if total else -1
            if step != shown:
                shown = step
                print(f"\r  {name}  {done / 1e6:.0f}/{total / 1e6:.0f}MB", end="", flush=True)
    print()
    if h.hexdigest() != SHA256[name]:
        raise ValueError(f"{name} 의 SHA-256 이 고정값과 다르다 — 받은 파일을 쓰지 않는다 ({h.hexdigest()})")


def extract(zpath, keep, dest):
    """zip 의 맨 위 폴더(clangd_23.1.0/)를 떼고 keep(상대 경로)가 참인 파일만 dest 아래로 푼다. 푼 상대 경로 목록."""
    out = []
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            parts = info.filename.split("/", 1)
            if info.is_dir() or len(parts) < 2 or not parts[1] or not keep(parts[1]):
                continue
            rel = parts[1]
            if rel.startswith(("/", "\\")) or ".." in rel.replace("\\", "/").split("/"):
                raise ValueError(f"zip 안의 경로가 이상하다: {info.filename}")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as f:
                shutil.copyfileobj(src, f, 1 << 20)
            mode = (info.external_attr >> 16) & 0o777
            if mode and os.name != "nt":
                os.chmod(target, mode)
            out.append(rel)
    return out


def install(force):
    tag = platform_tag()
    if not tag:
        print(f"이 OS({sys.platform}) 용 clangd 릴리스가 없다 — clangd 단계는 빠지고 나머지는 동작한다.")
        return 1
    have = found()
    need = [t for t, p in have.items() if force or not p]
    for t, p in have.items():
        if t not in need:
            print(f"  = {t} 있음: {p}")
    if not need:
        return 0
    root = tools_dir()
    root.parent.mkdir(parents=True, exist_ok=True)
    print(f"  clangd {VERSION} 내려받기 → {root}  ({', '.join(need)})")
    headers = f"lib/clang/{MAJOR}/"
    written = set(load_marker().get("files", []))
    try:
        with tempfile.TemporaryDirectory(dir=root.parent, prefix="clangd-dl-") as tmp:
            tmp = Path(tmp)
            stage = tmp / "stage"
            done_headers = False
            for tool in need:
                name = f"{PARTS[tool]}-{tag}-{VERSION}.zip"
                zpath = tmp / name
                download(name, zpath)

                def keep(rel, tool=tool, with_headers=not done_headers):
                    if rel == f"bin/{tool}{EXE}":
                        return True
                    return with_headers and rel.startswith(headers) and not rel.startswith(headers + "lib/")
                written.update(extract(zpath, keep, stage))
                done_headers = True
                zpath.unlink()
            for src in sorted(p for p in stage.rglob("*") if p.is_file()):
                dst = root / src.relative_to(stage)
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dst)
    except Exception as e:  # noqa: BLE001 — 네트워크·디스크·해시 어느 쪽이든 setup 을 멈추지 않고 이유만 알린다
        print(f"\n  [실패] {type(e).__name__}: {e}")
        return 1
    marker_path().write_text(json.dumps({"version": VERSION, "files": sorted(written)}, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    rc = 0
    for tool in need:
        exe = root / "bin" / f"{tool}{EXE}"
        ver, err = version_of(exe)
        if err:
            print(f"  [실패] {exe} 가 실행되지 않는다 ({err}) — CPU 종류가 릴리스와 다를 수 있다 (릴리스는 x86-64)")
            rc = 1
        else:
            print(f"  + {tool}: {exe} · {ver}")
    return rc


def status():
    for t, p in found().items():
        if p:
            ver, err = version_of(p)
            print(f"{t}: {p} · {ver or err}")
        else:
            print(f"{t}: 없음 — `python clangd_tools.py install` 또는 setup.bat")
    m = load_marker()
    print(f"이 스크립트가 설치한 것: {tools_dir()} · clangd {m['version']} · 파일 {len(m.get('files', []))}" if m else
          "이 스크립트가 설치한 것: 없음")
    return 0


def remove(dry):
    m = load_marker()
    root = tools_dir()
    if not m:
        print(f"  = {root} 에 이 하네스가 설치한 clangd 도구 없음")
        return 0
    files = [root / rel for rel in m.get("files", [])] + [marker_path()]
    print(f"  - {root} 의 clangd {m.get('version')} ({len(files) - 1}개 파일)")
    if dry:
        return 0
    for f in files:
        try:
            f.unlink()
        except FileNotFoundError:
            pass
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()  # 비었을 때만 — 사용자가 둔 파일은 남는다
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass
    return 0


def main():
    ap = argparse.ArgumentParser(description="clangd 도구 설치 (clangd · clangd-indexer)")
    ap.add_argument("command", choices=["install", "status", "remove"])
    ap.add_argument("--force", action="store_true", help="install: 이미 있어도 이 버전으로 다시 받는다")
    ap.add_argument("--dry-run", action="store_true", help="remove: 지울 것만 보인다")
    a = ap.parse_args()
    if a.command == "install":
        return install(a.force)
    if a.command == "remove":
        return remove(a.dry_run)
    return status()


if __name__ == "__main__":
    sys.exit(main())
