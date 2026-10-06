#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""탐색 비용 A/B — 인덱스가 엔진 탐색 비용을 줄이는가 (indexing-research.md 3절 C).

LSP vs grep 파일럿(https://github.com/Poytr1/lsp-vs-grep-token-study)의 설계를 따른다: 모델·프롬프트·과제를 고정하고
도구 표면만 바꾼다.
  A = Read·Grep·Glob + 셸 rg/grep/find (인덱스 없음)
  B = A + 인덱스 CLI (cindex.py · ue_q.py · gq.py)
정답은 clangd 인덱스(컴파일러 기준)에서 뽑는다 — 엔진 범위와 프로젝트 범위 인덱스를 합쳐서.

  python cost_ab.py --root <프로젝트> [--repeat 2] [--arms A,B] [--jobs 6] [--out <폴더>] [--model <id>] [--rescore]

먼저 인덱스를 만들어 둔다: ue_q.py index, gq.py index, cindex.py build --scope project / --scope engine.
비용이 든다 (실행마다 claude -p 한 세션). 결과: <out>/report.md, <out>/runs.json, 세션 로그 <out>/*.jsonl.
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import cindex  # noqa: E402

REF = 4
NAME_RE = re.compile(r"\b[UAFS][A-Z]\w*(?:::\w+)?")
FILE_RE = re.compile(r"[\w.-]+\.(?:h|hpp|cpp|cc|inl)\b")

TOOLS_A = ["Read", "Grep", "Glob", "Bash(rg *)", "Bash(grep *)", "Bash(find *)", "Bash(ls *)", "Bash(wc *)",
           "Bash(head *)", "Bash(tail *)", "Bash(sort *)", "Bash(uniq *)", "Bash(cat *)", "Bash(sed -n *)"]
DENY = ["Edit", "Write", "NotebookEdit", "Agent", "Task", "WebFetch", "WebSearch", "Skill", "PowerShell"]
SYS_A = ("코드 탐색 도구: Grep·Glob·Read 와 셸의 rg·grep·find·wc·head·sort. 파일은 고치지 않는다.")


def sys_b():
    py = Path(sys.executable).name if os.name == "nt" else "python3"
    s = SCRIPTS.as_posix()
    return SYS_A + f"""
추가로 인덱스 조회 CLI 가 있다 (프로젝트 폴더에서 실행):
- `{py} {s}/cindex.py <명령> <이름>` — clangd 의미 인덱스. 명령: sym · refs · callers · callees · bases · derived · overrides ·
  members · impact · file. `--db project`(기본) = 프로젝트 TU + 그것이 포함한 엔진 헤더, `--db engine` = 엔진 TU 전체.
  같은 이름이 여럿이면 A::B 로 좁힌다. 출력은 4KB 에서 끊긴다 (--full 로 푼다).
- `{py} {s}/ue_q.py sym|api <이름>` — 엔진 선언 좌표·시그니처 (정규식 인덱스).
- `{py} {s}/gq.py sym <이름>` — 프로젝트 선언 좌표.
인덱스는 grep 을 대체하지 않는다 — 문자열·주석·설정은 rg."""


# ---------------------------------------------------------------- 정답 (clangd 인덱스, 엔진 + 프로젝트 범위 합침)

class Truth:
    def __init__(self, dbs):
        self.cons = [sqlite3.connect(f"file:{Path(d).as_posix()}?mode=ro", uri=True) for d in dbs if d and Path(d).exists()]
        if not self.cons:
            raise SystemExit("clangd 인덱스가 없다 — cindex.py build --scope project / --scope engine 먼저")
        self.kids = {0: {}, 1: {}}  # predicate → subject → {object}
        for s, pr, o in self.q("SELECT subject, predicate, object FROM relations"):
            self.kids[pr].setdefault(s, set()).add(o)

    def q(self, sql, args=()):
        out = []
        for c in self.cons:
            out += c.execute(sql, args).fetchall()
        return out

    def qname(self, sid):
        r = self.q("SELECT qname FROM symbols WHERE id=?", (sid,))
        return r[0][0] if r else None

    def ids(self, qname):
        return {r[0] for r in self.q("SELECT id FROM symbols WHERE qname=?", (qname,))}

    def _closure(self, pred, start):
        seen, st = set(), list(start)
        while st:
            for k in self.kids[pred].get(st.pop(), ()):
                if k not in seen:
                    seen.add(k)
                    st.append(k)
        return {self.qname(i) for i in seen} - {None}

    def derived_all(self, cls):
        return self._closure(0, self.ids(cls))

    def overrides_all(self, method):
        return self._closure(1, self.ids(method))

    def callers(self, fn):
        ids = self.ids(fn)
        out = set()
        for i in ids:
            out |= {r[0] for r in self.q("SELECT container FROM refs WHERE sym=? AND (kind & ?)!=0 AND container!=?",
                                         (i, REF, cindex.NULL_ID))}
        return {self.qname(c) for c in out} - {None, fn}

    def callees(self, fn):
        out = set()
        for i in self.ids(fn):
            out |= {r[0] for r in self.q("SELECT r.sym FROM refs r JOIN symbols s ON s.id=r.sym WHERE r.container=? "
                                         "AND (r.kind & ?)!=0 AND s.kind IN ('InstanceMethod','Function','StaticMethod',"
                                         "'ClassMethod','Constructor')", (i, REF))}
        return {self.qname(c) for c in out} - {None, fn}

    def ref_files(self, cls):
        """클래스 자체 또는 그 멤버(메서드·필드)를 참조하는 파일 — 질문이 "타입으로 쓰거나, 상속하거나, 메서드를 정의·호출" 이다.
        (Peer->Tick() 처럼 멤버만 부르는 .cpp 도 포함)"""
        ids = set(self.ids(cls)) | {r[0] for r in self.q("SELECT id FROM symbols WHERE scope=?", (cls + "::",))}
        out = set()
        for i in ids:
            out |= {Path(r[0]).name for r in self.q("SELECT f.path FROM refs r JOIN files f ON f.id=r.file "
                                                     "WHERE r.sym=? AND (r.kind & ?)!=0", (i, REF))}
        return out

    def location(self, cls):
        for c in self.cons:
            r = c.execute("SELECT f.path, s.decl_line FROM symbols s JOIN files f ON f.id=s.decl_file WHERE s.qname=? "
                          "AND s.kind IN ('Class','Struct')", (cls,)).fetchone()
            if r:
                bases = {self.qname(x[0]) for x in self.q("SELECT subject FROM relations WHERE object IN "
                                                            f"({','.join('?' * len(self.ids(cls)))}) AND predicate=0",
                                                            tuple(self.ids(cls)))} - {None}
                return {"file": Path(r[0]).name, "line": r[1], "parents": sorted(bases)}
        return None


def pick_tasks(t):
    """정답 크기가 적당한(손으로 확인 가능한) 대상을 인덱스에서 결정적으로 고른다."""
    con = t.cons[-1]  # 엔진 범위 인덱스 (마지막에 넣는다)
    q = lambda s, a=(): con.execute(s, a).fetchall()
    classes = [r[0] for r in q("SELECT qname FROM symbols WHERE kind='Class' ORDER BY qname")]
    tasks = []
    der = next((c for c in classes if 8 <= len(t.derived_all(c)) <= 14), None)
    if der:
        tasks.append({"id": "derived", "kind": "names", "subject": der, "expect": sorted(t.derived_all(der)),
                      "q": f"{der} 를 상속한 클래스를 모두 찾아라 — 직접 자식과 그 아래(손자·증손…) 전부, 엔진과 프로젝트 전체."})
    meths = [r[0] for r in q("SELECT qname FROM symbols WHERE kind='InstanceMethod' AND name LIKE 'Do%' ORDER BY qname")]
    cal = next((m for m in meths if 6 <= len(t.callers(m)) <= 9), None)
    if cal:
        tasks.append({"id": "callers", "kind": "names", "subject": cal, "expect": sorted(t.callers(cal)),
                      "q": f"{cal} 를 직접 호출하는 함수·메서드를 모두 찾아라 (엔진과 프로젝트 전체)."})
    cee = next((m for m in meths if len(t.callees(m)) >= 3), None)
    if cee:
        tasks.append({"id": "callees", "kind": "names", "subject": cee, "expect": sorted(t.callees(cee)),
                      "q": f"{cee} 의 본문이 직접 호출하는 메서드를 모두 찾아라."})
    loc = next((c for c in classes[len(classes) // 3:] if t.location(c) and t.location(c)["parents"]), None)
    if loc:
        L = t.location(loc)
        tasks.append({"id": "where", "kind": "location", "subject": loc, "expect": L,
                      "q": f"{loc} 가 선언된 파일과 줄 번호, 그리고 부모 클래스를 찾아라."})
    rf = next((c for c in classes[len(classes) // 2:] if 7 <= len(t.ref_files(c)) <= 12), None)
    if rf:
        tasks.append({"id": "ref-files", "kind": "files", "subject": rf, "expect": sorted(t.ref_files(rf)),
                      "q": f"{rf} 를 쓰는 소스 파일(.h/.cpp)을 모두 찾아라 — 타입으로 쓰거나, 상속하거나, 그 메서드를 정의·호출하는 파일. "
                           "그 클래스가 선언된 헤더 자신은 뺀다."})
    ovr = next((c for c in classes[len(classes) // 4:] if 8 <= len(t.overrides_all(c + "::BeginPlay")) <= 14), None)
    if ovr:
        m = ovr + "::BeginPlay"
        tasks.append({"id": "overrides", "kind": "names", "subject": m, "expect": sorted(t.overrides_all(m)),
                      "q": f"{m} 를 재정의한 메서드를 모두 찾아라 — 직접 재정의한 것과 그 아래(손자·증손…) 전부, 엔진과 프로젝트 전체."})
    return tasks


# ---------------------------------------------------------------- 실행

def prompt_of(task, engine):
    return (f"엔진 소스는 {engine} 에 있고, 현재 폴더가 게임 프로젝트다. 코드는 고치지 말고 찾기만 한다.\n\n"
            f"질문: {task['q']}\n\n"
            "마지막에 답만 ```answer 코드 블록에 한 줄에 하나씩 적는다 (클래스·메서드는 A::B 처럼 한정 이름, 파일은 파일 이름).")


def run_one(task, arm, rep, a, out, engine):
    log = out / f"{task['id']}-{arm}-{rep}.jsonl"
    if a.rescore and log.exists():
        return log
    tools = TOOLS_A + ([f"Bash(python3 {SCRIPTS.as_posix()}/*)", f"Bash(python {SCRIPTS.as_posix()}/*)"] if arm == "B" else [])
    cmd = ["claude", "-p", prompt_of(task, engine), "--output-format", "stream-json", "--verbose",
           "--max-turns", str(a.max_turns), "--append-system-prompt", sys_b() if arm == "B" else SYS_A,
           "--allowedTools", *tools, "--disallowedTools", *DENY]
    if a.add_engine:  # 엔진은 프로젝트 밖에 있다 — 셸이 엔진 경로를 읽게 허용 (대화형에서 사용자가 승인한 상태와 같게)
        cmd += ["--add-dir", str(engine)]
    if a.model:
        cmd += ["--model", a.model]
    env = dict(os.environ, UE_ROOT=str(engine))
    with open(log, "w", encoding="utf-8") as f:
        subprocess.run(cmd, cwd=a.root, stdout=f, stderr=subprocess.DEVNULL, env=env, timeout=a.timeout)
    return log


def parse(log):
    r = {"tools": {}, "bash": [], "result_chars": 0, "final": "", "cost": 0.0, "turns": 0, "usage": {}, "model": "",
         "denied": 0, "error": None}
    for line in open(log, encoding="utf-8"):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        t = j.get("type")
        if t == "system" and j.get("subtype") == "init":
            r["model"] = j.get("model", "")
        elif t == "assistant":
            for c in j["message"].get("content", []):
                if c.get("type") == "tool_use":
                    r["tools"][c["name"]] = r["tools"].get(c["name"], 0) + 1
                    if c["name"] == "Bash":
                        r["bash"].append(c["input"].get("command", ""))
        elif t == "user":
            for c in (j.get("message") or {}).get("content", []) if isinstance((j.get("message") or {}).get("content"), list) else []:
                if c.get("type") == "tool_result":
                    body = c.get("content")
                    if isinstance(body, list):
                        body = "".join(x.get("text", "") for x in body if isinstance(x, dict))
                    r["result_chars"] += len(str(body or ""))
                    if "permission" in str(body).lower() and "denied" in str(body).lower():
                        r["denied"] += 1
        elif t == "result":
            r["final"] = j.get("result") or ""
            r["cost"] = j.get("total_cost_usd") or 0.0
            r["turns"] = j.get("num_turns") or 0
            r["usage"] = j.get("usage") or {}
            if j.get("is_error"):
                r["error"] = j.get("subtype")
    u = r["usage"]
    r["tokens_in"] = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
    r["tokens_out"] = u.get("output_tokens") or 0
    r["calls"] = sum(r["tools"].values())
    r["index_calls"] = sum(1 for b in r["bash"] if re.search(r"(cindex|ue_q|gq)\.py", b))
    return r


def answer_block(final):
    m = re.findall(r"```answer\s*\n(.*?)```", final, re.S)
    return m[-1] if m else final


def score(task, final):
    ans = answer_block(final)
    if task["kind"] == "location":
        e = task["expect"]
        ok_file = e["file"] in ans
        ok_line = bool(re.search(rf"\b{e['line']}\b", ans))
        ok_par = all(p in ans for p in e["parents"])
        rec = (ok_file + ok_line + ok_par) / 3
        return {"recall": rec, "precision": None, "missing": [k for k, ok in (("file", ok_file), ("line", ok_line), ("parent", ok_par)) if not ok], "extra": []}
    # 이름은 파일 이름을 걷어낸 뒤 뽑는다 (AI2Data.cpp 의 AI2Data 를 클래스로 읽지 않게)
    got = set(FILE_RE.findall(ans)) if task["kind"] == "files" else set(NAME_RE.findall(FILE_RE.sub(" ", ans)))
    got.discard(task["subject"])
    exp = set(task["expect"])
    hit = got & exp
    return {"recall": len(hit) / len(exp) if exp else 1.0, "precision": len(hit) / len(got) if got else 0.0,
            "missing": sorted(exp - got), "extra": sorted(got - exp)}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="게임 프로젝트 루트 (cwd 가 된다)")
    ap.add_argument("--out", default=str(Path.cwd() / "cost_ab"))
    ap.add_argument("--arms", default="A,B")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--model", default=None)
    ap.add_argument("--only", default=None, help="과제 id 쉼표 목록")
    ap.add_argument("--rescore", action="store_true", help="세션을 다시 돌리지 않고 로그만 채점")
    ap.add_argument("--refresh-truth", action="store_true", help="--rescore 때 정답을 지금 규칙으로 다시 계산")
    ap.add_argument("--no-add-engine", dest="add_engine", action="store_false",
                    help="엔진 폴더를 --add-dir 로 허용하지 않는다 (셸의 엔진 경로 접근이 막힌다)")
    a = ap.parse_args()
    a.root = str(Path(a.root).resolve())
    root, kind = cindex.project_of(a.root)
    engine = cindex.engine_dir_of(root, kind)
    if not engine:
        raise SystemExit("엔진 경로를 못 찾았다 — UE_ROOT 를 준다")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t = Truth([cindex.db_for("project", root, kind), cindex.db_for("engine", root, kind)])
    tf = out / "tasks.json"
    tasks = json.loads(tf.read_text(encoding="utf-8")) if a.rescore and tf.exists() else pick_tasks(t)
    if a.rescore and a.refresh_truth:  # 과제(대상)는 그대로, 정답만 지금 규칙으로 다시 계산
        fresh = {x["id"]: x for x in pick_tasks(t)}
        for x in tasks:
            if x["id"] in fresh and fresh[x["id"]]["subject"] == x["subject"]:
                x["expect"] = fresh[x["id"]]["expect"]
    tf.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.only:
        tasks = [x for x in tasks if x["id"] in a.only.split(",")]
    arms = a.arms.split(",")
    jobs = [(x, arm, rep) for rep in range(a.repeat) for x in tasks for arm in arms]
    print(f"과제 {len(tasks)} × 실험군 {len(arms)} × 반복 {a.repeat} = 세션 {len(jobs)} · 엔진 {engine}")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        logs = list(ex.map(lambda j: run_one(*j, a, out, engine), jobs))
    runs = []
    for (x, arm, rep), log in zip(jobs, logs):
        r = parse(log)
        s = score(x, r["final"])
        runs.append({"task": x["id"], "arm": arm, "rep": rep, **{k: r[k] for k in ("cost", "turns", "tokens_in", "tokens_out",
                     "calls", "index_calls", "result_chars", "tools", "model", "denied", "error")}, **s})
    (out / "runs.json").write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["| 과제 | 실험군 | 재현율 | 정밀도 | 비용 | 입력 토큰 | 출력 토큰 | 턴 | 도구 호출 (인덱스) | 도구 출력 글자 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for x in tasks:
        for arm in arms:
            rs = [r for r in runs if r["task"] == x["id"] and r["arm"] == arm]
            pr = mean([r["precision"] for r in rs])
            lines.append(f"| {x['id']} | {arm} | {mean([r['recall'] for r in rs]):.2f} | {'-' if pr is None else f'{pr:.2f}'} | "
                         f"${mean([r['cost'] for r in rs]):.3f} | {mean([r['tokens_in'] for r in rs]):,.0f} | "
                         f"{mean([r['tokens_out'] for r in rs]):,.0f} | {mean([r['turns'] for r in rs]):.1f} | "
                         f"{mean([r['calls'] for r in rs]):.1f} ({mean([r['index_calls'] for r in rs]):.1f}) | "
                         f"{mean([r['result_chars'] for r in rs]):,.0f} |")
    lines += ["", "| 실험군 | 재현율 | 정밀도 | 비용 합 | 비용 평균 | 입력 토큰 평균 | 턴 평균 | 도구 호출 평균 | 도구 출력 글자 평균 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        rs = [r for r in runs if r["arm"] == arm]
        lines.append(f"| {arm} | {mean([r['recall'] for r in rs]):.2f} | {mean([r['precision'] for r in rs]):.2f} | "
                     f"${sum(r['cost'] for r in rs):.2f} | ${mean([r['cost'] for r in rs]):.3f} | "
                     f"{mean([r['tokens_in'] for r in rs]):,.0f} | {mean([r['turns'] for r in rs]):.1f} | "
                     f"{mean([r['calls'] for r in rs]):.1f} | {mean([r['result_chars'] for r in rs]):,.0f} |")
    models = sorted({r["model"] for r in runs if r["model"]})
    errs = [f"{r['task']}-{r['arm']}-{r['rep']}: {r['error']}" for r in runs if r["error"]]
    report = "\n".join(lines) + f"\n\n모델 {', '.join(models) or '?'} · 세션 {len(runs)} · {time.time() - t0:.0f}s" + \
             (f"\n오류: {'; '.join(errs)}" if errs else "")
    (out / "report.md").write_text(report + "\n", encoding="utf-8")
    print(report)
    for r in runs:
        if r["missing"] or r["extra"]:
            print(f"  {r['task']}-{r['arm']}-{r['rep']}: 빠짐 {r['missing'][:6]} · 더함 {r['extra'][:6]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
