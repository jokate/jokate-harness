#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게임 프로젝트 좌표 인덱서 (UE / Unity 공용).

인덱스는 좌표만 담는다: 문서 헤딩, 소스 심볼, 모듈 의존, 애셋, 태그.
사양·동작 판단은 원문(get, 소스 파일)으로 한다. 출력은 기본 4KB 에서 끊는다.

  python gq.py index [--quiet]        # 프로젝트 루트 또는 하위에서
  python gq.py status
  python gq.py map [키워드]            # 엔진·VCS·모듈·문서 개요
  python gq.py find <질의>             # 심볼·애셋·문서·태그 통합 검색
  python gq.py sym <이름>              # 심볼 좌표
  python gq.py get <문서>#<절>         # 문서 절 본문 (부분 일치)
  python gq.py deps [모듈] [--reverse] [--mermaid]

인덱스 위치: UE Saved/ClaudeIndex · Unity Library/ClaudeIndex · 그 외 .claude/index (모두 VCS 무시 대상)
중첩 저장소·서드파티 등 제외할 경로는 <루트>/.claude/gq.json 에 적는다:
  {"exclude": ["Plugins/Developer", "ThirdParty"]}     # 루트 기준 경로 접두사
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

CAP = 4096
SKIP_DIRS = {".git", ".svn", ".vs", ".idea", ".vscode", ".claude", "Saved", "Intermediate", "Binaries",
             "DerivedDataCache", "Library", "Temp", "Logs", "obj", "Build", "node_modules", "__pycache__"}
EXCLUDE = []
ROOT = [None]
UNITY_ASSET_EXT = {".prefab", ".unity", ".asset", ".controller", ".overrideController", ".anim",
                   ".playable", ".inputactions", ".mixer", ".shadergraph", ".vfx", ".mat"}


def harness_emit(feature, detail="", ok=True, project=""):
    """하네스 이벤트 로그(모니터·웹뷰용). 하네스 훅이 설치된 머신에서만 남는다. 실패는 삼킨다."""
    try:
        hooks = str(Path.home() / ".claude" / "hooks")
        if hooks not in sys.path:
            sys.path.append(hooks)
        from harness_events import emit
        emit(feature, detail, ok=ok, project=project, source=Path(__file__).name)
    except Exception:
        pass


# ---------------------------------------------------------------- 프로젝트

def detect(start):
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        up = sorted(cand.glob("*.uproject"))
        if up:
            return cand, "ue", up[0]
        if (cand / "ProjectSettings" / "ProjectVersion.txt").is_file() and (cand / "Assets").is_dir():
            return cand, "unity", cand / "ProjectSettings" / "ProjectVersion.txt"
    return None, None, None


def engine_version(kind, marker):
    try:
        if kind == "ue":
            return json.loads(marker.read_text(encoding="utf-8")).get("EngineAssociation", "?")
        m = re.search(r"m_EditorVersion:\s*(\S+)", marker.read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except (OSError, ValueError):
        return "?"


def sh(cmd, cwd):
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def vcs_state(root):
    for cand in [root, *root.parents]:
        if (cand / ".git").exists():
            return "git", sh(["git", "rev-parse", "HEAD"], root)
        if (cand / ".svn").is_dir():
            return "svn", sh(["svn", "info", "--show-item", "revision"], root)
    return None, None


def index_dir(root, kind):
    return root / {"ue": "Saved", "unity": "Library"}.get(kind, ".claude") / ("ClaudeIndex" if kind else "index")


def load_excludes(root):
    try:
        cfg = json.loads((root / ".claude" / "gq.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    EXCLUDE[:] = [(root / e).resolve() for e in cfg.get("exclude", [])]


def skipped(d):
    if d.name in SKIP_DIRS or d.name.startswith("__External"):
        return True
    return any(d == e or e in d.parents for e in EXCLUDE)


def walk(base, exts):
    if not base.is_dir() or (base.resolve() != ROOT[0] and skipped(base.resolve())):
        return
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if not skipped(Path(dp, d).resolve())]
        for fn in fns:
            if os.path.splitext(fn)[1] in exts:
                yield Path(dp) / fn


def rel(root, p):
    return p.relative_to(root).as_posix()


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------- 스캔

HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def scan_docs(root):
    docs = {}
    for fp in walk(root, {".md"}):
        heads, fence = [], False
        for i, line in enumerate(read(fp).splitlines(), 1):
            if line.lstrip().startswith("```"):
                fence = not fence
            elif not fence:
                m = HEAD_RE.match(line)
                if m:
                    heads.append([len(m.group(1)), m.group(2), i])
        docs[rel(root, fp)] = heads
    return docs


UE_MACRO = re.compile(r"^\s*(UCLASS|USTRUCT|UENUM|UINTERFACE)\s*\(")
UE_DECL = re.compile(r"^\s*(class|struct|enum\s+class|enum)\s+(?:\w+_API\s+)?(\w+)(?:\s*:\s*(?:public\s+|private\s+|protected\s+)?([\w:]+))?[^;]*$")
UE_TAG = re.compile(r"UE_DEFINE_GAMEPLAY_TAG(?:_COMMENT|_STATIC)?\s*\(\s*\w+\s*,\s*\"([^\"]+)\"")
DEP_RE = re.compile(r"(Public|Private)DependencyModuleNames\s*\.\s*(?:AddRange|Add)\s*\(([^;]*?)\)\s*;", re.S)


def ue_source_roots(root):
    yield root / "Source"
    plugins = root / "Plugins"
    if plugins.is_dir():
        for up in plugins.rglob("*.uplugin"):
            yield up.parent / "Source"


def scan_ue(root):
    syms, tags, mods = [], {}, {}
    for src in ue_source_roots(root):
        for bc in walk(src, {".cs"}):
            if not bc.name.endswith(".Build.cs"):
                continue
            deps = {"Public": [], "Private": []}
            for vis, body in DEP_RE.findall(read(bc)):
                deps[vis] += re.findall(r"\"([^\"]+)\"", body)
            mods[bc.name[:-9]] = {"path": rel(root, bc.parent), "public": deps["Public"], "private": deps["Private"]}
        for fp in walk(src, {".h", ".cpp"}):
            text = read(fp)
            r = rel(root, fp)
            for t in UE_TAG.findall(text):
                tags.setdefault(t, []).append(r)
            if fp.suffix != ".h":
                continue
            pending = None
            for i, line in enumerate(text.splitlines(), 1):
                m = UE_MACRO.match(line)
                if m:
                    pending = m.group(1)
                    continue
                d = UE_DECL.match(line)
                if d and (pending or re.search(r"\w+_API\s", line)):
                    syms.append([d.group(2), (pending or d.group(1)).lower(), r, i, d.group(3) or ""])
                    pending = None
    for ini in walk(root / "Config", {".ini"}):
        for t in re.findall(r"GameplayTagList=\(Tag=\"([^\"]+)\"", read(ini)):
            tags.setdefault(t, []).append(rel(root, ini))
    return syms, tags, mods


def scan_ue_assets(root):
    out = []
    bases = [root / "Content"] + [up.parent / "Content" for up in (root / "Plugins").rglob("*.uplugin")] \
        if (root / "Plugins").is_dir() else [root / "Content"]
    for base in bases:
        for fp in walk(base, {".uasset", ".umap"}):
            out.append([fp.stem, rel(root, fp), fp.stem.split("_")[0] if "_" in fp.stem else fp.suffix[1:]])
    return out


CS_NS = re.compile(r"^\s*namespace\s+([\w.]+)")
CS_DECL = re.compile(r"^\s*(?:\[[^\]]*\]\s*)*(?:(?:public|internal|protected|private|sealed|abstract|static|partial|readonly|unsafe|new)\s+)*"
                     r"(class|struct|interface|enum|record)\s+(\w+)(?:<[^>{]*>)?(?:\s*:\s*([\w.]+))?")


def meta_guid(p):
    m = re.search(r"^guid:\s*(\w+)", read(Path(str(p) + ".meta")), re.M)
    return m.group(1) if m else None


def unity_roots(root):
    yield root / "Assets"
    pk = root / "Packages"
    if pk.is_dir():
        for d in pk.iterdir():
            if d.is_dir():
                yield d


def scan_unity(root):
    syms, tags, mods, guid_cs = [], {}, {}, {}
    asm_guid = {}
    for base in unity_roots(root):
        for ad in walk(base, {".asmdef"}):
            try:
                j = json.loads(read(ad))
            except ValueError:
                continue
            g = meta_guid(ad)
            if g:
                asm_guid[g] = j.get("name", ad.stem)
            mods[j.get("name", ad.stem)] = {"path": rel(root, ad.parent), "public": j.get("references", []), "private": []}
        for fp in walk(base, {".cs"}):
            r = rel(root, fp)
            g = meta_guid(fp)
            ns = ""
            for i, line in enumerate(read(fp).splitlines(), 1):
                n = CS_NS.match(line)
                if n:
                    ns = n.group(1)
                d = CS_DECL.match(line)
                if d:
                    syms.append([d.group(2), d.group(1), r, i, d.group(3) or "", ns])
                    if g and g not in guid_cs:
                        guid_cs[g] = d.group(2)
    for m in mods.values():
        m["public"] = [asm_guid.get(x[5:], x) if x.startswith("GUID:") else x for x in m["public"]]
    tm = read(root / "ProjectSettings" / "TagManager.asset")
    blk = re.search(r"tags:\s*\n((?:\s*-\s*.+\n)*)", tm)
    for t in re.findall(r"-\s*(.+)", blk.group(1) if blk else ""):
        tags.setdefault(t.strip(), []).append("ProjectSettings/TagManager.asset")
    return syms, tags, mods, guid_cs


def scan_unity_assets(root, guid_cs):
    out = []
    for base in unity_roots(root):
        for fp in walk(base, UNITY_ASSET_EXT):
            typ = fp.suffix[1:]
            if fp.suffix == ".asset":
                try:
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        head = f.read(4096)
                except OSError:
                    head = ""
                m = re.search(r"m_Script:\s*\{[^}]*guid:\s*(\w+)", head)
                if m and m.group(1) in guid_cs:
                    typ = guid_cs[m.group(1)]
            out.append([fp.stem, rel(root, fp), typ])
    return out


# ---------------------------------------------------------------- 인덱스 입출력

def cmd_index(root, kind, marker, quiet):
    t0 = time.time()
    docs = scan_docs(root)
    if kind == "ue":
        syms, tags, mods = scan_ue(root)
        assets = scan_ue_assets(root)
    elif kind == "unity":
        syms, tags, mods, guid_cs = scan_unity(root)
        assets = scan_unity_assets(root, guid_cs)
    else:
        syms, tags, mods, assets = [], {}, {}, []
    vcs, rev = vcs_state(root)
    idx = index_dir(root, kind)
    idx.mkdir(parents=True, exist_ok=True)
    meta = {"engine": kind, "version": engine_version(kind, marker) if marker else None,
            "vcs": vcs, "rev": rev, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
            "doc_mtime": max((os.path.getmtime(root / d) for d in docs), default=0)}
    for name, obj in (("meta", meta), ("docs", docs), ("symbols", syms), ("tags", tags),
                      ("modules", mods), ("assets", assets)):
        (idx / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    harness_emit("index.project", f"{kind or '엔진 미감지'} · 문서 {len(docs)} · 심볼 {len(syms)} · 애셋 {len(assets)} "
                 f"[{time.time() - t0:.1f}s]", project=root)
    if not quiet:
        print(f"인덱스 {meta['built']} [{time.time() - t0:.1f}s] · {kind or '엔진 미감지'} {meta['version'] or ''} · "
              f"문서 {len(docs)} · 심볼 {len(syms)} · 모듈 {len(mods)} · 애셋 {len(assets)} · 태그 {len(tags)}")
    return 0


def load(root, kind, name, default):
    try:
        return json.loads((index_dir(root, kind) / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def stale_reason(root, kind, meta):
    vcs, rev = vcs_state(root)
    if rev and rev != meta.get("rev"):
        return f"{vcs} 리비전 변경 ({(meta.get('rev') or '?')[:10]} → {rev[:10]})"
    docs = load(root, kind, "docs", {})
    newest = max((os.path.getmtime(root / d) for d in docs if (root / d).exists()), default=0)
    if newest > meta.get("doc_mtime", 0) + 1:
        return "문서 수정됨"
    return None


def emit(lines, full):
    out, size = [], 0
    for i, ln in enumerate(lines):
        size += len(ln.encode("utf-8")) + 1
        if size > CAP and not full:
            out.append(f"… (+{len(lines) - i} more · --full 또는 질의를 좁혀라)")
            break
        out.append(ln)
    print("\n".join(out))


# ---------------------------------------------------------------- 조회

def cmd_status(root, kind, meta):
    if not meta:
        print("인덱스 없음. `gq.py index` 를 돌려라.")
        return 1
    print(f"루트 {root} · 엔진 {kind or '미감지'} {meta.get('version') or ''} · VCS {meta.get('vcs') or '없음'} · 인덱스 {meta['built']}")
    s = stale_reason(root, kind, meta)
    print(f"[낡음] {s} → index" if s else "신선도: OK (애셋은 index 로만 갱신된다)")
    return 0


def cmd_map(root, kind, meta, q, full):
    docs, mods = load(root, kind, "docs", {}), load(root, kind, "modules", {})
    syms, assets = load(root, kind, "symbols", []), load(root, kind, "assets", [])
    ql = (q or "").lower()
    lines = [f"# {root.name} · {kind or '엔진 미감지'} {meta.get('version') or ''} · VCS {meta.get('vcs') or '없음'}"]
    s = stale_reason(root, kind, meta)
    if s:
        lines.append(f"[낡음] {s}")
    lines.append(f"\n## 모듈 {len(mods)} ({'Build.cs' if kind == 'ue' else 'asmdef'})")
    owner = {}
    for x in syms:
        cands = [n for n, m in mods.items() if x[2].startswith(m["path"] + "/")]
        if cands:
            o = max(cands, key=lambda n: len(mods[n]["path"]))
            owner[o] = owner.get(o, 0) + 1
    for n, m in sorted(mods.items()):
        if ql and ql not in n.lower() and ql not in m["path"].lower():
            continue
        cnt = owner.get(n, 0)
        lines.append(f"- {n}  {m['path']}  심볼 {cnt} · 의존 {len(m['public']) + len(m['private'])}")
    lines.append(f"\n## 문서 {len(docs)}")
    for d, heads in sorted(docs.items()):
        top = [h[1] for h in heads if h[0] <= 2][:6]
        if ql and ql not in d.lower() and not any(ql in h.lower() for h in top):
            continue
        lines.append(f"- {d}: " + " / ".join(top))
    types = {}
    for a in assets:
        if not ql or ql in a[1].lower():
            types[a[2]] = types.get(a[2], 0) + 1
    lines.append(f"\n## 애셋 {sum(types.values())} (유형: " + ", ".join(f"{k} {v}" for k, v in
                                                                sorted(types.items(), key=lambda x: -x[1])[:15]) + ")")
    emit(lines, full)
    return 0


def cmd_sym(root, kind, q, full, limit):
    syms = load(root, kind, "symbols", [])
    ql = q.lower()
    exact = [s for s in syms if s[0].lower() == ql]
    hits = exact or [s for s in syms if ql in s[0].lower()]
    lines = [f"{s[1]:<10} {s[0]:<36} {s[2]}:{s[3]}" + (f"  : {s[4]}" if s[4] else "") for s in hits[:limit]]
    if len(hits) > limit:
        lines.append(f"… (+{len(hits) - limit} more · --limit)")
    emit(lines or [f"'{q}' 심볼 없음"], full)
    return 0


def cmd_find(root, kind, q, full, limit):
    ql = q.lower()
    lines = []
    for s in [s for s in load(root, kind, "symbols", []) if ql in s[0].lower()][:limit]:
        lines.append(f"sym   {s[0]}  {s[2]}:{s[3]}")
    for a in [a for a in load(root, kind, "assets", []) if ql in a[1].lower()][:limit]:
        lines.append(f"asset {a[2]:<10} {a[1]}")
    docs = [(d, h) for d, heads in load(root, kind, "docs", {}).items() for h in heads
            if ql in h[1].lower() or ql in d.lower()]
    lines += [f"doc   {d}#{h[1]}  :{h[2]}" for d, h in docs[:limit]]
    tags = [(t, w) for t, w in load(root, kind, "tags", {}).items() if ql in t.lower()]
    lines += [f"tag   {t}  ({w[0]}{' +' + str(len(w) - 1) if len(w) > 1 else ''})" for t, w in tags[:limit]]
    total = sum(len(x) for x in (docs, tags)) + len(lines) - len(docs[:limit]) - len(tags[:limit])
    if total > len(lines):
        lines.append(f"… 결과 {total}개 중 {len(lines)}개 · 종류별 --limit {limit}")
    emit(lines or [f"'{q}' 결과 없음"], full)
    return 0


def cmd_get(root, kind, ref, full):
    doc_q, _, sec_q = ref.partition("#")
    docs = load(root, kind, "docs", {})
    cands = [d for d in docs if doc_q.lower() in d.lower()]
    if len(cands) != 1:
        exact = [d for d in cands if Path(d).stem.lower() == doc_q.lower()]
        if len(exact) != 1:
            emit([f"문서 후보 {len(cands)}개:"] + cands[:30], full)
            return 1
        cands = exact
    d = cands[0]
    lines = read(root / d).splitlines()
    heads = docs[d]
    if not sec_q:
        emit([f"{'  ' * (h[0] - 1)}{h[1]}  :{h[2]}" for h in heads], full)
        return 0
    hs = [i for i, h in enumerate(heads) if sec_q.lower() in h[1].lower()]
    if not hs:
        print(f"'{sec_q}' 절 없음. `gq.py get {d}` 로 목차를 봐라.")
        return 1
    i = hs[0]
    lvl, start = heads[i][0], heads[i][2]
    end = next((h[2] for h in heads[i + 1:] if h[0] <= lvl), len(lines) + 1)
    body = lines[start - 1:end - 1]
    if len("\n".join(body).encode("utf-8")) > 8192 and not full:
        subs = [h for h in heads[i + 1:] if start < h[2] < end]
        emit([f"{d}#{heads[i][1]} 는 8KB 초과. 하위 절:"] + [f"{'  ' * (h[0] - 1)}{h[1]}  :{h[2]}" for h in subs], full)
        return 0
    print(f"{d}:{start}-{end - 1}")
    print("\n".join(body))
    return 0


def cmd_deps(root, kind, q, reverse, mermaid, full):
    mods = load(root, kind, "modules", {})
    edges = [(n, d, vis) for n, m in mods.items() for vis in ("public", "private") for d in m[vis]]
    if q:
        ql = q.lower()
        edges = [e for e in edges if (e[1] if reverse else e[0]).lower() == ql]
    local = set(mods)
    if mermaid:
        lines = ["```mermaid", "graph LR"]
        for a, b, vis in edges:
            if b in local:
                lines.append(f"  {a} {'-->' if vis == 'public' else '-.->'} {b}")
        lines.append("```")
        lines.append("<!-- 프로젝트 내부 모듈만. 실선 public, 점선 private -->")
        emit(lines, True)
        return 0
    lines = [f"{a} → {b}  ({vis}{'' if b in local else ', 외부'})" for a, b, vis in edges]
    emit(lines or ["의존 없음"], full)
    return 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="게임 프로젝트 좌표 인덱서")
    ap.add_argument("command", choices=["index", "status", "map", "find", "sym", "get", "deps"])
    ap.add_argument("arg", nargs="*", default=[])
    ap.add_argument("--root", default=".")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--mermaid", action="store_true")
    a = ap.parse_args()
    arg = " ".join(a.arg).strip() or None

    root, kind, marker = detect(a.root)
    if root is None:
        root = Path(a.root).resolve()
    ROOT[0] = root.resolve()
    load_excludes(root)
    if a.command == "index":
        return cmd_index(root, kind, marker, a.quiet)
    meta = load(root, kind, "meta", None)
    if a.command == "status":
        return cmd_status(root, kind, meta)
    if not meta:
        print("인덱스 없음. `gq.py index` 를 먼저 돌려라.")
        return 1
    if a.command == "map":
        return cmd_map(root, kind, meta, arg, a.full)
    if a.command == "deps":
        return cmd_deps(root, kind, arg, a.reverse, a.mermaid, a.full)
    if arg is None:
        raise SystemExit(f"{a.command} 는 인자가 필요하다.")
    if a.command == "sym":
        return cmd_sym(root, kind, arg, a.full, a.limit)
    if a.command == "find":
        return cmd_find(root, kind, arg, a.full, a.limit)
    return cmd_get(root, kind, arg, a.full)


if __name__ == "__main__":
    sys.exit(main())
