# 코드 인덱싱 연구 — 설계 근거와 검증 기준

에이전트용 저장소 수준 코드 검색·위치 찾기 연구에서 이 하네스의 인덱스(`ue_q.py`, `gq.py`, `cindex.py`) 설계와
검증 기준을 끌어온 기록이다. 2026-10-06 수집.

**출처 확인 방식**: 수집 환경에서 arxiv.org·aclanthology.org·openreview.net 등이 막혀 논문 PDF·초록 페이지는 열지 못했다.
각 연구의 **공식 GitHub 저장소**(README, BibTeX, 소스, 커밋된 결과 파일)와 열리는 공식 페이지로 확인했다.
저장소에 없고 논문에만 있는 수치는 쓰지 않았다. 학회 표기 중 일부(RepoGraph, CodexGraph, SweRank)는 제3자 목록 기준이다.

## 1. 연구 요약 (확인된 것만)

| 연구 | 인덱스 | 검색 방식 | 확인된 결과 | 출처 |
|---|---|---|---|---|
| LocAgent (ACL 2025) | 디렉터리·파일·클래스·함수 노드, contains·imports·invokes·inherits 간선 | 이름 → BM25 → 퍼지 검색 + 그래프 순회(위/아래, 깊이) | 파일 수준 정확도 최대 92.7% | https://github.com/gersteinlab/LocAgent |
| KGCompass | 이슈·PR·코드 지식 그래프 | 그래프 + BM25, 순위 융합(RRF) | 파일 top-20: BM25 0.77 vs 그래프만 0.556, 융합 0.946 | https://github.com/GLEAM-Lab/KGCompass (artifacts/results) |
| Agentless | 저장소 트리 + 본문을 접은 파일 골격 | 파일 → 요소 → 줄 단계적 | SWE-bench Lite 27.3% ($0.34/건) | https://github.com/OpenAutoCoder/Agentless |
| AutoCodeRover (ISSTA 2024) | AST 클래스·메서드 | 클래스 검색은 시그니처만, 3건 넘으면 파일 목록 | Lite 30.67% | https://github.com/nus-apr/auto-code-rover |
| SWE-agent (NeurIPS 2024) | 없음 | 검색은 파일 이름만, 100건 넘으면 거부, 100줄 뷰어 | (정성) | https://github.com/SWE-agent/SWE-agent |
| mini-swe-agent | 없음 (bash 만) | — | SWE-bench Verified 74% 초과 | https://github.com/SWE-agent/mini-swe-agent |
| Aider repo map | tree-sitter 정의·참조 | 개인화 PageRank, 토큰 예산 안에 이진 탐색으로 맞춤 | (평가 없음, 기본 1k 토큰) | https://github.com/Aider-AI/aider (aider/repomap.py) |
| Agent Retrieval Bench (2026) | 벤치마크 | BM25 · 임베딩 · RepoMap 비교 | RepoMap 이 8k 토큰 예산 수율 최고(0.379), BM25 R@20 0.445, **모든 과제에서 이기는 방식 없음** | https://github.com/eyuansu62/agent-retrieval-bench |
| LSP vs grep 파일럿 (2026) | 언어 서버 vs grep | 도구 표면만 바꾸는 4개 실험군 | 위치 찾기: LSP 가 토큰 +6~118%, 참조: LSP 정밀도 1.00 vs grep 0.76, 참조 줄을 같이 주면 후속 읽기 약 5배 감소 | https://github.com/Poytr1/lsp-vs-grep-token-study |
| SWE-PolyBench | 지표 | 수정 줄 → 가장 안쪽 함수·클래스 노드 | 파일·노드 P/R/F1 | https://github.com/amazon-science/SWE-PolyBench |
| SWE-Explore-Bench · ContextBench (2026) | 벤치마크 | — | 줄 예산 재현율, 유효/출력 줄 비율, 단계별 커버리지 | https://github.com/Qiushao-E/SWE-Explore-Bench · https://github.com/EuniAI/ContextBench |
| Anthropic 도구 설계 글 | — | 페이지·필터·자르기, 간결/상세 모드, 자를 때 더 좁은 질의로 유도 | Claude Code 도구 출력 기본 상한 25,000 토큰 | https://www.anthropic.com/engineering/writing-tools-for-agents |
| clangd 인덱스 설계 | Symbol(불투명 ID) · Ref(종류·위치·Container) · Relation(BaseOf, OverriddenBy), 동적+배경+정적 인덱스 병합 | — | — | https://github.com/llvm/clangd-www (design/indexing.md) · llvm-project clangd/index/Ref.h, Relation.h |

## 2. 하네스에 반영한 원칙

| 원칙 (근거) | 반영 | 위치 |
|---|---|---|
| 심볼은 이름이 아니라 ID 로 (RepoGraph 의 이름 키는 오버로드를 합친다; LocAgent `파일:한정이름`) | clangd SymbolID 를 키로, 출력은 `A::B` 한정 이름 | `cindex.py` |
| 간선 우선순위: 포함 → 참조·호출 → 상속·오버라이드 → 포함 파일·모듈 (LocAgent, CodexGraph) | 참조(+Container), BaseOf, OverriddenBy, 모듈(가장 가까운 Build.cs) | `cindex.py` |
| 영향 질의를 일급 도구로 (CodePlan may-impact) | `impact`: 파생·재정의·참조 함수·파일·모듈 | `cindex.py impact` |
| **어휘 검색을 버리지 말고 같이 쓴다** (KGCompass 융합, ARB "이기는 방식 없음", LSP 파일럿) | ripgrep(`ue_q.py rg`)·정규식 인덱스를 그대로 두고 clangd 를 더한다 | 전체 |
| 참조마다 그 줄 원문을 같이 준다 (LSP 파일럿: 후속 읽기 약 5배 감소) | `refs`, `callers`, `members` 가 줄 원문을 붙인다 | `cindex.py` |
| 넓은 질의는 정보를 주며 거부·축약 (SWE-agent 100건, Moatless 10건) | 4KB 상한 + "질의를 좁혀라" 안내, 같은 이름 후보 수 표시 | 세 스크립트 |
| 엔진은 버전별 정적 조각, 프로젝트만 자주 갱신 (clangd 정적/배경 인덱스) | 엔진 범위 인덱스는 엔진 경로당 하나·공유, 프로젝트 범위는 다시 만든다 | `cindex.py` |
| 측정 전에 인덱스를 데운다 (LSP 파일럿: 차가운 질의는 불완전) | 검증은 만들어진 인덱스에서만, 실패 TU 를 따로 센다 | `cindex.py eval` |

반영하지 **않은** 것: BM25 순위 융합(RRF), PageRank 저장소 지도, 줄 예산 지표, 단계별 커버리지. 증분 갱신은 5절(`--mode bg`)로 들어갔다.

## 3. 검증 기준 — 세 갈래

연구들의 평가 방식을 이 하네스에 옮긴 것이다. 각 줄에 **구현 여부**와 **기준값의 출처**를 적는다.

### A. 인덱스가 맞는가 (컴파일러를 정답으로)

LSP 파일럿이 언어 서버를 정답으로 쓴 방식. 같은 compile_commands 의 clangd 를 정답, 정규식 인덱스와 ripgrep 을 비교 대상으로 둔다.

| 지표 | 구현 | 통과 기준 |
|---|---|---|
| 좌표 정확도 (정규식: 줄에 이름이 있나 / clangd: 줄·열이 맞나) | 구현 — 검증 탭 "자체 검사" | 틀림 2% 이하 — **하네스가 정한 값** (문헌 근거 없음) |
| 타입 재현율 (clangd 가 본 클래스·구조체·열거형 중 정규식이 찾는 비율) | 구현 — "정규식 ↔ clangd 대조" | 95% 이상 — **하네스가 정한 값** |
| 파일 일치·줄 일치(±1)·부모 클래스 일치 | 구현 | 불일치 0 — 하네스가 정한 값, 불일치는 표본으로 본다 |
| 정규식 오탐 후보 | 구현 | 판정 없이 표본만 (전방 선언·매크로일 수 있다) |
| clangd 실패 TU, Container 기록 여부, 신선도 | 구현 | 실패 TU 0 |
| 참조 집합 P/R (ripgrep 대비) | **미구현** | 참고값: LSP 파일럿 grep 정밀도 0.76 (파이썬) |
| 편집 후 일관성까지 걸리는 시간 | `--mode bg` 로 측정 가능 — 합성 175 TU 에서 `.cpp` 하나 1.2s, 79 TU 가 포함한 헤더 11.2s (5절) | 하네스 기준값 없음 |

### B. 맞는 코드를 찾는가 (검색 수준)

| 지표 | 구현 | 기준 |
|---|---|---|
| 질의 → 기대 경로의 Acc@1 · Acc@5 · MRR (LocAgent·CoSIL 지표) | 구현 — 질의 세트 (`.claude/index_eval.json` 또는 clangd 정의 위치로 자동 생성) | 절대 기준 없음. 연구들의 값은 파이썬 저장소 기준 참고치일 뿐 (LocAgent 파일 92.7%, KGCompass 0.894@5) |
| 과거 커밋 재생: 커밋 메시지 = 질의, 수정 파일·함수 = 정답, **부모 커밋에서 만든 인덱스**로 (SWE-PolyBench, KGCompass 시간 안전) | **미구현** | 제안: 새 인덱스가 ripgrep 대비 파일 Acc@5 이상, 함수 Recall@10 과 토큰 예산 수율은 더 높을 것 |
| 엄격(정답 전부 top-k) vs 느슨(하나라도) Acc@k 를 둘 다 보고 | 미구현 (현재는 질의당 정답 하나) | 연구마다 정의가 달라 섞어 비교하지 않는다 |

자동 생성 질의는 "이름 → 정의 파일" 이라 정규식 인덱스의 이름 검색을 재는 것이지, 자연어 요청에서 위치를 찾는 능력을 재지 않는다.

### C. 에이전트의 토큰을 아끼는가 (끝단)

LSP 파일럿 설계: 모델·프롬프트·과제를 고정하고 도구 표면만 바꾼다 (ripgrep 만 / 인덱스만 / 둘 다 / 인덱스 먼저).

| 지표 | 구현 | 비고 |
|---|---|---|
| 같은 정답률에서 성공까지 토큰·비용·턴 | 구현 — `evals/cost_ab.py` (A = rg·Read, B = A + 인덱스 CLI) | 2026-10-06 합성 픽스처. 도구 수정 전: 평균 비용 Sonnet +17%, Opus −5%. **조회 결함 수정 뒤: Sonnet −39%, Opus −38%, 재현율 B 1.00** (수정 전과 같은 과제). 새 과제 세트 8종·새 시드 픽스처(도구 그대로): Sonnet −38%, Opus −16%, 재현율 B 1.00 (Sonnet A 0.93) — 이득은 명령 하나와 바로 맞는 질문(상속·파생·피호출)에 몰리고, 출력을 모듈 단위로 다시 엮는 질문은 같거나 B 가 비싸다. 상세: `docs/VERIFICATION.md` 2026-10-06 (3) |
| 도구 호출 수, 도구 출력 크기 | 구현 — 같은 스크립트 | 수정 뒤 도구 호출 B 2.6 vs A 4.6(Sonnet), 도구 출력 글자 −61%(Sonnet)·−63%(Opus). 새 과제 세트: 도구 호출 B 2.6 vs A 5.0(Sonnet), 도구 출력 글자 −33%(Sonnet)·−14%(Opus). 후속 파일 읽기·잘림 비율은 따로 세지 않았다 |

## 4. 처음 질문에 대한 답 — "엔진 검색 검증은 인덱싱이 전제인데 기준이 뭔가"

- 전제(인덱스 존재·엔진 경로·엔진 소스 유무·버전 일치)는 `ue_q.py` 가 조회 직전에 맞추고 경고한다 (조회 첫 회 자동 생성, 헤더 1000개 미만 경고, 버전 경고).
- 인덱스 **품질**은 위 A·B 를 웹뷰 검증 탭 또는 `cindex.py eval` 로 잰다. clangd 인덱스가 있으면 정규식 인덱스를 컴파일러 기준으로 대조할 수 있다.
- `ue_q.py` 인덱스의 **신선도**는 여전히 조회 시점에 비교하지 않는다 (`index` 를 돌릴 때만). 웹뷰 자체 검사가 파일 표본으로 낡음을 보여 준다.

## 5. 속도 — clangd 의 약점을 무엇으로 메웠나 (2026-10-06 추가)

**먼저 정직하게**: "C++ 의미 색인을 빠르게" 를 직접 다룬 학술 논문은 찾지 못했다. 근거는 대부분 **엔지니어링 1차 자료**
(llvm-project clangd 소스, Kythe·scip-clang·Glean·SCIP 설계 문서, Chromium·LLVM 운영 문서)와 이 환경에서 돌린 실험이다.
논문으로는 Stack Graphs (Creager & van Antwerpen, EVCS 2023) 가 파일 단위 증분 이름 해석을 다루지만 PDF 호스트가 막혀
요약만 봤고, C++ 문법이 없어 쓰지 않았다. 수집 환경에서 막힌 곳: drops.dagstuhl.de, web.archive.org, *.github.io 등 —
이때는 GitHub 원본 저장소를 읽었다.

### 비용이 어디서 나오나
- clang Modules 문서: N 개 TU 가 M 개 헤더를 포함하면 컴파일러가 *M × N* 일을 한다 (모듈이 *M + N* 으로 줄이는 이유).
  https://github.com/llvm/llvm-project/blob/main/clang/docs/Modules.md
- scip-clang 설계 문서: Clang 소스 2.6M 줄이 전처리 후 575M 줄 (약 220배 중복). https://github.com/sourcegraph/scip-clang/blob/main/docs/Design.md
- ClangBuildAnalyzer 표본(Blender): 프런트엔드 2,118.9s vs 백엔드 1,204.1s, `<algorithm>` 하나가 3,389번 포함돼 261.6s.
  색인기는 프런트엔드 비용만 낸다 → 헤더 중복 파싱이 비용의 거의 전부. https://github.com/aras-p/ClangBuildAnalyzer
- 실험(합성, clang 18): 공용 헤더가 TU 비용의 약 85%, 전처리만은 0.13s — 파싱·의미 분석이 비싸다.

### 이미 clangd 안에 있는 것
- 색인 액션은 함수 본문 파싱을 건너뛰고, 이미 다른 TU 가 맡은 헤더의 본문도 건너뛴다 (`index/IndexAction.cpp` `SkipFunctionBodies`, `ShouldTraverseDecl`).
- clangd-indexer 는 파일마다 처음 닿은 TU 만 심볼을 모은다 (`indexer/IndexerMain.cpp` `Files.insert(...).second`) — 그래서 병렬이면 결과가 실행마다 조금 다르다
  (Kythe 문서의 "dynamic claiming" 과 같은 방식. https://github.com/kythe/kythe/blob/master/kythe/cxx/indexer/cxx/claiming.md).
- 같은 이유로 `Symbol.References`(참조한 TU 수)는 clangd-indexer 출력에서 0 또는 1 에 그친다 — 웹뷰는 이 값을 참조 수로 쓰지 않는다 (실측: 값이 있는 139개 전부 1).
- PCH 는 쓸 수 없다: clangd 가 PCH 옵션을 지운다 (`Compiler.cpp` `disableUnsupportedOptions`). UE 는 C++20 모듈을 안 쓴다.

### 반영한 것

| 기법 | 근거 | 반영 | 합성 측정 (175 TU, 4코어) |
|---|---|---|---|
| **증분 — 배경 색인 샤드** | clangd 배경 색인: 파일마다 샤드, 내용 다이제스트로 낡음 판정 (`index/Background.cpp`, `BackgroundIndexLoader.cpp`, `BackgroundIndexStorage.cpp`); clangd 원격 색인 문서 "clangd-indexer 는 비싸고 증분이 아니다" (https://github.com/llvm/clangd-www design/remote-index.md) | `cindex.py build --mode bg` | 변경 없음 0.6s, `.cpp` 1.2s, 헤더(79 TU) 11.2s — 전체 24.8s 대비 |
| clangd 증분의 구멍 메우기 | `Background.cpp` FIXME (헤더 → TU 하나만), `BackgroundQueue.cpp` (플래그 무시), `Background.h` (세션 안 재색인 없음) | `cindex_speed.py` 무효화 계획: include 그래프·강제 포함·명령 해시·내용 해시 | 결과 = 처음부터 만든 색인 (5절 위 표) |
| 파일 단위 소유 (Glean "units") | Glean incrementality 문서: 사실을 파일 단위로 소유 → 바뀐 단위만 교체 https://github.com/facebookincubator/Glean (glean/website/docs/implementation/incrementality.md) | 샤드가 곧 단위. **sqlite 는 아직 매번 전체 다시 적재** (175 TU 샤드 658개 읽기 0.3s) | — |
| **유니티 묶음** | Chromium jumbo 문서 (공용 헤더가 많아 총 작업량이 크게 준다, 대가: 내부 링크 이름 충돌·묶음 단위 재빌드) https://github.com/chromium/chromium/blob/70.0.3515.0/docs/jumbo.md; UE 의 UBT 유니티 빌드와 같은 원리 | `--unity N` (실패 묶음은 원래 TU 로) | 23s → 4s (N=8), 8s (N=4), 결과 동일 |
| **RIFF 바이너리** | clangd `index/Serialization.cpp`·`RIFF.cpp` 배치를 표준 라이브러리로 읽음 | `clangd_riff.py`, `--format binary` 기본 | 37.6MB → 2.17MB, 적재 1.84s → 0.77s |
| 스레드 우선순위 | Windows 에서 `low`(기본)·`background` 는 스레드를 백그라운드 모드(I/O 우선순위↓)로 둔다 (llvm `lib/Support/Windows/Threading.inc`) | bg 모드는 `--background-index-priority=normal` | 리눅스에서는 차이를 재지 않았다 |

### 반영하지 않은 것과 이유
- **TU 줄이기(헤더를 덮는 최소 TU 집합)**: 실험에서 이미 맡은 헤더뿐인 TU 도 약 0.9s 든다 → 효과는 있겠지만 include 그래프가 먼저 있어야 해 다음 단계로 남겼다.
- **정적 claiming (Kythe) / scip-clang 계획기**: 주된 이득이 속도가 아니라 결정성이다. scip-clang 은 Windows 빌드가 없다.
- **tree-sitter 등 구문 색인 혼합**: clangd 비용을 줄이지 않는다 (신선도 보완용). 이 하네스는 정규식 인덱스가 그 자리를 맡는다.
- **PCH·C++20 모듈**: clangd 가 PCH 를 지우고 UE 는 모듈을 안 쓴다.

### 아직 모르는 것
UE 규모(샤드 수만 개)의 배경 색인 시간·메모리, Windows 에서의 동작, UE compile_commands 로 유니티 묶음이 되는지(TU 마다 rsp 가 다르면 안 묶인다),
RIFF 버전 21 실파일. 위 수치는 모두 합성 프로젝트 한 번씩의 측정이다.

