"""UserPromptSubmit: 게임 프로젝트에서 요청을 분류해 맞는 스킬을 요청 바로 옆에 안내한다.
세션 시작 때의 라우팅 안내(game_context.py)만으로는 CLAUDE.md 없는 프로젝트에서 "구현해줘"가
바로 코드 작성으로 가는 것이 평가에서 확인됐다 (2026-10-01). 결정 시점에 가까운 곳에 넣는다.

분류는 키워드 규칙이다. 틀릴 수 있으므로 안내만 하고 강제하지 않는다. 게임 프로젝트가 아니면 아무것도 안 한다.
규칙을 바꾸려면 RULES 만 고친다 (위에서부터 처음 맞는 규칙 하나).
"""
import json
import os
import re
import sys
from pathlib import Path

RULES = [
    ("game-testing", "테스트·검증 요청", r"테스트|검증해|QA|체크리스트|\btests?\b"),
    ("game-design-doc", "기획서 기반 요청", r"기획서|기획|사양|GDD|\bspec\b"),
    ("game-mcp", "에디터 조작·조회 요청", r"에디터에서|에디터로|블루프린트|\bBP_|애셋|에셋|머티리얼|나이아가라|\bMCP\b"),
    ("game-onboard", "파악·조회 질문", r"파악|어디에|어디서|어디 있|시그니처|알려줘|설명해|뭐가 있|구성이|어떻게 (구현|동작|돼)"),
    ("game-architecture", "기능 추가·구현·설계 요청", r"구현|추가|만들어|넣어|붙여|설계|구조 잡|리팩터|개선|바꿔|\bimplement|\badd\b|\brefactor"),
]


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    prompt = data.get("prompt") or ""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from game_context import detect
    root, engine = detect(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    if root is None or not prompt.strip():
        return
    for skill, label, pattern in RULES:
        if re.search(pattern, prompt, re.I):
            msg = (f"[game-harness] 요청 분류: {label} ({engine}). "
                   f"다른 조회·코드 읽기·수정보다 먼저 `{skill}` 스킬을 호출하고 그 절차를 따른다. "
                   "분류가 틀렸으면 무시한다.")
            if skill == "game-architecture":
                msg += " 구조 선택지를 내고 사용자가 고를 때까지 코드를 쓰지 않는다."
            sys.stdout.buffer.write(msg.encode("utf-8"))
            return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
