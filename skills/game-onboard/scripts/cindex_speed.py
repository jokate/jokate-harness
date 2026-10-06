#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cindex.py 속도 보완 — 증분 색인(clangd 배경 색인 샤드)과 유니티 묶음. 표준 라이브러리만 쓴다.

근거 (references/indexing-research.md §5, 원본은 llvm-project clangd 소스):
  - 배경 색인은 파일마다 샤드(.idx)를 남기고, 다음 시작 때 내용 다이제스트가 바뀐 파일만 다시 색인한다
    (index/Background.cpp, BackgroundIndexLoader.cpp). 그래서 편집 한 번에 TU 하나 정도만 다시 돈다.
  - 그런데 clangd 는 세 가지를 놓친다 — 이 모듈이 메운다:
      1. 헤더가 바뀌면 그 헤더를 포함한 TU 중 **하나만** 다시 색인한다 (Background.cpp 의 FIXME).
         → 샤드의 include 그래프(+ 명령의 -include / /FI 강제 포함)로 포함한 TU 를 모두 찾아 그 샤드를 지운다.
      2. 컴파일 플래그가 바뀌어도 다시 색인하지 않는다 (BackgroundQueue.cpp: 다이제스트만 본다).
         → compile_commands 항목의 해시를 기억해 바뀐 TU 의 샤드를 지운다.
      3. 한 clangd 세션 안에서는 같은 파일을 다시 색인하지 않는다 (Background.h).
         → 갱신마다 clangd 를 새로 띄우고 색인이 끝나면 닫는다.
  - 유니티 묶음: .cpp 여러 개를 #include 하는 TU 하나로 묶으면 공용 헤더 파싱이 한 번으로 준다 (Chromium jumbo,
    UE 의 Module.*.cpp 와 같은 원리). 실험실(합성 프로젝트) 4~5.8배. 대신 파일 범위 심볼(익명 네임스페이스)이 빠질 수 있고,
    묶음 안 .cpp 하나를 고치면 묶음 전체를 다시 색인한다.
"""
import hashlib
import json
import os
import queue
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import clangd_riff

STATE_VERSION = 1


def npath(p):
    """비교용 경로: 절대·정규화, Windows 는 대소문자 무시."""
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def uri_path(uri):
    if not uri.startswith("file:"):
        return None
    p = unquote(urlparse(uri).path)
    if re.match(r"^/[A-Za-z]:", p):
        p = p[1:]
    return p


# ---------------------------------------------------------------- compile_commands

def entries_of(cdb_path):
    """compile_commands.json → [{file, directory, args}] (file 은 절대 경로). command 문자열이면 셸 규칙으로 나눈다."""
    out = []
    for e in json.loads(Path(cdb_path).read_text(encoding="utf-8")):
        d = e.get("directory") or "."
        if "arguments" in e:
            args = list(e["arguments"])
        else:
            cmd = e.get("command", "")
            args = shlex.split(cmd, posix=os.name != "nt")
            if os.name == "nt":
                args = [a[1:-1] if len(a) > 1 and a[0] == a[-1] == '"' else a for a in args]
        f = e["file"]
        f = f if os.path.isabs(f) else os.path.join(d, f)
        out.append({"file": os.path.normpath(f), "directory": d, "args": args})
    return out


def write_cdb(entries, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [{"directory": e["directory"], "file": e["file"], "arguments": e["args"]} for e in entries]
    text = json.dumps(data, indent=1)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return path


def filter_entries(entries, pattern):
    """clangd-indexer --filter 와 같은 뜻 (TU 경로에 정규식이 어디든 맞으면 포함). 배경 색인은 필터가 없어 여기서 거른다."""
    if not pattern:
        return entries
    rx = re.compile(pattern)
    return [e for e in entries if rx.search(e["file"])]


FORCED = ("-include", "-imacros", "/FI", "-FI", "--include")


def forced_includes(e):
    """명령의 강제 포함(-include X, /FI X, -FIX ...). 샤드 include 그래프에는 안 나온다 (전처리기 앞단에서 들어온다)."""
    out, args, i = [], e["args"], 0
    while i < len(args):
        a = args[i]
        val = None
        for f in FORCED:
            if a == f and i + 1 < len(args):
                val = args[i + 1]
                i += 1
                break
            if a.startswith(f + "=") and f.startswith("--"):
                val = a[len(f) + 1:]
                break
            if a.startswith(f) and len(a) > len(f) and f in ("/FI", "-FI", "-include"):
                val = a[len(f):]
                break
        if val:
            out.append(os.path.normpath(val if os.path.isabs(val) else os.path.join(e["directory"], val)))
        i += 1
    return out


def cmd_hash(e):
    return hashlib.sha1(json.dumps([e["directory"], e["args"]], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- 유니티 묶음

OUTPUT_FLAGS = ("-o", "-MF", "-MT", "-MQ", "/Fo", "-Fo", "/Fd", "/Fp")


def _flags_key(e):
    """묶을 수 있는지 판정용: 파일 자신과 출력 관련 인자를 뺀 나머지가 같아야 같은 묶음."""
    f, base, args, skip, out = npath(e["file"]), os.path.basename(e["file"]), e["args"], False, []
    for a in args[1:]:
        if skip:
            skip = False
            continue
        if a in OUTPUT_FLAGS:
            skip = True
            continue
        if a.startswith(OUTPUT_FLAGS) or a in ("-c", "--") or (os.path.isabs(a) and npath(a) == f) or a == base \
                or a.endswith(base) and npath(os.path.join(e["directory"], a)) == f:
            continue
        out.append(a)
    return json.dumps([e["directory"], args[0] if args else "", out])


def unity_entries(entries, per, work_dir, module_of, exclude=()):
    """같은 플래그·같은 모듈의 .cpp 를 per 개씩 묶은 TU 를 만든다. 반환: (새 항목, {묶음 파일: [원래 파일]}).
    플래그가 파일마다 다르면(예: TU 마다 다른 응답 파일) 묶이지 않고 그대로 간다. exclude(정규화 경로)는 묶지 않는다
    (묶었더니 오류가 난 파일들). 묶음 이름은 그룹 키 + 순번이라 한 그룹을 풀어도 다른 묶음 이름은 그대로다."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    groups = {}
    for e in entries:
        if npath(e["file"]) in exclude or not e["file"].lower().endswith((".cpp", ".cc", ".cxx", ".c++")):
            groups.setdefault(("single", e["file"]), []).append(e)
            continue
        groups.setdefault((_flags_key(e), module_of(e["file"])), []).append(e)
    out, members, keep = [], {}, set()
    for (key, mod), es in groups.items():
        if key == "single" or len(es) < 2:
            out.extend(es)
            continue
        es = sorted(es, key=lambda x: x["file"])
        for k in range(0, len(es), per):
            chunk = es[k:k + per]
            if len(chunk) == 1:
                out.extend(chunk)
                continue
            safe = re.sub(r"[^A-Za-z0-9_]+", "_", mod or "root")[:40]
            name = work_dir / f"Unity_{safe}_{hashlib.sha1(key.encode()).hexdigest()[:6]}_{k // per}.cpp"
            text = "// cindex.py 유니티 묶음 — 자동 생성, 고치지 않는다\n" + "".join(
                f'#include "{c["file"].replace(chr(92), "/")}"\n' for c in chunk)
            if not name.exists() or name.read_text(encoding="utf-8") != text:
                name.write_text(text, encoding="utf-8")
            keep.add(name.name)
            first = chunk[0]
            f0 = first["file"]
            args = [str(name) if (a == f0 or (os.path.isabs(a) and npath(a) == npath(f0))) else a for a in first["args"]]
            if str(name) not in args:
                args.append(str(name))
            out.append({"file": str(name), "directory": first["directory"], "args": args})
            members[str(name)] = [c["file"] for c in chunk]
    for old in work_dir.glob("Unity_*.cpp"):
        if old.name not in keep:
            old.unlink()
    return out, members


# ---------------------------------------------------------------- 샤드 그래프와 무효화

class ShardStore:
    """<cdb 폴더>/.cache/clangd/index/*.idx. 샤드마다 '자기 파일' 노드(다이제스트가 있는 노드)와 그 직접 include 를 읽는다.
    읽은 결과는 상태 파일에 샤드 mtime 과 같이 캐시해 바뀐 샤드만 다시 읽는다."""

    def __init__(self, cdb_dir, cache=None):
        self.dir = Path(cdb_dir) / ".cache" / "clangd" / "index"
        self.cache = dict(cache or {})
        self.own, self.includes, self.tus, self.errors = {}, {}, set(), set()

    def scan(self):
        seen = {}
        if self.dir.is_dir():
            for e in os.scandir(self.dir):
                if not e.name.endswith(".idx"):
                    continue
                st = e.stat()
                c = self.cache.get(e.name)
                if not c or c[0] != st.st_mtime_ns:
                    try:
                        x = clangd_riff.read(Path(e.path).read_bytes(), ("sources",))
                    except (OSError, ValueError, IndexError):
                        continue
                    node = next((s for s in x["sources"] if s[3] != "0000000000000000"), None)
                    if not node:
                        continue
                    p = uri_path(node[0])
                    c = [st.st_mtime_ns, p, node[1], node[2], [q for q in (uri_path(u) for u in node[4]) if q]]
                seen[e.name] = c
        self.cache = seen
        self.own, self.includes, self.tus, self.errors = {}, {}, set(), set()
        for name, (_, p, is_tu, had_err, incs) in seen.items():
            if not p:
                continue
            k = npath(p)
            self.own[k] = self.dir / name
            self.includes[k] = [npath(q) for q in incs]
            if is_tu:
                self.tus.add(k)
            if had_err:
                self.errors.add(k)
        return self

    def reachable(self, roots):
        """현재 TU 들에서 include 를 따라 닿는 파일들 (clangd loadProject 와 같은 방식)."""
        seen, stack = set(), [npath(r) for r in roots]
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            stack.extend(self.includes.get(k, ()))
        return seen


def _stat(p):
    try:
        st = os.stat(p)
        return [st.st_mtime_ns, st.st_size]
    except OSError:
        return None


def _sha1(p):
    try:
        h = hashlib.sha1()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()[:16]
    except OSError:
        return None


def load_state(path):
    try:
        s = json.loads(Path(path).read_text(encoding="utf-8"))
        return s if s.get("version") == STATE_VERSION else {}
    except (OSError, ValueError):
        return {}


def not_tu_yet(entries, store):
    """CDB 에서는 TU 인데 샤드는 다른 TU 에 포함된 파일로 만들어진 것 (유니티 묶음을 풀었을 때 등).
    다이제스트가 같아 clangd 는 건너뛰므로 샤드를 지워 TU 로 다시 색인하게 한다."""
    return [k for k in (npath(e["file"]) for e in entries) if k in store.own and k not in store.tus]


def plan(entries, store, state):
    """지울 TU 샤드와 이유. 내용이 같으면(mtime 만 바뀜, UHT 가 같은 .generated.h 를 다시 씀 등) 무효화하지 않는다."""
    files, cmds = state.get("files", {}), state.get("cmds", {})
    tus = {npath(e["file"]): e for e in entries}
    rev = {}
    for k, incs in store.includes.items():
        for q in incs:
            rev.setdefault(q, set()).add(k)
    for k, e in tus.items():
        for q in forced_includes(e):
            rev.setdefault(npath(q), set()).add(k)
    why, changed, now = {}, [], {}
    for k in not_tu_yet(entries, store):
        why[k] = "TU 로 바뀜"
    for k, e in tus.items():
        if k in cmds and cmds[k] != cmd_hash(e):
            why.setdefault(k, "플래그 변경")
    for k, old in files.items():
        st = _stat(k)
        if st and st == old[:2]:
            now[k] = old
            continue
        h = _sha1(k) if st else None
        if st and len(old) > 2 and old[2] and h == old[2]:
            now[k] = st + [h]  # 내용 같음
            continue
        changed.append(k)
        if st:
            now[k] = st + [h]
    for k in changed:
        if k in tus:
            continue  # TU 자신은 clangd 가 다이제스트로 잡는다
        stack, seen = [k], set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            for parent in rev.get(x, ()):
                if parent in tus:
                    why.setdefault(parent, "포함 헤더 변경")
                stack.append(parent)
    return why, changed, now


def save_state(path, entries, store, files_now, reachable, split=None):
    files = {}
    for k in reachable:
        if k in files_now:
            files[k] = files_now[k]
        else:
            st = _stat(k)
            if st:
                files[k] = st + [None]
    for e in entries:
        for q in forced_includes(e):
            k = npath(q)
            if k not in files:
                st = _stat(k)
                if st:
                    files[k] = files_now.get(k) or st + [None]
    state = {"version": STATE_VERSION, "files": files, "cmds": {npath(e["file"]): cmd_hash(e) for e in entries},
             "shards": store.cache, "split": sorted(split or ())}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- clangd 헤드리스 구동

INDEXED_RE = re.compile(r"Indexed (.+?) \(\d+ symbols")
ENQUEUE_RE = re.compile(r"Enqueueing (\d+) commands for indexing")


def run_background_index(clangd, cdb_dir, open_file, jobs=0, log_path=None, timeout=None, quiet=0.5, enqueue_wait=300):
    """clangd --background-index 를 LSP 로 띄워 색인이 끝날 때까지 기다리고 닫는다.
    순서: initialize(window.workDoneProgress) → initialized → didOpen(아무 파일) → 서버의 progress create 요청에 null 응답
          → $/progress 'backgroundIndexProgress' begin/report/end → shutdown/exit.
    didOpen 이 없으면 CDB 를 읽지 않아 아무것도 색인하지 않는다 (실험실 확인). 반환: 걸린 시간·색인한 TU·큐에 넣은 수."""
    args = [str(clangd), "--background-index", "--log=info", f"--compile-commands-dir={cdb_dir}",
            "--background-index-priority=normal"]  # Windows 의 기본(low)은 스레드를 백그라운드 모드(I/O 우선순위↓)로 둔다
    if jobs:
        args.append(f"-j={jobs}")
    t0 = time.time()
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(cdb_dir))
    events, indexed, state = queue.Queue(), [], {"enqueued": None, "enq_at": None, "failed": []}
    log = open(log_path, "w", encoding="utf-8", errors="replace") if log_path else None

    def err_reader():
        for raw in p.stderr:
            line = raw.decode("utf-8", "replace")
            if log:
                log.write(line)
            m = INDEXED_RE.search(line)
            if m:
                indexed.append(m.group(1))
                continue
            m = ENQUEUE_RE.search(line)
            if m:
                state["enqueued"], state["enq_at"] = int(m.group(1)), time.time()
            elif "Failed to index" in line or "failed to" in line.lower() and "index" in line.lower():
                state["failed"].append(line.strip()[:300])

    def out_reader():
        f = p.stdout
        while True:
            hdr = {}
            while True:
                line = f.readline()
                if not line:
                    events.put(None)
                    return
                line = line.strip()
                if not line:
                    break
                k, _, v = line.partition(b":")
                hdr[k.lower()] = v.strip()
            events.put(json.loads(f.read(int(hdr[b"content-length"]))))

    def send(msg):
        body = json.dumps(msg).encode("utf-8")
        p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        p.stdin.flush()

    threading.Thread(target=err_reader, daemon=True).start()
    threading.Thread(target=out_reader, daemon=True).start()
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "processId": os.getpid(), "rootUri": Path(cdb_dir).resolve().as_uri(),
        "capabilities": {"window": {"workDoneProgress": True}}, "initializationOptions": {}}})
    last_end, done, crashed, open_at = None, False, False, None
    try:
        while not done:
            if timeout and time.time() - t0 > timeout:
                raise TimeoutError(f"배경 색인이 {timeout}s 안에 끝나지 않았다")
            if open_at and state["enq_at"] is None and time.time() - open_at > enqueue_wait:
                raise RuntimeError(f"clangd 가 {enqueue_wait}s 동안 compile_commands 를 큐에 넣지 않았다 — 로그를 본다")
            try:
                m = events.get(timeout=0.1)
            except queue.Empty:
                m = 0
            if m is None:
                crashed = True
                break
            if m:
                if m.get("id") == 1 and "result" in m:
                    send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
                    text = Path(open_file).read_text(encoding="utf-8", errors="replace")
                    send({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": {
                        "uri": Path(open_file).resolve().as_uri(), "languageId": "cpp", "version": 1, "text": text}}})
                    open_at = time.time()
                elif "method" in m and "id" in m:  # 서버 → 클라이언트 요청 (workDoneProgress/create 등)
                    send({"jsonrpc": "2.0", "id": m["id"], "result": None})
                elif m.get("method") == "$/progress" and (m.get("params") or {}).get("token") == "backgroundIndexProgress":
                    kind = m["params"]["value"].get("kind")
                    last_end = time.time() if kind == "end" else None
            # 끝: CDB 를 큐에 넣은 뒤 진행 'end' 가 오고, quiet 초 동안 새 begin 이 없다
            if state["enq_at"] and last_end and last_end >= state["enq_at"] and time.time() - last_end > quiet:
                done = True
    finally:
        elapsed = time.time() - t0
        try:
            send({"jsonrpc": "2.0", "id": 2, "method": "shutdown"})
            send({"jsonrpc": "2.0", "method": "exit"})
        except OSError:
            pass
        try:
            p.wait(15)
        except subprocess.TimeoutExpired:
            p.kill()
        if log:
            log.close()
    return {"elapsed": elapsed, "indexed": indexed, "enqueued": state["enqueued"], "crashed": crashed,
            "failed": state["failed"]}
