# 게임 도메인 증상 — 신호 · 후보 패턴 · 엔진 관용구

SKILL.md 증상 표의 게임 도메인 줄을 펼친 것이다. 줄마다 **증상(사용자 말투) → 코드에서 보이는 신호 → 후보 2~3개(얻음/잃음) → 엔진 관용구**.
후보의 상세(언제·함정·설계 결정)는 [patterns.md](patterns.md), UE 기능 상세는 [ue-idioms.md](ue-idioms.md).

## 출처 표기

- `[서적]` 책 · `[공식]` 엔진·벤더 문서와 공식 샘플 · `[커뮤니티]` 블로그·위키·오픈소스 문서 · `[공식·요약]` 공식 페이지를 검색 요약으로만 확인
- `‡` 검색 요약만 확인한 주장 (원문 미열람) — 답에 쓸 때 그대로 표시한다
- `(추론)` 출처가 직접 말하지 않은 연결 — 답에 쓸 때 "추론"이라고 밝힌다
- 2026-10-06 수집. 원 사이트(gameprogrammingpatterns.com, gafferongames.com, dev.epicgames.com 등)가 수집 환경에서 막혀 같은 원고의 공개 저장소 사본을 읽었다:
  - GPP = Robert Nystrom, *Game Programming Patterns* 원고 `https://raw.githubusercontent.com/munificent/game-programming-patterns/master/book/<장>.markdown` (정식 `https://gameprogrammingpatterns.com/<장>.html`)
  - Gaffer = `https://raw.githubusercontent.com/gafferongames/gafferongames/master/content/post/<글>.md` (gafferongames.com 사이트 원고)
  - UnityMP = `https://raw.githubusercontent.com/Unity-Technologies/com.unity.multiplayer.docs/main/docs/learn/<문서>.md` (Unity 멀티플레이 공식 문서 원고)
  - GGPO = `https://raw.githubusercontent.com/pond3r/ggpo/master/doc/DeveloperGuide.md`
  - GASDoc = `https://raw.githubusercontent.com/tranek/GASDocumentation/master/README.md` (Epic GAS 를 설명하는 커뮤니티 문서, UE 5.3 기준)
  - UnityDemo = `https://github.com/Unity-Technologies/game-programming-patterns-demo` (Unity 디자인 패턴 e-book 공식 샘플)

## 목차
a. 버프·디버프·CC 중첩, 스탯 수정치
b. 입력 선입력(버퍼)·커맨드 입력·콤보
c. 애니메이션 타이밍에 묶인 로직 (판정 창·캔슬 창)
d. 저장·불러오기, 세이브 호환
e. UI 와 게임플레이 분리
f. 네트워크 권한·예측·보간·지연 보상
g. 초기화 순서
h. 비동기 로딩·스트리밍
i. FSM/BT 를 넘는 AI 의사결정
j. 태그·채널 기반 메시징
k. 리플레이·되돌리기·결정론
l. 변형 스폰 (종류마다 클래스·스포너)

## a. 버프·디버프·CC 중첩, 스탯 수정치

- **증상**: "버프가 끝나면 원래 값으로 안 돌아온다", "% 버프와 고정 버프 순서에 따라 값이 다르다", "같은 슬로우가 두 번 걸리면 겹쳐야 하나", "스턴 중 공격 금지 bool 이 늘어난다".
- **신호**: 버프 적용·해제 때 스탯 필드를 직접 `+=`/`-=` 한다. 최대치와 현재치가 한 변수에 섞였다. `bIsStunned`, `bIsSilenced` 같은 플래그가 늘어난다 (추론).
- **후보**
  1. **Attribute + Modifier 집계** — 기본값과 수정치 목록을 따로 들고 현재값을 계산한다. 얻음: 해제가 목록에서 빼기. 잃음: 연산 순서·공식을 정해 문서화해야 한다.
     GAS 는 Base/Current 를 나누고 `((Base + Add) * Mul) / Div` 로 합치며, 같은 채널의 Mul/Div 는 **곱하지 않고 더한 뒤** 적용한다 — "곱 버프 두 개 = 곱의 곱"이 아니다. 최대치는 별도 속성으로 둔다. Instant·Periodic 은 Base 를, Duration/Infinite 는 Current 를 바꾼다. [커뮤니티] GASDoc
  2. **Decorator(래퍼 체인)** — 같은 인터페이스로 감싸 덧붙인다. 잃음: 스택 중간 래퍼 하나를 빼기 어렵다 → 만료형 버프와 충돌 ‡ (https://refactoring.guru/design-patterns/decorator). 개별 제거가 잦으면 1번(목록 집계)이 맞다 (추론).
  3. **태그 + 요구조건** — CC 를 bool 대신 계층 태그로, 효과·능력이 "이 태그가 있으면 적용 안 함" 같은 조건을 가진다. 얻음: 조합 폭발 없이 조건이 데이터. 잃음: 태그 체계 설계·관리. [커뮤니티] GASDoc (Granted Tags, Application/Ongoing Tag Requirements, Immunity)
- **별도 결정 축 — 중첩 정책**: 시전자별 스택(Aggregate by Source) vs 대상당 한도(by Target), 만료·지속시간 갱신·주기 리셋. Paragon 슬로우: 중첩은 안 되지만 각자 수명은 추적하고 가장 센 것만 적용. [커뮤니티] GASDoc
- **UE**: GAS (AttributeSet, GE Modifier/Stacking, GameplayTag, GE Components 5.3+) — ue-idioms.md 15절. **Unity**: 내장 없음, 직접 만든 Stat/Modifier 클래스나 애셋.

## b. 입력 선입력(버퍼)·커맨드 입력·콤보

- **증상**: "모션 끝나기 직전 누른 공격이 씹힌다", "236P 인식이 빡빡하다", "키 리매핑을 넣으려니 입력 코드가 로직에 박혀 있다", "입력을 리플레이·네트워크로 보내고 싶다".
- **신호**: 입력 핸들러가 바로 `Jump()`/`Attack()` 을 부른다 (GPP command 도입부의 `if (isPressed(BUTTON_X)) jump();`). 행동 불가 상태에서 들어온 입력은 버린다.
- **후보**
  1. **Command** — 입력을 명령 객체로. 얻음: 리매핑, 플레이어·AI 가 같은 명령, 큐·직렬화(네트워크·리플레이). 잃음: 객체·클로저 증가. [서적] GPP command
  2. **Input Buffer(시간창 링버퍼)** — 최근 N 프레임 입력을 들고 있다가 행동 가능해지는 프레임에 소비하거나 패턴(236 등)과 매칭. 얻음: 타이밍 관용. 잃음: 버퍼 길이가 곧 게임 감각 (예시 수치 ‡: Smash 10F, SF6 4F).
     UE4 플러그인 사례: PlayerController 에 버퍼, "입력 시퀀스" 애셋과 매칭. [커뮤니티] https://raw.githubusercontent.com/Isatin/UE4InputBuffer/master/README.md
  3. **프레임별 입력 스냅샷(구조체)** — 시뮬레이션 프레임 시작에 키 상태를 구조체로 샘플링, 누름/뗌 이벤트를 보내지 않는다. 얻음: 결정론적 재생·전송에 맞다. 잃음: 틱 단위로 양자화. [커뮤니티] Gaffer deterministic_lockstep · GGPO
- **UE**: Enhanced Input 에 **입력 버퍼 기능은 문서화돼 있지 않다** → 게임 코드에 둔다. Combo 트리거는 5.8 에서 deprecated. Chorded Action 은 있다. — ue-idioms.md 11절. **Unity**: 내장 버퍼 없음 (관용구 출처 미확보).

## c. 애니메이션 타이밍에 묶인 로직 (판정 창·캔슬 창)

- **증상**: "공격 판정이 애니와 어긋난다", "재생 속도를 바꾸니 히트 판정이 안 나온다", "캔슬 구간을 코드 타이머로 하드코딩했다", "서버·클라 몽타주가 안 맞는다".
- **신호**: `Invoke("EnableHitbox", 0.23f)` 같은 매직 타이머, 애니 길이 상수 복제, 애니 상태 이름 문자열 비교 (추론).
- **후보**
  1. **애님 이벤트 → 게임플레이 이벤트(Observer)** — 클립 시점에 이벤트를 심고 로직이 받는다. 얻음: 타이밍을 아티스트·디자이너가 데이터로 소유. 잃음: 로직이 애님 애셋·재생 속도·블렌딩에 의존. GAS `PlayMontageAndWaitForEvent`: 몽타주 AnimNotify 가 보낸 GameplayEvent 를 능력이 받는다. [커뮤니티] GASDoc
  2. **구간 이벤트(Notify State) + State** — 히트박스 on/off, 무적, 캔슬 가능을 상태 진입/이탈로. 얻음: 시작·끝이 짝. 잃음: 중단(블렌드아웃·인터럽트) 때 End 가 오는지 확인해야 한다. 게임플레이에 중요한 알림은 Branching Point 로 — 공식 문서 요약: 프레임 정확, 대신 비싸다 [공식·요약].
  3. **Pushdown State** — "공격 끝나면 이전 상태로"를 상태 스택 push/pop 으로. 얻음: "X 하면서 공격" 상태 복제 없음. 잃음: 스택 오염·복귀 규칙 관리. [서적] GPP state
- **네트워크 주의**: 게임 결과에 영향 없는 애니·VFX·사운드만 먼저 재생하고 결과는 서버를 기다리는 action anticipation [공식] UnityMP dealing-with-latency. GAS 몽타주는 `PlayMontage` 대신 `PlayMontageAndWait` 태스크여야 ASC 로 복제된다 [커뮤니티] GASDoc.
- **UE**: AnimNotify / AnimNotifyState / Montage Section·Branching Point, GAS AbilityTask — ue-idioms.md 12·15절. **Unity**: Animation Event (매개변수 하나) ‡.

## d. 저장·불러오기, 세이브 호환

- **증상**: "패치 후 옛 세이브가 깨진다", "세이브에 포인터·런타임 캐시까지 들어간다", "되돌리기를 넣으려니 상태 전체 복사가 무겁다".
- **신호**: 런타임 객체를 통째로 직렬화. 세이브에 버전 필드 없음. 게임 상태와 표시·캐시 상태가 한 클래스. 정적 변수에 진행 상태가 숨어 있다 (GGPO 가 경고하는 형태).
- **후보**
  1. **Memento(스냅샷)** — 얻음: 되돌리기·롤백. 잃음: 잦으면 메모리, 스냅샷 수명 관리 ‡. GPP: 명령 단위 undo 에는 바뀐 부분만 저장하는 쪽이 싸다 [서적] GPP command.
  2. **게임 상태 격리 + 단일 직렬화 블록** — 결과에 영향 주는 상태만 한곳에. 렌더·오디오·룩업 테이블 제외, 포인터는 베이스+오프셋, 정적·숨은 상태를 찾아 옮긴다. 얻음: 저장·로드·롤백이 단순. 잃음: 기존 코드의 숨은 상태를 찾는 비용. [커뮤니티] GGPO
  3. **버전 헤더 + 단계별 마이그레이션** — 파일 앞 버전, 버전별 옛 구조체 고정 보관, v4→v5→v6 한 단계씩. 얻음: 옛 세이브 호환. 잃음: 옛 스키마 코드를 계속 유지. 버전 없는 옛 파일 판별법까지 다루는 사례 [커뮤니티] https://raw.githubusercontent.com/wiki/pret/pokeemerald/How-to-Support-Savefile-Backwards-Compatibility.md
- **UE**: `USaveGame` + `UGameplayStatics` 저장, 커스텀 버전 `FCustomVersionRegistration` 으로 FArchive 직렬화 분기 ‡ — `ue_q.py sym FCustomVersionRegistration` 로 확인 후 쓴다. **Unity**: 공식 출처 미확보.

## e. UI 와 게임플레이 분리

- **증상**: "HP바 갱신 때문에 전투 코드가 위젯을 참조한다", "UI 를 바꾸면 로직이 깨진다", "위젯이 매 틱 게임 값을 폴링한다", "UI 로직을 씬 없이 테스트하고 싶다".
- **신호**: 게임플레이 클래스에 `HealthText->SetText(...)`, 위젯 Tick 에서 게임 객체 조회, 같은 값을 여러 UI 가 따로 폴링 (추론).
- **후보**
  1. **MVP** — Presenter 가 Model 을 갱신하고 View 를 다룬다. 얻음: Presenter 를 엔진 객체 없이 목 View 로 테스트. 잃음: 보일러플레이트 ‡.
  2. **MVVM(바인딩)** — ViewModel 의 변경을 바인딩으로 View 에 전달, UI 이벤트는 ViewModel 메서드로 Model 을 바꾼다. Unity 공식 샘플은 ViewModel 을 Model 과 View 사이의 중재자로 둔다 [공식] UnityDemo `7_MVVM/Scripts/HealthViewModel.cs`. 잃음: 바인딩 프레임워크 의존, 디버깅 경로 간접 (추론).
  3. **Observer 단방향 통지** — 게임플레이는 이벤트만, UI 가 구독. 얻음: 게임플레이가 UI 를 모른다. 잃음: Observer 일반 비용 (patterns.md).
- **UE**: UMG Viewmodel(Beta, `FieldNotify`) · CommonUI — ue-idioms.md 16절. 바인딩이 매 프레임 폴링된다는 포럼 보고 ‡. **Unity**: UI Toolkit runtime data binding(Unity 6) ‡, UnityDemo `7_MVP`, `7_MVP_UIToolkit`, `7_MVVM`.

## f. 네트워크 권한·예측·보간·지연 보상

- **증상**: "입력하고 한 박자 늦게 움직인다", "서버 보정으로 튄다(rubber banding)", "다른 플레이어가 뚝뚝 끊긴다", "분명 맞췄는데 안 맞았다", "엄폐했는데 맞았다", "클라가 '내가 죽였다'를 보낸다".
- **신호**: 클라가 결과(위치·킬)를 RPC 로 통보하고 서버가 검증하지 않는다. 서버 상태 수신 즉시 위치를 덮어쓴다. `if (IsServer)` 분기가 기능마다 흩어져 있다 — Unity 문서는 authoritative / non-authoritative 로 추상화하라고 한다 [공식] UnityMP.
- **선택지 (UnityMP dealing-with-latency 요약표 [공식])**: 클라 권한(빠름, 보안 약함) · action anticipation(보안 강함, 시각 불일치 가능) · prediction(둘 다 좋지만 보정 필요, "복잡하고 촉수를 뻗는다") · server-side rewind(정확, 공격자 유리, "벽 뒤에서 맞음").
- **원칙**: 기본은 서버 권한, 보안·일관성 영향이 작은 사용자 소유 입력(조준 방향 등)만 클라 권한 예외. 판단 질문은 "서버가 이걸 정정할 수 있나". 클라 RPC 는 늘 검증. [공식] UnityMP
- **후보 상세**: Client-side prediction & reconciliation · Snapshot interpolation · Lag compensation · (대전·RTS) Deterministic lockstep / Rollback — patterns.md "네트워크".
- **UE**: CharacterMovement 이동 예측, GAS `FPredictionKey`(GE 제거·주기 효과는 예측 안 됨, 데미지·사망 예측 비권장 — "가능한 최소만 예측" [커뮤니티] GASDoc), Iris/Replication Graph, Mover(Experimental) — ue-idioms.md 13절. **Unity**: NGO 는 서버 권한, NetworkTransform 보간, 완전한 예측·서버 되감기는 직접 구현 [공식] UnityMP.

## g. 초기화 순서

- **증상**: "어떤 때는 null, 어떤 때는 정상", "A 의 BeginPlay 가 B 보다 먼저라고 가정했다", "클라에서만 PlayerState 가 아직 없어 초기화 실패", "싱글톤 첫 접근 때 프레임이 튄다".
- **신호**: 지연 초기화 싱글톤, 서로의 초기화 콜백에서 상대를 조회, 실행 순서 설정이나 한 프레임 미루기로 땜질 (추론. 지연 초기화 문제 자체는 GPP singleton).
- **후보**
  1. **명시적 전달 / 의존성 주입** — 얻음: 결합이 코드에 드러난다. 잃음: 깊은 호출 계층의 인자 배관. GPP: 먼저 넘겨주기를 고려하고, 로깅·오디오처럼 본질적으로 하나뿐인 것만 Service Locator. [서적] GPP service-locator
  2. **Service Locator + Null Service** — 얻음: 미등록이어도 게임이 돈다. 잃음: 의존이 런타임까지 숨는다. [서적] GPP service-locator
  3. **엔진 수명 범위 + 초기화 상태 머신** — UE `UGameFrameworkComponentManager` Init State: 이미 도달한 상태면 콜백이 즉시 온다(놓친 이벤트 경합 없음) [공식·요약]. 잃음: 엔진 규약에 묶인다.
- **함정 근거**: 지연 초기화는 초기화 시점(히치)과 힙 배치를 통제할 수 없게 한다 [서적] GPP singleton. GAS 에서 ASC 가 PlayerState 에 있으면 서버는 `PossessedBy`, 클라는 `OnRep_PlayerState` 에서 초기화한다 — `SetupPlayerInputComponent` 시점엔 PlayerState 가 아직 복제 안 됐을 수 있다 [커뮤니티] GASDoc. Unity 는 객체 간 Awake 순서가 비결정적이다 ‡.
- **UE**: Subsystem `ShouldCreateSubsystem` null 검사, Init State — ue-idioms.md 21절.

## h. 비동기 로딩·스트리밍

- **증상**: "무기를 처음 꺼낼 때 프레임이 튄다", "레벨 진입이 길다", "메모리에서 안 내려간다", "비동기로 불렀는데 게임 스레드가 멈춘다".
- **신호**: 하드 참조로 거대 애셋 체인을 붙잡는다. 소프트 참조를 바로 `LoadSynchronous`/`Get()` 으로 푼다. 로드 핸들을 놓지 않는다 (추론).
- **후보**
  1. **비동기 요청 + 완료 콜백 + 핸들 수명** — 얻음: 히치 제거. 잃음: 로드 전 상태 처리, 핸들 해제. UE `FStreamableManager::RequestAsyncLoad` 는 콜백 동안만 붙들어 준다 [공식·요약].
  2. **참조 카운팅 핸들** — 얻음: 공유 애셋의 안전한 해제. 잃음: Release 짝 맞추기(누수 위험). Unity Addressables 핸들 ‡.
  3. **Object Pool / 미리 데우기** — 얻음: 런타임 할당·로드 제거. 잃음: 메모리 상주. [서적] GPP object-pool
- **UE**: 소프트 참조, Asset Manager·Primary Asset·Bundle, World Partition — ue-idioms.md 9·22절.

## i. FSM/BT 를 넘는 AI 의사결정

- **증상**: "상태 전이가 폭발한다", "우선순위 if-else 사다리에 매직 임계값", "상황에 맞는 그럴듯한 차선책을 고르게 하고 싶다", "목표만 주면 행동 순서를 스스로 짜게", "두 목표 사이를 왔다 갔다 한다".
- **신호**: 상태 수가 '하는 일 × 들고 있는 것' 처럼 곱으로 는다 (GPP state 가 지적하는 조합 폭발). 상태마다 같은 전이 코드 중복.
- **후보**: Utility AI · GOAP · HTN, 공유 지식은 Blackboard — patterns.md "AI 의사결정".
- **근거**: FSM 의 강점(제한된 구조)이 복잡한 AI 에서는 약점이고 업계 흐름은 BT·플래닝 쪽. FSM 이 맞는 경우: 상태가 적고 뚜렷하며 시간에 걸친 입력에 반응할 때. [서적] GPP state
- **UE**: StateTree 유틸리티 선택(Consideration) — 따로 만들기 전에 이것부터 (ue-idioms.md 18절). Behavior Tree + Blackboard(Observer Aborts) ‡. GOAP·HTN 은 내장 없음.

## j. 태그·채널 기반 메시징

- **증상**: "업적·튜토리얼·UI 가 전투 코드에 직접 걸려 있다", "누가 이 이벤트를 받는지 모르겠다", "이벤트 처리 중 또 이벤트가 나서 무한 루프", "죽은 객체에 이벤트가 간다".
- **신호**: 전투 코드에서 업적·튜토리얼을 직접 호출. 문자열 이벤트 이름. 전역 이벤트 매니저 하나에 전부 등록.
- **후보**
  1. **Observer(동기)** — 얻음: 단순·빠름. 잃음: 느린 수신자가 송신자를 막는다, 수명 관리(댕글링·해제 누락), 흐름이 정적으로 안 보인다. [서적] GPP observer
  2. **Event Queue(비동기)** — 얻음: 시간 분리, 수신 측의 지연·합치기·버리기. 잃음: 중앙 큐 = 전역 변수, 처리 시점 상태 변화, 피드백 루프. 응답이 필요한 송신엔 부적합. [서적] GPP event-queue
  3. **채널 키 라우터(태그 채널 + 타입 페이로드)** — 얻음: 무관한 객체 간 통신, 계층 태그로 채널 조직. 잃음: 채널 규약 관리, 정적 추적 어려움, 복제 안 됨. [커뮤니티] Lyra GameplayMessageRouter 재배포본 README
- **UE**: Lyra GameplayMessageSubsystem(샘플 플러그인, 로컬 전용, 리스너 순서 보장 안 됨), GAS `SendGameplayEventToActor`, 델리게이트 — ue-idioms.md 5절.

## k. 리플레이·되돌리기·결정론

- **증상**: "프레임레이트에 따라 점프 높이가 다르다", "느린 PC 에서 물리가 폭주한다", "리플레이가 원본과 다르게 흘러간다", "되돌리기를 넣고 싶다", "대전 온라인이 끊긴다".
- **신호**: 물리·로직에 가변 `DeltaTime` 을 그대로 넣는다. 로직에서 벽시계나 시드 관리 안 된 RNG. 렌더·사운드 코드가 시뮬레이션 단계 안에서 돈다 (Gaffer, GGPO 가 직접 지적).
- **후보**
  1. **Fixed timestep(누산기 + 보간)** — patterns.md.
  2. **Command 기록 재생 / Command undo** — 리플레이는 프레임별 명령을 기록하고 재시뮬레이션, undo 는 명령마다 이전 값만 저장. 얻음: 저장량이 작다. 잃음: 모든 변경이 명령을 거치게 하는 규율, 결정론. [서적] GPP command
  3. **Deterministic lockstep / Rollback** — patterns.md.
- **UE**: 물리 Substepping, Async Physics Tick(고정 스텝, 실험적, Substepping 과 배타) ‡ — 쓰기 전에 그 엔진 버전 문서 확인. **Unity**: FixedUpdate + Maximum Allowed Timestep ‡.

## l. 변형 스폰 (종류마다 클래스·스포너)

- **증상**: "몬스터 종류마다 서브클래스·스포너를 만든다", "고블린 궁수/마법사 데이터가 복붙", "수천 개 인스턴스가 같은 메시·스탯을 각자 들고 있다", "보스는 일반 몹에서 조금만 다르다".
- **신호**: 종류별 Spawner 클래스. enum + switch 로 종류별 값을 꺼낸다 (GPP flyweight 가 이것을 신호로 지목). 데이터 파일의 같은 필드 반복.
- **후보**
  1. **Type Object** — 종류를 데이터 인스턴스로. 얻음: 재컴파일 없이 종류 추가. 잃음: 타입 객체 수명 관리, 종류별 *행동*은 어렵다. [서적] GPP type-object
  2. **Prototype(복제·데이터 위임)** — 얻음: "일반 + 약간" 변형. 잃음: clone 구현, 깊은/얕은 복제. 데이터의 `"prototype"` 필드 위임이 실용형. [서적] GPP prototype
  3. **Flyweight** — 공유(내재) / 인스턴스별(외재) 데이터를 나눈다. 얻음: 메모리·전송량. 잃음: 간접 참조, 구조가 덜 자명. [서적] GPP flyweight
- **UE**: Blueprint 서브클래스·CDO, Data Asset/Primary Data Asset (Type Object·Flyweight 역할) ‡, 행마다 다른 동작 데이터는 `FInstancedStruct` (ue-idioms.md 14절). **Unity**: Prefab Variant ‡, ScriptableObject 공유 데이터 [공식] UnityDemo `9_Flyweight/Scripts/ShipData.cs`.
