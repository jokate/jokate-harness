"""SessionStart 디스패처. <프로젝트>/.claude/session_start.json 에 선언된 명령을
프로젝트 루트에서 순서대로 돌린다. 선언 파일이 없으면 아무것도 안 한다. 어떤 경우에도 세션을 막지 않는다.

session_start.json:
  {"commands": [{"run": ["Tools/x_q.py", "index", "--quiet"], "timeout": 30}]}
  run[0] 이 .py 면 이 훅을 돌리는 파이썬으로 실행한다 (프로젝트 파일에 머신 경로를 안 남기려고).
  각 인자의 ~ 는 홈으로 펼친다 (예: "~/.claude/skills/game-onboard/scripts/gq.py").
  각 명령의 stdout 은 모델 컨텍스트로 넘어간다.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from harness_events import emit as harness_emit
except Exception:  # 이벤트 로그가 설치되지 않았어도 훅은 돈다
    def harness_emit(*a, **k):
        pass

DECL = Path(".claude") / "session_start.json"
MAX_OUT = 9000


def find_decl(start):
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / DECL).is_file():
            return cand
    return None


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    except ValueError:
        data = {}
    start = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    root = find_decl(start)
    if root is None:
        return

    commands = json.loads((root / DECL).read_text(encoding="utf-8")).get("commands", [])
    session = data.get("session_id", "")
    out = []
    for c in commands:
        run = [os.path.expanduser(x) for x in c.get("run") or []]
        if not run:
            continue
        feature = "session_start." + Path(run[0]).stem
        label = " ".join(c["run"])
        if run[0].endswith(".py"):
            run.insert(0, sys.executable)
        t0 = time.time()
        try:
            r = subprocess.run(run, cwd=str(root), capture_output=True, timeout=c.get("timeout", 30),
                               encoding="utf-8", errors="replace")
            if r.stdout.strip():
                out.append(r.stdout.strip())
            if r.returncode != 0:
                out.append(f"[session_start] 실패({r.returncode}): {label}\n{r.stderr.strip()[:500]}")
            harness_emit(feature, f"{label} ({time.time() - t0:.1f}s, 종료 {r.returncode})", ok=r.returncode == 0,
                         session=session, project=root, source="session_start")
        except subprocess.TimeoutExpired:
            out.append(f"[session_start] 시간 초과: {label}")
            harness_emit(feature, f"{label} 시간 초과", ok=False, session=session, project=root, source="session_start")
        except OSError as e:
            out.append(f"[session_start] 실행 불가: {label} ({e})")
            harness_emit(feature, f"{label} 실행 불가 ({e})", ok=False, session=session, project=root, source="session_start")

    if out:
        sys.stdout.buffer.write("\n".join(out)[:MAX_OUT].encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
