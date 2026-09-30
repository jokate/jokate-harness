---
name: game-mcp
description: 게임 엔진 에디터를 MCP 로 조작할 때의 운용 규칙 (Unreal MCP, Unity MCP 등). 에디터 MCP 도구(mcp__unreal__*, mcp__unity__* 등)로 애셋·BP·레벨·머티리얼·애니메이션을 만들거나 고치기 전에, MCP 호출이 실패하거나 결과가 이상할 때, "에디터에서 만들어줘", "BP 수정", "애셋 생성", "MCP 로 확인", "MCP 가드 추가", "MCP 로그 봐줘" 같은 요청에 쓴다. 읽기 먼저·쓰고 나서 재조회·실패는 가드 규칙으로 남기는 것이 핵심이다.
---

# game-mcp — 에디터 MCP 운용

에디터 MCP 는 강력하지만 **조용히 틀린다.** 호출은 성공했는데 에디터의 후처리(PostEditChange 등)가
안 돌아서 애셋이 깨진 채로 저장되는 식이다. 그래서 세 가지를 지킨다.

## 규칙

1. **읽기 먼저** — 쓰기 전에 대상의 현재 상태를 조회한다 (get_* / describe_* / export_*). 추측한 경로·이름으로 쓰지 않는다.
2. **쓰고 나서 재조회** — 쓰기 호출의 성공 응답은 검증이 아니다. 같은 속성을 다시 읽어 값이 들어갔는지 본다. 컴파일이 필요한 애셋(BP, 머티리얼, StateTree 등)은 컴파일·검증 도구까지.
3. **실패는 가드로 남긴다** — 같은 함정을 두 번 밟았으면 `<프로젝트>/.claude/mcp_guards.json` 에 규칙을 추가한다. PreToolUse 훅이 다음 호출 때 경고를 주입한다 (형식은 아래).
4. **저장은 명시적으로** — 대량 변경 후 저장 전에 사용자에게 무엇이 바뀌는지 요약하고 확인. 삭제·이동·리네임·리다이렉터 정리는 되돌리기 어렵다 — 매번 확인.
5. **도구가 없으면 스크립트** — 전용 도구가 없는 조작은 에디터 Python(`execute_python` 류)으로 하되, 무엇을 실행하는지 코드를 보여주고 실행.
6. **MCP 는 외부 시스템이다** — 에디터가 꺼져 있거나 세션이 끊기면 모든 호출이 실패한다. 연결 오류가 연속되면 사용자에게 에디터 상태 확인을 요청하고 멈춘다.

## 가드 규칙 형식 (`<프로젝트>/.claude/mcp_guards.json`)

```json
{
  "rules": [
    {
      "tool": "mcp__unreal__duplicate_asset$",
      "input": "AM_|[Mm]ontage",
      "warn": "몽타주 복제: 세그먼트가 0초에서 시작하지 않으면 길이 0 으로 깨진다. 새로 만들 것."
    },
    {
      "tool": "mcp__unreal__set_object_property$",
      "require_keys": ["actor", "blueprint_path"],
      "warn": "모든 인자를 명시해야 한다."
    }
  ]
}
```

- `tool`: 도구 전체 이름 정규식. `input`: 입력 JSON 직렬화에 대한 정규식(선택). `require_keys`: 없으면 경고할 키(선택).
- 차단하지 않고 경고만 주입한다. 차단이 필요하면 훅에서 `permissionDecision: "deny"` 로 바꿔야 한다 (훅 수정은 사용자 승인 후).
- 훅 설치 상태는 `game-bootstrap` 의 하네스 절 참고.

## 로그로 함정 찾기

PostToolUse 훅이 `~/.claude/mcp_logs/<프로젝트폴더>.jsonl` 에 호출마다 한 줄(도구, 실패 여부, 입출력 크기)을 남긴다.
"자주 실패하는 도구", "출력이 큰 도구"를 보고 싶으면 이 파일을 집계한다. 실패가 몰린 도구는 가드 후보다.

## 엔진별

- Unreal: [references/ue.md](references/ue.md) — MCP 선택지, 알려진 함정 유형, 조회 순서
- Unity: [references/unity.md](references/unity.md) — MCP 선택지, 직렬화 관련 주의
