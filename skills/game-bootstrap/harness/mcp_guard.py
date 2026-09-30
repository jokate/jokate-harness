"""MCP 함정 가드 훅 (PreToolUse). <프로젝트>/.claude/mcp_guards.json 의 규칙에 걸리면
경고를 모델 컨텍스트에 주입한다. 차단하지 않는다.

규칙 필드:
  tool          툴 전체 이름(mcp__server__tool)에 대한 정규식
  input         (선택) JSON 직렬화한 입력에 대한 정규식
  require_keys  (선택) 입력에 반드시 있어야 하는 키 목록. 하나라도 없으면 걸린다
  warn          주입할 경고문
"""
import json
import re
import sys
from pathlib import Path


def matches(rule, tool, tool_input, input_text):
    if not re.search(rule["tool"], tool):
        return False
    if "input" in rule and not re.search(rule["input"], input_text):
        return False
    if "require_keys" in rule and all(k in tool_input for k in rule["require_keys"]):
        return False
    return True


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    tool = data.get("tool_name", "")
    if not tool.startswith("mcp__"):
        return

    rules_path = Path(data.get("cwd") or ".") / ".claude" / "mcp_guards.json"
    if not rules_path.is_file():
        return
    rules = json.loads(rules_path.read_text(encoding="utf-8")).get("rules", [])

    tool_input = data.get("tool_input") or {}
    input_text = json.dumps(tool_input, ensure_ascii=False)
    warnings = [r["warn"] for r in rules if matches(r, tool, tool_input, input_text)]
    if not warnings:
        return

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": "[mcp_guard] " + " / ".join(warnings),
        }
    }
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
