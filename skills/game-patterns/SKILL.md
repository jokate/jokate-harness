---
name: game-patterns
description: 게임 프로그래밍 패턴과 엔진 관용구(UE / Unity)를 문제 기준으로 비교하고 트레이드오프를 낸다. "어떤 패턴이 맞나", "State vs 분기", "컴포넌트로 뺄까", "데이터로 뺄까", "이벤트로 풀까 직접 호출할까", "Subsystem 써도 되나", "GAS 로 할까", "ScriptableObject 이벤트", "ECS 로 갈까", "싱글톤 괜찮나" 같은 질문에 쓴다. 현재 프로젝트에서 어떤 구조를 고를지 조사하는 절차는 game-architecture 가 맡고, 이 스킬은 그 선택지 C(새 구조)를 채우는 카탈로그다. 고르는 것은 사용자다.
---

# game-patterns — 문제에서 패턴으로

패턴은 이름이 아니라 **해결하는 문제와 치르는 비용**으로 고른다. 이 스킬은 결정 트리와
트레이드오프 한 줄까지만 낸다. 추천하지 않는다.

## 쓰는 법

1. 사용자의 문제를 아래 증상 표에서 찾는다. 없으면 "이 표에 없는 문제"라고 말하고 증상을 한 줄로 되묻는다.
2. 후보 패턴 2~3개를 [references/patterns.md](references/patterns.md) 에서 꺼내 "얻는 것 / 잃는 것" 한 줄씩.
3. 엔진 관용구로 번역한다 — 이미 엔진에 있는 것을 다시 만들지 않는다:
   [references/ue-idioms.md](references/ue-idioms.md) · [references/unity-idioms.md](references/unity-idioms.md)
4. 프로젝트에 이미 같은 역할을 하는 구조가 있으면 그것을 먼저 적는다 (`game-onboard` 의 `gq.py find`).

## 증상 → 후보

| 증상 | 후보 | 먼저 볼 엔진 관용구 |
|---|---|---|
| 새 "종류"(무기·적·스킬)마다 클래스나 enum+switch 가 늘어난다 | Type Object, 데이터 주도 | UE DataAsset/DataTable · Unity ScriptableObject |
| 한 클래스가 이동·전투·UI·세이브를 다 안다 | Component | UE ActorComponent · Unity MonoBehaviour 분리 |
| bool 플래그 조합으로 상태를 표현, 분기 폭발 | State, 계층 상태머신 | UE StateTree · Unity Animator/자체 FSM |
| A 가 일어나면 B, C, D 가 반응해야 하고 A 는 몰라야 한다 | Observer, Event Queue | UE 델리게이트·GameplayEvent/Message · Unity C# event·SO 채널 |
| 입력·AI·리플레이가 같은 행동을 요청 | Command | UE GAS Ability 활성화 · Unity Input System 액션 → 커맨드 |
| 어디서든 접근해야 하는 서비스, 교체도 필요 | Service Locator, DI | UE Subsystem · Unity DI 컨테이너 |
| 짧은 수명 객체 대량 생성·파괴 | Object Pool | UE 자체 풀 · Unity `ObjectPool<T>` |
| 기능을 켜고 끄는 단위로 떼고 싶다 | 플러그인/모듈 경계 | UE Game Features · Unity asmdef/패키지 |
| 수천 개 동일 엔티티, 성능이 병목 | Data Locality, ECS | UE Mass · Unity DOTS/Entities |
| 디자이너가 코드 없이 행동을 조합 | Bytecode/그래프, Subclass Sandbox | UE BP·StateTree·GAS · Unity 그래프 툴 |

## 공통 경고

- 패턴 도입의 비용은 **간접화**다. 흐름 추적이 어려워지는 만큼 디버깅 도구(로그, 시각화)가 같이 와야 한다.
- 싱글톤·Service Locator·Subsystem 은 의존을 숨긴다. 호출부에서 의존이 안 보이면 테스트와 교체가 어렵다.
- 이벤트는 송신자와 수신자를 분리하지만 **정적 그래프에서 사라진다**. `game-architecture` 의 sequence 그림으로 보완.
- 새 추상화는 같은 축의 요청이 2건 이상 있을 때. 1건이면 국소 해결 + "다음에 오면 X 로" 메모.
