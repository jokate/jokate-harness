# Unity — 프로젝트와 엔진 파악

## 목차
1. 프로젝트 해부
2. 진입점 찾기
3. 데이터가 사는 곳
4. 엔진·패키지 소스
5. 직렬화·버전 함정

## 1. 프로젝트 해부

| 경로 | 의미 | 볼 때 |
|---|---|---|
| `ProjectSettings/ProjectVersion.txt` | 에디터 버전 | 가장 먼저 |
| `Packages/manifest.json` | 패키지 의존과 버전 (Addressables, Input System, Entities 등 사용 여부) | 기술 스택 |
| `Assets/**/*.asmdef` | 어셈블리 경계. 순환 참조 금지라 곧 강제된 레이어 구조. `gq.py deps` 가 파싱 | 경계 파악 |
| asmdef 없는 스크립트 | 전부 `Assembly-CSharp` 한 덩어리 → 경계가 없다는 뜻 | 구조 판단 |
| `*.meta` | GUID. 애셋 간 참조는 경로가 아니라 GUID | 참조 추적 |
| `ProjectSettings/TagManager.asset` | 태그·레이어 | 태그 |
| `Library/`, `Temp/`, `obj/`, `Logs/` | 생성물. 읽지 않는다 | — |

## 2. 진입점 찾기

- 부트스트랩: Build Settings 의 첫 씬(`ProjectSettings/EditorBuildSettings.asset`), `[RuntimeInitializeOnLoadMethod]`
- 전역 서비스: 싱글톤 `MonoBehaviour`, `DontDestroyOnLoad`, DI 컨테이너(VContainer/Zenject 등 — manifest 로 확인)
- 입력: Input System 의 `.inputactions` 애셋
- 씬 흐름: `SceneManager.LoadScene` 호출부, Addressables 사용 시 `Addressables.LoadSceneAsync`
- ECS 사용 시: `ISystem`/`SystemBase` 파생, Baker (`Baker<T>`)

`gq.py find` 로 위 이름들을 찾는다.

## 3. 데이터가 사는 곳

- `ScriptableObject` 파생 + `[CreateAssetMenu]` → 종류별 설정이 데이터로 빠져 있음. `gq.py map` 의 애셋 유형에 SO 클래스 이름이 나온다(guid 로 해석).
- 프리팹과 씬의 직렬화 필드 — 텍스트 직렬화면 YAML 로 읽을 수 있지만 크다. 필요한 필드만 `rg`.
- SO 이벤트 채널(Hipple 식)을 쓰면 정적 참조 그래프에 흐름이 안 나온다. 채널 애셋 이름으로 송수신자를 찾는다.

## 4. 엔진·패키지 소스

- 엔진 C# 레퍼런스 소스: Unity-Technologies/UnityCsReference (읽기 전용 공개. 버전 브랜치 확인)
- 패키지 소스: `Library/PackageCache/<패키지>@<버전>/` 에 풀려 있다. `rg` 로 직접 본다.
- 엔진 네이티브(C++) 는 공개되지 않는다. 동작은 문서·레퍼런스 소스·실험으로 확인.

## 5. 직렬화·버전 함정

- Asset Serialization 이 `Force Text` 가 아니면 `.asset`/프리팹을 읽을 수 없다 (`ProjectSettings/EditorSettings.asset` 의 `m_SerializationMode`, 값 의미는 확인 필요).
- 필드 이름을 바꾸면 직렬화 데이터가 끊긴다 → `[FormerlySerializedAs]`.
- asmdef `references` 는 이름 또는 `GUID:` 형식이고 한 목록에서 섞을 수 없다.
- Unity 6(6000.x) 이후 API 변경이 있다. 버전을 먼저 밝힌다.
