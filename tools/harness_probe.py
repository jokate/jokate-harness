#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""하네스 대조 시험 — 같은 과제를 하네스 두 팔(지금 · 수정안)에서 돌려 비교한다.

Harness²(arXiv 2610.14224)의 Propose → Probe → Compose 중 Probe 를 우리 정답지로 한다: 논문은 정답 없이 기준 실행과
수정안 실행의 차이만 보지만, 우리는 정답지(심볼 재현율)와 run_evals 의 채점(스킬 호출 · 셸 명령 · 답 정규식)이 있다.
하네스를 고치기 전에 돌려 "정확도를 잃지 않고 무엇이 줄었나"를 숫자로 보고, 결과를 경험 문서 초안으로 남긴다.

  python tools/harness_probe.py --spec <spec.json> [--reps 2] [--jobs 4] [--out <폴더>] [--rescore]

spec (JSON):
  {"base": "<프로젝트 스냅숏 폴더>", "name": "MNYS", "model": "sonnet", "budget": 1.5,
   "claude_args": [...],                                   # 없으면 run_evals cases.json 의 claude_args
   "arms": {"X": {"overlay": {"CLAUDE.local.md": "<파일>"}, "env": {}, "wiki": "<위키 원본 폴더>"},
            "Y": {"overlay": {...}, "env": {"GAME_HARNESS_ROUTING": "slim"}, "wiki": "<…>"}},
   "qa": {"file": "<과제.json — ab_wiki 모양: tasks[{id, question, key}]>", "prefix": "[SKIP] "},
   "cases": {"file": "<run_evals cases.json>", "only": ["arch-cc", "testing"]}}

- 팔마다 base 를 <out>/arms/<name>_<팔> 로 복사하고(원본은 건드리지 않는다) overlay 파일을 덮는다. overlay 의 글에서
  {ROOT} 는 그 팔의 복사본, {WIKI} 는 그 팔의 위키 사본 경로로 바뀐다. 위키 사본은 ~/.jokate-wiki/<name>_<팔> —
  game_context 가 <홈>/.jokate-wiki/<프로젝트 폴더 이름> 을 보므로 팔마다 자기 사본을 본다(실제 위키에 쓰지 않는다).
- 복사본의 `.claude/session_start.json` 은 비운다 — 색인 갱신 · 위키 drift(--write)가 실제 위키나 PC 를 건드리지 않게.
- 결과: <out>/report.md · runs.json · logs/*.jsonl · EXPERIENCE.draft.md(상황 · 관찰 · 근거 — 사람이 확인하고
  docs/experience/ 로 옮긴다. 근거가 약하면 옮기지 않는다).
비용이 든다 (실행마다 claude -p 한 세션, 2026-10 기준 정답지 과제 약 $0.3, 스킬 사례 약 $0.5~2).
"""
import argparse
import json
import os
import re
import shutil
import stat
import statistics
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

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills" / "game-bootstrap" / "evals"))
import run_evals  # noqa: E402  (채점 · 로그 읽기를 같이 쓴다)

TOP_SKIP = {"Content", "Binaries", "Intermediate", "DerivedDataCache", "Build", ".vs", ".idea"}
VCS = {".git", ".svn", ".hg"}
EXT_SKIP = {".uasset", ".umap", ".pak", ".zip", ".7z"}
INDEX_RE = re.compile(r"(cindex|gq|mnys_q|ue_q|wq)\.py")
GREP_RE = re.compile(r"(^|[\s|;&(])(rg|grep|egrep|findstr|Select-String)(\s|$)")


# ---------------------------------------------------------------- 팔 준비
def rmtree(p: Path):
    def onexc(func, path, _e):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(p, onexc=onexc)
    else:
        shutil.rmtree(p, onerror=onexc)


def copy_base(src: Path, dst: Path):
    def ignore(d, names):
        d = Path(d)
        out = []
        for n in names:
            p = d / n
            if p.is_dir() and (n in VCS or (d == src and n in TOP_SKIP)):
                out.append(n)
            elif p.is_file() and p.suffix.lower() in EXT_SKIP:
                out.append(n)
            elif d == src / "Saved" and n != "ClaudeIndex":
                out.append(n)
            elif d == src / "Saved" / "ClaudeIndex" and n == "bg":
                out.append(n)
        return out
    if dst.exists():
        rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def prepare_arm(spec, arm, conf, out: Path) -> dict:
    root = out / "arms" / f"{spec['name']}_{arm}"
    wiki = Path.home() / ".jokate-wiki" / root.name
    if not (root / ".probe_ready").is_file():
        t0 = time.perf_counter()
        copy_base(Path(spec["base"]), root)
        if conf.get("wiki"):
            if wiki.exists():
                rmtree(wiki)
            shutil.copytree(conf["wiki"], wiki, ignore=shutil.ignore_patterns(".git", "views"))
        (root / ".claude").mkdir(exist_ok=True)
        (root / ".claude" / "session_start.json").write_text('{"commands": []}\n', encoding="utf-8")
        for rel, src in (conf.get("overlay") or {}).items():
            text = Path(src).read_text(encoding="utf-8")
            text = text.replace("{ROOT}", root.as_posix()).replace("{WIKI}", wiki.as_posix())
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        (root / ".probe_ready").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
        print(f"팔 {arm}: {root} 준비 ({time.perf_counter() - t0:.0f}초)", flush=True)
    return {"root": root, "wiki": wiki if conf.get("wiki") else None, "env": conf.get("env") or {}}


# ---------------------------------------------------------------- 실행 · 읽기 · 채점
def run_one(job, arms, spec, args_base, logs: Path):
    arm = arms[job["arm"]]
    log = logs / f"{job['kind']}-{job['id']}-{job['arm']}{job['rep']}.jsonl"
    if log.is_file() and log.stat().st_size > 0 and job.get("skip_done"):
        return log
    argv = [shutil.which("claude") or "claude", "-p", job["prompt"], "--output-format", "stream-json", "--verbose",
            "--model", spec.get("model", "sonnet"), "--max-budget-usd", str(spec.get("budget", 1.5)), *args_base]
    if arm["wiki"]:
        argv += ["--add-dir", str(arm["wiki"])]
    env = {**os.environ, "GAME_HARNESS_NO_OPEN": "1", **arm["env"]}
    env.pop("CLAUDE_PROJECT_DIR", None)
    t0 = time.perf_counter()
    with open(log, "w", encoding="utf-8") as f:
        subprocess.run(argv, cwd=str(arm["root"]), stdout=f, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, env=env)
    print(f"  {log.stem} {time.perf_counter() - t0:.0f}초", flush=True)
    return log


def read_log(log: Path) -> dict:
    r = run_evals.parse(log)
    tokens, wiki_reads, greps, index_calls = 0, 0, 0, 0
    for line in open(log, encoding="utf-8", errors="replace"):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("type") == "assistant":
            for c in (j.get("message") or {}).get("content") or []:
                if c.get("type") != "tool_use":
                    continue
                inp = c.get("input") or {}
                if c["name"] == "Read" and re.search(r"[\\/]\.jokate-wiki[\\/]", str(inp.get("file_path", ""))):
                    wiki_reads += 1
                if c["name"] == "Grep":
                    greps += 1
                if c["name"] in ("Bash", "PowerShell"):
                    cmd = str(inp.get("command", ""))
                    if INDEX_RE.search(cmd):
                        index_calls += 1
                    elif GREP_RE.search(cmd):
                        greps += 1
        elif j.get("type") == "result":
            for u in (j.get("modelUsage") or {}).values():
                tokens += sum(u.get(k) or 0 for k in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                                                      "cacheCreationInputTokens"))
    r.update(tokens=tokens, wiki_reads=wiki_reads, greps=greps, index_calls=index_calls)
    return r


def aliases(sym):
    out = {sym}
    m = re.match(r"^[AUFIE][A-Z]{1,4}(?=[A-Z])", sym)
    if m and len(sym) - m.end() >= 4:
        out.add(sym[m.end():])
    if "_" in sym and len(sym.rsplit("_", 1)[1]) >= 4:
        out.add(sym.rsplit("_", 1)[1])
    return sorted(out, key=len, reverse=True)


def recall(final, key):
    hit = [k for k in key if any(re.search(r"(?<![A-Za-z0-9])" + re.escape(a) + r"(?![A-Za-z0-9])", final)
                                 for a in aliases(k))]
    return round(len(hit) / len(key), 3) if key else None


# ---------------------------------------------------------------- 보고
def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 3) if xs else None


def report(rows, spec, out: Path) -> str:
    arms = sorted({r["arm"] for r in rows})
    lines = [f"# 하네스 대조 시험 — {spec['name']} ({time.strftime('%Y-%m-%d %H:%M')})", "",
             "| 팔 | 설명 | 정답 재현율 | 스킬 사례 통과 | 비용 $/회 | 토큰/회 | 턴/회 | grep/회 | 인덱스/회 | 위키 읽기/회 | 실행 수 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in arms:
        rs = [r for r in rows if r["arm"] == a]
        qa = [r for r in rs if r["kind"] == "qa"]
        cs = [r for r in rs if r["kind"] == "case"]
        passed = sum(r["passed"] for r in cs)
        total = sum(r["checks"] for r in cs)
        lines.append(f"| {a} | {spec['arms'][a].get('note', '')} | {mean([r['recall'] for r in qa])} | "
                     f"{passed}/{total} | {mean([r['cost'] for r in rs])} | {mean([r['tokens'] for r in rs])} | "
                     f"{mean([r['turns'] for r in rs])} | {mean([r['greps'] for r in rs])} | "
                     f"{mean([r['index_calls'] for r in rs])} | {mean([r['wiki_reads'] for r in rs])} | {len(rs)} |")
    lines += ["", "## 과제별", "", "| 종류 | 과제 | " + " | ".join(f"{a} 재현율·통과" for a in arms) + " | "
              + " | ".join(f"{a} $" for a in arms) + " | 스킬 (팔별) |", "|---|---|" + "---|" * (2 * len(arms) + 1)]
    for kind, tid in sorted({(r["kind"], r["id"]) for r in rows}):
        cells, costs, skills = [], [], []
        for a in arms:
            rs = [r for r in rows if r["kind"] == kind and r["id"] == tid and r["arm"] == a]
            if kind == "qa":
                cells.append(str(mean([r["recall"] for r in rs])))
            else:
                cells.append(f"{sum(r['passed'] for r in rs)}/{sum(r['checks'] for r in rs)}")
            costs.append(str(mean([r["cost"] for r in rs])))
            skills.append(f"{a}:" + ",".join(sorted({s for r in rs for s in r["skills"]})) or "-")
        lines.append(f"| {kind} | {tid} | " + " | ".join(cells) + " | " + " | ".join(costs) + " | " + " ".join(skills) + " |")
    fails = [r for r in rows if r["kind"] == "case" and r["failed"]]
    if fails:
        lines += ["", "## 못 맞춘 채점 항목", ""] + [f"- {r['id']} {r['arm']}{r['rep']}: " + " · ".join(r["failed"]) for r in fails]
    text = "\n".join(lines) + "\n"
    (out / "report.md").write_text(text, encoding="utf-8")
    exp = ["# 경험 초안 — 사람이 확인하고 docs/experience/ 로 옮긴다 (근거가 약하면 옮기지 않는다)", "",
           f"## 상황\n{spec.get('situation', '(spec.situation 을 채운다)')}", "",
           "## 관찰 (숫자)", *[l for l in lines[2:3 + len(arms) + 1]], "",
           f"## 근거\n- {out / 'runs.json'} · {out / 'report.md'} · 로그 {out / 'logs'}",
           f"- 실행: 팔 {len(arms)} · 기록 {len(rows)} · 모델 {spec.get('model', 'sonnet')}", "",
           "## 교훈 (사람이 쓴다)\n- "]
    (out / "EXPERIENCE.draft.md").write_text("\n".join(exp) + "\n", encoding="utf-8")
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--reps", type=int, default=1, help="정답지 과제 반복 (스킬 사례는 --case-reps)")
    ap.add_argument("--case-reps", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default=None)
    ap.add_argument("--rescore", action="store_true", help="다시 돌리지 않고 남은 로그만 채점")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    out = Path(a.out or (Path.home() / ".claude" / "cache" / "game-harness" / "probe" / time.strftime("%Y%m%d-%H%M")))
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    cases_spec = json.loads(Path(spec["cases"]["file"]).read_text(encoding="utf-8")) if spec.get("cases") else {}
    args_base = [os.path.expanduser(x) for x in (spec.get("claude_args") or cases_spec.get("claude_args") or [])]
    arms = {k: prepare_arm(spec, k, v, out) for k, v in spec["arms"].items()}

    jobs = []
    if spec.get("qa"):
        qa = json.loads(Path(spec["qa"]["file"]).read_text(encoding="utf-8"))
        prefix = spec["qa"].get("prefix", qa.get("prompt_prefix", ""))
        prefix = prefix if prefix.endswith(" ") or not prefix else prefix + " "
        for t in qa["tasks"]:
            for arm in arms:
                for rep in range(1, a.reps + 1):
                    jobs.append({"kind": "qa", "id": t["id"], "arm": arm, "rep": rep, "prompt": prefix + t["question"],
                                 "key": t["key"]})
    if spec.get("cases"):
        only = set(spec["cases"].get("only") or [])
        for c in cases_spec.get("cases", []):
            if only and c["id"] not in only:
                continue
            for arm in arms:
                for rep in range(1, a.case_reps + 1):
                    jobs.append({"kind": "case", "id": c["id"], "arm": arm, "rep": rep, "prompt": c["prompt"], "case": c})
    print(f"실행 {len(jobs)}개 (동시 {a.jobs}) → {out}", flush=True)
    if not a.rescore:
        # 팔을 번갈아 넣는다 — 같은 시간대에 두 팔이 같이 돌게(시간대에 따른 차이를 줄인다)
        jobs.sort(key=lambda j: (j["rep"], j["kind"], j["id"], j["arm"]))
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            list(ex.map(lambda j: run_one(j, arms, spec, args_base, logs), jobs))
    rows = []
    for j in jobs:
        log = logs / f"{j['kind']}-{j['id']}-{j['arm']}{j['rep']}.jsonl"
        if not log.is_file():
            continue
        r = read_log(log)
        row = {k: j[k] for k in ("kind", "id", "arm", "rep")}
        row.update(cost=r["cost"], tokens=r["tokens"], turns=r["turns"], skills=r["skills"], greps=r["greps"],
                   index_calls=r["index_calls"], wiki_reads=r["wiki_reads"], recall=None, passed=0, checks=0, failed=[])
        if j["kind"] == "qa":
            row["recall"] = recall(r["final"], j["key"])
        else:
            res = run_evals.score(j["case"], r)
            row.update(passed=sum(ok for ok, _ in res), checks=len(res), failed=[why for ok, why in res if not ok])
        rows.append(row)
    (out / "runs.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(report(rows, spec, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
