# 조회 결과 앞이 잡음으로 차면 모델이 도구를 버린다

## 상황
인덱스(clangd · gq)가 있고 세션 안내도 하는데, 모델이 한두 번 써 보고 grep 으로 돌아갈 때.

## 교훈
도구를 권하기 전에 그 도구의 첫 화면을 직접 본다. 경로 순 표본이 생성 코드로 차거나, 같은 이름 후보 중 엔진 것을 골라
"0개"를 내면 모델은 도구를 믿지 않는다. 잡음은 기본에서 빼고(뺀 수는 한 줄로 알리고 옵션으로 되살린다), 같은 이름이면
프로젝트 것을 먼저 고른다. 그리고 grep 하는 순간에 한 줄로 알린다(세션 시작 안내만으로는 안 됐다).

## 근거
- 2026-10-22 MNYS: `cindex.py refs FYSInputHistory` 의 표본 8개가 전부 `Intermediate/…/YSStruct.gen.cpp`(참조 22 중 11),
  `callers BeginPlay` 는 같은 이름 40개 중 엔진 `APawn::BeginPlay` → 호출자 0. 고친 뒤: 참조 11 전부 Source · 0.2초,
  `AYSMonster::BeginPlay` + 프로젝트 후보 14.
- 같은 날 모니터 경고: 로그 · 기획 문서 · git 출력 grep 까지 세서 "clangd 있는데 grep" 이 늘 떴다 — 코드 grep 만 세니
  10-20~22 세션 52개에서 grep 202 → 99, 경고 세션 7 → 5.

## 적용
`cindex.py` 의 `GEN_SQL` · `rank` · `others_line`, 모니터 mod 의 `grepTarget` · `nudge`. PR jokate/jokate-harness#29.
효과(대화형 세션에서 실제로 clangd 로 가는지)는 아직 못 쟀다 — 다음 MNYS 세션들의 `/harness-history` 로 본다.
