#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""빌려 온 바깥 스킬의 원본이 바뀌었나 — 설치된 플러그인(자동 업데이트)과 하네스에 둔 사본을 비교한다.

  python tools/upstream_check.py            # 바뀐 원본과 옮긴 곳을 보인다
  python tools/upstream_check.py --diff     # 바뀐 원본의 줄 차이까지
  python tools/upstream_check.py --accept   # 옮긴 곳을 검토한 뒤: 사본 · 버전 · 커밋을 지금 설치본으로 올린다

하네스에 복사해 고친 글은 원본 업데이트를 받지 못한다. 그래서 원본 사본(docs/third_party/<이름>/)을 두고,
플러그인이 업데이트되면 무엇을 다시 볼지 알린다. 대응표: docs/third_party/upstream.json. install.py 끝에서도 한 줄 낸다.
"""
import argparse
import difflib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "docs" / "third_party" / "upstream.json"


def _text(p):
    return p.read_bytes().replace(b"\r\n", b"\n")  # Windows 체크아웃의 CRLF 를 차이로 세지 않는다


def installed(plugin, home=None):
    """설치 기록에서 (설치 경로, 버전, 커밋) — 없으면 None."""
    f = Path(home or Path.home()) / ".claude" / "plugins" / "installed_plugins.json"
    try:
        rows = json.loads(f.read_text(encoding="utf-8")).get("plugins", {}).get(plugin) or []
    except (OSError, ValueError):
        return None
    rows = [r for r in rows if isinstance(r, dict) and r.get("installPath")]
    if not rows:
        return None
    r = next((r for r in rows if r.get("scope") == "user"), rows[0])
    return Path(r["installPath"]), r.get("version", "?"), r.get("gitCommitSha", "")


def check(spec_path=SPEC, home=None, repo=REPO):
    """원본마다 {name, plugin, status: same|changed|absent, version, now, changed: [(upstream, into, 상태)]}."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = []
    for s in spec["sources"]:
        got = installed(s["plugin"], home)
        row = {"name": s["name"], "plugin": s["plugin"], "version": s["version"], "changed": []}
        if got is None:
            row.update(status="absent", now=None)
            out.append(row)
            continue
        root, ver, sha = got
        row["now"] = ver
        for b in s["borrowed"]:
            new, old = root / b["upstream"], repo / s["snapshot"] / b["upstream"]
            if not new.is_file():
                row["changed"].append((b["upstream"], b["into"], "원본에서 사라짐"))
            elif not old.is_file() or _text(new) != _text(old):
                row["changed"].append((b["upstream"], b["into"], "바뀜"))
        row["status"] = "changed" if row["changed"] else "same"
        row["_root"], row["_sha"] = root, sha
        out.append(row)
    return out


def summary(rows):
    """install.py 가 쓰는 한두 줄."""
    lines = []
    for r in rows:
        if r["status"] == "absent":
            lines.append(f"빌려 온 원본 {r['name']}: 플러그인이 없어 비교 못 함 (깔려면 claude plugin install {r['plugin']})")
        elif r["status"] == "same":
            lines.append(f"빌려 온 원본 {r['name']}: 그대로 (사본 {r['version']} · 설치 {r['now']})")
        else:
            lines.append(f"빌려 온 원본 {r['name']}: {len(r['changed'])}개 바뀜 (사본 {r['version']} → 설치 {r['now']}) "
                         "— python tools/upstream_check.py 로 옮긴 곳을 본다")
    return lines


def accept(rows, spec_path=SPEC, repo=REPO):
    """사본을 지금 설치본으로 올리고 버전 · 커밋을 기록한다(옮긴 곳 검토는 사람이 먼저)."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    done = []
    for r in rows:
        if r["status"] != "changed":
            continue
        s = next(x for x in spec["sources"] if x["name"] == r["name"])
        for up, _into, state in r["changed"]:
            dst = repo / s["snapshot"] / up
            if state == "원본에서 사라짐":
                continue  # 사본은 남긴다 — 옮긴 곳을 어떻게 할지는 사람이 정한다
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(r["_root"] / up, dst)
        s["version"], s["commit"] = r["now"], r["_sha"] or s["commit"]
        done.append(r["name"])
    Path(spec_path).write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return done


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--accept", action="store_true")
    a = ap.parse_args(argv)
    rows = check()
    for line in summary(rows):
        print(line)
    spec = {s["name"]: s for s in json.loads(SPEC.read_text(encoding="utf-8"))["sources"]}
    for r in rows:
        for up, into, state in r["changed"]:
            print(f"- {up} ({state}) → 다시 볼 곳: {', '.join(into)}")
            if a.diff and state == "바뀜":
                old = REPO / spec[r["name"]]["snapshot"] / up
                a_lines = _text(old).decode("utf-8", "replace").splitlines() if old.is_file() else []
                b_lines = _text(r["_root"] / up).decode("utf-8", "replace").splitlines()
                sys.stdout.writelines(l + "\n" for l in difflib.unified_diff(a_lines, b_lines, "사본", "설치본", lineterm=""))
    if a.accept:
        done = accept(rows)
        print("사본을 올렸다:", ", ".join(done) if done else "없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
