# cindex.py — clangd 의미 인덱스 상세

정규식 인덱스(`gq.py`, `ue_q.py`)는 선언 줄만 본다. `cindex.py` 는 clangd-indexer 가 **실제로 컴파일하며** 모은
심볼(함수·메서드·필드 포함, 선언+정의 위치) · 참조(어디서, 어느 함수 안에서) · 관계(상속 BaseOf, 오버라이드 OverriddenBy)를
sqlite 에 담는다. 설계 근거와 검증 기준: [indexing-research.md](indexing-research.md).

## 목차
1. 언제 무엇을 쓰나
2. 준비: clangd-indexer / clangd, compile_commands.json
3. 만들기 — 속도에 따라 고른다 (RIFF · 유니티 · 증분)
4. 조회 명령
5. 검증 (웹뷰 검증 탭과 같은 계산)
6. 함정
7. 검증 상태

## 1. 언제 무엇을 쓰나

| 질문 | 도구 |
|---|---|
| 클래스가 어디 있나, 부모가 뭔가, 시그니처 | `ue_q.py sym/api` (엔진) · `gq.py sym` (프로젝트) — 컴파일 없이 바로 |
| 이 함수를 **누가 부르나**, 이 함수 안에서 **뭘 부르나** | `cindex.py callers` / `callees` |
| 이 가상 함수를 **누가 재정의했나**, 이 클래스의 **자식 전부** | `cindex.py overrides` / `derived` |
| 이걸 바꾸면 **같이 볼 곳** (game-architecture 의 "다음 요청 때 고칠 곳") | `cindex.py impact` |
| 이름이 흔해서 grep 결과가 잡음투성이 (`Tick`, `BeginPlay`, `GetOwner`) | `cindex.py refs` — 같은 이름 다른 심볼을 가른다 |
| 문자열·주석·매크로 본문·설정 검색 | `ue_q.py rg` / Grep — 의미 인덱스로 대체하지 않는다 |

논문들의 결론도 같다: 의미 인덱스는 grep 을 **대체하지 않고 정밀도를 더한다** (indexing-research.md 3절).

## 2. 준비

### clangd-indexer (`--mode indexer`, 기본)
- clangd 공식 릴리스의 indexing tools 압축 파일에 들어 있다. 2026-10 기준 최신 23.1.0:
  `https://github.com/clangd/clangd/releases/download/23.1.0/clangd_indexing_tools-windows-23.1.0.zip` (`clangd-indexer.exe`)
  — 리눅스·맥은 이름의 `windows` 를 `linux`/`mac` 으로. `dexp` 는 어느 배포에도 없다.
- 둘 곳: PATH, `~/.claude/tools/clangd/bin/`, 또는 `--indexer <경로>` / 환경 변수 `CLANGD_INDEXER`.
- **setup 이 설치한다**: `clangd_tools.py install` (install.py 단계) — 못 찾는 것만 23.1.0 릴리스에서 받아 SHA-256 을 대조하고
  `~/.claude/tools/clangd/{bin, lib/clang/23/include, share}` 에 푼다. `lib/clang/23/include` 는 clang 내장 헤더(`stddef.h` 등)로
  실행 파일이 `../lib/clang/<버전>` 에서 찾는다 — 없으면 표준 헤더를 쓰는 TU 가 전부 실패한다(시험에서 33/33).
  `lib/clang/23/lib`(링크용 컴파일러 런타임)는 색인에 안 쓰여 뺀다. 버전 고정 이유: RIFF 리더와 시험이 23.1.0 출력으로 검증됐다.
  `status` 로 확인, `remove` 는 이 스크립트가 설치한 파일만 지운다 (`uninstall --purge` 가 부른다).

### clangd (`--mode bg`, 증분)
- 배경 색인은 clangd 본체를 쓴다 — 같은 릴리스의 `clangd-windows-23.1.0.zip` (릴리스 자산 목록 기준) 또는 이미 깔린 clangd.
- 찾는 순서: `--clangd` > 환경 변수 `CLANGD` > PATH > `~/.claude/tools/clangd/bin/` > clangd-indexer 옆.

### compile_commands.json
- **UE 프로젝트**: `python cindex.py cdb` → `Engine/Build/BatchFiles/Build.bat -mode=GenerateClangDatabase -project=<uproject> <이름>Editor Win64 Development -OutputDir=<프로젝트 루트>`.
  UBT 옵션은 버전마다 다르다 (UE 미러 소스를 읽은 결과, **실제 엔진에서 돌려 보지 않았다**):

  | UE | 옵션 |
  |---|---|
  | 5.1–5.3 | `-Filter=`, `-ExecCodeGenActions`(기본 꺼짐), `-OutputDir=` |
  | 5.4 | `-Filter=` 는 받지만 적용 안 됨, `-NoExecCodeGenActions`(UHT 기본 켜짐), `-OutputDir=` |
  | 5.5–5.6 | `-Include=` / `-Exclude=`, `-OutputFilename=`, `-OutputDir=`(기본 엔진 루트) |

  5.4+ 는 유니티 빌드·PCH 를 끄고 UHT(코드 생성)를 먼저 돈다 → `.generated.h` 가 생긴다. 항목은 `clang-cl.exe @rsp` 형태.
- **런처 설치 엔진**: 엔진 모듈이 미리 빌드돼 있어 위 데이터베이스에는 **프로젝트 파일만** 나온다. 엔진 cpp 까지 색인하려면
  VS Code 프로젝트 생성기의 `.vscode/compileCommands_<이름>.json` (cl.exe + 모듈별 rsp, 엔진 모듈 포함)을 쓴다.
  `/std` 가 빠져 있으니 `--extra-arg=/std:c++20` 을 준다. `cindex.py build` 는 이 파일을 자동으로 찾아 `compile_commands.json` 이름으로 복사해 넘긴다.
- **그 외 C++**: 빌드 시스템이 만든 것 (CMake 는 `CMAKE_EXPORT_COMPILE_COMMANDS=ON`) → `--cdb`.

## 3. 만들기 — 속도에 따라 고른다

clangd 의 약점은 속도다: 색인 비용은 거의 전부 **TU 마다 같은 헤더를 다시 파싱**하는 데서 나온다 (근거와 출처:
[indexing-research.md](indexing-research.md) 5절). 그래서 세 가지를 둔다.

```
python ~/.claude/skills/game-onboard/scripts/cindex.py build                         # clangd-indexer 전체, RIFF 출력 (기본)
python ~/.claude/skills/game-onboard/scripts/cindex.py build --unity 8               # .cpp 8개씩 한 TU 로 묶어 헤더 파싱을 줄인다
python ~/.claude/skills/game-onboard/scripts/cindex.py build --mode bg               # clangd 배경 색인 샤드로 증분 — 두 번째부터 바뀐 것만
python ~/.claude/skills/game-onboard/scripts/cindex.py build --mode bg --unity 8     # 둘 다
python ~/.claude/skills/game-onboard/scripts/cindex.py build --scope engine --unity 8   # 엔진 범위 (엔진 버전당 한 번)
python ~/.claude/skills/game-onboard/scripts/cindex.py ingest <clangd-indexer 출력(YAML|RIFF)>   # 이미 만든 출력 적재만
```

한 번에: `index_all.py [<프로젝트>]` (저장소의 `index_build.bat`) — gq·ue_q 인덱스 다음에 compile_commands.json 이 없을 때만 `cdb`,
프로젝트는 `--mode bg`(clangd 가 없으면 clangd-indexer 전체), 엔진은 엔진 clangd 인덱스가 없을 때만 `--scope engine --unity 8`.
cdb 에 엔진 TU 가 없으면(런처 설치 엔진) 엔진 단계는 빈 인덱스를 만들지 않고 건너뛴다 — 아래 2절의 VS Code cdb 를 `--cdb` 로 준다.

| 상황 | 권장 |
|---|---|
| 엔진 범위 (버전당 한 번, 오래 걸림) | `--unity 8` — 처음 색인이 가장 크게 준다 |
| 프로젝트 범위 (작업하며 자주) | `--mode bg` — 두 번째부터 바뀐 파일과 그것을 포함한 TU 만 |
| clangd-indexer 가 없다 | `--mode bg` (clangd 본체만 있으면 된다) |
| 두 인덱스를 비교·재현 | `--jobs 1` (병렬이면 헤더를 먼저 잡은 TU 가 매번 달라 참조 집합이 조금씩 다르다) |

**측정 (합성 UE 구조, 실제 UE 아님)**: 엔진 25 + 프로젝트 5 모듈, TU 175, 공용 헤더가 STL 10종을 포함, 리눅스 4코어, clangd 23.1.0.
한 번씩 잰 벽시계 값이다.

| 방식 | 처음 | 변경 없음 | `.cpp` 하나 수정 | 헤더 하나 수정 (TU 79개가 포함) | 플래그 하나 변경 |
|---|---|---|---|---|---|
| indexer (기본) | 23s | 항상 전체 | 항상 전체 | 항상 전체 | 항상 전체 |
| indexer `--unity 4` / `--unity 8` | 8s / **4s** | 항상 전체 | 항상 전체 | 항상 전체 | 항상 전체 |
| `--mode bg` | 24.8s | **0.6s** (0 TU) | **1.2s** (1 TU) | 11.2s (79 TU) | 1.2s (1 TU) |
| `--mode bg --unity 8` | 5.6s | 0.6s | 1.3s (묶음 1개) | 재지 않음 | 재지 않음 |

- 결과 동일성: 증분 결과 = 같은 상태에서 처음부터 만든 직렬 색인 (심볼·관계 완전 일치, 참조는 컴파일러 내장 헤더 경로 70건만 다름 —
  clangd 와 clangd-indexer 바이너리의 resource-dir 위치 차이). `--unity 4`·`8` = 묶지 않은 색인 (심볼·참조·관계 완전 일치).
- RIFF(binary) vs YAML: 출력 2.17MB vs 37.6MB (17배), 적재 0.77s vs 1.84s. 내용은 C++20 concept 74개의 종류 이름만 다르다 (YAML 쪽 버그).
- 위치: 프로젝트 `Saved/ClaudeIndex/clangd.sqlite` (UE) · 엔진 `~/.claude/cache/ue_index/<엔진경로>/clangd.sqlite` (ue.sqlite 옆, 프로젝트끼리 공유).
  `--mode bg` 는 그 옆 `bg/` 에 샤드(`.cache/clangd/index/*.idx`)와 `state.json` 을 둔다. 사용자 전역 clangd 캐시는 건드리지 않는다
  (`--compile-commands-dir` 를 주면 모든 파일이 그 CDB 프로젝트에 속해 샤드가 그 아래로 간다 — clangd GlobalCompilationDatabase.cpp, 실행으로 확인).
- 범위는 `--filter`(번역 단위 경로 정규식)로 자른다. 기본: project = 프로젝트 루트 아래 TU, engine = 엔진 루트 아래 TU.
  **프로젝트 범위 인덱스에도 프로젝트가 포함한 엔진 헤더의 심볼이 들어간다** — "내 프로젝트가 쓰는 엔진 API" 를 바로 조회할 수 있다.
- 세션 시작 훅은 이것을 돌리지 않는다 (컴파일이라 오래 걸린다). `status` 가 `[낡음]` 을 내면 다시 만든다.

### `--mode bg` 가 clangd 위에 더하는 것
clangd 배경 색인은 파일마다 샤드를 남기고 내용 다이제스트가 바뀐 파일만 다시 색인한다. 하지만 혼자서는 다음을 놓친다
(llvm-project clangd 소스와 실험으로 확인, indexing-research.md 5절). `cindex_speed.py` 가 샤드를 지워 메운다:

| clangd 혼자 | 이 하네스 |
|---|---|
| 헤더가 바뀌면 그 헤더를 포함한 TU 중 **하나만** 다시 색인 (Background.cpp FIXME) | 샤드의 include 그래프 + 명령의 `-include`/`/FI` 로 포함한 TU 를 **모두** 다시 |
| 컴파일 플래그가 바뀌어도 다시 색인 안 함 | compile_commands 항목 해시가 바뀐 TU 를 다시 |
| 한 세션 안에서는 같은 파일을 다시 색인 안 함 | 빌드마다 clangd 를 띄우고 끝나면 닫는다 |
| 다른 TU 의 include 로 이미 샤드가 있던 파일이 TU 가 되면 건너뜀 (유니티 묶음을 풀 때 등) | 그 샤드를 지워 TU 로 다시 |
| mtime 만 바뀌고 내용은 같아도(UHT 가 같은 `.generated.h` 를 다시 씀) — clangd 도 다이제스트라 괜찮다 | 내용 해시로 확인해 무효화하지 않는다 |
| CDB 에서 빠진 TU 의 샤드가 남는다 | include 로 닿지 않는 샤드를 지운다 |

### `--unity N` 의 대가
- 같은 플래그·같은 모듈의 `.cpp` 만 묶는다. TU 마다 다른 응답 파일(`@xxx.rsp`)을 쓰는 데이터베이스면 묶이지 않는다 (출력에 `TU a → a` 로 보인다).
- 파일 범위 이름이 겹치면(두 `.cpp` 에 같은 이름의 `static`·익명 namespace 함수) 묶음이 실패한다 → indexer 는 그 묶음의 원래 TU 를 다시 돌려 합치고,
  bg 는 그 묶음을 풀고 `state.json` 에 기억해 다음부터 묶지 않는다 (둘 다 실험으로 확인).
- 묶음 안 `.cpp` 하나를 고치면 묶음 전체를 다시 색인한다. 익명 namespace 심볼이 빠지거나 `static` 함수 참조가 더 잡힐 수 있다 (연구 실험).
- UE 코드는 원래 UBT 유니티 빌드로 컴파일되도록 쓰이지만, **UE 에서 이 묶음이 clangd 로 깨끗이 파싱되는지는 확인하지 않았다.**

## 4. 조회 명령

프로젝트 루트나 하위에서. 기본은 **있는 인덱스를 모두 같이** 본다 — 프로젝트 범위 + 엔진 범위를 심볼 ID 로 합치고 참조는 위치로 중복을 뺀다
(엔진 TU 의 참조는 엔진 인덱스에만, 프로젝트 TU 의 참조는 프로젝트 인덱스에만 있다). 엔진 클래스도 이름 그대로 묻는다.
`--db engine` / `--db project` 는 그 하나만. 출력은 4KB 에서 끊는다.

| 목적 | 명령 |
|---|---|
| 심볼 좌표 (선언·정의·시그니처) | `cindex.py sym <이름 \| A::B>` |
| 참조 위치 + **그 줄 원문** | `cindex.py refs <이름> [--kind decl\|def\|ref]` |
| 부르는 쪽 (참조의 Container) + 첫 호출 줄 | `cindex.py callers <이름>` |
| 이 함수가 부르는 함수 | `cindex.py callees <이름>` |
| 부모 / 자식 / 재정의 — 끝까지 따라간 트리, 단계별 개수 (`--depth N` 으로 제한) | `cindex.py bases` · `derived` · `overrides <이름>` |
| 멤버와 선언 줄 원문 | `cindex.py members <클래스>` |
| 바꾸면 같이 볼 곳 (파생·재정의 전 단계, 참조 함수, 파일·모듈 — 타입이면 멤버 호출·사용 포함) | `cindex.py impact <이름>` |
| 파일에 선언된 심볼 | `cindex.py file <경로 조각>` |
| 상태·신선도·실패 TU | `cindex.py status` |

- `[E]` 가 붙은 경로는 엔진 루트 기준, 없는 것은 프로젝트 루트 기준.
- 같은 이름이 여럿이면 첫 후보를 쓰고 `# 같은 이름 후보 N개 더` 를 붙인다 → `A::B` 로 좁힌다.
- 이름이 정확히 맞는 심볼이 없으면 **고르지 않는다** — `정확히 일치하는 심볼 없음` 과 비슷한 이름 후보를 보여 준다 (`sym` 은 후보를 그대로 보여 준다).
  예전에는 첫 부분 일치를 답처럼 썼다 (`DoMath1Subsystem` → `UMath1Subsystem1::DoMath1Subsystem1`) — 탐색 비용 A/B 에서 드러나 고쳤다.
- 웹뷰: `python ~/.claude/skills/game-onboard/scripts/index_view.py --open` — 검색·관계·호출·오버라이드·모듈 실사용 그래프.

## 5. 검증

`cindex.py eval` (또는 웹뷰 검증 탭). 기준은 [indexing-research.md](indexing-research.md) 4절.

- **자체 검사**: 좌표가 열까지 맞는가(표본 300), 파일 신선도, 실패 TU, Container 가 기록됐는가.
- **정규식 ↔ clangd 대조**: clangd(컴파일러)를 정답으로 정규식 인덱스의 타입 재현율, 파일·줄 일치, 부모 클래스 일치, 오탐 후보.
- **질의 세트**: `<루트>/.claude/index_eval.json` 의 `{"queries": [{"q", "expect", "root"}]}` 로 Acc@1·Acc@5·MRR.
  파일이 없으면 clangd 정의 위치로 자동 생성하고, 정답을 낸 소스는 채점에서 뺀다.

## 6. 함정

1. **종료 코드 0 이어도 실패할 수 있다.** TU 가 실패해도 0 이다 → `build` 가 stderr 의 `Error while processing` 을 세어 "실패 TU" 로 낸다.
2. **`.generated.h` 누락·낡음이면 UCLASS 타입과 멤버가 조용히 빠진다** (`FID_…_PROLOG` 미정의). 에디터 빌드(UHT) 한 번 뒤 다시 build. `build` 가 경고한다.
3. **멤버 시그니처는 기록되지 않는다** — clangd 는 클래스 멤버에 Signature·ReturnType 을 저장하지 않는다. `members` 는 선언 줄 원문을, 시그니처는 `ue_q.py api` 를 쓴다.
4. **Call 비트는 "호출"이 아니다** — 함수류 심볼에 대한 모든 참조(선언, `&Fn` 포함)에 붙는다. callers/callees 는 Reference 비트 + 참조의 Container 로 계산한 **근사 호출 그래프**다. 호출 관계(relation)는 clangd 에 없다.
5. 기록되지 않는 것: 지역 변수, 매크로 심볼 자체. cpp 안의 `static`·익명 namespace 함수에 대한 참조는 indexer 모드에서 빠지고 bg 모드에는 있다 (배경 색인은 CollectMainFileRefs 를 켠다).
6. `--jobs` 2 이상이면 실행마다 참조 집합이 조금 달라진다 (실험에서 212,709 vs 약 206k). 두 인덱스를 비교하려면 `--jobs 1`.
7. 헤더는 그 헤더에 처음 닿은 TU 기준으로 한 번만 색인된다. 템플릿 인스턴스 안의 참조는 clangd 의 정적 인덱스가 다 잡지 못한다.
8. clangd 23.1.0 은 C++20 concept 심볼을 `Kind: Lang: C` 라는 깨진 YAML 줄로 쓴다 → `--format yaml` 일 때만 `Unmapped(Concept?)` 로 받는다. 기본 RIFF 는 `Concept` 로 바르게 읽는다.
10. RIFF 는 clangd 버전과 묶인 형식이다. 리더(`clangd_riff.py`)는 버전 20(clangd 20.1~23.1, 검증), 19(소스 비교), 21(llvm main, 소스만 보고 짬 — 미검증)을 읽는다. 모르는 버전이면 `--format yaml` 로 돌린다.
11. `--mode bg` 는 오류 줄 수와 `.generated.h` 관련 오류를 세지 못한다 (clangd 로그에 진단이 안 나온다). 샤드의 HadErrors 표시로 "오류 있던 TU" 만 센다 — 0 이 아니면 indexer 모드로 한 번 돌려 원인을 본다.
9. `--filter` 는 LLVM 정규식(POSIX ERE)이라 `(?i)` 같은 플래그가 없다. 기본 필터는 구분자 `/`·`\` 와 드라이브 문자 대소문자를 둘 다 받게 만든다.

## 7. 검증 상태

| 항목 | 상태 |
|---|---|
| clangd-indexer 23.1.0(리눅스)로 가짜 UE 구조(엔진·프로젝트·UCLASS 매크로) 색인 → 적재 → 모든 조회 명령 | 검증됨 (이 저장소 작성 환경) |
| 표준 라이브러리 YAML 파서 = PyYAML (실험 YAML 5종, 문서 5,013개, concept 버그 줄 제외 불일치 0) | 검증됨 |
| 실패 TU·`.generated.h` 누락 감지 | 검증됨 (가짜 프로젝트) |
| 실제 UE 5.x 엔진·프로젝트, Windows, `cindex.py cdb`(UBT) | **검증 안 됨** |
| 실제 UE 규모의 색인 시간·메모리 | **검증 안 됨** (실험 기준 무거운 TU 약 1.2초/코어) |
| RIFF 리더 = YAML 적재 (concept 버그 외 심볼·참조·관계 일치), 옛 YAML 적재 코드와 새 코드 결과 동일 | 검증됨 (합성 175 TU) |
| `--mode bg` 증분: 변경 없음·`.cpp`·헤더·플래그·TU 제거·유니티 전환, 결과 = 처음부터 만든 색인 | 검증됨 (합성 175 TU, 리눅스) |
| `--unity` 결과 = 묶지 않은 색인, 실패 묶음 재색인·풀기 | 검증됨 (합성, 일부러 이름 충돌을 넣어) |
| `--mode bg` 를 Windows·UE 규모(샤드 수만 개)에서 | **검증 안 됨** |
| UE 의 실제 compile_commands 로 `--unity` 묶음이 되는지 (TU 마다 rsp 가 다르면 안 묶인다) | **검증 안 됨** |
| 탐색 비용: 인덱스 CLI 를 더하면 grep 만보다 싼가 (`evals/cost_ab.py`, 같은 모델·과제, 도구만 바꿈) | 합성 픽스처에서 조회 결함 수정 뒤 Sonnet −39%·Opus −38%, 재현율 1.00 (수정 전에는 +17%·−5%). 새 과제 세트·새 시드: Sonnet −38%·Opus −16%(반복 1회). 실제 UE 는 **검증 안 됨** |
