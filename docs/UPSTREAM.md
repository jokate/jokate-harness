# 빌려 온 바깥 스킬

| 원본 | 옮긴 곳 | 무엇 |
|---|---|---|
| mattpocock/skills `tdd` (SKILL · tests · mocking) | game-testing 3단계 · `references/good-tests.md` | 테스트 위치를 먼저 정한다 · 한 번에 한 조각 · 동어반복 같은 나쁜 모양 |
| mattpocock/skills `diagnosing-bugs` | game-testing 규칙 · `references/debugging.md` | 원인 모를 버그: 재현 고리 → 줄이기 → 가설 → 계측 → 회귀 → 정리 |
| mattpocock/skills `codebase-design` | game-architecture 과설계 가드 | 지우기 시험 · 구현체 하나면 가짜 경계 |
| mattpocock/skills `grilling` | game-architecture 질문 쓰는 법 | 사실은 직접 찾는다 · 지금 답할 수 있는 질문만 |

- **라이선스:** MIT, Copyright (c) 2026 Matt Pocock. 전문은 [third_party/mattpocock-skills-LICENSE](third_party/mattpocock-skills-LICENSE)에 있다.
- **복사가 아니라 옮김:** 게임 프로젝트에 맞게 우리말로 고쳐 옮겼다. 원본 사본은 비교용으로 `third_party/mattpocock-skills/`에 두었다.
- **업데이트 받기:**
  - 플러그인 `mattpocock-skills@claude-plugins-official`은 그대로 깔아 두었고, 공식 마켓 경로로 자동 업데이트된다.
  - `python tools/upstream_check.py`는 설치본과 사본을 비교해, 바뀐 원본과 그 내용을 옮긴 곳을 알려 준다(`--diff`로 줄 차이까지). install.py 끝에서도 한 줄 나온다.
  - 옮긴 곳을 검토한 뒤 `--accept`를 돌리면 사본, 버전, 커밋이 지금 설치본으로 올라간다.
- **옮기지 않은 것:**
  - improve-codebase-architecture: game-architecture와 겹친다. 하네스 쪽은 변경 이력을 근거로 삼고 추천을 표시하지 않는다.
  - domain-modeling · ADR: 프로젝트 주인의 용어집과 부딪친다.
  - to-questionnaire: 하네스의 질문 표로 충분하다.
  - 이슈 · 스펙 흐름(to-spec, to-tickets, triage 등): 플러그인이 그대로 제공한다.
  - writing-for-agents: 스킬 설명 줄을 줄이는 데 쓸 만하지만, 설명 줄을 바꾸면 스킬이 불리는 방식이 달라지므로 대조 시험과 함께 따로 한다.
- **고르지 않은 것:** grilling은 질문마다 추천 답을 붙이지만, game-architecture는 구조를 사용자가 고르게 하려고 추천을 표시하지 않는다. 그래서 그 부분은 옮기지 않았다.
