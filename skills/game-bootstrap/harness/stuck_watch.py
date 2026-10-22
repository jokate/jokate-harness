"""매몰 신호 카운터. 세션 안에서 반복을 세고, 임계값에 닿으면 사용자에게 경고를 띄운다.

신호 (SIGNALS 에 한 줄씩 — 새 신호는 여기에만 추가한다):
  edit  같은 파일을 N회 수정 (PostToolUse: Edit / Write / NotebookEdit)
  fail  셸 명령이 연속 N회 실패 (PostToolUseFailure: Bash / PowerShell, 성공하면 0으로)

임계값: 기본 edit 5, fail 3. <프로젝트>/.claude/stuck_watch.json 의 {"edit": 8, "fail": 4} 로 덮어쓴다. 0 이면 끈다.
범위: 게임 프로젝트(UE / Unity, game_context.detect)에서만 돈다. edit 은 코드 파일(CODE_EXT)만 센다 — 문서를 고쳐 쓰는 것은 매몰이 아니다.
  (2026-10-14 기준 10일간 경고 514건 중 473건이 게임이 아닌 릴레이 작업 폴더, 나머지 대부분이 문서 반복 수정이었다.)
상태: ~/.claude/cache/stuck/<session_id>.json
반복이 없는 방향 이탈은 못 잡는다. 그건 사람이 본다 — 멈추고 /clear 로 새로 시작한다.
어떤 경우에도 도구 호출을 막지 않는다.
"""
import json
import os
import sys
from pathlib import Path

try:
    from harness_events import emit as harness_emit
except Exception:  # 이벤트 로그가 설치되지 않았어도 훅은 돈다
    def harness_emit(*a, **k):
        pass

DEFAULTS = {"edit": 5, "fail": 3}
CODE_EXT = {".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hh", ".inl", ".cs", ".py", ".lua", ".hlsl", ".usf", ".ush",
            ".shader", ".compute", ".cginc"}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
STATE_DIR = Path.home() / ".claude" / "cache" / "stuck"


def sig_edit(event, data, state, limits):
    if event != "PostToolUse" or data.get("tool_name") not in EDIT_TOOLS:
        return None
    inp = data.get("tool_input") or {}
    path = inp.get("file_path") or inp.get("notebook_path")
    if not path or Path(path).suffix.lower() not in CODE_EXT:
        return None
    counts = state.setdefault("edit", {})
    n = counts[path] = counts.get(path, 0) + 1
    if limits["edit"] and n % limits["edit"] == 0:
        return f"같은 파일을 {n}회 수정했다: {Path(path).name}"
    return None


def sig_fail(event, data, state, limits):
    if data.get("tool_name") not in SHELL_TOOLS:
        return None
    if event == "PostToolUse":
        state["fail"] = 0
        return None
    if event != "PostToolUseFailure":
        return None
    n = state["fail"] = state.get("fail", 0) + 1
    if limits["fail"] and n % limits["fail"] == 0:
        return f"셸 명령이 연속 {n}회 실패했다"
    return None


SIGNALS = [sig_edit, sig_fail]


def in_game_project(data):
    try:
        from game_context import detect
    except Exception:  # 같은 폴더에 game_context.py 가 없으면(옛 설치) 예전처럼 어디서나 돈다
        return True
    try:
        return detect(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())[0] is not None
    except OSError:
        return False


def load_limits(data):
    limits = dict(DEFAULTS)
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    try:
        limits.update(json.loads((root / ".claude" / "stuck_watch.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return limits


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    if not in_game_project(data):
        return
    event = data.get("hook_event_name")
    session = data.get("session_id") or "unknown"
    path = STATE_DIR / f"{session}.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}

    limits = load_limits(data)
    hits = [m for m in (s(event, data, state, limits) for s in SIGNALS) if m]

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    if hits:
        msg = "[매몰 신호] " + " · ".join(hits) + ". 방향이 맞는지 확인하고, 아니면 멈추고 /clear 로 새로 시작."
        out = {"systemMessage": msg,
               "hookSpecificOutput": {
                   "hookEventName": event,
                   "additionalContext": msg + " (사용자에게 같은 경고가 떴다. 같은 접근을 반복 중이면 멈추고 한 줄로 상황을 알린다.)"}}
        sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
        harness_emit("stuck.warn", " · ".join(hits), session=session, project=data.get("cwd", ""), source="stuck_watch")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
