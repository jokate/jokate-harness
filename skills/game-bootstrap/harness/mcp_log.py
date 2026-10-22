"""MCP 호출 계측 훅. PostToolUse / PostToolUseFailure 의 stdin JSON 을 받아
~/.claude/mcp_logs/<프로젝트>.jsonl 에 한 줄씩 남긴다. 어떤 경우에도 세션을 막지 않는다.

실패하면 가드 규칙 후보도 쌓는다: <프로젝트>/.claude/mcp_guards.pending.json 에 {도구, 오류 요지, 입력 예, 횟수, 처음 · 마지막}.
같은 도구 · 같은 오류 요지는 한 줄로 합쳐 횟수만 는다. 규칙(mcp_guards.json)으로 올리는 것은 game-mcp 가 사용자와 정한다 —
근거(실패 기록) 없는 규칙을 만들지 않고, 후보를 자동으로 규칙에 넣지도 않는다(Harness² 의 '대조로 뒷받침된 교훈만 남긴다').
"""
import json
import re
import sys
import time
from pathlib import Path

try:
    from harness_events import emit as harness_emit
except Exception:  # 이벤트 로그가 설치되지 않았어도 훅은 돈다
    def harness_emit(*a, **k):
        pass

INPUT_PREVIEW = 300
PENDING_MAX = 50


def error_gist(text) -> str:
    """오류 요지: 첫 줄 120자. 경로 · 따옴표 안 값 · 숫자를 지워 같은 종류의 실패를 한 줄로 모은다."""
    first = next((ln.strip() for ln in str(text).splitlines() if ln.strip()), "")[:200]
    first = re.sub(r"[A-Za-z]:[\\/]\S+|/\S+/\S+", "<경로>", first)
    first = re.sub(r"'[^']*'|\"[^\"]*\"", "<값>", first)
    return re.sub(r"\d+", "N", first)[:120]


def add_pending(root: Path, tool: str, error, tool_input: str, now: str) -> None:
    """실패 하나를 가드 규칙 후보에 더한다. <root>/.claude 가 없으면(세팅 안 된 곳) 쓰지 않는다."""
    if not (root / ".claude").is_dir():
        return
    path = root / ".claude" / "mcp_guards.pending.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {"_description": "MCP 실패에서 모은 가드 규칙 후보. game-mcp 가 사용자와 검토해 mcp_guards.json 으로 올리거나 지운다.",
               "pending": []}
    gist = error_gist(error)
    for p in doc.setdefault("pending", []):
        if p.get("tool") == tool and p.get("error") == gist:
            p["count"] = p.get("count", 0) + 1
            p["last"] = now
            break
    else:
        doc["pending"].append({"tool": tool, "error": gist, "example_input": tool_input[:INPUT_PREVIEW],
                               "count": 1, "first": now, "last": now})
    doc["pending"] = doc["pending"][-PENDING_MAX:]
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    if record["failed"]:
        try:
            add_pending(Path(data.get("cwd") or "."), tool, data.get("error") or response, tool_input, record["ts"])
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
