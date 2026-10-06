# jokate-harness

게임 프로젝트(Unreal Engine / Unity)용 Claude Code 하네스. 어느 프로젝트에 들어가도
엔진·프로젝트·기획을 좌표로 빠르게 파악하고, 기능 요청에서 한 기능에 매몰되지 않고
유지보수가 가장 좋은 구조를 **근거(변경 이력 계측 + 그림)와 함께 사람이 고르게** 한다.

- 사용 가이드 (사람용): [docs/GUIDE.md](docs/GUIDE.md)
- 검증 기록: [docs/VERIFICATION.md](docs/VERIFICATION.md)

## 구성

```
skills/
  game-bootstrap/     0층 · 프로젝트 세팅 (/game-bootstrap) · harness/ 훅 원본 · evals/ 평가
  game-onboard/       1층 · 엔진·프로젝트 파악 · scripts/gq.py, ue_q.py, cindex.py(clangd 의미 인덱스), index_view.py(웹뷰)
  game-design-doc/    1층 · 기획서 → 사양 표 → 구현 대응·어긋남
  game-architecture/  2층 · 구현 전 구조 조사 · scripts/evidence.py, render.py
  game-patterns/      2층 · 패턴 카탈로그 + 게임 도메인 증상 + UE/Unity 관용구 (출처 표시)
  game-testing/       3층 · 검증 기준·테스트
  game-mcp/           4층 · 에디터 MCP 운용
mods/
  game-harness-monitor/  Claude Code mod · 하네스 기능이 동작하면 상태줄·토스트·/harness 패널로 보인다
setup.bat             한 번에: 설치 + 훅 등록 + mod 등록 + 프로젝트 세팅 + 사용법 출력
uninstall.bat         제거: 스킬·훅·설정 항목 (+ 프로젝트 폴더를 주면 그 세팅도)
rules/common.md       모든 프로젝트 공용 규칙 (답변 길이). 설치 때 ~/.claude/CLAUDE.md 의 표시 구간에 들어간다
install.py / .bat    머신 설치: 스킬·훅, settings 조각 출력 (bat 는 더블클릭용)
bootstrap.bat         프로젝트 세팅: 폴더를 끌어다 놓으면 CLAUDE.local.md + 인덱스 선언
```

## 빠른 시작

`setup.bat` 더블클릭 (Windows) — 또는 게임 프로젝트 폴더를 `setup.bat` 위에 끌어다 놓는다. 한 번에:

1. 스킬·훅·mod 를 `~/.claude` 에 설치하고 `settings.json` 에 훅과 mod(`env.CLAUDE_CODE_PLUGIN_DIRS`)를 등록한다 (원본은 `settings.json.bak`)
2. 프로젝트 폴더를 물어보고 세팅한다 (`CLAUDE.local.md` + 인덱스 선언. `CLAUDE.md` 가 이미 있으면 라우팅 절만. 덮어쓰지 않는다)
3. 사용법을 출력한다

PowerShell 에서는 `.\setup.bat "D:\Work\MyGame"`. 다시 돌려도 안전하다 — 다른 프로젝트를 추가할 때도 같은 파일.
그 뒤에는 그 프로젝트에서 Claude Code 를 **새로** 열고 평소처럼 요청하면 된다.

나눠서 하려면 `install.bat`(머신) + `bootstrap.bat`(프로젝트). 프로젝트 규칙 파일이 없으면 스킬이 거의 불리지 않는다 —
평가로 확인한 사실이다 ([검증 기록](docs/VERIFICATION.md)).

## 제거

`uninstall.bat` 더블클릭 — 또는 세팅했던 프로젝트 폴더를 그 위에 끌어다 놓는다. 미리보기는 `--dry-run`.

- 머신: `~/.claude/skills/game-*`·`~/.claude/mods/game-harness-monitor`(링크만 끊는다), 설치한 훅 파일, `settings.json` 의 해당 훅 항목과 mod 경로(원본은 `.bak`, 다른 훅·env 는 그대로), 하네스 이벤트 로그
- 프로젝트: `CLAUDE.local.md` 는 `CLAUDE.local.md.removed` 로 이름만 바꾼다. 인덱스 선언·HandOff·프로젝트 인덱스는 지운다. `CLAUDE.md` 는 건드리지 않는다
- 한 프로젝트에서만 빼려면 `uninstall.bat "<폴더>" --project-only`
- 이 저장소 폴더는 남는다. 다시 쓰려면 `setup.bat`

## 요구

Python 3.10+, git (svn 은 선택 — 이력 신호용, 검증 안 됨), Claude Code 2.1.x.
선택: clangd-indexer (clangd 릴리스의 indexing tools, 의미 인덱스용). 모니터 mod 는 Claude Code 의 함수 훅 플러그인(early access, 2.1.290 에서 확인)이 필요하다.

## 하네스가 동작하는지 보기

- 상태줄 `harness ● 기능 N개 · 마지막 …` 과 토스트 — 모니터 mod. `/harness` 로 기록 패널.
- `python ~/.claude/skills/game-onboard/scripts/index_view.py --open` — 인덱스 검색·그래프·검증과 하네스 이벤트 기록을 브라우저로.
- 상세: [docs/GUIDE.md](docs/GUIDE.md) 8절.
