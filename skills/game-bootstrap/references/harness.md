# 하네스 — 유저 레벨 훅

## 목차
1. 설계
2. 설치
3. 프로젝트 쪽 선언 파일
4. 검증 방법

## 1. 설계

- 훅은 `~/.claude/settings.json` 에 **한 번만** 등록한다. 프로젝트별 차이는 프로젝트의 `.claude/*.json` 선언 파일로 표현한다.
- 모든 훅은 입력 JSON 의 `cwd`(SessionStart 는 `CLAUDE_PROJECT_DIR` 우선)에서 위로 올라가며 선언 파일을 찾는다. 없으면 아무것도 안 한다.
- 모든 훅은 예외를 삼킨다 — 훅 실패가 세션을 막지 않는다.
- 같은 종류의 요청(새 프로젝트, 새 세션 작업)이 오면 프로젝트 선언 파일만 추가한다. 유저 settings 는 그대로.

트레이드오프: 프로젝트 `.claude/settings.json` 에 훅을 직접 넣는 방식(공식 지원)은 선언이 한 파일로 끝나지만,
파이썬 절대 경로 같은 머신 의존 값이 저장소에 들어간다. 이 설계는 그것을 피하는 대신 유저 레벨 설치가 선행 조건이다.

## 2. 설치

저장소 루트에서 `python install.py` — 훅 복사와 아래 조각 출력(파이썬 경로 채움)을 해 준다. 수동이면:
1. 이 스킬의 `harness/*.py` 를 `~/.claude/hooks/` 로 복사한다.
2. `~/.claude/settings.json` 의 `hooks` 에 아래를 합친다. `<PYTHON>` 은 그 머신의 python.exe 절대 경로 (`where python`).

```json
{
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command", "command": "<PYTHON>",
                  "args": ["<HOME>/.claude/hooks/session_start.py"], "timeout": 60},
                 {"type": "command", "command": "<PYTHON>",
                  "args": ["<HOME>/.claude/hooks/game_context.py"], "timeout": 15}]}
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "<PYTHON>",
                  "args": ["<HOME>/.claude/hooks/game_route.py"], "timeout": 5}]}
    ],
    "PreToolUse": [
      {"matcher": "mcp__.*",
       "hooks": [{"type": "command", "command": "<PYTHON>",
                  "args": ["<HOME>/.claude/hooks/mcp_guard.py"], "timeout": 5}]}
    ],
    "PostToolUse": [
      {"matcher": "mcp__.*",
       "hooks": [{"type": "command", "command": "<PYTHON>",
                  "args": ["<HOME>/.claude/hooks/mcp_log.py"], "timeout": 10, "async": true}]}
    ],
    "PostToolUseFailure": [
      {"matcher": "mcp__.*",
       "hooks": [{"type": "command", "command": "<PYTHON>",
                  "args": ["<HOME>/.claude/hooks/mcp_log.py"], "timeout": 10, "async": true}]}
    ]
  }
}
```

`command` + `args` 형식과 `async` 는 이 설정을 만든 머신(2026-10 Claude Code)에서 동작 중인 형식이다. 다른 버전에서 안 되면
`"command": "<PYTHON> <스크립트경로>"` 한 줄 형식으로 바꿔 본다 (확인 필요).

## 3. 프로젝트 쪽 선언 파일

| 파일 | 읽는 훅 | 형식 |
|---|---|---|
| `.claude/session_start.json` | session_start.py | `{"commands": [{"run": [스크립트, 인자...], "timeout": 초}]}` — `.py` 는 훅의 파이썬으로 실행, `~` 펼침, 루트에서 실행, stdout 은 컨텍스트로 (9000자 상한) |
| `.claude/mcp_guards.json` | mcp_guard.py | `{"rules": [{"tool": 정규식, "input": 정규식?, "require_keys": [..]?, "warn": 문장}]}` |
| `.claude/gq.json` | gq.py | `{"exclude": ["루트 기준 경로 접두사"]}` |

## 4. 검증 방법

훅은 stdin JSON 으로 직접 돌려볼 수 있다:

```bash
echo '{"cwd":"<프로젝트 경로>"}' | python ~/.claude/hooks/session_start.py
echo '{"cwd":"<프로젝트 경로>","tool_name":"mcp__unreal__duplicate_asset","tool_input":{"path":"AM_Test"}}' | python ~/.claude/hooks/mcp_guard.py
```

SessionStart 가 실제 세션 시작에 붙는지는 새 세션에서만 확인된다 — 인덱스 시각(`gq.py status`)으로 본다.
