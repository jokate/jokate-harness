# 빌려 온 바깥 스킬

## Matt Pocock skills (플러그인으로 깔아 둠)

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

## AWS AI-DLC (`awslabs/aidlc-workflows`, 깔지 않음)

| 원본 | 옮긴 곳 | 무엇 |
|---|---|---|
| 리뷰어 지식 `reviewing.md` · `stage-protocol-reviewer-repair` | game-architecture `references/review.md` 5 · 6절, 5절 4단계 | 판정 형식(심각도 · 위치 · 고칠 것) · 치명 1 또는 큼 3 이상이면 다시 · 고치기 2회 · 리뷰어에게 만든 쪽 생각을 안 넘김 |
| `build-and-test` 9단계 · `stage-protocol-loopback` · `stage-protocol-checkpoint` | game-testing `references/when-it-fails.md` · 규칙 · 테스트 문서, game-mcp 규칙 3 | 실패 사다리 · 기준 낮추기는 수정이 아님 · 되돌아간 기록 · 검증 명령 고정 · 못 돌린 검사는 통과가 아님 |
| `stage-protocol` 답 읽기 · `07-interaction-modes` | game-architecture 질문 쓰는 법 | 고름 + 지시는 한 번에 · 세 번째 수정부터 '지금 것으로 진행' · 그대로 / 고치기 / 새로 |
| `code-generation` 계획 승인 | game-architecture 5절 2단계 | 계획이 고른 안과 어긋날 때만 멈춤(사용자 결정 2026-11-03) |
| `stage-protocol-recovery` | game-design-doc 규칙 6 | 어긋나는 출처는 둘 다 인용 · 도중 자료는 근거지 이동 지시가 아님 |
| 리뷰어 지식 `reviewing.md`(독립 · 반박 자세) + Matt `grilling` | game-architecture 3절 · `references/critique.md` | 반대 검토: 누가 낸 안인지 모르는 비판자 · 안마다 오류 가능성 6항목 · 질문 두 바퀴 · 끝은 가장 덜 나쁜 안(사용자 요청 2026-11-03) |

- 옮긴 것은 프로토콜 · 안내 문서의 글 규칙이다. 원본 엔진(TS)이 그대로 강제하는지는 보지 않았다.
- 옮기지 않은 것: 엔진 · 33단계 · 14 에이전트 · 승인 기록(해시 영수증) · 감사 로그 · 작업 크기 점수(composer) · 센서 · Stop 훅 이어 가기.
  작업 크기별 절차 표와 배우는 고리도 넣지 않았다(사용자 결정 2026-11-03 — 국소 패치 가드 약화 · 자동 기억과 겹침).
- 깔지 않는 까닭: 설치기가 실행 파일을 깔고 사용자 PATH 를 바꾸며, 늘 들어가는 글이 약 50KB 다.

## 공통

- **라이선스:** Matt Pocock skills 는 MIT(Copyright (c) 2026 Matt Pocock, [전문](third_party/mattpocock-skills-LICENSE)), AI-DLC 는 MIT-0(Amazon.com, [전문](third_party/aidlc-workflows-LICENSE)). 옮긴 references 머리에 출처를 적었다.
- **복사가 아니라 옮김:** 게임 프로젝트에 맞게 우리말로 고쳐 옮겼다. 원본 사본은 비교용으로 `third_party/mattpocock-skills/`(19개) · `third_party/aidlc-workflows/`(9개)에 두었다.
- **추천:** 선택지 · 질문 · 후보 · 인터페이스 안에 `추천: X — 이유 한 줄`을 붙인다. 고르는 것은 그대로 사용자이고, 추천을 붙여도 스킬은 멈춘다(사용자 결정 2026-10-27).
- **업데이트 받기:**
  - 플러그인 `mattpocock-skills@claude-plugins-official`은 그대로 깔아 두었고, 공식 마켓 경로로 자동 업데이트된다.
  - AI-DLC 는 깔지 않는다. `python tools/upstream_check.py --remote` 가 GitHub main 의 같은 파일을 받아 사본과 비교한다. 네트워크가 안 되면 "확인 못 함"이라고 따로 쓴다.
  - `python tools/upstream_check.py`는 원본과 사본을 비교해, 바뀐 원본과 그 내용을 옮긴 곳을 알려 준다(`--diff`로 줄 차이까지). install.py 끝에서도 한 줄 나온다(네트워크 없이).
  - 옮긴 곳을 검토한 뒤 `--accept`를 돌리면 사본, 버전, 커밋이 지금 원본으로 올라간다.
- **Matt Pocock 쪽에서 옮기지 않은 것:**
  - 이슈 · 스펙 · 작업 흐름(to-spec, to-tickets, triage, wayfinder, implement, handoff, teach, retro, research, pr, wizard, grill-me, to-questionnaire, ask-matt, setup): 플러그인이 그대로 제공한다.
  - git-guardrails: push 를 막는다. 하네스는 push 를 사용자에게 묻는 방식이라 겹친다.
- **겹침:** 플러그인 스킬은 `mattpocock-skills:<이름>`으로 따로 불린다. 대조 시험에서 "프로토타입으로 확인"이 플러그인 prototype 으로 새던 것은 설명 줄을 고친 뒤 game-architecture 로 돌아왔다. 스킬 하나를 끄려면 권한 거부 규칙 `Skill(mattpocock-skills:<이름>)`을 쓴다.
