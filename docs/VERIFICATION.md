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

## 이후 반영 (재평가 전)

- `evidence.py roots` + 커밋이 적으면 게임 소스가 가장 많은 하위 저장소를 안내
- SessionStart `game_context.py`: 게임 프로젝트면 엔진·소스 저장소·스킬 라우팅을 컨텍스트에 주입
- 그림 규칙 3줄을 SKILL.md 본문으로, 셸 변수 축약 제거
- `ue_q.py`: 첫 조회 때 엔진 인덱스 자동 생성, 엔진 소스가 없는 설치(헤더 < 1000) 경고
- `game-design-doc` 추가

재평가: `python skills/game-bootstrap/evals/run_evals.py`

## 검증 안 된 것

- svn 경로 (`evidence.py`) — 작성 머신에 svn 없음
- 실제 Unity 프로젝트
- 라우팅 훅이 트리거율을 올리는지
- `game-design-doc` 실측
- 대화형 세션에서 PowerShell 도구로 한글 인자 명령이 파싱 실패하는지 (헤드리스에서만 관찰)
