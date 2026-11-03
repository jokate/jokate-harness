# 하네스 글쓰기 — 에이전트가 읽는 문서를 쓰는 법

> 일부를 Matt Pocock 의 skills(`writing-for-agents`, MIT, Copyright (c) 2026 Matt Pocock)에서 빌려 이 하네스에 맞게 고쳤다.
> 라이선스: `docs/third_party/mattpocock-skills-LICENSE` · 원본 추적: `docs/UPSTREAM.md`.

- 고치기 전에 연다: 스킬 · 세션 시작 안내 · 규칙 파일. 포인터는 README 의 docs 줄과 `docs/UPSTREAM.md`.

## 1. 두 짐

| 짐 | 대상 | 한도 |
|---|---|---|
| 문맥 | 하네스 스킬 description 합 (`game-bootstrap` 포함) | ≤ 4,000 B (지금 2,377 B) |
| 문맥 | 세션 시작 안내 (가장 긴 경우) | ≤ 1,800 B |
| 문맥 | CLAUDE.local.md 스킬 라우팅 절 | ≤ 300 B |
| 문맥 | 하네스 몫 합계 | ≤ 7,000 B |
| 사람 | 어떤 문서가 있고 언제 쓰이나 | 없음 — 목차 한 곳 |

- 문맥 짐은 안 쓰여도 내는 값이다. 사람 짐은 사람이 색인이 되는 값이다. 포인터 없는 문서는 사람 짐이다.
- 포인터 뒤의 글(본문 · references)은 포인터 한 줄 값만 낸다.

## 2. 문맥 포인터

- description 도 문서 이름 줄도 포인터다. 열리는 때는 대상이 아니라 낱말이 정한다 — 안 열리면 낱말부터 고친다.
- 앞에 둔다: 동사가 끝에 오는 한국어에서는 요청에 나올 명사가 맨 앞이다.
- 갈래마다 트리거 하나: 한 갈래의 다른 말("검증해줘" · "이거 동작 확인")은 하나만 남긴다.
- 신원은 맨 앞에 한 번: "게임 프로젝트(UE / Unity)" 가 다른 프로젝트 · 플러그인 스킬(`mattpocock-skills:*`)과 가른다. 두 번 쓰지 않는다.
- 예외 — 줄이기 전에 잰다: 명령을 경로째 주는 라우팅 줄은 신원이 아니라 행동이다.
  - 위키 먼저로 바꾸며 cindex 줄을 줄이니 cindex 호출 22 → 11, Grep 28 → 41 (`docs/experience/routing-single-source.md`).
  - "코드 세부는 cindex" 를 붙이고 줄은 두니 22 · 27, 재현율 0.908 → 0.961.

예시 — 2026-10-27 설명 줄 6개 정리 (합 3,537 → 2,377 B, 대조 전 13/14 → 뒤 15/15, `VERIFICATION.md`):

```
전  game-testing  게임 프로젝트(UE / Unity)의 … "이거 동작 확인" … "Functional Test", "Unity Test Framework" …
뒤  game-testing  게임 프로젝트(UE / Unity)의 테스트 · 검증 — 구현 전에 "무엇으로 확인하나" 정하기, … 원인 모를 버그는
                  재현 고리부터. "테스트 짜줘", "검증해줘", "QA 체크리스트", "버그 원인 찾아줘". …
```

- 줄일 때 새 갈래가 생기면 촉발 말을 하나 더한다: "프로토타입으로 확인" 은 없을 때 플러그인 prototype 으로 샜다.

## 3. 정보 위계

| 층 | 들어가는 것 | 짐 |
|---|---|---|
| description · 세션 시작 안내 · 규칙 파일 | 무엇인지 + 갈래별 트리거 | 항상 |
| SKILL.md 본문 | 모든 갈래가 쓰는 절차 · 규칙 · 끝난 기준 | 부를 때 |
| references/ | 일부 갈래만 쓰는 형식 · 표 · 근거 | 포인터가 열 때 |
| scripts/ | 매번 같게 돌아야 하는 일 (`gq.py`) | 실행할 때만 |

- 내리는 시험: 모든 갈래가 쓰면 본문, 일부만 쓰면 references 로 내리고 본문엔 포인터 한 줄.
- 너무 적게 내리면 본문이 부풀고 너무 많이 내리면 필요한 글이 숨는다.
- 환경이 아는 것은 옮겨 적지 않는다. 이유 · 함정 · 안 적힌 관례만 적는다 (포인터 줄의 명령은 예외).

## 4. 단계와 끝난 기준

- 끝난 기준은 확인할 수 있고 빠짐없게 쓴다. "충분히 이해함" 은 일찍 끝내게 만든다.
- 먼저 기준을 날카롭게 한다. 서두름이 관찰될 때만 뒷단계를 서브에이전트 · 인계로 가린다.
- game-testing: 출력 끝 `검증 상태: 검증됨(자동) / 검증됨(수동) / 검증 안 됨 — <이유>` 한 줄이 없으면 안 끝났다.
- game-architecture: `render.py` 의 `읽기 점검:` 기준(첫 화면 30줄 · 긴 줄 0 · 구조도 1장 이상)을 맞출 때까지 고친다.

## 5. 나누기 · 이끄는 말 · 가지치기

- 순서로 나눈다: 뒷단계가 앞단계를 서두르게 하고 문맥 경계가 있을 때만 (예: 구현 뒤 리뷰).
- 새 스킬은 사용자가 따로 치는 낱말이 있거나 다른 스킬이 불러야 할 때만 (game-patterns: 0회 불림 → 합침).
- 이끄는 말: 풀어 쓴 문장 대신 모델이 아는 낱말 하나 — 땜질 · 국소 패치 · 가드 · 좌표 · 검증 안 됨.
- 해야 할 일을 앞에 쓴다: "grep 하기 전에 `cindex.py refs`" 가 앞, "grep 으로 추측하지 않는다" 가 뒤.
- 가지치기: 한 뜻은 한 곳 · 15일 0회 훅 · 스킬은 뺀다 · 모델이 이미 하는 일은 문장째 지운다.

## 6. 스킬 기계

- 모델이 부르는 스킬: `description` 에 갈래별 트리거. 사용자도 이름으로 부를 수 있다. 문맥 짐이 든다.
- 사용자만 부르는 스킬: `disable-model-invocation: true` + 사람용 한 줄 description.
- description 은 한 줄이다: `context_budget.py` 가 `^description:\s*(.+)$` 로 재서 여러 줄은 잘못 잰다.
- 라우터 스킬을 만들지 않는다: 하네스의 라우터는 세션 시작 안내의 `routing_lines` 다 (7절).

## 7. 하네스 고유 규칙

| 할 일 | 명령 · 곳 |
|---|---|
| 바꾸기 전 대조 | `python tools/harness_probe.py --spec <spec.json>` |
| 크기 재기 · 시험 | `python tools/context_budget.py <프로젝트>` · `test_context_budget.py` |
| 교훈 남기기 | `EXPERIENCE.draft.md` 확인 → `docs/experience/<이름>.md` + `INDEX.md` 한 줄 |
| 날짜별 기록 | `docs/VERIFICATION.md` |
| 바깥에서 빌리기 | `docs/UPSTREAM.md` 표 + `upstream.json` + `python tools/upstream_check.py [--diff \| --accept]` |

- 라우팅 줄 · description 을 고치면 스킬이 불리는 방식이 바뀐다. 느낌 말고 대조한다.
- 대조 비용: 과제 약 $0.3, 스킬 사례 약 $0.5~2. 표본이 작아 재현율 ±0.05 는 잡음이다.
- 라우팅은 세션 시작 안내 한 곳에만 둔다. 두 곳이면 구조 질문이 onboard 와 위키로 엇갈렸다.
- 스킬 이름만 적은 라우팅은 안 불렸다 (MNYS 61세션: game-onboard 0회). 명령을 줄 그대로 준다.
- 한도를 바꾸려면 이유를 `docs/experience` 에 먼저 쓴다. 더하면 다른 것을 뺀다.
- 빌린 `references/` 파일은 본문에 "MIT" 와 `docs/UPSTREAM.md` 를 적는다 (`test_upstream_check.py`).

## 8. 고치기 전 점검

1. 항상 들어가는 글인가? 맞으면 `context_budget.py` 전 · 후 B 를 적었나.
2. 지금 description 의 갈래를 적었나. 고친 뒤 하나도 안 빠졌나.
3. 갈래마다 트리거 하나 · 맨 앞은 요청 낱말 · 신원은 뺐나.
4. 명령 줄을 줄였다면 `harness_probe.py` 로 호출 횟수를 비교했나.
5. 본문엔 모든 갈래가 쓰는 것만 있나. 나머지는 references 에 있나.
6. 단계마다 확인할 수 있는 끝난 기준이 있나.
7. 금지만 쓴 줄은 없나. 같은 뜻이 두 곳에 없나.
8. description 은 한 줄인가. 본문 줄은 사실 하나 · 120자 이하인가.
9. 결과를 `docs/experience` 나 `VERIFICATION.md` 에 남겼나.
