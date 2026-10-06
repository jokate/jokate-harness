"""하네스 추적 훅 (PostToolUse / PostToolUseFailure, matcher: Skill|Bash|PowerShell).
하네스 스킬(game-*)이 불렸거나 하네스 조회 스크립트(skills/game-*/scripts/*.py)가 실행됐으면
harness_events 에 한 줄 남긴다. 그 밖의 도구 호출은 무시한다. 어떤 경우에도 세션을 막지 않는다.

  skill.<스킬 이름>            예: skill.game-architecture
  script.<스크립트>.<명령>      예: script.ue_q.sym, script.evidence.hotspots
"""
import json
import re
import sys

SCRIPT = re.compile(r"game-[a-z-]+[\\/]+scripts[\\/]+(\w+)\.py[\"']?(?:\s+([a-z][\w-]*))?")


def main():
    from harness_events import emit
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    ok = data.get("hook_event_name") != "PostToolUseFailure"
    common = {"session": data.get("session_id", ""), "project": data.get("cwd", ""), "source": "harness_trace"}
    if tool == "Skill":
        name = str(inp.get("skill", ""))
        if name.split(":")[-1].startswith("game-"):
            emit(f"skill.{name.split(':')[-1]}", inp.get("args", "") or "", ok=ok, **common)
        return
    if tool in ("Bash", "PowerShell"):
        cmd = str(inp.get("command", ""))
        for m in SCRIPT.finditer(cmd):
            feature = f"script.{m.group(1)}" + (f".{m.group(2)}" if m.group(2) else "")
            emit(feature, cmd[:200], ok=ok, **common)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
