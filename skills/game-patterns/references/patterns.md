# 게임 프로그래밍 패턴 — 얻는 것과 잃는 것

주 출처: Robert Nystrom, *Game Programming Patterns* (https://gameprogrammingpatterns.com/contents.html) [서적].
Unity 공식 e-book (Unity 6판 "design patterns and SOLID", 샘플 https://github.com/Unity-Technologies/game-programming-patterns-demo) [공식].

## 목차
- 구조: Component, Type Object, Subclass Sandbox, Bytecode
- 결합 분리: Observer, Event Queue, Command, Service Locator
- 상태: State (FSM, 계층, 푸시다운)
- 성능: Object Pool, Data Locality, Dirty Flag, Spatial Partition
- 흐름: Game Loop, Update Method, Double Buffer

## 구조

**Component** — 여러 도메인이 한 클래스에 뭉친 것을 나눈다.
얻음: 도메인별 독립 변경, 조합으로 새 개체. 잃음: 컴포넌트 간 통신 설계(직접 참조 / 메시지 / 공유 상태 중 선택)가 새 문제가 된다.

**Type Object** — "종류"를 클래스가 아니라 데이터 인스턴스로 만든다.
얻음: 새 종류 = 데이터 추가, 코드 변경 0. 잃음: 데이터로 표현 가능한 행동만 가능. 넘어서면 Subclass Sandbox 나 Bytecode 가 필요.

**Subclass Sandbox** — 기반 클래스가 보호된 연산 집합을 주고, 하위 클래스는 그것만으로 행동을 구현.
얻음: 하위 클래스 간 결합 제거, 기반 클래스에 결합 집중. 잃음: 기반 클래스가 비대해진다.

**Bytecode / 그래프 인터프리터** — 행동을 데이터(명령 시퀀스·노드 그래프)로.
얻음: 디자이너 자율, 핫 리로드. 잃음: 인터프리터 구현·디버깅 도구 비용. 엔진에 이미 있으면(BP, StateTree, GAS) 다시 만들지 않는다.

## 결합 분리

**Observer** — 대상이 관찰자 목록에 알린다.
얻음: 송신자가 수신자를 모름. 잃음: 흐름이 정적으로 안 보임, 수신자 수명 관리(댕글링) 필요, 동기 호출이라 연쇄 반응 순서 문제.

**Event Queue** — 이벤트를 큐에 넣고 나중에 처리.
얻음: 시점 분리, 프레임 분산. 잃음: 발생 시점의 상태가 처리 시점에 없을 수 있음, 피드백 루프 위험.

**Command** — 요청을 객체로.
얻음: 입력·AI·리플레이·되돌리기가 같은 경로. 잃음: 커맨드 클래스 증식.

**Service Locator** — 전역 접근 지점 + 구현 교체.
얻음: 싱글톤보다 교체·널 서비스가 쉬움. 잃음: 의존이 호출부에 안 보임, 등록 시점 버그.

## 상태

**State** — 상태를 객체로, 전이를 명시적으로.
얻음: bool 조합 폭발 제거, 상태별 코드 격리. 잃음: 상태 간 공유 데이터 위치 결정, 상태 수가 늘면 전이 표 관리.
계층 상태머신: 공통 처리를 상위 상태로. 푸시다운 오토마톤: "이전 상태로 복귀"가 필요할 때(메뉴, 피격 경직).

## 성능

**Object Pool** — 미리 할당한 객체 재사용. 얻음: 할당·GC·스폰 비용 제거. 잃음: 반납 누락, 재사용 시 상태 초기화 버그. 반납 주체를 하나로 고정.
**Data Locality** — 같이 쓰는 데이터를 연속 메모리로. 얻음: 캐시 효율. 잃음: 객체 지향 표현을 포기, 코드 가독성.
**Dirty Flag** — 파생 데이터를 필요할 때만 재계산. 잃음: 플래그 갱신 누락 버그.
**Spatial Partition** — 위치 기반 조회를 격자·트리로. 엔진 물리·내비 쿼리가 이미 하면 쓰지 않는다.

## 흐름

**Game Loop / Update Method / Double Buffer** — 엔진이 제공한다. 직접 구현하지 않는다.
의미가 있는 것은 **틱 순서 의존**: A 의 Tick 결과를 B 가 같은 프레임에 읽는다면 순서를 명시(UE Tick Group·prerequisite, Unity Script Execution Order)하거나 이벤트로 바꾼다.
