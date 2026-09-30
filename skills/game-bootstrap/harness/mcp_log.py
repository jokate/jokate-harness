"""MCP 호출 계측 훅. PostToolUse / PostToolUseFailure 의 stdin JSON 을 받아
~/.claude/mcp_logs/<프로젝트>.jsonl 에 한 줄씩 남긴다. 어떤 경우에도 세션을 막지 않는다."""
import json
import sys
import time
from pathlib import Path

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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
