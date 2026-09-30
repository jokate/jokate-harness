# Unity 테스트

Unity Test Framework(UTF, `com.unity.test-framework`) 기준. 버전별 차이는 패키지 문서로 확인.

## 목차
1. 종류 선택
2. EditMode / PlayMode
3. 어셈블리 구성
4. 헤드리스 실행
5. 함정

## 1. 종류 선택

| 대상 | 형식 |
|---|---|
| 순수 로직, 데이터 검증, 에디터 도구 | EditMode 테스트 (`[Test]`) |
| 프레임 진행·물리·코루틴·씬 필요 | PlayMode 테스트 (`[UnityTest]` + `IEnumerator`) |
| SO 데이터 무결성 (중복 ID, 누락 참조) | EditMode 에서 `AssetDatabase.FindAssets` 로 전수 검사 |

## 2. 예시

```csharp
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using System.Collections;

public class DamageTests
{
    [Test]
    public void Formula_DefenseFull_IsZero()
    {
        Assert.That(Damage.Compute(10f, 1f), Is.EqualTo(0f).Within(1e-5f));
    }

    [UnityTest]
    public IEnumerator Hit_ReducesHp()
    {
        var go = new GameObject("Target");
        var hp = go.AddComponent<Health>();
        hp.Apply(5f);
        yield return null;
        Assert.That(hp.Current, Is.EqualTo(hp.Max - 5f));
        Object.Destroy(go);
    }
}
```

## 3. 어셈블리 구성

- 테스트는 별도 asmdef 에. 테스트 asmdef 는 대상 asmdef 를 references 에 넣고, `UNITY_INCLUDE_TESTS` 제약·NUnit 참조를 둔다 (Test Runner 창의 "Create Test Assembly Folder" 가 만들어 준다).
- 게임 코드가 `Assembly-CSharp` 에만 있으면 테스트 asmdef 에서 참조할 수 없다 → 테스트 대상 코드를 asmdef 로 빼는 것이 선행 조건. 이것 자체가 구조 결정이니 `game-architecture` 로.

## 4. 헤드리스 실행

```
"<Unity 설치>/Editor/Unity.exe" -batchmode -projectPath "<프로젝트>" ^
  -runTests -testPlatform EditMode ^
  -testResults "<출력>/results.xml" -logFile "<출력>/unity.log"
```

- PlayMode 는 `-testPlatform PlayMode`. 필터는 `-testFilter "<정규식|이름>"`.
- `-runTests` 는 끝나면 스스로 종료한다 — `-quit` 을 같이 주면 테스트 전에 종료될 수 있다(커뮤니티 보고, 버전별 확인 필요).
- 결과는 NUnit XML. 종료 코드와 실패 테스트 이름을 결과로 붙인다.

## 5. 함정

- 같은 프로젝트를 에디터가 열고 있으면 batchmode 가 실패한다 → 사용자 확인 후.
- PlayMode 테스트에서 만든 객체는 테스트 끝에 파괴한다. 씬 로드 테스트는 `[UnitySetUp]`/`[UnityTearDown]` 로 정리.
- 도메인 리로드 비활성(Enter Play Mode Options) 프로젝트는 static 상태가 테스트 간에 남는다.
