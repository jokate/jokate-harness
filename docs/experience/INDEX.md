# 하네스 경험 목차

하네스를 고치기 전에 이 목차를 보고, 맞는 항목만 연다. 항목은 **대조(전 · 후, 또는 두 팔)로 뒷받침된 교훈만** 남긴다 —
근거가 약하면 쓰지 않는다. Harness²(arXiv 2610.14224)의 경험 라이브러리(상황 · 교훈 · 근거, 목차로 필요할 때만 연다)를
하네스 개발에 옮긴 것이다. 새 수정은 `tools/harness_probe.py` 로 대조하고, 그 `EXPERIENCE.draft.md` 를 확인해 여기에 옮긴다.

| 항목 | 언제 보나 | 한 줄 교훈 |
|---|---|---|
| [routing-commands](routing-commands.md) | 스킬 · 인덱스가 안 불린다 | 스킬 이름만 알려 주면 모델은 grep 으로 간다 — 쓸 명령을 줄 그대로 준다 |
| [tool-output-noise](tool-output-noise.md) | 인덱스가 있는데 grep 으로 돌아간다 | 조회 결과 앞이 잡음(생성 코드 · 엔진 후보)으로 차면 모델이 도구를 버린다 — 잡음을 기본에서 뺀다 |
| [prune-unused](prune-unused.md) | 하네스가 무거워졌다 · 기능을 더하려 한다 | 15일 0회 동작한 훅 · 스킬은 뺀다 — 항상 들어가는 글은 가장 비싸다 |
| [routing-single-source](routing-single-source.md) | 라우팅 줄을 고친다 · 규칙 파일이 여럿이다 | 라우팅은 세션 시작 안내 한 곳에 — 인덱스 명령 줄은 줄이지 않는다(줄이면 cindex 22 → 11) |
