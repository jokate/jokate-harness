# Unreal Engine 관용구 — 패턴을 엔진 기능으로

## 출처 표시 (먼저 읽는다)

- 1~7절: API 이름을 UE 5.7 헤더로 확인했다 (`ue_q.py`). 다른 버전은 확인 필요.
- 8절 이후 (2026-10-06 보강): Epic 공식 문서 페이지를 근거로 했다. 다만 보강한 환경에서 dev.epicgames.com 원문 조회가
  네트워크 정책에 막혀 **검색 요약으로만 확인**했다 → `[공식·요약]`. GitHub 공개 자료는 `[커뮤니티]`. 확인 못 한 것은 "확인 필요".
- 버전: URL 에 `application_version=5.x` 가 있으면 그 버전, 없으면 최신 문서(요약에 버전 표시가 안 보임).
- **코드에 쓰기 전에** 그 프로젝트 엔진에서 `ue_q.py sym <이름>` → `api <이름>` 으로 이름과 시그니처를 확인한다. 여기 적힌 이름은 출발점이다.
- 공식 문서 URL 접두사 `https://dev.epicgames.com/documentation/en-us/unreal-engine/` 는 `…/` 로 줄인다.

## 목차
1. 수명과 서비스: Subsystem
2. 조합: ActorComponent, Game Features
3. 데이터: DataAsset, DataTable, GameplayTag
4. 능력: GAS 개요
5. 이벤트: 델리게이트, GameplayMessage
6. 상태·AI: StateTree, Behavior Tree
7. 모듈 경계: Build.cs, 플러그인
8. 객체 수명: UPROPERTY 참조, TObjectPtr, TWeakObjectPtr, TStrongObjectPtr
9. 로딩: 소프트 참조, FStreamableManager, Asset Manager
10. 인터페이스: UINTERFACE
11. 입력: Enhanced Input
12. 애니메이션 타이밍: Notify, Notify State, Montage
13. 네트워크: RepNotify, RPC, Replication Graph / Iris, 예측
14. 다형 데이터: FInstancedStruct
15. GAS 세부: 수정자·스택·GE 컴포넌트·Cue·Ability Task
16. UI: UMG Viewmodel, CommonUI
17. 대량 엔티티·상호작용: Mass, Smart Objects
18. StateTree 세부: 스키마, 유틸리티 선택
19. 데이터 서비스·검증: Data Registry, Data Validation
20. 시간과 순서: Timer, Tick Group, Tick 선행 조건
21. Subsystem 세부와 초기화 순서: Init State
22. 월드 스트리밍: World Partition
23. 상태·버전 요약표

## 1. 수명과 서비스 — Subsystem

`UEngineSubsystem` / `UEditorSubsystem` / `UGameInstanceSubsystem` / `UWorldSubsystem` / `ULocalPlayerSubsystem`.
공식 문서의 이점: 엔진 클래스를 오버라이드하지 않고, 이미 큰 클래스에 API 를 더 붙이지 않고, BP·Python 에 노출.
얻음: 수명이 명확한 서비스. 잃음: 범위가 정해진 싱글톤 = Service Locator 의 의존 은닉 (추론).
https://dev.epicgames.com/documentation/en-us/unreal-engine/programming-subsystems-in-unreal-engine

## 2. 조합 — ActorComponent, Game Features

- ActorComponent: Component 패턴 그대로. 컴포넌트 간 통신은 소유 액터 인터페이스 / 델리게이트 / GAS 중 하나로 통일한다.
- Game Features + Modular Gameplay: 기능을 플러그인으로 떼고 `UGameFeatureAction_AddComponents` 로 대상 액터에 컴포넌트를 주입. 액터는 `UGameFrameworkComponentManager` 에 리시버로 등록.
  얻음: 무관한 기능 간 우발적 의존 차단, 기능 단위 켜기/끄기. 잃음: 초기화 순서·비동기 로딩 간접화. Lyra 샘플이 기준 구현.
  https://dev.epicgames.com/documentation/en-us/unreal-engine/game-features-and-modular-gameplay-in-unreal-engine

## 3. 데이터 — DataAsset, DataTable, GameplayTag

- `UPrimaryDataAsset`: Type Object. Asset Manager 로 비동기 로딩·번들 관리.
- DataTable (`FTableRowBase`): 표 형태 대량 데이터(밸런스). 행 구조체 변경 시 CSV/JSON 재임포트 확인.
- GameplayTag: 계층형 이름. 문자열 비교 대신 쓰지만, 태그는 **전역 네임스페이스**라 남발하면 그 자체가 숨은 결합이 된다. enum·직접 참조로 충분하면 그쪽이 먼저.

## 4. 능력 — GAS 개요

`UAbilitySystemComponent`, `UGameplayAbility`, `UAttributeSet`, `UGameplayEffect`, GameplayCue.
공식 대상 장르: RPG, 액션, MOBA. 얻음: 능력·수치·효과·연출 분리, 네트워크 예측. 잃음: 셋업 부담, 태그 증식 (커뮤니티 통념).
https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-ability-system-for-unreal-engine — 세부는 15절.

## 5. 이벤트

- 델리게이트: `DECLARE_DYNAMIC_MULTICAST_DELEGATE_*` (BP 노출) / 네이티브 멀티캐스트. Observer.
- GameplayEvent (GAS `SendGameplayEventToActor`), Lyra 의 GameplayMessage 서브시스템: 태그 채널 기반 Event Queue 성격. 정적 추적이 안 되니 태그 이름 규칙을 문서화.
- Lyra `UGameplayMessageSubsystem` 은 **엔진이 아니라 Lyra 샘플 플러그인**이다 (런타임 모듈 `GameplayMessageRuntime`, `UGameInstanceSubsystem` 파생).
  `BroadcastMessage(채널 태그, USTRUCT)` / `RegisterListener` → 핸들로 해제. 헤더 주석: **한 채널의 리스너 호출 순서는 보장되지 않는다**.
  네트워크 코드가 없다 — 로컬 전용이고, 네트워크로 가는 것은 GAS Gameplay Event 쪽. 공식 문서 페이지는 찾지 못했다.
  [커뮤니티] https://github.com/thedodd/GameplayMessageRouter · https://github.com/imnazake/GameplayMessageRouter/blob/master/Source/GameplayMessageRuntime/Public/GameFramework/GameplayMessageSubsystem.h

## 6. 상태·AI

- StateTree: 계층 상태머신 + 조건·태스크 데이터화. 게임플레이 상태에도 쓸 수 있다. 세부는 18절.
- Behavior Tree: AI 의사결정. 상태가 많고 전이가 명시적이면 StateTree 가 맞는 경우가 많다 — 프로젝트에 이미 있는 쪽을 따른다.

## 7. 모듈 경계

- Build.cs 의 Public 의존은 헤더를 통해 전파된다. 구현에서만 쓰면 Private 으로.
- 순환 모듈 의존은 빌드를 느리게 하고 `CircularlyReferencedDependentModules` 는 레거시다. 순환이 보이면 공통 부분을 하위 모듈로 뺀다.
- Editor 전용 코드는 별도 Editor 모듈로.

## 8. 객체 수명 — 참조 종류가 곧 소유 설계다

패턴: 소유(강한 참조) / 비소유(약한 참조) / 범위 고정 루트.

| 쓰는 곳 | 도구 | 주의 |
|---|---|---|
| UObject 가 UObject 를 소유 | `UPROPERTY()` + `TObjectPtr<T>` (UE5) | 에디터 빌드에서 접근 추적·해석, 비에디터 빌드에서는 원시 포인터처럼 동작. 필요할 때 로드하지 않는다 → 지연 로드는 `TSoftObjectPtr` |
| 관찰만 (수명에 관여 안 함) | `TWeakObjectPtr<T>` | GC 되면 스스로 null. 쓰기 전 `IsValid` |
| UObject 가 아닌 C++ 객체가 UObject 를 붙듦 | `TStrongObjectPtr<T>` | `UPROPERTY` 로 못 쓴다. UObject 안에 두면 회수 못 하는 순환 위험 |

- `UPROPERTY` 없는 원시 `UObject*` 멤버는 GC 가 모른다 — 댕글링의 흔한 원인 (공식 문서의 "UPROPERTY 로 붙들어야 산다").
- 증분 GC(`gc.AllowIncrementalReachability`): **Experimental**. 완전 스레드 안전이 아니고, 모든 UPROPERTY 원시 포인터를 `TObjectPtr` 로 바꿔야 한다. 도입 버전 확인 필요.
- [공식·요약] …/unreal-object-handling-in-unreal-engine · https://dev.epicgames.com/documentation/unreal-engine/object-pointers-in-unreal-engine · …/incremental-garbage-collection-in-unreal-engine

## 9. 로딩 — 소프트 참조, FStreamableManager, Asset Manager

패턴: 핸들 기반 지연 로딩, 완료 콜백, ID + 번들 묶음.

- 하드 참조는 로드가 연쇄된다(메모리 증가). 소프트 참조(`TSoftObjectPtr` / `TSoftClassPtr`, 내부는 `FSoftObjectPath`)는 경로만 든다.
- `LoadSynchronous()` 는 프레임 스파이크 — 게임플레이에 영향 없는 곳에서만.
- `FStreamableManager::RequestAsyncLoad` → 완료 델리게이트, `FStreamableHandle`. 로드 중에는 매니저가 하드 참조를 들지만 **델리게이트 뒤에 놓는다** — 계속 쓰려면 다른 곳에서 붙든다.
- Asset Manager: Primary Asset 은 `FPrimaryAssetId`(타입 + 이름)로 부른다. Asset Bundle: 소프트 참조 UPROPERTY 에 `meta=(AssetBundles="…")` → 로드할 때 번들 목록을 준다. 게임은 `UAssetManager` 를 상속해 설정에 지정한다.
- [공식·요약] …/referencing-assets-in-unreal-engine · …/asynchronous-asset-loading-in-unreal-engine · …/asset-management-in-unreal-engine

## 10. 인터페이스 — UINTERFACE

패턴: 상속 결합 없는 능력 질의 (C++·BP 공용).

- `UINTERFACE` (UInterface 파생) + 함수를 담는 `I` 접두 클래스 한 쌍.
- **함정**: BP 에서 구현한 인터페이스는 C++ 객체에 없다 → `Cast<IFoo>` 가 null. `Implements<UFoo>()` 로 확인하고 `IFoo::Execute_함수(Obj)` 로 부른다. 저장은 `TScriptInterface<>`.
- `BlueprintNativeEvent` 의 C++ 본문은 `함수_Implementation`.
- [공식·요약] https://dev.epicgames.com/documentation/unreal-engine/interfaces-in-unreal-engine

## 11. 입력 — Enhanced Input

패턴: Command(입력 → 액션), 컨텍스트 스택(우선순위), 전처리(Modifier) → 판정(Trigger) 파이프라인.

- 네 개념: Input Action(`UInputAction`), Input Mapping Context(런타임에 사용자별 추가·제거·우선순위), Modifier(데드존·축 변환), Trigger(활성화 판정). Chorded Action(`UInputTriggerChordAction`) 내장.
- 5.1 부터 기본 활성, 레거시 Action/Axis 매핑은 deprecated.
- **Combo 트리거(`UInputTriggerCombo`)는 5.8 에서 deprecated** — "불안정하고 에디터에서 매핑 컨텍스트를 망가뜨릴 수 있다". 새 콤보 판정에 쓰지 않는다.
- **입력 버퍼는 엔진 기능으로 문서화돼 있지 않다** (Enhanced Input, GAS 문서 모두에서 못 찾음) → 게임 코드(또는 Ability 쪽)에 둔다. 패턴은 patterns.md 의 Input Buffer.
- 5.8: Enhanced Input 과 Common Input/UI 통합 (중복 데이터 애셋 제거).
- [공식·요약] …/enhanced-input-in-unreal-engine · https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5-8-release-notes · …/python-api/class/InputTriggerCombo?application_version=5.3

## 12. 애니메이션 타이밍 — Notify, Notify State, Montage

패턴: 타임라인 이벤트(애니메이션 시간에 대한 Observer), 구간 상태(시작·틱·끝), 구간 점프·대기열(콤보 체인).

- `UAnimNotifyState`: Begin → (Tick…) → End 순서를 보장한다 — 판정 창·캔슬 창을 구간으로 표현할 때 쓴다 (근거 요약이 최신·4.27 페이지를 섞었다 — 확인 필요).
- Montage 알림 **Tick Type**: `Queued`(비동기, 싸다, 한 프레임 어긋날 수 있다) vs `Branching Point`(동기, 프레임 정확, 비싸다). 정확한 시점이 필요할 때만 Branching Point.
- Montage Section: 이름으로 **점프**하거나 현재 구간이 끝나면 재생되게 **대기열**에 넣는다 — 콤보 다음 단을 여기에 둔다.
- 게임 로직을 Notify 에 직접 넣으면 판정이 애니메이션 애셋에 숨는다 → Notify 는 "이벤트 발신"만, 판정은 코드·데이터 쪽.
- [공식·요약] …/animation-notifies-in-unreal-engine · …/animation-montage-in-unreal-engine

## 13. 네트워크 — RepNotify, RPC, Replication Graph / Iris, 예측

패턴: 서버 권한 상태 동기화(+변경 콜백 = Observer), 원격 명령(RPC), 관심 영역 관리, 클라이언트 예측·보정.

- 속성 복제: `Replicated` / `ReplicatedUsing=OnRep_X` + `GetLifetimeReplicatedProps` 에서 `DOREPLIFETIME(_CONDITION)`. 기본은 바뀔 때만 보낸다. `REPNOTIFY_Always` / `REPNOTIFY_OnChanged`.
- RPC: `Server` / `Client`(소유 클라이언트) / `NetMulticast`. **기본 unreliable**. `Reliable` 은 ack 까지 재전송하고 뒤 RPC 가 기다린다(헤드 오브 라인). 클라이언트→서버는 그 액터를 소유해야 한다.
- 규모: Replication Graph(플러그인, 연결별 복제 목록·격자 공간화) **또는** Iris — **둘을 같이 못 쓴다**. Iris 는 문서 페이지가 Experimental, **5.8 릴리스 노트는 production-ready** 로 바꿨다 → 버전마다 다르다.
- 예측: Network Prediction 플러그인·Mover(롤백, CharacterMovement 대체 목표) 모두 **Experimental**.
- GAS 예측(`FPredictionKey`): 능력 활성화, GE 적용(속성·태그·Cue), 몽타주, 이동은 예측된다. **GE 제거와 주기 효과(DoT 틱)는 예측되지 않는다**.
- [공식·요약] https://dev.epicgames.com/documentation/unreal-engine/replicate-actor-properties-in-unreal-engine · https://dev.epicgames.com/documentation/unreal-engine/remote-procedure-calls-in-unreal-engine · https://dev.epicgames.com/documentation/unreal-engine/replication-graph-in-unreal-engine · …/iris-replication-system-in-unreal-engine · …/migrate-to-iris-in-unreal-engine · …/mover-in-unreal-engine · …/API/Plugins/GameplayAbilities/FPredictionKey

## 14. 다형 데이터 — FInstancedStruct

패턴: 타입 지운 다형 값 (USTRUCT 위의 variant). UObject 할당 없이 "종류마다 다른 데이터".

- 반응 매핑·효과 정의처럼 "행마다 다른 구조체"를 데이터로 둘 때 Type Object + Strategy 를 UObject 없이 표현한다.
- 위치가 버전마다 다르다: **5.0–5.4 StructUtils 플러그인**, **5.5 부터 CoreUObject**(5.5 릴리스 노트: production ready, 별도 플러그인 아님). Build.cs 의존 이름 변화는 확인 필요 — `ue_q.py sym FInstancedStruct` 로 그 엔진의 모듈을 본다.
- `TInstancedStruct<Base>` 로 기반 타입을 제한한다. 5.8: Iris 용 `FInstancedStructNetSerializer` 델타 직렬화.
- [공식·요약] https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/CoreUObject/FInstancedStruct · …/unreal-engine-5-5-release-notes

## 15. GAS 세부

패턴: 수정자 스택(속성에 대한 Decorator/Modifier), 크기 계산의 Strategy, 능력 = Command, Ability Task = 비동기 코루틴, Cue = 연출 이벤트 버스.

- **Modifier**: GE 가 속성을 어떻게 바꾸는가. 크기 종류: Scalable Float, Attribute Based, Custom Calculation Class(MMC, `UGameplayModMagnitudeCalculation`), Set By Caller.
- **Execution**(`UGameplayEffectExecutionCalculation`): Modifier 로 안 되는 복잡한 식. [커뮤니티] MMC 는 모든 지속 유형·예측 가능, Execution 은 Instant/Periodic 만·예측 안 됨·여러 속성 변경 가능 (UE 5.3 기준 문서).
- 집계식 `((Base + Add) * Mul) / Div`, 같은 채널의 Mul 들은 **곱하지 않고 더한다** — [커뮤니티] 출처만 있다 (공식 확인 필요). 버프 중첩 수치를 설계할 때 이 차이가 결과를 바꾼다.
- **Stacking**: 이미 붙은 GE 를 다시 적용할 때의 정책. `AggregateBySource`(시전자별) / `AggregateByTarget`(대상당 하나), 만료 정책 Clear Entire Stack / Refresh Duration / Remove Single Stack And Refresh Duration, 오버플로.
- **GE Components**(`UGameplayEffectComponent`, **5.3 도입**): GE 동작을 컴포넌트로. 인스턴스 하나를 모든 적용이 공유 → **적용별 런타임 상태를 두지 않는다**. 내장: 태그 부여·요구, 확률 적용, 면역, 추가 효과, 다른 효과 제거 등.
- **Gameplay Cue**: 연출(VFX/SFX) 복제의 권장 경로. `UGameplayCueNotify_Static`(인스턴스 없음, 일회성) / `AGameplayCueNotify_Actor`(상태·틱 가능). [커뮤니티] 기본 전송은 unreliable multicast.
- **Ability Task**(`UAbilityTask`): 능력 실행 중 비동기 작업(입력 대기, 몽타주, 루트 모션), 능력이 끝나면 정리된다.
- [공식·요약] …/gameplay-effects-for-the-gameplay-ability-system-in-unreal-engine · …/API/Plugins/GameplayAbilities/UGameplayEffectComponent · …/API/Plugins/GameplayAbilities/UGameplayCueNotify_Static · https://dev.epicgames.com/documentation/unreal-engine/gameplay-ability-tasks-in-unreal-engine
  [커뮤니티] https://github.com/tranek/GASDocumentation

## 16. UI — UMG Viewmodel, CommonUI

- **UMG Viewmodel**(플러그인 `ModelViewViewModel`, **Beta**): MVVM. `UMVVMViewModelBase` + View Binding, 필드 변경 알림(`INotifyFieldValueChanged`)으로 위젯을 갱신(push).
  얻음: 위젯 구조를 프로그래머 없이 바꿀 수 있다. 생성 방식: Create Instance / Manual / Global Viewmodel Collection / Property Path / Resolver.
- **CommonUI**: 레이어 스택과 입력 라우팅. 입력은 맨 위 트리로 가고, **활성화 가능 위젯**(`UCommonActivatableWidget`)만 라우팅 노드가 된다. 맨 위 층이 닫히면 다음 층으로 자동 복귀.
  컨테이너 `UCommonActivatableWidgetStack` / `Queue`. 상태 등급(Beta/Production) 확인 필요.
- [공식·요약] …/umg-viewmodel-for-unreal-engine · …/input-fundamentals-for-commonui-in-unreal-engine

## 17. 대량 엔티티·상호작용 — Mass, Smart Objects

- **Mass Entity**: ECS. Fragment(데이터) · Entity(ID) · Archetype(같은 구성의 묶음) · Processor(`UMassProcessor`, 상태 없는 로직, EntityQuery) · Tag(데이터 없는 표식). 수만 개 엔티티 대상.
  5.0 Experimental. 5.8 대개편: Signals 엔진 코어로, **희소(sparse) fragment**(아키타입 변경 없이 추가·제거), 프로세서 스케줄링. 현재 상태 등급 확인 필요.
- **Smart Objects**: 상호작용 지점은 정보만 들고 로직은 상호작용자가 가진다. **예약**: Claim → Use(Occupied) → Release, 해제 전엔 다른 에이전트가 못 쓴다. `USmartObjectSubsystem`. 5.0 Experimental, 이후 등급 확인 필요.
- [공식·요약] …/overview-of-mass-entity-in-unreal-engine · …/smart-objects-in-unreal-engine---overview · https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5-8-release-notes

## 18. StateTree 세부

- 계층 상태머신 + BT 의 Selector. **Schema**(`UStateTreeSchema`)가 쓸 수 있는 컨텍스트·평가기·태스크를 정한다. Evaluator / Global Task 로 상태 선택용 데이터를 낸다.
- 선택 방식에 **유틸리티**가 있다: Try Select Children with Highest Utility / at Random Weighted by Utility. 점수는 **Consideration**(0–1 정규화, AND/OR 결합) × 상태 Weight.
  → Utility AI 를 따로 만들기 전에 이것부터 본다. 도입 버전은 5.5 로 추정(5.5 "new State Selectors" + 5.5 Python 열거형) — 확인 필요.
- 5.4 연결된(linked) StateTree 애셋, 5.8 시작 상태 지정·새 전이 대상(Parent 등). Production 전환 시점 확인 필요.
- [공식·요약] …/overview-of-state-tree-in-unreal-engine · …/state-tree-selectors-overview

## 19. 데이터 서비스·검증 — Data Registry, Data Validation

- **Data Registry**: USTRUCT 행의 전역 저장소(읽기 전용 의도). 소스(DataTable, CurveTable…)를 **순서대로** 겹쳐 뒤 소스가 대체값 → 맥락별 덮어쓰기. `FDataRegistryId`. 즉시 조회는 **캐시에 없으면 못 찾는다** → `AcquireItem`(비동기).
- **Data Validation**: 데이터 실수를 저장·제출 시점에 잡는다. 자기 클래스면 `UObject::IsDataValid(FDataValidationContext&)` 오버라이드, 못 고치는 엔진 클래스면 `UEditorValidatorBase` 파생. `TArray<FText>` 판 검증 API 는 deprecated (5.4 / 5.5 — 출처마다 다름).
  Type Object 로 종류를 데이터로 뺐다면, 빠진 필드·잘못된 조합을 여기서 막는 것이 짝이다.
- [공식·요약] …/data-registries-in-unreal-engine · …/data-validation-in-unreal-engine · …/API/Plugins/DataValidation/UEditorValidatorBase

## 20. 시간과 순서 — Timer, Tick Group, Tick 선행 조건

- **Timer**(`FTimerManager`, 월드·게임 인스턴스마다): `SetTimer`(반복 가능)·`FTimerHandle` 로 일시정지·취소. 대상 객체가 파괴되면 자동 취소. `SetTimerForNextTick` 은 핸들이 없다(취소 불가). 매 프레임 폴링 Tick 의 대안.
- **Tick Group**: `TG_PrePhysics` → `TG_DuringPhysics` → `TG_PostPhysics` → `TG_PostUpdateWork`, 그룹은 다음 그룹 전에 전부 끝난다.
- **Tick 선행 조건**: `AddTickPrerequisiteActor/Component` — 늦은 그룹으로 옮기는 것보다 낫다(같은 그룹 안 병렬성 유지).
  patterns.md 의 "틱 순서 의존"을 명시하는 도구다.
- [공식·요약] …/gameplay-timers-in-unreal-engine · …/actor-ticking-in-unreal-engine

## 21. Subsystem 세부와 초기화 순서 — Init State

- `ShouldCreateSubsystem` 이 false 를 낼 수 있으면(예: 서버 전용) **호출부가 null 검사**를 해야 한다. World Subsystem 은 기본적으로 게임·PIE·에디터 월드에 생기고 **프리뷰 월드에는 없다**(`DoesSupportWorldType`). `UTickableWorldSubsystem` 은 Initialize/Deinitialize 를 Super 로 넘겨야 틱한다.
- 여러 컴포넌트의 초기화 순서 문제 → `UGameFrameworkComponentManager` 의 **Init State**: 태그로 상태를 등록(`RegisterInitState`), `RegisterAndCallForActorInitState` 는 **이미 그 상태면 즉시 호출**(놓친 이벤트 경합 없음). `IGameFrameworkInitStateInterface`.
  `InitState.Spawned → DataAvailable → DataInitialized → GameplayReady` 는 **Lyra 가 정의한 태그**지 엔진 정의가 아니다.
- Extension Handler 이벤트는 상태가 없다 — 지금 등록된 핸들러에만 간다. 반환 핸들을 들고 있어야 델리게이트가 산다.
- [공식·요약] https://dev.epicgames.com/documentation/unreal-engine/programming-subsystems-in-unreal-engine · …/game-framework-component-manager-in-unreal-engine

## 22. 월드 스트리밍 — World Partition

- 하나의 영속 레벨을 격자 셀로 나누고 **스트리밍 소스**(기본은 PlayerController) 주변을 로드한다. Cell Size, Loading Range, 액터별 Is Spatially Loaded. Data Layer, One File Per Actor, Level Instance.
- **함정**: 다른 액터를 참조하는 액터는 묶여 같이 로드된다 → 더 큰 셀로 올라가 "항상 로드"처럼 보일 수 있다 (Epic KB 요약).
- [공식·요약] …/world-partition-in-unreal-engine

## 23. 상태·버전 요약표 (찾은 것만)

| 기능 | 상태 | 버전 |
|---|---|---|
| Enhanced Input | 기본 | 5.1 기본 활성 · Combo 트리거 5.8 deprecated |
| Iris | 문서 Experimental → 5.8 릴리스 노트 production-ready | Replication Graph 와 같이 못 씀 |
| Network Prediction / Mover | Experimental | — |
| FInstancedStruct | production (5.5) | 5.0–5.4 StructUtils 플러그인 → 5.5 CoreUObject |
| UMG Viewmodel | Beta | 5.1 |
| Mass Entity | 5.0 Experimental | 5.8 대개편 |
| Smart Objects | 5.0 Experimental | 이후 확인 필요 |
| StateTree | 5.0 Experimental | 5.4 linked · 5.5 유틸리티 선택(추정) · 5.8 시작 상태 |
| GE Components | — | 5.3 |
| 증분 GC | Experimental | 확인 필요 |
| Lyra GameplayMessageRouter | 샘플 플러그인 (엔진 아님) | — |
