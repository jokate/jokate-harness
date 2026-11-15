---
paths:
  - "**/*.cpp"
  - "**/*.h"
  - "**/*.hpp"
  - "**/*.inl"
  - "**/*.cc"
  - "**/*.cs"
---
<!-- game-harness 가 관리한다. 고치려면 저장소의 rules/code.md 를 고치고 setup.bat -->
## 코드 (C++ · C#)
- 다른 사람과 같이 쓰는 저장소에서는 그 프로젝트의 컨벤션과 고치는 파일의 기존 모양이 먼저다. 아래 꼴은 프로젝트가 정하지 않은 곳에만 쓴다.
- 같이 쓰는 저장소인지 모르면 최근 이력에 다른 사람의 커밋이 있는지로 가른다.
- 혼자 하는 프로젝트에서는 새로 쓰거나 고치는 함수를 아래 꼴로 쓴다. 프로젝트 지침의 "제어문 다음 줄 한 줄짜리 허용"보다 이것이 우선이다.
- 함수 첫머리에서 포인터와 데이터 유효성을 검사하고 바로 반환한다. 필요한 입력이 다 있는지처럼 성격이 같은 검사는 한 `if` 에 묶어도 된다.
- 모든 `if` 에 중괄호를 붙인다. 한 줄짜리도 붙인다. 성격이 다른 검사는 블록을 나누고, 블록 사이에 빈 줄을 둔다.
- "조건이 맞으면 안에서 채운다" 대신 "아니면 바로 반환하고, 마지막에 본 작업"으로 쓴다. 중첩을 만들지 않는다.
- 삼항식은 마지막 결과 한 줄에만 쓴다. 갈래가 여럿이면 `if` 블록으로 푼다.
- UE 의 부정은 `IsValid(x) == false` 꼴로 쓴다.
- 스타일을 정리하다 조건의 뜻이 바뀌면 안 된다. 예: 하루 횟수 0 이 "제한 없음"인 `Max > 0 &&`. 뜻이 바뀌는 곳은 고치지 말고 알린다.
- 기존 파일을 Write 로 통째 다시 쓰면 줄 끝이 LF 가 된다. 원본이 CRLF 면 맞춰서, diff 에 바꾼 줄만 남긴다.

```cpp
EState UMyActivity::GetState(const FContext& InContext) const
{
	const UMyDB* _DB = InContext.DB.Get();

	if (IsValid(_DB) == false || InContext.Info == nullptr)
	{
		return EState::Disabled;
	}

	const int32 _Max = InContext.Info->DailyLimit;
	if (_Max > 0 && _DB->GetCount(InContext.ID) >= _Max)
	{
		return EState::Disabled;
	}

	return GetLimit(InContext).IsBlocked() ? EState::Disabled : EState::Enabled;
}
```
- 이유: 사용자가 정했다. 가독성을 위해서다. 조건이 늘어도 블록 하나만 더하면 되고, 어느 검사에서 막혔는지 한눈에 보인다.
