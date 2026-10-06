# Unreal Engine — 프로젝트와 엔진 파악

## 목차
1. 프로젝트 해부
2. 진입점 찾기
3. 데이터가 사는 곳
4. 엔진 소스 탐색 순서
5. 버전 함정

## 1. 프로젝트 해부

| 경로 | 의미 | 볼 때 |
|---|---|---|
| `<이름>.uproject` | 엔진 버전(`EngineAssociation`), 활성 플러그인, 모듈 목록 | 가장 먼저 |
| `Source/<모듈>/<모듈>.Build.cs` | 모듈 의존. `gq.py deps` 가 파싱 | 경계 파악 |
| `Source/<모듈>/Public` · `Private` | 공개 헤더 / 구현. Public 헤더가 모듈 API | API 파악 |
| `Plugins/<이름>/*.uplugin` | 프로젝트 플러그인. Game Feature 플러그인이면 기능 단위 경계 | 기능 분리 여부 |
| `Config/Default*.ini` | 엔진·게임 설정, 게임플레이 태그(`DefaultGameplayTags.ini`, `Config/Tags/*.ini`) | 설정·태그 |
| `Content/` | 애셋. 바이너리라 직접 못 읽는다 — 이름 접두사로 유형 추정, 내용은 에디터(MCP)로 | 데이터 흐름 |
| `Saved/`, `Intermediate/`, `Binaries/`, `DerivedDataCache/` | 생성물. 읽지 않는다 | — |

## 2. 진입점 찾기

`gq.py find` 로 아래를 차례로 찾는다. 이 목록에 걸리는 클래스가 게임 흐름의 뼈대다.

- 게임 규칙: `AGameModeBase` / `AGameStateBase` 파생 → `DefaultEngine.ini` 의 `GlobalDefaultGameMode`, 맵별 WorldSettings 오버라이드
- 수명 단위 서비스: `UGameInstanceSubsystem` / `UWorldSubsystem` / `ULocalPlayerSubsystem` 파생 — 전역 상태가 여기 있으면 Service Locator 성격
- 플레이어: `APlayerController`, `APawn`/`ACharacter` 파생, Enhanced Input(`UInputAction`, `UInputMappingContext`)
- 능력 체계: `UAbilitySystemComponent`, `UGameplayAbility`, `UAttributeSet`, `UGameplayEffect` 파생 → GAS 사용 여부
- 모듈형 기능: `UGameFeatureAction_AddComponents`, `UGameFrameworkComponentManager` → Game Features / Lyra 식 구조 여부
- AI: `UStateTree`, `UBehaviorTree` 애셋, `AAIController` 파생

## 3. 데이터가 사는 곳

- `UPrimaryDataAsset`/`UDataAsset` 파생 + `DA_` 애셋 → 종류별 설정이 데이터로 빠져 있음 (Type Object)
- `FTableRowBase` 파생 + `DT_` 애셋 → 표 형태 밸런스 데이터
- 태그: `UE_DEFINE_GAMEPLAY_TAG` (네이티브) + ini (데이터). `gq.py find <태그>` 로 정의 위치
- BP 전용 로직: 소스에 없는 동작은 BP 에 있다. `gq.py find <이름>` 에서 애셋만 나오면 BP 쪽 → MCP 로 그래프 조회 (`game-mcp`)

## 4. 엔진 소스 탐색 순서

1. `ue_q.py sym <타입>` — 어느 모듈 어느 헤더인가
2. `ue_q.py api <타입>` — 공개 멤버 시그니처와 UPROPERTY 만
3. `ue_q.py module <모듈>` — Build.cs 에 넣을 의존 이름
4. 동작이 궁금할 때만 `ue_q.py rg "<함수명>" --module <모듈> --type cpp` → `get <경로>:<줄범위>`

엔진 인덱스가 없으면 `ue_q.py index` (UE 5.x 전체 헤더 기준 수 분, 이후 증분). 엔진 경로는 `UE_ROOT` 환경변수 → 이 프로젝트용으로 저장한 경로(`index_build.bat --engine-root`, 못 찾으면 bat 이 묻는다) → `.uproject` EngineAssociation(소스 빌드·런처 레지스트리, 런처 설치 목록, 엔진 폴더 안 프로젝트) → `C:/Unreal/UE_5.7/Engine` 순으로 찾는다.

## 5. 버전 함정

- `EngineAssociation` 이 GUID 면 소스 빌드 엔진이다 (`HKCU\SOFTWARE\Epic Games\Unreal Engine\Builds` 에서 찾는다). 그래도 못 찾으면 `index_build.bat --engine-root <엔진 폴더>` 로 저장하거나 `UE_ROOT` 로 지정.
- 5.x 사이에도 API 가 바뀐다. 예: 자동화 테스트 컨텍스트 마스크는 5.7 헤더 기준 `EAutomationTestFlags_ApplicationContextMask` (전역 constexpr). 이전 버전 예제와 다를 수 있으니 `ue_q.py rg` 로 확인.
- UE 5.8 에 Epic 공식 "Unreal MCP" 플러그인이 실험 기능으로 들어갔다(커뮤니티 경유 정보, 검증 안 됨). 자체·커뮤니티 MCP 와 역할이 겹치는지 따로 판단.
