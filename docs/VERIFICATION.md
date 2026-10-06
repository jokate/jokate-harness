# 검증 기록

## 2026-10-01 — 초기 의도 대비

환경: Windows 11, Claude Code 2.1.280, UE 5.7(MNYS, git) · UE 5.6(InputProcessor, VCS 없음) · UE 5.3(MoonU). Unity 프로젝트·svn 클라이언트 없음.

| # | 초기 의도 | 판정 | 증거 |
|---|---|---|---|
| 1 | 여러 프로젝트에서 쓰는 범용 세팅 | 부분 | 유저 레벨 스킬·훅이 MNYS·InputProcessor·MoonU 에서 동작. CLAUDE.md 없는 프로젝트에서 스킬 미트리거 → 라우팅 훅 추가(재평가 전) |
| 2 | 프롬프트 구성·지시 자료 | 부합 | `docs/GUIDE.md` §5·6 |
| 3 | 구조 파악: 코드 / MCP / 기획 / 테스트 | 부합 | onboard · mcp · design-doc · testing. design-doc 은 실측 전 |
| 4 | 엔진 도메인 + 게임 패턴 | 부합 | game-patterns, 엔진 관용구 |
| 5 | 패턴·설계 구조 가이드 | 부합 | game-patterns, game-architecture |
| 6 | 엔진·프로젝트 빠른 파악 | 부합 (UE) | gq.py MNYS 실측, ue_q.py 엔진별 인덱스(5.7/5.6). Unity 는 가짜 프로젝트만 |
| 7 | 하네스 | 부합 | SessionStart 가 새 세션에서 발화·인덱스 갱신 확인 |
| 8 | 매몰 방지 + 유지보수 최선 구조 조사 + 근거 그림 (사내 포함) | 핵심 부합, 근거 반쪽 | 아래 E2E. SVN 검증 안 됨 |

## 2026-10-01 — E2E (새 헤드리스 세션, 수정 금지)

| 케이스 | 스킬 | 결과 |
|---|---|---|
| CC 체계 (MNYS 백로그 P3-12) | game-architecture ✅ | 요청 축 분해 → 기존 확장 지점 → A/B/C + "다음 요청 때 고칠 곳" → 그림 2장 → 판단 대기에서 멈춤. 코드 사실 2건 교차 확인 일치. 문서-코드 불일치 2건 발견. **결함**: 루트 저장소(커밋 2)를 보고 변경 이력 신호 생략 — 소스가 별도 저장소(`Source/`, 커밋 220). `flowchart` 사용(규칙 위반) |
| 연사 간격 (P2-9, 작은 필드 추가) | 미호출 ❌ | CLAUDE.md §10 덕에 선택지 A/B/C 는 냄. 백로그가 가리키는 타입이 코드에서 사라진 것 발견(확인함) |
| 구조 파악 (InputProcessor, CLAUDE.md 없음) | 미호출 ❌ | 직접 ls/cat 로 파악. 내용은 구체적이나 인덱서 미사용 |
| 엔진 API (UGameplayAbility) | game-onboard ✅ | 조회 권한이 막히자 기억으로 답하며 "확인 필요" 표기 — 정직 규칙 동작 |

비용: 세 케이스 합계 약 $3.1.

## 2026-10-01 — 반복 평가 (run_evals.py)

| 회차 | 케이스 | 결과 | 비용 | 그 회차 뒤에 바꾼 것 |
|---|---|---|---|---|
| 1 | 8 | 16/23 | $7.90 | UserPromptSubmit 분류 훅 추가, 평가 셸 허용을 조회 스크립트로 축소, testing 에 검증 상태 줄 |
| 2 | 8 | 17/23 | $7.01 | 아래 "원인 규명" 후 분류 훅 제거, 비대화식 `bootstrap.py`/`bootstrap.bat`, 평가에 fixture(사본+bootstrap) |
| 3 | 9 | 23/25 → 재채점 25/25 | $7.18 | 채점 정규식 수정 ("다음 CC 때 고칠 곳 3곳" 같은 표현을 놓쳤다 — 행동은 맞았다) |
| 4 | 9 | **25/25** (확인 라운드) | $6.49 | 산출물 직접 검토: `arch-new` 가 선택지에 "(추천)" 을 붙임 → SKILL.md 에 추천 금지 한 줄, 채점 추가 (기존 로그 재채점 시 6건 중 1건 위반) |
| 5 | 3 (구조 판단만) | **14/14** | $2.96 | — 멈춤 |

멈춤 기준: 전 케이스 통과 1회 + 확인 라운드 90% 이상. 3회차(재채점)·4회차·5회차 모두 충족. 평가·진단 누적 비용 약 $34.

산출물 샘플 (사람이 품질을 판정하는 용도): [docs/samples/](samples/) — 구조 판단 2건, 기획 대조 1건.

### 원인 규명 — 스킬이 안 불리던 프로젝트

CLAUDE.md 없는 프로젝트(InputProcessor)에서 스킬이 전혀 불리지 않았다. 한 턴짜리 헤드리스로 원인을 좁혔다.

| 시도 | 첫 행동 |
|---|---|
| SessionStart 라우팅 안내 | 파일 탐색 |
| + UserPromptSubmit 요청 분류 안내 (평문 stdout) — 훅 호출·주입은 `--include-hook-events` 로 확인 | 파일 탐색 ×2 |
| 같은 안내를 JSON `additionalContext` 로 | 파일 탐색 ×2 |
| 유저 레벨 `~/.claude/CLAUDE.md` 에 조건부 라우팅 | 파일 탐색 ×2, 게임 아닌 프로젝트에서 `*.uproject` 탐색 부작용 → 되돌림 |
| 요청에 스킬 이름을 직접 적음 | Skill ✅ |
| **프로젝트 CLAUDE.md** (템플릿 필수+구조 모듈) | Skill ✅ ×3, gq.py ×1 |
| **프로젝트 CLAUDE.local.md** (같은 내용) | Skill ✅ ×2 |

결론: 스위치는 프로젝트 규칙 파일이다. 훅이 넣는 컨텍스트는 규칙 파일만큼의 무게를 받지 못했다 (Claude Code 2.1.280, 이 머신 기준).

### 안전 기록

1회차에서 새 프로젝트 케이스의 세션이 "구현해줘"를 그대로 따라 셸 heredoc 과 서브에이전트로 소스 쓰기를 시도했다.
헤드리스가 허용 목록 밖 도구를 자동 거부해 **파일은 바뀌지 않았다**(수정 시각 확인). 이후 평가는 원본 대신 fixture 사본에서 돌리고,
셸 허용을 조회 스크립트 경로로 좁혔다. 읽기 전용 명령(ls·find·cat)은 허용 목록 밖이어도 실행된다.

## 2026-10-01 — 매몰 감지와 HandOff (`stuck_watch.py`, `handoff.py`)

Claude Code 2.1.285, 헤드리스. 임계값을 2로 낮춘 임시 프로젝트에서.

| 확인 | 결과 |
|---|---|
| 같은 파일 2회 수정 → 경고 | PostToolUse 훅의 `systemMessage` 가 사용자 채널 알림(`system/informational`, notice)으로 나옴 |
| 셸 명령 연속 2회 실패 → 경고 | Bash 의 0 아닌 종료 코드에서 PostToolUseFailure 발화, 같은 알림 |
| `[RESET]` → HandOff 작성 | UserPromptSubmit 훅이 `.claude/handoff.md` 를 쓰고 프롬프트를 막음, 안내문이 사용자에게 나옴. 짧은 세션 15초 |
| 긴 세션 (기록 5.3MB → 발췌 81KB) | haiku 80초. 형식은 지켰으나 수치 1건 틀림, 기록에 없는 문장 1건 — 읽고 나서 `/clear` |
| 다음 세션 주입 | SessionStart 가 문서를 넣고 `handoff.used.md` 로 바꿈. 새 세션이 '원래 요청'을 그대로 되읽음 |
| 실제 `~/.claude/settings.json` 등록 후 | 위 경고·작성 재확인 |

첫 판 HandOff 는 도구 호출을 못 봐서 끝난 일을 "남은 일"로 적었다 → 발췌에 도구 호출 한 줄(실패 표시 포함)을 넣었다.

검증 안 됨: 데스크톱 앱·대화형 터미널에서 알림이 어떻게 보이는지 · `/clear`·`/compact` 뒤 주입(헤드리스는 새 세션 시작으로만 확인) ·
임계값(5·3)이 실제 매몰을 잘 가르는지 · HandOff 로 시작한 세션이 실제로 매몰에서 벗어나는지.

## 2026-10-06 — 패턴 보강 · clangd 의미 인덱스 · 인덱스 웹뷰 · 하네스 모니터

환경: 이 저장소를 고친 클라우드 컨테이너 (Linux, Python 3.13, Claude Code 2.1.290, clangd-indexer 23.1.0 리눅스판, Chromium/Playwright).
**Windows·실제 UE 엔진·실제 프로젝트에서는 돌리지 않았다.** UE 는 매크로·Build.cs·.uproject 를 흉내 낸 가짜 엔진·프로젝트(fixture)로만 확인했다.

| 대상 | 확인 방법 | 결과 |
|---|---|---|
| 하네스 이벤트 기록 (`harness_events.py`, 훅 6종 + `harness_trace.py`) | 훅마다 stdin 에 샘플 JSON → `events.jsonl` 확인 | 세션 시작 명령 성공·실패, 라우팅 주입, game-* 스킬만 기록(다른 스킬 무시), Windows·POSIX 경로의 조회 스크립트 인식, 실패 표시, MCP 호출 기록 |
| `ue_q.py`·`gq.py` 인덱스 이벤트 | fixture 에서 index·조회 | `index.engine`, `index.project`, `index.engine.warn`(헤더 수) 기록 |
| 모니터 mod (`mods/game-harness-monitor`) | `claude plugin validate` · `tsc`(엔진이 놓은 설정 포함) · `claude plugin test` · `claude -p --plugin-dir` | 검증 통과, 타입 검사 통과, 테스트 5/5 (세션 시작 → 로그 폴링 → 처음 동작한 기능만 토스트·상태줄, `/harness` 명령, 패널이 terminal·desktop 표면에서 그려짐), 헤드리스 로드 오류 없음 |
| 설치·제거 (`install.py`, `uninstall.py`) | 임시 HOME 에 설치 → 재설치 → 제거 | 훅 7종·모듈·mod 링크·`env.CLAUDE_CODE_PLUGIN_DIRS` 등록, 재실행 시 중복 없음, 제거 후 사용자 기존 env·훅 보존 |
| clangd 의미 인덱스 (`cindex.py`) | fixture 에 compile_commands.json(5 TU) → 프로젝트·엔진 범위 build → 모든 조회 명령 | sym·refs(줄 원문)·callers·callees·bases·derived·overrides(3단계)·members·impact·file·status 출력이 소스와 일치 |
| 실패 감지 | 경로가 틀린 TU, `.generated.h` 누락 TU | 종료 코드 0 인데 실패 TU 2 / 1 로 집계, `.generated.h` 경고 |
| 표준 라이브러리 YAML 파서 | clangd 실험 YAML 5종(문서 5,013개)을 PyYAML 과 문서 단위 대조 | 불일치 0 (clangd 23.1.0 concept 버그 줄 73개는 적재 때 우회), 약 26–30 MB/s, 4,721 문서 적재 0.38초 |
| 인덱스 웹뷰 (`index_view.py`) | API 전 경로 + Playwright 스크린샷 (라이트·다크·폭 390px) | 검색·상세·상속/호출/오버라이드/모듈 그래프·자체 검사·대조·질의 세트·하네스 탭 동작, 콘솔 오류 0, 모바일 가로 스크롤 없음 |
| 정규식 ↔ clangd 대조 (fixture) | `cindex.py eval` | 타입 재현율 100%, 파일·줄·부모 일치 — fixture 가 작아 정규식의 실제 누락률은 말해 주지 않는다 |
| 게임 패턴 문서 | 출처 표시 검수 | 원 사이트(gameprogrammingpatterns.com, dev.epicgames.com 등)가 수집 환경에서 막혀 공개 저장소 사본(GitHub)으로 읽었고, 검색 요약만 본 주장은 `‡`·`[공식·요약]` 으로 표시 |

검증 안 됨:
- 실제 UE 5.x 엔진·프로젝트, Windows, UBT `GenerateClangDatabase`(`cindex.py cdb`), VS Code 생성기 경로, 실제 규모의 색인 시간·메모리
- 모니터 mod 를 사용자 머신의 Claude Code 버전(2026-10-01 기록 기준 2.1.280/2.1.285)과 대화형 터미널·데스크톱 앱에서 — 이번엔 테스트 키트와 헤드리스 로드만
- 실제 세션에서 훅이 이벤트를 남기는지 (stdin 샘플로만 확인)
- 하네스 평가(`run_evals.py`)는 이번 변경 뒤 다시 돌리지 않았다. game-patterns 평가 케이스는 없다
- 인덱스 검증 B(과거 커밋 재생)·C(토큰 비용)는 구현하지 않았다 — `skills/game-onboard/references/indexing-research.md` 3절
- 검증 기준값 중 좌표 오차 2%, 타입 재현율 95% 는 하네스가 정한 값이다 (문헌 근거 없음)

## 2026-10-06 (2) — clangd 색인 속도 보완 · 웹뷰 재설계

환경: 같은 컨테이너 (Linux 4코어, clangd·clangd-indexer 23.1.0 리눅스판, Chromium/Playwright). **Windows·실제 UE 에서는 돌리지 않았다.**
측정용 합성 UE 구조: 엔진 25 + 프로젝트 5 모듈, TU 175, 공용 헤더가 STL 10종 포함. 수치는 한 번씩 잰 벽시계 값.

| 대상 | 확인 방법 | 결과 |
|---|---|---|
| 적재 리팩터링 (YAML·RIFF·샤드 공통 경로) | 같은 직렬 YAML 을 이전 코드(git HEAD)와 새 코드로 적재해 표 비교 | 심볼·참조·관계 완전 일치 |
| RIFF 리더 (`clangd_riff.py`, 기본 `--format binary`) | 같은 직렬 실행의 YAML·RIFF 적재 비교 | concept 74개 종류 이름(YAML 버그)만 다름. 출력 37.6MB → 2.17MB, 적재 1.84s → 0.77s |
| `--unity 4`·`8` | 묶지 않은 직렬 색인과 표 비교 | 완전 일치. clangd-indexer 23s → 8s / 4s |
| 유니티 실패 처리 | 한 모듈 두 `.cpp` 에 같은 이름 익명·`static` 함수를 넣어 충돌 | indexer: 실패 묶음 1개 → 원래 TU 6개 재색인, 참조 중복 0 (파일 범위 함수 참조 3건이 더 잡힘). bg: 묶음을 풀고 기억, 다음 빌드부터 묶지 않음 |
| `--mode bg` 증분 | 처음 / 변경 없음 / `.cpp` 수정 / 모든 TU 가 포함한 헤더 / 79 TU 가 포함한 헤더 / mtime 만 / 플래그 / TU 제거·복구 / 유니티 켜고 끄기 | 24.8s / 0.6s(0 TU) / 1.2s(1) / 24.6s(175) / 11.2s(79) / 0.6s(0) / 1.2s(1) / 샤드 2개 정리·2 TU / 전환 때 TU 로 바뀐 파일 168개 재색인 |
| 증분 결과의 정확성 | 헤더 맨 위에 줄을 넣어 줄 번호를 밀고, 증분 결과 vs 같은 상태의 처음부터 직렬 색인 | 심볼·관계 완전 일치, 참조는 컴파일러 내장 헤더 경로 70건만 다름 (두 바이너리의 resource-dir 위치 차이) |
| 샤드 위치 | `XDG_CACHE_HOME` 을 빈 폴더로 두고 실행 | 샤드 전부 `<색인 폴더>/bg/.cache/clangd/index` — 전역 캐시에 쓴 것 없음 |
| clangd 자체 동작 (연구 문서 근거 재확인) | 무효화 없이 clangd 만 | 모든 TU 가 포함한 헤더를 고쳐도 TU 1개만 재색인, `Symbol.References` 는 값이 있는 139개 전부 1 |
| 웹뷰 | Playwright (라이트·다크·폭 390px), 그래프 배치 5종 | 콘솔 오류 0, 모바일 가로 스크롤 없음. 탐색 "참조 수" 를 실제 참조 기록 수로 바로잡음, 계층 배치(깊이 띠·직교 간선), 트리 배치, 파이프라인 증분 칸·인덱스 해부 |

검증 안 됨:
- UE 규모(샤드 수만 개)의 `--mode bg` 시간·메모리, Windows 에서의 배경 색인 구동(LSP 파이프·`--background-index-priority`)
- UE 의 실제 compile_commands 로 `--unity` 묶음이 되는지 — TU 마다 다른 rsp 면 묶이지 않는다
- RIFF 버전 19(소스 비교만)·21(소스만 보고 작성) 실파일
- `--mode bg` 는 오류 줄·`.generated.h` 오류를 세지 못한다 (샤드 HadErrors 로 오류 TU 만)

## 반영된 것 (누적)

- `evidence.py roots` + 커밋이 적으면 게임 소스가 가장 많은 하위 저장소 안내 (게임 소스 0 인 저장소는 제외)
- SessionStart `game_context.py`: 엔진·소스 저장소·스킬 라우팅 안내
- 그림 규칙 3줄을 SKILL.md 본문으로, 셸 변수 축약 제거
- `ue_q.py`: 첫 조회 때 엔진 인덱스 자동 생성, 엔진 소스가 없는 설치 경고, 프로젝트 엔진 버전과 다르면 경고
- `game-design-doc`, 비대화식 bootstrap
- 하네스 이벤트 로그 + 추적 훅 + 모니터 mod, `cindex.py`(clangd 의미 인덱스), `index_view.py`(웹뷰), game-patterns 도메인 증상·패턴 심화·UE 관용구 (2026-10-06)
- `cindex.py` 속도: RIFF 기본, `--unity N`, `--mode bg` 증분(`cindex_speed.py`) · 웹뷰 계층/트리 그래프·증분 칸·인덱스 해부 (2026-10-06)

## 검증 안 된 것

- svn 경로 (`evidence.py`) — 작성 머신에 svn 없음
- 실제 Unity 프로젝트 (가짜 프로젝트로만)
- 대화형 세션 — 평가는 전부 헤드리스(`claude -p`)였다. 대화형에서는 권한 프롬프트가 뜨는 점이 다르다
- 대화형 세션에서 PowerShell 도구로 한글 인자 명령이 파싱 실패하는지 (헤드리스에서만 관찰)
- 평가 케이스가 MNYS 1인 개발자 문맥에 치우쳐 있다 — 팀 프로젝트의 커밋 습관에서 변경 이력 신호가 어떻게 나오는지 모름
