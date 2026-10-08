# Cross-reference storage and serving at scale: clangd, Kythe, Glean, Sourcegraph (SCIP), stack graphs, Woboq/GNU Global/ctags

Research date: 2026-10-08. All code citations are pinned to the commit I read (listed per system). Web access was limited to GitHub plus a search engine. engineering.fb.com, gnu.org, github.blog, clangd.llvm.org and googlesource were blocked by the egress proxy, so claims from those sites come from search-result snippets and are marked "(search snippet)". "Inference" means my own reasoning, not something a source says.

Pinned sources:
- clangd: llvm/llvm-project `main` @ `d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd` (read 2026-10-08). clangd website: llvm/clangd-www @ `ae5866d4` (2026-09-18).
- Kythe: kythe/kythe @ `69141f022689a611e8a4a1d9b08a3783a2e8a9ed` (2026-09-18).
- Glean: facebookincubator/Glean @ `4e576957778b721f28cec21556066a02c3ed84d0` (2026-10-07).
- Sourcegraph: sourcegraph/sourcegraph-public-snapshot @ `c864f15a` (2024-08-22). This is the last public snapshot. Sourcegraph's code has been private since then, so current production behavior may differ.
- stack-graphs: github/stack-graphs @ `fcb7705d` (2025-09-09). The repo is no longer maintained.
- woboq_codebrowser @ `ebe91a86` (2026-04-06). universal-ctags @ `5b72de80` (2026-10-04).
- GNU GLOBAL: an unofficial GitHub mirror harai/gnu-global @ `f86ba74d` (GLOBAL 6.4, 2015). Upstream Savannah was unreachable.

---

## Q1. clangd: how MergedIndex merges dynamic/background/static indexes, ref de-dup, limits, file sharding, remote index, in-memory representation

### Takeaway
clangd never de-duplicates refs by position. It merges indexes by **file-level authority**: the higher-priority index reports all its refs, and the lower index's refs are kept only for files the higher index has not indexed (`indexedFiles(file) & IndexContents::References`). The background index also takes each file's refs from exactly **one** TU's shard, because refs are sharded by the file they are located in. This is the same "partition by location" idea you are considering, with the partition key being "files this index actually indexed" rather than a path prefix. Hot symbols are handled only with a `Limit` plus a boolean `HasMore`. There is no offset/cursor pagination and no precomputed ref count. The defaults are 1000 refs for LSP and a 10,000 cap per request on the remote server.

### Cited Findings
**Merge logic (Merge.cpp)**
- `MergedIndex::refs` keeps the dynamic index authoritative. The code comment says: "We don't want duplicated refs from the static/dynamic indexes, and we can't reliably deduplicate them because offsets may differ slightly. We consider the dynamic index authoritative and report all its refs, and only report static index refs from other files." — [Merge.cpp L125-156](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L125-L156)
- How the filter works:
  - It calls `Dynamic->indexedFiles()` once to get a callback.
  - Each static ref is dropped if `(DynamicContainsFile(O.Location.FileURI) & IndexContents::References) != None`.
  - `Remaining = Req.Limit.value_or(UINT32_MAX)` is decremented across both indexes.
  - If the dynamic index alone exhausts the limit and reports `More`, the static index is never queried.
  - Over the limit, the code sets `More = true` and keeps scanning the static index without emitting anything.
  - The comment says: "We return less than Req.Limit if static index returns more refs for dirty files."
  - Source: [Merge.cpp L129-155](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L129-L155)
- `containedRefs` (outgoing calls) uses the same "dynamic authoritative, static filtered by file" rule. — [Merge.cpp L158-190](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L158-L190)
- Relations are the only data that is de-duplicated by value. A `DenseSet<pair<SymbolID,SymbolID>>` records what the dynamic index reported, and static duplicates are skipped. The comment notes: "We might return stale relations from the static index; we don't currently have a good way of identifying them." — [Merge.cpp L200-248](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L200-L248)
- Symbols (`fuzzyFind`/`lookup`) work differently:
  - Dynamic results are slurped into a slab.
  - Static symbols also present in that slab are merged with `mergeSymbol`.
  - A static symbol whose definition file (or canonical declaration file) is owned by the dynamic index is treated as stale and dropped (`isIndexAuthoritative`).
  - Source: [Merge.cpp L23-31, L34-123](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L23-L123)
- `mergeSymbol` adds the two indexes' `References` counters (`S.References += O.References`). `Symbol::References` is "The number of translation units that reference this symbol from their main file. This number is only meaningful if aggregated in an index." It is a TU-popularity count, not a ref count. — [Merge.cpp L285](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L285); [Symbol.h L72-74](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Symbol.h#L72-L74)
- `IndexContents` is a per-file bitmask (`Symbols | References | Relations`). The header explains why: "if a staler index contains a reference but a fresher one does not, we want to trust the fresher index *only* if it actually includes references in general." — [Index.h L108-120](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Index.h#L108-L120)
- `SymbolIndex::indexedFiles()` returns a function that checks whether a file was used to build the index. — [Index.h L192-196](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Index.h#L192-L196)
  - Dex implements it as a `StringSet` lookup that returns the index's `IdxContents`. — [Dex.cpp L405-409](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/dex/Dex.cpp#L405-L409)
  - The remote-index client always returns `IndexContents::None` ("FIXME"). A remote static index therefore never suppresses anything, and all its refs pass through. — [remote/Client.cpp L179-185](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/remote/Client.cpp#L179-L185)
- **Layering order.** `ClangdServer` stacks indexes with `AddIndex`, where each new index gets "higher priority than existing indexes": Static first, then Background, then Dynamic. The result is `Merged(Dynamic, Merged(Background, Static))`. — [ClangdServer.cpp L244-272](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/ClangdServer.cpp#L244-L272)
- In `findReferences`, refs located in the open main file are discarded from index results: "Avoid indexed results for the main file - the AST is authoritative". — [XRefs.cpp ~L1857-1861](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/XRefs.cpp#L1856-L1861)

**Limits and "too many results"**
- `RefsRequest { IDs; Filter = RefKind::All; optional<uint32_t> Limit; bool WantContainer }`. The doc says: "If set, limit the number of refers returned from the index. The index may choose to return less than this." `refs()` "Returns true if there will be more results (limited by Req.Limit)". — [Index.h L68-78, L161-163](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Index.h#L68-L78)
- CLI defaults: `--limit-references` "Limit the number of references returned by clangd. 0 means no limit (default=1000)". `--limit-results` defaults to 100 for completion/symbol search. — [ClangdMain.cpp L317-330](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/tool/ClangdMain.cpp#L317-L330)
- `findReferences` asks the index only for the remaining quota (`Req.Limit = Limit - Results.References.size()`). Once the quota is already full, it still sends `Req.Limit = 0` "to correctly return the `HasMore` info". It ORs the index's return value into `Results.HasMore`. — [XRefs.cpp L1838-1857](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/XRefs.cpp#L1838-L1857)
- Remote server: `clangd-index-server --limit-results` defaults to 10000, described as "Maximum number of results to stream as a response to single request. Limit is to keep the server from being DOS'd." If the client sends no limit, or one above the cap, the server clamps it. It streams results and ends with `FinalResult{has_more}`. — [remote/server/Server.cpp L108-112, L225-257](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/remote/server/Server.cpp#L108-L112); [remote/Index.proto (`message FinalResult { optional bool has_more = 1; }`, `RefsRequest.limit`)](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/remote/Index.proto)
- **Incoming calls (callers) have no limit.**
  - `incomingCalls` issues `RefsRequest{IDs, WantContainer=true, Filter=RefKind::Reference}` with no Limit.
  - It groups the refs into `DenseMap<SymbolID, vector<Location>> CallsIn` keyed by `R.Container`.
  - It then issues **one batched `LookupRequest`** for all container IDs, not one lookup per caller.
  - Results are sorted by caller name. For virtual methods it repeats the query for overridden bases via `reverseRelations(OverriddenBy)`.
  - Source: [XRefs.cpp L2573-2650](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/XRefs.cpp#L2573-L2650)

**In-memory representation and query cost**
- `Ref = { SymbolLocation Location; RefKind Kind; SymbolID Container; }`. `RefKind` is a `uint8_t` bitfield: Declaration=1, Definition=2, Reference=4, Spelled=8, Call=16. Ordering is by `(Location, Kind, Container)`. — [Ref.h L28-105](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Ref.h#L28-L105)
- `SymbolLocation::Position` packs line and column into a single `uint32_t` ("Top 20 bit line, bottom 12 bits column"; `ColumnBits = 12`). `FileURI` is a `const char*` into interned storage. — [SymbolLocation.h L30-64](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/SymbolLocation.h#L30-L64)
- `RefSlab` is described as "An efficient structure of storing large set of symbol references in memory. Filenames are deduplicated."
  - It is a `vector<pair<SymbolID, ArrayRef<Ref>>>` with the strings in a `BumpPtrAllocator` arena via `UniqueStringSaver`.
  - `Builder` de-duplicates **exact** `(Symbol, Ref)` entries through a `DenseSet<Entry>`.
  - `build()` sorts each symbol's refs ("By file, affects xrefs display order") and copies them into the arena.
  - Sources: [Ref.h L109-166](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Ref.h#L109-L166); [Ref.cpp L36-64](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Ref.cpp#L36-L64)
- Dex keeps `llvm::DenseMap<SymbolID, llvm::ArrayRef<Ref>> Refs`. `Dex::refs` does a hash lookup and then a linear walk over the contiguous array:
  - it skips kinds not in `Req.Filter`;
  - it stops and returns `true` when `Remaining == 0`.
  - The cost is therefore O(refs scanned up to the limit), with no sorting or de-dup at query time.
  - Sources: [dex/Dex.h L151-152](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/dex/Dex.h#L151-L152); [dex/Dex.cpp L315-329](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/dex/Dex.cpp#L315-L329)
- For outgoing calls, Dex builds a separate `std::vector<RevRef> RevRefs` **sorted by container ID**, holding only refs with `RefKind::Call`. `lookupRevRefs` uses `std::equal_range`, which is a reverse index built at load time. — [dex/Dex.cpp L152-163, L332-358](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/dex/Dex.cpp#L152-L163)
- `IndexType::Light` (MemIndex) "is trivially cheap to build, but has poor query performance". `Heavy` (Dex) "is relatively expensive to build and uses more memory, but is fast". — [FileIndex.h L42-48](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/FileIndex.h#L42-L48)
- On-disk format (RIFF `.idx`):
  - Refs are grouped by symbol: "SymbolID: 8 bytes, NumRefs: varint, Ref[NumRefs]".
  - Each ref is written as a kind byte, then the location (file as a varint index into the string table, positions as varints), then the 8-byte container ID.
  - The string table is sorted "to improve compression" and zlib-compressed.
  - Source: [Serialization.cpp L158-200, L372-388](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Serialization.cpp#L372-L388)

**File sharding (background index)**
- `FileShardedIndex` attributes each Symbol to its declaration file and its definition file. Refs are attributed "into each file they occurred in" (keyed by `R.Location.FileURI`). Relations are stored in both the subject's and the object's shards. — [FileIndex.cpp L127-181](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/FileIndex.cpp#L127-L181)
- `BackgroundIndex::update` writes a shard only for files whose content digest changed. A `FileFilter` skips collecting index data for any file whose stored digest is unchanged ("Skip files that haven't changed, without errors").
  - As a result, a header's refs are taken from whichever TU (re)indexes it first after a change. No cross-TU de-dup is needed.
  - The comment admits a race: "This can override a newer version that is added in another thread ... rare in practice."
  - Source: [Background.cpp L184-252, L289-306](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Background.cpp#L184-L252)
- `FileSymbols` keeps one snapshot of slabs per key (file). `buildIndex` concatenates every file's RefSlab per SymbolID into one contiguous `RefsStorage` vector with **no de-dup** ("Sorting isn't required, but yields more stable results over rebuilds"). It only sorts and uniques Relations. — [FileIndex.h L57-70](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/FileIndex.h#L57-L70); [FileIndex.cpp L340-376](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/FileIndex.cpp#L340-L376)
- The background rebuild uses `buildIndex(IndexType::Heavy, DuplicateHandling::Merge)`. `DuplicateHandling` applies to symbols only: PickOne is "less accurate but faster", Merge is "more accurate but slower". — [BackgroundRebuild.cpp L97](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/BackgroundRebuild.cpp#L97); [FileIndex.h L50-55](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/FileIndex.h#L50-L55)

**Remote index**
- Design docs say: "For large codebases (e.g. LLVM and Chromium) global index can take a long time to build (multiple hours even on very powerful machines for Chrome-sized projects) and induces a large memory overhead (multiple GB of RAM) to serve within clangd." The remote index serves it from another machine. — [clangd-www design/indexing.md L83-92](https://github.com/llvm/clangd-www/blob/ae5866d4552e30a173b8e9c3cec872a82e4c0120/design/indexing.md)
- Public Chromium endpoints are listed as `linux.clangd-index.chromium.org:5900` (variants for chromeos, android, fuchsia, etc.). — [clangd-www guides/remote-index.md L58](https://github.com/llvm/clangd-www/blob/ae5866d4552e30a173b8e9c3cec872a82e4c0120/guides/remote-index.md)
- The server loads the whole `.idx` into an in-memory Dex (`loadIndex(..., UseDex=true)`) behind a `SwapIndex`. A hot-reload thread swaps in a new index when the file's modification time changes. A `Monitor` gRPC service reports index age. — [remote/server/Server.cpp L430-501, L633-644](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/remote/server/Server.cpp#L472-L501)

### Inferences
- Your "partition by location" plan is the clangd MergedIndex rule. To match clangd exactly:
  - Define the partition key as "**this file is in the higher-priority DB's indexed-files set** (with References content)", not "path is under the engine root".
  - With a pure path-prefix rule you lose refs in engine headers that no engine TU indexed but some project TU did. Examples: headers only reachable through project includes, generated headers, and different macro configurations.
  - clangd's file-set test keeps those refs because the engine index does not claim the file.
  - Concretely: treat the engine DB as authoritative for files in its `files` table (the files that engine TUs produced refs in). Take project-DB refs only for files *not* in that set.
- clangd's speed on hot symbols comes from:
  - a contiguous per-symbol array, which gives O(limit) work;
  - no position de-dup at query time;
  - stopping at the limit while still reporting `HasMore`.
  - None of these needs sorting a million rows. Your current pipeline (pull 1M rows from each DB, de-dup, sort, slice) does O(N log N) Python work even when only the first page is needed.
- The callers pattern to copy from `incomingCalls`: a single pass grouping refs by `container`, then one batched symbol lookup for all containers. In SQL that is a `GROUP BY container` joined to `symbols`, replacing one lookup per caller.
- clangd has no precomputed per-symbol ref count. A "ref count" for a symbol with millions of refs is something clangd simply does not offer; it says "HasMore" instead.

### Gaps
- I found no published latency benchmark for `Dex::refs` on hot symbols, for example refs/sec or ms for symbols with 10^6 refs. The O(limit) claim comes from reading the code.
- I found no published memory figures for the public Chromium/LLVM remote-index servers beyond "multiple GB of RAM".

---

## Q2. Kythe: serving-table layout, paged cross-references, page tokens, precomputed totals, hot nodes

### Takeaway
Kythe precomputes everything at post-processing time. In the legacy format, each node's xrefs are split into a small `PagedCrossReferences` header that holds **per-page counts** (`PageIndex{kind, count, page_key}`) plus separately keyed pages. Totals can therefore be computed without reading pages, and paging skips whole pages by count. Page tokens encode a skip offset. A newer **columnar** format puts the data in ordered keys (`"xr"-source-00-kind-file-start-end`, with callers as `20-caller`, `20-caller-kind-file-start-end`), so lookups become prefix scans and "paging becomes trivial". It was introduced explicitly because hot nodes created hot shards, stragglers and memory blowups.

### Cited Findings
- Legacy table format: `xrefs:<ticket> -> srvpb.PagedCrossReferences` and `xrefPages:<page_key> -> srvpb.PagedCrossReferences_Page` (alongside `decor:` and `docs:`). — [kythe/go/serving/xrefs/xrefs.go L20-25](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/go/serving/xrefs/xrefs.go#L20-L25)
- `PagedCrossReferences` is "for efficiently storing pre-cached data for CrossReferencesReply.{definition,reference,caller} anchors and related nodes". Its contents:
  - inline `repeated Group group`, plus `repeated PageIndex page_index`;
  - `PageIndex{kind, int32 count, page_key, build_config}`;
  - pre-grouped `Caller{caller anchor, semantic_caller, marked_source, repeated callsite}`;
  - `merge_with` ("Nodes with cross-references that should be merged into this node's set of cross-references. These are highly related nodes that share a definition.");
  - a per-node trigram `PageSearchIndex`, which maps path, corpus or root trigrams to delta-encoded page indices, so path filters can skip pages.
  - Source: [kythe/proto/serving.proto L265-379](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/proto/serving.proto#L265-L379)
- The post-processor's paging is generic. `pager.SetPager{MaxPageSize ...}` "splits a stream of Groups into a single Set and one-or-more associated Pages". The pipeline option `MaxPageSize` is the "maximum number of edges/cross-references that are allowed in" a page/set; "<= 0, no paging". — [kythe/go/util/pager/pager.go](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/go/util/pager/pager.go); [kythe/go/serving/pipeline/pipeline.go L59-62](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/go/serving/pipeline/pipeline.go#L59-L62)
- API (`CrossReferencesRequest`):
  - `page_size` / `page_token`: tokens are opaque, "valid only relative to a particular CrossReferencesRequest". The server "is allowed to return fewer cross-references than the requested page_size ... save that it must return at least 1".
  - `TotalsQuality {PRECISE_TOTALS, APPROXIMATE_TOTALS}`: with APPROXIMATE, "the totals may be partial/approximate so that the server can return results as soon as possible".
  - Source: [kythe/proto/xref.proto L392-424](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/proto/xref.proto#L392-L424)
- Reply:
  - `Total{definitions, declarations, documentation, callers, map ref_edge_to_count, related_nodes_by_relation}` covers "Total number of cross-references on all pages matching requested kinds, build configs, and filters".
  - `Total filtered` counts what `corpus_path_filters` removed.
  - `next_page_token` is empty when the results are exhausted.
  - Source: [kythe/proto/xref.proto L572-614](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/proto/xref.proto#L572-L614)
- Server mechanics:
  - `defaultPageSize = 2048`, `maxPageSize = 10000` (requests are clamped).
  - Default `experimental_default_totals_quality = "APPROXIMATE_TOTALS"`.
  - `xrefs_response_leeway_time = 50ms`: "leave this much time at the end of a CrossReferencesRequest to return any results already read". On hitting the soft deadline the server logs "trying to return already read xrefs" and returns partial results.
  - Source: [xrefs.go L69-73, L293-294, L742-747, L1030-1033](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/go/serving/xrefs/xrefs.go#L293-L294)
- Page skipping by stored counts:
  - `refStats.skipPage` subtracts `idx.Count` from `skip` and skips the whole page without reading it.
  - The server walks `cr.GetPageIndex()` to find the "first unskipped page", calling `AddCount` for the totals as it goes.
  - It can read ahead pages concurrently (`pageReadAhead`).
  - The next token is `PageToken{Indices["skip"] = initialSkip + stats.total}`, protobuf-marshalled, snappy-compressed and base64-encoded.
  - Under APPROXIMATE totals, the loop over tickets stops once the page is full.
  - Source: [xrefs.go L851-853, L985-1028, L1165-1174, L1325-1346](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/go/serving/xrefs/xrefs.go#L985-L1028)
- RFC 2909 (columnar format) describes the problem with hot nodes directly:
  - the old format "requires the Kythe PostProcessor to perform a complex reduction over a potentially massive number of decorations/references/edges/etc. to produce a single lookup value per node. A set of CrossReferences can be so large that it already requires manual paging ... These operations tend to create hot shards and stragglers, leading to long post-processing times and potentially failures due to memory exhaustion";
  - also "the server is forced to slowly decode large ProtocolBuffer messages even when only a subset of the data is required".
  - The proposal: "Split serving table ProtocolBuffer values into their component fields ... Single lookup API calls become scans over a key prefix; paging becomes trivial."
  - It also "removes the need for many 'limiters' (i.e. cutoff values for the size of outputs)", and keys are ordered (orderedcode) and unique for LevelDB/SSTable.
  - The RFC notes "the keys could be split and put into a relational database".
  - Source: [kythe/docs/rfc/2909.md](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/docs/rfc/2909.md)
- Columnar CrossReferences keys (prefix `"xr"-source`):
  - `Index` has an empty key (node, marked_source, merge_with).
  - Reference: `00-kind-file-start-end`.
  - Relation: `10-kind-reverse-ordinal-target`.
  - Caller: `20-caller`.
  - Callsite: `20-caller-kind-file-start-end`.
  - RelatedNode: `30-node`. NodeDefinition: `40-node`.
  - Source: [kythe/proto/xref_serving.proto L142-215](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/proto/xref_serving.proto#L142-L215)
- Chromium Code Search is powered by Kythe. Chromium's `build/toolchain/kythe.gni` says it "defines configuration for Kythe, an indexer and cross-referencer that powers codesearch". Google describes an internal pipeline that "combines these graphs ... prunes ... and optimizes it for serving cross-references", run several times per day. (search snippet) — [chromium build/toolchain/kythe.gni](https://chromium.googlesource.com/chromium/src/+/master/build/toolchain/kythe.gni); [Google Open Source Blog, 2020-04](https://opensource.googleblog.com/2020/04/code-search-for-google-open-source.html)

### Inferences
- Columnar Kythe is essentially a **covering B-tree index** with key `(symbol, kind, file, start, end)` plus a separate pre-aggregated caller block `(symbol, caller)` that leads into `(symbol, caller, kind, file, start, end)`. In SQLite this maps to:
  - `refs` with a composite index (or `WITHOUT ROWID` primary key) on `(sym, kind, file, line, col)`;
  - a `callers(sym, container, n_callsites, first_file, first_line)` table precomputed at load.
  - Paging is then keyset-based (`WHERE (file,line,col) > (?,?,?) ORDER BY ... LIMIT n`), not "pull everything and slice".
- Kythe's legacy `PageIndex.count` amounts to a precomputed totals table. A `ref_counts(sym, kind, n)` table, plus optionally per-file counts, gives O(1) ref-count queries. It also lets a page request skip whole files by count, the way `skipPage` skips pages.
- Kythe's defaults (2048 per page, at most 10000, approximate totals, 50 ms leeway) are reasonable defaults to copy.

### Gaps
- I did not find which serving format (legacy or columnar) Google's production Chromium Code Search uses today. The public docs for source.chromium.org could not be fetched.
- I found no published per-node size statistics, such as the largest xref sets in Chromium.

---

## Q3. Glean (Meta): storage, Angle, derived/stored predicates for xrefs, fast find-references, stacked/incremental DBs and de-dup

### Takeaway
Glean stores immutable facts in RocksDB (or LMDB). Every predicate is indexed by a **prefix of its key**, so fast find-references depends on having a predicate whose key *starts with the target*. For C++ that is `cxx1.TargetUses {target, file, from: PackedByteSpans}`. A deriver precomputes it from per-file `FileXRefs`, producing **one fact per (target, file)** with all spans packed into one value. Stacked (incremental) DBs combine a base DB and an increment by fact-ID ranges:
- lookups check the stacked layer first, then the base;
- iteration is base first, then stacked;
- a fact with the same key as a base fact is never re-created, which is de-dup by content key;
- facts owned by changed "units" (e.g. files) in the base are hidden through an ownership "slice" bitmap.

### Cited Findings
- Backend requirements: multiple tables, prefix seek and scan in lexicographic order, concurrent readers, and fast whole-DB save/restore. Glean supports RocksDB and LMDB. — [glean/website/docs/implementation/db.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/db.md)
- Core tables: **entities** (fact ID → key,value) and **keys** (fact key → fact ID). "for each fact, the key is stored twice ... this representation is rather wasteful of space". They describe truncating long keys to save space. — [db.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/db.md)
- Prefix indexing: "The order of fields in the schema matters a lot for efficiency. Glean indexes facts by a prefix of their keys ... the difference is between *O(log n)* and *O(n)*." To query in the other direction, "define a new predicate with a different field ordering, and automatically generate the facts ... by deriving them". — [docs/angle/efficiency.md L11-32](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/angle/efficiency.md)
- Derived predicates come in two kinds:
  - **stored**, computed once by `glean derive` and written to the DB before `glean finish`;
  - **on-demand**, computed at query time and used for abstraction layers like `codemarkup`.
  - Source: [docs/derived.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/derived.md)
- C++ xref schema:
  - `FileXRefMap {file, fixed: [FixedXRef], froms: [From]}` and `FileXRefs {xmap, targets: [XRefTargets]}` are file-keyed.
  - `From = {spans, expansions, spellings : src.PackedByteSpans}`.
  - `TargetUses {target: XRefTarget, file: src.File, from: From}` is commented "Note that ('target', 'file') makes a unique key for these facts. All uses of a declaration in a file".
  - Source: [glean/schema/source/cxx.angle L584-700](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/schema/source/cxx.angle#L641-L700)
- The C++ docs say `clang-derive` "computes derived facts on the result (e.g. find-references tables)". — [docs/indexer/cxx.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/indexer/cxx.md)
- The `CxxTargetUses` deriver:
  - streams `FileXRefMap`s, relying on all of one file's maps arriving in sequence ("We rely on the ordering property of the `allFacts` query");
  - accumulates a `HashMap XRefTarget Ranges` per file;
  - emits one `TargetUses` fact per target with the ranges packed (`rangesToPackedByteSpans`);
  - is batched and bounded by `cfgMaxQueryFacts` and `cfgMaxQuerySize`.
  - In incremental mode it processes only new `FileXRefMap`s.
  - Source: [glean/lang/clang/Derive/CxxTargetUses.hs L52, L92, L105-125](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/lang/clang/Derive/CxxTargetUses.hs)
- The language-neutral `codemarkup.cxx.CxxEntityUses` is defined on top of `cxx1.TargetUses { {declaration = D}, File, From }`. Clients query entity uses through it. — [glean/schema/source/codemarkup.cxx.angle ~L395-417](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/schema/source/codemarkup.cxx.angle)
- Query limits: `UserQueryOptions` has `max_results`, `max_bytes` and `max_time_ms`. Each one, if exceeded, returns partial results plus a `continuation` (`results_cont`). "If you don't set max_results, the server might impose a default". — [glean/if/glean.thrift L419-448](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/if/glean.thrift#L419-L448)
- Resumable queries save the iterator as `(Pid, Fact ID)`, which "uniquely determines where to restart from". — [db.md "Restarting a fact iterator"](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/db.md)
- Glass (Glean's code-nav server) sets `MAXIMUM_SYMBOLS_QUERY_LIMIT = 10000` ("Default ceiling on total items on any individual Glean query") and `MAXIMUM_QUERY_TIME_LIMIT = 15000` ms. `RequestOptions.limit` is "maximum results to return". — [glean/glass/if/glass.thrift L23-27, L162-167](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/glass/if/glass.thrift#L23-L27)
- **Stacked DBs: lookup, iteration and de-dup**
  - `StackedBase::idByKey` checks `stacked` first, then `base`, and accepts a base result only if `bid < mid`. `mid` is the stacked DB's starting ID, so fact IDs are partitioned into ranges.
  - `typeById` and `factById` route by `id < mid`.
  - `count(pid) = base + stacked`.
  - `Stacked<Define>::define` first looks up the clause key in the base. If it exists (and the values match) it **returns the base fact ID instead of writing a duplicate**. Source: [glean/rts/stacked.h L20-60, L164-198](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/rts/stacked.h#L20-L60)
  - Iterators "use an 'append iterator' which iterates through the base DB in the stack first and then the stacked DB". "For a stacked DB, we know whether the fact ID is in the lower or the upper DB because we know the fact ID boundary between the two DBs." Source: [db.md L145, L153](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/db.md)
- **Hiding stale base facts through ownership**
  - Indexers tag facts with *units*, arbitrary strings such as a file or module. "When building an incremental DB, we will *exclude* some units from the base DB. This is done by building a *slice* ... A fact is visible if its `UsetId` is in the slice ... A slice is represented by a bitmap."
  - Ownership propagates so that referenced facts stay visible (`A || B`). Derived facts get `O1 && ... && On`.
  - Scale assumption: "Typically we see between 10-100x more facts than sets ... one unit per file or module is good, but one unit per function would lead to more sets."
  - `factOwners` is an interval map from fact ID to set ID, cached in memory page by page and binary-searched. Sets are Elias-Fano encoded.
  - Source: [docs/implementation/incrementality.md L100-200](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/incrementality.md)
- Stacked-DB caveat (stated): a stacked DB may add owners to base facts, but "facts that derived from F in the original base DB will have ownership sets that don't include B ... At the time of writing, this isn't implemented yet." — [incrementality.md L231-274](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/incrementality.md)
- Meta's 2024-12-19 blog frames the goal as "we want the cost of indexing to be O(changes) rather than O(repository)" and says they avoid destructively modifying the original data. (search snippet; the page itself was blocked) — [Indexing code at scale with Glean, engineering.fb.com](https://engineering.fb.com/2024/12/19/developer-tools/glean-open-source-code-indexing/)

### Inferences
- The `TargetUses` shape (one row per (symbol, file) with spans packed into a blob) is the most directly copyable trick for symbols with millions of refs. A 3.4M-ref symbol spread over, say, 30–100k files becomes 30–100k rows. A prefix scan on `sym` then returns per-file rows that are cheap to count. You can page by file and decode only the files on the current page.
- Glean's stack semantics map onto your two DBs if you treat the **engine DB as base** and the **project DB as the stacked layer**:
  - "lookup stacked first, else base" applies to symbols;
  - "append iterate base then stacked" applies to refs;
  - "hide base facts owned by excluded units" becomes: hide engine-DB refs for files the project layer claims, or the reverse, depending on which you make authoritative.
  - The unit is the file, which is Glean's recommended granularity.

### Gaps
- I could not fetch the Meta blog page or any published latency numbers for Glean xref queries or DB sizes.
- I did not verify whether Glass applies a default limit specifically to `findReferenceRanges`. It reads `requestOptions_limit`, but I did not confirm what happens when that is unset.

---

## Q4. Sourcegraph precise code navigation (SCIP): storage layout, cross-repo references, cursors, caps

### Takeaway
Sourcegraph (as of the last public code, 2024-08) stores references as **one Postgres row per (upload, symbol, document)**, with each occurrence role's ranges in a **compact delta+varint, column-oriented `bytea`**. Find-references:
- fetches all such rows for the symbol across the chosen uploads, aggregated per symbol;
- decodes them and paginates in memory with an offset, because ranges are blobs and so "we can't use LIMIT+OFFSET at the level of locations";
- uses an opaque JSON/base64 cursor that walks a "local" phase and then a "remote" (cross-repo) phase;
- loads referencing uploads in batches of 500.

### Cited Findings
- Schema (codeintel-db):
  - `codeintel_scip_symbols(upload_id, document_lookup_id, schema_version, definition_ranges bytea, reference_ranges bytea, implementation_ranges bytea, type_definition_ranges bytea, symbol_id)` with `PRIMARY KEY (upload_id, symbol_id, document_lookup_id)`.
  - The table comment: "A mapping from SCIP Symbol names to path and ranges where that symbol occurs within a particular SCIP index".
  - Source: [migrations/codeintel/squashed.sql L238-266, L396](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/migrations/codeintel/squashed.sql#L238-L248)
- Documents are content-addressed: `codeintel_scip_documents(id, payload_hash, raw_scip_payload)`. `payload_hash` is "A deterministic hash of the raw SCIP payload. We use this as a unique value to enforce deduplication between indexes with the same document data". `codeintel_scip_document_lookup(upload_id, document_path, document_id)` maps paths to the shared documents. Symbol names are stored as a trie (`codeintel_scip_symbol_names(id, upload_id, name_segment, prefix_id)`). — [squashed.sql L93-151](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/migrations/codeintel/squashed.sql#L93-L151)
- Range encoding:
  - `EncodeRanges` "de-interlace[s] each component of the ranges and 'column-orient[s]' each component (all start lines packed together, etc) and delta-encode[s]", then writes varints.
  - The rationale per quadrant: start-line deltas "produce small integers", and start/end distances "should result in a long run of zeros".
  - Source: [internal/codeintel/shared/ranges/ranges.go L13-96](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/shared/ranges/ranges.go#L13-L45)
- Query and pagination:
  - The `symbolUsagesQuery` comment says it "gets ALL usages of a bunch of symbols across the ENTIRE instance (within the given set of uploadIDs). We need to do this because the ranges are stored using a custom binary encoding which means we can't use LIMIT+OFFSET at the level of locations."
  - The query uses `array_agg(ranges ORDER BY document_path) ... GROUP BY upload_id, symbol_name ORDER BY upload_id, symbol_name` "to maintain determinism for pagination", and excludes `(upload_id, document_path) NOT IN (skip list)`.
  - In Go, `totalCount` is the sum of all decoded loci; pages are taken by decrementing an offset and stopping at `opts.Limit`.
  - Source: [codenav/internal/lsifstore/locations_by_position.go L315-407](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/internal/lsifstore/locations_by_position.go#L315-L407)
- The cursor is `PreciseCursor`:
  - `Phase` is ""/"local", then "remote", then "done", with `LocalUploadOffset`, `LocalLocationOffset`, `RemoteUploadOffset`, `RemoteLocationOffset`, `VisibleUploads`, `DefinitionIDs`, `UploadIDs` (the current batch) and `SymbolNames`.
  - `SkipPathsByUploadID` lists "paths to skip for particular uploads in the remote phase". This is how the remote phase avoids re-returning what the local phase already returned.
  - The service loops through the phases until a page is full: "each invocation of either phase may produce fewer results than the requested page size".
  - Source: [codenav/types.go L148-171, L214-242](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/types.go#L148-L171); [codenav/service_new.go L145-157, L283-356](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/service_new.go#L145-L157)
- Cross-repo:
  - The remote phase fetches upload IDs that reference the symbol's monikers/packages: `GetUploadIDsWithReferences(..., limit = maximumIndexesPerMonikerSearch, offset = RemoteUploadOffset)`. Package references live in `lsif_references(dump_id, scheme, manager, name, version)`.
  - `PRECISE_CODE_INTEL_MAXIMUM_INDEXES_PER_MONIKER_SEARCH` defaults to **500**. The rationale: "Previously this limit was meant to keep the number of SQLite files we'd have to open ... Since we've migrated to Postgres ... we only want to limit these values based on the number of elements we can pass to an IN () clause ... as well as the size required to encode them in a user-facing pagination cursor."
  - Sources: [service_new.go L515-540](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/service_new.go#L515-L540); [uploads/internal/store/dependencies.go L32-37](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/uploads/internal/store/dependencies.go#L32-L37); [cmd/frontend/internal/codeintel/config.go L22](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/cmd/frontend/internal/codeintel/config.go#L22); [codenav/request_state.go L22-28](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/request_state.go#L22-L28)
- Default GraphQL references page size: `DefaultReferencesPageSize = 100`. Definitions are capped by `DefinitionsLimit = 100`. — [transport/graphql/root_resolver_references.go L19](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/transport/graphql/root_resolver_references.go#L19); [codenav/service.go L381-382](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/service.go#L381-L382)
- When the same symbol is found through several matching strategies, related usages are de-duplicated with `collections.DeduplicateBy(... RangeKey / SymbolAndRoleKey / SymbolRoleKey)`, so de-dup happens on ranges in memory. — [locations_by_position.go ~L295-310](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/internal/lsifstore/locations_by_position.go)

### Inferences
- Sourcegraph's model shows both sides of per-(symbol, file) blobs:
  - Storage is compact and the row count is O(files).
  - Exact location-level LIMIT/OFFSET in SQL is lost, so they fall back to "fetch all, decode, slice". For a 3.4M-ref symbol that is the same kind of cost you have now, though cheaper per ref.
  - To get both benefits, store a per-(sym, file) **count column** next to the blob. Paging can then skip whole files by count (Kythe-style) and decode only the files on the requested page.
- Their `SkipPathsByUploadID` is a path-level exclusion between two sources, which is the same idea as clangd's `indexedFiles` filter applied across "local" and "remote" indexes.

### Gaps
- Sourcegraph's current (2025–2026) private code may have changed. I could not verify current production behavior or any published latency or size numbers for codeintel-db.
- I did not fetch the "Announcing SCIP" blog for its storage-size claims; the site was blocked.

---

## Q5. Woboq codebrowser, Chromium Code Search, GNU GLOBAL (GRTAGS), Universal Ctags: refs-at-scale tricks

### Takeaway
The static tools use **pre-materialized per-symbol or per-tag records**:
- Woboq writes one `refs/<USR>` file per symbol. Each file is generated only once, and the first TU that generates it wins, which avoids duplicate refs from headers seen by many TUs.
- GNU GLOBAL stores GRTAGS as a B-tree keyed by tag name. Each record covers **one (file, tag)** with a **delta- and range-compressed line list**, and the file ID comes first so a file's records can be deleted quickly on incremental updates.
- ctags relies on sorted files plus binary search. Its reference tags are limited.
- Chromium Code Search is Kythe-based (see Q2).

### Cited Findings
- Woboq writes refs as `outputPrefix/refs/<symbol-ref-name>` with `OF_Append`. Each TU appends its references for each symbol as lines like `<use f='file' l='line' u='c|r|w|a|m' c='context'/>`, `<dec .../>`, `<def .../>`, `<ovr .../>` or `<inh .../>`. — [generator/annotator.cpp L344-430](https://github.com/woboq/woboq_codebrowser/blob/ebe91a86e4d06a23f5f7709d081f83e2cc14ef26/generator/annotator.cpp#L344-L430)
- References are registered only for files where `shouldProcess(FID)` is true. `ProjectManager::shouldProcess` returns false for `External` projects and `!exists(<output>.html)` otherwise. A file is therefore processed (HTML plus its refs) only by the **first TU** that reaches it, and external projects' files are never processed. — [generator/annotator.cpp L199-240, L606-666](https://github.com/woboq/woboq_codebrowser/blob/ebe91a86e4d06a23f5f7709d081f83e2cc14ef26/generator/annotator.cpp#L199-L240); [generator/projectmanager.cpp L77-88](https://github.com/woboq/woboq_codebrowser/blob/ebe91a86e4d06a23f5f7709d081f83e2cc14ef26/generator/projectmanager.cpp#L77-L88)
- GNU GLOBAL tag format (version 6):
  - Compact format "is the default format of GRTAGS": `<file id> <tag name> <line number>,...`. "Line numbers are sorted in a line. Each line number might be expressed as difference from the previous line number except for the head ... ex: 10,3,2 means '10 13 15' ... successive line numbers are expressed as a range. ex: 10-3 means '10 11 12 13'."
  - Design notes: "Use file id instead of path name", and "Put file id at the head of tag record ... This is advantageous for deleting tag record when incremental updating."
  - Source: [libutil/gtagsop.c L134-200 (unofficial mirror, GLOBAL 6.4)](https://github.com/harai/gnu-global/blob/f86ba74d867385353815f8656c4a6cf4029c1f0b/libutil/gtagsop.c#L134-L200)
- GLOBAL's DB layer opens Berkeley-DB-style `dbopen(path, ..., DB_BTREE, &info)`, with `R_DUP` (duplicate keys) when `DBOP_DUP` is set. — [libutil/dbop.c L216-274](https://github.com/harai/gnu-global/blob/f86ba74d867385353815f8656c4a6cf4029c1f0b/libutil/dbop.c#L216-L274)
- The gtags man page notes that `-c` (compact) affects GTAGS only, because GRTAGS is always compact. (search snippet) — [gtags(1) man page, mankier](https://www.mankier.com/1/gtags)
- Universal Ctags:
  - "The NAME action will perform binary search on sorted (including 'foldcase') tags files, which is much faster then on unsorted tags files." — [man/readtags.1.rst.in L57-60](https://github.com/universal-ctags/ctags/blob/5b72de800ae3dfb15473ced6717ba4d7b2859925/man/readtags.1.rst.in#L57-L60)
  - Tags are sorted by name by default. Support for generating reference tags "is new and limited to specific areas". — [man/ctags.1.rst.in L345-349, L1747-1752](https://github.com/universal-ctags/ctags/blob/5b72de800ae3dfb15473ced6717ba4d7b2859925/man/ctags.1.rst.in#L345-L349)

### Inferences
- GLOBAL's GRTAGS record (one per (tag, file), holding a delta+range-encoded line list) has the same shape as Glean's `TargetUses` and Sourcegraph's `codeintel_scip_symbols`, reached independently. Three systems arriving at **(symbol, file) → compressed positions** is a strong signal that it is the right granularity for hot symbols.
- Woboq's "first TU to generate the file owns its refs" is another instance of partitioning by location file, used to avoid de-dup.

### Gaps
- I could not fetch the official GNU GLOBAL manual (gnu.org was blocked). I used an unofficial 2015 mirror at version 6.4. The current upstream is 6.6.x, and the format may differ in details.
- I found no public design documentation of Chromium Code Search's current serving layer beyond "Kythe-powered".

---

## Q6. GitHub stack graphs / precise code navigation: storage and querying at scale

### Takeaway
Stack graphs store **per-file** results, a serialized graph plus precomputed partial paths, in SQLite. At query time they load only the files whose partial paths can match the current symbol stack, by looking up `root_paths` on an indexed `symbol_stack` text key. This gives file-incremental indexing. The design targets go-to-definition-style name resolution; it is not a stored reference table, and GitHub no longer maintains the open-source repo.

### Cited Findings
- SQLite schema (`VERSION = 6`, all tables STRICT):
  - `graphs(file TEXT PRIMARY KEY, tag, error, value BLOB)`;
  - `file_paths(file, local_id, value BLOB)`;
  - `root_paths(file, symbol_stack TEXT, value BLOB)`.
  - Indexes: `idx_graphs_file`, `idx_file_paths_local_id(file, local_id)` and `idx_root_paths_symbol_stack(symbol_stack)`.
  - Pragmas: `journal_mode=WAL`, `foreign_keys=false`, `secure_delete=false`.
  - Values are bincode-encoded.
  - Source: [stack-graphs/src/storage.rs L37-75](https://github.com/github/stack-graphs/blob/fcb7705d5b38ae13b3665a9b2c882e5a97243d44/stack-graphs/src/storage.rs#L37-L75)
- Lookups use `SELECT file,value from root_paths WHERE symbol_stack LIKE ? ESCAPE ?` over generated `storage_key_patterns`, memoizing which stacks are already loaded (`loaded_root_paths`). — [storage.rs L631-680](https://github.com/github/stack-graphs/blob/fcb7705d5b38ae13b3665a9b2c882e5a97243d44/stack-graphs/src/storage.rs#L631-L680)
- The README says: "This repository is no longer supported or updated by GitHub." — [README.md](https://github.com/github/stack-graphs/blob/fcb7705d5b38ae13b3665a9b2c882e5a97243d44/README.md)
- GitHub's 2021-12-09 posts describe stack graphs as file-incremental: the system must reuse results for unchanged files because "in each commit that we receive, it's very likely that only a small number of files have been modified". At query time, data from all files in the commit is merged. (search snippet) — [Introducing stack graphs, GitHub blog](https://github.blog/open-source/introducing-stack-graphs/); [Stack graphs: Name resolution at scale (arXiv 2211.01224)](https://www.arxiv.org/pdf/2211.01224)

### Inferences
- The transferable idea is narrow: store per-file blobs keyed by file plus a small indexed lookup key, then load only what matches. For find-references at your scale, the (symbol, file) blob tables in Q3–Q5 fit better.

### Gaps
- I found no public description of how GitHub serves "find all references" for very hot symbols, such as caps or pagination, in its precise code navigation. The blog pages could not be fetched directly.

---

## Q7. Synthesis: which mechanisms transfer to our two-SQLite-DB design (storage, hot-symbol queries, merging/de-dup, memory/disk)

### Takeaway
Across all systems, nobody materializes and sorts every ref of a hot symbol per request. The common recipe:
1. **Merge by file-level authority**, not position de-dup (clangd, Glean ownership slices, woboq, Sourcegraph skip-paths).
2. **Precompute counts and caller groups** at build time (Kythe `PageIndex.count` / `Total` / `Caller` groups, clangd `RevRefs`).
3. **Store at (symbol, file) granularity**, with compressed positions or at least an index ordered for prefix scans (Glean `TargetUses`, Sourcegraph `codeintel_scip_symbols`, GLOBAL GRTAGS, Kythe columnar keys).
4. **Cap with a has-more flag or cursor plus approximate totals** (clangd 1000 / 10000 with `HasMore`; Kythe 2048 / 10000 with APPROXIMATE totals and a 50 ms leeway; Glean `max_results`/`max_bytes`/`max_time_ms` with continuation; Glass 10000 results and 15 s; Sourcegraph pages of 100 and 500-upload batches).

### Cited Findings
- File-authority merge: [clangd Merge.cpp L125-156](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Merge.cpp#L125-L156); [Glean incrementality.md (slices)](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/incrementality.md); [woboq projectmanager.cpp L77-88](https://github.com/woboq/woboq_codebrowser/blob/ebe91a86e4d06a23f5f7709d081f83e2cc14ef26/generator/projectmanager.cpp#L77-L88); [Sourcegraph types.go SkipPathsByUploadID](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/types.go#L148-L171)
- Precomputed counts and callers: [Kythe serving.proto PageIndex/Caller](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/proto/serving.proto#L265-L379); [Kythe xref_serving.proto 20-caller keys](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/proto/xref_serving.proto#L142-L215); [clangd Dex RevRefs](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/dex/Dex.cpp#L152-L163)
- (symbol, file) granularity: [Glean cxx.angle TargetUses](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/schema/source/cxx.angle#L693-L700); [Sourcegraph squashed.sql codeintel_scip_symbols](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/migrations/codeintel/squashed.sql#L238-L248); [GNU GLOBAL gtagsop.c compact format](https://github.com/harai/gnu-global/blob/f86ba74d867385353815f8656c4a6cf4029c1f0b/libutil/gtagsop.c#L134-L200)
- Caps and continuations: [clangd ClangdMain.cpp L324-330](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/tool/ClangdMain.cpp#L324-L330); [clangd remote Server.cpp L108-112](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/remote/server/Server.cpp#L108-L112); [Kythe xrefs.go L69-73, L293-294](https://github.com/kythe/kythe/blob/69141f022689a611e8a4a1d9b08a3783a2e8a9ed/kythe/go/serving/xrefs/xrefs.go#L293-L294); [Glean glean.thrift L419-448](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/if/glean.thrift#L419-L448); [Glass glass.thrift L23-27](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/glass/if/glass.thrift#L23-L27); [Sourcegraph root_resolver_references.go L19](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/codenav/transport/graphql/root_resolver_references.go#L19)
- Batched caller resolution instead of one lookup per caller: [clangd XRefs.cpp incomingCalls L2573-2650](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/XRefs.cpp#L2573-L2650)
- Memory and disk techniques:
  - clangd packs line/col into 32 bits and interns file strings in an arena. Its `.idx` uses varints and a zlib-compressed sorted string table. ([SymbolLocation.h](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/SymbolLocation.h#L30-L64), [Serialization.cpp](https://github.com/llvm/llvm-project/blob/d78ca659e2b2c89c2dbc0ba2b571761e4d9ee8bd/clang-tools-extra/clangd/index/Serialization.cpp#L158-L200))
  - Sourcegraph uses column-oriented delta varints for ranges and content-hash de-dup of documents. ([ranges.go](https://github.com/sourcegraph/sourcegraph-public-snapshot/blob/c864f15af264f0f456a6d8a83290b5c940715349/internal/codeintel/shared/ranges/ranges.go#L13-L45))
  - GLOBAL uses file IDs and delta/range line lists. ([gtagsop.c](https://github.com/harai/gnu-global/blob/f86ba74d867385353815f8656c4a6cf4029c1f0b/libutil/gtagsop.c#L134-L200))
  - Glean notes the key-stored-twice cost and uses Elias-Fano ownership sets. ([db.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/db.md), [incrementality.md](https://github.com/facebookincubator/Glean/blob/4e576957778b721f28cec21556066a02c3ed84d0/glean/website/docs/implementation/incrementality.md))

### Inferences
These are my proposals for your SQLite design; none were tested here.

1. **Partition rule (no de-dup).**
   - At build time, record in each DB the set of files whose refs it is authoritative for. The engine DB owns the files its TUs produced refs in.
   - For a merged query, take refs from the engine DB for files in engine-owned, and from the project DB for every other file. This is clangd's `indexedFiles` filter. A pure path-prefix rule silently drops engine-header refs that only project TUs saw.
   - Better still, do the filtering **once at load time**: delete project-DB rows whose file is engine-owned. A query then just concatenates the two DBs with no runtime filter or de-dup. This is the clangd/woboq "one owner per file" rule, materialized.
2. **Ordered, limit-able ref access.**
   - Give `refs` a covering composite index, ideally `WITHOUT ROWID` with key `(sym, file_order, line, col, kind)`, where `file_order` is a path-sorted file ID shared by both DBs or a path string.
   - Serve pages with keyset pagination (`WHERE sym=? AND (file_order,line,col) > (?,?,?) ORDER BY ... LIMIT ?`).
   - Merge the two DBs' sorted streams lazily (e.g. `heapq.merge`), so the first page costs O(page) rather than O(N log N).
   - Return `has_more` (clangd) and an opaque cursor that holds the last key (Kythe/Sourcegraph tokens; Glean's saved `(Pid, FactId)` iterator).
3. **Counts precomputed.**
   - Build `ref_counts(sym, kind_mask_bucket, n)`, plus optionally per-(sym, file) counts, at load time.
   - With the partition rule there is no de-dup, so the merged count is `n_engine + n_project`, O(1). Expose "exact" versus "approximate" like Kythe's `TotalsQuality`.
4. **Callers precomputed.**
   - Build `callers(sym, container, n_sites, first_file, first_line)` (Kythe `20-caller` group; clangd groups by `Container`) with an index on `(sym, n_sites DESC)` or `(sym, container)`.
   - Resolve caller names with one JOIN or one batched `IN (...)`, not one query per caller (clangd `incomingCalls`). Cost becomes O(#callers) instead of O(#refs).
5. **Optional compact storage for hot symbols.**
   - Use a `(sym, file) → blob` table with delta+varint column-oriented positions (Sourcegraph, GLOBAL, Glean `TargetUses`) plus a count column.
   - Hot-symbol scans then touch O(files) rows, and paging skips whole files by count (Kythe `skipPage`).
6. **Caps.**
   - Default page ≈ 100–2048 refs and a hard cap ≈ 10k per request, matching clangd, Kythe and Glass.
   - Use a soft time budget that returns partial results plus a cursor (Kythe 50 ms leeway; Glean `max_time_ms`).

### Gaps
- None of the sources publishes latency numbers that compare directly with your measurements (41–45 s at 3.4M refs). The expected speedups above are inferences from algorithmic cost, not measured results.
- How much location-based partitioning loses depends on how many engine-header refs only project TUs see, for example in templates or macros. That has to be measured on your data by comparing engine-file refs in the project DB against the engine DB for the same files.
