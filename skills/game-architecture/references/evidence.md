# 이 절차의 근거

태그: [연구] 동료 심사 논문 · [서적] · [공식] 엔진·도구 공식 문서 · [벤더] 도구 회사 연구 (이해상충) · [프리프린트] 심사 전
[미확인] 은 원문을 열어 확인하지 못한 것.

## 왜 구조를 먼저 보나

- Parnas (1972): 모듈은 처리 단계가 아니라 "바뀔 가능성이 큰 설계 결정"을 하나씩 숨기도록 나눈다. [연구][미확인] https://dl.acm.org/doi/10.1145/361598.361623
- Ousterhout, *A Philosophy of Software Design*: 복잡도의 증상은 change amplification, cognitive load, unknown unknowns. 당장 돌아가게만 짜는 tactical programming 이 복잡도를 쌓는다. [서적]
- Khomh et al. (EMSE 2012): 안티패턴 클래스는 크기를 통제해도 더 자주 바뀌고 결함이 더 많다. [연구] https://link.springer.com/article/10.1007/s10664-011-9171-y
- Zimmermann & Nagappan (ICSE 2008): 의존 그래프 지표가 복잡도 지표보다 결함 예측 recall 이 10%p 높다. [연구] https://www.microsoft.com/en-us/research/publication/predicting-defects-using-network-analysis-on-dependency-graphs/
- MacCormack, Rusnak, Baldwin (2012): 느슨한 조직이 더 모듈화된 제품을 만든다 (Conway 의 법칙 검증). [연구] https://www.hbs.edu/faculty/Pages/item.aspx?num=32217

## 왜 변경 이력인가

- Nagappan & Ball (ICSE 2005): 절대 churn 보다 크기로 정규화한 상대 churn 이 결함 밀도를 잘 예측한다. [연구] https://dblp.org/rec/conf/icse/NagappanB05.html
- Code Maat: logical coupling 정의와 기본 필터. [공식] https://github.com/adamtornhill/code-maat
- Tornhill & Borg, Code Red (2022): 저품질 코드에서 결함 15배, 해결 시간 +124%. [벤더] https://arxiv.org/abs/2203.04374

## 왜 에이전트에게 이 절차가 필요한가

- GitClear 2025: 2024년 처음으로 복붙 라인이 이동(리팩터) 라인을 넘었고, 5줄 이상 중복 블록 빈도 8배. 상관이지 인과 아님. [벤더] https://gitclear-public.s3.us-west-2.amazonaws.com/GitClear-AI-Copilot-Code-Quality-2025.pdf
- SmellBench (arXiv 2605.07001): 아키텍처 스멜 수리에서 에이전트 최고 해결률 47.7%, 가장 공격적인 에이전트는 스멜 140개를 새로 만들었다 — 국소 수정은 되지만 모듈 횡단 추론이 약하다. [프리프린트] https://arxiv.org/abs/2605.07001
- METR (2025): 숙련 개발자가 AI 를 쓰면 19% 느려졌지만 스스로는 20% 빨라졌다고 느꼈다 → 체감 대신 계측된 신호. [연구] https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/
- Anthropic Claude Code best practices: 탐색 → 계획 → 구현, 기존 패턴 참조를 명시, 검증 수단 제공, 새 컨텍스트 리뷰. 리뷰 지적을 전부 따르면 과설계로 간다는 경고. [공식] https://code.claude.com/docs/en/best-practices

## 반대 방향 — 과설계

- Nystrom, *Game Programming Patterns* 1장: 좋은 구조는 변경을 쉽게 하지만 디커플링 추상화는 투기적 일반화·성능 비용을 낳는다. [서적] https://gameprogrammingpatterns.com/architecture-performance-and-games.html
- "같은 축 요청 2건 이상일 때만 새 추상화" 기준은 위 두 방향을 절충한 이 스킬의 규칙이다. 연구에서 나온 수치가 아니다.
