---
name: game-bootstrap
description: 새 게임 프로젝트(UE / Unity)에 Claude 작업 환경을 세팅한다 — 협업 규칙 CLAUDE.md, 프로젝트 인덱스 자동 갱신, MCP 가드, 하네스(훅) 점검. 사용자가 /game-bootstrap 으로 직접 부를 때만 쓴다.
disable-model-invocation: true
argument-hint: "[프로젝트 루트 — 생략하면 현재 폴더]"
---

# game-bootstrap — 프로젝트 세팅

파일을 만드는 스킬이다. **만들 파일 목록을 먼저 보여주고 승인받은 뒤에** 만든다.
이미 있는 파일은 덮어쓰지 않는다 — 차이를 보여주고 합칠지 묻는다.

## 층 구조 (이 스킬 묶음 전체)

| 층 | 스킬 | 역할 |
|---|---|---|
| 0 | game-bootstrap | 세팅 (이 스킬) |
| 1 | game-onboard | 엔진·프로젝트 파악 (gq.py, ue_q.py) |
| 1 | game-design-doc | 기획서 → 사양 표 → 구현 대응·어긋남 보고 |
| 2 | game-architecture / game-patterns | 구현 전 구조 조사와 근거 / 패턴 카탈로그 |
| 3 | game-testing | 검증 기준과 테스트 |
| 4 | game-mcp | 에디터 MCP 운용 |

새 엔진을 지원하려면 각 층 스킬의 `references/<엔진>.md` 한 벌을 추가한다. SKILL.md 는 고치지 않는다.

## 절차

### 1. 감지 (읽기만)

- 엔진: 루트의 `*.uproject` → UE, `ProjectSettings/ProjectVersion.txt` + `Assets/` → Unity
- VCS: `.git` / `.svn` (상위 폴더까지). 중첩 저장소가 있으면 목록화
- 기존 세팅: `CLAUDE.md`, `CLAUDE.local.md`, `.claude/` 내용
- 결과를 표 하나로 보여준다.

### 2. 하네스 점검 (유저 레벨, 한 번만)

`~/.claude/settings.json` 에 아래 세 훅이 있는지, `~/.claude/hooks/` 에 스크립트가 있는지 본다.
상세와 설정 조각: [references/harness.md](references/harness.md). 없거나 다르면 차이를 보여주고 설치 여부를 묻는다.

| 훅 | 스크립트 | 프로젝트 쪽 선언 |
|---|---|---|
| SessionStart | `session_start.py` | `.claude/session_start.json` (없으면 아무것도 안 함) |
| SessionStart | `game_context.py` | 없음 — `.uproject`/Unity 프로젝트면 엔진·소스 저장소·스킬 라우팅 주입 |
| UserPromptSubmit | `game_route.py` | 없음 — 게임 프로젝트에서 요청을 키워드로 분류해 맞는 스킬을 요청 옆에 안내 (규칙은 스크립트의 RULES) |
| PreToolUse `mcp__.*` | `mcp_guard.py` | `.claude/mcp_guards.json` (없으면 아무것도 안 함) |
| PostToolUse(+Failure) `mcp__.*` | `mcp_log.py` | 없음 — `~/.claude/mcp_logs/<폴더명>.jsonl` |

원본은 이 스킬의 `harness/` 폴더, 설치는 저장소 루트의 `python install.py`. 훅은 전부 cwd 를 보고 스스로 판단하므로 유저 settings 는 프로젝트마다 고치지 않는다.

### 3. 협업 규칙 인터뷰

AskUserQuestion 으로 묻는다 (기본값 없이 — 고르는 것은 사용자):
- 규칙 파일: 팀 공유 `CLAUDE.md` (VCS 커밋) / 개인 `CLAUDE.local.md` (커밋 안 함) / 둘 다
- 포함할 모듈: [references/claude-md-template.md](references/claude-md-template.md) 의 선택 모듈 목록을 보여주고 다중 선택
- 기획 문서 위치와 취급 (참고용 / 수정 가능)

사내 저장소면 개인 선호(가설 우선, 답변 형식 등)는 `CLAUDE.local.md` 로, 팀 합의 사항만 `CLAUDE.md` 로 가르는 것을 안내한다.
SVN 은 `CLAUDE.local.md` 를 무시하려면 `svn:ignore` 속성이 필요하다 — VCS 변경이라 사용자가 직접 하도록 명령만 알려준다.

### 4. 생성 (승인 후)

| 파일 | 내용 |
|---|---|
| `CLAUDE.md` / `CLAUDE.local.md` | 템플릿 + 인터뷰 결과. 200줄 미만 |
| `.claude/session_start.json` | `{"commands": [{"run": ["~/.claude/skills/game-onboard/scripts/gq.py", "index", "--quiet"], "timeout": 60}]}` |
| `.claude/mcp_guards.json` | `{"rules": []}` — 에디터 MCP 를 쓰는 프로젝트만 |
| `.claude/gq.json` | 1단계에서 서드파티·중첩 저장소를 찾았을 때만 `{"exclude": [...]}` |

UE 엔진 소스 인덱스가 그 엔진 경로로 아직 없으면 `ue_q.py index` 를 돌릴지 묻는다 (수 분 소요, 엔진당 한 번).

### 5. 확인

1. `python ~/.claude/skills/game-onboard/scripts/gq.py index` → `map` 을 돌려 결과를 보여준다.
2. 새 세션에서 SessionStart 가 인덱스를 갱신하는지는 **이 세션에서 확인할 수 없다** — "다음 세션 시작 후 `gq.py status` 로 인덱스 시각 확인"을 안내한다.
3. 권한 프롬프트가 많으면 며칠 쓴 뒤 `/fewer-permission-prompts` 로 허용 목록을 만든다 (조회 명령 위주).

## 사람을 위한 자료

지시하는 법, 요청 템플릿, 언제 무엇이 적용되나, 쓰면서 고치는 법: game-harness 저장소의 `docs/GUIDE.md`.
이 스킬 폴더가 링크 설치면 `~/.claude/skills/game-bootstrap/../../docs/GUIDE.md`. 세팅이 끝나면 위치를 사용자에게 알려준다.
