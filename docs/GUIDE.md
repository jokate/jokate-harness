# game-harness 사용 가이드

사람이 읽는 문서다. 이 저장소로 Claude Code 작업 환경을 세팅하고, 지시하고, 쓰면서 고치는 법.
기준일 2026-10-01. Claude Code 2.1.x, UE 5.x / Unity 6 대상.

## 목차
1. 이게 뭔가
2. 층 구조
3. 설치와 새 프로젝트 세팅
4. 언제 무엇이 적용되나
5. Claude 에게 지시하는 법
6. 요청 템플릿
7. 쓰면서 고치는 법
8. 출처

---

## 1. 이게 뭔가

게임 프로젝트용 **하네스**다. 모델을 바꾸는 게 아니라, 모델을 둘러싼 환경(지시·맥락·도구·강제·평가)을 설계해서
어느 프로젝트에 들어가도 같은 방식으로 일하게 만든다.

| 하네스 요소 | 이 저장소의 구현 | 역할 |
|---|---|---|
| 지시 | 프로젝트 `CLAUDE.md` (bootstrap 이 템플릿으로 생성) | 항상 필요한 규칙 |
| 필요할 때 가져오는 맥락 | `skills/game-*` (SKILL.md + references) | 트리거될 때만 로드 |
| 조회 도구 | `gq.py`(프로젝트), `ue_q.py`(엔진) | 통째로 읽지 않고 좌표로 |
| 센서 | `evidence.py` (변경 이력 → hotspot·co-change) | 구조 판단의 근거를 계측 |
| 결정론적 강제 | 훅: SessionStart 인덱스 갱신·라우팅, MCP 가드·로그 | 모델 판단에 기대지 않는 것 |
| 평가 | `evals/run_evals.py` | 하네스가 의도대로 도는지 재검증 |

핵심 목적은 하나다: **AI 가 한 기능에 매몰되어 국소 패치를 쌓는 것을 막고, 그 프로젝트에서 유지보수가 가장 좋은 구조를 근거와 함께 사람이 고르게 한다.**

## 2. 층 구조

| 층 | 스킬 | 언제 | 산출 |
|---|---|---|---|
| 0 | `game-bootstrap` | `/game-bootstrap` 직접 호출 | 프로젝트 CLAUDE.md, 인덱스 갱신 선언, MCP 가드 파일 |
| 1 | `game-onboard` | 구조·위치·엔진 API 질문 | 좌표 (file:line, 모듈 그래프) |
| 1 | `game-design-doc` | 기획서 읽기·기획과 구현 대조 | 사양 표, 구현 대응, 판단 대기, 어긋남 |
| 2 | `game-architecture` | 기능 추가·구현·설계 요청 (코드 전) | 선택지 A/B/C + "다음 요청 때 고칠 곳" + 근거 그림 → **사람이 고른다** |
| 2 | `game-patterns` | 패턴 비교 | 증상 → 후보 패턴 → 엔진 관용구, 트레이드오프 한 줄 |
| 3 | `game-testing` | 검증 기준·테스트 | 완료 기준 먼저, 검증됨(자동/수동)/검증 안 됨 표기 |
| 4 | `game-mcp` | 에디터 MCP 조작 | 읽기 먼저·쓰고 재조회·실패는 가드로 |

흐름: 기획서(design-doc) → 사양 표 → 구조 조사(architecture) → 사람 선택 → 완료 기준(testing) → 구현 → 새 컨텍스트 리뷰.

새 엔진을 지원하려면 각 스킬의 `references/<엔진>.md` 한 벌만 추가한다. SKILL.md 는 고치지 않는다.

## 3. 설치와 새 프로젝트 세팅

**머신당 한 번** — Windows 면 `install.bat` 더블클릭으로 끝. 인자를 줄 때는:

```
python install.py            # 스킬 복사 + 훅 복사, settings 조각 출력
python install.py --link     # 스킬을 저장소로 링크 (이 저장소를 고치면 바로 반영 — 개발용)
```

출력된 `hooks` 조각을 `~/.claude/settings.json` 에 합친다 (자동으로 고치지 않는다).

**프로젝트마다**

Claude Code 에서 `/game-bootstrap` → 감지 결과 확인 → 규칙 모듈 선택 → 생성 승인.
사내 저장소면 개인 선호는 `CLAUDE.local.md`(커밋 안 함), 팀 합의만 `CLAUDE.md`.

## 4. 언제 무엇이 적용되나

2026-10-01 헤드리스 세션으로 실측한 결과 (`docs/VERIFICATION.md`).

| 구성 | 적용 시점 | 상태 |
|---|---|---|
| 스킬 목록 등록 | 세션 시작 | 검증됨 |
| 라우팅 안내 (`[game-harness]` 줄) | 세션 시작, `.uproject`/Unity 프로젝트일 때만 | 검증됨. 단독으로는 CLAUDE.md 없는 프로젝트의 트리거를 못 올렸다 |
| 프로젝트 인덱스 갱신 | 세션 시작, `.claude/session_start.json` 이 있을 때만 | 검증됨 |
| 스킬 자동 트리거 | 요청이 description 과 맞을 때 모델이 판단 | **확률적.** 첫 평가에서 4건 중 CC·엔진·테스트는 걸렸고, 작은 필드 추가·CLAUDE.md 없는 프로젝트는 안 걸림 |
| `game-bootstrap` | 직접 호출할 때만 | 설계상 |
| MCP 가드·로그 | MCP 호출마다 | 기존부터 동작 |

실측에서 얻은 가장 중요한 사실: **실질적인 스위치는 프로젝트 CLAUDE.md 였다.** CLAUDE.md 에 "기능 요청은 구조부터" 규칙이 있는
프로젝트는 스킬이 안 불려도 구조 판단으로 갔고, 없는 프로젝트는 스킬도 안 불렸다. 그래서 새 프로젝트는 bootstrap 부터.

## 5. Claude 에게 지시하는 법

### 어디에 무엇을 두나

| 무엇 | 어디 | 기준 |
|---|---|---|
| 항상 필요한 사실·규칙 | `CLAUDE.md` / `CLAUDE.local.md` | 지우면 실수하는 것만. 200줄 미만 |
| 특정 경로에서만 필요한 규칙 | `.claude/rules/*.md` + `paths` | 예: `Source/**/*.h` 헤더 규칙 |
| 가끔 필요한 절차·지식 | 스킬 | 트리거될 때만 본문 로드 |
| 출력이 큰 조사 | 서브에이전트 | 결론만 받아 메인 컨텍스트를 아낀다 |
| 반드시 지켜야 하는 금지 | 훅 | 규칙 파일의 "하지 마"는 어길 수 있다 |
| 외부 시스템 | MCP | 에디터, 이슈 트래커 |

### 요청 한 건의 구조

```
[목표]   무엇이 되어야 하나 — 관찰 가능한 결과로
[맥락]   관련 문서·파일·애셋 좌표 (모르면 "찾아서")
[제약]   건드리면 안 되는 것, 따라야 할 기존 패턴
[완료]   무엇으로 확인하나 (테스트 / PIE 에서 무엇을 본다)
[산출]   코드 / 선택지만 / 문서 / 그림
[가설]   (선택) 내 생각 한 줄 — 틀려도 됨
```

- 동사를 분명히. "제안해줘"는 제안만 한다. 고치길 원하면 "고쳐라".
- 규칙에는 이유를 붙인다. 이유가 있으면 비슷한 경우로 일반화한다.
- 긴 자료는 앞에, 질문은 끝에.
- `IMPORTANT`, `CRITICAL`, `MUST` 는 쓰지 않는다. 최신 모델은 과잉 반응한다.

### 세션 운용

- 관련 없는 작업 사이에는 `/clear`. 같은 수정을 두 번 넘게 교정했으면 `/clear` 후 더 나은 요청으로.
- 큰 작업은 plan mode 로 탐색·계획 먼저. 한 문장으로 설명되는 수정은 계획 생략.
- 조사는 "서브에이전트로 조사해라"라고 명시.
- 구현 후 "새 컨텍스트로 이 diff 리뷰해라". 단, 리뷰 지적을 전부 따르면 과설계로 간다.
- 스킬을 콕 집어 부르고 싶으면 이름을 말한다 ("game-architecture 로"). 자동 트리거는 확률적이다.

## 6. 요청 템플릿

**기능 구현**
```
<기능>을 추가하고 싶다. 기획: <문서#절>.
구현 전에 구조부터 조사해서 선택지와 근거 그림을 내라. 고르는 건 내가 한다.
완료 기준: <관찰 가능한 결과>.
```

**기획서 → 사양**
```
<문서#절> 기획을 사양 표로 뽑고 구현과 대조해라. 빈칸은 판단 대기로, 어긋남은 보고만.
```

**버그**
```
증상: <무엇을 하면 무엇이 된다. 기대는 무엇>. 재현: <맵/캐릭터/입력>.
원인만 먼저. 수정은 원인 확인 후 내가 승인하면.
```

**조사**
```
<질문>. 서브에이전트로 조사하고 결론과 좌표(file:line)만 가져와라.
```

**에디터 작업 (MCP)**
```
<애셋>에 <변경>. 쓰기 전에 현재 상태를 조회해서 보여주고, 쓴 뒤 재조회로 확인해라.
```

**설계 상담**
```
<문제 증상>. 후보 패턴 2~3개를 얻는 것/잃는 것 한 줄씩. 추천은 하지 마라.
```

## 7. 쓰면서 고치는 법

하네스는 처음부터 완벽할 수 없다. 실패를 **어디에 반영하는지**만 정해 둔다.

| 실패 | 고칠 곳 |
|---|---|
| 스킬이 안 불림 | 그 스킬 description 앞쪽 트리거 문구, 또는 프로젝트 CLAUDE.md 에 라우팅 한 줄 |
| 스킬은 불렸는데 절차를 건너뜀 | SKILL.md 본문 (references 는 안 읽힐 수 있다 — 핵심 규칙은 본문으로) |
| 에디터 MCP 로 같은 함정 두 번 | 프로젝트 `.claude/mcp_guards.json` 규칙 한 줄 |
| 조회 도구가 틀린 좌표·누락 | `gq.py` / `ue_q.py` 스크립트, 제외 경로는 `.claude/gq.json` |
| 매번 반드시 일어나야 하는데 안 일어남 | 훅 (`skills/game-bootstrap/harness/`) |
| 위 수정이 정말 효과 있나 | `evals/cases.json` 에 그 실패를 케이스로 추가 → `run_evals.py` |

평가는 비용이 든다(케이스당 약 $0.5~2). 큰 수정 뒤, 모델 업데이트 뒤에만 돌린다.

## 8. 출처

- 프롬프팅: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Claude Code best practices: https://code.claude.com/docs/en/best-practices
- 메모리·CLAUDE.md: https://code.claude.com/docs/en/memory
- 스킬: https://code.claude.com/docs/en/skills · https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- 기능별 역할: https://code.claude.com/docs/en/features-overview
- 컨텍스트 엔지니어링: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- 구조 판단 근거(연구·서적): `skills/game-architecture/references/evidence.md`
