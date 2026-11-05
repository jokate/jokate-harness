# 사람이 읽는 글 — 답과 문서의 규칙

> 일부 규칙을 STE-KO(MIT, Copyright (c) 2026 Beamonic)와 hanlint(MIT, eddmpython)에서 빌려 고쳤다.
> 생각만 빌린 곳: Google developer documentation style guide, Diátaxis, Pinker 『The Sense of Style』. 원문 추적: 아래 '출처'.

사용자는 설계 판단만 읽는다. 그래서 답과 문서의 맨 앞에는 정한 것과 정할 것만 둔다.
규칙 본문은 `rules/common.md`(모든 프로젝트의 전역 CLAUDE.md 에 들어간다)와 game-architecture '읽기 규칙'이다.
에이전트가 읽는 스킬 문서를 쓰는 법은 `docs/WRITING.md` 다.

## 문서 철학

사용자 인터뷰로 정했다. 작업 문서와 검수 문서를 쓰기 전에 읽는다.

| 항목 | 정한 것 |
|---|---|
| 독자 | 사용자 본인이다. 작업할 때 참고하고 검수할 때 본다. AI 에게 일을 맡길 때도 같은 문서를 넘긴다 |
| 한 벌 | 사람과 AI 가 함께 읽기 좋은 문서 하나만 쓴다. AI 용을 따로 만들지 않는다 |
| 첫 화면 | 설계 판단만 둔다. 폰에서 한눈에 보여야 한다 (사용자 선호, 아래 '연구 결과') |
| 결정 단위 | 결정마다 그 밑에 왜와 근거를 매단다. 어느 결정에도 붙지 않는 사실은 뺀다 |
| 왜 | 자세히 쓴다. 사내 프로젝트에서 왜 도입했는지를 사용자가 검수한다. 칸을 정해 한 줄에 사실 하나씩 쓴다 |
| 근거 | 육하원칙 표로 쓴다 |
| 코드 구조 문서 | 자세히 써도 된다. 한꺼번에 쏟지 않고 결정 단위 모양을 따른다 |
| 말투 | 문서는 "~다", 대화와 보고는 "~습니다" |

### 결정 블록

```
### 결정: <정한 것 한 줄>
- 문제: <이 결정이 없으면 무엇이 어떻게 깨지나>
- 버린 안: <안> — <버린 이유>
- 대가: <이 결정으로 잃는 것>
- 뒤집는 조건: <무엇이 바뀌면 다시 본다>

| 누가 | 언제 | 어디서 | 무엇을 | 어떻게 | 왜 | 확신 |
|---|---|---|---|---|---|---|
```

- 네 칸은 설계 결정 기록(ADR: Nygard 의 양식, MADR)에서 빌렸다. 배경, 버린 안, 결과를 적는 업계 양식이다.
- 작은 결정에도 네 칸을 쓴다. 칸에 쓸 것이 없으면 "없음".
- 버린 안이 여럿이면 줄을 늘린다. 한 줄에 몰아 쓰지 않는다.
- 구조 조사 문서(game-architecture)에서는 '추천' 밑에 이 네 칸을 쓴다. 고른 뒤에는 고른 안이 결정이 된다.

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
| 첫 두 낱말에 핵심을 둔다 (소제목, 목록 항목, 표 첫 칸) | 훑는 독자는 줄의 첫 두 낱말을 셋째 낱말보다 훨씬 자주 읽는다 | NN/g F 패턴 시선 추적 | 없음 |
| 꾸밈말과 자랑조를 빼고 사실만 쓴다 | 객관 문체만으로 사용성이 27% 올랐다 | Nielsen · Morkes 1997 | 없음 |
| 소제목은 결론 문장으로, 펼침은 두 단까지 | 소제목만 이어 읽어도 결론이 보이게 한다 | NN/g 층 케이크 패턴, 점진 공개 (질적 근거라 약하다) | 없음 |

- 검사는 첫 화면만 막는다. 근거 쪽 몰아 쓴 줄은 수만 알린다. 날짜 꼬리표는 어디서든 막는다.
- 기준값은 사용자가 읽기 어렵다고 한 문서와 지적이 없던 문서를 재서 정했다. 측정 표는 `docs/VERIFICATION.md`.
- 대화 답은 기계 검사가 없다. 전역 규칙만 걸린다.
- 읽기 점검은 모양만 본다. 빠진 정보나 틀린 정보는 내용 검수가 따로 본다. 문서 문제는 내용과 모양 두 축으로 갈린다 (Aghajani 외 2019).

## 연구 결과

| 연구 | 결과 | 규칙에 준 뜻 |
|---|---|---|
| Nielsen 1997 | 사용자 79% 가 새 쪽을 훑는다. 낱말 하나씩 읽는 사람은 16% 다 | 독자는 훑는다고 보고 쓴다 |
| Nielsen · Morkes 1997 | 간결 +58%, 훑기 쉬움 +47%, 객관 +27%, 셋을 합치면 사용성 +124% | 첫 화면은 짧게, 훑기 쉽게, 꾸밈말 없이 |
| NN/g F 패턴 (232명 시선 추적) | 줄 왼쪽을 훑는 독자는 첫 두 낱말을 훨씬 자주 읽는다 | 첫 두 낱말에 핵심 |
| NN/g 층 케이크 패턴 | 소제목에만 시선이 머물며 훑는다. 소제목이 설명적일 때만 통한다 | 소제목은 결론 문장 |
| NN/g 모바일 이해도 (276명) | 폰에서 이해도가 낮지 않았다. 어려운 글은 폰에서 낱말당 약 30ms 더 걸렸다 | 폰 규칙은 사용자 선호다. 이해도 근거로 대지 않는다 |
| Brick 외 2020 (2,305명) | 작은 표가 같은 내용의 글보다 이해도가 높았다 (d=0.39) | 근거는 표. 단 작고 단순하게 |
| Tang 외 2006 (실무자 81명) | 설계 근거 기록은 중요하다고 보지만 기록하는 데 장벽이 있다 | 결정 블록을 양식으로 정해 장벽을 낮춘다 |
| Singhal 외 2023 · Zhang 외 2024 | 길고 목록 많은 답은 훈련 보상이 만든 버릇이다 | 길이와 모양을 규칙으로 막는다 |
| Gruteke Klein 외 2025 · Panickssery 외 2024 | 가독성 공식은 사람 읽기를 못 맞히고, 모델은 자기 글을 후하게 본다 | 판정은 사용자 피드백으로 한다 |

- 한국어 화면을 훑는 방식에 대한 연구는 못 찾았다. 위 결과를 한국어에도 쓴다.

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
| [ADR](https://adr.github.io/) · [MADR](https://adr.github.io/madr/) | 결정 블록의 네 칸 (배경, 버린 안, 결과) | 생각만 |
| [Singhal 외 2023](https://arxiv.org/abs/2310.03716) · [Zhang 외 2024](https://arxiv.org/abs/2409.11704) | 길고 목록 많은 답은 훈련 보상의 버릇이다 | 논문 |
| [Nielsen 1997](https://www.nngroup.com/articles/how-users-read-on-the-web/) · [Nielsen · Morkes 1997](https://www.nngroup.com/articles/concise-scannable-and-objective-how-to-write-for-the-web/) | 훑는 독자 비율, 간결 · 훑기 · 객관 문체 효과 | 연구 보고 |
| [NN/g F 패턴](https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content-discovered/) · [층 케이크](https://www.nngroup.com/articles/layer-cake-pattern-scanning/) · [점진 공개](https://www.nngroup.com/articles/progressive-disclosure/) · [모바일](https://www.nngroup.com/articles/mobile-content/) | 첫 두 낱말, 결론 소제목, 펼침 두 단, 폰 이해도 | 연구 보고 |
| [Brick 외 2020](https://doi.org/10.1098/rsos.190876) | 작은 표 대 글 이해도 | 논문 |
| [Tang 외 2006](https://doi.org/10.1016/j.jss.2006.04.029) · [Aghajani 외 2019](https://2019.icse-conferences.org/details/icse-2019-Technical-Papers/49/Software-Documentation-Issues-Unveiled) | 설계 근거 기록의 장벽, 문서 문제의 두 축 | 논문 (본문 수치는 못 읽음) |
