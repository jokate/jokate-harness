#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""변경 이력에서 구조 근거를 뽑는다 (git / svn 공용). 결과는 Markdown + Mermaid.

  python evidence.py hotspots [--path Source] [--months 12] [--top 15]
  python evidence.py coupling [--path Source] [--months 12] [--top 20] [--mermaid]
  python evidence.py focus <경로조각> [--path .] [--months 12]     # 그 파일들과 함께 바뀌어 온 파일
  python evidence.py roots [--path .]                               # 하위 저장소 목록 (중첩 저장소 찾기)

--path 에서 위로 올라가며 가장 가까운 .git/.svn 을 쓴다. 소스가 별도 저장소(예: Source/.git)면
루트에서 돌려도 그 이력은 안 보인다 — 먼저 roots 로 확인하라. 커밋이 적으면 출력에 경고가 붙는다.

정의 (Code Maat 기본값을 따른다):
  degree = 함께 바뀐 커밋 수 / 두 파일 커밋 수의 평균
  필터   = min-revs 5, min-shared 5, min-degree 30%, 커밋당 파일 30개 초과 커밋 제외
  hotspot = 커밋 수 순위. git 이면 churn(추가+삭제 줄)과 LOC 대비 상대 churn 을 함께 낸다.
C++ 는 .h/.cpp 를 한 단위로 묶는다 (--no-unit 으로 끈다). 바이너리 애셋(.uasset, .prefab 등)도 커밋 단위 결합에는 포함된다. .meta 와 생성물은 뺀다.
"""

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

NOISE = re.compile(r"(\.meta$|(^|/)(Intermediate|Saved|Binaries|DerivedDataCache|Library|Temp|obj)/|\.sln$|\.csproj$)")
TEXT_EXT = {".h", ".hpp", ".cpp", ".c", ".inl", ".cs", ".py", ".ini", ".json", ".md", ".uplugin", ".uproject"}


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"실패: {' '.join(cmd)}\n{r.stderr.strip()[:400]}")
    return r.stdout


def detect_vcs(path):
    p = Path(path).resolve()
    for cand in [p, *p.parents]:
        if (cand / ".git").exists():
            return "git", cand
        if (cand / ".svn").is_dir():
            return "svn", cand
    raise SystemExit("git/svn 작업 사본이 아니다.")


SKIP_ROOTS = {"Saved", "Intermediate", "Binaries", "DerivedDataCache", "Library", "Temp", "Logs", "obj",
              "node_modules", ".vs", ".idea", ".claude"}


def commit_count(kind, root):
    if kind == "git":
        r = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=str(root), capture_output=True,
                           encoding="utf-8", errors="replace")
        return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None
    r = subprocess.run(["svn", "info", "--show-item", "revision"], cwd=str(root), capture_output=True,
                       encoding="utf-8", errors="replace")
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None


def source_count(kind, root):
    """게임 소스(.h/.cpp/.cs) 추적 파일 수. svn 은 비용이 커서 세지 않는다(None)."""
    if kind != "git":
        return None
    r = subprocess.run(["git", "ls-files", "*.h", "*.cpp", "*.cs"], cwd=str(root), capture_output=True,
                       encoding="utf-8", errors="replace")
    return len(r.stdout.splitlines()) if r.returncode == 0 else None


def vcs_roots(base, depth=3):
    """base 아래(자신 포함)의 저장소 루트 [(kind, path, commits, sources)]. svn 은 커밋 수 대신 최신 리비전."""
    out, base = [], Path(base).resolve()
    for dp, dns, _ in os.walk(base):
        d = Path(dp)
        if len(d.relative_to(base).parts) > depth:
            dns[:] = []
            continue
        for kind, marker in (("git", ".git"), ("svn", ".svn")):
            if (d / marker).exists():
                out.append((kind, d, commit_count(kind, d), source_count(kind, d)))
        dns[:] = [x for x in dns if x not in SKIP_ROOTS and not x.startswith(".")]
    return out


def cmd_roots(args):
    base = Path(args.path).resolve()
    roots = vcs_roots(base)
    if not roots:
        print("저장소 없음 (git/svn). 변경 이력 신호를 쓸 수 없다 — 정적 구조만으로 판단한다.")
        return 0
    print("| 저장소 | 종류 | 커밋(svn=리비전) | 소스 파일(.h/.cpp/.cs) |\n|---|---|---|---|")
    for kind, d, n, src in sorted(roots, key=lambda r: (-(r[3] or 0), -(r[2] or 0))):
        print(f"| `{os.path.relpath(d, base)}` | {kind} | {n if n is not None else '?'} | {src if src is not None else '?'} |")
    print("\n소스 파일이 가장 많은 저장소를 --path 로 준다. 소스 0 인 저장소는 게임 코드가 아니다.")
    return 0


def git_changesets(root, path, since):
    out = run(["git", "log", f"--since={since}", "--numstat", "--no-renames", "--date=short",
               "--pretty=format:--%h--%ad--%aN", "--", path], root)
    sets, cur = [], None
    for line in out.splitlines():
        if line.startswith("--"):
            _, rev, date, author = line.split("--", 3)
            cur = {"rev": rev, "date": date, "author": author, "files": {}}
            sets.append(cur)
        elif line.strip() and cur is not None:
            a, d, f = line.split("\t", 2)
            churn = (int(a) if a.isdigit() else 0) + (int(d) if d.isdigit() else 0)
            cur["files"][f] = churn
    return sets


def svn_changesets(root, path, since):
    prefix = run(["svn", "info", "--show-item", "relative-url", str(root)], root).strip().lstrip("^")
    xml = run(["svn", "log", "-v", "--xml", "-r", f"{{{since}}}:HEAD", path], root)
    sets = []
    for e in ET.fromstring(xml).iter("logentry"):
        files = {}
        for p in e.iter("path"):
            if p.get("kind") == "dir":
                continue
            f = p.text or ""
            if f.startswith(prefix + "/"):
                files[f[len(prefix) + 1:]] = None
        sets.append({"rev": e.get("revision"), "date": (e.findtext("date") or "")[:10],
                     "author": e.findtext("author") or "", "files": files})
    return sets


def load(args):
    vcs, root = detect_vcs(args.path)
    since = (datetime.now() - timedelta(days=30 * args.months)).strftime("%Y-%m-%d")
    rel = os.path.relpath(Path(args.path).resolve(), root)
    rel = "." if rel == "." else rel.replace("\\", "/")
    sets = (git_changesets if vcs == "git" else svn_changesets)(root, rel, since)
    for s in sets:
        units = {}
        for f, c in s["files"].items():
            if NOISE.search(f):
                continue
            u = f if args.no_unit else unit(f)
            UNIT_FILES.setdefault(u, set()).add(f)
            units[u] = (units.get(u) or 0) + (c or 0) if c is not None else units.get(u)
        s["files"] = units
    sets = [s for s in sets if s["files"]]
    if len(sets) < 20:
        richer = [r for r in vcs_roots(args.path) if r[1] != root and (r[2] or 0) > len(sets) and (r[3] is None or r[3] > 0)]
        if richer:
            k, d, n, src = max(richer, key=lambda r: ((r[3] or 0), (r[2] or 0)))
            print(f"> ⚠ 이 저장소({root.name})는 기간 내 커밋 {len(sets)}개뿐이다. 게임 소스가 가장 많은 하위 저장소 "
                  f"`{os.path.relpath(d, Path(args.path).resolve())}` ({k}, 커밋 {n}, 소스 {src}) → `--path` 로 다시. 전체 목록은 `roots`.")
    return vcs, root, since, sets


UNIT_FILES = {}
CPP_UNIT = re.compile(r"\.(h|hpp|cpp|inl)$")


def unit(f):
    """C++ 헤더/소스를 한 단위로 묶는다. UE 의 Public/Private/Classes 분리도 접는다."""
    if not CPP_UNIT.search(f):
        return f
    return re.sub(r"/(Public|Private|Classes)/", "/", CPP_UNIT.sub("", f)) + ".{h,cpp}"


def loc(root, u):
    total = None
    for f in UNIT_FILES.get(u, {u}):
        p = root / f
        if p.suffix not in TEXT_EXT or not p.is_file():
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                total = (total or 0) + sum(1 for _ in fh)
        except OSError:
            pass
    return total


def header(vcs, root, since, sets, what):
    print(f"<!-- evidence.py {what} · {vcs} · {root.name} · {since} 이후 커밋 {len(sets)}개 -->")


def cmd_hotspots(args):
    vcs, root, since, sets = load(args)
    revs, churn, authors = Counter(), Counter(), {}
    for s in sets:
        for f, c in s["files"].items():
            revs[f] += 1
            churn[f] += c or 0
            authors.setdefault(f, set()).add(s["author"])
    header(vcs, root, since, sets, "hotspots")
    has_churn = vcs == "git"
    print("\n| # | 파일 | 커밋 | 작성자 | " + ("churn | LOC | 상대 churn |" if has_churn else "LOC |"))
    print("|---|---|---|---|" + ("---|---|---|" if has_churn else "---|"))
    for i, (f, n) in enumerate(revs.most_common(args.top), 1):
        n_loc = loc(root, f)
        cells = [str(i), f"`{f}`", str(n), str(len(authors[f]))]
        if has_churn:
            rel = f"{churn[f] / n_loc:.1f}" if n_loc else "-"
            cells += [str(churn[f]), str(n_loc or "-"), rel]
        else:
            cells.append(str(n_loc or "-"))
        print("| " + " | ".join(cells) + " |")
    print("\n상대 churn = churn ÷ LOC (Nagappan & Ball 2005: 절대 churn 보다 결함 예측력이 높다). 바이너리는 LOC 없음.")
    return 0


def pairs(sets, args):
    revs, shared = Counter(), Counter()
    for s in sets:
        fs = sorted(s["files"])
        for f in fs:
            revs[f] += 1
        if len(fs) > args.max_changeset:
            continue
        for a, b in combinations(fs, 2):
            shared[(a, b)] += 1
    out = []
    for (a, b), n in shared.items():
        if n < args.min_shared or revs[a] < args.min_revs or revs[b] < args.min_revs:
            continue
        deg = n / ((revs[a] + revs[b]) / 2)
        if deg >= args.min_degree:
            out.append((deg, n, a, b))
    return sorted(out, reverse=True), revs


def short(f):
    parts = f.split("/")
    return "/".join(parts[-2:]) if len(parts) > 1 else f


def node_id(f, ids):
    return ids.setdefault(f, f"n{len(ids)}")


def cmd_coupling(args):
    vcs, root, since, sets = load(args)
    ps, revs = pairs(sets, args)
    header(vcs, root, since, sets, "coupling")
    print(f"\n필터: min-revs {args.min_revs} · min-shared {args.min_shared} · degree ≥ {args.min_degree:.0%} · "
          f"커밋당 파일 ≤ {args.max_changeset}. 결과 {len(ps)}쌍.\n")
    print("| degree | 함께 | 파일 A | 파일 B |\n|---|---|---|---|")
    for deg, n, a, b in ps[:args.top]:
        print(f"| {deg:.0%} | {n} | `{a}` | `{b}` |")
    if args.mermaid and ps:
        ids = {}
        print("\n```mermaid\ngraph TD")
        for deg, n, a, b in ps[:args.top]:
            print(f'  {node_id(a, ids)}["{short(a)}"] ---|"{deg:.0%} ({n})"| {node_id(b, ids)}["{short(b)}"]')
        print("```")
    return 0


def cmd_focus(args):
    vcs, root, since, sets = load(args)
    q = args.query.replace("\\", "/").lower()
    hit_sets = [s for s in sets if any(q in f.lower() for f in s["files"])]
    co = Counter()
    for s in hit_sets:
        if len(s["files"]) > args.max_changeset:
            continue
        for f in s["files"]:
            if q not in f.lower():
                co[f] += 1
    header(vcs, root, since, sets, f"focus '{args.query}'")
    print(f"\n'{args.query}' 를 건드린 커밋 {len(hit_sets)}개에서 함께 바뀐 파일 (많은 순):\n")
    print("| 함께 | 비율 | 파일 |\n|---|---|---|")
    for f, n in co.most_common(args.top):
        print(f"| {n} | {n / max(len(hit_sets), 1):.0%} | `{f}` |")
    print("\n비율이 높은데 정적 의존(include/using/모듈 의존)이 없으면 숨은 결합 후보다.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="변경 이력 기반 구조 근거")
    ap.add_argument("command", choices=["hotspots", "coupling", "focus", "roots"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("--path", default=".")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-revs", type=int, default=5)
    ap.add_argument("--min-shared", type=int, default=5)
    ap.add_argument("--min-degree", type=float, default=0.30)
    ap.add_argument("--max-changeset", type=int, default=30)
    ap.add_argument("--mermaid", action="store_true")
    ap.add_argument("--no-unit", action="store_true", help="C++ .h/.cpp 를 묶지 않는다")
    a = ap.parse_args()
    if a.command == "focus" and not a.query:
        raise SystemExit("focus 는 경로 조각이 필요하다.")
    return {"hotspots": cmd_hotspots, "coupling": cmd_coupling, "focus": cmd_focus, "roots": cmd_roots}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
