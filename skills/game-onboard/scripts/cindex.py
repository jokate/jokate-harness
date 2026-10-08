#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clangd 기반 의미 인덱스. 컴파일러가 본 그대로의 심볼·참조·관계를 sqlite 에 담는다. 표준 라이브러리만 쓴다.

정규식 인덱스(gq.py, ue_q.py)는 선언 줄만 본다. 이 인덱스는 clangd-indexer 가 실제로 컴파일하며 모은 것이라
  - 함수·메서드·필드·매크로까지 심볼이 있고 (선언 + 정의 위치)
  - 참조가 있다 (어디서 쓰나, 어느 함수 안에서 쓰나 → 호출자/피호출 함수)
  - 관계가 있다 (상속 BaseOf, 오버라이드 OverriddenBy)
대신 compile_commands.json 이 필요하고, 컴파일이 되는 상태여야 정확하다 (UE 는 UHT 가 만든 .generated.h 가 있어야 한다).

  python cindex.py cdb [--target <이름>Editor] [--platform Win64] [--config Development] [--compiler Default]   # UE: compile_commands.json 생성
      Win64 는 기본으로 -Compiler=Default 를 넘긴다 — 안 넘기면 UBT 가 Clang 을 강제해 VS 의 Clang 구성 요소 없이는 실패한다
      UBT 가 실패하면 코드 생성(UHT)을 건너뛰고(-NoExecCodeGenActions) 한 번 더 한다 (--codegen auto|on|off)
  python cindex.py build [--cdb <파일|폴더>] [--scope project|engine|all] [--filter 정규식] [--jobs N]
                         [--mode indexer|bg] [--format binary|yaml] [--unity N]
      --mode indexer (기본) clangd-indexer 전체 색인. 출력은 RIFF(binary) 가 기본 — YAML 보다 17배쯤 작고 적재 2배+ 빠름
      --mode bg      clangd 배경 색인 샤드로 증분: 두 번째부터 바뀐 파일·그 헤더를 포함한 TU·플래그가 바뀐 TU 만 다시 색인
      --unity N      같은 플래그·같은 모듈의 .cpp 를 N 개씩 한 TU 로 묶어 공용 헤더 파싱을 줄인다 (실패한 묶음은 원래대로 다시)
  python cindex.py ingest <clangd-indexer 출력(YAML|RIFF)> [--scope ...]   # 이미 만든 출력을 적재만
  python cindex.py optimize [--force]        # 옛 모양 인덱스를 조회용(스키마 2)으로 다시 쓰고 소유권 표시를 맞춘다 (색인은 그대로)
  python cindex.py status
  python cindex.py sym <이름|A::B>          # 심볼 좌표 (선언·정의·시그니처)
  python cindex.py refs <이름> [--kind decl|def|ref] [--module M] [--path 조각] [--cursor C]   # 총계·모듈 묶음·표본·다음 커서
  python cindex.py callers <이름>           # 이 심볼을 참조하는 함수 (참조의 Container 기준)
  python cindex.py callees <이름>           # 이 함수 안에서 참조하는 함수·메서드
  python cindex.py bases <이름> · derived <이름> · overrides <이름>   # 전 단계 트리 (--depth N 으로 제한)
  python cindex.py members <클래스>         # 멤버와 선언 줄 원문 (clangd 는 멤버 시그니처를 기록하지 않는다)
  python cindex.py impact <이름>            # 바꾸면 같이 볼 곳: 파생 타입·재정의(전 단계)·참조하는 함수·파일·모듈 (타입이면 멤버 사용 포함)
  python cindex.py file <경로 조각>          # 파일에 선언된 심볼
  python cindex.py eval                      # 정규식 인덱스와 대조 + 질의 세트 (index_view.py 검증 탭과 같은 계산)

인덱스 위치: --scope project → UE Saved/ClaudeIndex/clangd.sqlite (그 외 .claude/index/clangd.sqlite)
            --scope engine  → ~/.claude/cache/ue_index/<엔진경로>/clangd.sqlite (ue.sqlite 옆)
조회는 기본으로 있는 인덱스를 모두 같이 본다 (프로젝트 + 엔진, 심볼 ID 로 합침). --db engine|project|<경로> 면 그 하나만.
참조는 파일마다 주인이 하나다 — 엔진 인덱스가 참조를 가진 파일은 엔진 쪽만 센다 (clangd MergedIndex 규칙, 프로젝트 몫을 먼저 보인다).
이름이 정확히 맞지 않으면 추측하지 않고 비슷한 이름 후보를 보여 준다. bases·derived·overrides 는 끝까지 따라간다 (--depth N).
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


def fits(lines, budget=CAP):
    """앞에서부터 budget 바이트 안에 드는 줄 수."""
    size = 0
    for i, ln in enumerate(lines):
        size += len(ln.encode("utf-8")) + 1
        if size > budget:
            return i
    return len(lines)


def emit(lines, full=False, tail=None):
    """출력은 기본 4KB 에서 끊는다. tail(잘림 안내·다음 커서)은 끊겨도 남긴다."""
    n = len(lines) if full else fits(lines)
    out = lines[:n] + ([f"… (+{len(lines) - n} more · --full 또는 질의를 좁혀라)"] if n < len(lines) else [])
    print("\n".join(out + list(tail or [])))


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
# 스키마 2 (2026-10-08, reports/엔진 규모 clangd 인덱스 조회 속도.md P0~P1):
#  - files.id 는 (rel, root, path) 순서 → ORDER BY r.file 이 경로 순이고 refs(sym, file, line, col) 인덱스가 그 순서를 그대로 준다
#  - refs 표는 (sym, file, line, col) 순서로 다시 쓴다 → 한 심볼의 행이 연속이라 표 접근이 순차다
#  - refs(sym) 인덱스는 refs(sym, file, line, col) 의 접두로 대신한다. sym 으로 시작하는 인덱스를 둘 두지 않는다 —
#    refs(sym, container, kind) 를 더했더니 플래너가 그쪽을 골라 정렬 질의가 3.9s → 11.6s 로 느려졌다 (합성 측정)
#  - 심볼별 개수·호출자·모듈은 적재 끝에 요약 표로 계산해 둔다 (Kythe PageIndex.count/Caller, Glean 파생 술어와 같은 생각)
INDEXES = """
CREATE INDEX symbols_name ON symbols(name COLLATE NOCASE);
CREATE INDEX symbols_qname ON symbols(qname COLLATE NOCASE);
CREATE INDEX symbols_decl ON symbols(decl_file);
CREATE INDEX symbols_scope ON symbols(scope);
CREATE INDEX refs_sym_file ON refs(sym, file, line, col);
CREATE INDEX refs_container ON refs(container);
CREATE INDEX rel_subject ON relations(subject, predicate);
CREATE INDEX rel_object ON relations(object, predicate);
"""
STATS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ref_files(file INTEGER PRIMARY KEY, n INTEGER);
CREATE TABLE IF NOT EXISTS owned_out(file INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS sym_stats(sym TEXT PRIMARY KEY, n_refs INTEGER, n_use INTEGER, n_files INTEGER,
  n_callers INTEGER, n_modules INTEGER) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS sym_callers(sym TEXT, container TEXT, n INTEGER, file INTEGER, line INTEGER);
CREATE TABLE IF NOT EXISTS sym_modules(sym TEXT, module TEXT, n INTEGER);
"""
SCHEMA_VERSION = 2
TOP_CALLERS = 500   # 심볼마다 남기는 호출자 행 (나머지는 sym_stats 의 총계로만). clangd 원격 서버의 요청 상한이 1만이다
TOP_MODULES = 40


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


def ingest(source, db_path, roots, info=None, keep_doc=300, dedupe_refs=False, engine_db=None):
    """source: YAML 파일 · RIFF 파일 · RIFF 파일 목록(배경 색인 샤드, 또는 유니티 + 재색인 출력 → dedupe_refs).
    원본 표를 임시 파일(.stage)에 다 쓰고, finalize 로 조회용 모양(스키마 2)으로 다시 써서 바꿔치기한다.
    engine_db: 프로젝트 인덱스를 만들 때 엔진 인덱스가 있으면 준다 — 엔진이 주인인 파일을 표시한다 (apply_owner)."""
    t0 = time.time()
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    stage, tmp = db_path.with_suffix(".stage"), db_path.with_suffix(".building")
    for f in (stage, tmp):
        if f.exists():
            f.unlink()
    con = sqlite3.connect(str(stage))
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
    try:
        finalize(stage, tmp, engine_db)
    finally:
        stage.unlink(missing_ok=True)
    swap_in(tmp, db_path)
    return counts


# ---------------------------------------------------------------- 조회용 모양 (스키마 2)

def db_identity(meta):
    """인덱스 한 벌의 식별값. 프로젝트 인덱스의 소유권 표시가 어느 엔진 인덱스를 보고 만든 것인지 대조한다."""
    return meta.get("build_id") or ("gen:" + (meta.get("generated_at") or ""))


def _table_names(con):
    return {n for (n,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _window_ok():
    return sqlite3.sqlite_version_info >= (3, 25, 0)


def finalize(src, dst, engine_db=None, log=None):
    """원본 표(src: 적재 직후 또는 옛 스키마 인덱스)를 조회용 DB(dst)로 새로 쓴다. 표를 새 파일에 순서대로 다시 쓰므로 빈 페이지도 없다.
      1. 파일 id 를 (rel, root, path) 순서로 다시 매긴다
      2. refs 를 (sym, file, line, col) 순서로 다시 쓴다
      3. 인덱스 · (프로젝트면) 엔진이 주인인 파일 표시 · 요약 표 · ANALYZE"""
    t0 = time.time()
    dst = Path(dst)
    if dst.exists():
        dst.unlink()
    con = sqlite3.connect(str(dst))
    try:
        con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA cache_size=-262144; PRAGMA threads=4;"
                          + SCHEMA + STATS_SCHEMA)
        con.execute("ATTACH DATABASE ? AS src", (str(src),))
        old = [r[0] for r in con.execute("SELECT id FROM src.files ORDER BY rel, root, path")]
        con.execute("CREATE TEMP TABLE fmap(old INTEGER PRIMARY KEY, new INTEGER)")
        con.executemany("INSERT INTO fmap VALUES(?,?)", ((o, i) for i, o in enumerate(old, 1)))
        con.execute("INSERT INTO files SELECT m.new, f.path, f.module, f.root, f.rel, f.mtime "
                    "FROM src.files f JOIN fmap m ON m.old = f.id ORDER BY m.new")
        con.execute("INSERT INTO symbols SELECT x.id, x.name, x.scope, x.qname, x.kind, x.lang, d.new, x.decl_line, x.decl_col, "
                    "f.new, x.def_line, x.def_col, x.signature, x.return_type, x.type, x.tpl_args, x.flags, x.nrefs, x.doc "
                    "FROM src.symbols x LEFT JOIN fmap d ON d.old = x.decl_file LEFT JOIN fmap f ON f.old = x.def_file")
        con.execute("INSERT INTO refs SELECT r.sym, r.kind, m.new, r.line, r.col, r.container "
                    "FROM src.refs r JOIN fmap m ON m.old = r.file ORDER BY r.sym, m.new, r.line, r.col")
        con.execute("INSERT INTO relations SELECT subject, predicate, object FROM src.relations")
        con.execute("INSERT INTO meta SELECT key, value FROM src.meta")
        con.commit()
        con.execute("DETACH DATABASE src")
        t_copy = time.time() - t0
        con.executescript(INDEXES)
        owner = apply_owner(con, engine_db) if engine_db and Path(engine_db).exists() else None
        build_stats(con, excl=owner is not None)
        meta = {"schema": str(SCHEMA_VERSION), "file_order": "path", "build_id": f"{random.getrandbits(48):012x}",
                "owner_build": owner[1] if owner else "", "owned_files": str(owner[0]) if owner else "0",
                "stats_scope": "own" if owner else "all", "elapsed_finalize": f"{time.time() - t0:.2f}"}
        con.executemany("INSERT OR REPLACE INTO meta VALUES(?,?)", list(meta.items()))
        con.commit()
        con.execute("ANALYZE")
        con.commit()
    finally:
        con.close()
    (log or (lambda m: None))(f"조회용으로 다시 씀 [{time.time() - t0:.1f}s · 표 복사 {t_copy:.1f}s]"
                              + (f" · 엔진이 주인인 파일 {owner[0]}개" if owner else ""))


def engine_ref_paths(con):
    """엔진 인덱스가 참조를 가진 파일의 정규화 경로. 옛 인덱스(ref_files 없음)는 files 전체 — 심볼이 선언된 파일에는 선언 참조도 있다."""
    q = ("SELECT f.path FROM files f JOIN ref_files rf ON rf.file = f.id" if "ref_files" in _table_names(con)
         else "SELECT path FROM files")
    return {norm(p) for (p,) in con.execute(q)}


def apply_owner(con, engine_db):
    """clangd MergedIndex 규칙: 파일마다 참조의 주인은 인덱스 하나다. 엔진 인덱스가 참조를 가진 파일은 엔진이 주인이고,
    프로젝트 인덱스의 그 파일 참조는 병합 조회에서 뺀다 (owned_out). 경로 접두("엔진 폴더 아래")가 아니라 엔진 인덱스가 실제로
    색인한 파일로 정한다 — 엔진 TU 가 아무도 열지 않은 엔진 헤더(프로젝트 TU 만 연 것)의 참조는 프로젝트 쪽에 남는다.
    반환 (표시한 파일 수, 엔진 인덱스 식별값)."""
    e = sqlite3.connect(f"file:{Path(engine_db).as_posix()}?mode=ro", uri=True)
    try:
        owned = engine_ref_paths(e)
        ident = db_identity(dict(e.execute("SELECT key, value FROM meta").fetchall()))
    finally:
        e.close()
    ids = [(i,) for i, p in con.execute("SELECT id, path FROM files") if norm(p) in owned]
    con.execute("DELETE FROM owned_out")
    con.executemany("INSERT INTO owned_out VALUES(?)", ids)
    return len(ids), ident


def build_stats(con, excl=False):
    """심볼별 요약 표. excl 이면 owned_out 파일의 참조를 뺀다 (프로젝트 인덱스를 엔진 인덱스와 합쳐 볼 때의 몫).
    - ref_files: 파일별 참조 수 (다른 인덱스가 이 인덱스를 주인으로 볼 때 쓴다 — 항상 전체)
    - sym_stats: 참조 수 · 사용(Reference 비트) 수 · 사용이 있는 파일 수 · 호출자(Container) 수 · 모듈 수
    - sym_callers: 심볼마다 사용 수 상위 TOP_CALLERS 개 호출자와 첫 위치 · sym_modules: 상위 TOP_MODULES 개 모듈"""
    w = " AND r.file NOT IN (SELECT file FROM owned_out)" if excl else ""
    for t in ("ref_files", "sym_stats", "sym_callers", "sym_modules"):
        con.execute(f"DELETE FROM {t}")
    for t in ("sc", "sm", "sf"):
        con.execute(f"DROP TABLE IF EXISTS temp.{t}")
    con.execute("DROP INDEX IF EXISTS sym_callers_sym")
    con.execute("DROP INDEX IF EXISTS sym_modules_sym")
    con.execute("INSERT INTO ref_files SELECT file, COUNT(*) FROM refs GROUP BY file")
    con.execute(f"CREATE TEMP TABLE sc AS SELECT r.sym AS sym, r.container AS container, COUNT(*) AS n, MIN(r.rowid) AS rid "
                f"FROM refs r WHERE (r.kind & {REF}) != 0{w} GROUP BY r.sym, r.container")
    con.execute(f"CREATE TEMP TABLE sm AS SELECT r.sym AS sym, f.module AS module, COUNT(*) AS n FROM refs r "
                f"JOIN files f ON f.id = r.file WHERE (r.kind & {REF}) != 0{w} GROUP BY r.sym, f.module")
    con.execute(f"CREATE TEMP TABLE sf AS SELECT sym, COUNT(*) AS c FROM (SELECT r.sym AS sym FROM refs r "
                f"WHERE (r.kind & {REF}) != 0{w} GROUP BY r.sym, r.file) GROUP BY sym")
    if _window_ok():
        con.execute("INSERT INTO sym_callers SELECT x.sym, x.container, x.n, r.file, r.line FROM "
                    "(SELECT sym, container, n, rid, ROW_NUMBER() OVER (PARTITION BY sym ORDER BY n DESC, rid) AS k FROM temp.sc) x "
                    f"JOIN refs r ON r.rowid = x.rid WHERE x.k <= {TOP_CALLERS}")
        con.execute("INSERT INTO sym_modules SELECT sym, module, n FROM (SELECT sym, module, n, "
                    f"ROW_NUMBER() OVER (PARTITION BY sym ORDER BY n DESC, module) AS k FROM temp.sm) WHERE k <= {TOP_MODULES}")
    else:  # 윈도 함수가 없는 SQLite(3.25 미만): 자르지 않는다
        con.execute("INSERT INTO sym_callers SELECT x.sym, x.container, x.n, r.file, r.line FROM temp.sc x JOIN refs r ON r.rowid = x.rid")
        con.execute("INSERT INTO sym_modules SELECT sym, module, n FROM temp.sm")
    con.execute("CREATE INDEX sym_callers_sym ON sym_callers(sym, n DESC)")
    con.execute("CREATE INDEX sym_modules_sym ON sym_modules(sym, n DESC)")
    con.execute(f"INSERT INTO sym_stats SELECT a.sym, a.n_refs, a.n_use, IFNULL(f.c, 0), IFNULL(c.c, 0), IFNULL(m.c, 0) FROM "
                f"(SELECT r.sym AS sym, COUNT(*) AS n_refs, SUM((r.kind & {REF}) != 0) AS n_use FROM refs r WHERE 1{w} GROUP BY r.sym) a "
                "LEFT JOIN temp.sf f ON f.sym = a.sym "
                "LEFT JOIN (SELECT sym, COUNT(*) AS c FROM temp.sc GROUP BY sym) c ON c.sym = a.sym "
                "LEFT JOIN (SELECT sym, COUNT(*) AS c FROM temp.sm GROUP BY sym) m ON m.sym = a.sym")
    for t in ("sc", "sm", "sf"):
        con.execute(f"DROP TABLE temp.{t}")
    con.commit()


def refresh_owner(project_db, engine_db, log=print):
    """엔진 인덱스를 다시 만든 뒤 프로젝트 인덱스의 소유권 표시와 요약 표만 다시 계산한다 (프로젝트 색인은 다시 하지 않는다)."""
    con = sqlite3.connect(str(project_db), timeout=60)
    try:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        if int(meta.get("schema") or 1) < SCHEMA_VERSION:
            con.close()
            con = None
            return upgrade_db(project_db, engine_db, log)
        t0 = time.time()
        if engine_db and Path(engine_db).exists():
            n, ident = apply_owner(con, engine_db)
        else:
            con.execute("DELETE FROM owned_out")
            n, ident = 0, ""
        build_stats(con, excl=bool(ident))
        con.executemany("INSERT OR REPLACE INTO meta VALUES(?,?)",
                        [("owner_build", ident), ("owned_files", str(n)), ("stats_scope", "own" if ident else "all")])
        con.commit()
        con.execute("ANALYZE")
        con.commit()
        log(f"  프로젝트 인덱스 소유권 다시 계산: 엔진이 주인인 파일 {n}개 [{time.time() - t0:.1f}s] → {project_db}")
        return True
    finally:
        if con is not None:
            con.close()


def upgrade_db(db_path, engine_db=None, log=print):
    """옛 스키마 인덱스를 조회용 모양으로 바꾼다 (색인은 다시 하지 않는다). 새 파일에 쓰고 바꿔치기한다."""
    db_path = Path(db_path)
    tmp = db_path.with_suffix(".building")
    log(f"  {db_path.name} 를 스키마 {SCHEMA_VERSION} 로 다시 쓴다 (색인은 그대로): {db_path}")
    finalize(db_path, tmp, engine_db, log=lambda m: log("  " + m))
    swap_in(tmp, db_path)
    return True


def db_state(db_path):
    """(스키마, meta) — 없거나 못 열면 (0, {})."""
    try:
        con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        try:
            meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        finally:
            con.close()
    except sqlite3.Error:
        return 0, {}
    return int(meta.get("schema") or 1), meta


def optimize(root, kind, force=False, log=print):
    """있는 인덱스를 조회용 모양으로 맞춘다: 옛 스키마면 다시 쓰고, 프로젝트 인덱스의 소유권 표시가 지금 엔진 인덱스와 다르면 다시 계산.
    반환: 한 일 목록 (아무것도 안 했으면 빈 목록)."""
    pdb, edb = db_for("project", root, kind), db_for("engine", root, kind)
    done = []
    if edb and edb.exists():
        sv, _ = db_state(edb)
        if force or sv < SCHEMA_VERSION:
            upgrade_db(edb, None, log)
            done.append("엔진 인덱스 다시 씀")
    if pdb and pdb.exists():
        sv, meta = db_state(pdb)
        eng = edb if edb and edb.exists() else None
        want = db_identity(db_state(eng)[1]) if eng else ""
        if force or sv < SCHEMA_VERSION:
            upgrade_db(pdb, eng, log)
            done.append("프로젝트 인덱스 다시 씀")
        elif meta.get("owner_build", "") != want:
            refresh_owner(pdb, eng, log)
            done.append("프로젝트 인덱스 소유권 다시 계산")
    return done


def swap_in(tmp, db_path):
    """새로 만든 인덱스를 제자리에 넣는다. 보통은 파일 바꿔치기(os.replace).
    Windows 에서는 다른 프로세스(떠 있는 웹뷰, 조회 중인 세션)가 그 DB 를 열고 있으면 바꿔치기가 거부된다 —
    SQLite 가 파일을 FILE_SHARE_DELETE 없이 연다. 그때는 SQLite backup API 로 내용을 기존 파일에 통째로 써 넣는다
    (SQLite 잠금을 지키므로 읽는 쪽이 열려 있어도 된다. 바꿔치기보다 느리다 — DB 크기만큼 복사)."""
    try:
        os.replace(tmp, db_path)
        return
    except OSError:
        if not Path(db_path).exists():
            raise
    print(f"  {Path(db_path).name} 를 다른 프로세스가 열고 있어 바꿔치기 대신 내용을 덮어쓴다", flush=True)
    src = sqlite3.connect(str(tmp))
    dst = sqlite3.connect(str(db_path), timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    Path(tmp).unlink()


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
    if a.platform.lower() == "win64" and a.compiler:
        # GenerateClangDatabase 는 -Compiler= 가 없으면 -Compiler=Clang 을 붙여 Visual Studio 의 Clang(LLVM) 구성 요소를 요구한다
        # (UE 5.5·5.6 UBT 소스, Modes/GenerateClangDatabase.cs). Default = 평소 빌드와 같은 컴파일러(보통 MSVC) → 그 구성 요소 없이 돈다.
        # MSVC 면 항목이 cl.exe @rsp 가 되고 clangd 는 실행 파일 이름으로 cl 모드를 고른다.
        cmd.append(f"-Compiler={a.compiler}")

    def run_ubt(c):
        print("실행:", " ".join(f'"{x}"' if " " in x else x for x in c), flush=True)
        t0 = time.time()
        rc = subprocess.run(c, cwd=str(eng.parent if eng else root)).returncode
        print(f"종료 {rc} [{time.time() - t0:.0f}s]", flush=True)
        return rc
    # 5.4+ 는 compile_commands 를 쓰기 전에 코드 생성(UHT — UCLASS·GENERATED_BODY 처리)을 먼저 돌고, UHT 오류면 통째로 실패한다.
    # 생성 코드 폴더(Intermediate/Build/<플랫폼>/<앱>/Inc/<모듈>)는 이 모드와 평소 빌드가 같이 쓴다 (UEBuildTarget.cs 주석:
    # "shared between all intermediate environment variants") → UHT 를 건너뛰어도 마지막 에디터 빌드의 .generated.h 를 쓴다.
    codegen = "-NoExecCodeGenActions"
    rc = run_ubt(cmd + ([codegen] if a.codegen == "off" else []))
    if rc != 0 and a.codegen == "auto":
        print(f"\nUBT 가 실패했다. 코드 생성(UHT — GENERATED_BODY·UCLASS 처리)에서 막혔을 수 있어 UHT 를 건너뛰고({codegen}) 다시 한다.\n"
              "  .generated.h 는 마지막 에디터 빌드 것을 쓴다 — 에디터 빌드를 한 번도 안 했으면 UCLASS 타입이 인덱스에서 빠진다.", flush=True)
        rc = run_ubt(cmd + [codegen])
    found = [p for p in (Path(out), eng.parent if eng else None, eng, root) if p and (p / "compile_commands.json").is_file()]
    if found and rc == 0:
        print("compile_commands.json:", found[0] / "compile_commands.json")
    harness_emit("index.clangd.cdb", f"{target} {a.platform} {a.config} → 종료 {rc}", ok=rc == 0, project=root)
    return rc


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
    print(f"clangd-indexer 종료 {r.returncode} [{took:.0f}s] · TU {errors['tus']} · 오류 있던 TU {errors['failed_tu']} · "
          f"오류 줄 {errors['count']}" + (f" · .generated.h 관련 {errors['generated_h']}" if errors["generated_h"] else "")
          + f" (전체: {err_path})")
    return out, took, errors, r.returncode


def build_indexer(root, eng, scope, a, out_dir, roots):
    """clangd-indexer 전체 색인. --unity N 이면 같은 플래그의 .cpp 를 N 개씩 묶고, 실패한 묶음은 원래 TU 로 다시 돈다."""
    import cindex_speed as sp
    indexer = find_indexer(a.indexer)
    if not indexer:
        print("clangd-indexer 를 못 찾았다. setup.bat(또는 clangd_tools.py install)이 ~/.claude/tools/clangd 에 설치한다. "
              "직접 둔 것이면 PATH · --indexer · CLANGD_INDEXER (references/cindex.md). clangd 만 있으면 --mode bg 를 쓴다.")
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
        print("clangd 를 못 찾았다. setup.bat(또는 clangd_tools.py install)이 ~/.claude/tools/clangd 에 설치한다. "
              "직접 둔 것이면 PATH · --clangd · CLANGD.")
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
    edb = db_for("engine", root, kind) if scope == "project" else None
    counts = ingest(src, db, roots, info, dedupe_refs=a.mode != "bg" and isinstance(src, list),
                    engine_db=edb if edb and edb.exists() and edb != db else None)
    print(f"적재 완료 · 심볼 {counts['symbols']} · 참조 {counts['refs']} · 관계 {counts['relations']} · 파일 {counts['files']} → {db}")
    pdb = db_for("project", root, kind) if scope == "engine" else None
    if pdb and pdb.exists() and pdb != db:
        refresh_owner(pdb, db)
    if not a.keep_yaml and not a.yaml and a.mode != "bg":
        for s in (src if isinstance(src, list) else [src]):
            Path(s).unlink(missing_ok=True)
    failed = errors.get("failed_tu", 0)
    detail = f"{scope} · {info.get('mode', '')} · 심볼 {counts['symbols']} · 참조 {counts['refs']} · 관계 {counts['relations']}"
    if info.get("rebuilt") is not None:
        detail += f" · 재색인 {info['rebuilt']}/{info.get('batches') or info.get('tus')}"
    harness_emit("index.clangd", detail + (f" · 오류 있던 TU {failed}" if failed else ""), ok=not failed, project=root)
    return 0


GENERATED_RE = re.compile(r"\.generated\.h|_PROLOG\b|GENERATED_BODY|GENERATED_UCLASS_BODY")
PROGRESS_RE = re.compile(r"^\[(\d+)/(\d+)\] Processing file")


def summarize_errors(err_path, keep=30):
    """clangd-indexer 는 번역 단위(TU)가 실패해도 종료 코드 0 이다 → stderr 로 판정한다.
    'Error while processing <파일>' = 오류가 있던 TU (심볼은 대부분 남는다). UE 에서 가장 흔한 원인은 .generated.h 누락·낡음(UHT 미실행)이고,
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

def like_escape(s):
    """LIKE 패턴용 — C++ 이름의 '_' 가 한 글자 와일드카드로 읽히지 않게 (ESCAPE '\\' 와 같이 쓴다)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Index:
    """인덱스 파일 하나 (프로젝트 또는 엔진). 조회는 MultiIndex 를 거친다 — 파일 하나여도 MultiIndex([Index]) 로 연다.
    여기 메서드는 그 인덱스 몫만 답한다. excl 은 병합 조회에서 다른 인덱스가 주인인 파일 목록 표 (owned_out 또는 temp 표)."""

    def __init__(self, db_path, role=None):
        self.path = Path(db_path)
        # autocommit: temp 표에 써도 트랜잭션이 열린 채 남지 않게 — 남으면 공유 잠금을 쥐고 있어 다른 프로세스가 인덱스를 못 고친다
        self.con = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, check_same_thread=False,
                                   isolation_level=None)
        self.lock = threading.Lock()
        self.meta = dict(self.q("SELECT key, value FROM meta"))
        self.roots = {n: p for n, p in json.loads(self.meta.get("roots", "[]"))}
        self.schema = int(self.meta.get("schema") or 1)
        self.path_order = self.meta.get("file_order") == "path"
        scope = self.meta.get("scope")
        self.role = role or (scope if scope in ("project", "engine") else
                             ("engine" if "ue_index" in str(self.path) else "project"))
        self.tables = {n for (n,) in self.q("SELECT name FROM sqlite_master WHERE type='table'")}
        self.has_stats = {"sym_stats", "sym_callers", "sym_modules"} <= self.tables

    def q(self, sql, args=()):
        with self.lock:
            return self.con.execute(sql, args).fetchall()

    def write_temp(self, sql, rows=None):
        with self.lock:
            if rows is None:
                self.con.execute(sql)
            else:
                self.con.executemany(sql, rows)

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

    # ---- 심볼 (작은 결과 — 인덱스끼리는 ID 로 합친다)

    def find_exact(self, name, kinds=None):
        name = name.strip()
        rows = self.q(self.SYM + "WHERE s.qname = ? OR (s.name = ? AND ? NOT LIKE '%::%')", (name, name, name))
        out = [self.row(r) for r in rows]
        return [s for s in out if s["kind"] in kinds] if kinds else out

    def find_fuzzy(self, name, limit=200, kinds=None):
        """접두 일치(이름·한정 이름 인덱스 범위 읽기)부터. 그것으로 다 차지 않을 때만 부분 일치로 표 전체를 훑는다."""
        name = name.strip()
        pat, cap = like_escape(name), limit * 4
        rows = self.q(self.SYM + "WHERE s.name LIKE ? ESCAPE '\\' OR s.qname LIKE ? ESCAPE '\\' LIMIT ?",
                      (pat + "%", pat + "%", cap))
        if len(rows) < cap:
            seen = {r[0] for r in rows}
            more = self.q(self.SYM + "WHERE s.name LIKE ? ESCAPE '\\' OR s.qname LIKE ? ESCAPE '\\' LIMIT ?",
                          (f"%{pat}%", f"%{pat}%", cap))
            rows += [r for r in more if r[0] not in seen][:cap - len(rows)]
        out = [self.row(r) for r in rows]
        return [s for s in out if s["kind"] in kinds] if kinds else out

    # 파일을 먼저 거른다. LEFT JOIN 쪽 조건(df.rel LIKE)은 조인 순서를 바꾸지 못해 심볼 표 전체를 훑었다 (928 ms, 합성 측정).
    # CROSS JOIN 은 SQLite 에서 왼쪽 표를 바깥 반복으로 고정한다 (optoverview "Manual Control Of Query Plans Using CROSS JOIN")
    FILE_SYM = ("SELECT s.id, s.name, s.scope, s.kind, df.rel, df.root, s.decl_line, s.decl_col, ff.rel, ff.root, s.def_line, "
                "s.signature, s.return_type, s.type, s.flags, s.nrefs, df.module, df.path, ff.path, s.tpl_args, s.doc "
                "FROM files df CROSS JOIN symbols s ON s.decl_file=df.id LEFT JOIN files ff ON ff.id=s.def_file "
                "WHERE df.rel LIKE ? ESCAPE '\\' ORDER BY df.rel, s.decl_line LIMIT ?")

    def file_syms(self, pattern, limit):
        return [self.row(r) for r in self.q(self.FILE_SYM, (f"%{like_escape(pattern)}%", limit))]

    def by_id(self, sid):
        r = self.q(self.SYM + "WHERE s.id = ?", (sid,))
        return self.row(r[0]) if r else None

    def by_ids(self, ids):
        ids = [i for i in dict.fromkeys(ids) if i and i != NULL_ID]
        out = {}
        for k in range(0, len(ids), 500):
            chunk = ids[k:k + 500]
            for r in self.q(self.SYM + f"WHERE s.id IN ({','.join('?' * len(chunk))})", chunk):
                out[r[0]] = self.row(r)
        return out

    def members(self, s):
        prefix = s["scope"] + s["name"] + "::"
        return [self.row(r) for r in self.q(self.SYM + "WHERE s.scope = ? ORDER BY s.decl_file, s.decl_line", (prefix,))]

    def related(self, sid, predicate, forward):
        if forward:
            rows = self.q("SELECT object FROM relations WHERE subject=? AND predicate=?", (sid, predicate))
        else:
            rows = self.q("SELECT subject FROM relations WHERE object=? AND predicate=?", (sid, predicate))
        found = self.by_ids([r[0] for r in rows])
        return [found[r[0]] for r in rows if r[0] in found]

    def files_by_ids(self, ids):
        ids = list(dict.fromkeys(i for i in ids if i is not None))
        out = {}
        for k in range(0, len(ids), 500):
            chunk = ids[k:k + 500]
            for fid, rel, root, path, mod in self.q(f"SELECT id, rel, root, path, module FROM files WHERE id IN "
                                                    f"({','.join('?' * len(chunk))})", chunk):
                out[fid] = {"path": ("[E] " if root == "engine" else "") + (rel or ""), "abs_path": path, "module": mod or ""}
        return out

    # ---- 참조 (이 인덱스 몫. excl: 병합 조회에서 뺄 파일 표)

    @staticmethod
    def _x(excl, alias="r"):
        return f" AND {alias}.file NOT IN (SELECT file FROM {excl})" if excl else ""

    def refs_part(self, sid, mask=None, limit=500, after=None, path=None, module=None, excl=None):
        """경로 순 참조 limit 개와 더 있는지. after: 앞 페이지 마지막 (file, line, col) — 스키마 2 는 keyset, 옛 인덱스는 OFFSET 정수."""
        where, args = ["r.sym=?"], [sid]
        if mask:
            where.append("(r.kind & ?) != 0")
            args.append(mask)
        if path:
            where.append("f.rel LIKE ? ESCAPE '\\'")
            args.append(f"%{like_escape(path)}%")
        if module:
            where.append("f.module = ?")
            args.append(module)
        offset = 0
        if after is not None:
            if self.path_order and isinstance(after, tuple):
                where.append("(r.file, r.line, r.col) > (?, ?, ?)")
                args += list(after)
            elif isinstance(after, int):
                offset = after
        order = "r.file, r.line, r.col" if self.path_order else "f.rel, r.line, r.col"
        rows = self.q("SELECT r.kind, f.rel, f.root, r.line, r.col, r.container, f.path, f.module, r.file FROM refs r "
                      f"LEFT JOIN files f ON f.id=r.file WHERE {' AND '.join(where)}{self._x(excl)} ORDER BY {order} "
                      "LIMIT ? OFFSET ?", (*args, limit + 1, offset))
        out = [{"kind": k, "path": ("[E] " if root == "engine" else "") + (rel or ""), "line": ln, "col": c, "container": cont,
                "abs_path": ap, "module": mod or "", "file": fid, "role": self.role, "pos": offset + n}
               for n, (k, rel, root, ln, c, cont, ap, mod, fid) in enumerate(rows[:limit])]
        return out, len(rows) > limit, offset

    def stat(self, sid, stats_ok):
        if not stats_ok:
            return None
        r = self.q("SELECT n_refs, n_use, n_files, n_callers, n_modules FROM sym_stats WHERE sym=?", (sid,))
        return r[0] if r else (0, 0, 0, 0, 0)

    def ref_total(self, sid, mask=None, path=None, module=None, excl=None, stats_ok=False):
        st = self.stat(sid, stats_ok) if not (path or module) and mask in (None, REF) else None
        if st is not None:
            return st[1] if mask == REF else st[0]
        where, args, join = ["r.sym=?"], [sid], ""
        if mask:
            where.append("(r.kind & ?) != 0")
            args.append(mask)
        if path or module:
            join = " JOIN files f ON f.id=r.file"
            if path:
                where.append("f.rel LIKE ? ESCAPE '\\'")
                args.append(f"%{like_escape(path)}%")
            if module:
                where.append("f.module = ?")
                args.append(module)
        return self.q(f"SELECT COUNT(*) FROM refs r{join} WHERE {' AND '.join(where)}{self._x(excl)}", args)[0][0]

    def callers_part(self, sid, limit, excl=None, stats_ok=False):
        """사용(Reference 비트) 참조를 Container 로 묶은 상위 limit 개: [(container, 수, 첫 파일 id, 첫 줄)].
        요약 표가 맞으면 그것을, 아니면 SQL 로 묶는다 — 파이썬으로 전부 가져와 세지 않는다."""
        if stats_ok:
            return self.q("SELECT container, n, file, line FROM sym_callers WHERE sym=? ORDER BY n DESC LIMIT ?", (sid, limit))
        # MIN(rowid) 와 같이 쓴 맨 열(file, line)은 그 행의 값이다 (SQLite 맨 열 규칙) — 스키마 2 는 rowid 가 경로 순이다
        return [(c, n, f, ln) for c, n, _, f, ln in self.q(
            f"SELECT container, COUNT(*) AS n, MIN(r.rowid), r.file, r.line FROM refs r WHERE r.sym=? AND (r.kind & {REF}) != 0"
            f"{self._x(excl)} GROUP BY container ORDER BY n DESC LIMIT ?", (sid, limit))]

    def callers_total(self, sid, excl=None, stats_ok=False):
        st = self.stat(sid, stats_ok)
        if st is not None:
            return st[3]
        return self.q(f"SELECT COUNT(DISTINCT container) FROM refs r WHERE r.sym=? AND (r.kind & {REF}) != 0{self._x(excl)}",
                      (sid,))[0][0]

    def modules_part(self, sid, limit, excl=None, stats_ok=False):
        """[(모듈, 사용 수)] 상위 limit 개와 이 인덱스의 모듈 수."""
        if stats_ok:
            rows = self.q("SELECT module, n FROM sym_modules WHERE sym=? ORDER BY n DESC LIMIT ?", (sid, limit))
            return rows, self.stat(sid, True)[4]
        rows = self.q(f"SELECT f.module, COUNT(*) AS n FROM refs r JOIN files f ON f.id=r.file WHERE r.sym=? "
                      f"AND (r.kind & {REF}) != 0{self._x(excl)} GROUP BY f.module ORDER BY n DESC", (sid,))
        return rows[:limit], len(rows)

    def files_part(self, sid, limit, excl=None, stats_ok=False):
        """[(파일 표시 경로, 사용 수)] 상위 limit 개와 이 인덱스의 파일 수."""
        rows = self.q(f"SELECT r.file, COUNT(*) AS n FROM refs r WHERE r.sym=? AND (r.kind & {REF}) != 0{self._x(excl)} "
                      "GROUP BY r.file ORDER BY n DESC LIMIT ?", (sid, limit))
        st = self.stat(sid, stats_ok)
        total = st[2] if st is not None else self.q(
            f"SELECT COUNT(DISTINCT r.file) FROM refs r WHERE r.sym=? AND (r.kind & {REF}) != 0{self._x(excl)}", (sid,))[0][0]
        names = self.files_by_ids([f for f, _ in rows])
        return [(names.get(f, {}).get("path", "?"), n) for f, n in rows], total

    def callees_part(self, sid, excl=None):
        # Call 비트는 함수류 심볼에 대한 모든 참조에 붙는다(선언·&Fn 포함) — Reference 비트와 같이 본다
        return self.q("SELECT r.sym, COUNT(*) FROM refs r JOIN symbols s ON s.id=r.sym WHERE r.container=? "
                      "AND (r.kind & ?) = ? AND s.kind IN (%s)%s GROUP BY r.sym ORDER BY COUNT(*) DESC"
                      % (",".join("?" * len(FUNC_KINDS)), self._x(excl)), (sid, REF | CALL, REF | CALL) + FUNC_KINDS)

    def has_refs(self, sid, mask=None, path=None, module=None, excl=None):
        return self.ref_total(sid, mask, path, module, excl) > 0 if (path or module) else bool(self.q(
            f"SELECT 1 FROM refs r WHERE r.sym=?{' AND (r.kind & ?) != 0' if mask else ''}{self._x(excl)} LIMIT 1",
            (sid, mask) if mask else (sid,)))


def rank(syms, name):
    pref = {k: i for i, k in enumerate(TYPE_KINDS + FUNC_KINDS)}
    last = name.strip().split("::")[-1].lower()
    return sorted(syms, key=lambda s: (s["name"].lower() != last, pref.get(s["kind"], 50), s["tpl_args"] != "",
                                       len(s["scope"]), s["path"]))


def link_owners(ixs):
    """병합 조회의 소유권: 엔진 인덱스가 참조를 가진 파일은 엔진만 답한다 (clangd MergedIndex). 그래서 질의할 때 위치로 중복을 빼지 않는다.
    반환: 인덱스마다 (뺄 파일 표 또는 None, 요약 표를 써도 되는가), 그리고 상태 설명."""
    out = [[None, ix.has_stats and ix.meta.get("stats_scope", "all") == "all"] for ix in ixs]
    proj = [i for i, ix in enumerate(ixs) if ix.role == "project"]
    eng = [i for i, ix in enumerate(ixs) if ix.role == "engine"]
    if not proj or not eng:
        return out, ""
    p, e = ixs[proj[0]], ixs[eng[0]]
    if "owned_out" in p.tables and p.meta.get("owner_build") and p.meta.get("owner_build") == db_identity(e.meta):
        out[proj[0]] = ["owned_out", p.has_stats and p.meta.get("stats_scope") == "own"]
        return out, f"엔진이 주인인 파일 {p.meta.get('owned_files', '?')}개 (빌드 때 표시)"
    # 표시가 없거나 다른 엔진 인덱스를 보고 만든 것 → 이 연결에서만 계산한다 (요약 표는 못 쓴다: SQL 로 센다)
    owned = engine_ref_paths(e.con)
    ids = [(i,) for i, path in p.q("SELECT id, path FROM files") if norm(path) in owned]
    p.write_temp("CREATE TEMP TABLE IF NOT EXISTS owned_tmp(file INTEGER PRIMARY KEY)")
    p.write_temp("DELETE FROM temp.owned_tmp")
    p.write_temp("INSERT INTO temp.owned_tmp VALUES(?)", ids)
    out[proj[0]] = ["temp.owned_tmp", False]
    return out, f"엔진이 주인인 파일 {len(ids)}개 (조회 때 계산 — `cindex.py optimize` 로 표시하면 빨라진다)"


class MultiIndex:
    """프로젝트 범위 + 엔진 범위 인덱스를 한 번에 본다 (기본). 인덱스 하나여도 이것으로 연다.
    - 심볼은 clangd USR 해시 ID 라 두 인덱스에서 같다 → ID 로 합친다 (작은 결과).
    - 참조는 파일마다 주인이 하나다 (link_owners) → 각 인덱스에 LIMIT·COUNT·GROUP BY 를 내려보내고 작은 결과만 합친다.
      프로젝트 인덱스가 먼저다 (clangd 가 작고 새로운 dynamic 인덱스를 먼저 묻는 것과 같고, 자기 게임 코드의 사용처를 먼저 본다).
    예전에는 두 인덱스에서 참조를 최대 100만 행씩 가져와 파이썬에서 위치로 중복을 뺐다 — 참조 340만 심볼에서 45초 (합성 측정)."""

    def __init__(self, ixs):
        self.ixs = sorted(ixs, key=lambda i: i.role != "project")
        self.path = " + ".join(str(i.path) for i in self.ixs)
        self.meta = self.ixs[0].meta
        self.roots = self.ixs[0].roots
        links, self.owner_note = link_owners(self.ixs)
        self.parts = [(ix, x, ok) for ix, (x, ok) in zip(self.ixs, links)]

    def q(self, sql, args=()):
        if len(self.ixs) != 1:
            raise RuntimeError("q() 는 인덱스 하나일 때만 쓴다")
        return self.ixs[0].q(sql, args)

    @staticmethod
    def _merge(lists):
        out = {}
        for s in (x for lst in lists for x in lst):
            cur = out.get(s["id"])
            if cur is None or (not cur["def_path"] and s["def_path"]):
                out[s["id"]] = s
        return list(out.values())

    def find_exact(self, name, kinds=None):
        return self._merge(ix.find_exact(name, kinds) for ix in self.ixs)

    def find_fuzzy(self, name, limit=200, kinds=None):
        return self._merge(ix.find_fuzzy(name, limit, kinds) for ix in self.ixs)

    def find(self, name, limit=200, kinds=None):
        """정확히 맞는 것(한정 이름 또는 이름)이 있으면 그것만, 없으면 접두·부분 일치. 웹뷰 검색이 쓴다."""
        return rank(self.find_exact(name, kinds) or self.find_fuzzy(name, limit, kinds), name)[:limit]

    def file_syms(self, pattern, limit):
        return sorted(self._merge(ix.file_syms(pattern, limit) for ix in self.ixs), key=lambda s: (s["path"], s["line"] or 0))[:limit]

    def by_id(self, sid):
        found = [s for s in (ix.by_id(sid) for ix in self.ixs) if s]
        return self._merge([found])[0] if found else None

    def by_ids(self, ids):
        ids = list(ids)
        return {s["id"]: s for s in self._merge(list(ix.by_ids(ids).values()) for ix in self.ixs)}

    def names(self, ids):
        found = self.by_ids(ids)
        return {sid: found.get(sid) for sid in ids}

    def members(self, s):
        return sorted(self._merge(ix.members(s) for ix in self.ixs), key=lambda m: (m["path"], m["line"] or 0))

    def related(self, sid, predicate, forward):
        return self._merge(ix.related(sid, predicate, forward) for ix in self.ixs)

    def bases(self, sid):
        return self.related(sid, BASE_OF, False)

    def derived(self, sid):
        return self.related(sid, BASE_OF, True)

    # ---- 참조

    @staticmethod
    def _cursor(c):
        """'<인덱스 순번>:<file>:<line>:<col>' (keyset) 또는 '<순번>:o<오프셋>' (옛 인덱스)."""
        if not c:
            return 0, None
        try:
            head, rest = c.split(":", 1)
            if rest.startswith("o"):
                return int(head), int(rest[1:])
            f, ln, col = rest.split(":")
            return int(head), (int(f), int(ln), int(col))
        except ValueError:
            raise SystemExit(f"--cursor 형식이 아니다: {c!r}")

    def refs_page(self, sid, mask=None, limit=500, cursor=None, path=None, module=None):
        """(참조 limit 개, 더 있는가, 다음 커서). 프로젝트 인덱스 몫을 경로 순으로 다 낸 뒤 엔진 몫."""
        start, after = self._cursor(cursor)
        out, more, nxt = [], False, None
        for pi, (ix, x, _) in enumerate(self.parts):
            if pi < start:
                continue
            rows, part_more, _ = ix.refs_part(sid, mask, limit - len(out), after if pi == start else None, path, module, x)
            for r in rows:
                r["part"] = pi
            out += rows
            if len(out) >= limit:
                more = part_more or any(ix2.has_refs(sid, mask, path, module, x2) for ix2, x2, _ in self.parts[pi + 1:])
                if more and out:
                    nxt = self.cursor_after(out[-1])
                break
        return out, more, nxt

    def cursor_after(self, r):
        """이 참조 다음부터 이어 보는 커서."""
        ix = self.parts[r["part"]][0]
        return f"{r['part']}:{r['file']}:{r['line']}:{r['col']}" if ix.path_order else f"{r['part']}:o{r['pos'] + 1}"

    def refs(self, sid, mask=None, limit=500):
        return self.refs_page(sid, mask, limit)[0]

    def ref_parts(self, sid, mask=None, path=None, module=None):
        """[(역할, 참조 수)] — 파일마다 주인이 하나라 더하면 총계다."""
        return [(ix.role, ix.ref_total(sid, mask, path, module, x, ok)) for ix, x, ok in self.parts]

    def ref_count(self, sid):
        return sum(n for _, n in self.ref_parts(sid))

    def _callers(self, sid, limit):
        """[(container, 수, 인덱스 순번, 첫 파일 id, 첫 줄)] 상위 limit. 인덱스마다 상위 limit 을 받아 합친다 —
        함수 본문은 한 파일에 있고 파일마다 주인이 하나라 호출자가 인덱스끼리 겹치지 않는다 (파일 범위 NULL 만 더해진다)."""
        merged = {}
        for pi, (ix, x, ok) in enumerate(self.parts):
            for cont, n, f, ln in ix.callers_part(sid, limit, x, ok):
                cur = merged.get(cont)
                if cur:
                    cur[0] += n
                else:
                    merged[cont] = [n, pi, f, ln]
        top = sorted(merged.items(), key=lambda kv: -kv[1][0])[:limit]
        return [(c, v[0], v[1], v[2], v[3]) for c, v in top]

    def callers_total(self, sid):
        return sum(ix.callers_total(sid, x, ok) for ix, x, ok in self.parts)

    def callers(self, sid, limit=200):
        top = self._callers(sid, limit)
        syms = self.by_ids(c for c, *_ in top)
        return [(syms.get(c) if c != NULL_ID else None, n) for c, n, *_ in top]

    def caller_sites(self, sid, limit):
        """호출자마다 첫 참조 위치 하나 (줄 원문을 같이 보이려고)."""
        top = self._callers(sid, limit)
        syms = self.by_ids(c for c, *_ in top)
        files = {}
        for pi, (ix, _, _) in enumerate(self.parts):
            files[pi] = ix.files_by_ids([f for _, _, p, f, _ in top if p == pi])
        out = []
        for c, n, pi, f, ln in top:
            fi = files[pi].get(f, {})
            out.append((syms.get(c) if c != NULL_ID else None, n,
                        {"path": fi.get("path", ""), "line": ln, "abs_path": fi.get("abs_path")}))
        return out

    def modules(self, sid, limit):
        """([(모듈, 사용 수)] 상위 limit, 모듈 수, 모듈 수가 하한인가). 인덱스마다 TOP_MODULES 개까지 받아 합친다 —
        어느 인덱스도 잘리지 않았으면 모듈 수가 정확하고, 잘렸으면 하한이다 (사용 수 상위는 그래도 맞다)."""
        merged, totals, cut = {}, [], False
        for ix, x, ok in self.parts:
            rows, total = ix.modules_part(sid, max(limit, TOP_MODULES), x, ok)
            totals.append(total)
            cut = cut or total > len(rows)
            for m, n in rows:
                merged[m] = merged.get(m, 0) + n
        top = sorted(merged.items(), key=lambda kv: -kv[1])
        n_mod = max(len(merged), max(totals or [0]))
        return top[:limit], n_mod, cut

    def files(self, sid, limit):
        """([(파일, 사용 수)] 상위 limit, 사용이 있는 파일 수). 파일은 인덱스끼리 겹치지 않는다."""
        rows, total = [], 0
        for ix, x, ok in self.parts:
            r, t = ix.files_part(sid, limit, x, ok)
            rows += r
            total += t
        return sorted(rows, key=lambda kv: -kv[1])[:limit], total

    def callees(self, sid):
        n = {}
        for ix, x, _ in self.parts:
            for cid, k in ix.callees_part(sid, x):
                n[cid] = n.get(cid, 0) + k
        syms = self.by_ids(n)
        return [(syms.get(c), k) for c, k in sorted(n.items(), key=lambda kv: -kv[1]) if syms.get(c)]


def tree(ix, sid, predicate, forward, max_depth=0):
    """관계를 끝까지 따라간다 (깊이 우선, 들여쓰기용 깊이 포함). [(깊이, 심볼)] — 같은 심볼은 한 번만."""
    seen, out = {sid}, []

    def walk(cur, d):
        if max_depth and d > max_depth:
            return
        for x in sorted(ix.related(cur, predicate, forward), key=lambda s: s["scope"] + s["name"]):
            if x["id"] in seen:
                continue
            seen.add(x["id"])
            out.append((d, x))
            walk(x["id"], d + 1)
    walk(sid, 1)
    return out


def tree_lines(title, items):
    if not items:
        return [f"## {title} 0"]
    per = {}
    for d, _ in items:
        per[d] = per.get(d, 0) + 1
    head = f"## {title} {len(items)} (" + " · ".join(f"{d}단계 {n}" for d, n in sorted(per.items())) + ")"
    return [head] + [f"  {'  ' * (d - 1)}{fmt(x)}" for d, x in items]


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


IMPACT_MEMBERS = 200


def impact_lines(ix, s, limit):
    """이 심볼을 바꾸면 같이 봐야 할 곳: 파생 타입·재정의(전 단계), 참조하는 함수, 참조가 있는 파일·모듈.
    타입이면 멤버(메서드·필드) 사용도 센다 — Peer->Tick() 처럼 멤버만 부르는 곳도 그 타입을 바꾸면 영향받는다.
    심볼마다 상위 몫만 받아(요약 표·SQL 집계) 합친다 — 참조를 전부 가져오지 않는다. 상위에서 잘린 몫이 있으면 수에 + 를 붙인다."""
    out = []
    if s["kind"] in TYPE_KINDS:
        out += tree_lines("파생 타입 (전 단계)", tree(ix, s["id"], BASE_OF, True)[:limit * 2])
    if s["kind"] in FUNC_KINDS:
        out += tree_lines("재정의한 쪽 (전 단계)", tree(ix, s["id"], OVERRIDDEN_BY, True)[:limit * 2])
    members = [m["id"] for m in ix.members(s)] if s["kind"] in TYPE_KINDS else []
    ids = [s["id"]] + members[:IMPACT_MEMBERS]
    per = max(limit * 4, 50)
    by_fn, files, mods = {}, {}, {}
    n_use, fn_cut, file_cut, mod_cut = 0, False, False, False
    for i in ids:
        n_use += sum(n for _, n in ix.ref_parts(i, REF))
        top = ix._callers(i, per)
        fn_cut = fn_cut or len(top) >= per
        for c, n, *_ in top:
            by_fn[c] = by_fn.get(c, 0) + n
        frows, ftotal = ix.files(i, per)
        file_cut = file_cut or ftotal > len(frows)
        for f, n in frows:
            files[f] = files.get(f, 0) + n
        mrows, _, approx = ix.modules(i, TOP_MODULES)
        mod_cut = mod_cut or approx or len(mrows) >= TOP_MODULES
        for m, n in mrows:
            mods[m] = mods.get(m, 0) + n
    note = " (타입 이름 + 멤버 사용)" if len(ids) > 1 else ""
    if len(members) > IMPACT_MEMBERS:
        note += f" — 멤버 {len(members)}개 중 {IMPACT_MEMBERS}개만"
    top = sorted(by_fn.items(), key=lambda kv: -kv[1])[:limit]
    syms = ix.by_ids(c for c, _ in top)
    out.append(f"## 참조하는 함수·범위 {len(by_fn)}{'+' if fn_cut else ''}{note} · 사용 참조 {n_use}")
    out += [f"  {n:>4}× {fmt(syms.get(c) if c != NULL_ID else None)}" for c, n in top]
    out.append(f"## 참조가 있는 파일 {len(files)}{'+' if file_cut else ''}{note} · 모듈 {len(mods)}{'+' if mod_cut else ''}: "
               + ", ".join(f"{m or '(모듈 없음)'} {n}" for m, n in sorted(mods.items(), key=lambda x: -x[1])[:12]))
    out += [f"  {n:>4}× {rel}" for rel, n in sorted(files.items(), key=lambda x: -x[1])[:limit]]
    return out


def open_index(a, root, kind):
    """--db 가 없으면 있는 인덱스를 다 같이 본다 (프로젝트 + 엔진). --db project|engine|경로 면 그 하나만."""
    if not a.db:
        dbs = [(p, r) for p, r in ((db_for("project", root, kind), "project"), (db_for("engine", root, kind), "engine"))
               if p and p.exists()]
        if dbs:
            return MultiIndex([Index(p, r) for p, r in dbs])
    db = pick_db(a.db, root, kind)
    if not db or not db.exists():
        print(f"clangd 인덱스 없음: {db}. `cindex.py build` 를 먼저 돌린다.")
        return None
    return MultiIndex([Index(db, a.db if a.db in ("engine", "project") else None)])


def pick_one(ix, name, kinds=None):
    """정확히 맞는 심볼만 고른다. 없으면 고르지 않고 비슷한 이름 후보를 보여 준다 — 근사 결과를 답처럼 내지 않는다."""
    cands = rank(ix.find_exact(name, kinds), name)
    if cands:
        return cands[0], cands[1:]
    near = rank(ix.find_fuzzy(name, 40, kinds), name)[:12]
    print(f"정확히 일치하는 심볼 없음: {name!r}" + (" — 비슷한 이름 (이 중 하나로 다시 묻는다):" if near else ""))
    for s in near:
        print("  " + fmt(s))
    return None, []


def cmd_status(ix):
    counts = json.loads(ix.meta.get("counts", "{}"))
    errors = json.loads(ix.meta.get("errors", '{"count": 0}')) if ix.meta.get("errors") else {"count": "?"}
    print(f"인덱스 {ix.path} · {ix.meta.get('generated_at')} · 심볼 {counts.get('symbols')} · 참조 {counts.get('refs')} · "
          f"관계 {counts.get('relations')} · 파일 {counts.get('files')}")
    print(f"출처 {ix.meta.get('source')} · cdb {ix.meta.get('cdb', '-')} · 필터 {ix.meta.get('filter', '-') or '-'} · "
          f"오류 있던 TU {errors.get('failed_tu', '?')} · 오류 줄 {'-' if errors.get('count') is None else errors.get('count')}"
          + (f" (.generated.h 관련 {errors.get('generated_h')})" if errors.get("generated_h") else ""))
    print(f"스키마 {ix.schema}" + (f" · 요약 표 {'있음' if ix.has_stats else '없음'} · 요약 범위 {ix.meta.get('stats_scope', '-')}"
                                   if ix.schema >= SCHEMA_VERSION else
                                   " — 옛 모양: `cindex.py optimize` 로 바꾸면 참조·호출자 조회가 빨라진다 (색인은 다시 안 한다)"))
    stale = [p for (p, m) in ix.q("SELECT path, mtime FROM files ORDER BY RANDOM() LIMIT 300")
             if not os.path.exists(p) or int(os.stat(p).st_mtime) != m]
    print(f"[낡음] 표본 파일 {len(stale)}개가 인덱스 뒤 바뀌었다 → build" if stale else "신선도: 표본 300 파일 OK")
    return 0


ROLE_NAMES = {"project": "프로젝트", "engine": "엔진"}


def part_text(parts):
    """[(역할, 수)] → ' (프로젝트 n · 엔진 m)'. 인덱스가 하나면 빈 문자열."""
    return " (" + " · ".join(f"{ROLE_NAMES.get(r, r)} {n}" for r, n in parts) + ")" if len(parts) > 1 else ""


def refs_report(ix, s, head, a, lc):
    """에이전트용 참조 보고: 총계(인덱스별) · 사용 모듈 상위 · 프로젝트 먼저 경로 순 표본(줄 원문) · 잘림 표시와 다음 커서.
    결과가 많으면 전부 내지 않고 좁히는 법을 알려 준다 (SWE-agent: 결과 50개 이하로 요약한 검색이 하나씩 보여 주는 검색보다 해결률이 높았다)."""
    mask = {"decl": DECL, "def": DEF, "ref": REF}.get(a.kind)
    rows, more, _ = ix.refs_page(s["id"], mask, a.limit, a.cursor, a.path, a.module)
    parts = ix.ref_parts(s["id"], mask, a.path, a.module)
    total = sum(n for _, n in parts)
    names = ix.names({r["container"] for r in rows})
    filt = " ".join(x for x in (f"--kind {a.kind}" if a.kind else "", f"--path {a.path}" if a.path else "",
                                f"--module {a.module}" if a.module else "") if x)
    summary = [f"참조 {total}{part_text(parts)}" + (f" · 필터 {filt}" if filt else "")]
    if not (a.path or a.module) and total:
        mods, n_mod, approx = ix.modules(s["id"], 6)
        if mods:
            summary.append(f"사용 모듈 {n_mod}{'+' if approx else ''}: " + " · ".join(f"{m or '(모듈 없음)'} {n}" for m, n in mods)
                           + (" …" if n_mod > len(mods) else ""))
    lines = [f"{'D' if r['kind'] & DEF else 'd' if r['kind'] & DECL else 'r'} {r['path']}:{r['line']}:{r['col']}"
             f"  in {(names.get(r['container']) or {}).get('name', '(파일 범위)')}  │ {lc.text(r['abs_path'], r['line'])}"
             for r in rows]
    top = head + summary
    shown = len(lines) if a.full else min(len(lines), fits(lines, max(CAP - len("\n".join(top).encode("utf-8")) - 400, 600)))
    rest = shown < len(lines) or more
    tail = []
    if rest and shown:
        tail.append(f"[잘림] {shown}/{total} · 다음: --cursor {ix.cursor_after(rows[shown - 1])} · "
                    "좁히기: --module <모듈> | --path <경로 조각> | --kind ref|decl|def")
    order = "프로젝트 먼저 · 경로 순" if len(ix.parts) > 1 else "경로 순"
    print("\n".join(top + [f"── {order} · {shown}개 ──" if rows else "참조 없음"] + lines[:shown] + tail))
    return 0


def cmd_query(a, root, kind):
    ix = open_index(a, root, kind)
    if ix is None:
        return 1
    c, arg = a.command, " ".join(a.arg).strip()
    if c == "status":
        for sub in ix.ixs:
            if len(ix.ixs) > 1:
                print(f"--- {'엔진' if sub.role == 'engine' else '프로젝트'} 범위")
            cmd_status(sub)
        if ix.owner_note:
            print(f"--- 합쳐 보기: {ix.owner_note}")
        return 0
    if not arg:
        raise SystemExit(f"{c} 는 인자가 필요하다.")
    if c == "sym":
        exact = rank(ix.find_exact(arg), arg)
        rows = exact or rank(ix.find_fuzzy(arg, a.limit), arg)
        head = [] if exact else [f"# 정확히 일치하는 심볼 없음: {arg!r} — 이름이 비슷한 것"]
        emit(head + [fmt(s) + (f"\n    정의 {s['def_path']}:{s['def_line']}" if s["def_path"] and s["def_path"] != s["path"] else "")
                     for s in rows[:a.limit]] or [f"없음: {arg!r}"], a.full)
        return 0
    if c == "file":
        emit([fmt(s) for s in ix.file_syms(arg, a.limit * 4)] or [f"없음: {arg!r}"], a.full)
        return 0
    kinds = FUNC_KINDS if c in ("callees", "overrides") else (TYPE_KINDS if c in ("bases", "derived", "members") else None)
    s, others = pick_one(ix, arg, kinds)
    if s is None:
        return 1
    head = [f"# {fmt(s)}"] + ([f"# 같은 이름 후보 {len(others)}개 더 — A::B 로 좁힌다"] if others else [])
    lc = LineCache()
    if c == "refs":
        return refs_report(ix, s, head, a, lc)
    elif c == "callers":
        sites = ix.caller_sites(s["id"], a.limit)
        n_call = ix.callers_total(s["id"])
        uses = ix.ref_parts(s["id"], REF)
        lines = [f"{n:>4}× {fmt(x)}\n       {site['path']}:{site['line']}  │ {lc.text(site['abs_path'], site['line'])}"
                 for x, n, site in sites]
        summary = f"호출자 {n_call} · 사용 참조 {sum(n for _, n in uses)}{part_text(uses)} — 사용 수 순"
        tail = ([f"[잘림] 호출자 상위 {len(sites)}/{n_call} · 더 보려면 --limit N · 좁히기: refs {arg} --module <모듈> | --path <경로 조각>"]
                if n_call > len(sites) else [])
        emit(head + [summary] + (lines or ["없음"]), a.full, tail)
    elif c == "members":
        rows = ix.members(s)
        emit(head + [f"{m['kind']:<15} {m['name']:<32} :{m['line']}  │ {lc.text(m['abs_path'], m['line'])}" for m in rows[:a.limit * 3]]
             + ([f"… (+{len(rows) - a.limit * 3})"] if len(rows) > a.limit * 3 else []) or ["멤버 없음"], a.full)
    elif c == "impact":
        emit(head + impact_lines(ix, s, a.limit), a.full)
    elif c == "callees":
        emit(head + [f"{n:>4}× {fmt(x)}" for x, n in ix.callees(s["id"])[:a.limit]] or ["없음"], a.full)
    elif c == "bases":
        emit(head + tree_lines("부모 (위로, 전 단계)", tree(ix, s["id"], BASE_OF, False, a.depth)), a.full)
    elif c == "derived":
        emit(head + tree_lines("파생 (아래로, 전 단계)", tree(ix, s["id"], BASE_OF, True, a.depth)), a.full)
    elif c == "overrides":
        emit(head + tree_lines("재정의 대상 (위로)", tree(ix, s["id"], OVERRIDDEN_BY, False, a.depth))
             + tree_lines("재정의한 쪽 (아래로, 전 단계)", tree(ix, s["id"], OVERRIDDEN_BY, True, a.depth)), a.full)
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
        self.ix = MultiIndex([Index(db, scope)]) if self.available else None

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
            rel["호출하는 쪽 (참조 Container)"] = [self._out(x) for x, _ in self.ix.callers(sid, 60) if x]
            rel["부르는 함수"] = [self._out(x) for x, _ in self.ix.callees(sid) if x][:60]
        refs = self.ix.refs(sid, None, 60)
        s["ref_rows"] = self.ix.ref_count(sid)
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
            return out + [(x["id"], "calls", False) for x, _ in ix.callers(i, 60) if x and x["kind"] in FUNC_KINDS][:25]
        return bfs_graph(starts, nb, lambda i: sym(i)["scope"] + sym(i)["name"], lambda i: sym(i)["kind"], depth,
                         lambda i: {"module": sym(i).get("module"), "path": sym(i).get("path"), "line": sym(i).get("line")})

    def _module_edges(self):
        """[(참조한 모듈, 선언된 모듈, 참조 수)] — 실제 참조로 본 모듈 의존."""
        return self.ix.q("SELECT rf.module, df.module, COUNT(*) FROM refs r JOIN files rf ON rf.id=r.file "
                         "JOIN symbols s ON s.id=r.sym JOIN files df ON df.id=s.decl_file "
                         "WHERE rf.module != '' AND df.module != '' AND rf.module != df.module "
                         "AND (r.kind & ?) != 0 GROUP BY rf.module, df.module", (REF,))

    def _module_roots(self):
        return dict(self.ix.q("SELECT module, root FROM files WHERE module != '' GROUP BY module"))

    def _module_graph(self, focus, depth):
        """실제 참조로 본 모듈 의존: 모듈 A 파일의 참조가 모듈 B 에 선언된 심볼을 가리키면 A → B."""
        rows = self._module_edges()
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
            out.append({"name": "clangd 오류 있던 TU" + (" (배경 색인)" if bg else ""),
                        "metric": f"오류 있던 TU {errors.get('failed_tu', '?')} · 오류 줄 {'-' if bg else errors['count']} · "
                                  f".generated.h 관련 {'-' if bg else errors.get('generated_h', 0)}",
                        "pass": not errors.get("failed_tu") and errors.get("count") in (0, None),
                        "why": "clangd-indexer 는 TU 에 오류가 있어도 종료 코드 0 이라 stderr 로 센다 (배경 색인은 샤드의 오류 표시). "
                               "오류가 있어도 심볼은 대부분 들어간다. UE 에서 .generated.h 누락·낡음(UHT 미실행)이면 UCLASS 클래스 선언과 멤버가 "
                               "빠진다 (.cpp 의 메서드 정의만 남는다) — 에디터 빌드 뒤 다시 build.",
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
        facts += [["오류 있던 TU", errors.get("failed_tu", "-")],
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
            # 재정의 관계가 가장 많은 메서드 (Symbol.References 는 배경 색인 빌드에서 0 이라 쓰지 않는다)
            row = ix.q("SELECT s.id FROM symbols s JOIN relations r ON r.subject=s.id AND r.predicate=? "
                       "GROUP BY s.id ORDER BY COUNT(*) DESC, (SELECT COUNT(*) FROM refs x WHERE x.sym=s.id) DESC LIMIT 1",
                       (OVERRIDDEN_BY,))
            if not row:
                row = (ix.q("SELECT sym FROM sym_stats ORDER BY n_refs DESC LIMIT 1") if ix.ixs[0].has_stats else
                       ix.q("SELECT sym FROM refs GROUP BY sym ORDER BY COUNT(*) DESC LIMIT 1"))
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
        rows = self._module_edges()
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
        roots = self._module_roots()
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



class MergedCindexSource(CindexSource):
    """웹뷰에서 clangd 를 하나로 본다 — 프로젝트 + 엔진 인덱스 (명령줄 기본과 같은 MultiIndex: 심볼 ID 로 합치고 참조는 위치로 중복 제거).
    검색·상세·참조·그래프·모듈 행렬은 합친 인덱스로, 개요는 겹치는 심볼을 ID 로 한 번만 센다.
    파이프라인·해부·커버리지·자체 검사는 인덱스마다 다른 것이라 각 인덱스 결과를 묶어 보인다 (개별 소스는 aux 로 남아 대조에 쓰인다)."""

    def __init__(self, parts):
        self.parts = [p for p in parts if p.available]
        self.name = "clangd"
        self.scope = "all"
        self.covers = {"engine", "project"}
        self.db = None
        self.available = bool(self.parts)
        names = {"project": "프로젝트", "engine": "엔진"}
        self.label = "clangd · " + ("+".join(names[p.scope] for p in self.parts) if self.parts else "프로젝트+엔진") + " (cindex)"
        # 범위별 소스와 연결을 나누지 않는다 — 합쳐 보기는 프로젝트 인덱스 연결에 소유권 temp 표를 만들 수 있다
        self.ix = (MultiIndex([Index(p.db, p.scope) for p in self.parts]) if len(self.parts) > 1 else self.parts[0].ix) if self.parts else None
        self._ov = None

    def _part(self, scope):
        return next((p for p in self.parts if p.scope == scope), None)

    def info(self):
        if not self.available:
            return {"missing": "clangd 인덱스 없음 — `cindex.py build` (index_build.bat)"}
        out = {"parts": {p.scope: p.info() for p in self.parts}, "db": " + ".join(str(p.db) for p in self.parts)}
        if not self._part("engine"):
            out["note"] = "엔진 clangd 인덱스 없음 — 프로젝트 인덱스에 든 엔진 헤더 심볼만 보인다 (런처 설치 엔진은 엔진 TU 가 없다)"
        return out

    def _module_edges(self):
        if len(self.parts) == 1:
            return self.parts[0]._module_edges()
        n = {}
        for p in self.parts:
            for a, b, c in p._module_edges():
                n[(a, b)] = n.get((a, b), 0) + c
        return [(a, b, c) for (a, b), c in n.items()]

    def _module_roots(self):
        out = {}
        for p in self.parts:
            for m, r in p._module_roots().items():
                out.setdefault(m, r)
        return out

    def overview(self):
        if len(self.parts) == 1:
            return self.parts[0].overview()
        if self._ov is None:
            self._ov = self._merged_overview()
        return self._ov

    def _merged_refs(self):
        """합쳐 본 참조 수 — 파일마다 주인이 하나라 각 인덱스의 주인 몫을 더한다 (ref_files 가 있으면 파일별 합으로)."""
        total = 0
        for ix, x, _ in self.ix.parts:
            if x:
                total += ix.q(f"SELECT IFNULL(SUM(n), 0) FROM ref_files WHERE file NOT IN (SELECT file FROM {x})")[0][0] \
                    if "ref_files" in ix.tables else ix.q(f"SELECT COUNT(*) FROM refs r WHERE 1{Index._x(x)}")[0][0]
            else:
                total += int(json.loads(ix.meta.get("counts", "{}")).get("refs") or 0)
        return total

    def _merged_overview(self):
        """두 인덱스를 합친 개요. 심볼·관계·파일은 ID·경로로 겹친 것을 한 번만 센다 (엔진 헤더 심볼은 양쪽에 있다).
        참조는 파일 소유권으로 센다 — 엔진 인덱스가 가진 파일의 참조는 엔진 쪽만 (MultiIndex 와 같은 규칙)."""
        proj, eng = self._part("project"), self._part("engine")
        ovs = {p.scope: p.overview() for p in self.parts}
        con = sqlite3.connect(f"file:{Path(proj.db).as_posix()}?mode=ro", uri=True)
        try:
            con.execute("ATTACH DATABASE ? AS e", (f"file:{Path(eng.db).as_posix()}?mode=ro",))
            kinds = con.execute("SELECT kind, COUNT(*) FROM (SELECT id, kind FROM main.symbols UNION SELECT id, kind FROM e.symbols) "
                                "GROUP BY kind ORDER BY 2 DESC").fetchall()
            rel = dict(con.execute("SELECT predicate, COUNT(*) FROM (SELECT subject, predicate, object FROM main.relations "
                                   "UNION SELECT subject, predicate, object FROM e.relations) GROUP BY predicate").fetchall())
            n_files = con.execute("SELECT COUNT(*) FROM (SELECT path FROM main.files UNION SELECT path FROM e.files)").fetchone()[0]
        finally:
            con.close()
        refs = self._merged_refs()
        mods = {}
        for o in ovs.values():
            for m in o["modules"]:
                k = (m["name"], m["group"])
                cur = mods.get(k)
                if cur is None:
                    mods[k] = dict(m)
                else:  # 엔진 모듈은 엔진 인덱스가 더 많이 본다 — 큰 쪽을 쓰고 참조는 더한다
                    cur["symbols"], cur["files"] = max(cur["symbols"], m["symbols"]), max(cur["files"], m["files"])
                    cur["refs"] = cur.get("refs", 0) + m.get("refs", 0)
        rk = {}
        for o in ovs.values():
            for k, v in (o.get("ref_kinds") or {}).items():
                rk[k] = rk.get(k, 0) + (v or 0)
        pb, eb = ovs["project"]["build"], ovs["engine"]["build"]
        return {"counts": {"symbols": sum(n for _, n in kinds), "refs": refs, "relations": sum(rel.values()), "files": n_files},
                "kinds": kinds, "modules": sorted(mods.values(), key=lambda m: -m["symbols"])[:400],
                "relations": {"BaseOf": rel.get(BASE_OF, 0), "OverriddenBy": rel.get(OVERRIDDEN_BY, 0)},
                "ref_kinds": rk, "failed_tu": sum(o.get("failed_tu") or 0 for o in ovs.values()),
                "generated_h": sum(o.get("generated_h") or 0 for o in ovs.values()),
                "build": {"at": pb.get("at"), "mode": f"프로젝트 {pb.get('mode') or '-'} · 엔진 {eb.get('mode') or '-'}",
                          "tus": (pb.get("tus") or 0) + (eb.get("tus") or 0) if (pb.get("tus") or eb.get("tus")) else None,
                          "engine_at": eb.get("at")},
                "note": "프로젝트+엔진 합침 — 심볼·관계·파일은 겹친 것을 한 번만, 참조는 파일 주인 기준 (엔진 인덱스가 가진 파일은 엔진 쪽만). "
                        + self.ix.owner_note}

    def pipeline(self):
        """파이프라인은 인덱스마다 다르다 — 자주 바뀌는 프로젝트 인덱스를 보이고 엔진 인덱스는 사실 줄로 붙인다."""
        main = self._part("project") or self.parts[0]
        out = main.pipeline()
        for p in self.parts:
            if p is not main:
                m = p.ix.meta
                out["facts"] = out["facts"] + [[f"{'엔진' if p.scope == 'engine' else '프로젝트'} 인덱스",
                                                 f"{m.get('generated_at', '-')} · {m.get('mode', m.get('source', '-'))} · TU {m.get('tus', '-')}"]]
        out["mode"] = f"{'프로젝트' if main.scope == 'project' else '엔진'} 인덱스 기준 — " + str(out.get("mode") or "")
        return out

    def anatomy(self, name=None):
        """심볼이 있는 인덱스의 원본 레코드 (이름이 없으면 프로젝트 인덱스에서 고른다)."""
        for p in sorted(self.parts, key=lambda p: p.scope != "project"):
            a = p.anatomy(name)
            if a:
                a["index"] = "프로젝트" if p.scope == "project" else "엔진"
                return a
        return None

    def coverage(self):
        outs = [p.coverage() for p in self.parts]
        return {"root": " + ".join(o.get("root", "") for o in outs if o.get("root")),
                "total": sum(o.get("total", 0) for o in outs), "indexed": sum(o.get("indexed", 0) for o in outs),
                "modules": sorted((m for o in outs for m in o.get("modules", [])), key=lambda m: -m["disk"])[:200]}

    def checks(self):
        out = []
        for p in self.parts:
            out += [dict(c, name=f"[{'프로젝트' if p.scope == 'project' else '엔진'}] {c['name']}") for c in p.checks()]
        return out

def _fmt_bytes(n):
    if not n:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def view_sources(root, kind):
    """웹뷰 소스: 합친 clangd 하나 + 범위별 clangd (aux — 선택 목록에는 안 보이고 정규식↔clangd 대조·질의 세트에 쓰인다)."""
    parts = [CindexSource("project", db_for("project", root, kind))]
    if kind == "ue":
        parts.append(CindexSource("engine", db_for("engine", root, kind)))
    for p in parts:
        p.aux = True
    return [MergedCindexSource(parts)] + parts


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
            or next((s for s in sources.values() if s.engine == "clangd" and s.available and not hasattr(s, "parts")), None)
        if oracle is None:
            return {"note": f"{spec_path} 도 clangd 인덱스도 없어 질의 세트를 만들 수 없다.", "summary": [], "results": []}
        rows = oracle.ix.q("SELECT s.name, df.rel, df.root FROM symbols s JOIN files df ON df.id=s.def_file WHERE s.kind IN "
                           "('Class','Struct','Enum') AND s.tpl_args = '' AND s.name != '' AND df.root != '' "
                           "ORDER BY RANDOM() LIMIT ?", (n_auto,))
        queries = list(rows)
        note = (f"{spec_path} 가 없어 {oracle.label} 의 정의 위치로 질의 {len(queries)}개를 자동 생성했다 (이름 → 정의 파일). "
                f"정답을 낸 소스는 채점에서 뺐다. 요청→수정 파일 같은 실제 과제 세트는 이 파일에 적는다: "
                f'{{"queries": [{{"q": "…", "expect": "경로 조각", "root": "engine|project(생략 가능)"}}]}}')
    # 정답을 낸 인덱스를 품은 합친 소스도 빼야 자기 채점이 아니다
    names = [s.name for s in sources.values() if s.available and hasattr(s, "search") and s is not oracle
             and oracle not in getattr(s, "parts", ())]
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
    ap.add_argument("command", choices=["cdb", "build", "ingest", "optimize", "status", "sym", "refs", "callers", "callees",
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
    ap.add_argument("--cursor", default=None, help="refs: 앞 출력의 [잘림] 줄에 있는 커서로 이어 본다")
    ap.add_argument("--path", default=None, help="refs: 경로 조각으로 좁힌다")
    ap.add_argument("--module", default=None, help="refs: 모듈로 좁힌다 (Build.cs 이름)")
    ap.add_argument("--force", action="store_true", help="optimize: 이미 스키마 2 여도 다시 쓴다")
    ap.add_argument("--depth", type=int, default=0, help="bases·derived·overrides: 따라갈 단계 (0 = 끝까지)")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--target", default=None)
    ap.add_argument("--platform", default="Win64")
    ap.add_argument("--config", default="Development")
    ap.add_argument("--ubt", default=None)
    ap.add_argument("--codegen", default="auto", choices=["auto", "on", "off"],
                    help="cdb: UBT 의 코드 생성(UHT). auto = 돌리고 실패하면 건너뛰고 다시, on = 다시 안 함, off = 처음부터 건너뜀 "
                         "(-NoExecCodeGenActions, UE 5.4+ — 마지막 에디터 빌드의 .generated.h 를 쓴다)")
    ap.add_argument("--compiler", default="Default",
                    help="cdb (Win64): UBT -Compiler=. Default = 평소 빌드 컴파일러(보통 MSVC), Clang = clang-cl (VS 의 Clang 구성 요소 필요), "
                         "VisualStudio2022 등. 빈 값이면 넘기지 않는다 (UBT 가 Clang 을 강제)")
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
    if a.command == "optimize":
        done = optimize(root, kind, a.force)
        print("조회용 모양: " + (" · ".join(done) if done else "이미 맞다 (스키마 %d, 소유권 표시 최신)" % SCHEMA_VERSION))
        return 0
    return cmd_query(a, root, kind)


if __name__ == "__main__":
    sys.exit(main())
