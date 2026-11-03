# 빌려 온 바깥 스킬

| 원본 (mattpocock/skills) | 옮긴 곳 | 무엇 |
|---|---|---|
| `tdd` (SKILL · tests · mocking) | game-testing 3단계 · `references/good-tests.md` | 테스트 위치를 먼저 정한다 · 한 번에 한 조각 · 동어반복 같은 나쁜 모양 · 목은 바깥 경계에만 |
| `diagnosing-bugs` | game-testing 규칙 · `references/debugging.md` | 원인 모를 버그: 재현 고리 → 줄이기 → 가설 → 계측 → 회귀 → 정리 |
| `codebase-design` (SKILL · DEEPENING · DESIGN-IT-TWICE) | game-architecture 과설계 가드 · `references/interface-design.md` | 지우기 시험 · 구현체 하나면 가짜 경계 · 의존 4종류 · 두 번 설계(서브에이전트 3안 비교) |
| `grilling` | game-architecture 질문 쓰는 법 | 사실은 직접 찾는다 · 지금 답할 수 있는 질문만 · 질문마다 추천 답 |
| `prototype` (SKILL · LOGIC · UI) | game-architecture 3절 · `references/prototype.md` | 버리는 프로토타입: 규칙 · 상태는 HTML 한 장, 느낌 · 화면은 엔진 안 CVar 변형 |
| `improve-codebase-architecture` (SKILL · HTML-REPORT) | game-architecture 0절 · `references/scan.md` | 구조 점검: 범위 먼저 · 마찰 찾기 · 후보 표 · 추천 · 고른 뒤 1절부터 |
| `code-review` | game-architecture 5절 4단계 · `references/review.md` | 구현 뒤 리뷰: 규칙 축 · 사양 축 서브에이전트 · 게임용 냄새 12개 |
| `domain-modeling` (SKILL · GLOSSARY-FORMAT · ADR-FORMAT) | game-design-doc 규칙 5 · `references/terms.md` · game-architecture 1절 | 용어집 말로 쓰기 · 어긋나면 바로 짚기 · 결정 기록은 세 조건일 때만 |
| `writing-for-agents` (SKILL · SKILL-MECHANICS) | [WRITING.md](WRITING.md) · 스킬 설명 줄 6개 | 두 짐 · 문맥 포인터 · 갈래당 촉발 하나 · 가지치기 |

- **라이선스:** MIT, Copyright (c) 2026 Matt Pocock. 전문은 [third_party/mattpocock-skills-LICENSE](third_party/mattpocock-skills-LICENSE)에 있고, 옮긴 references 머리에 출처를 적었다.
- **복사가 아니라 옮김:** 게임 프로젝트에 맞게 우리말로 고쳐 옮겼다. 원본 사본은 비교용으로 `third_party/mattpocock-skills/`에 두었다(19개 파일).
- **추천:** 선택지 · 질문 · 후보 · 인터페이스 안에 `추천: X — 이유 한 줄`을 붙인다. 고르는 것은 그대로 사용자이고, 추천을 붙여도 스킬은 멈춘다(사용자 결정 2026-10-27).
- **업데이트 받기:**
  - 플러그인 `mattpocock-skills@claude-plugins-official`은 그대로 깔아 두었고, 공식 마켓 경로로 자동 업데이트된다.
  - `python tools/upstream_check.py`는 설치본과 사본을 비교해, 바뀐 원본과 그 내용을 옮긴 곳을 알려 준다(`--diff`로 줄 차이까지). install.py 끝에서도 한 줄 나온다.
  - 옮긴 곳을 검토한 뒤 `--accept`를 돌리면 사본, 버전, 커밋이 지금 설치본으로 올라간다.
- **옮기지 않은 것:**
  - 이슈 · 스펙 · 작업 흐름(to-spec, to-tickets, triage, wayfinder, implement, handoff, teach, retro, research, pr, wizard, grill-me, to-questionnaire, ask-matt, setup): 플러그인이 그대로 제공한다.
  - git-guardrails: push 를 막는다. 하네스는 push 를 사용자에게 묻는 방식이라 겹친다.
- **겹침:** 플러그인 스킬은 `mattpocock-skills:<이름>`으로 따로 불린다. 대조 시험에서 "프로토타입으로 확인"이 플러그인 prototype 으로 새던 것은 설명 줄을 고친 뒤 game-architecture 로 돌아왔다. 스킬 하나를 끄려면 권한 거부 규칙 `Skill(mattpocock-skills:<이름>)`을 쓴다.
