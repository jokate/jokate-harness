# Unity 관용구 — 패턴을 엔진 기능으로

Unity 6(6000.x) 문서 기준. 이전 버전은 확인 필요.

## 목차
- 데이터와 이벤트: ScriptableObject
- 조합: MonoBehaviour 컴포넌트
- 경계: asmdef, 패키지
- 서비스: 싱글톤 vs DI
- 성능: ObjectPool, DOTS
- 상태: Animator, 자체 FSM

## 데이터와 이벤트 — ScriptableObject

- 데이터: Type Object 그대로. `[CreateAssetMenu]` 로 디자이너가 새 종류를 만든다.
- 이벤트 채널·변수 애셋 (Ryan Hipple, Unite 2017): 씬 객체 간 하드 참조 제거, 디자이너 조합.
  공식 가이드: 원본 SO 값을 런타임에 바꾸지 말고 런타임 값으로 복사해 쓴다.
  얻음: 씬 간 결합 제거. 잃음: 참조 추적 도구 부재, 보이지 않는 이벤트 그물, 대형 프로젝트 적합성 논란.
  https://unity.com/how-to/architect-game-code-scriptable-objects · https://github.com/roboryantron/Unite2017

## 조합 — MonoBehaviour

Component 패턴 그대로. `GetComponent` 남발은 숨은 결합이다 — `[SerializeField]` 참조나 `[RequireComponent]` 로 의존을 드러낸다.

## 경계 — asmdef, 패키지

- asmdef: 컴파일 시간 단축 + 단방향 의존 강제(순환 금지, Assembly-CSharp 참조 금지). 곧 레이어 구조다.
  잃음: 경계를 잘못 자르면 순환 해소 리팩터나 병합이 강제된다.
  https://docs.unity3d.com/6000.2/Documentation/Manual/assembly-definitions-intro.html
- 로컬 패키지(`Packages/`): 프로젝트 간 재사용 단위. 기능을 떼는 최종 형태.

## 서비스 — 싱글톤 vs DI

- 싱글톤 `MonoBehaviour` + `DontDestroyOnLoad`: 가장 흔하고 가장 추적이 어렵다. 초기화 순서 문제.
- DI 컨테이너(VContainer, Zenject 등): 의존을 생성자·주입으로 드러냄. 잃음: 학습·설정 비용, 런타임 리플렉션 비용(구현별).
- 프로젝트가 이미 쓰는 쪽을 따른다. 섞으면 두 규칙을 다 알아야 한다.

## 성능

- `UnityEngine.Pool.ObjectPool<T>`: Object Pool. 반납 시 상태 초기화를 `actionOnRelease` 에 모은다.
- DOTS / Entities: Data Locality + ECS. baking 은 되돌릴 수 없고, 하이브리드 컴포넌트는 성능 이점 없음.
  잃음: 학습 곡선, GameObject 세계와의 이중 구조. 병목이 증명된 곳에만.
  https://docs.unity3d.com/Packages/com.unity.entities@1.4/manual/ecs-workflow-example-authoring-baking.html

## 상태

- Animator 상태머신은 애니메이션용이다. 게임플레이 상태를 Animator 파라미터로 표현하면 로직이 애셋에 숨는다.
- 게임플레이 FSM 은 코드(State 패턴)나 전용 툴로. 전이 표를 한 곳에.
