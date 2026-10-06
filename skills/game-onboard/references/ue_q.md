# ue_q.py — UE 엔진 소스 조회 상세

엔진 헤더는 수만 줄짜리가 흔하다. `Read` 로 열면 컨텍스트가 그 파일 하나로 끝난다.
`ue_q.py` 는 엔진당 하나인 sqlite 인덱스(`~/.claude/cache/ue_index/<엔진경로>/ue.sqlite`, UE 5.7 기준 40k 헤더 · 100k 심볼)로
좌표를 찾고 **4KB 상한**으로 본문을 끊어서 낸다. 헤더 통째 Read 대비 평균 7.5배 토큰 절감(MNYS 실측).

## 목차
1. 규칙
2. 명령
3. 전형적 흐름
4. 재색인·엔진 경로
5. 한계

## 1. 규칙

1. 엔진 설치 폴더 아래 파일을 `Read`/`Glob`/`Grep` 으로 직접 열지 않는다. 항상 `ue_q.py` 를 먼저 쓴다.
2. 흐름은 **좁혀 들어가기**: `sym` → `api` 또는 `decl` → 정말 필요할 때만 `get` 으로 줄 범위.
3. 출력 끝에 `… (+N more …)` 가 붙으면 잘린 것이다. `--full` 로 풀기 전에 `--limit`/`--max`/`--module` 로 더 좁힐 수 있는지 먼저 본다.
4. `--full` 은 한 번에 한 심볼만. 1000줄짜리 클래스를 `decl --full --max 2000` 으로 통째로 꺼내지 않는다 — `api` 로 시그니처만 보고, 필요한 구간만 `get`.
5. 인덱스는 좌표뿐이다. 사양·동작 판단은 `decl`/`get` 원문으로 한다. 확인 못 한 시그니처는 "확인 필요".
6. 엔진 경로 불일치가 보이거나 엔진을 갱신했으면 `index` 를 돌린다.

## 2. 명령

프로젝트 루트나 하위에서 실행 (`*.uproject` 로 엔진 버전을 찾는다). 경로는 셸 변수로 줄이지 않는다.

| 목적 | 명령 |
|---|---|
| 심볼 좌표 (정확 → 부분 일치) | `python ~/.claude/skills/game-onboard/scripts/ue_q.py sym UAnimSequence` |
| 선언 블록 (기본 150줄, 4KB) | `python ~/.claude/skills/game-onboard/scripts/ue_q.py decl UAnimSequence [--max 60] [--path Classes/Animation]` |
| 멤버 함수 시그니처 + UPROPERTY 만 | `python ~/.claude/skills/game-onboard/scripts/ue_q.py api UControlRig` |
| 줄 범위 (최대 200줄) | `python ~/.claude/skills/game-onboard/scripts/ue_q.py get Source/Runtime/Engine/Classes/Animation/AnimSequence.h:200-260` |
| 파일 경로 찾기 | `python ~/.claude/skills/game-onboard/scripts/ue_q.py file AnimSequence.h` |
| 모듈 정보·Build.cs 의존성 | `python ~/.claude/skills/game-onboard/scripts/ue_q.py module ControlRig` |
| 의존 방향 | `python ~/.claude/skills/game-onboard/scripts/ue_q.py deps LevelSequence [--reverse]` |
| 정규식 검색 (ripgrep, 대소문자 무시) | `python ~/.claude/skills/game-onboard/scripts/ue_q.py rg "OnAnimNotify" --module Engine --type h --limit 20` |
| 통합 검색 (심볼+모듈+파일명) | `python ~/.claude/skills/game-onboard/scripts/ue_q.py find MetaSound` |
| 인덱스 상태 / 재색인 | `python ~/.claude/skills/game-onboard/scripts/ue_q.py status` · `index [--force]` |

- 모든 검색은 대소문자를 무시한다. `get` 경로는 엔진 루트 기준이며, 고유하면 뒤쪽 조각(`Engine/HitResult.h:20-30`)만 줘도 된다.
- `sym` 출력: `kind name  module  path:line  : parent`. kind 는 `uclass/ustruct/uenum/interface/class/struct/enum/delegate`.
- `api` 는 클래스 본문 깊이 1의 함수 시그니처와 `UPROPERTY`/`UFUNCTION` 멤버만 낸다. 인라인 본문은 `{…}` 로 접고 `meta=(…)` 는 뗀다.
- 같은 이름이 여럿이면 `decl`/`api` 는 첫 후보를 내고 `# 같은 이름 N개 더` 를 붙인다. `--path` 로 고른다.

## 3. 전형적 흐름

```
# 1. 클래스가 어디 있고 부모가 뭔지
python ~/.claude/skills/game-onboard/scripts/ue_q.py sym UMetaSoundSource
# 2. 어떤 함수/프로퍼티가 있는지 (4KB)
python ~/.claude/skills/game-onboard/scripts/ue_q.py api UMetaSoundSource
# 3. 특정 함수 주변 원문이 필요할 때만
python ~/.claude/skills/game-onboard/scripts/ue_q.py rg "CreateSoundGenerator" --module MetasoundEngine --type h
python ~/.claude/skills/game-onboard/scripts/ue_q.py get Plugins/Runtime/Metasound/Source/MetasoundEngine/Public/MetasoundSource.h:300-330
# 4. 구현(cpp)을 봐야 하면
python ~/.claude/skills/game-onboard/scripts/ue_q.py rg "UMetaSoundSource::CreateSoundGenerator" --module MetasoundEngine --type cpp
```

모듈 경계를 모르면: `find <키워드>` → `module <이름>` → `deps <이름> --reverse` 로 누가 쓰는지.
플러그인 에디터 API 를 찾을 땐 `--module <Name>Editor` 로 좁히면 잡음이 크게 준다.

## 4. 재색인·엔진 경로

- 증분: `index` (size+mtime 서명, 수 초). 전체: `index --force` (16 코어 기준 약 10초).
- 엔진 루트: env `UE_ROOT` > 이 프로젝트용으로 저장한 경로 > `<프로젝트>.uproject` 의 `EngineAssociation` + 레지스트리 > `C:/Unreal/UE_5.7/Engine`.
  저장은 `index_all.py --engine-root <엔진 폴더>` (`index_build.bat` 은 못 찾으면 창에서 묻는다) — `~/.claude/cache/game-harness/engine_roots.json`,
  프로젝트 경로 → 엔진 폴더. 머신마다 경로가 달라 프로젝트 폴더(VCS)가 아니라 홈에 둔다. `UE_5.7` 과 `UE_5.7/Engine` 둘 다 받고, `Source/Runtime` 이 없으면 거부한다.
- 인덱스는 엔진 경로별 캐시라 같은 엔진을 쓰는 프로젝트끼리 공유한다. 엔진 패치 후엔 한 번만 `index`.
- `rg` 가 PATH 에 없으면 Claude Code 내장 ripgrep 을 쓴다. 다른 환경이면 `RG_PATH` 로 지정.

## 5. 한계

- 선언은 줄 단위 정규식이다. 매크로로 생성되는 클래스, `template<>` 특수화, `namespace` 안 정의 일부, `#define` 매크로 자체는 `sym` 에 안 잡힌다 → `rg`.
- `api` 는 파서가 아니다. 여러 줄에 걸친 특이한 선언은 뭉개질 수 있다 → `decl` 로 확인.
- 심볼은 헤더에서만 뽑는다. cpp 전용 정의(static 함수, 익명 namespace)는 `rg --type cpp`.
