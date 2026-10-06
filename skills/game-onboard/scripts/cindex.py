#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clangd 기반 의미 인덱스. 컴파일러가 본 그대로의 심볼·참조·관계를 sqlite 에 담는다. 표준 라이브러리만 쓴다.

정규식 인덱스(gq.py, ue_q.py)는 선언 줄만 본다. 이 인덱스는 clangd-indexer 가 실제로 컴파일하며 모은 것이라
  - 함수·메서드·필드·매크로까지 심볼이 있고 (선언 + 정의 위치)
  - 참조가 있다 (어디서 쓰나, 어느 함수 안에서 쓰나 → 호출자/피호출 함수)
  - 관계가 있다 (상속 BaseOf, 오버라이드 OverriddenBy)
대신 compile_commands.json 이 필요하고, 컴파일이 되는 상태여야 정확하다 (UE 는 UHT 가 만든 .generated.h 가 있어야 한다).

  python cindex.py cdb [--target <이름>Editor] [--platform Win64] [--config Development]   # UE: compile_commands.json 생성
  python cindex.py build [--cdb <파일|폴더>] [--scope project|engine|all] [--filter 정규식] [--jobs N]
                         [--mode indexer|bg] [--format binary|yaml] [--unity N]
      --mode indexer (기본) clangd-indexer 전체 색인. 출력은 RIFF(binary) 가 기본 — YAML 보다 17배쯤 작고 적재 2배+ 빠름
      --mode bg      clangd 배경 색인 샤드로 증분: 두 번째부터 바뀐 파일·그 헤더를 포함한 TU·플래그가 바뀐 TU 만 다시 색인
      --unity N      같은 플래그·같은 모듈의 .cpp 를 N 개씩 한 TU 로 묶어 공용 헤더 파싱을 줄인다 (실패한 묶음은 원래대로 다시)
  python cindex.py ingest <clangd-indexer 출력(YAML|RIFF)> [--scope ...]   # 이미 만든 출력을 적재만
  python cindex.py status
  python cindex.py sym <이름|A::B>          # 심볼 좌표 (선언·정의·시그니처)
  python cindex.py refs <이름> [--kind decl|def|ref]
  python cindex.py callers <이름>           # 이 심볼을 참조하는 함수 (참조의 Container 기준)
  python cindex.py callees <이름>           # 이 함수 안에서 참조하는 함수·메서드
  python cindex.py bases <이름> · derived <이름> · overrides <이름>
  python cindex.py members <클래스>         # 멤버와 선언 줄 원문 (clangd 는 멤버 시그니처를 기록하지 않는다)
  python cindex.py impact <이름>            # 바꾸면 같이 볼 곳: 파생 타입·재정의·참조하는 함수·파일·모듈
  python cindex.py file <경로 조각>          # 파일에 선언된 심볼
  python cindex.py eval                      # 정규식 인덱스와 대조 + 질의 세트 (index_view.py 검증 탭과 같은 계산)

인덱스 위치: --scope project → UE Saved/ClaudeIndex/clangd.sqlite (그 외 .claude/index/clangd.sqlite)
            --scope engine  → ~/.claude/cache/ue_index/<엔진경로>/clangd.sqlite (ue.sqlite 옆)
--db engine|project|<경로> 로 조회할 인덱스를 고른다 (기본 project, 없으면 engine).
clangd-indexer 위치: --indexer > 환경 변수 CLANGD_INDEXER > PATH > ~/.claude/tools/clangd/bin
clangd(--mode bg) 위치: --clangd > 환경 변수 CLANGD > PATH > ~/.claude/tools/clangd/bin > clangd-indexer 옆
출력은 기본 4KB 에서 끊는다 (--full 로 푼다).
"""
import argparse
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gq  # noqa: E402
import ue_q  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

CAP = 4096
TOOL_VERSION = 1
NULL_ID = "0000000000000000"
# clangd index/Ref.h 의 RefKind 비트, index/Relation.h 의 RelationKind (clangd 소스로 확인)
DECL, DEF, REF, SPELLED, CALL = 1, 2, 4, 8, 16
BASE_OF, OVERRIDDEN_BY = 0, 1
TYPE_KINDS = ("Class", "Struct", "Union", "Enum")
FUNC_KINDS = ("Function", "InstanceMethod", "StaticMethod", "ClassMethod", "Constructor", "Destructor",
              "ConversionFunction")
FLAG_DEPRECATED = 1 << 1   # clangd index/Symbol.h SymbolFlag::Deprecated


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


def emit(lines, full=False):
    out, size = [], 0
    for i, ln in enumerate(lines):
        size += len(ln.encode("utf-8")) + 1
        if size > CAP and not full:
            out.append(f"… (+{len(lines) - i} more · --full 또는 질의를 좁혀라)")
            break
        out.append(ln)
    print("\n".join(out))


# ---------------------------------------------------------------- 위치

def project_of(start):
    root, kind, _ = gq.detect(start)
    if root is None:
        return Path(start).resolve(), None
    return root, kind


def engine_dir_of(root, kind):
    return ue_q.engine_root(root) if kind == "ue" else None


def db_for(scope, root, kind):
    if scope == "engine":
        if kind != "ue":
            return None
        return ue_q.db_path(root).with_name("clangd.sqlite")
    return gq.index_dir(root, kind) / "clangd.sqlite"


def pick_db(arg, root, kind):
    if arg and arg not in ("engine", "project"):
        return Path(arg)
    order = [arg] if arg else ["project", "engine"]
    for scope in order:
        p = db_for(scope, root, kind)
        if p and p.exists():
            return p
    return db_for(order[0], root, kind)


def find_indexer(explicit):
    exe = "clangd-indexer.exe" if os.name == "nt" else "clangd-indexer"
    cands = [explicit, os.environ.get("CLANGD_INDEXER"), shutil.which("clangd-indexer"),
             str(Path.home() / ".claude" / "tools" / "clangd" / "bin" / exe)]
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


def uri_to_path(uri):
    if not uri:
        return ""
    if uri.startswith("file://"):
        p = unquote(uri[7:])
        if re.match(r"^/[A-Za-z]:[/\\]", p):
            p = p[1:]
        return p
    return unquote(uri)


def norm(p):
    p = p.replace("\\", "/")
    return p.lower() if os.name == "nt" or re.match(r"^[A-Za-z]:/", p) else p


# ---------------------------------------------------------------- YAML (clangd-indexer --format=yaml 이 쓰는 부분집합)

def _scalar(v):
    if v == "":
        return ""
    if v[0] == "'" and v[-1] == "'" and len(v) >= 2:
        return v[1:-1].replace("''", "'")
    if v[0] == '"' and v[-1] == '"' and len(v) >= 2:
        return _unescape(v[1:-1])
    if v.isdigit():
        return int(v)
    return v


_ESC = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/", "0": "\0", "b": "\b", "f": "\f"}


def _unescape(s):
    if "\\" not in s:
        return s
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c != "\\" or i + 1 >= len(s):
            out.append(c)
            i += 1
            continue
        n = s[i + 1]
        if n in _ESC:
            out.append(_ESC[n])
            i += 2
        elif n in "xuU":
            width = {"x": 2, "u": 4, "U": 8}[n]
            try:
                out.append(chr(int(s[i + 2:i + 2 + width], 16)))
            except ValueError:
                out.append(s[i:i + 2 + width])
            i += 2 + width
        else:
            out.append(n)
            i += 2
    return "".join(out)


def _parse_block(lines):
    """들여쓰기 블록 → dict. 값이 빈 키는 다음 줄이 '- ' 로 시작하면 list, 아니면 dict."""
    root = {}
    stack = [(-1, root)]
    n = len(lines)
    i = 0
    while i < n:
        raw = lines[i]
        s = raw.lstrip(" ")
        if not s:
            i += 1
            continue
        ind = len(raw) - len(s)
        if s.startswith("- "):
            while len(stack) > 1 and stack[-1][0] >= ind:
                stack.pop()
            lst = stack[-1][1]
            item = {}
            if isinstance(lst, list):
                lst.append(item)
            stack.append((ind, item))
            s = s[2:]
            ind += 2
        else:
            while len(stack) > 1 and stack[-1][0] >= ind:
                stack.pop()
        key, _, val = s.partition(":")
        val = val.strip()
        cont = stack[-1][1]
        if val == "":
            nxt = lines[i + 1].lstrip(" ") if i + 1 < n else ""
            child = [] if nxt.startswith("- ") else {}
            if isinstance(cont, dict):
                cont[key] = child
            stack.append((ind, child))
        elif isinstance(cont, dict):
            cont[key] = _scalar(val)
        i += 1
    return root


def iter_docs(path):
    """('Symbol'|'Refs'|'Relations'|..., dict) 를 하나씩. 파일 전체를 메모리에 올리지 않는다."""
    kind, buf = None, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if line.startswith("--- !"):
                kind, buf = line[5:].strip(), []
            elif line == "...":
                if kind:
                    yield kind, _parse_block(buf)
                kind, buf = None, []
            elif kind:
                buf.append(line)
    if kind and buf:
        yield kind, _parse_block(buf)


# ---------------------------------------------------------------- 적재

SCHEMA = """
CREATE TABLE files(id INTEGER PRIMARY KEY, path TEXT UNIQUE, module TEXT, root TEXT, rel TEXT, mtime INTEGER);
CREATE TABLE symbols(id TEXT PRIMARY KEY, name TEXT COLLATE NOCASE, scope TEXT, qname TEXT COLLATE NOCASE,
  kind TEXT, lang TEXT, decl_file INTEGER, decl_line INTEGER, decl_col INTEGER,
  def_file INTEGER, def_line INTEGER, def_col INTEGER, signature TEXT, return_type TEXT, type TEXT,
  tpl_args TEXT, flags INTEGER, nrefs INTEGER, doc TEXT);
CREATE TABLE refs(sym TEXT, kind INTEGER, file INTEGER, line INTEGER, col INTEGER, container TEXT);
CREATE TABLE relations(subject TEXT, predicate INTEGER, object TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""
INDEXES = """
CREATE INDEX symbols_name ON symbols(name COLLATE NOCASE);
CREATE INDEX symbols_qname ON symbols(qname COLLATE NOCASE);
CREATE INDEX symbols_decl ON symbols(decl_file);
CREATE INDEX refs_sym ON refs(sym);
CREATE INDEX refs_container ON refs(container);
CREATE INDEX rel_subject ON relations(subject, predicate);
CREATE INDEX rel_object ON relations(object, predicate);
"""


class FileTable:
    """경로 → id. 루트(project/engine) 기준 상대 경로와 모듈(가장 가까운 *.Build.cs, 없으면 첫 폴더)을 같이 둔다."""

    def __init__(self, cur, roots):
        self.cur, self.ids = cur, {}
        self.roots = [(name, norm(str(p)).rstrip("/") + "/") for name, p in roots if p]
        self.mod_cache = {}

    def module(self, path, rel_root):
        d = Path(path).parent
        chain = []
        while True:
            key = str(d)
            if key in self.mod_cache:
                found = self.mod_cache[key]
                break
            chain.append(key)
            try:
                bc = next((e.name for e in os.scandir(d) if e.name.endswith(".Build.cs")), None)
            except OSError:
                bc = None
            if bc:
                found = bc[:-len(".Build.cs")]
                break
            if d.parent == d or (rel_root and norm(str(d)).rstrip("/") + "/" == rel_root):
                found = ""
                break
            d = d.parent
        for k in chain:
            self.mod_cache[k] = found
        return found

    def get(self, uri):
        path = uri_to_path(uri)
        if not path:
            return None
        fid = self.ids.get(path)
        if fid is not None:
            return fid
        n = norm(path)
        root, rel, rel_root = "", path, None
        for name, prefix in self.roots:
            if n.startswith(prefix):
                root, rel, rel_root = name, path.replace("\\", "/")[len(prefix):], prefix
                break
        try:
            mtime = int(os.stat(path).st_mtime)
        except OSError:
            mtime = 0
        self.cur.execute("INSERT INTO files(path, module, root, rel, mtime) VALUES(?,?,?,?,?)",
                         (path, self.module(path, rel_root), root, rel, mtime))
        fid = self.ids[path] = self.cur.lastrowid
        return fid


def _yloc(d):
    """YAML {FileURI, Start{Line, Column}} → (uri, 줄, 열) 0 기준 그대로 (RIFF 와 같은 모양). 없으면 None."""
    if not d or not d.get("FileURI"):
        return None
    st = d.get("Start") or {}
    return d["FileURI"], int(st.get("Line", 0)), int(st.get("Column", 0))


def yaml_records(yaml_path):
    """clangd-indexer YAML → 공통 레코드. ("S", 심볼 튜플) · ("R", [참조 튜플]) · ("L", [관계 튜플]).
    튜플 모양은 clangd_riff.read 와 같다 (줄·열 0 기준)."""
    for kind, d in iter_docs(yaml_path):
        if kind == "Symbol":
            info_ = d.get("SymInfo") or {}
            if "Lang" not in info_ and str(info_.get("Kind", "")).startswith("Lang:"):
                # clangd 23.1.0 YAML 쓰기 버그: SymbolKind::Concept 등에 문자열이 없어 'Kind: Lang: C' 한 줄로 나온다
                info_ = {"Kind": "Unmapped(Concept?)", "Lang": str(info_["Kind"]).split(":", 1)[1].strip()}
            yield "S", (str(d.get("ID")), str(d.get("Name") or ""), str(d.get("Scope") or ""), str(info_.get("Kind", "")),
                        str(info_.get("Lang", "")), _yloc(d.get("CanonicalDeclaration")), _yloc(d.get("Definition")),
                        str(d.get("Signature") or ""), str(d.get("ReturnType") or ""), str(d.get("Type") or ""),
                        str(d.get("TemplateSpecializationArgs") or ""), int(d.get("Flags") or 0),
                        int(d.get("References") or 0), str(d.get("Documentation") or ""))
        elif kind == "Refs":
            sid, out = str(d.get("ID")), []
            for r in d.get("References") or []:
                loc = _yloc(r.get("Location"))
                if loc:
                    out.append((sid, int(r.get("Kind") or 0), loc[0], loc[1], loc[2],
                                str((r.get("Container") or {}).get("ID") or NULL_ID)))
            yield "R", out
        elif kind == "Relations":
            yield "L", [(str((d.get("Subject") or {}).get("ID")), int(d.get("Predicate") or 0),
                         str((d.get("Object") or {}).get("ID")))]


def _merge_sym(a, b):
    """같은 심볼의 두 사본 합치기 (배경 색인은 선언 파일·정의 파일 샤드에 한 번씩 넣는다). 빈 칸을 채우고 플래그는 OR."""
    if a == b:
        return a
    x = list(a)
    for i in (5, 6, 7, 8, 9, 10, 13):  # 선언·정의·시그니처·반환·타입·템플릿 인자·문서
        if not x[i] and b[i]:
            x[i] = b[i]
    x[11] = a[11] | b[11]
    x[12] = max(a[12], b[12])
    return tuple(x)


def riff_records(paths, dedupe_refs=False):
    """RIFF 파일(들) → 공통 레코드. 파일이 여럿이면(배경 색인 샤드, 유니티 실패분 재색인) 심볼을 합치고 관계 중복을 뺀다.
    참조는 샤드마다 그 위치의 파일이 주인이라 겹치지 않는다. 여러 clangd-indexer 출력을 합칠 때만 dedupe_refs."""
    import clangd_riff
    paths = list(paths)
    if len(paths) == 1:
        x = clangd_riff.read(Path(paths[0]).read_bytes())
        for s in x["symbols"]:
            yield "S", s
        yield "R", x["refs"]
        yield "L", x["relations"]
        return
    syms, rels, seen = {}, set(), set()
    # 중복 제거가 필요할 때(유니티 실패분 재색인)는 뒤 파일(작은 재색인 출력)부터 읽어 그 키만 기억하고 큰 첫 출력을 거른다
    order = list(reversed(paths)) if dedupe_refs else paths
    for i, p in enumerate(order):
        x = clangd_riff.read(Path(p).read_bytes(), ("symbols", "refs", "relations"))
        for s in x["symbols"]:
            old = syms.get(s[0])
            syms[s[0]] = _merge_sym(old, s) if old else s
        refs = x["refs"]
        if dedupe_refs:
            last = i == len(order) - 1
            refs = [r for r in refs if r[:5] not in seen and (last or not seen.add(r[:5]))]
        yield "R", refs
        rels.update(x["relations"])
    for s in syms.values():
        yield "S", s
    yield "L", sorted(rels)


def records_for(source, dedupe_refs=False):
    """적재 원본 판별: 경로 목록 = RIFF 묶음(샤드 또는 여러 clangd-indexer 출력), 'RIFF' 로 시작하는 파일 = clangd-indexer 바이너리,
    그 밖 = YAML."""
    if isinstance(source, (list, tuple)):
        return riff_records(source, dedupe_refs), f"RIFF {len(source)}개"
    with open(source, "rb") as f:
        magic = f.read(4)
    return (riff_records([source]), "RIFF") if magic == b"RIFF" else (yaml_records(source), "YAML")


def ingest(source, db_path, roots, info=None, keep_doc=300, dedupe_refs=False):
    """source: YAML 파일 · RIFF 파일 · RIFF 파일 목록(배경 색인 샤드, 또는 유니티 + 재색인 출력 → dedupe_refs).
    임시 파일에 다 쓰고 바꿔치기한다."""
    t0 = time.time()
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(str(tmp))
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
    cur = con.cursor()
    files = FileTable(cur, roots)
    counts = {"symbols": 0, "refs": 0, "relations": 0}
    syms, refs, rels = [], [], []

    def flush():
        cur.executemany("INSERT OR REPLACE INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", syms)
        cur.executemany("INSERT INTO refs VALUES(?,?,?,?,?,?)", refs)
        cur.executemany("INSERT INTO relations VALUES(?,?,?)", rels)
        syms.clear(), refs.clear(), rels.clear()

    def at(loc):  # (uri, 줄0, 열0) → (파일 id, 줄1, 열1)
        return (files.get(loc[0]), loc[1] + 1, loc[2] + 1) if loc else (None, None, None)

    records, fmt = records_for(source, dedupe_refs)
    for tag, v in records:
        if tag == "S":
            sid, name, scope, kind, lang, decl, defn, sig, ret, typ, targs, flags, nrefs, doc = v
            syms.append((sid, name, scope, scope + name, kind, lang, *at(decl), *at(defn), sig, ret, typ, targs,
                         flags, nrefs, doc[:keep_doc]))
            counts["symbols"] += 1
        elif tag == "R":
            for sid, k, uri, line, col, cont in v:
                fid = files.get(uri)
                if fid is not None:
                    refs.append((sid, k, fid, line + 1, col + 1, cont))
                    counts["refs"] += 1
        else:
            rels.extend(v)
            counts["relations"] += len(v)
        if len(syms) + len(refs) + len(rels) > 50000:
            flush()
    flush()
    con.executescript(INDEXES)
    counts["files"] = cur.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    took = time.time() - t0
    meta = {"tool_version": TOOL_VERSION, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_ingest": f"{took:.2f}", "counts": json.dumps(counts),
            "roots": json.dumps([[n, str(p)] for n, p in roots if p]), "format": fmt,
            "input": str(source if not isinstance(source, (list, tuple)) else Path(source[0]).parent)}
    meta.update({k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) for k, v in (info or {}).items()})
    meta["history"] = json.dumps(_history(db_path, info, counts, took, source), ensure_ascii=False)
    cur.executemany("INSERT OR REPLACE INTO meta VALUES(?,?)", list(meta.items()))
    con.commit()
    con.close()
    os.replace(tmp, db_path)
    return counts


def _history(db_path, info, counts, took_ingest, out_path, keep=30):
    """빌드 이력: 이전 인덱스의 이력을 이어받아 이번 빌드 한 줄을 붙인다 (웹뷰 파이프라인 탭이 속도 변화를 그린다)."""
    hist = []
    if Path(db_path).exists():
        try:
            con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
            row = con.execute("SELECT value FROM meta WHERE key='history'").fetchone()
            con.close()
            hist = json.loads(row[0]) if row else []
        except (sqlite3.Error, ValueError):
            hist = []
    info = info or {}
    errors = info.get("errors") if isinstance(info.get("errors"), dict) else {}
    out_bytes = info.get("out_bytes")
    if out_bytes is None:
        try:
            out_bytes = Path(out_path).stat().st_size
        except (OSError, TypeError):
            out_bytes = 0
    hist.append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": info.get("mode", info.get("source", "")),
                 "scope": info.get("scope", ""), "tus": info.get("tus"), "failed_tu": errors.get("failed_tu", 0),
                 "t_index": float(info.get("elapsed_index") or 0), "t_ingest": round(took_ingest, 2),
                 "out_bytes": out_bytes, "symbols": counts["symbols"], "refs": counts["refs"],
                 "relations": counts["relations"], "files": counts.get("files"),
                 "reused": info.get("reused"), "rebuilt": info.get("rebuilt")})
    return hist[-keep:]


# ---------------------------------------------------------------- 만들기

UBT_HINT = "UnrealBuildTool 진입점을 못 찾았다. --ubt 로 Build.bat 또는 UnrealBuildTool(.exe|.dll) 경로를 준다."


def find_ubt(eng):
    for rel in ("Build/BatchFiles/Build.bat", "Build/BatchFiles/Linux/Build.sh", "Build/BatchFiles/Mac/Build.sh",
                "Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.exe", "Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll"):
        p = Path(eng) / rel
        if p.is_file():
            return p
    return None


def cmd_cdb(root, kind, a):
    if kind != "ue":
        print("cdb 는 UE 프로젝트용이다. 다른 프로젝트는 빌드 시스템(CMake 의 CMAKE_EXPORT_COMPILE_COMMANDS 등)으로 "
              "compile_commands.json 을 만들고 build --cdb 로 준다.")
        return 1
    eng = engine_dir_of(root, kind)
    ubt = Path(a.ubt) if a.ubt else find_ubt(eng)
    if not ubt:
        print(UBT_HINT)
        return 1
    upro = gq.detect(root)[2]
    target = a.target or f"{upro.stem}Editor"
    # UBT 소스(공개 미러) 기준 — 실제 엔진에서 돌려 보지 않았다: 5.1+ -OutputDir (기본 엔진 루트),
    # 5.4+ 유니티 빌드·PCH 끄고 UHT 를 먼저 돈다(-NoExecCodeGenActions 로 끔), 5.5+ -Include=/-Exclude= 필터.
    # 런처 설치 엔진은 엔진 모듈이 미리 빌드돼 있어 프로젝트 파일만 나온다 (references/cindex.md).
    out = a.out or str(root)
    cmd = ([str(ubt)] if ubt.suffix != ".dll" else ["dotnet", str(ubt)]) + [
        "-mode=GenerateClangDatabase", f"-project={upro}", target, a.platform, a.config, f"-OutputDir={out}"]
    print("실행:", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    t0 = time.time()
    r = subprocess.run(cmd, cwd=str(eng.parent if eng else root))
    print(f"종료 {r.returncode} [{time.time() - t0:.0f}s]")
    found = [p for p in (Path(out), eng.parent if eng else None, eng, root) if p and (p / "compile_commands.json").is_file()]
    if found:
        print("compile_commands.json:", found[0] / "compile_commands.json")
    harness_emit("index.clangd.cdb", f"{target} {a.platform} {a.config} → 종료 {r.returncode}", ok=r.returncode == 0, project=root)
    return r.returncode


def resolve_cdb(arg, root, eng):
    """compile_commands.json 위치. --cdb 가 없으면 프로젝트 루트 → build/ → 엔진 쪽 → .vscode/compileCommands_<이름>.json 순."""
    cands = [Path(arg)] if arg else [root, root / "build", eng.parent if eng else None, eng]
    for c in cands:
        if not c:
            continue
        p = c / "compile_commands.json" if c.is_dir() else c
        if p.is_file():
            return p
    if not arg:
        vs = sorted((root / ".vscode").glob("compileCommands_*.json")) if (root / ".vscode").is_dir() else []
        if vs:
            return vs[0]
    return None


def staged_cdb(cdb, work_dir):
    """clangd-indexer 는 compile_commands.json 이라는 이름의 데이터베이스를 읽는다. 다른 이름(.vscode/compileCommands_X.json)이면
    작업 폴더에 그 이름으로 복사해 넘긴다 (항목의 경로는 절대 경로라 위치가 바뀌어도 된다)."""
    if cdb.name == "compile_commands.json":
        return cdb
    dst = work_dir / "cdb" / "compile_commands.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cdb, dst)
    return dst


def erescape(s):
    """LLVM Regex(POSIX ERE) 용 이스케이프. Python re.escape 는 ERE 가 모르는 이스케이프를 만든다."""
    return "".join("\\" + c if c in ".[]()*+?{}|^$\\" else c for c in s)


def default_filter(scope, root, eng):
    """번역 단위 경로 정규식. 구분자는 / 와 \\ 둘 다, 드라이브 문자는 대소문자 둘 다 받는다 (LLVM Regex 는 (?i) 가 없다)."""
    def pat(p):
        parts = [x for x in re.split(r"[\\/]+", str(p)) if x != ""]
        out = []
        for i, part in enumerate(parts):
            if i == 0 and re.fullmatch(r"[A-Za-z]:", part):
                out.append(f"[{part[0].upper()}{part[0].lower()}]:")
            else:
                out.append(erescape(part))
        lead = "[/\\\\]" if str(p).startswith(("/", "\\")) else ""
        return lead + "[/\\\\]".join(out) + "[/\\\\]"
    if scope == "project":
        return pat(root)
    if scope == "engine" and eng:
        return pat(eng)
    return None


def find_clangd(explicit):
    """배경 색인 모드용 clangd 본체. --clangd > CLANGD > PATH > ~/.claude/tools/clangd/bin > clangd-indexer 옆."""
    exe = "clangd.exe" if os.name == "nt" else "clangd"
    idx = find_indexer(None)
    cands = [explicit, os.environ.get("CLANGD"), shutil.which("clangd"),
             str(Path.home() / ".claude" / "tools" / "clangd" / "bin" / exe), str(Path(idx).parent / exe) if idx else None]
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


def _module_of_path(roots):
    """유니티 묶음을 모듈 안에서만 만들려고 쓰는 모듈 판정 (FileTable.module 과 같은 규칙: 가장 가까운 *.Build.cs)."""
    ft = FileTable.__new__(FileTable)
    ft.mod_cache = {}
    prefixes = [norm(str(p)).rstrip("/") + "/" for _, p in roots if p]

    def mod(path):
        n = norm(path)
        rel_root = next((x for x in prefixes if n.startswith(x)), None)
        return ft.module(path, rel_root)
    return mod


def _run_indexer(indexer, cdb_file, out_dir, fmt, jobs, extra, flt, tag=""):
    """clangd-indexer 한 번. 반환: (출력 경로, 걸린 초, 오류 요약, 종료 코드)."""
    out = out_dir / f"clangd-index{tag}.{'riff' if fmt == 'binary' else 'yaml'}"
    cmd = [indexer, "--executor=all-TUs", f"--format={fmt}"]
    if flt:
        cmd.append(f"--filter={flt}")
    if jobs:
        cmd.append(f"--execute-concurrency={jobs}")
    cmd += [f"--extra-arg={x}" for x in extra or []]
    cmd.append(str(cdb_file))
    print("실행:", " ".join(cmd))
    err_path = out_dir / f"clangd-index{tag}.stderr.txt"
    t0 = time.time()
    with open(out, "wb") as o, open(err_path, "wb") as e:
        r = subprocess.run(cmd, stdout=o, stderr=e)
    took = time.time() - t0
    errors = summarize_errors(err_path)
    print(f"clangd-indexer 종료 {r.returncode} [{took:.0f}s] · TU {errors['tus']} · 실패 TU {errors['failed_tu']} · "
          f"오류 줄 {errors['count']}" + (f" · .generated.h 관련 {errors['generated_h']}" if errors["generated_h"] else "")
          + f" (전체: {err_path})")
    return out, took, errors, r.returncode


def build_indexer(root, eng, scope, a, out_dir, roots):
    """clangd-indexer 전체 색인. --unity N 이면 같은 플래그의 .cpp 를 N 개씩 묶고, 실패한 묶음은 원래 TU 로 다시 돈다."""
    import cindex_speed as sp
    indexer = find_indexer(a.indexer)
    if not indexer:
        print("clangd-indexer 를 못 찾았다. clangd 릴리스의 indexing tools 를 받아 PATH 나 "
              "~/.claude/tools/clangd/bin 에 두거나 --indexer / CLANGD_INDEXER 로 준다 (references/cindex.md). "
              "clangd 만 있으면 --mode bg 를 쓴다.")
        return None, None
    cdb = resolve_cdb(a.cdb, root, eng)
    if not cdb:
        print("compile_commands.json 을 못 찾았다. UE 는 `cindex.py cdb`, 그 외는 빌드 시스템으로 만들고 --cdb 로 준다.")
        return None, None
    flt = a.filter or default_filter(scope, root, eng)
    fmt = a.format
    if a.unity and fmt != "binary":
        print("--unity 는 --format binary 와 같이 쓴다 (실패한 묶음을 다시 돌린 결과를 합칠 때 RIFF 를 읽는다).")
        return None, None
    info = {"source": "clangd-indexer", "indexer": indexer, "cdb": str(cdb), "filter": flt or "", "scope": scope,
            "format": fmt}
    if not a.unity:
        out, took, errors, rc = _run_indexer(indexer, staged_cdb(cdb, out_dir), out_dir, fmt, a.jobs, a.extra_arg, flt)
        errors.pop("failed_all", None)
        info.update({"mode": "clangd-indexer (전체)", "tus": errors["tus"], "exit": str(rc), "elapsed_index": f"{took:.2f}",
                     "errors": errors, "out_bytes": out.stat().st_size})
        if rc != 0 and out.stat().st_size == 0:
            harness_emit("index.clangd", f"clangd-indexer 실패 (종료 {rc})", ok=False, project=root)
            return None, None
        return out, info
    entries = sp.filter_entries(sp.entries_of(cdb), flt)
    batched, members = sp.unity_entries(entries, a.unity, out_dir / "unity", _module_of_path(roots))
    staged = sp.write_cdb(batched, out_dir / "unity-cdb" / "compile_commands.json")
    print(f"유니티 묶음: TU {len(entries)} → {len(batched)} (묶음 {len(members)}개, 묶음당 최대 {a.unity})")
    out, took, errors, rc = _run_indexer(indexer, staged, out_dir, fmt, a.jobs, a.extra_arg, None)
    outs, total = [out], took
    mem = {sp.npath(b): {sp.npath(x) for x in ms} for b, ms in members.items()}
    failed_all = [sp.npath(f) for f in errors.pop("failed_all", [])]
    failed_b = [f for f in failed_all if f in mem]
    single_failed = [f for f in failed_all if f not in mem]
    retry_set = set().union(*(mem[b] for b in failed_b)) if failed_b else set()
    retry = [e for e in entries if sp.npath(e["file"]) in retry_set]
    if retry:
        print(f"실패한 묶음 {len(failed_b)}개 → 원래 TU {len(retry)}개로 다시 색인")
        staged2 = sp.write_cdb(retry, out_dir / "unity-retry-cdb" / "compile_commands.json")
        out2, took2, e2, _ = _run_indexer(indexer, staged2, out_dir, fmt, a.jobs, a.extra_arg, None, tag="-retry")
        e2.pop("failed_all", None)
        outs.append(out2)
        total += took2
        # 오류 줄 수에는 유니티 때문에만 난 오류(묶음 안 이름 충돌 등)도 들어 있다
        errors = {"count": errors["count"] + e2["count"], "generated_h": errors["generated_h"] + e2["generated_h"],
                  "failed_tu": len(single_failed) + e2["failed_tu"], "failed_sample": (single_failed + e2["failed_sample"])[:30],
                  "sample": errors["sample"][:15] + e2["sample"][:15], "tus": len(entries), "unity_failed": len(failed_b)}
    else:
        errors["unity_failed"] = 0
    info.update({"mode": f"clangd-indexer (유니티 {a.unity})", "tus": len(entries), "batches": len(batched),
                 "exit": str(rc), "elapsed_index": f"{total:.2f}", "errors": errors,
                 "out_bytes": sum(o.stat().st_size for o in outs)})
    return (outs if len(outs) > 1 else out), info


def build_background(root, eng, scope, a, out_dir, roots):
    """clangd 배경 색인 샤드로 증분 색인 (cindex_speed.py 머리말). 샤드는 <색인 폴더>/bg/.cache/clangd/index 에만 쓴다
    (--compile-commands-dir 를 주면 모든 파일이 그 CDB 프로젝트에 속해 샤드가 거기로 간다 — GlobalCompilationDatabase.cpp)."""
    import cindex_speed as sp
    clangd = find_clangd(a.clangd)
    if not clangd:
        print("clangd 를 못 찾았다. PATH 나 ~/.claude/tools/clangd/bin 에 두거나 --clangd / CLANGD 로 준다.")
        return None, None
    cdb = resolve_cdb(a.cdb, root, eng)
    if not cdb:
        print("compile_commands.json 을 못 찾았다. UE 는 `cindex.py cdb`, 그 외는 빌드 시스템으로 만들고 --cdb 로 준다.")
        return None, None
    flt = a.filter or default_filter(scope, root, eng)
    bg = out_dir / "bg"
    bg.mkdir(parents=True, exist_ok=True)
    t_plan = time.time()
    entries = sp.filter_entries(sp.entries_of(cdb), flt)
    if not entries:
        print("필터 뒤 남은 번역 단위가 없다 — --filter 나 --scope 를 확인한다.")
        return None, None
    n_tus, originals, members = len(entries), entries, {}
    state_path = bg / "state.json"
    state = sp.load_state(state_path)
    split = set(state.get("split", ()))  # 묶었더니 오류가 난 파일 — --unity 를 껐다 켜도 기억한다
    if a.unity:
        entries, members = sp.unity_entries(originals, a.unity, bg / "unity", _module_of_path(roots), split)
        print(f"유니티 묶음: TU {n_tus} → {len(entries)} (묶음 {len(members)}개" +
              (f", 오류로 푼 파일 {len(split)}개" if split else "") + ")")
    sp.write_cdb(entries, bg / "compile_commands.json")
    store = sp.ShardStore(bg, state.get("shards")).scan()
    why, changed, files_now = sp.plan(entries, store, state)
    for k in why:
        sh = store.own.get(k)
        if sh and sh.exists():
            sh.unlink()
    reasons = {}
    for r in why.values():
        reasons[r] = reasons.get(r, 0) + 1
    t_plan = time.time() - t_plan
    cold = not store.own
    print(f"{'처음 색인' if cold else '증분'} · TU {len(entries)} · 바뀐 파일 {len(changed)} · 강제 재색인 TU {len(why)}"
          + (f" ({', '.join(f'{k} {v}' for k, v in reasons.items())})" if reasons else "") + f" [계획 {t_plan:.2f}s]")
    # 열 파일: CDB 를 읽게 하는 방아쇠일 뿐. 빈 파일 + .clangd(표준 라이브러리 색인 끔)로 미리보기 비용을 없앤다
    probe_dir = bg / "probe"
    probe_dir.mkdir(exist_ok=True)
    (probe_dir / ".clangd").write_text("Index:\n  StandardLibrary: No\nCompileFlags:\n  Remove: ['*']\n", encoding="utf-8")
    probe = probe_dir / "cindex_probe.cpp"
    probe.write_text("// cindex.py 배경 색인 방아쇠\n", encoding="utf-8")
    print(f"실행: {clangd} --background-index --compile-commands-dir={bg}" + (f" -j={a.jobs}" if a.jobs else ""))
    try:
        res = sp.run_background_index(clangd, bg, probe, a.jobs, log_path=bg / "clangd.log", timeout=a.timeout or None)
    except (TimeoutError, RuntimeError, OSError) as e:
        print(f"배경 색인 실패: {e} ({bg / 'clangd.log'})")
        harness_emit("index.clangd", f"배경 색인 실패: {e}", ok=False, project=root)
        return None, None
    if res["crashed"]:
        print(f"clangd 가 도중에 끝났다 — {bg / 'clangd.log'} 를 본다.")
    store.scan()
    bad_batches = [b for b in members if sp.npath(b) in store.errors]
    if bad_batches:
        # 묶음에서만 나는 오류(파일 범위 이름 충돌 등)일 수 있다 → 그 묶음을 풀어 원래 TU 로 한 번 더 돈다. 다음 빌드도 풀어 둔다
        for b in bad_batches:
            split.update(sp.npath(m) for m in members[b])
            sh = store.own.get(sp.npath(b))
            if sh and sh.exists():
                sh.unlink()
        entries, members = sp.unity_entries(originals, a.unity, bg / "unity", _module_of_path(roots), split)
        sp.write_cdb(entries, bg / "compile_commands.json")
        for k in sp.not_tu_yet(entries, store):
            store.own[k].unlink(missing_ok=True)
        print(f"오류 난 묶음 {len(bad_batches)}개를 풀어 다시 색인 (TU {len(entries)})")
        try:
            res2 = sp.run_background_index(clangd, bg, probe, a.jobs, log_path=bg / "clangd-retry.log",
                                           timeout=a.timeout or None)
        except (TimeoutError, RuntimeError, OSError) as e:
            print(f"묶음을 푼 재색인 실패: {e} ({bg / 'clangd-retry.log'})")
            res2 = {"elapsed": 0, "indexed": [], "enqueued": None, "crashed": True, "failed": [str(e)]}
        res = {"elapsed": res["elapsed"] + res2["elapsed"], "indexed": res["indexed"] + res2["indexed"],
               "enqueued": res2["enqueued"], "crashed": res["crashed"] or res2["crashed"],
               "failed": res["failed"] + res2["failed"]}
        store.scan()
    tu_keys = {sp.npath(e["file"]) for e in entries}
    forced = {sp.npath(q) for e in entries for q in sp.forced_includes(e)}
    reach = store.reachable(tu_keys | forced)
    shards = sorted(str(store.own[k]) for k in reach if k in store.own)
    keep = {Path(s).name for s in shards}
    removed = 0
    for name in list(store.cache):
        if name not in keep:  # CDB 에서 빠진 TU 와 그것만 포함하던 헤더의 샤드
            (store.dir / name).unlink(missing_ok=True)
            store.cache.pop(name)
            removed += 1
    sp.save_state(state_path, entries, store, files_now, reach, split)
    rebuilt = sorted({sp.npath(x) for x in res["indexed"]} & tu_keys)
    bad = sorted(tu_keys & store.errors)
    errors = {"count": None, "failed_tu": len(bad), "failed_sample": bad[:30], "sample": res["failed"][:30],
              "tus": len(entries), "note": "배경 색인은 오류 줄을 세지 않는다 — 샤드의 HadErrors 표시로 오류 TU 를 센다"}
    print(f"배경 색인 [{res['elapsed']:.1f}s] · 다시 색인 {len(rebuilt)} · 재사용 {len(entries) - len(rebuilt)} · "
          f"샤드 {len(shards)} · 지운 샤드 {removed} · 오류 있던 TU {len(bad)}")
    info = {"source": "clangd-background", "clangd": clangd, "cdb": str(cdb), "filter": flt or "", "scope": scope,
            "mode": "clangd 배경 색인 (증분)" + (f" · 유니티 {a.unity}" if a.unity else ""), "tus": n_tus,
            "batches": len(entries) if a.unity else None, "elapsed_plan": f"{t_plan:.2f}",
            "elapsed_index": f"{res['elapsed']:.2f}", "rebuilt": len(rebuilt), "reused": len(entries) - len(rebuilt),
            "invalidated": len(why), "invalidated_reasons": reasons, "changed_files": len(changed), "shards": len(shards),
            "unity_split": len(split) if a.unity else None,
            "errors": errors, "out_bytes": sum(Path(s).stat().st_size for s in shards), "cold": cold}
    return shards, info


def cmd_build(root, kind, a):
    eng = engine_dir_of(root, kind)
    scope = a.scope
    db = Path(a.db) if a.db and a.db not in ("engine", "project") else db_for(scope if scope != "all" else "project", root, kind)
    if db is None:
        print("engine 범위는 UE 프로젝트에서만 쓴다.")
        return 1
    roots = [("project", root), ("engine", eng)]
    out_dir = db.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.yaml:
        src, info = Path(a.yaml), {"source": "file", "mode": "적재만"}
    elif a.mode == "bg":
        src, info = build_background(root, eng, scope, a, out_dir, roots)
    else:
        src, info = build_indexer(root, eng, scope, a, out_dir, roots)
    if src is None:
        return 1
    errors = info.get("errors") if isinstance(info.get("errors"), dict) else {}
    if errors.get("generated_h"):
        print("  [경고] .generated.h 누락·낡음 — UCLASS 타입이 인덱스에서 빠진다. 에디터 빌드(UHT) 한 번 뒤 다시 build.")
    counts = ingest(src, db, roots, info, dedupe_refs=a.mode != "bg" and isinstance(src, list))
    print(f"적재 완료 · 심볼 {counts['symbols']} · 참조 {counts['refs']} · 관계 {counts['relations']} · 파일 {counts['files']} → {db}")
    if not a.keep_yaml and not a.yaml and a.mode != "bg":
        for s in (src if isinstance(src, list) else [src]):
            Path(s).unlink(missing_ok=True)
    failed = errors.get("failed_tu", 0)
    detail = f"{scope} · {info.get('mode', '')} · 심볼 {counts['symbols']} · 참조 {counts['refs']} · 관계 {counts['relations']}"
    if info.get("rebuilt") is not None:
        detail += f" · 재색인 {info['rebuilt']}/{info.get('batches') or info.get('tus')}"
    harness_emit("index.clangd", detail + (f" · 실패 TU {failed}" if failed else ""), ok=not failed, project=root)
    return 0


GENERATED_RE = re.compile(r"\.generated\.h|_PROLOG\b|GENERATED_BODY|GENERATED_UCLASS_BODY")
PROGRESS_RE = re.compile(r"^\[(\d+)/(\d+)\] Processing file")


def summarize_errors(err_path, keep=30):
    """clangd-indexer 는 번역 단위(TU)가 실패해도 종료 코드 0 이다 → stderr 로 판정한다.
    'Error while processing <파일>' = 실패한 TU. UE 에서 가장 흔한 원인은 .generated.h 누락·낡음(UHT 미실행)이고,
    그러면 UCLASS 타입과 그 멤버가 인덱스에서 조용히 빠진다."""
    count, generated, failed, sample, failed_all, tus = 0, 0, 0, [], [], 0
    try:
        with open(err_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = PROGRESS_RE.match(line)
                if m:  # all-TUs 실행기의 진행 줄 '[i/N] Processing file …' — N 이 처리 대상 TU 수
                    tus = max(tus, int(m.group(2)))
                elif line.startswith("Error while processing"):
                    failed += 1
                    failed_all.append(line.strip()[len("Error while processing "):].rstrip("."))
                elif " error: " in line or line.startswith("error:"):
                    count += 1
                    generated += bool(GENERATED_RE.search(line))
                    if len(sample) < keep:
                        sample.append(line.strip()[:300])
    except OSError:
        pass
    return {"count": count, "generated_h": generated, "failed_tu": failed, "failed_sample": failed_all[:keep], "sample": sample,
            "tus": tus, "failed_all": failed_all}


# ---------------------------------------------------------------- 조회

class Index:
    def __init__(self, db_path):
        self.path = Path(db_path)
        self.con = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
        self.lock = threading.Lock()
        self.meta = dict(self.q("SELECT key, value FROM meta"))
        self.roots = {n: p for n, p in json.loads(self.meta.get("roots", "[]"))}

    def q(self, sql, args=()):
        with self.lock:
            return self.con.execute(sql, args).fetchall()

    SYM = ("SELECT s.id, s.name, s.scope, s.kind, df.rel, df.root, s.decl_line, s.decl_col, ff.rel, ff.root, s.def_line, "
           "s.signature, s.return_type, s.type, s.flags, s.nrefs, df.module, df.path, ff.path, s.tpl_args, s.doc "
           "FROM symbols s LEFT JOIN files df ON df.id=s.decl_file LEFT JOIN files ff ON ff.id=s.def_file ")

    @staticmethod
    def row(r):
        return {"id": r[0], "name": r[1], "scope": r[2], "kind": r[3],
                "path": (("[E] " if r[5] == "engine" else "") + (r[4] or "")) if r[4] is not None else "",
                "line": r[6], "col": r[7],
                "def_path": (("[E] " if r[9] == "engine" else "") + (r[8] or "")) if r[8] is not None else "",
                "def_line": r[10], "signature": r[11], "return_type": r[12], "type": r[13],
                "deprecated": bool((r[14] or 0) & FLAG_DEPRECATED), "refs": r[15], "module": r[16] or "",
                "abs_path": r[17], "abs_def_path": r[18], "tpl_args": r[19], "doc": r[20]}

    def find(self, name, limit=200, kinds=None):
        name = name.strip()
        rows = self.q(self.SYM + "WHERE s.qname = ? OR (s.name = ? AND ? NOT LIKE '%::%')", (name, name, name))
        if not rows:
            rows = self.q(self.SYM + "WHERE s.name LIKE ? OR s.qname LIKE ? LIMIT ?", (f"%{name}%", f"%{name}%", limit * 4))
        out = [self.row(r) for r in rows]
        if kinds:
            out = [s for s in out if s["kind"] in kinds]
        pref = {k: i for i, k in enumerate(TYPE_KINDS + FUNC_KINDS)}
        out.sort(key=lambda s: (s["name"].lower() != name.split("::")[-1].lower(), pref.get(s["kind"], 50),
                                s["tpl_args"] != "", len(s["scope"]), s["path"]))
        return out[:limit]

    def by_id(self, sid):
        r = self.q(self.SYM + "WHERE s.id = ?", (sid,))
        return self.row(r[0]) if r else None

    def names(self, ids):
        out = {}
        for sid in ids:
            s = self.by_id(sid) if sid and sid != NULL_ID else None
            out[sid] = s
        return out

    def refs(self, sid, mask=None, limit=500):
        rows = self.q("SELECT r.kind, f.rel, f.root, r.line, r.col, r.container, f.path FROM refs r "
                      "LEFT JOIN files f ON f.id=r.file WHERE r.sym=? ORDER BY f.rel, r.line LIMIT ?", (sid, limit * 3))
        out = [{"kind": k, "path": ("[E] " if root == "engine" else "") + (rel or ""), "line": ln, "col": c,
                "container": cont, "abs_path": ap} for k, rel, root, ln, c, cont, ap in rows if not mask or k & mask]
        return out[:limit]

    def callers(self, sid):
        rows = self.q("SELECT container, COUNT(*) FROM refs WHERE sym=? AND (kind & ?) != 0 GROUP BY container "
                      "ORDER BY COUNT(*) DESC", (sid, REF))
        return [(self.by_id(c) if c != NULL_ID else None, n) for c, n in rows]

    def caller_sites(self, sid, limit):
        """호출자마다 첫 참조 위치 하나 (줄 원문을 같이 보이려고)."""
        rows = self.q("SELECT r.container, COUNT(*), MIN(r.rowid) FROM refs r WHERE r.sym=? AND (r.kind & ?) != 0 "
                      "GROUP BY r.container ORDER BY COUNT(*) DESC LIMIT ?", (sid, REF, limit))
        out = []
        for cont, n, rid in rows:
            site = self.q("SELECT f.rel, f.root, r.line, f.path FROM refs r JOIN files f ON f.id=r.file WHERE r.rowid=?", (rid,))
            rel, root, line, ap = site[0] if site else ("", "", 0, None)
            out.append((self.by_id(cont) if cont != NULL_ID else None, n,
                        {"path": ("[E] " if root == "engine" else "") + (rel or ""), "line": line, "abs_path": ap}))
        return out

    def members(self, s):
        prefix = s["scope"] + s["name"] + "::"
        rows = self.q(self.SYM + "WHERE s.scope = ? ORDER BY s.decl_file, s.decl_line", (prefix,))
        return [self.row(r) for r in rows]

    def callees(self, sid):
        # Call 비트는 함수류 심볼에 대한 모든 참조에 붙는다(선언·&Fn 포함) — Reference 비트와 같이 본다
        rows = self.q("SELECT r.sym, COUNT(*) FROM refs r JOIN symbols s ON s.id=r.sym WHERE r.container=? "
                      "AND (r.kind & ?) = ? AND s.kind IN (%s) GROUP BY r.sym ORDER BY COUNT(*) DESC"
                      % ",".join("?" * len(FUNC_KINDS)), (sid, REF | CALL, REF | CALL) + FUNC_KINDS)
        return [(self.by_id(x), n) for x, n in rows]

    def related(self, sid, predicate, forward):
        if forward:
            rows = self.q("SELECT object FROM relations WHERE subject=? AND predicate=?", (sid, predicate))
        else:
            rows = self.q("SELECT subject FROM relations WHERE object=? AND predicate=?", (sid, predicate))
        return [s for s in (self.by_id(r[0]) for r in rows) if s]

    def bases(self, sid):
        return self.related(sid, BASE_OF, False)

    def derived(self, sid):
        return self.related(sid, BASE_OF, True)


class LineCache:
    """참조마다 그 줄 원문을 붙인다 — 위치만 주면 에이전트가 파일을 다시 연다 (references/indexing-research.md)."""

    def __init__(self):
        self.files = {}

    def text(self, path, line, width=140):
        if not path or not line:
            return ""
        if path not in self.files:
            try:
                with open(path, "rb") as f:
                    self.files[path] = f.read().decode("utf-8", "replace").splitlines()
            except OSError:
                self.files[path] = None
        lines = self.files[path]
        if not lines or line > len(lines):
            return ""
        t = lines[line - 1].strip()
        return t if len(t) <= width else t[:width] + "…"


def fmt(s):
    if s is None:
        return "(파일 범위)"
    loc = f"{s['path']}:{s['line']}" if s["path"] else "(위치 없음)"
    sig = s["signature"] if s["kind"] in FUNC_KINDS else ""
    dep = " [deprecated]" if s["deprecated"] else ""
    return f"{s['kind']:<15} {s['scope']}{s['name']}{s['tpl_args']}{sig}  {loc}{dep}"


def impact_lines(ix, s, limit):
    """이 심볼을 바꾸면 같이 봐야 할 곳: 파생 타입(3단계), 재정의, 참조하는 함수, 참조가 있는 파일·모듈."""
    out = []
    if s["kind"] in TYPE_KINDS:
        seen, frontier = {}, [s["id"]]
        for depth in range(1, 4):
            nxt = []
            for sid in frontier:
                for d in ix.derived(sid):
                    if d["id"] not in seen:
                        seen[d["id"]] = (depth, d)
                        nxt.append(d["id"])
            frontier = nxt
        out.append(f"## 파생 타입 {len(seen)}")
        out += [f"  {'  ' * (dep - 1)}{fmt(d)}" for dep, d in sorted(seen.values(), key=lambda x: x[0])[:limit]]
    if s["kind"] in FUNC_KINDS:
        seen, frontier = {}, [s["id"]]
        for depth in range(1, 4):
            nxt = []
            for sid in frontier:
                for d in ix.related(sid, OVERRIDDEN_BY, True):
                    if d["id"] not in seen:
                        seen[d["id"]] = (depth, d)
                        nxt.append(d["id"])
            frontier = nxt
        out.append(f"## 재정의한 쪽 {len(seen)} (3단계까지)")
        out += [f"  {'  ' * (dep - 1)}{fmt(d)}" for dep, d in sorted(seen.values(), key=lambda x: x[0])[:limit]]
    callers = [(x, n) for x, n in ix.callers(s["id"])]
    out.append(f"## 참조하는 함수·범위 {len(callers)}")
    out += [f"  {n:>4}× {fmt(x)}" for x, n in callers[:limit]]
    rows = ix.q("SELECT f.module, f.rel, COUNT(*) FROM refs r JOIN files f ON f.id=r.file WHERE r.sym=? AND (r.kind & ?) != 0 "
                "GROUP BY f.id ORDER BY COUNT(*) DESC", (s["id"], REF))
    mods = {}
    for m, _, n in rows:
        mods[m or "(모듈 없음)"] = mods.get(m or "(모듈 없음)", 0) + n
    out.append(f"## 참조가 있는 파일 {len(rows)} · 모듈 {len(mods)}: " + ", ".join(f"{m} {n}" for m, n in sorted(mods.items(), key=lambda x: -x[1])))
    out += [f"  {n:>4}× {rel}" for _, rel, n in rows[:limit]]
    return out


def open_index(a, root, kind):
    db = pick_db(a.db, root, kind)
    if not db or not db.exists():
        print(f"clangd 인덱스 없음: {db}. `cindex.py build` 를 먼저 돌린다.")
        return None
    return Index(db)


def pick_one(ix, name, kinds=None):
    cands = ix.find(name, limit=20, kinds=kinds)
    if not cands:
        print(f"없음: {name!r}")
        return None, []
    return cands[0], cands[1:]


def cmd_query(a, root, kind):
    ix = open_index(a, root, kind)
    if ix is None:
        return 1
    c, arg = a.command, " ".join(a.arg).strip()
    if c == "status":
        counts = json.loads(ix.meta.get("counts", "{}"))
        errors = json.loads(ix.meta.get("errors", '{"count": 0}')) if ix.meta.get("errors") else {"count": "?"}
        print(f"인덱스 {ix.path} · {ix.meta.get('generated_at')} · 심볼 {counts.get('symbols')} · 참조 {counts.get('refs')} · "
              f"관계 {counts.get('relations')} · 파일 {counts.get('files')}")
        print(f"출처 {ix.meta.get('source')} · cdb {ix.meta.get('cdb', '-')} · 필터 {ix.meta.get('filter', '-') or '-'} · "
              f"실패 TU {errors.get('failed_tu', '?')} · 오류 줄 {'-' if errors.get('count') is None else errors.get('count')}"
              + (f" (.generated.h 관련 {errors.get('generated_h')})" if errors.get("generated_h") else ""))
        stale = [p for (p, m) in ix.q("SELECT path, mtime FROM files ORDER BY RANDOM() LIMIT 300")
                 if not os.path.exists(p) or int(os.stat(p).st_mtime) != m]
        print(f"[낡음] 표본 파일 {len(stale)}개가 인덱스 뒤 바뀌었다 → build" if stale else "신선도: 표본 300 파일 OK")
        return 0
    if not arg:
        raise SystemExit(f"{c} 는 인자가 필요하다.")
    if c == "sym":
        rows = ix.find(arg, limit=a.limit)
        emit([fmt(s) + (f"\n    정의 {s['def_path']}:{s['def_line']}" if s["def_path"] and s["def_path"] != s["path"] else "")
              for s in rows] or [f"없음: {arg!r}"], a.full)
        return 0
    if c == "file":
        rows = ix.q(Index.SYM + "WHERE df.rel LIKE ? ORDER BY df.rel, s.decl_line LIMIT ?", (f"%{arg}%", a.limit * 4))
        emit([fmt(Index.row(r)) for r in rows] or [f"없음: {arg!r}"], a.full)
        return 0
    kinds = FUNC_KINDS if c in ("callees", "overrides") else (TYPE_KINDS if c in ("bases", "derived", "members") else None)
    s, others = pick_one(ix, arg, kinds)
    if s is None:
        return 1
    head = [f"# {fmt(s)}"] + ([f"# 같은 이름 후보 {len(others)}개 더 — A::B 로 좁힌다"] if others else [])
    lc = LineCache()
    if c == "refs":
        mask = {"decl": DECL, "def": DEF, "ref": REF}.get(a.kind)
        rows = ix.refs(s["id"], mask, a.limit)
        names = ix.names({r["container"] for r in rows})
        lines = [f"{'D' if r['kind'] & DEF else 'd' if r['kind'] & DECL else 'r'} {r['path']}:{r['line']}:{r['col']}"
                 f"  in {(names.get(r['container']) or {}).get('name', '(파일 범위)')}  │ {lc.text(r['abs_path'], r['line'])}"
                 for r in rows]
        emit(head + (lines or ["참조 없음"]), a.full)
    elif c == "callers":
        emit(head + [f"{n:>4}× {fmt(x)}\n       {site['path']}:{site['line']}  │ {lc.text(site['abs_path'], site['line'])}"
                     for x, n, site in ix.caller_sites(s["id"], a.limit)] or ["없음"], a.full)
    elif c == "members":
        rows = ix.members(s)
        emit(head + [f"{m['kind']:<15} {m['name']:<32} :{m['line']}  │ {lc.text(m['abs_path'], m['line'])}" for m in rows[:a.limit * 3]]
             + ([f"… (+{len(rows) - a.limit * 3})"] if len(rows) > a.limit * 3 else []) or ["멤버 없음"], a.full)
    elif c == "impact":
        emit(head + impact_lines(ix, s, a.limit), a.full)
    elif c == "callees":
        emit(head + [f"{n:>4}× {fmt(x)}" for x, n in ix.callees(s["id"])[:a.limit]] or ["없음"], a.full)
    elif c in ("bases", "derived"):
        emit(head + [fmt(x) for x in (ix.bases if c == "bases" else ix.derived)(s["id"])] or ["없음"], a.full)
    elif c == "overrides":
        up = ix.related(s["id"], OVERRIDDEN_BY, False)
        down = ix.related(s["id"], OVERRIDDEN_BY, True)
        emit(head + [f"재정의 대상(위) {fmt(x)}" for x in up] + [f"재정의한 쪽(아래) {fmt(x)}" for x in down] or ["없음"], a.full)
    return 0


# ---------------------------------------------------------------- 웹뷰 소스 (index_view.py 가 쓴다)

def _lines(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return None


class CindexSource:
    engine = "clangd"
    modes = ["inherit", "calls", "overrides", "modules"]

    def __init__(self, scope, db):
        self.name = f"clangd-{scope}"
        self.label = f"{'엔진' if scope == 'engine' else '프로젝트'} · clangd (cindex)"
        self.scope, self.db = scope, db
        self.covers = {"engine", "project"} if scope == "project" else {"engine"}
        self.available = bool(db and db.exists())
        self.ix = Index(db) if self.available else None

    def info(self):
        if not self.available:
            return {"missing": f"{self.db} 없음 — `cindex.py build --scope {self.scope}`"}
        m = self.ix.meta
        errors = json.loads(m["errors"]) if m.get("errors") else {}
        return {"db": str(self.db), "built": m.get("generated_at"), "counts": json.loads(m.get("counts", "{}")),
                "cdb": m.get("cdb"), "filter": m.get("filter"), "errors": errors.get("count")}

    def _out(self, s):
        return dict(s, src=self.name)

    def search(self, text, limit):
        return [self._out(s) for s in self.ix.find(text, limit)]

    def by_name(self, name):
        return [self._out(s) for s in self.ix.find(name, 20) if s["name"].lower() == name.lower()]

    def detail(self, sid):
        s = self.ix.by_id(sid)
        if s is None:
            return None
        path, line = (s["abs_def_path"], s["def_line"]) if s["kind"] in TYPE_KINDS and s["abs_def_path"] else (s["abs_path"], s["line"])
        lines = _lines(path)
        if lines and line:
            start = max(0, line - 1)
            if start > 0 and ue_q.MACRO.match(lines[start - 1]):
                start -= 1
            end = ue_q.block_end(lines, line - 1)[0]
            s["snippet"] = {"start": start + 1, "lines": lines[start:min(end + 1, start + 200)]}
        rel = {}
        if s["kind"] in TYPE_KINDS:
            rel["부모"] = [self._out(x) for x in self.ix.bases(sid)]
            rel["자식"] = [self._out(x) for x in self.ix.derived(sid)]
        if s["kind"] in FUNC_KINDS:
            rel["재정의 대상"] = [self._out(x) for x in self.ix.related(sid, OVERRIDDEN_BY, False)]
            rel["재정의한 쪽"] = [self._out(x) for x in self.ix.related(sid, OVERRIDDEN_BY, True)]
            rel["호출하는 쪽 (참조 Container)"] = [self._out(x) for x, _ in self.ix.callers(sid) if x][:60]
            rel["부르는 함수"] = [self._out(x) for x, _ in self.ix.callees(sid) if x][:60]
        refs = self.ix.refs(sid, None, 60)
        s["ref_rows"] = self.ix.q("SELECT COUNT(*) FROM refs WHERE sym=?", (sid,))[0][0]
        rel["참조 위치"] = [{"id": sid, "src": self.name, "name": f"{'정의' if r['kind'] & DEF else '선언' if r['kind'] & DECL else '참조'}",
                          "path": r["path"], "line": r["line"]} for r in refs]
        s["relations"] = rel
        return self._out(s)

    def graph(self, mode, focus, depth):
        from index_view import bfs_graph
        ix = self.ix
        if mode == "modules":
            return self._module_graph(focus, depth)
        kinds = FUNC_KINDS if mode in ("calls", "overrides") else TYPE_KINDS
        starts = [s["id"] for s in ix.find(focus, 3, kinds)][:1]
        cache = {}

        def sym(i):
            if i not in cache:
                cache[i] = ix.by_id(i) or {"name": i, "kind": "?", "scope": ""}
            return cache[i]

        def nb(i):
            if mode == "inherit":
                return [(b["id"], "base", True) for b in ix.bases(i)] + [(d["id"], "base", False) for d in ix.derived(i)][:40]
            if mode == "overrides":
                return ([(x["id"], "overrides", True) for x in ix.related(i, OVERRIDDEN_BY, False)] +
                        [(x["id"], "overrides", False) for x in ix.related(i, OVERRIDDEN_BY, True)])
            out = [(x["id"], "calls", True) for x, _ in ix.callees(i) if x][:25]
            return out + [(x["id"], "calls", False) for x, _ in ix.callers(i) if x and x["kind"] in FUNC_KINDS][:25]
        return bfs_graph(starts, nb, lambda i: sym(i)["scope"] + sym(i)["name"], lambda i: sym(i)["kind"], depth,
                         lambda i: {"module": sym(i).get("module"), "path": sym(i).get("path"), "line": sym(i).get("line")})

    def _module_graph(self, focus, depth):
        """실제 참조로 본 모듈 의존: 모듈 A 파일의 참조가 모듈 B 에 선언된 심볼을 가리키면 A → B."""
        rows = self.ix.q("SELECT rf.module, df.module, COUNT(*) FROM refs r JOIN files rf ON rf.id=r.file "
                         "JOIN symbols s ON s.id=r.sym JOIN files df ON df.id=s.decl_file "
                         "WHERE rf.module != '' AND df.module != '' AND rf.module != df.module "
                         "AND (r.kind & ?) != 0 GROUP BY rf.module, df.module", (REF,))
        edges = {}
        for a, b, n in rows:
            edges.setdefault(a, []).append((b, n))
        rev = {}
        for a, outs in edges.items():
            for b, n in outs:
                rev.setdefault(b, []).append((a, n))
        mods = set(edges) | set(rev)
        starts = [m for m in mods if m.lower() == focus.lower()] or sorted(mods, key=lambda m: -len(edges.get(m, [])))[:3]
        from index_view import bfs_graph
        weight = {}

        def nb(m):
            out = [(b, "refs", True) for b, n in edges.get(m, [])] + [(a, "refs", False) for a, n in rev.get(m, [])]
            for b, n in edges.get(m, []):
                weight[(m, b)] = n
            return out[:60]
        g = bfs_graph(starts, nb, lambda m: m, lambda m: "module", depth)
        for e in g["edges"]:
            e["kind"] = f"refs ×{weight.get((e['source'], e['target']), '?')}"
        return g

    def checks(self):
        ix = self.ix
        out = []
        rows = ix.q("SELECT s.name, f.path, s.decl_line, s.decl_col FROM symbols s JOIN files f ON f.id=s.decl_file "
                    "WHERE s.kind NOT IN ('Macro', 'Unknown') AND s.name != '' ORDER BY RANDOM() LIMIT 300")
        bad, cache = [], {}
        for name, path, line, col in rows:
            lines = cache.setdefault(path, _lines(path))
            ok = lines is not None and 0 < line <= len(lines) and lines[line - 1][col - 1:col - 1 + len(name)] == name
            if not ok:
                bad.append(f"{name} {path}:{line}:{col}")
        out.append({"name": "좌표 정확도 (열까지)", "metric": f"{len(rows) - len(bad)}/{len(rows)}",
                    "pass": bool(rows) and len(bad) <= len(rows) * 0.02,
                    "why": "clangd 좌표는 컴파일러가 낸 것이라 줄·열이 정확해야 한다. 틀리면 적재 변환(0→1 기준)이나 파일이 바뀐 것이다. "
                           "매크로가 만든 이름(GENERATED_BODY 안 등)은 철자가 그 자리에 없을 수 있다.",
                    "samples": bad[:20]})
        files = ix.q("SELECT path, mtime FROM files ORDER BY RANDOM() LIMIT 400")
        changed = [p for p, m in files if not os.path.exists(p) or int(os.stat(p).st_mtime) != m]
        out.append({"name": "신선도 (파일 표본)", "metric": f"변경 {len(changed)}/{len(files)}", "pass": not changed,
                    "why": "인덱스 뒤 바뀐 파일. 있으면 `cindex.py build`.", "samples": changed[:20]})
        errors = json.loads(ix.meta["errors"]) if ix.meta.get("errors") else None
        if errors is not None:
            bg = errors.get("count") is None
            out.append({"name": "clangd 실패 TU" if not bg else "clangd 오류 있던 TU (배경 색인)",
                        "metric": f"실패 TU {errors.get('failed_tu', '?')} · 오류 줄 {'-' if bg else errors['count']} · "
                                  f".generated.h 관련 {'-' if bg else errors.get('generated_h', 0)}",
                        "pass": not errors.get("failed_tu") and errors.get("count") in (0, None),
                        "why": "clangd-indexer 는 TU 가 실패해도 종료 코드 0 이라 stderr 로 센다. 실패한 TU 의 심볼·참조는 빠진다. "
                               "UE 에서 .generated.h 누락·낡음(UHT 미실행)이면 UCLASS 타입과 멤버가 통째로 사라진다 — 에디터 빌드 뒤 다시 build.",
                        "samples": errors.get("failed_sample", []) + errors.get("sample", [])})
        n_sym = ix.q("SELECT COUNT(*) FROM symbols")[0][0]
        n_def = ix.q("SELECT COUNT(*) FROM symbols WHERE kind IN ('Class','Struct') AND def_file IS NOT NULL")[0][0]
        n_rel = ix.q("SELECT COUNT(*) FROM relations")[0][0]
        n_cont = ix.q("SELECT COUNT(*) FROM refs WHERE container != ?", (NULL_ID,))[0][0]
        n_ref = ix.q("SELECT COUNT(*) FROM refs")[0][0]
        out.append({"name": "내용 분포", "metric": f"심볼 {n_sym} · 정의 있는 클래스/구조체 {n_def} · 관계 {n_rel} · "
                                               f"Container 있는 참조 {n_cont}/{n_ref}",
                    "pass": n_sym > 0 and (n_ref == 0 or n_cont > 0),
                    "why": "호출자/피호출 함수는 참조의 Container 로 계산한다. Container 가 전부 비면 그 clangd 버전이 기록하지 않는 것이다."})
        return out


    # ---- 웹뷰 개요·파이프라인·행렬·커버리지

    def overview(self):
        ix = self.ix
        m = ix.meta
        kinds = ix.q("SELECT kind, COUNT(*) FROM symbols GROUP BY kind ORDER BY 2 DESC")
        mods = ix.q("SELECT f.module, f.root, COUNT(s.id), COUNT(DISTINCT f.id) FROM files f LEFT JOIN symbols s "
                    "ON s.decl_file=f.id WHERE f.module != '' GROUP BY f.module, f.root ORDER BY 3 DESC LIMIT 400")
        refs_by_mod = dict(ix.q("SELECT f.module, COUNT(*) FROM refs r JOIN files f ON f.id=r.file GROUP BY f.module"))
        rel = dict(ix.q("SELECT predicate, COUNT(*) FROM relations GROUP BY predicate"))
        rk = ix.q("SELECT SUM((kind & 1) != 0), SUM((kind & 2) != 0), SUM((kind & 4) != 0), SUM((kind & 20) = 20), "
                  "SUM(container != ?) FROM refs", (NULL_ID,))[0]
        errors = json.loads(m["errors"]) if m.get("errors") else {}
        return {"counts": json.loads(m.get("counts", "{}")), "kinds": kinds,
                "modules": [{"name": n, "group": root or "외부", "symbols": c, "files": f, "refs": refs_by_mod.get(n, 0)}
                            for n, root, c, f in mods],
                "relations": {"BaseOf": rel.get(BASE_OF, 0), "OverriddenBy": rel.get(OVERRIDDEN_BY, 0)},
                "ref_kinds": {"선언": rk[0] or 0, "정의": rk[1] or 0, "참조": rk[2] or 0, "호출성 참조": rk[3] or 0,
                              "Container 있음": rk[4] or 0},
                "failed_tu": errors.get("failed_tu", 0), "generated_h": errors.get("generated_h", 0),
                "build": {"at": m.get("generated_at"), "mode": m.get("mode", m.get("source")), "tus": m.get("tus"),
                          "seconds_index": m.get("elapsed_index"), "seconds_ingest": m.get("elapsed_ingest")}}

    def pipeline(self):
        m = self.ix.meta

        def val(k):  # meta 는 문자열이 아니면 JSON 으로 저장된다
            v = m.get(k)
            try:
                return json.loads(v) if isinstance(v, str) and v[:1] in "{[0123456789-tfn" else v
            except ValueError:
                return v
        errors = val("errors") or {}
        hist = json.loads(m.get("history", "[]"))
        last = hist[-1] if hist else {}
        bg = m.get("source") == "clangd-background"
        stages = []
        if m.get("elapsed_cdb"):
            stages.append({"name": "compile_commands 준비", "seconds": float(m["elapsed_cdb"])})
        if m.get("elapsed_plan"):
            stages.append({"name": "무효화 계획 (바뀐 파일 → 포함한 TU)", "seconds": float(m["elapsed_plan"])})
        stages.append({"name": "clangd 배경 색인 (바뀐 TU 만)" if bg else "clangd 색인 (TU 파싱·심볼 수집)",
                       "seconds": float(m.get("elapsed_index") or 0)})
        stages.append({"name": "sqlite 적재" + (" (샤드 읽기)" if bg else ""), "seconds": float(m.get("elapsed_ingest") or 0)})
        units = val("batches") or val("tus")
        incr = None
        if val("rebuilt") is not None:
            incr = {"units": units, "rebuilt": val("rebuilt"), "reused": val("reused"), "invalidated": val("invalidated"),
                    "reasons": val("invalidated_reasons") or {}, "changed_files": val("changed_files"),
                    "shards": val("shards"), "cold": val("cold"), "unity_split": val("unity_split")}
        facts = [["방식", m.get("mode", m.get("source", "-"))], ["범위", m.get("scope", "-")], ["번역 단위", val("tus") or "-"]]
        if val("batches"):
            facts.append(["유니티 묶은 뒤 TU", val("batches")])
        if incr:
            facts += [["다시 색인 / 재사용", f"{incr['rebuilt']} / {incr['reused']}"],
                      ["강제 재색인", f"{incr['invalidated']}" + (" (" + ", ".join(f"{k} {v}" for k, v in incr["reasons"].items()) + ")"
                                                                if incr["reasons"] else "")],
                      ["바뀐 파일", incr["changed_files"]], ["샤드", incr["shards"]]]
        facts += [["실패 TU" if not bg else "오류 있던 TU", errors.get("failed_tu", "-")],
                  ["출력" if not bg else "샤드 합계", _fmt_bytes(last.get("out_bytes"))],
                  ["형식", m.get("format", "-")], ["필터", m.get("filter") or "-"], ["compile_commands", m.get("cdb", "-")]]
        return {"mode": m.get("mode", m.get("source")), "at": m.get("generated_at"), "stages": stages, "facts": facts,
                "history": hist, "errors": errors, "incremental": incr, "units": units}

    def anatomy(self, name=None):
        """clangd 가 심볼 하나에 대해 남기는 원본 레코드 셋(Symbol · Refs · Relations)을 그대로 보인다.
        이름이 없으면 재정의 관계와 참조가 가장 많은 메서드를 고른다 (세 종류가 다 보이게)."""
        ix = self.ix
        sid = None
        if name:
            hits = ix.find(name, 5)
            sid = hits[0]["id"] if hits else None
        if not sid:
            row = ix.q("SELECT s.id FROM symbols s JOIN relations r ON r.subject=s.id AND r.predicate=? "
                       "WHERE s.nrefs > 0 GROUP BY s.id ORDER BY COUNT(*) DESC, s.nrefs DESC LIMIT 1", (OVERRIDDEN_BY,))
            if not row:
                row = ix.q("SELECT sym FROM refs GROUP BY sym ORDER BY COUNT(*) DESC LIMIT 1")
            sid = row[0][0] if row else None
        if not sid:
            return None
        r = ix.q("SELECT s.id, s.name, s.scope, s.kind, s.lang, df.rel, s.decl_line, s.decl_col, ff.rel, s.def_line, "
                 "s.def_col, s.signature, s.return_type, s.flags, s.nrefs, df.module FROM symbols s "
                 "LEFT JOIN files df ON df.id=s.decl_file LEFT JOIN files ff ON ff.id=s.def_file WHERE s.id=?", (sid,))[0]
        symbol = [["ID", r[0]], ["Name", r[1]], ["Scope", r[2] or "(전역)"], ["SymInfo.Kind", r[3]], ["SymInfo.Lang", r[4]],
                  ["CanonicalDeclaration", f"{r[5]}:{r[6]}:{r[7]}" if r[5] else "-"],
                  ["Definition", f"{r[8]}:{r[9]}:{r[10]}" if r[8] else "- (이 인덱스가 본 TU 에 정의 없음)"],
                  ["Signature", r[11] or "-"], ["ReturnType", r[12] or "-"], ["Flags", str(r[13] or 0)],
                  ["References", str(r[14] or 0)]]
        total = ix.q("SELECT COUNT(*) FROM refs WHERE sym=?", (sid,))[0][0]
        refs = ix.refs(sid, None, 12)
        names = ix.names({x["container"] for x in refs})
        bits = [("Decl", DECL), ("Def", DEF), ("Ref", REF), ("Spelled", SPELLED), ("Call", CALL)]
        ref_rows = [{"path": x["path"], "line": x["line"], "col": x["col"], "kind": x["kind"],
                     "bits": [n for n, b in bits if x["kind"] & b],
                     "container": ((names.get(x["container"]) or {}).get("scope", "") +
                                   (names.get(x["container"]) or {}).get("name", "")) or "(없음 · 파일 범위)"} for x in refs]
        rels = []
        for pred, pname in ((BASE_OF, "BaseOf"), (OVERRIDDEN_BY, "OverriddenBy")):
            for subj, obj in ix.q("SELECT subject, object FROM relations WHERE (subject=? OR object=?) AND predicate=? "
                                  "LIMIT 12", (sid, sid, pred)):
                a, b = ix.by_id(subj), ix.by_id(obj)
                qn = lambda s, raw: ((s.get("scope") or "") + s["name"]) if s else raw
                rels.append({"predicate": pname, "subject": qn(a, subj), "object": qn(b, obj),
                             "self_is": "subject" if subj == sid else "object"})
        return {"qname": (r[2] or "") + r[1], "module": r[15] or "", "symbol": symbol, "refs": ref_rows,
                "refs_total": total, "relations": rels}

    def declared(self):
        return {}

    def matrix(self, focus, limit, declared=None):
        rows = self.ix.q("SELECT rf.module, df.module, COUNT(*) FROM refs r JOIN files rf ON rf.id=r.file "
                         "JOIN symbols s ON s.id=r.sym JOIN files df ON df.id=s.decl_file "
                         "WHERE rf.module != '' AND df.module != '' AND rf.module != df.module "
                         "AND (r.kind & ?) != 0 GROUP BY rf.module, df.module", (REF,))
        weight = {}
        for a, b, n in rows:
            weight[a] = weight.get(a, 0) + n
            weight[b] = weight.get(b, 0) + n
        if focus:
            f = next((x for x in weight if x.lower() == focus.lower()), None)
            chosen = [f] + sorted({b for a, b, _ in rows if a == f} | {a for a, b, _ in rows if b == f},
                                  key=lambda x: -weight[x]) if f else []
        else:
            chosen = sorted(weight, key=lambda x: -weight[x])
        chosen = list(dict.fromkeys(chosen))[:limit]
        idx = {n: i for i, n in enumerate(chosen)}
        declared = declared or {}
        cells = {}
        for a, b, n in rows:
            if a in idx and b in idx:
                cells[(idx[a], idx[b])] = [idx[a], idx[b], n, declared.get(a, {}).get(b, "")]
        for a, deps in declared.items():
            for b, kind in deps.items():
                if a in idx and b in idx and (idx[a], idx[b]) not in cells:
                    cells[(idx[a], idx[b])] = [idx[a], idx[b], 0, kind]
        roots = dict(self.ix.q("SELECT module, root FROM files WHERE module != '' GROUP BY module"))
        return {"modules": [{"name": n, "size": weight.get(n, 0), "group": roots.get(n, "")} for n in chosen],
                "cells": list(cells.values()), "measure": "refs", "has_declared": bool(declared)}

    def refs_with_text(self, sid, limit):
        lc = LineCache()
        rows = self.ix.refs(sid, None, limit)
        names = self.ix.names({r["container"] for r in rows})
        return [{"kind": "정의" if r["kind"] & DEF else "선언" if r["kind"] & DECL else "참조", "path": r["path"],
                 "line": r["line"], "col": r["col"], "text": lc.text(r["abs_path"], r["line"], 200),
                 "container": ((names.get(r["container"]) or {}).get("scope", "") +
                               (names.get(r["container"]) or {}).get("name", "(파일 범위)"))} for r in rows]

    def coverage(self):
        """디스크의 C++ 소스 중 clangd 가 본 파일 비율 (모듈별). 어떤 TU 도 포함하지 않은 헤더는 인덱스에 없다."""
        from index_view import ModuleResolver, disk_sources
        root_name = "engine" if self.scope == "engine" else "project"
        root = self.ix.roots.get(root_name)
        if not root:
            return {"modules": [], "note": "루트 정보 없음"}
        seen = {norm(p) for (p,) in self.ix.q("SELECT path FROM files WHERE root = ?", (root_name,))}
        res = ModuleResolver()
        per = {}
        for f in disk_sources(root, root_name):
            mod = res.of(f, root)
            d = per.setdefault(mod, [0, 0, []])
            d[0] += 1
            if norm(f) in seen:
                d[1] += 1
            elif len(d[2]) < 8:
                d[2].append(os.path.relpath(f, root).replace("\\", "/"))
        mods = sorted(per.items(), key=lambda x: -x[1][0])
        total = sum(v[0] for _, v in mods)
        hit = sum(v[1] for _, v in mods)
        return {"root": root, "total": total, "indexed": hit,
                "modules": [{"name": k, "disk": v[0], "indexed": v[1], "missing_sample": v[2]} for k, v in mods[:200]]}


def _fmt_bytes(n):
    if not n:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def view_sources(root, kind):
    out = [CindexSource("project", db_for("project", root, kind))]
    if kind == "ue":
        out.append(CindexSource("engine", db_for("engine", root, kind)))
    return out


# ---------------------------------------------------------------- 검증: 정규식 ↔ clangd, 질의 세트

def compare_pairs(sources):
    pairs = []
    # 프로젝트 clangd 인덱스에는 프로젝트가 포함한 엔진 헤더도 들어 있어 엔진 정규식 인덱스와도 대조한다
    for regex, scope, cl in (("engine", "engine", "clangd-engine"), ("engine", "engine", "clangd-project"),
                             ("project", "project", "clangd-project")):
        r, c = sources.get(regex), sources.get(cl)
        if r and c and r.available and c.available:
            pairs.append({"id": f"{regex}|{cl}", "label": f"{r.label} ↔ {c.label} ({scope} 경로 심볼)"})
    return pairs


def compare(sources, pair):
    """clangd(컴파일러 기준)를 정답으로 정규식 인덱스의 타입 재현율·좌표 일치·상속 일치·오탐을 잰다."""
    regex_name, cl_name = pair.split("|")
    rs, cs = sources[regex_name], sources[cl_name]
    root_name = "engine" if regex_name == "engine" else "project"
    ix = cs.ix
    truth = ix.q("SELECT s.id, s.name, df.rel, s.def_line FROM symbols s JOIN files df ON df.id=s.def_file "
                 "WHERE s.kind IN ('Class','Struct','Enum') AND s.tpl_args = '' AND s.name != '' AND df.root = ? "
                 "AND (df.rel LIKE '%.h' OR df.rel LIKE '%.hpp' OR df.rel LIKE '%.inl')", (root_name,))
    if not truth:
        return {"note": "대조할 clangd 심볼이 없다 (그 범위 경로에 정의된 클래스·구조체·열거형 0개).", "checks": []}
    miss, wrong_path, line_off, hit = [], [], [], 0
    for sid, name, rel, line in truth:
        cands = rs.by_name(name)
        if not cands:
            miss.append(f"{name} {rel}:{line}")
            continue
        same = [c for c in cands if c["path"].replace("\\", "/").lower() == rel.lower()]
        if not same:
            wrong_path.append(f"{name}: clangd {rel} · 정규식 {cands[0]['path']}")
            continue
        hit += 1
        if min(abs(c["line"] - line) for c in same) > 1:
            line_off.append(f"{name} {rel}: clangd {line} · 정규식 {same[0]['line']}")
    total = len(truth)
    checks = [
        {"name": "타입 재현율", "metric": f"{hit + len(wrong_path)}/{total} ({(hit + len(wrong_path)) / total:.1%})",
         "pass": (hit + len(wrong_path)) / total >= 0.95,
         "why": "clangd 가 헤더에서 정의를 본 클래스·구조체·열거형(템플릿 특수화 제외) 중 정규식 인덱스가 이름으로 찾는 비율. "
                "95% 미만이면 정규식이 놓치는 선언 형태가 있다 — 표본을 본다.", "samples": miss[:30]},
        {"name": "파일 일치", "metric": f"{hit}/{hit + len(wrong_path)}", "pass": not wrong_path,
         "why": "찾은 것 중 같은 파일을 가리키는 비율. 다르면 같은 이름 다른 타입(전방 선언·동명이인)을 집었다.",
         "samples": wrong_path[:30]},
        {"name": "줄 일치 (±1)", "metric": f"{hit - len(line_off)}/{hit}", "pass": not line_off,
         "why": "정규식은 선언 줄, clangd 는 이름 토큰 줄을 준다. 매크로 줄(UCLASS) 차이로 ±1 은 같게 본다.",
         "samples": line_off[:30]},
    ]
    # 상속: 정규식 parent ↔ clangd BaseOf
    sample = random.sample(truth, min(300, total))
    agree = disagree = 0
    dis = []
    for sid, name, rel, line in sample:
        cands = [c for c in rs.by_name(name) if c["path"].replace("\\", "/").lower() == rel.lower()]
        if not cands or not cands[0].get("parent"):
            continue
        bases = {b["name"] for b in ix.bases(sid)}
        if cands[0]["parent"] in bases:
            agree += 1
        else:
            disagree += 1
            dis.append(f"{name}: 정규식 {cands[0]['parent']} · clangd {', '.join(sorted(bases)) or '(없음)'}")
    if agree + disagree:
        checks.append({"name": "부모 클래스 일치 (표본)", "metric": f"{agree}/{agree + disagree}", "pass": disagree == 0,
                       "why": "정규식 인덱스의 첫 부모가 clangd 의 BaseOf 관계에 있는가.", "samples": dis[:30]})
    # 오탐: clangd 가 본 파일에서 정규식만 아는 타입 이름
    seen_files = {r[0].lower() for r in ix.q("SELECT rel FROM files WHERE root = ?", (root_name,))}
    names = {t[1] for t in truth}
    fp = []
    if hasattr(rs, "q"):
        rows = rs.q("SELECT s.name, f.path FROM symbols s JOIN files f ON f.id=s.file_id WHERE s.kind != 'delegate'")
    else:
        rows = [(s[0], s[2]) for s in getattr(rs, "syms", []) if s[1] != "delegate"]
    for name, path in rows:
        if path.replace("\\", "/").lower() in seen_files and name not in names:
            fp.append(f"{name} {path}")
    checks.append({"name": "정규식 오탐 후보", "metric": f"{len(fp)}개", "pass": None,
                   "why": "clangd 가 컴파일한 파일인데 clangd 정의 목록에 없는 정규식 타입. 전방 선언·매크로·템플릿 특수화일 수 있어 "
                          "판정 없이 표본만 보인다.", "samples": fp[:30]})
    return {"note": f"정답 = clangd 인덱스({cs.db}) · 대상 = {rs.label} · 범위 {root_name} 경로 · 타입 {total}개", "checks": checks}


def run_queryset(sources, root, n_auto=200):
    """질의 → 기대 위치. <루트>/.claude/index_eval.json 이 있으면 그것, 없으면 clangd 정의 위치로 자동 생성.
    지표: Acc@1, Acc@5, MRR (코드 위치 찾기 연구들의 지표 — references/indexing-research.md).
    소스는 자기가 다루는 범위(engine/project)의 질의로만 채점한다. 자동 생성 정답을 낸 clangd 소스는 채점에서 뺀다(자기 채점)."""
    spec_path = Path(root) / ".claude" / "index_eval.json"
    queries, note, oracle = [], "", None
    if spec_path.is_file():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        queries = [(q["q"], q["expect"], q.get("root")) for q in spec.get("queries", [])]
        note = f"질의 세트: {spec_path} ({len(queries)}개)"
    else:
        oracle = next((s for s in sources.values() if s.engine == "clangd" and s.available and s.scope == "project"), None) \
            or next((s for s in sources.values() if s.engine == "clangd" and s.available), None)
        if oracle is None:
            return {"note": f"{spec_path} 도 clangd 인덱스도 없어 질의 세트를 만들 수 없다.", "summary": [], "results": []}
        rows = oracle.ix.q("SELECT s.name, df.rel, df.root FROM symbols s JOIN files df ON df.id=s.def_file WHERE s.kind IN "
                           "('Class','Struct','Enum') AND s.tpl_args = '' AND s.name != '' AND df.root != '' "
                           "ORDER BY RANDOM() LIMIT ?", (n_auto,))
        queries = list(rows)
        note = (f"{spec_path} 가 없어 {oracle.label} 의 정의 위치로 질의 {len(queries)}개를 자동 생성했다 (이름 → 정의 파일). "
                f"정답을 낸 소스는 채점에서 뺐다. 요청→수정 파일 같은 실제 과제 세트는 이 파일에 적는다: "
                f'{{"queries": [{{"q": "…", "expect": "경로 조각", "root": "engine|project(생략 가능)"}}]}}')
    names = [s.name for s in sources.values() if s.available and hasattr(s, "search") and s is not oracle]
    results, stats = [], {n: [] for n in names}
    for q, expect, qroot in queries:
        ranks = {}
        for n in names:
            src = sources[n]
            if qroot and qroot not in getattr(src, "covers", {qroot}):
                ranks[n] = "-"
                continue
            try:
                hits = src.search(q, 10)
            except Exception:
                hits = []
            rank = next((i + 1 for i, h in enumerate(hits)
                         if expect.lower() in (h.get("path") or "").replace("\\", "/").lower()), None)
            ranks[n] = rank
            stats[n].append(rank)
        results.append({"query": q, "expect": expect, "ranks": ranks})
    summary = []
    for n, rs in stats.items():
        if not rs:
            continue
        acc1 = sum(1 for r in rs if r == 1) / len(rs)
        acc5 = sum(1 for r in rs if r and r <= 5) / len(rs)
        mrr = sum(1 / r for r in rs if r) / len(rs)
        summary.append({"name": f"{sources[n].label}", "metric": f"질의 {len(rs)} · Acc@1 {acc1:.1%} · Acc@5 {acc5:.1%} · MRR {mrr:.3f}",
                        "pass": None, "why": "검색 상위 10개 안에서 기대 경로가 처음 나온 순위로 계산. 소스가 다루지 않는 범위의 질의는 뺐다. "
                                             "판정 기준은 references/indexing-research.md."})
    return {"note": note, "summary": summary, "results": results[:300], "sources": names}


def cmd_eval(root, kind):
    sys.path.insert(0, str(HERE))
    from index_view import App
    app = App(str(root))
    pairs = compare_pairs(app.sources)
    if not pairs:
        print("대조할 정규식 인덱스와 clangd 인덱스 쌍이 없다.")
    for p in pairs:
        r = compare(app.sources, p["id"])
        print(f"## {p['label']}\n{r['note']}")
        for c in r["checks"]:
            mark = "–" if c["pass"] is None else ("통과" if c["pass"] else "실패")
            print(f"- {c['name']}: {mark} · {c['metric']}")
    qs = run_queryset(app.sources, root)
    print(f"\n## 질의 세트\n{qs['note']}")
    for c in qs["summary"]:
        print(f"- {c['name']}: {c['metric']}")
    return 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="clangd 기반 의미 인덱스")
    ap.add_argument("command", choices=["cdb", "build", "ingest", "status", "sym", "refs", "callers", "callees",
                                        "bases", "derived", "overrides", "members", "impact", "file", "eval"])
    ap.add_argument("arg", nargs="*", default=[])
    ap.add_argument("--root", default=".")
    ap.add_argument("--db", default=None, help="engine | project | sqlite 경로")
    ap.add_argument("--scope", default="project", choices=["project", "engine", "all"])
    ap.add_argument("--cdb", default=None, help="compile_commands.json 파일 또는 폴더")
    ap.add_argument("--filter", default=None, help="clangd-indexer --filter (번역 단위 경로 정규식)")
    ap.add_argument("--jobs", type=int, default=0)
    ap.add_argument("--indexer", default=None)
    ap.add_argument("--extra-arg", action="append", help="clangd-indexer --extra-arg (예: VS Code 생성기 cdb 에 /std:c++20)")
    ap.add_argument("--yaml", default=None, help="build: 이미 만든 clangd-indexer 출력(YAML·RIFF)을 적재만")
    ap.add_argument("--keep-yaml", action="store_true", help="build: clangd-indexer 출력 파일을 지우지 않는다")
    ap.add_argument("--mode", default="indexer", choices=["indexer", "bg"],
                    help="build: indexer = clangd-indexer 전체 색인, bg = clangd 배경 색인 샤드로 증분 (바뀐 것만)")
    ap.add_argument("--format", default="binary", choices=["binary", "yaml"],
                    help="build --mode indexer: 출력 형식. binary(RIFF)가 17배쯤 작고 적재가 빠르다")
    ap.add_argument("--unity", type=int, default=0, help="build: 같은 플래그의 .cpp 를 N 개씩 한 TU 로 묶는다 (0 = 끔)")
    ap.add_argument("--clangd", default=None, help="build --mode bg: clangd 경로 (기본 CLANGD > PATH > ~/.claude/tools)")
    ap.add_argument("--timeout", type=int, default=0, help="build --mode bg: 초 (0 = 없음)")
    ap.add_argument("--kind", default=None, choices=["decl", "def", "ref"])
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--target", default=None)
    ap.add_argument("--platform", default="Win64")
    ap.add_argument("--config", default="Development")
    ap.add_argument("--ubt", default=None)
    ap.add_argument("--out", default=None, help="cdb: -OutputDir")
    a = ap.parse_args()
    root, kind = project_of(a.root)
    if a.command == "cdb":
        return cmd_cdb(root, kind, a)
    if a.command == "build":
        return cmd_build(root, kind, a)
    if a.command == "ingest":
        if not a.arg:
            raise SystemExit("ingest <YAML>")
        a.yaml = a.arg[0]
        return cmd_build(root, kind, a)
    if a.command == "eval":
        return cmd_eval(root, kind)
    return cmd_query(a, root, kind)


if __name__ == "__main__":
    sys.exit(main())
