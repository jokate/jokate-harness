#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실제 diff 로 diff-proto 페이지를 만든다 (git · svn · 패치 파일). 스킬 diff-proto 가 쓴다.

  python diffdoc.py <이야기.json> [--path <저장소나 하위 폴더>] [--base <리비전>] [--patch <파일>] [--add <파일> …]
                    [--doc <설계.md>] [--check] [--force] [--project <루트>] [--keep] [--no-open] [--timeout <분>]

코드는 diff 에서만 온다. 이야기(JSON)는 그룹의 제목 · 왜 · 볼 것 · 위험과, 어느 hunk 가 그 그룹인지만 적는다.
- 이야기가 diff 에 없는 파일을 가리키면 멈춘다(--force 로 넘긴다). 없는 변경을 설명하는 문서를 막는다.
- 그룹은 핵심만 담는다. 어느 그룹에도 안 든 hunk 는 '나머지 변경' 으로 접혀 나오고 판정하지 않는다.
  사용자는 모든 코드를 보지 않는다 — 핵심 설계와 핵심 구현만 확인한다(사용자 결정 2026-11-26). 빠지는 hunk 는 없다.
- --doc 은 설계 포인트 문서(md)를 페이지 맨 위에 싣는다. 그림과 표는 구조 문서 렌더러가 그린다.
git 은 추적 안 된 새 파일도 넣는다. svn 은 올리지 않은 새 파일을 --add 로 준다.
--check 는 그룹 점검 줄만 찍고 끝난다. 폼은 decide.py 가 띄운다(Enter 로 보내면 검토 결과를 찍고 이야기 파일을 지운다).
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

import decide

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
RISKS = ("높음", "중간", "낮음")
BIG_FILE = 300_000   # 이보다 큰 새 파일은 내용을 넣지 않는다
BIG_DIFF = 3000      # 줄 수가 이보다 많으면 범위를 좁히라고 알린다
REST = "나머지 변경"
REST_LIST = 30       # 점검 줄에 이름을 다 적는 나머지 hunk 수
KEPT = "앞서 확인한 변경"


def _decode_line(raw):
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def decode(raw):
    """줄마다 UTF-8, 아니면 CP949 로 읽는다 — 한글 Windows 에서는 경로 줄과 본문의 인코딩이 다를 수 있다."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return "\n".join(_decode_line(line) for line in raw.split(b"\n"))


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"실패: {' '.join(cmd)}\n{decode(r.stderr).strip()[:400]}")
    return decode(r.stdout)


def detect_vcs(path):
    p = Path(path).resolve()
    for cand in [p, *p.parents]:
        if (cand / ".git").exists():
            return "git", cand
        if (cand / ".svn").is_dir():
            return "svn", cand
    raise SystemExit("git/svn 작업 사본이 아니다. --patch <파일> 로 diff 를 준다.")


def _clean(path, strip_prefix):
    path = path.split("\t")[0].strip().strip('"')
    if strip_prefix and path[:2] in ("a/", "b/"):
        path = path[2:]
    return path


def parse_diff(text):
    """통합 diff → [{path, status, binary, hunks:[{header, lines:[[종류, 옛 줄, 새 줄, 글]]}]}].
    hunk 머리의 줄 수만큼만 본문으로 읽는다 — '--- ' 로 시작하는 지운 줄을 파일 머리로 잘못 읽지 않는다."""
    files, cur, hunk = [], None, None
    old = new = left_old = left_new = 0
    git = False
    for line in text.splitlines():
        if hunk is not None and (left_old > 0 or left_new > 0):
            kind, body = line[:1], line[1:]
            if kind == "\\":
                continue
            if kind == "-":
                hunk["lines"].append(["-", old, None, body])
                old, left_old = old + 1, left_old - 1
            elif kind == "+":
                hunk["lines"].append(["+", None, new, body])
                new, left_new = new + 1, left_new - 1
            else:
                hunk["lines"].append([" ", old, new, body])
                old, new, left_old, left_new = old + 1, new + 1, left_old - 1, left_new - 1
            continue
        hunk = None
        if line.startswith("diff --git ") or line.startswith("Index: "):
            git = line.startswith("diff")
            m = re.match(r'diff --git "?a/(.*?)"? "?b/(.*?)"?$', line) if git else None
            cur = {"path": m.group(2) if m else line[7:].strip(), "status": "수정", "binary": False, "hunks": []}
            files.append(cur)
        elif cur is None:
            continue
        elif m := HUNK.match(line):
            old, new = int(m.group(1)), int(m.group(3))
            left_old = int(m.group(2)) if m.group(2) is not None else 1
            left_new = int(m.group(4)) if m.group(4) is not None else 1
            hunk = {"header": line.strip(), "lines": []}
            cur["hunks"].append(hunk)
        elif line.startswith("new file mode"):
            cur["status"] = "추가"
        elif line.startswith("deleted file mode"):
            cur["status"] = "삭제"
        elif line.startswith("rename to "):
            cur["status"], cur["path"] = "이름 바꿈", line[10:].strip().strip('"')
        elif line.startswith(("Binary files ", "GIT binary patch", "Cannot display: file marked as a binary")):
            cur["binary"] = True
        elif line.startswith("--- "):
            if _clean(line[4:], git) == "/dev/null" or "(nonexistent)" in line or "(revision 0)" in line:
                cur["status"] = "추가"
        elif line.startswith("+++ "):
            if _clean(line[4:], git) == "/dev/null" or "(nonexistent)" in line:
                cur["status"] = "삭제"
            else:
                cur["path"] = _clean(line[4:], git)
    return files


def new_file(root, rel, label="추가"):
    """diff 에 안 잡히는 새 파일을 '전부 더한 hunk' 하나로 만든다."""
    path = Path(root) / rel
    entry = {"path": str(rel).replace("\\", "/"), "status": label, "binary": False, "hunks": []}
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise SystemExit(f"--add 파일을 못 읽었다: {path}\n{e}")
    if b"\0" in raw[:8000] or len(raw) > BIG_FILE:
        entry["binary"] = True
        return entry
    lines = decode(raw).splitlines()
    if lines:
        entry["hunks"].append({"header": f"@@ -0,0 +1,{len(lines)} @@", "lines": [["+", None, i, s] for i, s in enumerate(lines, 1)]})
    return entry


def _ours(root, rel, story):
    """하네스가 쓴 파일인가 — 이야기 · 답 · 결정 로그(.claude/)는 사용자의 변경이 아니다."""
    path = (Path(root) / rel).resolve()
    story = Path(story).resolve()
    return ".claude" in Path(rel).parts or path in (story, decide.answers_path(story).resolve())


def collect(args):
    """→ 파일 목록. 패치 파일이 있으면 그것만, 없으면 작업 사본의 diff."""
    if args.patch:
        files = parse_diff(decode(Path(args.patch).read_bytes()))
        root = Path(args.path).resolve()
    else:
        vcs, root = detect_vcs(args.path)
        rel = Path(args.path).resolve().relative_to(root).as_posix() or "."
        if vcs == "git":
            files = parse_diff(run(["git", "-c", "core.quotepath=off", "diff", "--no-color", "--no-ext-diff", "-U3",
                                    args.base or "HEAD", "--", rel], root))
            untracked = run(["git", "-c", "core.quotepath=off", "ls-files", "--others", "--exclude-standard", "--", rel], root)
            files += [new_file(root, f, "추가 · 추적 안 됨") for f in untracked.splitlines() if f.strip() and not _ours(root, f, args.story)]
        else:
            files = parse_diff(run(["svn", "diff", "--internal-diff"] + (["-r", args.base] if args.base else []) + [rel], root))
    files += [new_file(root, Path(f).resolve().relative_to(root) if Path(f).is_absolute() else f, "추가 · 올리지 않음") for f in args.add]
    return files


def fingerprint(f, hunk):
    """hunk 의 해시. 줄 번호가 밀려도 같고, 본문이 한 글자라도 바뀌면 달라진다."""
    body = "\n".join(l[0] + l[3] for l in hunk["lines"]) if hunk else f["status"] + ("·binary" if f["binary"] else "")
    return hashlib.sha1((f["path"] + "\n" + body).encode("utf-8", "replace")).hexdigest()[:16]


def _selected(sel):
    """'2' · '2-4' · '1,3' → hunk 번호 집합(1부터). 비면 전부."""
    if not sel:
        return None
    picked = set()
    for part in sel.split(","):
        lo, _, hi = part.partition("-")
        picked.update(range(int(lo), int(hi or lo) + 1))
    return picked


def _counts(hunks):
    kinds = [l[0] for h in hunks for l in h["lines"]]
    return kinds.count("+"), kinds.count("-")


def build(files, story, confirmed=frozenset()):
    """diff 와 이야기를 묶는다. → (폼, 점검 줄, 오류).
    confirmed 는 앞 차례에 확인받은 hunk 의 해시다. 이야기가 다시 담지 않은 그 hunk 는 묻지 않고 접어 둔다."""
    claimed, errors, groups = {}, [], []
    units = [(fi, hi) for fi, f in enumerate(files) for hi in (range(len(f["hunks"])) if f["hunks"] else [None])]
    fps = {(fi, hi): fingerprint(files[fi], files[fi]["hunks"][hi] if hi is not None else None) for fi, hi in units}

    def make(gid, info, picked):
        out = []
        for fi in sorted({fi for fi, _ in picked}):
            f = files[fi]
            out.append({"path": f["path"], "status": f["status"], "binary": f["binary"],
                        "hunks": [f["hunks"][hi] for pfi, hi in picked if pfi == fi and hi is not None]})
        added, removed = _counts([h for f in out for h in f["hunks"]])
        return {"id": gid, "title": info["title"], "why": info.get("why") or "", "look": info.get("look") or "",
                "risk": info.get("risk") or "", "files": out, "added": added, "removed": removed,
                "fps": [fps[u] for u in picked], "locked": bool(info.get("locked")), "skipped": bool(info.get("skipped"))}

    for gi, g in enumerate(story.get("groups") or [], 1):
        name = str(g.get("title") or "").strip()
        if not name:
            errors.append(f"그룹 {gi}: title 이 없다")
            continue
        if g.get("risk") and g["risk"] not in RISKS:
            errors.append(f"그룹 {gi} '{name}': risk 는 {' · '.join(RISKS)} 중 하나다")
        picked = []
        for pattern in g.get("match") or []:
            path, _, sel = pattern.partition("#")
            try:
                numbers = _selected(sel)
            except ValueError:
                errors.append(f"그룹 {gi} '{name}': hunk 번호를 못 읽었다 — {pattern}")
                continue
            hit = False
            for fi, hi in units:
                p = files[fi]["path"]
                if not (p == path or p.endswith("/" + path) or fnmatch(p, path)):
                    continue
                if numbers is not None and (hi is None or hi + 1 not in numbers):
                    continue
                hit = True
                if (fi, hi) not in claimed:
                    claimed[(fi, hi)] = gi
                    picked.append((fi, hi))
            if not hit:
                errors.append(f"그룹 {gi} '{name}': diff 에 없는 것을 가리킨다 — {pattern}")
        if picked:
            groups.append(make(f"g{gi}", g, picked))
        elif g.get("match"):
            errors.append(f"그룹 {gi} '{name}': 든 hunk 가 없다(앞 그룹이 다 가져갔거나 diff 에 없다)")
        else:
            errors.append(f"그룹 {gi} '{name}': match 가 없다")
    kept = [u for u in units if u not in claimed and fps[u] in confirmed]
    rest = [u for u in units if u not in claimed and fps[u] not in confirmed]
    if rest:
        groups.append(make("rest", {"title": REST, "why": "이야기가 핵심으로 꼽지 않은 hunk 다. 판정하지 않는다.", "skipped": True}, rest))
    if kept:
        groups.append(make("kept", {"title": KEPT, "why": "앞 차례에 확인했고 그 뒤로 바뀌지 않았다.", "locked": True}, kept))
    added, removed = _counts([h for f in files for h in f["hunks"]])
    stats = f"파일 {len(files)}개 · +{added} −{removed} · hunk {len(units)}개"
    report = f"{stats} · 핵심 {len(claimed)}개 · 판정 안 하는 나머지 {len(rest)}개" + (f" · 앞서 확인한 것 {len(kept)}개" if kept else "")
    if rest:
        names = [files[fi]["path"] + (f"#{hi + 1}" if hi is not None else "") for fi, hi in rest]
        report += "\n나머지: " + " · ".join(names[:REST_LIST]) + (f" 외 {len(names) - REST_LIST}개" if len(names) > REST_LIST else "")
        report += "\n점검: 나머지에 동작이 바뀌는 hunk 가 있으면 그룹에 넣는다 — 사용자는 나머지를 보지 않는다"
    if added + removed > BIG_DIFF:
        report += f"\n점검: 바뀐 줄이 {added + removed}줄이다 — --path 를 하위 폴더로 좁히거나 나눠서 낸다"
    if not story.get("groups"):
        report += "\n점검: 그룹이 없다 — 설명 없는 diff 다"
    spec = {"kind": "diff", "title": str(story.get("title") or "").strip(), "context": story.get("context") or [],
            "stats": stats, "groups": groups}
    return spec, report, errors


def design_doc(path):
    """설계 포인트 문서(md)를 페이지 맨 위에 싣는 함수를 돌려준다. 그리는 일은 game-architecture 의 render.py 가 한다."""
    src = Path(path)
    folder = Path(__file__).resolve().parent.parent.parent / "game-architecture" / "scripts"
    if not src.is_file():
        raise SystemExit(f"설계 문서가 없다: {path}")

    if not (folder / "render.py").is_file():
        raise SystemExit("game-architecture 스킬(render.py)이 없다 — setup.bat 을 다시 돌린다")

    sys.path.insert(0, str(folder))
    import render
    md = src.read_text(encoding="utf-8")
    title = next((ln.lstrip("# ").strip() for ln in md.splitlines() if ln.startswith("# ")), src.stem)
    return lambda url_for: render.render_html(md, src.with_suffix(".html"), title, src=src, url_for=url_for)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story", nargs="?", help="이야기 JSON: {title, context[], groups[{title, why, look, risk, match[]}]}")
    ap.add_argument("--doc", help="페이지 맨 위에 실을 설계 포인트 문서(md): 클래스 관계 · 책임 · 흐름")
    ap.add_argument("--status", action="store_true", help="이야기 없이: 어느 hunk 가 확인됐고 어느 hunk 가 남았는지만 찍는다")
    ap.add_argument("--path", default=".", help="저장소나 그 하위 폴더. diff 를 이 아래로 좁힌다")
    ap.add_argument("--base", help="비교할 리비전 (git 기본 HEAD · svn 기본 BASE)")
    ap.add_argument("--patch", help="작업 사본 대신 읽을 통합 diff 파일")
    ap.add_argument("--add", action="append", default=[], help="diff 에 안 잡히는 새 파일 (svn 에 올리지 않은 파일)")
    ap.add_argument("--check", action="store_true", help="점검 줄만 찍고 끝난다")
    ap.add_argument("--force", action="store_true", help="이야기가 diff 와 안 맞아도 띄운다")
    ap.add_argument("--project", default=".")
    ap.add_argument("--keep", action="store_true", help="보낸 뒤에도 이야기 · 답 파일을 지우지 않는다")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args(argv)

    # 헤드리스 실행이면 첫 명령(--status · --check)에서 바로 알린다 — 이야기를 다 쓴 뒤에야 알면 그 토큰이 버려진다
    if decide.blocked("diff"):
        return decide.UNATTENDED
    confirmed = decide.load_confirmed(args.project)
    if args.status:
        args.story = args.story or "-"
        files = collect(args)
        skipped = decide.load_skipped(args.project)
        marks = [(f"- {f['path']}" + (f"#{hi + 1}" if h else ""), fingerprint(f, h)) for f in files for hi, h in enumerate(f["hunks"] or [None])]
        left = [name for name, fp in marks if fp not in confirmed and fp not in skipped]
        unseen = sum(1 for _, fp in marks if fp in skipped and fp not in confirmed)
        total = len(marks)
        print(f"hunk {total}개 · 확인 {total - len(left) - unseen}개" + (f" · 보지 않은 나머지 {unseen}개" if unseen else "") + f" · 남은 것 {len(left)}개")
        if left:
            print("\n".join(left))
            print("다음: 남은 것 가운데 동작이 바뀌는 hunk 는 그룹에 담아 확인받는다. 나머지는 접혀 나온다.")
        elif not total:
            print("바뀐 것이 없다.")
        elif unseen:
            print(f"구현이 확정됐다 — 핵심 hunk 는 전부 확인됐다. 나머지 {unseen}개는 사용자가 보지 않았다.")
        else:
            print("구현이 확정됐다 — 바뀐 hunk 가 전부 확인됐다.")
        return 0
    if not args.story:
        ap.error("이야기 JSON 이 필요하다 (확인 상태만 보려면 --status)")
    try:
        story = json.loads(Path(args.story).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"이야기를 못 읽었다: {args.story}\n{e}")
    files = collect(args)
    if not files:
        raise SystemExit("바뀐 것이 없다.")
    spec, report, errors = build(files, story, confirmed)
    spec_errors, warns = decide.check_spec(spec)
    print(report)
    for w in warns:
        print(f"점검: {w}")
    errors = spec_errors + errors
    if errors:
        print("이야기 오류:\n" + "\n".join(f"- {e}" for e in errors))
        if not args.force or spec_errors:
            return 1
    doc = design_doc(args.doc) if args.doc else None
    if args.check:
        return 0
    return decide.run_form(spec, args.story, decide.answers_path(args.story), args, record=False, doc=doc)


if __name__ == "__main__":
    sys.exit(main())
