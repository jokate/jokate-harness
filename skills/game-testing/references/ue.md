# Unreal Engine 테스트

매크로·클래스 이름은 UE 5.7 헤더(`Misc/AutomationTest.h`, `FunctionalTesting`)에서 확인했다. 다른 버전은 확인 필요.

## 목차
1. 종류 선택
2. 단위 테스트 (Simple / Spec)
3. 기능 테스트 (Functional Test)
4. 헤드리스 실행
5. 함정

## 1. 종류 선택

| 대상 | 형식 |
|---|---|
| 순수 로직 | `IMPLEMENT_SIMPLE_AUTOMATION_TEST` 또는 Spec (`BEGIN_DEFINE_SPEC`) |
| 여러 입력 조합 | `IMPLEMENT_COMPLEX_AUTOMATION_TEST` (GetTests 로 케이스 나열) |
| 월드·액터 필요 | `AFunctionalTest` 파생 액터를 테스트 맵에 배치, 또는 latent command (`ADD_LATENT_AUTOMATION_COMMAND`) |
| 빌드·배포 파이프라인 | Gauntlet (범위 밖, 필요 시 별도 조사) |

테스트 코드는 게임 모듈에 `#if WITH_DEV_AUTOMATION_TESTS` 로 감싸거나 별도 Tests 모듈로 둔다.

## 2. 단위 테스트

```cpp
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDamageFormulaTest, "Game.Damage.Formula",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FDamageFormulaTest::RunTest(const FString& Parameters)
{
    TestEqual(TEXT("기본 피해"), ComputeDamage(10.f, 0.f), 10.f);
    TestTrue(TEXT("방어 100% 면 0"), FMath::IsNearlyZero(ComputeDamage(10.f, 1.f)));
    return true;
}
#endif
```

플래그: 컨텍스트 플래그(EditorContext 등) 하나 이상 + 필터 플래그 하나. 5.7 헤더는 컨텍스트가 없으면 `static_assert` 로 막는다.
필터 플래그 이름(`EngineFilter`, `ProductFilter` 등)과 조합 규칙은 버전별로 `ue_q.py rg "EAutomationTestFlags" --module Core` 로 확인.

Spec 형식(BDD, `Describe`/`It`)은 `BEGIN_DEFINE_SPEC(클래스, "경로", 플래그) ... END_DEFINE_SPEC(클래스)` + `Define()` 구현.

## 3. 기능 테스트

1. `AFunctionalTest` 를 상속(또는 BP 파생)해 `StartTest` 에서 시나리오를 돌리고 `FinishTest(EFunctionalTestResult::Succeeded, ...)` 호출.
2. 테스트 전용 맵에 배치. 맵 이름·경로 규칙은 프로젝트 설정을 따른다.
3. Session Frontend → Automation 탭 또는 아래 커맨드라인으로 실행.

시그니처는 `ue_q.py api AFunctionalTest` 로 확인하고 쓴다.

## 4. 헤드리스 실행

```
"<엔진>/Binaries/Win64/UnrealEditor-Cmd.exe" "<프로젝트>.uproject" ^
  -ExecCmds="Automation RunTests Game.Damage;Quit" ^
  -unattended -nullrhi -nopause -nosplash -log ^
  -testexit="Automation Test Queue Empty"
```

- `-testexit=` 은 5.7 `LaunchEngineLoop.cpp` 에서 확인했다 (로그에 해당 문구가 나오면 종료).
- 결과 리포트 경로 옵션(`-ReportExportPath=` 등)은 **확인 필요**.
- 종료 코드와 로그의 `Test Completed. Result={Success|Fail}` 줄을 결과로 붙인다 (로그 문구는 버전별 확인).
- 월드가 필요한 기능 테스트는 `-nullrhi` 에서 렌더링 의존 부분이 실패할 수 있다.

## 5. 함정

- 에디터가 떠 있으면 같은 프로젝트로 Cmd 실행 시 에셋·DDC 잠금 충돌 가능 → 사용자 확인 후.
- 테스트 이름 경로(`Game.Damage.Formula`)가 필터 단위다. 기능별 접두사를 통일한다.
- 핫 리로드/Live Coding 후에는 테스트 목록이 갱신 안 될 수 있다. 에디터 재시작 후 재확인.
