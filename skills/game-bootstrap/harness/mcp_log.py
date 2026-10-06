"""MCP 호출 계측 훅. PostToolUse / PostToolUseFailure 의 stdin JSON 을 받아
~/.claude/mcp_logs/<프로젝트>.jsonl 에 한 줄씩 남긴다. 어떤 경우에도 세션을 막지 않는다."""
import json
import sys
import time
from pathlib import Path

try:
    from harness_events import emit as harness_emit
except Exception:  # 이벤트 로그가 설치되지 않았어도 훅은 돈다
    def harness_emit(*a, **k):
        pass

INPUT_PREVIEW = 300


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    tool = data.get("tool_name", "")
    if not tool.startswith("mcp__"):
        return

    _, server, name = (tool.split("__", 2) + ["", ""])[:3]
    tool_input = json.dumps(data.get("tool_input", {}), ensure_ascii=False)
    response = data.get("tool_response", data.get("error", ""))
    if not isinstance(response, str):
        response = json.dumps(response, ensure_ascii=False)

    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session": data.get("session_id", ""),
        "server": server,
        "tool": name,
        "failed": data.get("hook_event_name") == "PostToolUseFailure",
        "in_chars": len(tool_input),
        "out_chars": len(response),
        "input": tool_input[:INPUT_PREVIEW],
    }

    project = Path(data.get("cwd") or ".").name or "unknown"
    log_dir = Path.home() / ".claude" / "mcp_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / f"{project}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    harness_emit("mcp.call", f"{server}/{name}", ok=not record["failed"], session=record["session"],
                 project=data.get("cwd", ""), source="mcp_log")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
