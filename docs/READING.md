# 사람이 읽는 글 — 답과 문서의 규칙

> 일부 규칙을 STE-KO(MIT, Copyright (c) 2026 Beamonic)와 hanlint(MIT, eddmpython)에서 빌려 고쳤다.
> 생각만 빌린 곳: Google developer documentation style guide, Diátaxis, Pinker 『The Sense of Style』. 원문 추적: 아래 '출처'.

사용자는 설계 판단만 읽는다. 그래서 답과 문서의 맨 앞에는 정한 것과 정할 것만 둔다.
규칙 본문은 `rules/common.md`(모든 프로젝트의 전역 CLAUDE.md 에 들어간다)와 game-architecture '읽기 규칙'이다.
에이전트가 읽는 스킬 문서를 쓰는 법은 `docs/WRITING.md` 다.

## 규칙

| 규칙 | 왜 | 빌린 곳 | 기계 검사 (`render.py` 읽기 점검) |
|---|---|---|---|
| 맨 앞엔 정한 것과 정할 것만 | 사용자는 설계 판단만 읽는다 | 결론 먼저(BLUF), Google 문장 구조 | 첫 화면 30줄 |
| 본문은 단정, 확신은 표의 칸 | 흐린 말은 판단을 미룬다 | hanlint AI 글 지침 5 | 없음 |
| 한 문장에 사실 하나 | 몰아 쓰면 독자가 다시 풀어 읽는다 | STE-KO 4.2, 8.2 | 가운뎃점 3개나 괄호 2개가 있는 줄 |
| 지금 상태만 쓴다 | 고친 기록이 섞이면 지금 맞는 것을 독자가 다시 맞춘다 | Diátaxis 참조 문서 | 날짜 꼬리표 |
| 작업 · 커밋 번호는 근거 표에만 | 번호는 쓰는 쪽만 안다 | 지식의 저주(Pinker) | 첫 화면 번호 |
| 지어낸 이름은 처음에 푼다 | 위와 같다 | STE-KO 1.5, 1.7, Google 약어 | 없음 |
| 근거는 육하원칙 표 | 근거를 같은 칸으로 견준다 | 사용자 결정 | 구조 문서의 표 머리줄 |
| 첫 줄에 앞 말을 되받지 않는다 | 첫 줄은 판단에 쓴다 | STE-KO 10.4 | 없음 |

- 검사는 첫 화면만 막는다. 근거 쪽 몰아 쓴 줄은 수만 알린다. 날짜 꼬리표는 어디서든 막는다.
- 기준값은 사용자가 읽기 어렵다고 한 문서와 지적이 없던 문서를 재서 정했다. 측정 표는 `docs/VERIFICATION.md`.
- 대화 답은 기계 검사가 없다. 전역 규칙만 걸린다.

## 쓰지 않은 것

| 후보 | 안 쓴 이유 |
|---|---|
| 가독성 공식(Flesch 류) | 사람이 실제로 읽는 어려움을 잘 못 맞힌다 (Gruteke Klein 외 2025) |
| Claude 가 Claude 글을 채점 | 자기 글을 후하게 본다 (Panickssery 외 2024) |
| 영어 AI 티 지우기 도구 (humanizer, slop-guard 등) | 영어 전용이다. 위키백과 'Signs of AI writing' 도 신호만 지우면 탐지만 어려워진다고 경고한다 |
| 문장 길이 25어절 상한 (STE-KO 4.1) | 통제 언어용 수치다. 몰아 쓴 줄 검사가 새면 그때 더한다 |
| hanlint 설치 | 시험 전이다. 설치는 사용자 허락이 필요하다 |

## 출처

| 출처 | 쓴 것 | 이용 |
|---|---|---|
| [STE-KO](https://github.com/beamonic/ste-ko) | 4.2 한 문장 한 생각 · 8.2 괄호 안 괄호 · 1.5 약어 · 1.7 용어 정의 · 10.4 앞 턴 되풀이 | MIT |
| [hanlint](https://github.com/eddmpython/hanlint) | AI 글 지침 5 (흐린 말) | MIT |
| [Google developer documentation style guide](https://developers.google.com/style/abbreviations) | 약어는 처음 나올 때 푼다 · 조건과 목표를 앞에 | 생각만. 라이선스 문구 확인 못 함 |
| [Diátaxis](https://diataxis.fr/reference/) | 참조 문서는 지금 상태를 중립으로 쓴다 | 생각만. 라이선스 확인 못 함 |
| Pinker 『The Sense of Style』 | 지식의 저주 | 생각만 |
| [Singhal 외 2023](https://arxiv.org/abs/2310.03716) · [Zhang 외 2024](https://arxiv.org/abs/2409.11704) | 길고 목록 많은 답은 훈련 보상의 버릇이다 | 논문 |
