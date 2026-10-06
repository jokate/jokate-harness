---
name: game-onboard
description: 게임 프로젝트(Unreal Engine / Unity)와 엔진을 빠르게 파악한다. 처음 보는 프로젝트에 들어갔을 때, "이 프로젝트 구조 파악", "어디에 뭐가 있나", "이 기능 어디서 처리하나", "모듈/asmdef 구성", "엔진이 X를 어떻게 구현했나", "이 엔진 클래스 시그니처", "이 함수 누가 부르나", "이 가상 함수 누가 재정의했나", "이거 바꾸면 어디가 영향받나" 같은 질문을 받았을 때, 또는 낯선 엔진 타입을 건드리는 코드를 쓰기 전에 쓴다. 문서·소스·애셋을 통째로 읽지 않고 좌표 인덱스(gq.py, ue_q.py)와 clangd 의미 인덱스(cindex.py)로 좁혀 들어간다. 인덱스를 브라우저로 보고 검증하는 웹뷰(index_view.py)도 있다.
---

# game-onboard — 엔진과 프로젝트를 좌표로 파악한다

게임 프로젝트의 구조는 절반이 코드 밖에 있다(BP, DataAsset, DataTable, ScriptableObject, 프리팹, Config, 태그).
grep 만으로는 절반만 본다. 그리고 엔진과 프로젝트는 변하는 속도가 다르다.

| 대상 | 성질 | 인덱스 | 갱신 |
|---|---|---|---|
| 엔진 | 버전 고정, 거대 | `ue_q.py` → `~/.claude/cache/ue_index/<엔진경로>/` (엔진당 1개, 프로젝트 공유) | 엔진 설치·패치 때 `index` |
| 프로젝트 | 매일 변함 | `gq.py` → UE `Saved/ClaudeIndex` · Unity `Library/ClaudeIndex` | SessionStart 훅 (`game-bootstrap` 참고) |
| 의미 (참조·호출·상속·오버라이드) | 컴파일 기준 | `cindex.py` → 프로젝트 `Saved/ClaudeIndex/clangd.sqlite` · 엔진 `ue_index/<엔진경로>/clangd.sqlite` | 수동 `build` (compile_commands.json + clangd-indexer, 증분 `--mode bg` 는 clangd) |

정규식 인덱스는 선언 줄만 본다. 누가 부르나·누가 재정의했나·바꾸면 어디가 영향받나는 `cindex.py` 로 본다. 의미 인덱스는 grep 을 대체하지 않는다 — 문자열·주석·설정은 `rg`.

## 규칙

1. 문서·소스를 통째로 `Read` 하지 않는다. `map` → `find`/`sym` → `get` 또는 해당 줄 범위만 읽는다.
2. 인덱스는 좌표뿐이다. 동작·사양 판단은 원문으로 한다. 확인 못 한 API 는 "확인 필요"로 쓴다.
3. `[낡음]` 이 뜨면 믿기 전에 `index`.
4. 엔진 버전에 따라 다른 API 는 버전을 먼저 밝힌다 (`gq.py status` 가 버전을 준다).
5. 조사 출력이 크면 서브에이전트(Explore)에 맡기고 결론만 받는다.

## 명령

프로젝트 루트나 하위에서 실행. 셸 변수로 경로를 줄이지 말고 전체 경로를 쓴다 (변수 확장은 권한 프롬프트를 부른다).

| 목적 | 명령 |
|---|---|
| 개요 (엔진·버전·VCS·모듈·문서·애셋 유형) | `python ~/.claude/skills/game-onboard/scripts/gq.py map [키워드]` |
| 통합 검색 (심볼·애셋·문서 헤딩·태그) | `python ~/.claude/skills/game-onboard/scripts/gq.py find <질의>` |
| 프로젝트 심볼 좌표 | `python ~/.claude/skills/game-onboard/scripts/gq.py sym <이름>` |
| 문서 목차 / 절 본문 | `python ~/.claude/skills/game-onboard/scripts/gq.py get <문서>` · `get <문서>#<절>` |
| 모듈 의존 (Build.cs / asmdef) | `python ~/.claude/skills/game-onboard/scripts/gq.py deps [모듈] [--reverse] [--mermaid]` |
| 인덱스 갱신 / 신선도 | `python ~/.claude/skills/game-onboard/scripts/gq.py index` · `status` |
| UE 엔진 심볼 → 선언 → 시그니처 | `python ~/.claude/skills/game-onboard/scripts/ue_q.py sym X` → `api X` / `decl X --max 60` |
| UE 엔진 모듈·의존 / 본문 검색 | `python ~/.claude/skills/game-onboard/scripts/ue_q.py module X` · `deps X` · `rg "패턴" --module X` |
| 부르는 쪽 / 부르는 함수 (참조 줄 원문 포함) | `python ~/.claude/skills/game-onboard/scripts/cindex.py callers X` · `callees X` · `refs X` |
| 자식 · 재정의 · 바꾸면 같이 볼 곳 | `python ~/.claude/skills/game-onboard/scripts/cindex.py derived X` · `overrides X` · `impact X` |
| 의미 인덱스 만들기 / 상태 | `python ~/.claude/skills/game-onboard/scripts/cindex.py build [--scope engine] [--mode bg] [--unity 8]` · `status` |
| 인덱스 웹뷰 (검색·그래프·검증·하네스 기록) | `python ~/.claude/skills/game-onboard/scripts/index_view.py --open` |

제외할 경로(서드파티, 중첩 저장소)는 `<루트>/.claude/gq.json` 에 `{"exclude": ["Plugins/Developer"]}`.
UE 엔진 소스 조회 규칙·출력 형식·전형적 흐름·한계: [references/ue_q.md](references/ue_q.md) — 엔진 API 를 볼 때는 먼저 읽는다.
clangd 의미 인덱스 준비(clangd-indexer, compile_commands.json)·명령·함정: [references/cindex.md](references/cindex.md).
속도: 엔진 범위는 `--unity 8`(처음 색인이 크게 준다), 프로젝트 범위는 `--mode bg`(두 번째부터 바뀐 파일과 그것을 포함한 TU 만) — 근거와 합성 측정은 cindex.md 3절.
인덱스 설계 근거와 검증 기준(연구 기반): [references/indexing-research.md](references/indexing-research.md).
의미 인덱스가 없으면 "누가 부르나" 류 답은 `rg` 결과임을 밝힌다 (같은 이름 다른 심볼이 섞인다).

## 처음 들어간 프로젝트 — 순서

1. `gq.py index` → `map`. 엔진·버전·VCS·모듈 수·문서 목록을 한 화면으로 본다.
2. 프로젝트 CLAUDE.md, 아키텍처·결정 기록 문서가 있으면 `get` 으로 목차부터.
3. 진입점을 찾는다 — 엔진별 목록은 references 에 있다.
4. 데이터 흐름: 설정이 코드에 있나 데이터(DataAsset/SO/테이블)에 있나. `map` 의 애셋 유형 분포가 단서다.
5. 모듈 경계: `deps --mermaid` 로 그림 한 장. 순환·역방향 의존이 있으면 기록한다.
6. 결과는 사용자가 요청할 때만 문서로 남긴다.

## 엔진별 상세

- Unreal: [references/ue.md](references/ue.md) — 프로젝트 해부, 진입점, 엔진 소스 탐색 순서, 버전 함정
- Unity: [references/unity.md](references/unity.md) — 프로젝트 해부, 진입점, 패키지 소스, 직렬화 함정

엔진 판별: 루트에 `*.uproject` 면 UE, `ProjectSettings/ProjectVersion.txt` + `Assets/` 면 Unity.

## 한계 (검증 상태)

- `gq.py` 의 심볼 추출은 정규식이다. UE 는 리플렉션 매크로와 `*_API` 클래스만, Unity 는 최상위 타입 선언만 잡는다. 매크로로 생성된 타입·중첩 타입은 빠질 수 있다.
- Unity 경로는 가짜 프로젝트로만 검증했다. 실제 대형 Unity 프로젝트에서는 검증 안 됨.
- Unity 엔진 소스 인덱서는 없다. 패키지 소스는 `Library/PackageCache` 에서 직접 `rg` 로 본다.
- `cindex.py` 는 가짜 UE 구조와 clangd/clangd-indexer 23.1.0(리눅스)으로만 검증했다. 실제 UE 엔진·Windows·UBT `cdb`, UE 규모의 `--mode bg`·`--unity` 는 검증 안 됨 (references/cindex.md 7절).
