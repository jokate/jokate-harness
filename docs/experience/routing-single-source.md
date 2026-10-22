# 라우팅은 한 곳에 — 그러나 인덱스 명령 줄은 줄이지 않는다

## 상황
스킬 라우팅이 규칙 파일(CLAUDE.local.md · CLAUDE.md)과 세션 시작 안내(game_context)에 둘 다 있을 때, 또는 라우팅 줄을
줄여 항상 들어가는 글을 아끼려 할 때.

## 교훈
- 라우팅은 세션 시작 안내 한 곳에만 둔다. 규칙 파일에는 "안내는 [game-harness] 줄에 있다" 한 줄만. 두 곳이면 어긋난다.
- 인덱스 명령 줄(`cindex.py refs/callers/derived/impact` 경로째 · "grep 으로 추측하지 않는다")은 줄이지 않는다 — 줄이면
  모델이 그 도구를 덜 쓴다. 글을 아끼려면 중복 · 안 쓰는 스킬 설명에서 아낀다.
- 위키가 있으면 구조 질문은 위키 먼저이되, "코드 세부는 cindex 로 확인"을 같은 줄에 붙인다 — 위키로만 보내면 인덱스 사용이 준다.

## 근거 (tools/harness_probe.py, MNYS 10-17 스냅숏, Sonnet, 2026-10-22)
| 팔 | 정답 재현율 (8과제 × 2) | 스킬 사례 | $/회 | cindex 호출 | Grep 도구 |
|---|---|---|---|---|---|
| X 지금 (라우팅 두 곳, 구조 → game-onboard / 위키 엇갈림) | 0.908 | 13/18 (맞는 스킬 5/5) | 0.356 | 22 | 28 |
| Y 한 곳 · 위키 먼저 · cindex 줄 줄임 | 0.920 | 14/18 (5/5) | 0.360 | 11 | 41 |
| Z 한 곳 · 위키 먼저 + "코드 세부는 cindex" · cindex 줄 그대로 | 0.961 | (Y 와 같은 라우팅) | 0.358 | 22 | 27 |

- 새 프로젝트(bootstrap 만 한 fixture 3개, run_evals): 템플릿의 라우팅 절을 한 줄 안내로 바꿔도 8/8 (지금 템플릿도 8/8),
  비용 $1.10 → $0.96. 한 줄을 더 줄인 지금 문구(라우팅 절 170 B)로 다시: 8/8 · $0.96.
- 하네스 몫 항상 글(tools/context_budget.py, MNYS): 8,194 B → 6,935 B.
- 한계: 과제 8개 × 2회 · 스킬 사례 1회라 작은 차이(재현율 ±0.05)는 잡음이다. Z 는 X · Y 와 다른 시간에 돌았다.

## 적용
`game_context.routing_lines` (옛 search_routing · 라우팅 줄 대체), `claude-md-template.md` 의 스킬 라우팅 절,
MNYS `CLAUDE.local.md` (백업 `~/.claude/cache/game-harness/mnys-CLAUDE.local.md.bak-20261022`).
