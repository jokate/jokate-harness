#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게임 하네스 평가. 케이스마다 새 헤드리스 세션(claude -p)을 병렬로 띄우고 채점한다.

  python run_evals.py [--cases cases.json] [--only id1,id2] [--out <폴더>] [--rescore]

채점 종류: skill(스킬 호출) · bash_re(실행한 셸 명령 정규식) · final_re / final_not_re(최종 답변 정규식)
세션 로그(jsonl)와 최종 답변(md)은 --out 에 남는다. --rescore 는 세션을 다시 돌리지 않고 남은 로그만 채점한다.
비용이 든다 (케이스당 대략 $0.5~2, 2026-10 기준 실측).
"""
import argparse
import json
import os
import re
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


def run_case(case, args_base, out):
    log = out / f"{case['id']}.jsonl"
    cmd = ["claude", "-p", case["prompt"], "--output-format", "stream-json", "--verbose"] + args_base
    with open(log, "w", encoding="utf-8") as f:
        subprocess.run(cmd, cwd=case["cwd"], stdout=f, stderr=subprocess.DEVNULL, shell=(os.name == "nt"))
    return log


def parse(log):
    skills, shell, tools, final, cost, turns = [], [], [], "", 0.0, 0
    for line in open(log, encoding="utf-8"):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("type") == "assistant":
            for c in j["message"].get("content", []):
                if c.get("type") != "tool_use":
                    continue
                tools.append(c["name"])
                if c["name"] == "Skill":
                    skills.append(c["input"].get("skill", ""))
                if c["name"] in ("Bash", "PowerShell"):
                    shell.append(c["input"].get("command", ""))
        elif j.get("type") == "result":
            final, cost, turns = j.get("result") or "", j.get("total_cost_usd") or 0.0, j.get("num_turns") or 0
    return {"skills": skills, "shell": shell, "tools": tools, "final": final, "cost": cost, "turns": turns}


def score(case, r):
    rows = []
    for ch in case["checks"]:
        t = ch["type"]
        if t == "skill":
            ok = ch["name"] in r["skills"]
        elif t == "bash_re":
            ok = any(re.search(ch["re"], c) for c in r["shell"])
        elif t == "final_re":
            ok = bool(re.search(ch["re"], r["final"]))
        elif t == "final_not_re":
            ok = not re.search(ch["re"], r["final"])
        else:
            ok = False
        rows.append((ok, ch.get("why", t)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    ap.add_argument("--only")
    ap.add_argument("--out", default=str(Path.cwd() / "harness_eval"))
    ap.add_argument("--rescore", action="store_true")
    a = ap.parse_args()

    spec = json.loads(Path(a.cases).read_text(encoding="utf-8"))
    cases = spec["cases"]
    if a.only:
        keep = set(a.only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    args_base = [os.path.expanduser(x) for x in spec.get("claude_args", [])]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    if not a.rescore:
        with ThreadPoolExecutor(max_workers=len(cases)) as ex:
            list(ex.map(lambda c: run_case(c, args_base, out), cases))

    total_ok = total = 0
    cost = 0.0
    lines = ["| 케이스 | 통과 | 스킬 호출 | 턴 | 비용 |", "|---|---|---|---|---|"]
    detail = []
    for c in cases:
        r = parse(out / f"{c['id']}.jsonl")
        (out / f"{c['id']}_final.md").write_text(r["final"], encoding="utf-8")
        rows = score(c, r)
        n_ok = sum(ok for ok, _ in rows)
        total_ok += n_ok
        total += len(rows)
        cost += r["cost"]
        lines.append(f"| {c['id']} | {n_ok}/{len(rows)} | {', '.join(r['skills']) or '-'} | {r['turns']} | ${r['cost']:.2f} |")
        detail += [f"- {'✅' if ok else '❌'} {c['id']}: {why}" for ok, why in rows]
    print("\n".join(lines))
    print()
    print("\n".join(detail))
    print(f"\n합계 {total_ok}/{total} · 비용 ${cost:.2f} · {time.time() - t0:.0f}s · 로그 {out}")
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
