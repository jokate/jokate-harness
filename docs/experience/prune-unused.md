# 쓰이지 않는 훅 · 스킬은 뺀다

## 상황
기능을 더하려 할 때, 하네스가 무거워졌다고 느낄 때, 세션마다 들어가는 글이 늘었을 때.

## 교훈
기능마다 실제로 동작한 횟수(이벤트 로그 `~/.claude/cache/game-harness/events.jsonl`, 대화 기록의 Skill 호출)를 먼저 센다.
오래 0회면 뺀다 — 특히 항상 들어가는 글(스킬 description · 세션 안내 · 규칙 파일)과 프롬프트마다 도는 훅. 부를 때만
들어가는 것(스킬 본문 · 스크립트 · 참고 문서)으로 옮길 수 있으면 옮긴다. 하네스 몫 항상 글은 `tools/context_budget.py` 로
재고 7,000 B 안에 둔다 — 더하면 다른 것을 뺀다.

## 근거
- Harness²(arXiv 2610.14224) 부품 떼기: 항상 글(prompt-related)을 떼면 −1.5점(가장 작음), 스킬 −5.3 · 스크립트 −3.7.
  부록의 지침: 항상 글은 가장 비싼 선택이고, 중복 · 일반론은 나머지를 흐린다.
- 2026-10-07~22 감사(MNYS 대화 기록 127세션 · 이벤트 로그): handoff(프롬프트마다 실행) 0회, diagram_view 0회(렌더 흔적 0),
  game-patterns 스킬 0회 — 그런데 그 description 이 992 B 로 하네스 스킬 중 가장 길었다. 하네스 몫 항상 글 8,194 B.

## 적용
`install.py` 의 `OBSOLETE_HOOKS` · `OBSOLETE_SKILLS` (설치하면 등록 · 파일을 지운다), game-patterns 는
`skills/game-architecture/references/patterns.md` 로. `tools/context_budget.py` 와 그 시험.
