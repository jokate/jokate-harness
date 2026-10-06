# game-harness 사용 가이드

사람이 읽는 문서다. 이 저장소로 Claude Code 작업 환경을 세팅하고, 지시하고, 쓰면서 고치는 법.
기준일 2026-10-06. Claude Code 2.1.x, UE 5.x / Unity 6 대상.

## 목차
1. 이게 뭔가
2. 층 구조
3. 설치와 새 프로젝트 세팅
4. 언제 무엇이 적용되나
5. Claude 에게 지시하는 법
6. 요청 템플릿
7. 쓰면서 고치는 법
8. 하네스가 동작하는지 보기 — 모니터와 웹뷰
9. 출처

---

## 1. 이게 뭔가

게임 프로젝트용 **하네스**다. 모델을 바꾸는 게 아니라, 모델을 둘러싼 환경(지시·맥락·도구·강제·평가)을 설계해서
어느 프로젝트에 들어가도 같은 방식으로 일하게 만든다.

| 하네스 요소 | 이 저장소의 구현 | 역할 |
|---|---|---|
| 지시 | 프로젝트 `CLAUDE.md` (bootstrap 이 템플릿으로 생성) | 항상 필요한 규칙 |
| 필요할 때 가져오는 맥락 | `skills/game-*` (SKILL.md + references) | 트리거될 때만 로드 |
| 조회 도구 | `gq.py`(프로젝트), `ue_q.py`(엔진), `cindex.py`(clangd 의미 인덱스: 참조·호출·상속·오버라이드) | 통째로 읽지 않고 좌표로 |
| 센서 | `evidence.py` (변경 이력 → hotspot·co-change) | 구조 판단의 근거를 계측 |
| 결정론적 강제 | 훅: SessionStart 인덱스 갱신·라우팅, MCP 가드·로그 | 모델 판단에 기대지 않는 것 |
| 평가 | `evals/run_evals.py`, 인덱스 검증(`cindex.py eval`, 웹뷰 검증 탭) | 하네스·인덱스가 의도대로 도는지 재검증 |
| 관찰 | 하네스 이벤트 로그 → 모니터 mod(상태줄·토스트·`/harness`), 웹뷰 하네스 탭 | 어떤 기능이 지금 동작했는지 사람이 본다 |

핵심 목적은 하나다: **AI 가 한 기능에 매몰되어 국소 패치를 쌓는 것을 막고, 그 프로젝트에서 유지보수가 가장 좋은 구조를 근거와 함께 사람이 고르게 한다.**

## 2. 층 구조

| 층 | 스킬 | 언제 | 산출 |
|---|---|---|---|
| 0 | `game-bootstrap` | `/game-bootstrap` 직접 호출 | 프로젝트 CLAUDE.md, 인덱스 갱신 선언, MCP 가드 파일 |
| 1 | `game-onboard` | 구조·위치·엔진 API 질문, 누가 부르나·누가 재정의했나 | 좌표 (file:line, 모듈 그래프), 참조·호출·영향 범위 |
| 1 | `game-design-doc` | 기획서 읽기·기획과 구현 대조 | 사양 표, 구현 대응, 판단 대기, 어긋남 |
| 2 | `game-architecture` | 기능 추가·구현·설계 요청 (코드 전) | 선택지 A/B/C + "다음 요청 때 고칠 곳" + 근거 그림 → **사람이 고른다** |
| 2 | `game-patterns` | 패턴 비교, 게임 도메인 문제(버프 중첩·선입력·네트워크 예측·세이브 호환 등) | 증상 → 신호 → 후보 패턴 → 엔진 관용구, 얻음/잃음/쓰지 말 때 (출처 표시 포함) |
| 3 | `game-testing` | 검증 기준·테스트 | 완료 기준 먼저, 검증됨(자동/수동)/검증 안 됨 표기 |
| 4 | `game-mcp` | 에디터 MCP 조작 | 읽기 먼저·쓰고 재조회·실패는 가드로 |

흐름: 기획서(design-doc) → 사양 표 → 구조 조사(architecture) → 사람 선택 → 완료 기준(testing) → 구현 → 새 컨텍스트 리뷰.

새 엔진을 지원하려면 각 스킬의 `references/<엔진>.md` 한 벌만 추가한다. SKILL.md 는 고치지 않는다.

## 3. 설치와 새 프로젝트 세팅

**한 번에** — `setup.bat` 더블클릭, 또는 프로젝트 폴더를 `setup.bat` 위에 끌어다 놓는다 (PowerShell: `.\setup.bat "<폴더>"`).
설치, `settings.json` 훅 등록(원본은 `.bak`), 프로젝트 세팅, 사용법 출력까지 한다. 아래는 나눠서 할 때.

**머신당 한 번** — Windows 면 `install.bat` 더블클릭으로 끝. 인자를 줄 때는:

```
python install.py            # 스킬 복사 + 훅 복사, settings 조각 출력
python install.py --link     # 스킬을 저장소로 링크 (이 저장소를 고치면 바로 반영 — 개발용)
```

출력된 `hooks` 조각을 `~/.claude/settings.json` 에 합친다 (자동으로 고치지 않는다).

**프로젝트마다 — 이걸 안 하면 하네스가 사실상 꺼져 있다 (4절)**

- 빠른 길: 프로젝트 폴더를 `bootstrap.bat` 위에 끌어다 놓는다. `CLAUDE.local.md`(커밋 안 됨)와 인덱스 갱신 선언이 생긴다.
  팀 규칙으로 커밋하려면 `bootstrap.bat <폴더> --team` → `CLAUDE.md`. 미리보기는 `--dry-run`.
- 대화형: Claude Code 에서 `/game-bootstrap` → 감지 결과 확인 → 선택 모듈(답변 형식, 가설 우선 등) 고르기 → 생성 승인.
- **이미 CLAUDE.md 가 있는 프로젝트**: `bootstrap.bat <폴더> --routing-only` — 스킬 라우팅 한 절만 `CLAUDE.local.md` 로 넣는다.
  기본값대로 만들면 기존 규칙과 겹치거나(전제·범위·정직) 충돌한다(조회 도구). 미리보기(`--dry-run`)가 겹침을 경고한다.
- 이미 있는 파일은 덮어쓰지 않는다. 사내 저장소면 개인 선호는 `CLAUDE.local.md`, 팀 합의만 `CLAUDE.md`.

**선택: clangd 의미 인덱스** — "누가 부르나·누가 재정의했나·바꾸면 어디가 영향받나"를 grep 이 아니라 컴파일러 기준으로 보려면.
1. clangd 릴리스의 `clangd_indexing_tools-windows-<버전>.zip` 에서 `clangd-indexer.exe` 를 `~/.claude/tools/clangd/bin/` 에 둔다.
2. 프로젝트에서 `python ~/.claude/skills/game-onboard/scripts/cindex.py cdb` (UBT 로 compile_commands.json) → `cindex.py build`.
   에디터 빌드를 한 번 해 둔다 — `.generated.h` 가 없으면 UCLASS 타입이 빠진다. 상세: `skills/game-onboard/references/cindex.md`.

**제거** — `uninstall.bat` (프로젝트 폴더를 끌어다 놓으면 그 세팅도). 한 프로젝트에서만 빼려면 `--project-only`, 미리보기는 `--dry-run`. 상세는 README.

## 4. 언제 무엇이 적용되나

2026-10-01 헤드리스 세션 평가로 실측한 결과 (`docs/VERIFICATION.md`).

| 구성 | 적용 시점 | 상태 |
|---|---|---|
| 스킬 목록 등록 | 세션 시작 | 검증됨 |
| **프로젝트 규칙 파일** (CLAUDE.md / CLAUDE.local.md) | 세션 시작 | **스킬 호출의 실질적 스위치.** 있으면 9/9 케이스에서 맞는 스킬이 불렸다 |
| 라우팅 안내 (`[game-harness]` 줄) | 세션 시작, `.uproject`/Unity 프로젝트일 때만 | 동작하지만 규칙 파일 없이는 트리거를 못 올렸다. 소스 저장소 위치 안내로 남겨 둔다 |
| 프로젝트 인덱스 갱신 | 세션 시작, `.claude/session_start.json` 이 있을 때만 | 검증됨 |
| `game-bootstrap` | 직접 호출할 때만 (`bootstrap.bat` 도 같은 일) | 설계상 |
| MCP 가드·로그 | MCP 호출마다 | 기존부터 동작 |
| 하네스 이벤트 기록 (`harness_events.py`) | 훅이 무언가 했을 때, 하네스 스킬·조회 스크립트가 불렸을 때 | 훅에 샘플 입력을 넣어 기록 확인 (2026-10-06). 실제 세션에서는 검증 안 됨 |
| 모니터 mod (`game-harness-monitor`) | 세션 시작부터 (`CLAUDE_CODE_PLUGIN_DIRS` 로 로드) | Claude Code 2.1.290 에서 로드·테스트 통과. **사용자 머신 버전에서 검증 안 됨** — 함수 훅 플러그인은 early access |
| clangd 의미 인덱스 | 수동 `cindex.py build` | 가짜 UE 구조로 검증. 실제 UE·Windows 검증 안 됨 |

가장 중요한 실측 사실: **훅이 넣는 안내(세션 시작·요청 시점 모두)와 유저 레벨 `~/.claude/CLAUDE.md` 는 스킬 호출을 올리지 못했다.
프로젝트 규칙 파일은 CLAUDE.md 든 CLAUDE.local.md 든 올렸다.** 그래서 새 프로젝트는 bootstrap 부터.

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

### 매몰됐을 때 — `[RESET]`

매몰된 모델은 자기 매몰을 못 알아챈다. 그래서 감지와 요약을 세션 밖에 둔다.

1. `[매몰 신호]` 경고가 뜨거나(같은 파일 5회 수정, 셸 명령 연속 3회 실패) 답이 이상하다 싶으면 `[RESET]` 을 친다.
2. 훅이 대화 기록을 별도 모델(haiku)에 넘겨 `<프로젝트>/.claude/handoff.md` 를 쓴다 (긴 세션은 1분 남짓). 세션의 모델은 관여하지 않는다.
3. 문서를 읽어 보고 `/clear`. 새 세션이 그 문서로 시작하고, 작업을 잇기 전에 무엇을 할지 먼저 확인받는다.

- 임계값: `<프로젝트>/.claude/stuck_watch.json` 에 `{"edit": 8, "fail": 4}`. 0 이면 끈다.
- 한계: 반복이 없는 방향 이탈은 카운터가 못 잡는다 — 사람이 건다. HandOff 는 요약이라 틀릴 수 있다 — `/clear` 전에 읽는다.
- `.claude/handoff.md`, `handoff.used.md` 는 커밋하지 않는다.

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
| 스킬이 안 불림 | 먼저 프로젝트 규칙 파일이 있는지(bootstrap). 있는데도 안 불리면 그 파일의 라우팅 줄, 그다음 스킬 description 트리거 문구 |
| 스킬은 불렸는데 절차를 건너뜀 | SKILL.md 본문 (references 는 안 읽힐 수 있다 — 핵심 규칙은 본문으로) |
| 에디터 MCP 로 같은 함정 두 번 | 프로젝트 `.claude/mcp_guards.json` 규칙 한 줄 |
| 조회 도구가 틀린 좌표·누락 | 웹뷰 검증 탭(또는 `cindex.py eval`)으로 먼저 잰다 → `gq.py` / `ue_q.py` / `cindex.py`, 제외 경로는 `.claude/gq.json` |
| 인덱스가 기대 위치를 못 찾는다 | `<프로젝트>/.claude/index_eval.json` 에 그 질의를 넣고 웹뷰 "질의 세트" 로 Acc@1·MRR 을 본다 |
| 매번 반드시 일어나야 하는데 안 일어남 | 훅 (`skills/game-bootstrap/harness/`) |
| 매몰을 놓쳤다 / 경고가 너무 잦다 | `stuck_watch.py` 의 `SIGNALS` 에 신호 한 줄, 임계값은 프로젝트 `.claude/stuck_watch.json` |
| HandOff 가 틀리거나 빠뜨림 | `handoff.py` 의 `INSTRUCTION` (형식), `extract` (무엇을 넘기나) |
| 위 수정이 정말 효과 있나 | `evals/cases.json` 에 그 실패를 케이스로 추가 → `run_evals.py` |

평가는 비용이 든다(케이스당 약 $0.5~2). 큰 수정 뒤, 모델 업데이트 뒤에만 돌린다.

## 8. 하네스가 동작하는지 보기 — 모니터와 웹뷰

하네스의 훅과 조회 스크립트는 동작할 때마다 `~/.claude/cache/game-harness/events.jsonl` 에 한 줄을 남긴다
(기능 id 예: `context.routing`, `session_start.gq`, `skill.game-architecture`, `script.ue_q.sym`, `index.clangd`, `stuck.warn`, `handoff.write`).

**모니터 mod** (`mods/game-harness-monitor`, setup 이 켠다)
- 상태줄: 이 세션에서 하나라도 동작한 뒤부터 `harness ● 기능 N개 · 마지막 <기능>` (실패가 있으면 `· 실패 N`).
- 토스트: 기능이 이 세션에서 **처음** 동작할 때 한 번 — "하네스 기능 시작: 스킬 game-architecture".
- `/harness`: 기능별 횟수와 시간순 기록 패널.
- 로그를 읽기만 한다. 도구 호출을 막거나 바꾸지 않는다. 상태줄에 아무것도 없으면 이 세션에서 하네스가 아직 아무것도 안 한 것이다.
- Claude Code 의 함수 훅 플러그인(early access)이 필요하다. 2.1.290 에서 확인했고, 그보다 낮은 버전에서는 안 뜰 수 있다 — 그때는 웹뷰 하네스 탭으로 본다.

**인덱스 웹뷰** — `python ~/.claude/skills/game-onboard/scripts/index_view.py --open` (프로젝트 폴더에서, 127.0.0.1 에만 열린다)
- 검색: 엔진·프로젝트 정규식 인덱스와 clangd 인덱스를 골라 검색 → 선언 원문, 부모·자식, 호출하는 쪽·부르는 함수, 재정의.
- 그래프: 상속 · 호출 · 오버라이드 · 모듈 의존(정규식은 Build.cs 선언, clangd 는 실제 참조로 본 의존). 노드 더블클릭으로 중심 이동, 드래그·휠.
- 검증: 소스별 자체 검사(좌표 정확도·신선도·실패 TU), 정규식 ↔ clangd 대조(타입 재현율·파일/줄/부모 일치), 질의 세트(Acc@1·Acc@5·MRR).
  기준과 근거: `skills/game-onboard/references/indexing-research.md`.
- 하네스: 이벤트 로그를 기능별로 모아 보기, 세션 id 필터, 5초 자동 갱신.

## 9. 출처

- 프롬프팅: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Claude Code best practices: https://code.claude.com/docs/en/best-practices
- 메모리·CLAUDE.md: https://code.claude.com/docs/en/memory
- 스킬: https://code.claude.com/docs/en/skills · https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- 기능별 역할: https://code.claude.com/docs/en/features-overview
- 컨텍스트 엔지니어링: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- 구조 판단 근거(연구·서적): `skills/game-architecture/references/evidence.md`
