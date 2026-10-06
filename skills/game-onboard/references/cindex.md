# cindex.py — clangd 의미 인덱스 상세

정규식 인덱스(`gq.py`, `ue_q.py`)는 선언 줄만 본다. `cindex.py` 는 clangd-indexer 가 **실제로 컴파일하며** 모은
심볼(함수·메서드·필드 포함, 선언+정의 위치) · 참조(어디서, 어느 함수 안에서) · 관계(상속 BaseOf, 오버라이드 OverriddenBy)를
sqlite 에 담는다. 설계 근거와 검증 기준: [indexing-research.md](indexing-research.md).

## 목차
1. 언제 무엇을 쓰나
2. 준비: clangd-indexer, compile_commands.json
3. 만들기
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

### clangd-indexer
- clangd 공식 릴리스의 indexing tools 압축 파일에 들어 있다. 2026-10 기준 최신 23.1.0:
  `https://github.com/clangd/clangd/releases/download/23.1.0/clangd_indexing_tools-windows-23.1.0.zip` (`clangd-indexer.exe`)
  — 리눅스·맥은 이름의 `windows` 를 `linux`/`mac` 으로. `dexp` 는 어느 배포에도 없다.
- 둘 곳: PATH, `~/.claude/tools/clangd/bin/`, 또는 `--indexer <경로>` / 환경 변수 `CLANGD_INDEXER`.

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

## 3. 만들기

```
python ~/.claude/skills/game-onboard/scripts/cindex.py build                    # 프로젝트 범위 (기본)
python ~/.claude/skills/game-onboard/scripts/cindex.py build --scope engine     # 엔진 범위 (엔진 버전당 한 번)
python ~/.claude/skills/game-onboard/scripts/cindex.py build --cdb <파일|폴더> --jobs 1 --extra-arg=/std:c++20
python ~/.claude/skills/game-onboard/scripts/cindex.py ingest <clangd-indexer YAML>   # 이미 만든 YAML 적재만
```

- 범위는 `--filter`(번역 단위 경로 정규식)로 자른다. 기본: project = 프로젝트 루트 아래 TU, engine = 엔진 루트 아래 TU.
  **프로젝트 범위 인덱스에도 프로젝트가 포함한 엔진 헤더의 심볼이 들어간다** — "내 프로젝트가 쓰는 엔진 API" 를 바로 조회할 수 있다.
- 위치: 프로젝트 `Saved/ClaudeIndex/clangd.sqlite` (UE) · 엔진 `~/.claude/cache/ue_index/<엔진경로>/clangd.sqlite` (ue.sqlite 옆, 프로젝트끼리 공유).
- 엔진은 버전 고정이라 한 번 만들고 둔다. 프로젝트는 구조 작업 전에 다시 만든다 (증분 갱신은 없다 — 7절).
- 세션 시작 훅은 이것을 돌리지 않는다 (컴파일이라 오래 걸린다). `status` 가 `[낡음]` 을 내면 다시 만든다.

## 4. 조회 명령

프로젝트 루트나 하위에서. `--db engine` 으로 엔진 범위 인덱스를, 기본은 프로젝트 범위. 출력은 4KB 에서 끊는다.

| 목적 | 명령 |
|---|---|
| 심볼 좌표 (선언·정의·시그니처) | `cindex.py sym <이름 \| A::B>` |
| 참조 위치 + **그 줄 원문** | `cindex.py refs <이름> [--kind decl\|def\|ref]` |
| 부르는 쪽 (참조의 Container) + 첫 호출 줄 | `cindex.py callers <이름>` |
| 이 함수가 부르는 함수 | `cindex.py callees <이름>` |
| 부모 / 자식 / 재정의 | `cindex.py bases` · `derived` · `overrides <이름>` |
| 멤버와 선언 줄 원문 | `cindex.py members <클래스>` |
| 바꾸면 같이 볼 곳 (파생 3단계, 재정의 3단계, 참조 함수, 파일·모듈) | `cindex.py impact <이름>` |
| 파일에 선언된 심볼 | `cindex.py file <경로 조각>` |
| 상태·신선도·실패 TU | `cindex.py status` |

- `[E]` 가 붙은 경로는 엔진 루트 기준, 없는 것은 프로젝트 루트 기준.
- 같은 이름이 여럿이면 첫 후보를 쓰고 `# 같은 이름 후보 N개 더` 를 붙인다 → `A::B` 로 좁힌다.
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
5. 기록되지 않는 것: cpp 안의 `static`·익명 namespace 함수에 대한 참조, 지역 변수, 매크로 심볼 자체.
6. `--jobs` 2 이상이면 실행마다 참조 집합이 조금 달라진다 (실험에서 212,709 vs 약 206k). 두 인덱스를 비교하려면 `--jobs 1`.
7. 헤더는 그 헤더에 처음 닿은 TU 기준으로 한 번만 색인된다. 템플릿 인스턴스 안의 참조는 clangd 의 정적 인덱스가 다 잡지 못한다.
8. clangd 23.1.0 은 C++20 concept 심볼을 `Kind: Lang: C` 라는 깨진 YAML 줄로 쓴다 → 적재 때 `Unmapped(Concept?)` 로 바꿔 받는다 (상류 수정은 23.1.0 이후).
9. `--filter` 는 LLVM 정규식(POSIX ERE)이라 `(?i)` 같은 플래그가 없다. 기본 필터는 구분자 `/`·`\` 와 드라이브 문자 대소문자를 둘 다 받게 만든다.

## 7. 검증 상태

| 항목 | 상태 |
|---|---|
| clangd-indexer 23.1.0(리눅스)로 가짜 UE 구조(엔진·프로젝트·UCLASS 매크로) 색인 → 적재 → 모든 조회 명령 | 검증됨 (이 저장소 작성 환경) |
| 표준 라이브러리 YAML 파서 = PyYAML (실험 YAML 5종, 문서 5,013개, concept 버그 줄 제외 불일치 0) | 검증됨 |
| 실패 TU·`.generated.h` 누락 감지 | 검증됨 (가짜 프로젝트) |
| 실제 UE 5.x 엔진·프로젝트, Windows, `cindex.py cdb`(UBT) | **검증 안 됨** |
| 실제 UE 규모의 색인 시간·메모리 | **검증 안 됨** (실험 기준 무거운 TU 약 1.2초/코어) |
| 증분 갱신 | 없음 — 프로젝트 범위를 다시 만든다 |
