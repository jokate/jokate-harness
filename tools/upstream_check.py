#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""빌려 온 바깥 스킬의 원본이 바뀌었나 — 원본과 하네스에 둔 사본을 비교한다.

  python tools/upstream_check.py            # 바뀐 원본과 옮긴 곳을 보인다 (플러그인 원본만, 네트워크 없음)
  python tools/upstream_check.py --remote   # GitHub 원본(kind: git)도 받아 비교한다
  python tools/upstream_check.py --diff     # 바뀐 원본의 줄 차이까지
  python tools/upstream_check.py --accept   # 옮긴 곳을 검토한 뒤: 사본 · 버전 · 커밋을 지금 원본으로 올린다

원본 종류 두 가지 (docs/third_party/upstream.json 의 sources[].kind):
- plugin (기본): 설치된 플러그인(자동 업데이트) 폴더와 비교한다.
- git: 깔지 않는 원본(AI-DLC 처럼 설치기가 PATH 를 바꾸는 것). --remote 일 때만 GitHub 에서 받아 비교한다.
  네트워크가 안 되면 "확인 못 함" — "그대로"와 다르다.
하네스에 복사해 고친 글은 원본 업데이트를 받지 못한다. 그래서 원본 사본(docs/third_party/<이름>/)을 두고,
원본이 바뀌면 무엇을 다시 볼지 알린다. install.py 끝에서도 한 줄 낸다(네트워크 없이).
"""
import argparse
import difflib
import json
import shutil
import sys
import urllib.error
import urllib.request
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


def _gh_slug(url):
    return url.rstrip("/").removesuffix(".git").split("github.com/")[-1]


def github_fetch(repo_url, branch, path=None, timeout=10):
    """path 가 없으면 branch 의 최신 커밋 sha, 있으면 그 파일 바이트(없는 파일은 None). 네트워크 실패는 OSError."""
    slug = _gh_slug(repo_url)
    url = (f"https://api.github.com/repos/{slug}/commits/{branch}" if path is None
           else f"https://raw.githubusercontent.com/{slug}/{branch}/{path}")
    req = urllib.request.Request(url, headers={"User-Agent": "game-harness-upstream-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404 and path is not None:
            return None
        raise OSError(f"HTTP {e.code}") from e
    return json.loads(data)["sha"] if path is None else data


def _check_git(s, repo, remote, fetch):
    row = {"name": s["name"], "kind": "git", "version": s["version"], "commit": s.get("commit", ""), "changed": []}
    if not remote:
        row.update(status="offline", now=None)
        return row
    branch = s.get("branch", "main")
    try:
        sha = fetch(s["repo"], branch)
        got = {b["upstream"]: fetch(s["repo"], branch, b["upstream"]) for b in s["borrowed"]}
    except (OSError, ValueError, KeyError) as e:
        row.update(status="unreachable", now=None, error=str(e))
        return row
    row["now"], row["_sha"], row["_got"] = sha[:7], sha, got
    for b in s["borrowed"]:
        new, old = got[b["upstream"]], repo / s["snapshot"] / b["upstream"]
        if new is None:
            row["changed"].append((b["upstream"], b["into"], "원본에서 사라짐"))
        elif not old.is_file() or new.replace(b"\r\n", b"\n") != _text(old):
            row["changed"].append((b["upstream"], b["into"], "바뀜"))
    row["status"] = "changed" if row["changed"] else "same"
    return row


def check(spec_path=SPEC, home=None, repo=REPO, remote=False, fetch=github_fetch):
    """원본마다 {name, status: same|changed|absent|offline|unreachable, version, now, changed: [(upstream, into, 상태)]}."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = []
    for s in spec["sources"]:
        if s.get("kind", "plugin") == "git":
            out.append(_check_git(s, Path(repo), remote, fetch))
            continue
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
        where = "원격" if r.get("kind") == "git" else "설치"
        if r["status"] == "absent":
            lines.append(f"빌려 온 원본 {r['name']}: 플러그인이 없어 비교 못 함 (깔려면 claude plugin install {r['plugin']})")
        elif r["status"] == "offline":
            lines.append(f"빌려 온 원본 {r['name']}: 원격 비교는 python tools/upstream_check.py --remote "
                         f"(사본 {r['version']} · {r['commit'][:7]})")
        elif r["status"] == "unreachable":
            lines.append(f"빌려 온 원본 {r['name']}: 확인 못 함 — 원격에 닿지 않음 ({r.get('error', '')}). 그대로라는 뜻이 아니다")
        elif r["status"] == "same":
            lines.append(f"빌려 온 원본 {r['name']}: 그대로 (사본 {r['version']} · {where} {r['now']})")
        else:
            flag = " --remote" if r.get("kind") == "git" else ""
            lines.append(f"빌려 온 원본 {r['name']}: {len(r['changed'])}개 바뀜 (사본 {r['version']} → {where} {r['now']}) "
                         f"— python tools/upstream_check.py{flag} 로 옮긴 곳을 본다")
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
            if r.get("kind") == "git":
                dst.write_bytes(r["_got"][up])
            else:
                shutil.copyfile(r["_root"] / up, dst)
        if r.get("kind") == "git":
            s["version"], s["commit"] = f"{s.get('branch', 'main')}@{r['now']}", r["_sha"]
        else:
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
    ap.add_argument("--remote", action="store_true", help="GitHub 원본(kind: git)도 받아 비교")
    a = ap.parse_args(argv)
    rows = check(remote=a.remote)
    for line in summary(rows):
        print(line)
    spec = {s["name"]: s for s in json.loads(SPEC.read_text(encoding="utf-8"))["sources"]}
    for r in rows:
        for up, into, state in r["changed"]:
            print(f"- {up} ({state}) → 다시 볼 곳: {', '.join(into)}")
            if a.diff and state == "바뀜":
                old = REPO / spec[r["name"]]["snapshot"] / up
                a_lines = _text(old).decode("utf-8", "replace").splitlines() if old.is_file() else []
                new = r["_got"][up].replace(b"\r\n", b"\n") if r.get("kind") == "git" else _text(r["_root"] / up)
                b_lines = new.decode("utf-8", "replace").splitlines()
                sys.stdout.writelines(l + "\n" for l in difflib.unified_diff(a_lines, b_lines, "사본", "원본", lineterm=""))
    if a.accept:
        done = accept(rows)
        print("사본을 올렸다:", ", ".join(done) if done else "없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
