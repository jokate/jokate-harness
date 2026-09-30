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
install.py / .bat    머신 설치: 스킬·훅, settings 조각 출력 (bat 는 더블클릭용)
bootstrap.bat         프로젝트 세팅: 폴더를 끌어다 놓으면 CLAUDE.local.md + 인덱스 선언
```

## 빠른 시작

`install.bat` 더블클릭 (Windows). 또는

```
python install.py            # 또는 --link (저장소 수정이 바로 반영)
```

출력된 hooks 조각을 `~/.claude/settings.json` 에 합친다.

그다음 **프로젝트마다 한 번**: 프로젝트 폴더를 `bootstrap.bat` 위에 끌어다 놓는다 (또는 Claude Code 에서 `/game-bootstrap`).
프로젝트 규칙 파일이 없으면 스킬이 거의 불리지 않는다 — 평가로 확인한 사실이다 ([검증 기록](docs/VERIFICATION.md)).

## 요구

Python 3.10+, git (svn 은 선택 — 이력 신호용, 검증 안 됨), Claude Code 2.1.x.
