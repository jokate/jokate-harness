# 변경 이력 신호 — 계산법과 해석

## 목차
1. 무엇을 계산하나
2. 해석 규칙
3. 한계
4. VCS 별 차이

## 1. 무엇을 계산하나

| 신호 | 정의 | 스크립트 | 출처 |
|---|---|---|---|
| hotspot | 기간 내 커밋 수 순위. git 이면 churn(추가+삭제 줄)과 상대 churn(churn ÷ LOC) | `evidence.py hotspots` | Tornhill / CodeScene. 상대 churn 은 Nagappan & Ball 2005 |
| co-change (logical coupling) | degree = 함께 바뀐 커밋 수 ÷ 두 단위 커밋 수의 평균 | `evidence.py coupling` | Code Maat `logical_coupling` |
| focus | 특정 파일을 건드린 커밋에서 함께 바뀐 파일과 비율 | `evidence.py focus` | co-change 의 한쪽 고정판 |
| 모듈 의존 | Build.cs Public/Private 의존, asmdef references | `gq.py deps` | 정적 구조 |

기본 필터 (Code Maat 기본값): min-revs 5, min-shared 5, degree ≥ 30%, 커밋당 파일 30개 초과 커밋 제외
(일괄 포맷 변경·대량 이동 커밋이 결합을 부풀리는 것을 막는다).

C++ 는 `.h`/`.cpp` 와 UE `Public/Private/Classes` 분리를 한 단위로 접는다. 접지 않으면 헤더-소스 짝이 상위를 다 차지한다.

## 2. 해석 규칙

- **숨은 결합**: co-change degree 가 높은데 정적 의존(include / using / 모듈 의존)이 없다 → 한쪽 변경이 다른 쪽을 암묵적으로 요구한다. 이벤트·태그·문자열 키·데이터 스키마 공유가 흔한 원인.
- **땜질 누적**: hotspot 상위 + 상대 churn 높음 → 요청마다 같은 파일에 분기를 얹어 온 흔적. 여기에 또 분기를 더하는 선택지는 표시한다.
- **레이어 위반**: 하위 모듈이 상위 모듈과 자주 함께 바뀐다 → 경계가 잘못 잘렸거나 상위 개념이 하위로 샜다.
- **정상 결합**: 같은 기능 폴더 안의 짝 결합은 응집(cohesion)의 신호일 수 있다. 결합 자체가 나쁜 것이 아니라 **경계를 넘는** 결합이 비용이다.
- hotspot 의 절대 임계값은 없다. 상위 N 순위로만 쓴다 (CodeScene 도 임계값을 공개하지 않는다).

## 3. 한계

- 커밋 습관에 좌우된다. 한 커밋에 여러 작업을 몰아넣는 저장소는 결합이 부풀고, 잘게 쪼개는 저장소는 줄어든다. 결과를 낼 때 커밋 수와 기간을 같이 적는다.
- 1인 프로젝트는 작성자 수 신호가 의미 없다.
- 바이너리 애셋(.uasset, 프리팹)은 커밋 단위 결합만 잡힌다 — 내부 참조는 에디터(AssetRegistry / GUID)로 봐야 한다.
- 결함 예측과의 상관은 연구 결과지만 인과가 아니다. "이 파일이 나쁘다"가 아니라 "여기를 더 조심해서 봐야 한다"로 쓴다.

## 4. VCS 별 차이

| | git | svn |
|---|---|---|
| 변경 파일 | `git log --numstat --no-renames` | `svn log -v --xml -r {날짜}:HEAD` |
| churn(줄 수) | 있음 | 없음 (커밋 수만) |
| 경로 | 저장소 루트 기준 | 저장소 URL 기준 → 작업 사본 relative-url 을 벗겨 낸다 |
| 검증 | MNYS(git) 에서 검증함 | **검증 안 됨** (작성 환경에 svn 없음). 첫 사용 때 출력 경로가 작업 사본 기준으로 나오는지 확인 |

중첩 저장소(예: `Source/` 가 별도 git)면 `--path` 로 그 안을 가리킨다. 스크립트는 `--path` 에서 위로 올라가며 가장 가까운 `.git`/`.svn` 을 쓴다.
