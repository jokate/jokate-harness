# game-harness

게임 프로젝트(Unreal Engine / Unity)용 Claude Code 하네스. 어느 프로젝트에 들어가도
엔진·프로젝트·기획을 좌표로 빠르게 파악하고, 기능 요청에서 한 기능에 매몰되지 않고
유지보수가 가장 좋은 구조를 **근거(변경 이력 계측 + 그림)와 함께 사람이 고르게** 한다.

- 사용 가이드 (사람용): [docs/GUIDE.md](docs/GUIDE.md)
- 검증 기록: [docs/VERIFICATION.md](docs/VERIFICATION.md)

## 구성

```
skills/
  game-bootstrap/     0층 · 프로젝트 세팅 (/game-bootstrap) · harness/ 훅 원본 · evals/ 평가
  game-onboard/       1층 · 엔진·프로젝트 파악 · scripts/gq.py, ue_q.py
  game-design-doc/    1층 · 기획서 → 사양 표 → 구현 대응·어긋남
  game-architecture/  2층 · 구현 전 구조 조사 · scripts/evidence.py, render.py
  game-patterns/      2층 · 패턴 카탈로그 + UE/Unity 관용구
  game-testing/       3층 · 검증 기준·테스트
  game-mcp/           4층 · 에디터 MCP 운용
setup.bat             한 번에: 설치 + 훅 등록 + 프로젝트 세팅 + 사용법 출력
install.py / .bat    머신 설치: 스킬·훅, settings 조각 출력 (bat 는 더블클릭용)
bootstrap.bat         프로젝트 세팅: 폴더를 끌어다 놓으면 CLAUDE.local.md + 인덱스 선언
```

## 빠른 시작

`setup.bat` 더블클릭 (Windows) — 또는 게임 프로젝트 폴더를 `setup.bat` 위에 끌어다 놓는다. 한 번에:

1. 스킬·훅을 `~/.claude` 에 설치하고 `settings.json` 에 훅을 등록한다 (원본은 `settings.json.bak`)
2. 프로젝트 폴더를 물어보고 세팅한다 (`CLAUDE.local.md` + 인덱스 선언. `CLAUDE.md` 가 이미 있으면 라우팅 절만. 덮어쓰지 않는다)
3. 사용법을 출력한다

PowerShell 에서는 `.\setup.bat "D:\Work\MyGame"`. 다시 돌려도 안전하다 — 다른 프로젝트를 추가할 때도 같은 파일.
그 뒤에는 그 프로젝트에서 Claude Code 를 **새로** 열고 평소처럼 요청하면 된다.

나눠서 하려면 `install.bat`(머신) + `bootstrap.bat`(프로젝트). 프로젝트 규칙 파일이 없으면 스킬이 거의 불리지 않는다 —
평가로 확인한 사실이다 ([검증 기록](docs/VERIFICATION.md)).

## 요구

Python 3.10+, git (svn 은 선택 — 이력 신호용, 검증 안 됨), Claude Code 2.1.x.
