# Unreal Engine 관용구 — 패턴을 엔진 기능으로

API 이름은 UE 5.7 헤더 기준으로 확인했다(`ue_q.py`). 다른 버전은 확인 필요.

## 목차
- 수명과 서비스: Subsystem
- 조합: ActorComponent, Game Features
- 데이터: DataAsset, DataTable, GameplayTag
- 능력: GAS
- 이벤트: 델리게이트, GameplayMessage
- 상태·AI: StateTree, Behavior Tree
- 모듈 경계: Build.cs, 플러그인

## 수명과 서비스 — Subsystem

`UEngineSubsystem` / `UEditorSubsystem` / `UGameInstanceSubsystem` / `UWorldSubsystem` / `ULocalPlayerSubsystem`.
공식 문서의 이점: 엔진 클래스를 오버라이드하지 않고, 이미 큰 클래스에 API 를 더 붙이지 않고, BP·Python 에 노출.
얻음: 수명이 명확한 서비스. 잃음: 범위가 정해진 싱글톤 = Service Locator 의 의존 은닉 (추론).
https://dev.epicgames.com/documentation/en-us/unreal-engine/programming-subsystems-in-unreal-engine

## 조합 — ActorComponent, Game Features

- ActorComponent: Component 패턴 그대로. 컴포넌트 간 통신은 소유 액터 인터페이스 / 델리게이트 / GAS 중 하나로 통일한다.
- Game Features + Modular Gameplay: 기능을 플러그인으로 떼고 `UGameFeatureAction_AddComponents` 로 대상 액터에 컴포넌트를 주입. 액터는 `UGameFrameworkComponentManager` 에 리시버로 등록.
  얻음: 무관한 기능 간 우발적 의존 차단, 기능 단위 켜기/끄기. 잃음: 초기화 순서·비동기 로딩 간접화. Lyra 샘플이 기준 구현.
  https://dev.epicgames.com/documentation/en-us/unreal-engine/game-features-and-modular-gameplay-in-unreal-engine

## 데이터 — DataAsset, DataTable, GameplayTag

- `UPrimaryDataAsset`: Type Object. Asset Manager 로 비동기 로딩·번들 관리.
- DataTable (`FTableRowBase`): 표 형태 대량 데이터(밸런스). 행 구조체 변경 시 CSV/JSON 재임포트 확인.
- GameplayTag: 계층형 이름. 문자열 비교 대신 쓰지만, 태그는 **전역 네임스페이스**라 남발하면 그 자체가 숨은 결합이 된다. enum·직접 참조로 충분하면 그쪽이 먼저.

## 능력 — GAS

`UAbilitySystemComponent`, `UGameplayAbility`, `UAttributeSet`, `UGameplayEffect`, GameplayCue.
공식 대상 장르: RPG, 액션, MOBA. 얻음: 능력·수치·효과·연출 분리, 네트워크 예측. 잃음: 셋업 부담, 태그 증식 (커뮤니티 통념).
https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-ability-system-for-unreal-engine

## 이벤트

- 델리게이트: `DECLARE_DYNAMIC_MULTICAST_DELEGATE_*` (BP 노출) / 네이티브 멀티캐스트. Observer.
- GameplayEvent (GAS `SendGameplayEventToActor`), Lyra 의 GameplayMessage 서브시스템: 태그 채널 기반 Event Queue 성격. 정적 추적이 안 되니 태그 이름 규칙을 문서화.

## 상태·AI

- StateTree: 계층 상태머신 + 조건·태스크 데이터화. 게임플레이 상태에도 쓸 수 있다.
- Behavior Tree: AI 의사결정. 상태가 많고 전이가 명시적이면 StateTree 가 맞는 경우가 많다 — 프로젝트에 이미 있는 쪽을 따른다.

## 모듈 경계

- Build.cs 의 Public 의존은 헤더를 통해 전파된다. 구현에서만 쓰면 Private 으로.
- 순환 모듈 의존은 빌드를 느리게 하고 `CircularlyReferencedDependentModules` 는 레거시다. 순환이 보이면 공통 부분을 하위 모듈로 뺀다.
- Editor 전용 코드는 별도 Editor 모듈로.
