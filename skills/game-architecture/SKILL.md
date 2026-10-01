---
name: game-architecture
description: 게임 프로젝트(UE / Unity)에서 기능을 구현하거나 구조를 바꾸기 전에, 그 프로젝트에서 유지보수가 가장 좋은 구조를 조사하고 근거를 그림으로 제시한다. "이 기능 구현해줘", "X 추가", "어떻게 설계하지", "구조 잡아줘", "리팩터링", "이거 어디에 넣어야 하나", "같은 요청이 또 올 것 같다" 같은 요청에서 코드를 쓰기 전에 쓴다. 한 기능에 매몰된 국소 패치(케이스마다 필드·플래그·분기 추가)를 막는 것이 목적이다. 구조를 고르는 것은 사용자다 — 이 스킬은 선택지와 근거까지만 낸다. 패턴 자체의 비교·카탈로그는 game-patterns.
---

# game-architecture — 구현 전에 구조를 조사한다

에이전트는 국소 수정에 강하고 모듈을 가로지르는 추론에 약하다. 요청 한 건을 통과시키는 패치는
돌아가지만, 같은 종류의 요청이 올 때마다 고칠 곳이 늘어난다(change amplification).
이 스킬은 그 반대 방향 — 과설계 — 도 같이 막는다. 근거는 [references/evidence.md](references/evidence.md).

## 0. 진입 판정

- diff 를 한 문장으로 설명할 수 있는 수정(오타, 값 조정, 명백한 버그)은 이 절차를 건너뛰고 바로 구현한다.
- 새 기능, 새 종류(캐릭터·무기·스킬·UI 화면…), 두 모듈 이상을 건드리는 변경이면 아래를 밟는다.
- 사용자가 "그냥 빨리"라고 하면 1줄로 트레이드오프만 말하고 따른다.

## 1. 요청을 축으로 분해한다

요청을 **언제(트리거) / 무엇을(효과) / 어떤 조건으로(게이트) / 누구에게(대상)** 로 쪼갠다.
기획서가 근거면 `game-design-doc` 의 사양 표로 먼저 뽑는다 (같은 축이다). 빈칸은 판단 대기로 모은다.
그리고 같은 축의 과거 요청을 2~3건 찾는다 — 기획서, 결정 기록, `evidence.py focus`, VCS 로그 메시지.

산출: "앞으로 바뀔 설계 결정" 목록 (Parnas: 모듈은 바뀔 결정 하나를 숨기도록 나눈다).

## 2. 구조를 조사한다 (읽기 전용, 출력이 크면 서브에이전트)

1. `game-onboard` 로 엔진·모듈 맵을 잡는다. `gq.py deps --mermaid` 로 현재 모듈 그래프.
2. **기존 확장 지점**을 목록화한다. 새 구조를 만들기 전에 이미 있는 축에 얹을 수 있는지가 먼저다.
   - UE: Subsystem, Component, GAS(Ability/Effect/Cue), Game Feature Action, DataAsset/DataTable, 인터페이스, 델리게이트
   - Unity: asmdef 경계, ScriptableObject(데이터·이벤트 채널), 컴포넌트, DI 컨테이너, ECS System
   - 프로젝트 고유: 이미 있는 레지스트리·디스패처·데이터 테이블 (이게 제일 중요하다)
3. 변경 이력 신호를 뽑는다. 이 단계를 건너뛰지 않는다 — VCS 가 없을 때만 생략하고 그렇다고 적는다.
   - 먼저 소스 저장소를 확정한다: `python ~/.claude/skills/game-architecture/scripts/evidence.py roots`
     (소스가 루트와 별도 저장소인 프로젝트가 흔하다. SessionStart 의 `[game-harness]` 줄에도 나온다)
   - `python ~/.claude/skills/game-architecture/scripts/evidence.py hotspots --path <소스저장소>` — 자주 바뀌는 단위 (상대 churn 포함)
   - `python ~/.claude/skills/game-architecture/scripts/evidence.py coupling --path <소스저장소> --mermaid` — 함께 바뀌는 쌍
   - `python ~/.claude/skills/game-architecture/scripts/evidence.py focus <이번에 건드릴 파일 조각> --path <소스저장소>` — 이 파일이 바뀔 때 따라 바뀌어 온 것
   - 출력에 `⚠` 경고가 붙으면 그 안내대로 `--path` 를 바꿔 다시 돌린다.
   - 그래도 커밋이 적으면(수십 개 미만) 신호가 약하다고 밝히고 정적 구조만으로 판단한다.
4. 교차 판정:
   - co-change 높음 + 정적 의존 없음 → **숨은 결합**. 이번 변경이 그 결합을 늘리는지 본다.
   - 이번 수정 대상이 hotspot 상위 → 거기에 분기를 더 얹는 것은 **땜질 금지 구역**.
   - fan-in 높은 모듈·헤더 → 변경 위험 구역. 인터페이스를 바꾸면 파급이 크다.

신호 해석과 한계: [references/signals.md](references/signals.md)

## 3. 선택지를 2~3개 낸다

| 선택지 | 내용 |
|---|---|
| A. 국소 패치 | 기준선. 항상 포함한다 — 비교 대상이 있어야 B·C 의 비용이 보인다 |
| B. 기존 확장 지점 활용 | 2단계에서 찾은 축에 얹는다 |
| C. 새 구조 | 패턴 이름을 명시 (`game-patterns` 참조) |

각 선택지마다 딱 세 줄:
- **다음 같은 요청 때 고칠 곳**: 파일·애셋 개수와 이름. 답이 "새 필드 추가", "새 분기 추가"면 땜질로 표시.
- **트레이드오프**: "X 를 얻고 Y 를 잃는다" 한 줄.
- **근거**: 2단계 신호 중 이 선택지를 지지·반대하는 것.

추천·권장 표시("추천", "이게 낫다")를 붙이지 않는다. 판단 재료는 트레이드오프와 "다음 요청 때 고칠 곳"으로 충분하다 — 고르는 것은 사용자다.

과설계 가드: 새 추상화(C)는 **같은 축의 요청 증거가 2건 이상**일 때만 제안한다. 1건이면 "지금은 A/B, 두 번째 요청이 오면 C" 로 적는다.

## 4. 근거를 그림으로 낸다

규칙 (렌더러 호환 — 어기면 GitLab·Azure DevOps·SVN HTML 에서 깨진다):
- Mermaid 는 `graph TD` / `graph LR` 와 `sequenceDiagram` 만. `flowchart` 키워드, C4 문법 금지. subgraph 제목은 `subgraph id["제목"]`.
- 노드 15개 이하, 그림 하나에 주장 하나. 수치는 간선 라벨에.
- Before/After 는 선택지별 subgraph 로 나누고, 제목에 "다음 요청 때 N곳"을 적는다.

템플릿: [references/diagrams.md](references/diagrams.md). 최소 세트:

1. **현재 구조도** — 관련 모듈·클래스만, 노드 15개 이하
2. **Before/After change-impact** — "다음 같은 요청"이 왔을 때 선택지별로 고치는 노드를 강조. 노드 수가 곧 change amplification 수치
3. **신호 표** — hotspot·co-change 상위 (evidence.py 출력 그대로)
4. 이벤트·델리게이트·SO 채널 흐름이 핵심이면 sequence 다이어그램 1장 추가

**그림은 반드시 렌더해서 보여 준다.** Claude Code 대화창은 Mermaid 를 그리지 않고 코드로만 보인다 — 코드 블록만 내면 사용자는 그림을 못 본다.
1. 답변 전체(아래 출력 형식 그대로, mermaid 블록 포함)를 `<프로젝트>/Saved/ClaudeArch/<YYYYMMDD>-<주제>.md` 로 저장한다 (Unity 는 `Library/ClaudeArch/`. 프로젝트 인덱스와 같은, VCS 가 무시하는 폴더다).
2. `python ~/.claude/skills/game-architecture/scripts/render.py <그 파일.md> --open` — 단일 HTML 을 만들고 브라우저로 연다.
3. 대화창에는 mermaid 코드를 다시 붙이지 않는다. 선택지 요약(각 세 줄)과 HTML 경로만 적는다.

파일 쓰기가 막혀 있으면(읽기 전용 세션) mermaid 블록을 대화에 내고, 그림으로 보려면 저장 후 render.py 를 돌리라고 한 줄 적는다.
사용자가 다른 위치를 정하면 거기에 저장한다.

## 5. 멈춘다

선택지와 그림을 내고 **멈춘다.** 고르는 것은 사용자다. 선택되면:
1. 선택된 구조로 계획을 세운다 — 검증 기준(빌드·테스트·PIE 확인 항목)을 구현보다 먼저 적는다 (`game-testing`).
2. 구현한다.
3. 구현 후 새 컨텍스트 서브에이전트에 diff 리뷰를 맡긴다: 새 플래그·분기·중복 블록이 생겼나, 범위를 벗어났나, "다음 요청 시 고칠 곳 수"가 계획과 같은가.

## 출력 형식

```
## 요청 축
언제: … / 무엇을: … / 조건: … / 대상: …
같은 축 과거 요청: …(출처)

## 기존 확장 지점
- …

## 신호
(표 + 해석 1~2줄, 신호가 약하면 약하다고)

## 선택지
### A. … — 다음 요청 때 N곳: … · 트레이드오프: … · 근거: …
### B. …
### C. …

## 그림
(mermaid 블록들)
```
