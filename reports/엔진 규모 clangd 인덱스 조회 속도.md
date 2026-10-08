# 엔진 규모 참조 조회, 빌드 때 미리 접어 두라

우리 측정에서 느린 조회는 거의 전부 **참조가 많은 심볼(이하 핫 심볼)의 참조·개수·호출자 조회**에서 나오며, 원인은 SQLite 의 용량이 아니라 **질의 모양**이다. 기본 경로인 `MultiIndex` 는 두 DB 에서 각각 최대 100만 행을 파이썬으로 끌어와 위치로 중복을 빼고 정렬한 뒤 앞의 60개만 잘라 쓰므로, 참조 340만 개짜리 심볼 하나에 **refs(60) 45.3초, ref_count 41.5초**가 걸렸고 [측정] 같은 상한 때문에 DB 하나에 참조가 100만을 넘는 심볼은 개수도 틀리게 나온다 [코드 확인]. clangd·Kythe·Glean·Sourcegraph 는 이 문제를 같은 네 수로 피한다: 참조를 **그 참조가 있는 파일 기준으로 한 인덱스에만 소속시켜 질의 시 중복 제거를 없애고**, **개수와 호출자 묶음을 빌드 때 계산해 두고**, **(심볼, 파일, 줄) 순서로 저장해 LIMIT 가 앞에서 멈추게 하고**, **기본 응답에 상한과 "더 있음" 표시**를 둔다 [인용]. 우리 프로토타입에서 이 방향의 SQL 수정만으로 members 1,427 → 0.1 ms, file_syms 928 → 6.7 ms, 핫 심볼 호출자 조회 27.9초(전체를 N+1 로 풀던 방식) → 상위 60개 SQL 집계 0.42초가 나왔다 [측정]. 가장 큰 효과는 (1) 즉시 고칠 SQL 세 가지, (2) 엔진 DB 가 참조를 가진 파일은 엔진 DB 만 답하게 하는 **소유권 분할**, (3) 심볼별 개수·호출자 **요약 테이블**, (4) **경로 순 파일 ID** 와 `(sym, file, line)` 인덱스에서 나오고, 웹뷰 클릭 한 번을 Google Code Search 가 쓰는 200 ms 목표 안에 넣는 데 필요한 것도 이 넷이다 [추론]. 부분 문자열 검색용 FTS5 trigram 은 효과가 확실하지만(147.9 ms → 0–7 ms) 지금 느린 경우가 일치 없는 검색 하나뿐이라 그다음 순위다. 모든 수치는 실제 UE 가 아닌 **합성 DB(심볼 100만·참조 1천만)** 에서 잰 것이고, 실제 UE 엔진 인덱스의 크기와 소유권 분할로 잃는 참조 수는 아직 재지 않았다.

**표기 규칙**

| 표기 | 뜻 |
|---|---|
| **[측정]** | 우리 합성 벤치마크(Linux, SQLite 3.45.1, Python sqlite3) |
| **[조사 실험]** | 조사 과정에서 한 별도 로컬 실험(참조 400만, 핫 심볼 120만, 같은 SQLite 3.45.1) |
| **[코드 확인]** | `skills/game-onboard/scripts/cindex.py` 를 직접 읽은 사실 |
| **[인용]** | 외부 출처(링크 첨부) |
| **[추론]** | 위 근거로 내린 판단. 측정하지 않았다 |

## 1. 340만 참조 심볼이 45초를 먹는 이유: 끌어와서 정렬한다

### 1.1 MultiIndex 경로

`MultiIndex.refs()` 는 프로젝트 DB 와 엔진 DB 에 각각 `ix.refs(sid, mask, 1_000_000)` 를 부른다(`cindex.py` L1088–1097) [코드 확인]. 받은 결과는 `(path, line, col, kind)` 키로 중복을 빼고, 파이썬에서 정렬한 뒤 자른다. 다른 세 함수도 같은 목록에 기댄다.

| 함수 | 하는 일 |
|---|---|
| `ref_count()` | 위 결과의 `len()` 을 센다 |
| `callers()` | 같은 목록을 다시 가져와 파이썬 dict 로 센다 |
| `caller_sites()` | 같은 목록을 다시 가져와 파이썬 dict 로 센다 |

그래서 화면에 60개만 보여도 **비용은 심볼의 전체 참조 수에 비례**한다.

| MultiIndex 질의 | 참조 965 | 참조 28,212 | 참조 3,401,559 |
|---|---|---|---|
| refs(60) | 16.6 ms | 376.6 ms | **45,255 ms** |
| ref_count | 10.1 ms | 359.4 ms | **41,451 ms** |
| caller_sites(20) (CLI `callers`) | 11.3 ms | 352.5 ms | **41,518 ms** |
| callers()[:60] (웹뷰) | 48.4 ms | 1,401.5 ms | 미측정 |

[측정, 같은 DB 를 두 번 붙여 잰 값]

웹뷰 심볼 상세(`detail`, L1361–1386)는 클릭할 때마다 `callers(sid)`(전체 호출자를 하나씩 `by_id` 로 푼 뒤 앞의 60개를 자름), `callees`, `refs(sid, None, 60)`, `ref_count(sid)` 를 차례로 부른다 [코드 확인]. 측정값을 더하면 클릭 한 번에 걸리는 시간은 다음과 같다.

| 심볼의 참조 수 | 클릭 한 번 (측정값의 합) |
|---|---|
| 965 | 약 75 ms |
| 28,212 | 약 2.1초 |
| 340만 | callers 를 빼고도 약 87초 |

사용자 지연의 고전적 경계는 셋이다: 0.1초는 즉각 반응으로 느끼는 한계, 1초는 생각의 흐름이 끊기지 않는 한계, 10초는 주의를 붙잡아 두는 한계다 ([Nielsen](https://nngroup.com/articles/response-times-3-important-limits)). Google Code Search 팀은 더 엄격하게 "자주 쓰는 모든 동작은 종단 간 200 ms 미만"을 목표로 잡고, 서버 측 검색 중앙값 50 ms 미만을 달성했다 ([Software Engineering at Google, 17장](https://abseil.io/resources/swe-book/html/ch17.html)). 우리는 참조 2.8만 개짜리 심볼에서 이미 1초 선을 넘는다.

### 1.2 단일 DB 경로

| 단일 DB 질의 | 측정 | 원인 |
|---|---|---|
| find 정확 일치(클래스) | 0.0 ms | qname·name 인덱스 |
| find 정확 일치 `BeginPlay` | 36.5 ms | 같은 이름의 심볼이 많아 전부 돌려주고 순위를 매긴다 |
| fuzzy `Montage` (흔한 문자열) | 8.0 ms | `LIKE '%x%'` 지만 LIMIT 를 일찍 채우고 끝난다 |
| fuzzy `Zzqx` (일치 없음) | **147.9 ms** | 심볼 테이블 전체를 훑는다 |
| members | **1,426.9 ms** | `WHERE scope=?` 에 쓸 인덱스가 없다 |
| file_syms | **927.8 ms** | `LEFT JOIN files … WHERE df.rel LIKE` 가 조인 순서를 고정한다 |
| refs / callers (참조 55개 심볼) | 0.1 / 0.9 ms | 짧은 인덱스 범위 읽기 |
| refs (핫 심볼, limit 500) | **4,035.7 ms** | `ORDER BY f.rel, r.line` 때문에 340만 행을 정렬한다 |
| callers (핫 심볼) | **27,910.5 ms** | 호출자 966,535개를 하나씩 `by_id` 로 조회한다(N+1) |
| callees / derived | 0.0 ms | |
| `import cindex` | 33 ms | |

[측정]

### 1.3 원인 해부

원인은 서로 다르지만 모두 문서화된 동작으로 설명된다.

**정렬.** `ORDER BY f.rel` 은 조인한 뒤 얻는 경로 문자열의 순서다. 어떤 인덱스도 이 순서를 미리 만들어 두지 못한다. 그래서 SQLite 는 결과 전체를 임시 인덱스에 넣어 정렬한 뒤에야 첫 행을 내보내고, LIMIT 가 있어도 일찍 멈추지 못한다 ([SQLite Temporary Files §2.8](https://www.sqlite.org/tempfiles.html)).

**file_syms.** SQLite 는 외부 조인의 테이블 순서를 바꾸지 않는다. LEFT JOIN 을 일반 조인으로 낮추는 증명기도 "때로 거짓 음성을 낸다"고 문서에 적혀 있다 ([SQLite optimizer §16](https://www.sqlite.org/optoverview.html#the_outer_join_strength_reduction_optimization), [§7.1.2](https://www.sqlite.org/optoverview.html#manual_control_of_query_plans_using_cross_join)). 그래서 ANALYZE 를 돌려도 993 ms 였고, 질의를 다시 쓰자 6.7 ms 가 됐다 [측정].

**callers.** 우리 코드는 호출자마다 질의를 하나씩 보낸다. clangd 의 `incomingCalls` 는 참조를 컨테이너별로 묶은 뒤 **모든 컨테이너 ID 를 한 번의 `LookupRequest` 로** 조회한다 ([clangd XRefs.cpp L2573–2650](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/XRefs.cpp#L2573-L2650)).

**중복 제거.** 중복 제거를 SQL 로 옮겨도 해결되지 않는다. ATTACH 후 `UNION` + `GROUP BY` + `LIMIT 60` 으로 정확히 중복을 빼 보았다.

| 심볼의 참조 수 | 소요 시간 [측정] |
|---|---|
| 2.8만 | 202.5 ms |
| 340만 | **24,397 ms** |

`UNION` 은 양쪽 결과를 모두 임시 인덱스에 넣으면서 중복을 버리는 방식으로 구현되어 있다 ([SQLite Temporary Files §2.8](https://www.sqlite.org/tempfiles.html)). 위치로 중복을 빼는 방식은 정확성도 보장하지 못한다. clangd 소스에는 "오프셋이 조금씩 다를 수 있어 믿을 만하게 중복을 뺄 수 없다"는 주석이 있다 ([clangd Merge.cpp L125–156](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L125-L156)). **질의할 때 정확히 중복을 빼는 것은 막다른 길이다.**

### 1.4 같은 패턴을 쓰는 다른 경로

다른 두 경로도 같은 패턴을 쓴다. `impact`(L1195–)는 타입과 그 타입의 모든 멤버마다 100만 행 상한으로 참조를 가져온다. 웹뷰 호출 그래프는 BFS 의 노드마다 전체 `callers()` 를 부른다(L1409–1410) [코드 확인, 미측정]. `UObject`·`AActor` 처럼 멤버가 많은 타입에서는 위 표보다 나쁠 것이다 [추론].

### 1.5 핫 심볼은 구조적 현상이다

핫 심볼은 우연한 예외가 아니다. 소프트웨어에서 들어오는 의존(=참조받는 쪽)의 분포는 지수 약 2의 거듭제곱 법칙에 잘 맞는다 ([Louridas et al., TOSEM 2008](https://www.spinellis.gr/pubs/jrnl/2008-TOSEM-PowerLaws/html/LSV08.html)). 조사 노트는 이 지수로 계산해, 상위 0.1–1% 심볼이 전체 참조의 과반을 가질 수 있다고 추정했다 [추론]. 다만 C++ 의 심볼 단위 참조 분포는 공개된 자료가 없으므로, UE 에서의 실제 모양은 우리가 직접 재야 한다.

## 2. 네 시스템은 같은 네 가지 수로 핫 심볼을 피했다

| 기법 | 누가 어떻게 [인용] | 우리 설계에 옮기면 |
|---|---|---|
| **위치 파일 단위 소유, 질의 시 중복 제거 없음** | **clangd `MergedIndex`**: 우선순위가 높은 인덱스의 참조는 모두 낸다. 낮은 인덱스의 참조는 높은 쪽이 참조까지 색인한 파일(`indexedFiles(file) & IndexContents::References`)이 **아닐 때만** 낸다 ([Merge.cpp](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L125-L156), [Index.h L108–120](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Index.h#L108-L120)).<br>**clangd 배경 색인**: 참조를 그 참조가 있는 파일의 샤드에 넣는다 ([FileIndex.cpp](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/FileIndex.cpp#L127-L181)).<br>**woboq**: 파일을 처음 처리한 TU 가 그 파일을 소유한다 ([projectmanager.cpp](https://github.com/woboq/woboq_codebrowser/blob/ebe91a86e4d06a23f5f7709d081f83e2cc14ef26/generator/projectmanager.cpp#L77-L88)).<br>**Glean**: 소유 단위(파일) slice 비트맵으로 기반 DB 의 사실을 가린다 ([incrementality.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/incrementality.md)).<br>**Sourcegraph**: `SkipPathsByUploadID` 로 경로 단위 제외 ([types.go](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/types.go#L148-L171)) | 엔진 DB 가 참조를 가진 파일은 엔진 DB 만 답한다. 그러면 결과는 이어 붙이기만 하고 개수는 더하기만 하면 된다 |
| **빌드 때 집계** | **Kythe**: 노드마다 페이지별 개수(`PageIndex.count`), 총계(`Total`), 미리 묶은 `Caller` 그룹을 저장한다 ([serving.proto](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/proto/serving.proto#L265-L379)). 컬럼형 형식은 `20-caller` 키를 쓴다 ([xref_serving.proto](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/proto/xref_serving.proto#L142-L215)).<br>**Glean**: find-references 용 `TargetUses` 를 저장형 파생 술어로 미리 만든다 ([derived.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/derived.md), [cxx.angle](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/schema/source/cxx.angle#L641-L700)).<br>**clangd Dex**: 컨테이너 순으로 정렬한 `RevRefs` 를 적재할 때 만든다 ([Dex.cpp L152–163](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/dex/Dex.cpp#L152-L163)) | `sym_stats`·`sym_callers`·`sym_modules` 요약 테이블 |
| **접근 순서 = 저장 순서** | **Glean**: "키 접두로 색인하므로 필드 순서가 O(log n) 와 O(n) 을 가른다" ([efficiency.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/angle/efficiency.md)).<br>**Kythe**: 컬럼형으로 바꾸며 "조회가 키 접두 스캔이 되고 페이지 나누기가 쉬워진다" ([RFC 2909](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/docs/rfc/2909.md)).<br>**clangd Dex**: 심볼별 연속 배열을 limit 까지만 훑는다 ([Dex.cpp L315–329](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/dex/Dex.cpp#L315-L329)) | 경로 순 file ID, `(sym, file, line)` 인덱스, keyset 페이지 나누기 |
| **상한 + 더 있음 + 커서** | **clangd**: 참조 기본 1000(`--limit-references`) + `HasMore` ([ClangdMain.cpp](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/tool/ClangdMain.cpp#L317-L330)). 원격 서버는 요청당 10000 ([Server.cpp](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/remote/server/Server.cpp#L108-L112)).<br>**Kythe**: 페이지 기본 2048·최대 10000, 기본은 근사 총계, 50 ms 여유 시간 ([xrefs.go](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/go/serving/xrefs/xrefs.go#L293-L294)).<br>**Glean**: `max_results`·`max_bytes`·`max_time_ms` + continuation ([glean.thrift](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/if/glean.thrift#L419-L448)) | 기본 응답 = 총계 + 묶음 + 상위 N + `truncated` + 커서 |

### 2.1 이미 반쯤 와 있다

우리 적재기는 이미 첫 번째 원칙을 따른다. `riff_records()` 주석에 "참조는 샤드마다 그 위치의 파일이 주인이라 겹치지 않는다"고 적혀 있다(L388–390) [코드 확인]. 즉 한 DB 안에서는 clangd 배경 색인의 파일별 소유 덕분에 중복이 없다. 중복은 **두 DB 가 같은 엔진 헤더 샤드를 각각 가질 때만** 생긴다. 파일 단위 분할은 바로 그 중복만 정확히 없앤다 [추론].

### 2.2 핫 노드는 어디서나 문제였다

Kythe 는 거대한 xref 집합이 "hot shard 와 straggler 를 만들고 메모리 고갈로 실패"하게 한다는 이유로 저장 형식을 바꿨다 ([RFC 2909](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/docs/rfc/2909.md)). GitHub 는 2026년 2월, 질의 하나가 hot shard 에 부하를 몰아 전체 검색이 느려지는 장애를 겪었다 ([GitHub status](https://www.githubstatus.com/incidents/jn8kcmg5ydch)).

### 2.3 정확한 총계는 필수가 아니다

clangd 는 심볼별 참조 개수를 아예 제공하지 않는다. `Symbol::References` 는 참조 개수가 아니라 그 심볼을 참조한 TU 수다. 응답에는 `HasMore` 만 붙인다 ([Symbol.h](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Symbol.h#L72-L74)). Kythe 도 기본값은 근사 총계다. 우리 DB 는 한 번 빌드하고 읽기만 하므로 정확한 총계를 미리 계산하는 비용이 작다. 그러니 정확한 총계를 주되, **질의할 때 세지는 않는 쪽**이 맞다 [추론].

## 3. 개선안: 효과 큰 순서

### 3.1 [P0] 바로 고칠 SQL 세 가지와 실행 계획 고정

**바꿀 것.** **members** 에는 `symbols(scope)` 인덱스를 추가한다. **file_syms** 는 `LEFT JOIN … WHERE df.rel LIKE ?` 를 `WHERE s.decl_file IN (SELECT id FROM files WHERE rel LIKE ?)` 로 다시 쓴다. **callers** 는 `GROUP BY container ORDER BY COUNT(*) DESC LIMIT ?` 로 집계하고, 이름은 `symbols` 와 한 번 JOIN 하거나 `IN (…)` 한 번으로 가져온다. 웹뷰 `detail` 과 호출 그래프도 `callers()[:60]` 대신 이 제한판을 부르게 한다. 여기에 두 가지를 더한다. 빌드 마지막에 `ANALYZE` 를 넣고(지금 `ingest()` 에는 없다 [코드 확인]), 웹뷰 `find` 가 `%x%` 로 가기 전에 접두 일치(`name LIKE 'x%'`)를 먼저 시도하게 한다.

**효과 [측정].**

| 대상 | 전 | 후 | 비고 |
|---|---|---|---|
| members | 1,426.9 ms | 0.1 ms | 인덱스 빌드 0.7초 |
| file_syms | 927.8 ms | 6.7 ms | |
| 핫 심볼 callers | 27.9초 (전체, N+1) | 2,723.5 ms (`refs(sym)` 만, 상위 60 집계) | |
| 핫 심볼 callers | 27.9초 (전체, N+1) | 421.3 ms (커버링 `refs(sym, container, kind)`) | |
| 2.8만 참조 심볼 callers | 54.4 ms (`refs(sym)`) | 5.8 ms (커버링) | |
| 접두 일치 `GetAbility%` | — | 0.2 ms | NOCASE 인덱스 범위 스캔 |

**근거.** 필요한 열이 모두 인덱스에 있으면 SQLite 는 "원래 행을 찾아가지 않으며 많은 질의가 두 배 빨라진다" ([SQLite optimizer §9](https://www.sqlite.org/optoverview.html#covering_indexes)). 호출자 이름의 일괄 조회는 clangd `incomingCalls` 와 같은 방식이다.

**위험·검증.** 커버링 인덱스 `refs(sym, container, kind)` 는 446 MB 다 [측정]. 크기보다 더 큰 문제는 이 인덱스를 **`refs(sym, file, line)` 없이** 넣었을 때 정렬된 refs 질의가 3,933 ms 에서 **11,630 ms 로 오히려 느려졌다**는 점이다 [측정]. 조사 노트의 설명은 이렇다. 두 인덱스는 `sym=?` 조건에 대해 문서의 비용 모델 `(K+1)·logN` 상 동점이고 ([SQLite Query Planning](https://www.sqlite.org/queryplanner.html)), stat1 의 첫 열 통계도 같아서 ANALYZE 로 둘을 구별할 수 없다. 그런데 넓은 인덱스로 가면 테이블 행을 컨테이너 순서로 찾아가게 되어 페이지 접근이 무작위가 된다. 조사 실험에서 같은 실행 계획에 그 인덱스를 강제했더니 7.6배 느려졌다 [조사 실험]. 그래서 3.3의 요약 테이블을 만들 계획이면 이 커버링 인덱스는 넣지 말고, 그때까지는 `refs(sym)` 판(2.7초)을 쓰는 편이 낫다.

소유권 분할 전에 `MultiIndex` 에서 두 DB 의 GROUP BY 결과를 합칠 때는 컨테이너별로 **합 대신 최댓값**을 취한다. 공유 헤더 때문에 같은 참조를 두 번 세는 것을 피하기 위해서다. 지금 `callees` 가 이미 이렇게 한다. 함수 본문은 한 파일에 있으므로 대체로 맞지만, 근사다 [추론].

실행 계획은 **EXPLAIN QUERY PLAN 문자열을 단언하는 테스트**로 고정한다. 사용자의 Windows python.org 빌드는 Python 버전에 따라 SQLite 3.35.5–3.53.4 를 번들하고 ([태그별 PCbuild/python.props](https://github.com/python/cpython/blob/3.14/PCbuild/python.props)), 그 사이에 3.45.0 의 "ANALYZE 가 저품질로 판정한 인덱스를 더 잘 무시", 3.46.1 의 "커버링 인덱스 예측 개선" 같은 플래너 변경이 있었다 ([SQLite changes](https://www.sqlite.org/changes.html)). Linux 3.45.1 에서 본 계획이 그대로라고 가정하면 안 된다.

### 3.2 [P1] 소유권 분할: 엔진 DB 가 가진 파일은 엔진 DB 만 답한다

**바꿀 것: 빌드.** 프로젝트 DB 를 만들 때 엔진 DB 를 ATTACH 하고, "엔진 DB 에 참조가 하나라도 있는 파일"의 정규화 경로 집합을 구한 뒤, 프로젝트 DB `refs` 에서 그 파일에 있는 행을 지운다. 지우는 대신 `files` 에 소유 표시만 남겨도 된다. 엔진 DB 의 빌드 식별값은 프로젝트 DB `meta` 에 적어 둔다. 엔진 DB 가 다시 빌드되면 분할을 다시 돌리고, 식별값이 어긋나 있으면 질의할 때 파일 필터로 대신한다.

**바꿀 것: 질의(`MultiIndex`).** refs 는 clangd `findReferences` 처럼 남은 몫만 차례로 채운다 ([XRefs.cpp L1838–1857](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/XRefs.cpp#L1838-L1857)). 프로젝트 DB 에서 먼저 `ORDER BY … LIMIT n` 으로 받고, 모자라면 엔진 DB 에서 받고, 다 차면 멈추고 `has_more` 를 돌려준다. ref_count 는 두 DB 의 개수를 더하고, callers 는 두 DB 의 상위 목록을 개수 기준으로 합친다. 파이썬 쪽 중복 제거와 100만 행 상한은 없앤다.

**근거.** clangd 의 규칙이 그대로 이것이다. 주석은 "dynamic 인덱스를 권위로 보고 그 참조를 모두 내보내며, static 인덱스 참조는 다른 파일의 것만 낸다"고 적고 있다 ([Merge.cpp L125–156](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L125-L156)). 판정 기준이 중요하다. 경로 접두("엔진 폴더 아래")가 아니라 "**그 인덱스가 실제로 색인한 파일**"이어야, 엔진 TU 는 아무도 열지 않았지만 프로젝트 TU 는 연 엔진 헤더(생성 헤더, 엔진 인덱스에서 실패한 TU 만 포함하던 헤더 등)의 참조가 살아남는다. Glean 의 stacked DB 도 기반 DB 를 고치지 않고 소유 단위로 가린다 ([incrementality.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/incrementality.md), [stacked.h](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/rts/stacked.h#L20-L60)). 프로젝트 결과를 먼저 내는 순서는 clangd 가 작고 최신인 dynamic 인덱스를 먼저 묻는 것과 같고, UE 개발자가 가장 먼저 보고 싶은 자기 게임 코드의 사용처와도 맞는다.

**효과.** 이 변경 뒤 MultiIndex 의 비용은 "DB 별 LIMIT 질의의 합"이 된다. 단일 DB 에서 핫 심볼(340만)로 잰 값은 다음과 같다 [측정].

| 질의 | 단일 DB 측정 |
|---|---|
| 정렬 LIMIT 60 | 206–498 ms |
| COUNT(*) | 128.6 ms |
| 호출자 상위 60 (커버링) | 421.3 ms |

따라서 3.3–3.4 를 적용하기 전에도 45초가 1초 안팎이 되고, 적용 뒤에는 수 ms 대가 된다고 본다 [추론]. 100만 상한 때문에 개수가 잘리는 오류도 구조적으로 사라진다. 프로젝트 TU 가 끌어들인 엔진 헤더 참조가 빠지므로 프로젝트 DB 도 작아질 것이다 [추론, 미측정].

**비용.** 프로젝트 DB 빌드에 엔진 DB 와 대조하는 처리가 한 번 더 들어간다. 시간은 재지 않았다.

**위험·검증.** 가장 큰 위험은 **프로젝트 TU 에서만 보이는, 엔진 소유 파일 안의 참조**다. 빌드 구성 차이(`WITH_EDITOR` 같은 매크로, 엔진 인덱스와 프로젝트 인덱스의 타깃 차이)나 템플릿·매크로 전개 때문에 같은 엔진 헤더라도 두 TU 가 본 참조가 다를 수 있다 [추론]. clangd 는 이 차이를 감수하고 권위 쪽을 믿는다. 우리는 실제 UE 데이터에서 규모를 잰 뒤에 정해야 한다.

```sql
-- 프로젝트 DB 를 main 으로 열고 엔진 DB 를 붙인다 (일회성 검증)
ATTACH 'engine.db' AS e;
CREATE TEMP TABLE owned AS
  SELECT DISTINCT f.path FROM e.refs r JOIN e.files f ON f.id = r.file;
-- (1) 분할하면 프로젝트 DB 에서 빠질 행 수
SELECT COUNT(*) FROM refs r JOIN files f ON f.id = r.file
 WHERE f.path IN (SELECT path FROM owned);
-- (2) 그중 엔진 DB 에 같은 (심볼, 파일, 줄, 열) 이 없는 행 = 실제로 잃는 참조
SELECT COUNT(*) FROM refs r JOIN files f ON f.id = r.file
 WHERE f.path IN (SELECT path FROM owned)
   AND NOT EXISTS (SELECT 1 FROM e.refs r2 JOIN e.files f2 ON f2.id = r2.file
                    WHERE r2.sym = r.sym AND f2.path = f.path
                      AND r2.line = r.line AND r2.col = r.col);
```

(2)를 심볼 종류와 파일별로 나눠 보면, 손실이 매크로·템플릿 때문인지 빌드 구성 때문인지 드러난다. 손실이 작으면 그대로 분할한다. 크면 해당 파일만 예외로 두고, 그 파일에 한해 두 DB 를 모두 읽어 위치로 중복을 뺀다.

경로 대소문자는 이미 막혀 있다. `norm()` 이 Windows 에서 경로를 소문자로 바꾼다(L154–156) [코드 확인]. 엔진 DB 를 다른 경로의 설치본으로 만들어 쓰는 경우는 따로 확인해야 한다.

### 3.3 [P1] 개수와 호출자를 빌드 때 계산해 둔다

**바꿀 것.** 3.2의 분할을 마친 뒤 빌드 마지막에 요약 테이블 셋을 만든다.

| 테이블 | 내용 | 비고 |
|---|---|---|
| `sym_stats` | `sym` PK, `n_refs`, `n_files`, `n_callers`, 종류별 개수 | `WITHOUT ROWID` 가능 |
| `sym_callers` | `sym`, `container`, `n`, `first_file`, `first_line` | 인덱스 `(sym, n DESC)` |
| `sym_modules` | `sym`, `module`, `n` | |

참조 종류의 비트 검사(`kind & ?`)는 인덱스를 쓸 수 없다. 그래서 호출·읽기·선언처럼 종류 묶음별로 따로 센다.

한 심볼에 호출자가 너무 많으면 `row_number() OVER (PARTITION BY sym ORDER BY n DESC) <= K` 로 상위 K 개만 남긴다. 나머지는 "기타" 한 행으로 합쳐 총계를 보존한다 ([SQLite 윈도 함수, 3.25.0+](https://www.sqlite.org/windowfunctions.html)).

웹뷰 `detail`, CLI `callers`, `impact`, 호출 그래프가 모두 이 테이블을 읽게 바꾼다.

**근거.** 2절의 Kythe `PageIndex.count`·`Total`·`Caller` 그룹, Glean 저장형 파생 술어, clangd `RevRefs` 가 모두 같은 원리다. 질의할 때 하던 집계를 빌드로 옮긴다.

**효과.**

조사 실험(참조 400만, 핫 심볼 120만)에서 호출자 상위 60 조회 시간은 다음과 같았다 [조사 실험].

| 방식 | 시간 |
|---|---|
| 테이블 스캔 | 708 ms |
| 커버링 인덱스 | 111 ms |
| 요약 테이블 | **~0 ms** |

요약 테이블 생성에는 2.2초가 걸렸다 [조사 실험].

우리 DB 에서 MultiIndex `ref_count` 41.5초와 단일 DB `COUNT(*)` 128.6 ms 는 기본키 조회 한 번이 된다. 짧은 범위 읽기인 정확 일치 find 가 0.0 ms 였으므로 1 ms 미만으로 본다 [추론]. 3.1의 446 MB 커버링 인덱스와 그 실행 계획 함정도 필요 없어진다.

**비용.** 우리 1천만 참조 DB 에서의 빌드 시간과 디스크는 재지 않았다. 디스크는 서로 다른 (심볼, 컨테이너) 쌍 수에 비례한다. 핫 심볼 하나만 96만 행이므로, 상위 K 절단을 기본으로 둔다.

**위험.** 분할 전에 집계하면 개수가 두 번 세어진다. 빌드 순서를 확인하는 테스트가 필요하다.

### 3.4 [P1] 정렬은 인덱스에 맡긴다

**바꿀 것.** 적재가 끝나면 `files` 의 ID 를 `(root, rel)` 경로 순서로 다시 매긴다(지금 `FileTable` 은 처음 본 순서로 ID 를 준다 [코드 확인]). 그 위에 `refs(sym, file, line)` 인덱스를 두고, `ORDER BY f.rel` 을 `ORDER BY r.file, r.line, r.col` 로 바꾸고, 다음 페이지는 OFFSET 대신 keyset 조건 `(r.file, r.line, r.col) > (?, ?, ?)` 로 가져온다. `refs(sym)` 은 새 인덱스의 접두로 대체되므로 지울 수 있다. 재번호를 매기면서 `refs` 를 `(sym, file, line)` 순서로 다시 써 두면 테이블 행 접근도 순차가 된다 [추론].

**근거.** SQLite 공식 문서는 OFFSET 이 "오프셋에 비례하는 시간"을 쓴다고 하고, 행 값 비교로 페이지를 넘기라고 권한다 ([SQLite Row Values §3.1](https://www.sqlite.org/rowvalue.html#scrolling_window_queries)). Kythe 컬럼형 키 `00-kind-file-start-end` 도 같은 "심볼 접두 + 위치 순" 배치다.

**효과.**

| 실험 | 결과 | 출처 |
|---|---|---|
| 핫 심볼 정렬 LIMIT 60, `refs(sym, file, line)` 추가 | 3,933 ms → 498 ms | [측정] |
| 파일 목록부터 구하는 두 단계 방식 | 206 ms | [측정] |
| 경로 순 ID 추가 (참조 120만 심볼) | 0.36–0.41초 → **~0 ms**. 실행 계획에서 `USE TEMP B-TREE FOR ORDER BY` 가 사라졌다 | [조사 실험] |
| keyset 으로 100만 번째 위치 조회 | ~0 ms (OFFSET 은 51 ms) | [조사 실험] |

경로 순 ID 를 우리 1천만 DB 에서 재지는 않았다.

**비용.** `refs(sym, file, line)` 은 +317 MB 다 [측정]. `refs(sym)` 을 지우면 −253 MB 가 되지만 실행 계획 확인이 필요하다 [추론]. 재번호와 재작성 시간은 재지 않았다.

**위험.** 3.1의 실행 계획 함정이 바로 이 지점에서 생긴다. 이 인덱스를 넣을 때는 EQP 단언 테스트를 반드시 함께 넣는다. 최후 수단은 `INDEXED BY` 다. SQLite 는 이를 성능 조정용으로 쓰지 말라고 하지만, 지정한 인덱스가 없으면 질의 준비 단계에서 바로 실패하므로 빌드를 한 번만 하는 DB 에서는 쓸 만하다 ([SQLite INDEXED BY](https://www.sqlite.org/lang_indexedby.html)).

### 3.5 [P2] 부분 문자열 검색은 FTS5 trigram, 범위는 좁게

**바꿀 것.** 검색 순서를 정확 일치 → 접두 일치(0.2 ms) → trigram 부분 일치 → (3자 미만이면) LIMIT 스캔으로 둔다. trigram 테이블은 별도 파일로 두고 처음에는 **name 열만, `detail=none`** 으로 만든다. 약어 검색(`GAP` → `GetAbilityPointer`)을 위해 머리글자 열과 B-tree 인덱스를 추가한다. 실행할 때 TEMP FTS5 trigram 테이블을 만들어 보고, 지원되지 않으면 기존 경로로 물러난다.

**근거.** clangd Dex 는 CamelCase 경계를 건너뛰는 trigram 역색인을 쓰고 ([Trigram.h](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Trigram.h)), Russ Cox 의 Code Search 와 Zoekt 도 n-gram 색인 뒤에 후보 검증을 둔다 ([Zoekt design](https://github.com/sourcegraph/zoekt/blob/main/doc/design.md)). FTS5 trigram 은 SQLite 3.34.0 부터 있다 ([fts5_tokenize.c @3.34.0](https://github.com/sqlite/sqlite/blob/version-3.34.0/ext/fts5/fts5_tokenize.c)). LIKE 조건을 FTS5 가 받아도 SQLite 코어가 후보마다 LIKE 를 다시 평가하므로 결과는 정확하다 ([fts5_main.c](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_main.c)). 와일드카드 사이 리터럴이 3자 미만이면 색인을 쓰지 못한다 ([fts5_expr.c](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_expr.c)). python.org Windows 빌드는 3.10–3.15 모두 `SQLITE_ENABLE_FTS5` 로 컴파일되고 번들 SQLite 의 최저 버전도 3.35.5 다. 공식 NuGet 패키지의 `sqlite3.dll` 에서 FTS5·trigram 문자열을 직접 확인했다 ([CPython sqlite3.vcxproj](https://github.com/python/cpython/blob/3.14/PCbuild/sqlite3.vcxproj), [NuGet python](https://api.nuget.org/v3-flatcontainer/python/index.json)).

**효과.**

| 방식 | 효과 | 비용 | 출처 |
|---|---|---|---|
| name+qname, `detail=full` | 부분 문자열 질의 3.8–230 ms → 0–7 ms | +216 MB, 빌드 11.5초 | [측정] |
| name 전용, `detail=none` | LIKE 정확성 그대로 | 1M 심볼에 +31.7 MB | [조사 실험] |
| 머리글자 열 + B-tree | 0.09 ms | +12.9 MB, 빌드 2.4초 | [조사 실험] |

**위험.** 2자 리터럴(`%ab%`)은 FTS 를 거치면 일반 스캔보다 느렸다(242–313 ms 대 137–169 ms) [조사 실험]. SQLite 3.47 미만에서는 tokenizer 옵션 문자열이 잘못되면 프로세스가 죽으므로 옵션은 상수로만 쓴다 ([fts5_tokenize.c @3.47.0](https://github.com/sqlite/sqlite/blob/version-3.47.0/ext/fts5/fts5_tokenize.c)).

**P2 인 이유.** 지금 느린 경우는 일치 없는 검색(147.9 ms, MultiIndex 는 두 DB 몫) 하나뿐이다. 또 에이전트는 위치를 찾을 때 시맨틱 도구를 거의 쓰지 않고(0–6%) grep 을 쓴다 ([arXiv 2608.13568](https://arxiv.org/abs/2608.13568)). 이득은 주로 웹뷰에 간다.

### 3.6 [P3] 저장 압축과 실행 설정은 나중에

**정수화.** 16자 hex TEXT 인 `sym`·`container` 를 INTEGER 로 바꾸면 조사 실험(참조 400만)에서 `(sym)` 인덱스가 56%, `(sym, file, line)` 인덱스가 45% 줄었다 [조사 실험]. SQLite 는 정수를 1–8 바이트 가변 길이로 저장한다 ([SQLite file format](https://www.sqlite.org/fileformat2.html#record_format)). 다만 모든 질의와 적재를 바꾸는 스키마 전면 변경이다.

**(심볼, 파일) → 델타+varint 블롭.** Glean `TargetUses`, Sourcegraph `codeintel_scip_symbols`, GNU GLOBAL GRTAGS 가 각자 따로 도달한 형태다 ([Sourcegraph schema](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/migrations/codeintel/squashed.sql#L238-L248), [GLOBAL gtagsop.c](https://github.com/harai/gnu-global/blob/f86ba74d867385353815f8656c4a6cf4029c1f0b/libutil/gtagsop.c#L134-L200)). 행 수가 파일 수 수준으로 준다. 하지만 Sourcegraph 는 "위치 단위로 LIMIT+OFFSET 을 쓸 수 없어 전부 가져와 푼다"고 적었다 ([locations_by_position.go](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/internal/lsifstore/locations_by_position.go#L315-L407)). 파이썬에서 디코딩하는 비용도 있으므로 디스크가 실제로 문제가 될 때만 검토한다.

**두 DB 병렬 질의.** CPython 은 `sqlite3_step` 동안 GIL 을 놓는다 ([cursor.c](https://github.com/python/cpython/blob/main/Modules/_sqlite/cursor.c)). 연결 두 개를 두 스레드로 돌리면 무거운 집계가 1.88배 빨랐다 [조사 실험]. 하지만 P1 이후에는 질의가 ms 단위라 얻을 것이 적다.

**mmap·cache_size.** Linux 에서 OS 캐시가 데워진 상태로는 효과가 없었다 [조사 실험]. mmap 상한은 약 2 GiB 다 ([SQLite mmap](https://www.sqlite.org/mmap.html)). Windows 에서는 따로 재야 한다.

## 4. 로드맵

| 순위 | 변경 | 근거 [인용] | 효과 | 비용 | 위험·검증 |
|---|---|---|---|---|---|
| P0-1 | `symbols(scope)` 인덱스 | B-tree 동등 검색 | members 1,426.9 → 0.1 ms [측정] | 빌드 0.7초 [측정] | Windows SQLite 에서 EQP 확인 |
| P0-2 | file_syms 를 `IN (SELECT …)` 로 다시 쓰기 | 외부 조인은 재배치되지 않음 ([optoverview §16](https://www.sqlite.org/optoverview.html#the_outer_join_strength_reduction_optimization)) | 927.8 → 6.7 ms [측정] | 없음 | EQP 단언 |
| P0-3 | callers 를 SQL GROUP BY + LIMIT + 일괄 이름 조회로. 웹뷰·그래프도 제한판 사용 | clangd `incomingCalls` 일괄 조회 | 핫 심볼 27.9초(전체 N+1) → 상위 60: 2.7초(`refs(sym)`) / 0.42초(커버링) [측정, 단일 DB] | 커버링 +446 MB [측정] | 커버링만 추가하면 정렬 질의 11.6초 [측정]. MultiIndex 합산은 최댓값 근사 [추론] |
| P0-4 | 빌드 끝 `ANALYZE`, EQP 단언 테스트, 접두 일치 단계 | [lang_analyze](https://www.sqlite.org/lang_analyze.html) | ANALYZE 단독 효과 없음(993 ms), 접두 일치 0.2 ms [측정] | 미측정 | SQLite 3.35–3.53 계획 차이 |
| P1-1 | **소유권 분할**: 엔진 DB 가 참조를 가진 파일은 엔진만 답함. 프로젝트 먼저, LIMIT 를 각 DB 로 내림, `has_more` | clangd MergedIndex, Glean slice, woboq | 45초 → DB 별 제한 질의의 합(단일 DB 206–498 ms [측정]). 3.3–3.4 뒤 ms 대 [추론]. 100만 상한 오류 제거 | 빌드 대조 1회(미측정), 프로젝트 DB 축소 [추론] | **프로젝트 TU 만 보는 엔진 헤더 참조 수**를 3.2절 SQL 로 실측. 엔진 DB 재빌드 시 무효화 |
| P1-2 | **요약 테이블** `sym_stats`·`sym_callers`·`sym_modules` (상위 K + 기타) | Kythe `PageIndex.count`/`Caller`, Glean 파생 술어, Dex `RevRefs` | ref_count 41.5초 → 기본키 조회 [추론], 호출자 상위 60 ~0 ms [조사 실험] | 참조 400만에 2.2초 [조사 실험]. 우리 DB 의 디스크·시간 미측정 | 분할 뒤에 집계하는지 테스트, K 결정 |
| P1-3 | **경로 순 file ID + `refs(sym, file, line)` + keyset** | Kythe 컬럼형 키, [Row Values](https://www.sqlite.org/rowvalue.html#scrolling_window_queries) | 3,933 → 498 ms [측정]. 경로 순이면 ~0 ms [조사 실험] | +317 MB [측정], `refs(sym)` 삭제 시 −253 MB [추론], 재번호 미측정 | 실행 계획 함정. EQP 테스트 필수 |
| P1-4 | 에이전트 출력 형태(5절) | SWE-agent, arXiv 2608.13568 | 지연보다 토큰·턴 수 (미측정) | CLI 코드 | 총계는 P1-2 에 의존 |
| P2-1 | FTS5 trigram(name 전용 `detail=none` 우선), 3자 미만 우회, 실행 시 탐지 | Dex, Zoekt, [fts5 source](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_expr.c) | 147.9 ms → 0–7 ms 범위 [측정] | +216 MB / 11.5초 [측정], name 전용 none ~32 MB [조사 실험] | Windows 미검증, 2자 질의는 더 느려짐 |
| P2-2 | 머리글자 열 + B-tree | Dex head-jump trigram | 0.09 ms [조사 실험] | +12.9 MB, 2.4초 [조사 실험] | 실제 UE 이름 분포 |
| P3 | 정수화, (심볼, 파일) 블롭, 병렬 질의, mmap·page_size | SQLite file format, Glean/Sourcegraph/GLOBAL | 인덱스 −45~−56%, 병렬 1.88배 [조사 실험] | 스키마 전면 변경 | Windows I/O·백신 영향 미측정 |

## 5. 에이전트에게는 빠른 답보다 접힌 답이 낫다

### 5.1 지연보다 출력 모양이 중요하다

에이전트 한 턴에는 몇 초짜리 LLM 호출이 들어간다. 그래서 인덱스 질의 하나가 100–500 ms 걸려도 전체 시간을 좌우하지는 않는다고 본다 [추론, 직접 잰 연구 없음]. 비용을 키우는 것은 출력의 크기와 모양이다.

SWE-agent 는 하나씩 보여 주는 검색이 "에이전트의 비용 예산이나 컨텍스트를 소진"시킨다고 진단했다. SWE-bench Lite(GPT-4 Turbo) 결과는 다음과 같다 ([SWE-agent](https://arxiv.org/pdf/2405.15793), 검색 발췌로 확인).

| 검색 도구 | 해결률 |
|---|---|
| **결과 50개 이하로 요약한 검색** | **18.0%** |
| 하나씩 보여 주는 검색 | 12.0% |
| 검색 도구 없음 | 15.7% |

실제 배포된 `search_dir` 도 줄이 아니라 **파일별 개수**를 보여 준다. 100개 파일을 넘으면 "검색을 좁히라"고만 답한다 ([search_dir](https://github.com/SWE-agent/SWE-agent/blob/main/tools/search/bin/search_dir)).

2026년 소규모 예비 연구에서는 시맨틱 참조 찾기의 정밀도가 1.00 으로 grep(0.76)보다 높았지만, 재현율은 모든 조건에서 0.66–0.67 로 같았다. 위치만 주는 LSP 는 여러 파일에 걸친 이름 바꾸기의 4분의 3에서 호출 지점을 놓쳤다 ([arXiv 2608.13568](https://arxiv.org/abs/2608.13568)). 한 블로그 파일럿에서는 줄 원문을 함께 준 LSP 가 위치만 준 LSP 보다 성공률이 높고 토큰도 적었다 ([AgentConnect](https://www.agentconnect.md/blog/grep-beat-lsp-harness/), 2차 자료). 긴 출력의 가운데 묻힌 정보는 모델이 잘 쓰지 못한다 ([Lost in the Middle, TACL 2024](https://aclanthology.org/2024.tacl-1.9/)). 상한 없이 그래프를 따라가게 둔 LocAgent 재현 실험은 182건 만에 $300 예산을 다 썼다 ([arXiv 2605.17965](https://arxiv.org/pdf/2605.17965), 경쟁 저자의 재현).

### 5.2 지금 출력과 권장 출력

| 요소 | 지금 [코드 확인] | 권장 | 근거 |
|---|---|---|---|
| 총계 | CLI `refs` 에 없음. 웹뷰 `ref_rows` 는 100만 상한으로 잘림 | 헤더에 정확한 총계와 프로젝트·엔진 내역 | Kythe `Total`, clangd `HasMore` |
| 묶음 | `impact` 만 파일·모듈별 | 모듈 상위 k + "나머지 m개 모듈 n건" | SWE-agent `search_dir` 의 파일별 개수 |
| 표본 | `--limit` 40개, 경로 순 | 프로젝트 먼저, 파일이 겹치지 않게 | Google 우선순위 랭킹, clangd 의 dynamic 우선 |
| 줄 원문 | refs·callers 모두 있음(좋음) | 유지 | 2608.13568, AgentConnect |
| 잘림 표시 | 4 KB 캡의 "+N more". 이미 가져온 줄 기준이라 총계가 아님(L90–98) | `[잘림] 40/N` + 좁히기 옵션(`--module`, `--path`, `--kind`) + 커서 | SWE-agent, clangd `HasMore` |
| 전수 모드 | `--full` 로 stdout 에 그대로 출력 | 파일로 내보내고 에이전트가 grep | Google: 전부는 요청할 때만 |
| 다단계 (`impact`·그래프) | 상한 없이 전부 가져옴 | 깊이·분기 상한, 핫 노드에서 확장을 멈추고 "N개 더 (via X)" | LocAgent 재현, GitHub hot shard |

Google Code Search 도 기본은 순위가 매겨진 결과이고, 리팩터링처럼 전부가 필요할 때만 전체를 가져온다. 응답이 지나치게 커지지 않게 하는 안전장치도 둔다 ([SWE book 17장](https://abseil.io/resources/swe-book/html/ch17.html)).

### 5.3 권장 출력 예

아래 예에서 숫자 자리는 형식만 보이도록 비워 두었다.

```
# UAbilitySystemComponent::TryActivateAbility  [함수]  <선언 위치>
참조 <N> (프로젝트 <Np> · 엔진 <Ne>) · 파일 <F> · 호출자 <C>  [정확]
모듈: <모듈1> <n1> · <모듈2> <n2> · … (상위 6, 나머지 <m>개 모듈 <n>건)
── 프로젝트 먼저 · 40/<N> ──
r Source/<Game>/…/<File>.cpp:<줄>  in <호출 함수>  │ <줄 원문>
…
[잘림] 다음: --cursor <토큰> · 좁히기: --module <M> | --path <P> | --kind call
```

이 헤더의 총계와 모듈 묶음은 P1-2 요약 테이블에서 그대로 나온다. **속도를 고치는 일과 에이전트 출력을 고치는 일이 같은 작업**이다.

## 6. 검증 안 된 것 / 한계

| 영역 | 검증 안 된 것 | 확인 방법 |
|---|---|---|
| 데이터 | 모든 측정은 합성 DB 에서 했다. 심볼 100만, 참조 1천만, 관계 50만, 파일 6만, 1.3 GB 이고, 참조는 Pareto 분포라 한 심볼이 전체의 약 3분의 1(340만)을 가진다. **실제 UE 엔진 인덱스의 크기와 심볼별 참조 분포는 한 번도 재지 않았다.** | 실제 인덱스에서 심볼별 참조 수의 순위-빈도(로그-로그) 그래프를 그린다 |
| MultiIndex 측정 | 같은 DB 를 두 번 붙여 쟀으므로 실제 두 DB 의 행 분포와 다르다 | 실제 프로젝트·엔진 DB 쌍으로 다시 잰다 |
| 플랫폼 | Linux, SQLite 3.45.1, OS 캐시가 데워진 상태에서만 쟀다. 조사 실험은 단일 실행이다. Windows 는 Python 버전에 따라 SQLite 3.35.5–3.53.4 이고, 실행 계획 선택·NTFS·백신·mmap·FTS5 탐지 모두 재지 않았다 | 지원하는 가장 낮은 버전과 가장 높은 버전의 Windows Python 에서 EQP 단언과 시간을 잰다 |
| 개선 효과 | 소유권 분할은 실제 두 DB 데이터가 없어 아예 재지 않았다. 경로 순 ID 의 ~0 ms, 요약 테이블의 ~0 ms 와 2.2초, 정수화의 크기 감소는 참조 400만 조사 실험 값이다. 요약 테이블 디스크, 재번호 빌드 시간, `refs(sym)` 삭제 뒤의 실행 계획은 미측정이다. 3.2절의 "1초 안팎"과 "ms 대"는 단일 DB 측정을 조합한 추론이다 | 우리 1천만 DB, 이어서 실제 UE DB 에서 P1 변경 뒤 같은 표를 다시 채운다 |
| 분할 정확성 | 엔진 소유 파일 중 프로젝트 TU 만 본 참조의 수. 빌드 구성 차이, 생성 헤더, 매크로가 변수다. 엔진 DB 를 다른 경로의 설치본으로 공유할 때 경로가 맞는지도 미확인 | 3.2절 SQL (1)(2) |
| 출처 | 조사 환경에서 sqlite.org·arxiv.org·engineering.fb.com·github.blog 가 차단됐다. SQLite 문서는 Ubuntu 공식 문서 묶음(3.53.4)으로 읽었다. SWE-agent 절제표, 2608.13568, LocAgent 재현 수치는 검색 발췌다. 2608.13568 은 표본이 작은 예비 프리프린트이고 AgentConnect 는 블로그 파일럿이다. Sourcegraph 코드는 2024-08 공개 스냅샷, GNU GLOBAL 은 2015년 비공식 미러(6.4)다 | 핵심 수치는 원문 접근이 가능할 때 대조한다 |
| 외부 비교 | Kythe·Glean·Sourcegraph 어디에도 우리 수치와 직접 비교할 지연 측정이 공개되어 있지 않다. clangd Dex 의 "limit 까지만 훑는다"는 성질도 코드를 읽고 내린 판단이며 공개 벤치마크는 없다 | 해당 없음. 기대 효과는 알고리즘 비용에 근거한 추론으로만 읽는다 |

## 결론

이번 분석으로 문제가 다시 정의됐다. 조회가 느린 이유는 SQLite 가 1천만 행을 감당하지 못해서가 아니다. **두 DB 를 합치는 설계가 질의 시점에 정확한 중복 제거를 요구했고, 그 요구가 모든 참조를 끌어오게 만들었다.** 우리 적재기는 DB 안에서는 이미 clangd 의 "파일마다 주인은 하나" 규칙에 기대고 있다. 이 규칙을 DB 사이로 넓히기만 하면 중복 제거 자체가 필요 없어진다. 그 뒤에는 업계가 정리해 둔 순서를 따르면 된다. 집계는 빌드로 옮기고, 저장 순서를 접근 순서에 맞추고, 기본 응답에 상한을 둔다. 같은 요약 테이블이 웹뷰의 200 ms 예산과 에이전트의 토큰 예산을 함께 해결한다는 점이 이 방향을 택할 가장 실용적인 이유다.

다음에 할 일은 코드 수정보다 측정 두 가지다. 실제 UE 인덱스에서 심볼별 참조 수의 분포를 보고, 3.2절 SQL 로 분할 손실을 센다. 분포가 이번 합성 데이터만큼 치우쳐 있고 분할 손실이 작으면 P0–P1 로 충분하다. 핫 심볼이 훨씬 무겁거나 디스크가 빠듯하면, Glean·Sourcegraph·GLOBAL 이 각자 따로 도달한 (심볼, 파일) 압축 블롭이 다음 단계다.
