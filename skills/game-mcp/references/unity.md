# Unity MCP

## 목차
1. 선택지
2. 주의

## 1. 선택지

| 종류 | 설명 | 상태 |
|---|---|---|
| Unity 공식 MCP | Unity 6 이상, AI Assistant 패키지, 베타 | 문서 경유 정보, **검증 안 됨** https://unity.com/blog/unity-ai-mcp-how-to-get-started |
| IvanMurzak/Unity-MCP | 커뮤니티. 설정 시 프로젝트용 스킬 자동 생성, CLI 제공 | **검증 안 됨** https://github.com/IvanMurzak/Unity-MCP |
| CoderGamester/mcp-unity | 커뮤니티 | **검증 안 됨** |

## 2. 주의

- 애셋 간 참조는 GUID 다. 경로를 바꾸는 조작(이동·리네임)은 `.meta` 를 같이 옮기는지 확인 — 에디터 API(`AssetDatabase.MoveAsset`)를 거치지 않은 파일 이동은 참조를 끊는다.
- 텍스트 직렬화 프로젝트는 YAML 을 직접 고치고 싶어지지만, 에디터가 열려 있으면 덮어써진다. 에디터 경유로.
- 플레이 모드 중의 변경은 종료 시 사라진다. 조작 전 모드 확인.
- 스크립트 변경은 도메인 리로드를 부른다. 리로드 중 MCP 호출은 실패할 수 있다 — 컴파일 완료를 기다린 뒤 재조회.
- 실패 사례는 UE 와 같은 방식으로 `<프로젝트>/.claude/mcp_guards.json` 에 쌓는다.
