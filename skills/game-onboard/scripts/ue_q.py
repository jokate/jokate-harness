#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UE 엔진 소스 조회기.

인덱스는 엔진 설치 경로별로 `~/.claude/cache/ue_index/<엔진경로>/ue.sqlite` 에 하나만 둔다.
같은 엔진을 쓰는 프로젝트끼리 공유한다. 파생물이다. 지우고 다시 만들 수 있다.
저장하는 것은 좌표(어느 심볼이 어느 파일 몇 줄에 있는가)와 모듈 관계뿐이다.
엔진 헤더를 통째로 읽지 않으려고 만든 도구다 — 출력은 기본 4KB 에서 끊는다.

사용:
  python ue_q.py index [--force] [--quiet]
  python ue_q.py status
  python ue_q.py sym UAnimSequence            # 심볼 좌표 (정확 → 부분)
  python ue_q.py decl UAnimSequence [--max 150]   # 선언 블록
  python ue_q.py api UAnimSequence            # 멤버 함수 시그니처 + UPROPERTY
  python ue_q.py file AnimSequence.h          # 파일 경로 찾기
  python ue_q.py get Source/.../AnimSequence.h:200-260
  python ue_q.py module ControlRig
  python ue_q.py deps ControlRig [--reverse]
  python ue_q.py rg "OnAnimNotify" --module Engine --type h
  python ue_q.py find MetaSound

엔진 루트: env UE_ROOT > 이 프로젝트용으로 저장한 경로 > <프로젝트>.uproject EngineAssociation + 레지스트리 > C:/Unreal/UE_5.7/Engine
  저장: index_all.py --engine-root <엔진 폴더> (index_build.bat 은 못 찾으면 묻는다) → ~/.claude/cache/game-harness/engine_roots.json
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

DEFAULT_ENGINE = "C:/Unreal/UE_5.7/Engine"
CACHE_ROOT = Path.home() / ".claude" / "cache" / "ue_index"
TOOL_VERSION = 1
CAP = 4000
SKIP_DIRS = {"ThirdParty", "Programs", "Intermediate", "Binaries", ".git"}
PLUGIN_SKIP_DIRS = {"Content", "Resources", "Config"}
SOURCE_DOMAINS = ("Runtime", "Editor", "Developer")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


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


def uproject(project):
    return next(iter(sorted(project.glob("*.uproject"))), None)


def find_project(start):
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if uproject(cand):
            return cand
    return None


def engine_roots_path():
    """프로젝트별로 저장한 엔진 경로. 머신마다 다른 값이라 프로젝트 폴더(VCS)가 아니라 홈에 둔다."""
    return Path.home() / ".claude" / "cache" / "game-harness" / "engine_roots.json"


def _project_key(project):
    return os.path.normcase(str(Path(project).resolve()))


def as_engine_dir(text):
    """사용자가 준 경로 → 엔진 폴더(…/Engine). UE_5.7 과 UE_5.7/Engine 둘 다 받는다. 엔진이 아니면 None.
    Source 만 보면 프로젝트 폴더도 통과하므로 Source/Runtime 을 본다."""
    text = (text or "").strip().strip('"').strip()
    if not text:
        return None
    p = Path(text).expanduser()
    for c in (p, p / "Engine"):
        if (c / "Source" / "Runtime").is_dir():
            return c.resolve()
    return None


def _saved_roots():
    try:
        data = json.loads(engine_roots_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_engine_root(project, eng):
    data = _saved_roots()
    data[_project_key(project)] = str(eng)
    path = engine_roots_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    engine_source.cache_clear()


def engine_root(project):
    return engine_source(project)[0]


@lru_cache(maxsize=None)
def engine_source(project):
    """(엔진 폴더, 어디서 찾았나) — 어디서: UE_ROOT · 저장 · 레지스트리 · 기본값."""
    env = os.environ.get("UE_ROOT")
    if env:
        p = Path(env)
        for c in (p, p / "Engine"):
            if (c / "Source").is_dir():
                return c, "UE_ROOT"
    saved = _saved_roots().get(_project_key(project)) if project else None
    if saved and (Path(saved) / "Source").is_dir():
        return Path(saved), "저장"
    try:
        ver = json.loads(uproject(project).read_text(encoding="utf-8"))["EngineAssociation"]
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\EpicGames\Unreal Engine\%s" % ver) as k:
            p = Path(winreg.QueryValueEx(k, "InstalledDirectory")[0]) / "Engine"
            if (p / "Source").is_dir():
                return p, "레지스트리"
    except Exception:
        pass
    return Path(DEFAULT_ENGINE), "기본값"


# ---------------------------------------------------------------- parsing

API = r"(?:([A-Z][A-Z0-9_]*_API)\s+)?"
DEPR = r"(?:UE_DEPRECATED\([^)]*\)\s*)?"
DECL = re.compile(
    r"^\s*(?:template\s*<[^>]*>\s*)?(class|struct)\s+" + DEPR + API + DEPR +
    r"(?:alignas\([^)]*\)\s+)?([A-Za-z_]\w*)\s*(?:final\s*)?(?::(?!:)\s*([^{]*)|\{|$)")
ENUM = re.compile(r"^\s*enum\s+(?:class\s+|struct\s+)?" + DEPR + r"([A-Za-z_]\w*)\s*(?::(?!:)|\{|$)")
MACRO = re.compile(r"^\s*(UCLASS|USTRUCT|UENUM|UINTERFACE)\b(.*)")
DELEGATE = re.compile(r"^\s*(DECLARE_(?:\w+_)?DELEGATE\w*|DECLARE_EVENT\w*)\s*\(([^)]*)")
IDENT = re.compile(r"[A-Za-z_]\w*")
BASE = re.compile(r"(?:(?:public|protected|private|virtual)\s+)*([A-Za-z_]\w*)")
QUICK = ("class ", "struct ", "enum ", "template", "UCLASS", "USTRUCT", "UENUM",
         "UINTERFACE", "DECLARE_")
MACRO_KIND = {"UCLASS": "uclass", "USTRUCT": "ustruct", "UENUM": "uenum",
              "UINTERFACE": "interface"}


def parse_header(abs_path):
    """헤더 한 개 → [(name, kind, line, api, parent)]. 선언만 본다. 본문은 파지 않는다."""
    try:
        with open(abs_path, "rb") as f:
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return abs_path, []
    out = []
    pending = None
    pending_api = ""
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.lstrip()
        if not s.startswith(QUICK):
            continue
        m = MACRO.match(s)
        if m:
            pending = MACRO_KIND[m.group(1)]
            pending_api = "MinimalAPI" if "MinimalAPI" in m.group(2) else ""
            continue
        rs = s.rstrip()
        m = DECL.match(s)
        if m:
            if rs.endswith(";") and "{" not in rs:
                continue
            kind = pending or m.group(1)
            if pending == "uclass" and m.group(1) == "struct":
                kind = "struct"
            parent = ""
            if m.group(4):
                b = BASE.match(m.group(4).strip())
                parent = b.group(1) if b else ""
            out.append((m.group(3), kind, lineno, m.group(2) or pending_api, parent))
            pending = None
            pending_api = ""
            continue
        m = ENUM.match(s)
        if m:
            if rs.endswith(";") and "{" not in rs:
                continue
            out.append((m.group(1), pending if pending == "uenum" else "enum", lineno, "", ""))
            pending = None
            pending_api = ""
            continue
        m = DELEGATE.match(s)
        if m:
            macro = m.group(1)
            args = [a.strip() for a in m.group(2).split(",")]
            idx = 1 if ("RetVal" in macro or macro.startswith("DECLARE_EVENT")) else 0
            if len(args) > idx and IDENT.fullmatch(args[idx]):
                out.append((args[idx], "delegate", lineno, "", macro))
            continue
        if s.startswith(("class ", "struct ", "enum ")):
            pending = None
            pending_api = ""
    return abs_path, out


DEPS = re.compile(r"(Public|Private)DependencyModuleNames\s*\.\s*(?:AddRange|Add)\s*\(")
STR = re.compile(r'"([A-Za-z0-9_]+)"')


def parse_buildcs(abs_path):
    try:
        text = Path(abs_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []
    deps = {"Public": [], "Private": []}
    for m in DEPS.finditer(text):
        depth = 1
        i = m.end()
        while i < len(text) and depth:
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            i += 1
        for n in STR.findall(text[m.end():i]):
            if n not in deps[m.group(1)]:
                deps[m.group(1)].append(n)
    return deps["Public"], deps["Private"]


# ---------------------------------------------------------------- walking

def walk_engine(eng):
    """(rel_path, kind, size, mtime, module, module_dir) 를 낸다. 모듈은 가장 가까운 Build.cs."""
    roots = [eng / "Source" / d for d in SOURCE_DOMAINS] + [eng / "Plugins"]
    for top in roots:
        if not top.is_dir():
            continue
        in_plugins = top.name == "Plugins"
        stack = [(top, None, None)]
        while stack:
            d, module, module_dir = stack.pop()
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            rel_dir = d.relative_to(eng).as_posix()
            in_source = not in_plugins or "/Source/" in rel_dir + "/"
            files = []
            subdirs = []
            for e in entries:
                if e.is_dir(follow_symlinks=False):
                    if e.name in SKIP_DIRS or (not in_source and e.name in PLUGIN_SKIP_DIRS):
                        continue
                    subdirs.append(e)
                elif e.name.endswith((".h", ".cpp", ".Build.cs")):
                    files.append(e)
            for e in files:
                if e.name.endswith(".Build.cs"):
                    module = e.name[:-len(".Build.cs")]
                    module_dir = d
                    break
            if not in_source:
                for e in subdirs:
                    stack.append((Path(e.path), module, module_dir))
                continue
            for e in files:
                try:
                    st = e.stat()
                except OSError:
                    continue
                kind = "buildcs" if e.name.endswith(".cs") else e.name.rsplit(".", 1)[1]
                yield (rel_dir + "/" + e.name, kind, st.st_size, int(st.st_mtime),
                       module or "", module_dir)
            for e in subdirs:
                stack.append((Path(e.path), module, module_dir))


def domain_of(rel):
    parts = rel.split("/")
    if parts[0] == "Source" and len(parts) > 1:
        return parts[1], ""
    if parts[0] == "Plugins" and "Source" in parts:
        return "Plugin", parts[parts.index("Source") - 1]
    return "", ""


# ---------------------------------------------------------------- db

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
  id INTEGER PRIMARY KEY, path TEXT UNIQUE, module TEXT, kind TEXT, size INTEGER, mtime INTEGER);
CREATE TABLE IF NOT EXISTS modules(
  name TEXT PRIMARY KEY COLLATE NOCASE, path TEXT, domain TEXT, plugin TEXT,
  deps_public TEXT, deps_private TEXT);
CREATE TABLE IF NOT EXISTS symbols(
  name TEXT COLLATE NOCASE, kind TEXT, file_id INTEGER, line INTEGER, api TEXT, parent TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS symbols_name ON symbols(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS symbols_file ON symbols(file_id);
CREATE INDEX IF NOT EXISTS symbols_parent ON symbols(parent COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS files_module ON files(module);
"""


def db_path(project):
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", str(engine_root(project)).strip("/\\"))
    return CACHE_ROOT / key / "ue.sqlite"


def open_db(project, create=False):
    p = db_path(project)
    if not p.exists() and not create:
        print("인덱스 없음. `python ue_q.py index` 를 먼저 돌려라.")
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.executescript(SCHEMA)
    return con


def meta_get(con, key, default=None):
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def cmd_index(project, eng, force, quiet):
    t0 = time.time()
    if not (eng / "Source").is_dir():
        print("엔진 루트가 아니다: %s (index_build.bat --engine-root <엔진 폴더> 로 저장하거나 UE_ROOT 로 지정)" % eng, file=sys.stderr)
        return 1
    con = open_db(project, create=True)
    if force or meta_get(con, "engine_root") not in (None, str(eng)):
        con.executescript("DELETE FROM symbols; DELETE FROM files; DELETE FROM modules;")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA journal_mode=MEMORY")

    old = {r[0]: (r[1], r[2], r[3]) for r in
           con.execute("SELECT path, id, size, mtime FROM files")}
    seen = set()
    to_parse = []
    to_build = []
    changed_rows = []
    for rel, kind, size, mtime, module, mdir in walk_engine(eng):
        seen.add(rel)
        prev = old.get(rel)
        if prev and prev[1] == size and prev[2] == mtime:
            continue
        changed_rows.append((rel, module, kind, size, mtime))
        if kind == "h":
            to_parse.append(rel)
        elif kind == "buildcs":
            to_build.append((rel, module, mdir))
    gone = [p for p in old if p not in seen]

    cur = con.cursor()
    if gone:
        cur.executemany("DELETE FROM symbols WHERE file_id=?", [(old[p][0],) for p in gone])
        cur.executemany("DELETE FROM files WHERE path=?", [(p,) for p in gone])
    cur.executemany(
        "INSERT INTO files(path, module, kind, size, mtime) VALUES(?,?,?,?,?) "
        "ON CONFLICT(path) DO UPDATE SET module=excluded.module, kind=excluded.kind, "
        "size=excluded.size, mtime=excluded.mtime", changed_rows)
    ids = {r[0]: r[1] for r in cur.execute("SELECT path, id FROM files")}
    if to_parse:
        cur.executemany("DELETE FROM symbols WHERE file_id=?", [(ids[p],) for p in to_parse])

    for rel, module, mdir in to_build:
        pub, pri = parse_buildcs(eng / rel)
        domain, plugin = domain_of(rel)
        cur.execute("INSERT OR REPLACE INTO modules VALUES(?,?,?,?,?,?)",
                    (module, mdir.relative_to(eng).as_posix(), domain, plugin,
                     "," + ",".join(pub) + ",", "," + ",".join(pri) + ","))

    n_sym = 0
    abs_paths = [str(eng / p) for p in to_parse]
    if len(abs_paths) > 300:
        pool = Pool(max(2, (os.cpu_count() or 4) // 2))
        results = pool.imap_unordered(parse_header, abs_paths, chunksize=64)
    else:
        pool = None
        results = map(parse_header, abs_paths)
    batch = []
    for abs_path, syms in results:
        rel = Path(abs_path).relative_to(eng).as_posix()
        fid = ids[rel]
        batch.extend((n, k, fid, ln, api, parent) for n, k, ln, api, parent in syms)
        if len(batch) > 20000:
            cur.executemany("INSERT INTO symbols VALUES(?,?,?,?,?,?)", batch)
            n_sym += len(batch)
            batch = []
    if batch:
        cur.executemany("INSERT INTO symbols VALUES(?,?,?,?,?,?)", batch)
        n_sym += len(batch)
    if pool:
        pool.close()
        pool.join()

    counts = {
        "files": cur.execute("SELECT COUNT(*) FROM files").fetchone()[0],
        "headers": cur.execute("SELECT COUNT(*) FROM files WHERE kind='h'").fetchone()[0],
        "modules": cur.execute("SELECT COUNT(*) FROM modules").fetchone()[0],
        "symbols": cur.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
    }
    elapsed = time.time() - t0
    for k, v in (("engine_root", str(eng)), ("tool_version", TOOL_VERSION),
                 ("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                 ("elapsed", "%.1f" % elapsed), ("counts", json.dumps(counts))):
        cur.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, str(v)))
    con.commit()
    if force or len(changed_rows) > 1000:
        con.execute("VACUUM")
    con.close()
    harness_emit("index.engine", "%s · 헤더 %d · 심볼 %d · 변경 %d [%.1fs]"
                 % (eng, counts["headers"], counts["symbols"], len(changed_rows), elapsed), project=project)
    if not quiet:
        print("색인 완료 [%.1fs] 파일 %d(헤더 %d) · 모듈 %d · 심볼 %d"
              % (elapsed, counts["files"], counts["headers"], counts["modules"], counts["symbols"]))
        print("  변경 %d(헤더 재파싱 %d, 심볼 %d) · 삭제 %d · db %s"
              % (len(changed_rows), len(to_parse), n_sym, len(gone), kb(db_path(project).stat().st_size)))
    return 0


def cmd_status(project, eng):
    con = open_db(project)
    if con is None:
        return 1
    counts = json.loads(meta_get(con, "counts", "{}"))
    root = meta_get(con, "engine_root")
    print("인덱스: %s [%ss] · 파일 %s(헤더 %s) · 모듈 %s · 심볼 %s · db %s"
          % (meta_get(con, "generated_at"), meta_get(con, "elapsed"), counts.get("files"),
             counts.get("headers"), counts.get("modules"), counts.get("symbols"),
             kb(db_path(project).stat().st_size)))
    print("엔진: %s%s" % (root, "" if root == str(eng) else "  [현재 해석 결과와 다름: %s]" % eng))
    print("파일 변경 감지는 index 로만 한다 (size+mtime 증분).")
    return 0


# ---------------------------------------------------------------- output

def kb(n):
    return "%.1fKB" % (n / 1024.0) if n >= 1024 else "%dB" % n


def emit(lines, full=False, cap=CAP, hint="--full"):
    used = 0
    for i, ln in enumerate(lines):
        b = len(ln.encode("utf-8", "replace")) + 1
        if not full and used + b > cap:
            print("… (+%d more lines, use %s)" % (len(lines) - i, hint))
            return
        print(ln)
        used += b


def read_lines(eng, rel):
    try:
        with open(eng / rel, "rb") as f:
            return f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None


# ---------------------------------------------------------------- queries

SYM_SQL = ("SELECT s.name, s.kind, f.module, f.path, s.line, s.api, s.parent "
           "FROM symbols s JOIN files f ON f.id=s.file_id ")
KIND_PREF = {"uclass": 0, "interface": 1, "class": 2, "ustruct": 3, "struct": 4,
             "uenum": 5, "enum": 6, "delegate": 7}


def sym_rows(con, name, substring=True, limit=200, path_filter=None):
    rows = con.execute(SYM_SQL + "WHERE s.name=? COLLATE NOCASE", (name,)).fetchall()
    if not rows and substring:
        rows = con.execute(SYM_SQL + "WHERE s.name LIKE ? LIMIT ?",
                           ("%" + name + "%", limit * 4)).fetchall()
    if path_filter:
        pf = path_filter.lower()
        rows = [r for r in rows if pf in r[3].lower()]
    rows.sort(key=lambda r: (r[0] != name, len(r[0]), KIND_PREF.get(r[1], 9), r[3]))
    return rows


def fmt_sym(r):
    name, kind, module, path, line, api, parent = r
    tail = ("  : " + parent) if parent and kind != "delegate" else ""
    if kind == "delegate":
        tail = "  " + parent
    return "%-9s %-36s %-22s %s:%d%s" % (kind, name, module, path, line, tail)


def cmd_sym(con, name, limit, full, path_filter):
    rows = sym_rows(con, name, path_filter=path_filter)
    if not rows:
        print("없음: %r" % name)
        return 0
    lines = [fmt_sym(r) for r in rows[:limit]]
    if len(rows) > limit:
        lines.append("… (+%d more, --limit N)" % (len(rows) - limit))
    emit(lines, full, hint="--limit N / --full")
    return 0


def pick_symbol(con, name, path_filter):
    rows = [r for r in sym_rows(con, name, substring=False, path_filter=path_filter)]
    if not rows:
        rows = sym_rows(con, name, path_filter=path_filter)
        if not rows:
            print("없음: %r" % name)
            return None, []
        exact = [r for r in rows if r[0].lower() == name.lower()]
        if not exact:
            print("정확히 일치하는 심볼이 없다. 후보:")
            emit([fmt_sym(r) for r in rows[:12]])
            return None, []
        rows = exact
    return rows[0], rows[1:]


BLOCK_CMT = re.compile(r"/\*.*?\*/")
LINE_CMT = re.compile(r"//.*$")
STRINGS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


def clean_code(line, in_cmt):
    """주석·문자열을 비운 코드만 남긴다. 중괄호 세기 용도라 대충이면 된다."""
    out = []
    i = 0
    while i < len(line):
        if in_cmt:
            j = line.find("*/", i)
            if j < 0:
                return "".join(out), True
            i = j + 2
            in_cmt = False
            continue
        j = line.find("/*", i)
        k = line.find("//", i)
        if k >= 0 and (j < 0 or k < j):
            out.append(line[i:k])
            break
        if j >= 0:
            out.append(line[i:j])
            i = j + 2
            in_cmt = True
            continue
        out.append(line[i:])
        break
    return STRINGS.sub('""', "".join(out)), in_cmt


def block_end(lines, start, max_scan=20000):
    """start(0-based) 선언 줄부터 닫는 중괄호 줄까지. (end_idx, found)"""
    depth = 0
    opened = False
    in_cmt = False
    for i in range(start, min(len(lines), start + max_scan)):
        code, in_cmt = clean_code(lines[i], in_cmt)
        if code.lstrip().startswith("#"):
            continue
        for c in code:
            if c == "{":
                depth += 1
                opened = True
            elif c == "}":
                depth -= 1
        if opened and depth <= 0:
            return i, True
        if not opened and (code.rstrip().endswith(";") or i - start > 6):
            return i if code.rstrip().endswith(";") else start, False
    return min(len(lines) - 1, start + max_scan - 1), False


def decl_block(eng, row):
    lines = read_lines(eng, row[3])
    if lines is None:
        return None, None, None
    start = row[4] - 1
    # UCLASS/USTRUCT 매크로 줄이 바로 위에 있으면 같이 낸다
    if start > 0 and MACRO.match(lines[start - 1]):
        start -= 1
    end, _ = block_end(lines, row[4] - 1)
    return lines, start, end


def cmd_decl(con, eng, name, max_lines, full, path_filter):
    row, others = pick_symbol(con, name, path_filter)
    if row is None:
        return 1
    lines, start, end = decl_block(eng, row)
    if lines is None:
        print("파일을 못 읽었다: %s" % row[3])
        return 1
    head = ["# %s %s  %s  %s:%d-%d  (%d lines)"
            % (row[1], row[0], row[2], row[3], start + 1, end + 1, end - start + 1)]
    if others:
        head.append("# 같은 이름 %d개 더: %s  (--path 로 고른다)"
                    % (len(others), ", ".join("%s:%d" % (o[3], o[4]) for o in others[:3])))
    body = ["%5d  %s" % (i + 1, lines[i].rstrip()) for i in range(start, end + 1)]
    if len(body) > max_lines:
        cut = len(body) - max_lines
        body = body[:max_lines] + ["… (+%d lines to closing brace at %d; --max N)" % (cut, end + 1)]
    emit(head + body, full, hint="--full (줄 수는 --max N)")
    return 0


UMETA = re.compile(r",?\s*meta\s*=\s*\((?:[^()]|\([^()]*\))*\)")
API_TOK = re.compile(r"\b[A-Z][A-Z0-9_]*_API\b\s*")
SPEC = re.compile(r"^\s*(public|protected|private)\s*:\s*$")
SKIP_START = ("GENERATED_", "UE_DEPRECATED", "UE_NONCOPYABLE", "DECLARE_", "friend ",
              "typedef ", "using ", "static_assert", "#", "//", "/*", "*")


def compact(s):
    s = API_TOK.sub("", s)
    return " ".join(s.split())


def sig(tag, s):
    """선언 한 줄로 압축. 본문이 붙어 있거나 ';' 가 없으면 {…} 로 표시."""
    head = s.split("{", 1)[0].rstrip()
    return tag + compact(head) + ("" if head.endswith(";") else " {…}")


def cmd_api(con, eng, name, full, path_filter):
    row, others = pick_symbol(con, name, path_filter)
    if row is None:
        return 1
    lines, start, end = decl_block(eng, row)
    if lines is None:
        print("파일을 못 읽었다: %s" % row[3])
        return 1
    out = ["# %s %s  %s  %s:%d-%d%s"
           % (row[1], row[0], row[2], row[3], start + 1, end + 1,
              ("  : " + row[6]) if row[6] else "")]
    if others:
        out.append("# 같은 이름 %d개 더 (--path 로 고른다)" % len(others))
    depth = 0
    in_cmt = False
    tag = ""
    tag_depth = 0
    acc = ""
    acc_depth = 0
    for i in range(row[4] - 1, end + 1):
        raw = lines[i]
        code, in_cmt = clean_code(raw, in_cmt)
        s = code.strip()
        disp = BLOCK_CMT.sub("", LINE_CMT.sub("", raw)).strip() if s else ""
        opens = code.count("{")
        closes = code.count("}")
        if depth == 1 and s:
            if acc:
                acc = acc + " " + disp
                acc_depth += code.count("(") - code.count(")")
                if acc_depth <= 0:
                    out.append(sig(tag, acc))
                    acc = ""
                    tag = ""
            elif tag_depth > 0:
                tag += " " + disp
                tag_depth += s.count("(") - s.count(")")
                if tag_depth <= 0:
                    tag = compact(UMETA.sub("", tag)) + " "
            elif SPEC.match(s):
                out.append(s.replace(" ", ""))
            elif s.startswith(("UPROPERTY", "UFUNCTION")):
                tag = disp
                tag_depth = s.count("(") - s.count(")")
                if tag_depth <= 0:
                    tag = compact(UMETA.sub("", tag)) + " "
            elif s.startswith(SKIP_START):
                pass
            elif s.startswith(("struct ", "class ", "enum ", "union ")) and "{" in code:
                out.append(compact(disp.split("{")[0]) + " {…}")
            elif "(" in s and s.count("(") > s.count(")"):
                acc = disp
                acc_depth = s.count("(") - s.count(")")
            elif "(" in s or tag:
                out.append(sig(tag, disp))
                tag = ""
        depth += opens - closes
        if i > row[4] - 1 and depth <= 0 and (opens or closes):
            break
    emit(out, full, hint="--full")
    return 0


def cmd_file(con, frag, limit, full):
    rows = con.execute(
        "SELECT path, kind, size, module FROM files WHERE path LIKE ? ORDER BY length(path) LIMIT ?",
        ("%" + frag + "%", limit + 1)).fetchall()
    if not rows:
        print("없음: %r" % frag)
        return 0
    lines = ["%-7s %8s  %-22s %s" % (r[1], kb(r[2]), r[3], r[0]) for r in rows[:limit]]
    if len(rows) > limit:
        lines.append("… (+more, --limit N)")
    emit(lines, full, hint="--limit N / --full")
    return 0


def resolve_path(con, eng, p):
    p = p.replace("\\", "/")
    ep = str(eng).replace("\\", "/")
    if p.lower().startswith(ep.lower() + "/"):
        p = p[len(ep) + 1:]
    if (eng / p).is_file():
        return p, None
    rows = con.execute("SELECT path FROM files WHERE path LIKE ? LIMIT 6", ("%" + p,)).fetchall()
    if len(rows) == 1:
        return rows[0][0], None
    if not rows:
        return None, "파일 없음: %r" % p
    return None, "여럿이다 — 더 좁혀라: " + ", ".join(r[0] for r in rows)


def cmd_get(con, eng, ref, full):
    m = re.match(r"^(.*?):(\d+)(?:-(\d+))?$", ref)
    if not m:
        print("형식: get <path>:<start>-<end>  (최대 200줄)")
        return 1
    rel, err = resolve_path(con, eng, m.group(1))
    if err:
        print(err)
        return 1
    a = int(m.group(2))
    b = int(m.group(3)) if m.group(3) else a + 40
    if b - a + 1 > 200:
        b = a + 199
        note = "  (200줄에서 끊음)"
    else:
        note = ""
    lines = read_lines(eng, rel)
    if lines is None:
        print("파일을 못 읽었다: %s" % rel)
        return 1
    b = min(b, len(lines))
    out = ["# %s:%d-%d  (파일 %d줄)%s" % (rel, a, b, len(lines), note)]
    out += ["%5d  %s" % (i, lines[i - 1].rstrip()) for i in range(a, b + 1)]
    emit(out, full)
    return 0


def module_row(con, name):
    r = con.execute("SELECT * FROM modules WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if r:
        return r, []
    rows = con.execute("SELECT * FROM modules WHERE name LIKE ? ORDER BY length(name) LIMIT 20",
                       ("%" + name + "%",)).fetchall()
    return (rows[0], rows[1:]) if rows else (None, [])


def deps_list(s):
    return [x for x in s.split(",") if x]


def wrap(prefix, names, width=110):
    """긴 목록은 줄로 쪼갠다 — 바이트 상한에서 통째로 잘려나가지 않게."""
    out = []
    cur = prefix
    for n in names:
        piece = n + ", "
        if len(cur) + len(piece) > width and cur != prefix:
            out.append(cur.rstrip())
            cur = " " * len(prefix)
        cur += piece
    out.append(cur.rstrip(", "))
    return out


def cmd_module(con, name, full):
    r, others = module_row(con, name)
    if r is None:
        print("없음: %r" % name)
        return 0
    n_h, n_cpp = con.execute(
        "SELECT SUM(kind='h'), SUM(kind='cpp') FROM files WHERE module=?", (r[0],)).fetchone()
    out = ["%s  [%s%s]  %s  (h %s · cpp %s)"
           % (r[0], r[2], ("/" + r[3]) if r[3] else "", r[1], n_h or 0, n_cpp or 0)]
    out += wrap("public : ", deps_list(r[4]))
    out += wrap("private: ", deps_list(r[5]))
    if others:
        out += wrap("비슷한 이름: ", [o[0] for o in others[:12]])
    emit(out, full)
    return 0


def cmd_deps(con, name, reverse, full):
    r, _ = module_row(con, name)
    if r is None:
        print("없음: %r" % name)
        return 0
    if not reverse:
        out = wrap("%s → public : " % r[0], deps_list(r[4]))
        out += wrap("%s → private: " % r[0], deps_list(r[5]))
        emit(out, full)
        return 0
    pat = "%," + r[0] + ",%"
    rows = con.execute(
        "SELECT name, domain, plugin, deps_public LIKE ? FROM modules "
        "WHERE deps_public LIKE ? OR deps_private LIKE ? ORDER BY domain, name",
        (pat, pat, pat)).fetchall()
    out = ["%s ← %d modules" % (r[0], len(rows))]
    by = {}
    for n, dom, plug, pub in rows:
        by.setdefault(dom, []).append(n + ("" if pub else "(priv)"))
    for dom, names in by.items():
        out += wrap("[%s] " % dom, names)
    emit(out, full)
    return 0


def find_rg():
    """(argv 머리, env). rg 가 PATH 에 없으면 Claude Code 가 품은 ripgrep 을 ARGV0=rg 로 부른다."""
    import shutil
    env = dict(os.environ)
    p = os.environ.get("RG_PATH") or shutil.which("rg")
    if p and Path(p).is_file():
        return [p], env
    for cand in (os.environ.get("CLAUDE_CODE_EXECPATH"),
                 str(Path.home() / ".local" / "bin" / "claude.exe"),
                 str(Path.home() / ".local" / "bin" / "claude")):
        if cand and Path(cand).is_file():
            env["ARGV0"] = "rg"
            return [cand], env
    return None, env


def cmd_rg(con, eng, pattern, module, path, ftype, limit, full):
    rg, env = find_rg()
    if rg is None:
        print("rg 를 못 찾았다. RG_PATH 로 ripgrep 실행 파일을 지정해라.")
        return 1
    targets = []
    if module:
        r, _ = module_row(con, module)
        if r is None:
            print("모듈 없음: %r" % module)
            return 1
        targets = [r[1]]
    elif path:
        targets = [path.replace("\\", "/")]
    else:
        targets = ["Source/" + d for d in SOURCE_DOMAINS] + ["Plugins"]
    cmd = rg + ["-n", "--no-heading", "-i", "--color", "never", "-M", "300",
           "-g", "!**/ThirdParty/**", "-g", "!**/Intermediate/**", "-g", "!**/Binaries/**",
           "-g", "!**/Programs/**"]
    if ftype in ("h", "cpp"):
        cmd += ["-g", "*." + ftype]
    else:
        cmd += ["-g", "*.{h,cpp,inl,cs}"]
    if not module and not path:
        cmd += ["-g", "!Plugins/**/Content/**"]
    cmd += ["-e", pattern, "--"] + targets
    try:
        proc = subprocess.Popen(cmd, cwd=str(eng), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (FileNotFoundError, OSError):
        print("rg 를 못 찾았다.")
        return 1
    out = []
    extra = 0
    for bline in proc.stdout:
        line = bline.decode("utf-8", "replace").rstrip("\r\n")
        if len(out) < limit:
            p, _, rest = line.partition(":")
            out.append((p.replace("\\", "/") + ":" + rest)[:220])
        else:
            extra += 1
            if extra > 2000:
                break
    proc.stdout.close()
    proc.kill()
    proc.wait()
    if not out:
        print("없음: %r" % pattern)
        return 0
    if extra:
        out.append("… (+%d%s more, --limit N / --module / --type)" % (extra, "+" if extra > 2000 else ""))
    emit(out, full, hint="--limit N / --full")
    return 0


def cmd_find(con, q, full):
    like = "%" + q + "%"
    out = []
    syms = con.execute(SYM_SQL + "WHERE s.name LIKE ? LIMIT 400", (like,)).fetchall()
    if syms:
        syms.sort(key=lambda r: (r[0].lower() != q.lower(), len(r[0]), KIND_PREF.get(r[1], 9)))
        out.append("[심볼] %d" % len(syms))
        out += ["  " + fmt_sym(r) for r in syms[:15]]
    mods = con.execute("SELECT name, domain, plugin, path FROM modules WHERE name LIKE ? "
                       "ORDER BY length(name) LIMIT 40", (like,)).fetchall()
    if mods:
        out.append("[모듈] %d: " % len(mods) + ", ".join(
            "%s(%s)" % (m[0], m[2] or m[1]) for m in mods[:12]))
    files = con.execute("SELECT path FROM files WHERE path LIKE ? AND kind!='cpp' "
                        "ORDER BY length(path) LIMIT 60", (like,)).fetchall()
    files = [f[0] for f in files if q.lower() in f[0].rsplit("/", 1)[-1].lower()]
    if files:
        out.append("[파일] %d" % len(files))
        out += ["  " + f for f in files[:10]]
    if not out:
        print("없음: %r" % q)
        return 0
    out.append("다음: decl <심볼> · api <심볼> · get <path>:<a>-<b>")
    emit(out, full)
    return 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="UE 엔진 소스 조회기")
    ap.add_argument("command", choices=["index", "status", "sym", "decl", "api", "file",
                                        "get", "module", "deps", "rg", "find"])
    ap.add_argument("arg", nargs="*", default=[])
    ap.add_argument("--root", default=".")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--full", action="store_true", help="4KB 출력 상한을 푼다")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--max", type=int, default=150, help="decl: 최대 줄 수")
    ap.add_argument("--path", default=None, help="decl/api/sym: 경로 조각으로 후보를 좁힌다 · rg: 검색 경로")
    ap.add_argument("--module", default=None, help="rg: 모듈 디렉터리로 한정")
    ap.add_argument("--type", default=None, choices=["h", "cpp"])
    ap.add_argument("--reverse", action="store_true", help="deps: 이 모듈에 의존하는 모듈")
    args = ap.parse_args()
    arg = " ".join(args.arg).strip() or None

    project = find_project(args.root)
    if project is None:
        if args.quiet:
            return 0
        raise SystemExit(".uproject 를 못 찾았다. --root 로 프로젝트 루트를 줘라.")
    eng = engine_root(project)
    try:
        assoc = json.loads(uproject(project).read_text(encoding="utf-8")).get("EngineAssociation", "")
    except (OSError, ValueError):
        assoc = ""
    if re.fullmatch(r"\d+\.\d+", assoc) and ("_%s" % assoc) not in str(eng) and engine_source(project)[1] not in ("UE_ROOT", "저장"):
        print("[경고] 프로젝트는 UE %s 인데 %s 로 조회한다 (해당 버전 미설치?). "
              "버전별로 다른 API 는 '확인 필요'로 쓰고, 설치돼 있으면 index_build.bat --engine-root 또는 UE_ROOT 로 지정." % (assoc, eng))
        harness_emit("index.engine.warn", "프로젝트 UE %s ≠ 조회 엔진 %s" % (assoc, eng), ok=False, project=project)

    if args.command == "index":
        return cmd_index(project, eng, args.force, args.quiet)
    if args.command == "status":
        return cmd_status(project, eng)
    if arg is None:
        raise SystemExit("%s 는 인자가 필요하다." % args.command)
    if not db_path(project).exists():
        print("[엔진 인덱스 없음 → 지금 만든다: %s]" % eng)
        if cmd_index(project, eng, False, True) != 0:
            return 1
    con = open_db(project)
    if con is None:
        return 1
    n_h = con.execute("SELECT COUNT(*) FROM files WHERE kind='h'").fetchone()[0]
    if n_h < 1000:
        print("[경고] 엔진 헤더가 %d개뿐이다 — %s 설치에 엔진 소스가 없다 (런처 설치 옵션 확인). "
              "'없음' 결과는 엔진에 없다는 뜻이 아니다." % (n_h, eng))
        harness_emit("index.engine.warn", "엔진 헤더 %d개 — 엔진 소스 없음 의심 (%s)" % (n_h, eng), ok=False, project=project)
    stored = meta_get(con, "engine_root")
    if stored and stored != str(eng):
        eng = Path(stored)
    c = args.command
    if c == "sym":
        return cmd_sym(con, arg, args.limit, args.full, args.path)
    if c == "decl":
        return cmd_decl(con, eng, arg, args.max, args.full, args.path)
    if c == "api":
        return cmd_api(con, eng, arg, args.full, args.path)
    if c == "file":
        return cmd_file(con, arg, args.limit, args.full)
    if c == "get":
        return cmd_get(con, eng, arg, args.full)
    if c == "module":
        return cmd_module(con, arg, args.full)
    if c == "deps":
        return cmd_deps(con, arg, args.reverse, args.full)
    if c == "rg":
        return cmd_rg(con, eng, arg, args.module, args.path, args.type, args.limit, args.full)
    return cmd_find(con, arg, args.full)


if __name__ == "__main__":
    sys.exit(main())
