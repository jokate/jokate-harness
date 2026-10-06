#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""인덱스 웹뷰 — 하네스 인덱스를 브라우저에서 검색·시각화·검증한다. 표준 라이브러리만 쓴다.

  python index_view.py [--root <프로젝트>] [--port 8765] [--open]

붙는 소스 (있는 것만 켜진다):
  engine   ue_q.py 엔진 인덱스 — 정규식 선언 추출 (~/.claude/cache/ue_index/<엔진>/ue.sqlite)
  project  gq.py 프로젝트 인덱스 — 정규식 선언 추출 (UE Saved/ClaudeIndex · Unity Library/ClaudeIndex)
  clangd   cindex.py 의미 인덱스 — clangd-indexer 결과 (심볼·참조·관계). 엔진용·프로젝트용 각각
  harness  하네스 이벤트 로그 (~/.claude/cache/game-harness/events.jsonl)

탭: 검색(좌표·선언 원문·관계) · 그래프(상속·호출·모듈 의존) · 검증(소스별 자체 검사, 정규식↔clangd 대조, 질의 세트) · 하네스.
127.0.0.1 에만 열고, 읽기만 한다 (검증 탭의 검사도 읽기 전용).
"""
import argparse
import json
import os
import random
import sqlite3
import sys
import threading
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gq  # noqa: E402
import ue_q  # noqa: E402

try:
    import cindex  # noqa: E402
except ImportError:  # clangd 인덱서가 없는 설치
    cindex = None

PAGE = HERE.parent / "webview" / "index.html"
MAX_NODES = 160
SNIPPET_MAX = 200


def _harness_events():
    for d in (Path.home() / ".claude" / "hooks", HERE.parents[1] / "game-bootstrap" / "harness"):
        if (d / "harness_events.py").is_file():
            sys.path.insert(0, str(d))
            try:
                import harness_events
                return harness_events
            except ImportError:
                return None
    return None


def read_text_lines(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None


def snippet(lines, line, end=None):
    """line 은 1-based. end 가 없으면 선언 블록 끝(중괄호)까지, 최대 SNIPPET_MAX 줄."""
    if lines is None:
        return None
    start = max(0, line - 1)
    if start > 0 and ue_q.MACRO.match(lines[start - 1]):
        start -= 1
    stop = (end - 1) if end else ue_q.block_end(lines, line - 1)[0]
    stop = min(stop, start + SNIPPET_MAX - 1, len(lines) - 1)
    return {"start": start + 1, "lines": [lines[i] for i in range(start, stop + 1)]}


def coord_check(rows, resolve_path, n=200):
    """좌표 정확도: 표본 심볼의 path:line 에 그 이름이 실제로 있는가 (매크로 줄이면 다음 줄까지 본다)."""
    sample = random.sample(rows, min(n, len(rows))) if rows else []
    bad = []
    cache = {}
    for name, path, line in sample:
        if path not in cache:
            cache[path] = read_text_lines(resolve_path(path))
        lines = cache[path]
        ok = lines is not None and 0 < line <= len(lines) and (
            name in lines[line - 1] or (line < len(lines) and name in lines[line]))
        if not ok:
            bad.append(f"{name} {path}:{line}")
    total = len(sample)
    return {"name": "좌표 정확도", "metric": f"{total - len(bad)}/{total}",
            "pass": total > 0 and len(bad) <= total * 0.02,
            "why": "표본 심볼의 path:line 에 이름이 있는가. 2% 넘게 틀리면 인덱스가 낡았거나 파서가 잘못 짚는다.",
            "samples": bad[:20]}


SRC_EXT = (".h", ".hpp", ".hh", ".inl", ".cpp", ".cc", ".cxx", ".c")
SKIP_WALK = {"Intermediate", "Binaries", "ThirdParty", "Saved", "DerivedDataCache", ".git", ".vs", "Content"}


class ModuleResolver:
    """경로 → 모듈: 가장 가까운 *.Build.cs (UE). 없으면 루트 아래 첫 폴더."""

    def __init__(self):
        self.cache = {}

    def of(self, path, root):
        d = os.path.dirname(path)
        chain = []
        found = None
        while d and d not in self.cache:
            chain.append(d)
            try:
                bc = next((e.name for e in os.scandir(d) if e.name.endswith(".Build.cs")), None)
            except OSError:
                bc = None
            if bc:
                found = bc[:-len(".Build.cs")]
                break
            parent = os.path.dirname(d)
            if parent == d or len(d) <= len(root):
                break
            d = parent
        if found is None:
            found = self.cache.get(d) if d in self.cache else None
        if not found:
            rel = os.path.relpath(path, root).replace("\\", "/").split("/")
            found = rel[1] if len(rel) > 2 and rel[0] in ("Source", "Plugins") else rel[0]
        for c in chain:
            self.cache[c] = found
        return found


def disk_sources(root, kind_root):
    """커버리지 분모: 디스크의 C++ 소스. UE 프로젝트는 Source + Plugins/*/Source, 엔진은 Source/{Runtime,Editor,Developer} + Plugins."""
    root = str(root)
    bases = []
    if kind_root == "engine":
        bases = [os.path.join(root, "Source", d) for d in ("Runtime", "Editor", "Developer")] + [os.path.join(root, "Plugins")]
    else:
        bases = [os.path.join(root, "Source"), os.path.join(root, "Plugins")]
    out = []
    for base in bases:
        for dp, dns, fns in os.walk(base):
            dns[:] = [d for d in dns if d not in SKIP_WALK]
            out += [os.path.join(dp, f) for f in fns if f.endswith(SRC_EXT)]
    return out


def bfs_graph(focus_ids, neighbors, label_of, kind_of, depth, info_of=None):
    """중심에서 깊이 depth 까지 넓이 우선. info_of(id) → {"module", "path", "line"} 를 주면 노드에 붙인다 (트리·3D 뷰가 쓴다)."""
    nodes, edges, seen = {}, [], set()
    q = deque((f, 0) for f in focus_ids)

    def node(i, **kw):
        d = {"id": i, "label": label_of(i), "kind": kind_of(i), **kw}
        if info_of:
            d.update({k: v for k, v in (info_of(i) or {}).items() if v not in (None, "")})
        return d
    for f in focus_ids:
        nodes[f] = node(f, focus=True)
    while q and len(nodes) < MAX_NODES:
        cur, d = q.popleft()
        if d >= depth:
            continue
        for other, ekind, forward in neighbors(cur):
            key = (cur, other, ekind) if forward else (other, cur, ekind)
            if key not in seen:
                seen.add(key)
                edges.append({"source": key[0], "target": key[1], "kind": ekind})
            if other not in nodes:
                if len(nodes) >= MAX_NODES:
                    break
                nodes[other] = node(other)
                q.append((other, d + 1))
    edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
    return {"nodes": list(nodes.values()), "edges": edges, "truncated": len(nodes) >= MAX_NODES}


# ---------------------------------------------------------------- 소스: 정규식 엔진 인덱스

class EngineSource:
    name, label, engine = "engine", "엔진 · 정규식 (ue_q)", "regex"
    covers = {"engine"}
    modes = ["inherit", "modules"]

    def __init__(self, project):
        self.project = project
        self.db = ue_q.db_path(project) if project else None
        self.available = bool(self.db and self.db.exists())
        if self.available:
            self.con = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True, check_same_thread=False)
            self.lock = threading.Lock()
            self.eng = Path(ue_q.meta_get(self.con, "engine_root") or ue_q.engine_root(project))

    def q(self, sql, args=()):
        with self.lock:
            return self.con.execute(sql, args).fetchall()

    def info(self):
        if not self.available:
            return {"missing": f"{self.db} 없음 — `ue_q.py index`" if self.db else ".uproject 없음"}
        meta = dict(self.q("SELECT key, value FROM meta"))
        return {"db": str(self.db), "engine_root": meta.get("engine_root"), "built": meta.get("generated_at"),
                "counts": json.loads(meta.get("counts", "{}"))}

    ROW = ("SELECT s.rowid, s.name, s.kind, f.module, f.path, s.line, s.parent, s.api "
           "FROM symbols s JOIN files f ON f.id=s.file_id ")

    def _row(self, r):
        return {"id": str(r[0]), "name": r[1], "kind": r[2], "module": r[3], "path": r[4], "line": r[5],
                "parent": r[6] if r[2] != "delegate" else "", "api": r[7]}

    def search(self, text, limit):
        rows = self.q(self.ROW + "WHERE s.name LIKE ? ORDER BY (s.name = ? COLLATE NOCASE) DESC, length(s.name) "
                      "LIMIT ?", (f"%{text}%", text, limit))
        return [self._row(r) for r in rows]

    def by_name(self, name):
        return [self._row(r) for r in self.q(self.ROW + "WHERE s.name = ? COLLATE NOCASE", (name,))]

    def detail(self, sid):
        r = self.q(self.ROW + "WHERE s.rowid = ?", (int(sid),))
        if not r:
            return None
        sym = self._row(r[0])
        sym["snippet"] = snippet(read_text_lines(self.eng / sym["path"]), sym["line"])
        derived = self.q(self.ROW + "WHERE s.parent = ? COLLATE NOCASE AND s.kind != 'delegate' LIMIT 200",
                         (sym["name"],))
        sym["relations"] = {
            "부모": self.by_name(sym["parent"])[:5] if sym["parent"] else [],
            "자식": [self._row(x) for x in derived],
        }
        return sym

    def graph(self, mode, focus, depth):
        if mode == "modules":
            rows = self.q("SELECT name, deps_public, deps_private FROM modules")
            deps = {n: ([x for x in pub.split(",") if x], [x for x in pri.split(",") if x]) for n, pub, pri in rows}
            rdeps = {}
            for n, (pub, pri) in deps.items():
                for d in pub:
                    rdeps.setdefault(d, []).append((n, "public"))
                for d in pri:
                    rdeps.setdefault(d, []).append((n, "private"))
            starts = [n for n in deps if n.lower() == focus.lower()] or [n for n in deps if focus.lower() in n.lower()][:5]

            def nb(n):
                pub, pri = deps.get(n, ([], []))
                out = [(d, "public", True) for d in pub] + [(d, "private", True) for d in pri]
                return out + [(u, k, False) for u, k in rdeps.get(n, [])][:40]
            return bfs_graph(starts, nb, lambda n: n, lambda n: "module" if n in deps else "external", depth)
        starts = [s["id"] for s in self.by_name(focus)[:3]] or [s["id"] for s in self.search(focus, 3)]
        cache = {}

        def sym(i):
            if i not in cache:
                r = self.q(self.ROW + "WHERE s.rowid = ?", (int(i),))
                cache[i] = self._row(r[0]) if r else {"name": i, "kind": "?", "parent": ""}
            return cache[i]

        def nb(i):
            s = sym(i)
            out = [(p["id"], "base", True) for p in self.by_name(s["parent"])[:1]] if s.get("parent") else []
            kids = self.q(self.ROW + "WHERE s.parent = ? COLLATE NOCASE AND s.kind != 'delegate' LIMIT 30", (s["name"],))
            return out + [(str(k[0]), "base", False) for k in kids]
        return bfs_graph(starts, nb, lambda i: sym(i)["name"], lambda i: sym(i)["kind"], depth,
                         lambda i: {"module": sym(i).get("module"), "path": sym(i).get("path"), "line": sym(i).get("line")})

    def overview(self):
        meta = dict(self.q("SELECT key, value FROM meta"))
        kinds = self.q("SELECT kind, COUNT(*) FROM symbols GROUP BY kind ORDER BY 2 DESC")
        groups = {n: (d or "") + ("/" + p if p else "") for n, d, p in self.q("SELECT name, domain, plugin FROM modules")}
        mods = self.q("SELECT f.module, COUNT(s.rowid), COUNT(DISTINCT f.id) FROM files f LEFT JOIN symbols s "
                      "ON s.file_id=f.id WHERE f.module != '' GROUP BY f.module ORDER BY 2 DESC LIMIT 400")
        files = self.q("SELECT kind, COUNT(*) FROM files GROUP BY kind")
        return {"counts": json.loads(meta.get("counts", "{}")), "kinds": kinds,
                "modules": [{"name": m, "group": groups.get(m, ""), "symbols": n, "files": nf} for m, n, nf in mods],
                "file_kinds": files, "build": {"at": meta.get("generated_at"), "seconds": meta.get("elapsed"),
                                               "engine_root": meta.get("engine_root")}}

    def declared(self):
        out = {}
        for n, pub, pri in self.q("SELECT name, deps_public, deps_private FROM modules"):
            d = {x: "private" for x in pri.split(",") if x}
            d.update({x: "public" for x in pub.split(",") if x})
            out[n] = d
        return out

    def matrix(self, focus, limit, declared=None):
        return declared_matrix(self.declared(), {m["name"]: m["symbols"] for m in self.overview()["modules"]}, focus, limit)

    def pipeline(self):
        meta = dict(self.q("SELECT key, value FROM meta"))
        counts = json.loads(meta.get("counts", "{}"))
        return {"mode": "정규식 (ue_q.py index)", "at": meta.get("generated_at"),
                "stages": [{"name": "엔진 폴더 순회 + 헤더 정규식 파싱 + 적재", "seconds": float(meta.get("elapsed") or 0)}],
                "facts": [["파일", counts.get("files")], ["헤더", counts.get("headers")], ["모듈", counts.get("modules")],
                          ["심볼", counts.get("symbols")], ["증분", "size+mtime 서명 (index 할 때만)"]], "history": []}

    def checks(self):
        out = []
        rows = self.q("SELECT s.name, f.path, s.line FROM symbols s JOIN files f ON f.id=s.file_id "
                      "WHERE s.kind != 'delegate' ORDER BY RANDOM() LIMIT 400")
        out.append(coord_check(rows, lambda p: self.eng / p))
        files = self.q("SELECT path, size, mtime FROM files ORDER BY RANDOM() LIMIT 400")
        changed = []
        for path, size, mtime in files:
            try:
                st = (self.eng / path).stat()
                if st.st_size != size or int(st.st_mtime) != mtime:
                    changed.append(path)
            except OSError:
                changed.append(path + " (없음)")
        out.append({"name": "신선도 (파일 표본)", "metric": f"변경 {len(changed)}/{len(files)}", "pass": not changed,
                    "why": "인덱스 이후 바뀐 엔진 파일. 있으면 `ue_q.py index`.", "samples": changed[:20]})
        n_h = self.q("SELECT COUNT(*) FROM files WHERE kind='h'")[0][0]
        out.append({"name": "엔진 소스 포함", "metric": f"헤더 {n_h}", "pass": n_h >= 1000,
                    "why": "헤더가 1000개 미만이면 엔진 소스 없이 설치된 것으로 본다 (ue_q.py 와 같은 기준)."})
        resolved = str(ue_q.engine_root(self.project))
        out.append({"name": "엔진 경로 일치", "metric": resolved, "pass": resolved == str(self.eng),
                    "why": "인덱스를 만든 엔진과 지금 프로젝트가 가리키는 엔진이 같은가."})
        return out


# ---------------------------------------------------------------- 소스: 정규식 프로젝트 인덱스

class ProjectSource:
    name, label, engine = "project", "프로젝트 · 정규식 (gq)", "regex"
    covers = {"project"}
    modes = ["inherit", "modules"]

    def __init__(self, root, kind):
        self.root, self.kind = root, kind
        self.dir = gq.index_dir(root, kind) if root else None
        self.available = bool(self.dir and (self.dir / "meta.json").is_file())
        if self.available:
            self.meta = gq.load(root, kind, "meta", {})
            self.syms = gq.load(root, kind, "symbols", [])
            self.mods = gq.load(root, kind, "modules", {})

    def info(self):
        if not self.available:
            return {"missing": f"{self.dir} 없음 — `gq.py index`" if self.dir else "프로젝트 루트 없음"}
        return {"dir": str(self.dir), "built": self.meta.get("built"), "engine": self.meta.get("engine"),
                "version": self.meta.get("version"),
                "counts": {"symbols": len(self.syms), "modules": len(self.mods)}}

    def _row(self, i):
        s = self.syms[i]
        return {"id": str(i), "name": s[0], "kind": s[1], "path": s[2], "line": s[3], "parent": s[4] or "",
                "module": self._module(s[2])}

    def _module(self, path):
        cands = [n for n, m in self.mods.items() if path.startswith(m["path"] + "/")]
        return max(cands, key=lambda n: len(self.mods[n]["path"])) if cands else ""

    def search(self, text, limit):
        t = text.lower()
        hits = [i for i, s in enumerate(self.syms) if t in s[0].lower()]
        hits.sort(key=lambda i: (self.syms[i][0].lower() != t, len(self.syms[i][0])))
        return [self._row(i) for i in hits[:limit]]

    def by_name(self, name):
        n = name.lower()
        return [self._row(i) for i, s in enumerate(self.syms) if s[0].lower() == n]

    def detail(self, sid):
        i = int(sid)
        if not 0 <= i < len(self.syms):
            return None
        sym = self._row(i)
        sym["snippet"] = snippet(read_text_lines(self.root / sym["path"]), sym["line"])
        sym["relations"] = {
            "부모": self.by_name(sym["parent"])[:5] if sym["parent"] else [],
            "자식": [self._row(j) for j, s in enumerate(self.syms) if (s[4] or "").lower() == sym["name"].lower()][:200],
        }
        return sym

    def graph(self, mode, focus, depth):
        if mode == "modules":
            local = set(self.mods)
            starts = [n for n in local if n.lower() == focus.lower()] or sorted(local)[:30]

            def nb(n):
                m = self.mods.get(n)
                if not m:
                    return []
                out = [(d, "public", True) for d in m["public"]] + [(d, "private", True) for d in m["private"]]
                return out + [(u, vis, False) for u, um in self.mods.items() for vis in ("public", "private")
                              if n in um[vis]]
            return bfs_graph(starts, nb, lambda n: n, lambda n: "module" if n in local else "external",
                             depth if focus else 1)
        starts = [s["id"] for s in self.by_name(focus)[:3]] or [s["id"] for s in self.search(focus, 3)]

        def nb(i):
            s = self._row(int(i))
            out = [(p["id"], "base", True) for p in self.by_name(s["parent"])[:1]] if s["parent"] else []
            return out + [(str(j), "base", False) for j, x in enumerate(self.syms)
                          if (x[4] or "").lower() == s["name"].lower()][:30]
        return bfs_graph(starts, nb, lambda i: self.syms[int(i)][0], lambda i: self.syms[int(i)][1], depth,
                         lambda i: {k: self._row(int(i))[k] for k in ("module", "path", "line")})

    def overview(self):
        kinds = {}
        per_mod = {}
        for s in self.syms:
            kinds[s[1]] = kinds.get(s[1], 0) + 1
            m = self._module(s[2]) or "(모듈 밖)"
            per_mod[m] = per_mod.get(m, 0) + 1
        assets = gq.load(self.root, self.kind, "assets", [])
        atypes = {}
        for a in assets:
            atypes[a[2]] = atypes.get(a[2], 0) + 1
        docs = gq.load(self.root, self.kind, "docs", {})
        tags = gq.load(self.root, self.kind, "tags", {})
        return {"counts": {"symbols": len(self.syms), "modules": len(self.mods), "docs": len(docs), "assets": len(assets),
                           "tags": len(tags)},
                "kinds": sorted(kinds.items(), key=lambda x: -x[1]),
                "modules": [{"name": m, "group": "project", "symbols": n,
                             "files": len({s[2] for s in self.syms if (self._module(s[2]) or "(모듈 밖)") == m})}
                            for m, n in sorted(per_mod.items(), key=lambda x: -x[1])],
                "asset_types": sorted(atypes.items(), key=lambda x: -x[1])[:16],
                "build": {"at": self.meta.get("built"), "vcs": self.meta.get("vcs"), "rev": (self.meta.get("rev") or "")[:10]}}

    def declared(self):
        return {n: {**{d: "private" for d in m["private"]}, **{d: "public" for d in m["public"]}} for n, m in self.mods.items()}

    def matrix(self, focus, limit, declared=None):
        sizes = {}
        for s in self.syms:
            m = self._module(s[2])
            if m:
                sizes[m] = sizes.get(m, 0) + 1
        return declared_matrix(self.declared(), sizes, focus, limit)

    def pipeline(self):
        return {"mode": "정규식 (gq.py index, 세션 시작 훅)", "at": self.meta.get("built"),
                "stages": [], "facts": [["VCS", self.meta.get("vcs") or "없음"], ["리비전", (self.meta.get("rev") or "-")[:10]],
                                        ["갱신", "세션 시작마다 (.claude/session_start.json)"]], "history": []}

    def checks(self):
        out = [coord_check([(s[0], s[2], s[3]) for s in self.syms], lambda p: self.root / p)]
        stale = gq.stale_reason(self.root, self.kind, self.meta)
        out.append({"name": "신선도", "metric": stale or "OK", "pass": not stale,
                    "why": "VCS 리비전·문서 수정 시각 기준 (gq.py status 와 같은 기준). 애셋은 index 로만 갱신된다."})
        return out


def declared_matrix(declared, sizes, focus, limit):
    """Build.cs 선언 의존 행렬. 노드는 focus 와 그 이웃, 없으면 크기 상위 limit 개."""
    names = set(declared) | {d for v in declared.values() for d in v}
    if focus:
        f = next((n for n in names if n.lower() == focus.lower()), None)
        chosen = [f] if f else []
        if f:
            chosen += [d for d in declared.get(f, {})] + [n for n, v in declared.items() if f in v]
    else:
        chosen = sorted(names, key=lambda n: (-sizes.get(n, 0), n))
    chosen = list(dict.fromkeys(chosen))[:limit]
    idx = {n: i for i, n in enumerate(chosen)}
    cells = [[idx[a], idx[b], 0, kind] for a, deps in declared.items() if a in idx
             for b, kind in deps.items() if b in idx and a != b]
    return {"modules": [{"name": n, "size": sizes.get(n, 0), "local": n in declared} for n in chosen], "cells": cells,
            "measure": "declared"}


# ---------------------------------------------------------------- 서버

class App:
    def __init__(self, root):
        self.root, kind, _ = gq.detect(root) if root else (None, None, None)
        if self.root is None:
            self.root, kind = Path(root).resolve(), None
        self.kind = kind
        self.sources = {}
        is_ue = kind == "ue"
        for src in [EngineSource(self.root if is_ue else None), ProjectSource(self.root, kind)]:
            self.sources[src.name] = src
        if cindex is not None:
            for src in cindex.view_sources(self.root, kind):
                self.sources[src.name] = src
        self.events = _harness_events()

    def info(self):
        return {"root": str(self.root), "kind": self.kind,
                "sources": [{"name": s.name, "label": s.label, "engine": s.engine, "available": s.available,
                             "modes": getattr(s, "modes", []), "info": s.info()} for s in self.sources.values()],
                "harness": {"available": self.events is not None,
                            "log": str(self.events.log_path()) if self.events else None},
                "compare": cindex.compare_pairs(self.sources) if cindex is not None else []}

    def handle(self, path, qs):
        arg = lambda k, d="": qs.get(k, [d])[0]  # noqa: E731
        if path == "/api/info":
            return self.info()
        if path == "/api/events":
            if not self.events:
                return {"events": []}
            sess = arg("session") or None
            return {"events": self.events.read(limit=int(arg("limit", "500")), session=sess)}
        if path == "/api/coverage":
            src = self.sources.get(arg("src"))
            return src.coverage() if src is not None and getattr(src, "available", False) and hasattr(src, "coverage") \
                else {"error": "커버리지는 clangd 소스에만 있다"}
        if path == "/api/compare" and cindex is not None:
            return cindex.compare(self.sources, arg("pair"))
        if path == "/api/queryset" and cindex is not None:
            return cindex.run_queryset(self.sources, self.root)
        src = self.sources.get(arg("src"))
        if src is None or not src.available:
            return {"error": f"소스 없음: {arg('src')}"}
        if path == "/api/search":
            return {"results": src.search(arg("q"), int(arg("limit", "50")))}
        if path == "/api/detail":
            sym = src.detail(arg("id"))
            if sym and sym.get("parent") and not sym["relations"].get("부모"):
                # 프로젝트 클래스의 부모는 대개 엔진에 있다 — 다른 소스에서 찾아 잇는다
                for other in self.sources.values():
                    if other is not src and other.available and other.engine == src.engine:
                        hits = other.by_name(sym["parent"])[:3]
                        if hits:
                            sym["relations"][f"부모 ({other.label})"] = [dict(h, src=other.name) for h in hits]
            return {"symbol": sym}
        if path == "/api/graph":
            return src.graph(arg("mode", "inherit"), arg("focus"), max(1, min(4, int(arg("depth", "2")))))
        if path == "/api/checks":
            return {"checks": src.checks()}
        if path == "/api/overview":
            return src.overview()
        if path == "/api/pipeline":
            return src.pipeline()
        if path == "/api/matrix":
            declared = {}
            for other in self.sources.values():
                if other.available and hasattr(other, "declared"):
                    declared.update(other.declared())
            return src.matrix(arg("focus"), max(5, min(80, int(arg("limit", "28")))), declared)
        if path == "/api/refs" and hasattr(src, "refs_with_text"):
            return {"refs": src.refs_with_text(arg("id"), int(arg("limit", "200")))}
        if path == "/api/anatomy" and hasattr(src, "anatomy"):
            return {"anatomy": src.anatomy(arg("name"))}
        return {"error": f"모르는 경로: {path}"}


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if not u.path.startswith("/api/"):
                return self._send(404, b"not found", "text/plain")
            try:
                data = app.handle(u.path, parse_qs(u.query))
                code = 200
            except Exception as e:  # 화면에 원인을 그대로 보인다
                data, code = {"error": f"{type(e).__name__}: {e}"}, 500
            self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
    return Handler


def main():
    ap = argparse.ArgumentParser(description="하네스 인덱스 웹뷰")
    ap.add_argument("--root", default=".")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="브라우저로 연다")
    a = ap.parse_args()
    app = App(a.root)
    srv = None
    for port in range(a.port, a.port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit("빈 포트를 못 찾았다")
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    on = [s.name for s in app.sources.values() if s.available]
    print(f"인덱스 웹뷰 {url} · 루트 {app.root} · 소스 {', '.join(on) or '없음'} · Ctrl+C 로 끝낸다")
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
