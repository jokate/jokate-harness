---
name: game-patterns
description: 게임 프로그래밍 패턴과 엔진 관용구(UE / Unity)를 문제 기준으로 비교하고 트레이드오프를 낸다. "어떤 패턴이 맞나", "State vs 분기", "컴포넌트로 뺄까", "데이터로 뺄까", "이벤트로 풀까 직접 호출할까", "Subsystem 써도 되나", "GAS 로 할까", "ECS 로 갈까", "싱글톤 괜찮나" 같은 구조 질문과, "버프 중첩·스탯 수정치", "입력 선입력·콤보 판정", "애니 판정 창·캔슬 창", "세이브 호환", "UI 와 로직 분리", "네트워크 예측·보간·지연 보상", "초기화 순서", "비동기 로딩 히치", "Utility AI·GOAP·HTN", "이벤트 버스", "리플레이·롤백·고정 타임스텝", "종류마다 클래스·스포너" 같은 게임 도메인 문제에 쓴다. 현재 프로젝트에서 어떤 구조를 고를지 조사하는 절차는 game-architecture 가 맡고, 이 스킬은 그 선택지 C(새 구조)를 채우는 카탈로그다. 고르는 것은 사용자다.
---

# game-patterns — 문제에서 패턴으로

패턴은 이름이 아니라 **해결하는 문제와 치르는 비용**으로 고른다. 이 스킬은 결정 트리와
트레이드오프까지만 낸다. 추천하지 않는다.

## 쓰는 법

1. 사용자의 문제를 아래 두 표에서 찾는다. 없으면 "이 표에 없는 문제"라고 말하고 증상을 한 줄로 되묻는다.
2. 코드에서 **신호**를 확인한다 — 증상이 말뿐인지 실제 코드에 있는지 (`game-onboard` 의 `gq.py find`·`cindex.py refs`, 또는 원문). 신호 목록은 references 에 있다.
3. 후보 패턴 2~3개를 [references/patterns.md](references/patterns.md) 에서 꺼내 "얻는 것 / 잃는 것 / 쓰지 말 때" 한 줄씩.
4. 엔진 관용구로 번역한다 — 이미 엔진에 있는 것을 다시 만들지 않는다:
   [references/ue-idioms.md](references/ue-idioms.md) · [references/unity-idioms.md](references/unity-idioms.md)
5. 프로젝트에 이미 같은 역할을 하는 구조가 있으면 그것을 먼저 적는다.

출처 표시를 답에 그대로 옮긴다: `[서적]` `[공식]` `[커뮤니티]` 는 원문 확인, `[공식·요약]` 과 `‡` 는 검색 요약만 확인, `(추론)` 은 출처 없음, "출처 미확보"는 찾지 못함.
엔진 API 이름은 쓰기 전에 그 프로젝트 엔진에서 `ue_q.py sym` / `api` 로 확인한다 (버전마다 다르다).

## 구조 증상 → 후보

| 증상 | 후보 | 먼저 볼 엔진 관용구 |
|---|---|---|
| 새 "종류"(무기·적·스킬)마다 클래스나 enum+switch 가 늘어난다 | Type Object, Flyweight, 데이터 주도 | UE DataAsset/DataTable · Unity ScriptableObject |
| 한 클래스가 이동·전투·UI·세이브를 다 안다 | Component, Mediator | UE ActorComponent · Unity MonoBehaviour 분리 |
| bool 플래그 조합으로 상태를 표현, 분기 폭발 | State, 계층·푸시다운 상태머신 | UE StateTree · Unity Animator/자체 FSM |
| 같은 알고리즘의 변형을 고르는 조건문이 커진다 | Strategy, Type Object | UE `TInstancedStruct` · Unity SO 교체 |
| A 가 일어나면 B, C, D 가 반응해야 하고 A 는 몰라야 한다 | Observer, Event Queue | UE 델리게이트·GameplayEvent/Message · Unity C# event·SO 채널 |
| 입력·AI·리플레이가 같은 행동을 요청 | Command | UE GAS Ability 활성화 · Unity Input System 액션 → 커맨드 |
| 어디서든 접근해야 하는 서비스, 교체도 필요 | Service Locator, DI | UE Subsystem · Unity DI 컨테이너 |
| 짧은 수명 객체 대량 생성·파괴 | Object Pool | UE 자체 풀 · Unity `ObjectPool<T>` |
| 기능을 켜고 끄는 단위로 떼고 싶다 | 플러그인/모듈 경계 | UE Game Features · Unity asmdef/패키지 |
| 수천 개 동일 엔티티, 성능이 병목 | Data Locality, ECS | UE Mass · Unity DOTS/Entities |
| 디자이너가 코드 없이 행동을 조합 | Bytecode/그래프, Subclass Sandbox | UE BP·StateTree·GAS · Unity 그래프 툴 |

## 게임 도메인 증상 → 후보

줄마다 신호·얻음/잃음·관용구 상세는 [references/domain.md](references/domain.md) 의 같은 글자 절.

| | 증상 | 후보 | UE 관용구 |
|---|---|---|---|
| a | 버프가 끝나도 값이 안 돌아온다 · 중첩 규칙 · CC bool 증가 | Attribute+Modifier 집계, Decorator, 태그+요구조건 | GAS Modifier·Stacking·Tag |
| b | 선입력이 씹힌다 · 236P 판정 · 리매핑 | Command, Input Buffer, 프레임 입력 스냅샷 | Enhanced Input (버퍼는 게임 코드) |
| c | 판정이 애니와 어긋난다 · 캔슬 창 하드코딩 | 애님 이벤트→Observer, Notify State+State, Pushdown | AnimNotify(State), Montage Section·Branching Point |
| d | 패치 후 세이브가 깨진다 · 되돌리기 | Memento, 상태 격리 블록, 버전 헤더+단계 마이그레이션 | USaveGame, 커스텀 버전 ‡ |
| e | 전투 코드가 위젯을 안다 · 위젯이 매 틱 폴링 | MVP, MVVM, Observer | UMG Viewmodel(Beta), CommonUI |
| f | 입력이 늦다 · 보정으로 튄다 · 엄폐했는데 맞았다 | 예측+보정, 스냅샷 보간, 지연 보상, lockstep/rollback | CharacterMovement, GAS 예측, Iris/RepGraph |
| g | 가끔 null · 초기화 순서 가정 | 명시적 전달/DI, Service Locator+Null, 초기화 상태 머신 | Subsystem, GameFramework Init State |
| h | 첫 사용 때 히치 · 메모리가 안 내려간다 | 비동기 요청+핸들, 참조 카운트 핸들, Pool/미리 데우기 | 소프트 참조, StreamableManager, Asset Manager |
| i | 전이 폭발 · if 사다리 · 목표만 주고 싶다 | Utility AI, GOAP, HTN, Blackboard | StateTree 유틸리티 선택, BT+Blackboard |
| j | 업적·UI 가 전투에 직접 걸림 · 이벤트 무한 루프 | Observer, Event Queue, 태그 채널 라우터 | Lyra GameplayMessage(샘플), GAS Event |
| k | 프레임레이트마다 결과가 다르다 · 리플레이 불일치 | Fixed timestep, Command 기록, lockstep/rollback | Substepping, Async Physics ‡ |
| l | 종류마다 스포너 · 데이터 복붙 · 같은 데이터 수천 벌 | Type Object, Prototype, Flyweight | DataAsset, CDO, `FInstancedStruct` |

## 공통 경고

- 패턴 도입의 비용은 **간접화**다. 흐름 추적이 어려워지는 만큼 디버깅 도구(로그, 시각화)가 같이 와야 한다.
- 싱글톤·Service Locator·Subsystem 은 의존을 숨긴다. 호출부에서 의존이 안 보이면 테스트와 교체가 어렵다.
- 이벤트는 송신자와 수신자를 분리하지만 **정적 그래프에서 사라진다**. `game-architecture` 의 sequence 그림으로 보완.
- 새 추상화는 같은 축의 요청이 2건 이상 있을 때. 1건이면 국소 해결 + "다음에 오면 X 로" 메모.
- 네트워크·결정론 패턴(예측, 롤백, lockstep)은 게임 전체 구조를 바꾼다. 한 기능 요청으로 도입하지 않고 사용자에게 범위를 먼저 확인한다.
