# Fast substring / fuzzy symbol-name search at million-symbol scale, and SQLite FTS5 trigram on Windows CPython

Research date: 2026-10-08. Sources were read directly from GitHub (source code, commit messages, CPython build files) and from official python.org NuGet packages, unless noted otherwise. sqlite.org, swtch.com, reviews.llvm.org, lists.llvm.org, docs.google.com, burntsushi.net, nelhage.com and dev.epicgames.com were blocked by this session's egress policy. Facts from those sites come from search-engine snippets and are marked "(via search snippet)". "Local experiment" means a measurement made during this research on Linux, Python 3.13.16 linked against the system SQLite 3.45.1, on a 4-vCPU Xeon @ 2.10 GHz, with **synthetic** CamelCase identifiers. Those numbers are indicative only.

---

## Q1. clangd Dex: design, ranking, memory and latency

### Takeaway
Dex is an in-memory inverted index. Its keys are "fuzzy" trigrams generated along CamelCase/underscore segment boundaries, plus scope, path-proximity, type and code-completion tokens. Each posting list holds symbol IDs sorted by precomputed symbol quality, which lets a LIMIT-ed iterator tree stop early. Candidates are then rescored with FuzzyMatch × quality × boosts. On LLVM (292k symbols) the posting lists took 54.4 MB raw and 23.5 MB after VByte compression, at roughly 1.0–1.2 ms per real query.

### Cited Findings
**Origins and timeline**
- Kirill Bobyrev posted the Dex RFC to clangd-dev/cfe-dev in July 2018. The design doc was a Google Doc (https://docs.google.com/document/d/1C-A6PGT6TynyaX4PXyExNMiGmJ2jL1UwV91Kyx11gOI). The design doc itself was not readable here. — [RFC thread (via search snippet)](http://lists.llvm.org/pipermail/clangd-dev/2018-July/000022.html); [commit 5e82f05e "Introduce Dex symbol index search tokens", 2018-07-25](https://github.com/llvm/llvm-project/commit/5e82f05e7a0b94249f4da48fc6cfe49316c7ee0d)
- That first commit describes search tokens as "Trigrams - these are essential for unqualified symbol name fuzzy search; Scopes for filtering the symbols by the namespace; Paths, e.g. these can be used to uprank symbols defined close to the edited file". On trigram extraction it says "each extracted trigram is a valid sequence for Fuzzy Matcher jumps … trigrams generation algorithm for the query string is different … it simply yields sequences of 3 consecutive lowercased valid characters". — [commit 5e82f05e](https://github.com/llvm/llvm-project/commit/5e82f05e7a0b94249f4da48fc6cfe49316c7ee0d)
- Timeline:
  - Query iterators (AND/OR/Document) landed on 2018-07-26. — [bea258d3](https://github.com/llvm/llvm-project/commit/bea258d3d7ce297807671d493619065a68366347)
  - Incomplete (1–2 character) trigrams for short queries landed on 2018-08-13. — [ff2dd909](https://github.com/llvm/llvm-project/commit/ff2dd9095fa6f0d904f2df6da0f3e281d6bd2ed0)
  - The Dex prototype landed on 2018-08-20. — [870aaf29](https://github.com/llvm/llvm-project/commit/870aaf2963966663cbef71d89817f4ef81a60918)
  - The LIMIT iterator landed on 2018-08-24. — [a98961bc](https://github.com/llvm/llvm-project/commit/a98961bc841fe930b80593af2342fa0c7d28d4f8)
  - Dex became the default static index on 2018-08-28. — [8212eae9](https://github.com/llvm/llvm-project/commit/8212eae99689323fd2585599f132f088615f96a6)
  - Proximity-path boosting landed on 2018-09-06. — [19a9461e](https://github.com/llvm/llvm-project/commit/19a9461e5fc012f58741888243fd6497ebffa6ff)
  - Dex became the default for the dynamic index on 2019-02-07. — [4b68d910](https://github.com/llvm/llvm-project/commit/4b68d910d94b086f95f329f19c185e0aad207486)

**Trigram generation (current `main`, Oct 2026)**
- Header comment: "The symbol's name is broken into segments, e.g. "FooBar" has two segments. Trigrams can start at any character in the input. Then we can choose to move to the next character or to the start of the next segment." It also says: "For "FooBar" we get the following trigrams: {f, fo, fb, foo, fob, fba, oob, oba, bar}. Trigrams are lowercase, as trigram matching is case-insensitive." — [Trigram.h](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Trigram.h)
- Implementation: for each character, `Next[I] = {NextTail, NextHead}`. A trigram is emitted for each I→J→K path where J and K are either the next tail character in the same segment or the head of the next segment. Delimiters are skipped. Short "incomplete trigrams" (unigrams/bigrams) are generated only for the first two segment heads. Example in the source: `"_abc_def_ghi_jkl"` produces `"_", "_a", "a", "ab", "ad", "d", "de", "dg"`. — [Trigram.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Trigram.cpp)
- Query side: query trigrams are only consecutive lowercase letter/digit triples. If the query is too short, one 1–2 character token is used ("to perform prefix match"). — [Trigram.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Trigram.cpp), [Trigram.h](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Trigram.h)
- Build hot path: trigram dedup uses a linear scan for identifiers shorter than 14 characters and sort+unique above that. "The magic number was tuned by running IndexBenchmark.DexBuild." — [Trigram.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Trigram.cpp)
- In 2018, Sam McCall removed "one-segment-skipping" (which let "ab" match `a_yellow_bee`). His commit message: "It costs ~3% of overall ram (~9% of posting list ram) and some quality." — [commit 2ec5a10d, 2018-10-04](https://github.com/llvm/llvm-project/commit/2ec5a10db3c4b843db864fb6702e2b675887a6e8)
- In 2021, Bobyrev changed query trigram generation because `"va_"` produced no trigrams. The resulting query "will discard the query information and return all symbols, some of which will be later be scored expensively". — [commit 976a74d7, 2021-12-07](https://github.com/llvm/llvm-project/commit/976a74d7d2dbd19670614f603caf490cca892fdc)

**Index build and posting lists**
- `Dex::buildIndex` sorts all symbols by `quality(*Sym)` in descending order. The DocID is the rank, so "items in the posting lists are stored in the descending order of symbol quality".
- `IndexBuilder::add` adds each symbol's ID to these posting lists:
  - one per trigram of `Sym.Name` (the unqualified name only)
  - `ScopeDocs[Sym.Scope]`
  - one per proximity URI (each parent directory of the declaration file)
  - `TypeDocs[Sym.Type]`
  - a `RestrictedForCodeCompletion` sentinel
- Source: [Dex.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Dex.cpp)
- Posting lists are VByte-compressed in 32-byte chunks: "Chunk is a fixed-width piece of PostingList which contains the first DocID in uncompressed format (Head) and delta-encoded Payload"; `PayloadSize = 32 - sizeof(DocID)`; `ApproxEntriesPerChunk = 15`. — [PostingList.h](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/PostingList.h), [PostingList.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/PostingList.cpp)
- **Memory and latency numbers** from the VByte commit, measured on the "recent LLVM symbol index (292k symbols)" with 7,751 user-recorded `FuzzyFindRequest`s:

  | Metric | Before | After VByte | Change |
  |---|---|---|---|
  | Memory, posting lists only | 54.4 MB | 23.5 MB | −60% |
  | Time to process all queries | 7.70 s | 9.4 s | +25% |

  — [commit 6c2f5bd0, 2018-09-25 (D52300)](https://github.com/llvm/llvm-project/commit/6c2f5bd0f1b13cc24f85c3c8da8e3667644e485e)
- Iterator cost ordering made queries about 10% faster. Benchmarks: `DexAdHocQueries` 5.88 ms → 5.24 ms per iteration; `DexRealQ` 960 ms → 873 ms for the whole real-query set. — [commit 38bdac5d, 2018-08-30](https://github.com/llvm/llvm-project/commit/38bdac5db854d298013388cd6887f49f56d10ffe)
- Making `advanceTo()` skip binary search when the iterator is already past the target "saves up to 6-7% performance". — [commit 59491a1f](https://github.com/llvm/llvm-project/commit/59491a1fa955da7a5baa9182722f655cb4496881)
- In 2021, AND-iterator early reset based on child size estimates gave "45-60%" faster queries: "on small queries it is close to 45% but the longer they go the closer it gets to 60% and beyond". — [commit a0987e35, 2021-07-23 (D106528)](https://github.com/llvm/llvm-project/commit/a0987e350ccce4fb9c3cbaf56732be1def5f810f)
- Using Dex for the dynamic index cost memory. For a sample TU: "Without Dex: 17.9M, With Dex: 24.4M … considerable but seems tolerable". — [commit 4b68d910, 2019-02-07](https://github.com/llvm/llvm-project/commit/4b68d910d94b086f95f329f19c185e0aad207486)
- The on-disk index format (RIFF, compressed string table, varints) is "~10x more compact than YAML … llvmidx.riff = 20M, llvmidx.yaml = 272M, llvmidx.yaml.gz = 32M". — [commit 50f36310, 2018-09-04](https://github.com/llvm/llvm-project/commit/50f3631057f717448ba34b4175daaa81215fbd5e)
- The clangd docs say a whole-project index for Chromium-sized code can take "multiple hours … to build" and "induces a large memory overhead (multiple GB of RAM) to serve within clangd", which is the motivation for the remote index. — [clangd-www design/indexing.md](https://github.com/llvm/clangd-www/blob/main/design/indexing.md)

**Query tree and scoring (`Dex::fuzzyFind`)**
- Query tree: `AND( AND(trigram iterators), OR(scope iterators [+ BOOST(ALL, 0.2) if AnyScope]), OR(BOOST(proximity URI)…, ALL), OR(BOOST(type)…, ALL), [RestrictedForCodeCompletion] )`, wrapped in `LIMIT(Req.Limit * 100)` ("Retrieve more items than it was requested … FIXME: Tune this ratio").
- Every surviving candidate is rescored with `FuzzyMatcher.match(Sym->Name)`: `FinalScore = FuzzyScore * SymbolQuality * boost`, and a TopN heap keeps the best `Limit`.
- Queries shorter than 3 characters set `More = true` "for short queries we use specialized trigrams that don't yield all results".
- Source for all three points: [Dex.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Dex.cpp)
- Iterator model: "Inverted index maps these tokens to the posting lists - sorted (by symbol quality) sequences of symbol IDs … Having the resulting IDs sorted is important, because it allows receiving a certain number of the most valuable items … without processing all items". — [Iterator.h](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Iterator.h)
- Quality signals:
  - References: "Sample data points: (10, 1.00), (100, 1.41), (1000, 1.82)", computed as `Score *= 6.0*(1-S)/(1+S)+0.59` with `S = References^-0.06`.
  - Deprecated ×0.1; implementation detail ×0.2.
  - Scope-proximity score range [0.6, 2]; file proximity `exp(FileDistance * -0.4 / UpCost)`.
  - Source: [Quality.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/Quality.cpp)
- FuzzyMatch: a DP over (pattern prefix × word prefix), with bonuses and penalties for case match and segment alignment. "The first pattern character may only match the start of a word segment." "This algorithm was inspired by VS code's client-side filtering." Limits are `MaxPat = 63, MaxWord = 127`. Scores are in [0,1], or up to 2 when the pattern is the full word. — [FuzzyMatch.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/FuzzyMatch.cpp), [FuzzyMatch.h](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/FuzzyMatch.h)
- LSP `workspace/symbol` (`getWorkspaceSymbols`):
  - splits the query into scope and name;
  - sets `AnyScope = !HasLeadingColons`;
  - multiplies the limit by 5 when AnyScope is used with scopes;
  - post-filters with `approximateScopeMatch`;
  - re-ranks with `SymbolQualitySignals`/`SymbolRelevanceSignals`.
  - Source: [FindSymbols.cpp](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/FindSymbols.cpp)

### Inferences
- Average latency per query, derived from the VByte commit: 7.70 s / 7,751 ≈ 1.0 ms before compression and 9.4 s / 7,751 ≈ 1.2 ms after, on 292k symbols.
- Posting-list memory per symbol, derived: 23.5 MB / 292k ≈ 80 bytes. This covers trigram, scope, proximity and type tokens, all in RAM, plus the symbol slab. Scaling linearly to 1M symbols gives about 80 MB, and to 5M about 400 MB (inferred, not measured).
- Dex's "fuzzy trigrams" are a superset of contiguous trigrams, plus head-jump trigrams. Because every character's next character is either the next tail or the next head, every contiguous substring of length ≥ 3 is covered. A query like "gap" also matches `GetAbilityPointer` (g→a→p via segment heads), which a plain substring trigram index such as FTS5 cannot do.
- Dex does not try to return exact substring results from the index alone. The index produces a candidate superset, which is capped at 100×Limit and ordered by quality. FuzzyMatcher then filters it. Early termination plus a quality-sorted DocID order is what keeps latency flat as the corpus grows.

### Gaps
- The 2018 Google design doc and the Phabricator reviews (D50337, D52300) were not readable from this session, because docs.google.com and reviews.llvm.org are blocked. Any extra numbers in them are not captured.
- No published Dex memory or latency figures at Unreal Engine scale (millions of symbols) were found.

---

## Q2. Google Code Search (Russ Cox), Zoekt, livegrep: index structures, size vs corpus, latency

### Takeaway
These tools cover three size/speed trade-offs:
- **Code Search** posting lists store file IDs only. The index is about 18% of the corpus, and the trigrams narrow candidates by orders of magnitude.
- **Zoekt** stores positional trigrams, so an index is about 3–3.5× the corpus. It needs only two posting-list lookups per substring and targets under 50 ms on Android/Chrome-sized code.
- **livegrep** uses a suffix array of about 3–5× the corpus, memory-mapped.

All three index file contents, not a symbol table. Zoekt uses ctags only as a ranking signal.

### Cited Findings
- **Russ Cox Code Search (2012 article; the codesearch Go repo README is dated June 2015):**
  - "Indexing the Linux 3.1.3 kernel sources, a total of 420 MB, creates a 77 MB index" (about 18%).
  - For "hello world" the index "narrows the search from 36,972 files to 25 files and cuts the time required for the search by about 100x". Sample timings: 0.01 s with the index vs 1.96 s for the brute-force run.
  - Source: [swtch.com regexp4 (via search snippet)](https://swtch.com/~rsc/regexp/regexp4.html); README: [google/codesearch README](https://github.com/google/codesearch/blob/master/README)
- Code Search on-disk format:
  - "The list of posting lists is a sequence of posting lists. Each posting list has the form: trigram [3] deltas [v]..." The deltas are between **file IDs**; there are no positions.
  - "Index entries are only written for the non-empty posting lists … finding the posting list for a specific trigram requires a binary search over the posting list index."
  - Source: [index/read.go](https://github.com/google/codesearch/blob/master/index/read.go)
- The indexer skips files longer than `maxFileLen = 1<<30`, files with lines longer than `maxLineLen = 2000`, and files with more than `maxTextTrigrams = 20000` distinct trigrams ("probably not text"). — [index/write.go](https://github.com/google/codesearch/blob/master/index/write.go)
- **Zoekt (Sourcegraph):**
  - Goal: "sub-50ms results on large codebases, such as Android (~2G text) or Chrome".
  - "Positional trigrams … we store the offset of each ngram's occurrence within a file … we only have to intersect just a couple of posting-lists: one for the beginning, and one for the end … we can select any pair of trigrams from the pattern for which the number of matches is minimal."
  - Size: "The index is large. Empirically, it is about 3x the corpus size, composed of 2x (offsets), and 1x (original content)."
  - Memory: "searching with positional trigrams only requires 1.2x corpus size of RAM."
  - Shards: "In practice, the shard size is about 3.5x the corpus size … uint32 for all offsets, so the total size of a shard should be below 4G … caps content size per shard at 1G."
  - Source: [zoekt doc/design.md](https://github.com/sourcegraph/zoekt/blob/main/doc/design.md)
- Zoekt case-insensitive search: "we look for occurrences of all the different case variants, ie. {"abc", "Abc", "aBc", …}, and then compare the candidate matches without regard for case." — [zoekt design.md](https://github.com/sourcegraph/zoekt/blob/main/doc/design.md)
- Zoekt ranking signals listed in the design doc: "number of atoms matched; closeness …; quality of match: does match boundary coincide with a word boundary?; … symbol ranking: is the match a symbol definition? … programs to do this already exist, eg. `ctags`". There is also an optional BM25 mode (`UseBM25Scoring`). — [zoekt design.md](https://github.com/sourcegraph/zoekt/blob/main/doc/design.md)
- In the code, `scoreLine` adds "WordMatch", "PartialWordMatch", "Symbol"/"EdgeSymbol" and per-language "kind:<lang>:<kind>" scores. ctags must be universal-ctags. — [zoekt index/score.go](https://github.com/sourcegraph/zoekt/blob/main/index/score.go), [doc/ctags.md](https://github.com/sourcegraph/zoekt/blob/main/doc/ctags.md)
- **livegrep:** "The index file will vary somewhat in size, but will usually be 3-5x the size of the indexed text. `livegrep` memory-maps the index file into RAM, so it can work out of index files larger than (available) RAM, but will perform better if the file can be loaded entirely into memory." — [livegrep README](https://github.com/livegrep/livegrep/blob/main/README.md)
- livegrep builds a suffix array over all source concatenated into a single buffer, using libdivsufsort. — [Nelson Elhage 2015 (via search snippet)](https://blog.nelhage.com/2015/02/regular-expression-search-with-suffix-arrays/)
- Zoekt's own comparison: suffix arrays can't turn regexps into index ranges either, while positional trigrams allow straightforward incremental builds. — [zoekt design.md](https://github.com/sourcegraph/zoekt/blob/main/doc/design.md)
- Older livegrep forks' READMEs reportedly said the index was "approximately the same size as the original source code", which conflicts with the current "3-5x" figure. — (via search snippet only; the current README above is authoritative.)

### Inferences
- For a **symbol-name** corpus of about 1M names averaging about 20 characters (about 20 MB of text), these ratios suggest:
  - a non-positional trigram index of tens of MB;
  - a positional index of about 60 MB plus content;
  - a suffix array of about 60–100 MB.
- These are rough extrapolations of the ratios above, not measurements. A symbol corpus is tiny compared with source text, so any of these fits in RAM.
- The local FTS5 numbers (Q4) fall in the same range: 32 MB for name-only with detail=none (≈1.6× the name text) up to 261 MB for name+qname with detail=full.

### Gaps
- The exact query latency distribution from Russ Cox's article and Elhage's suffix-array numbers could not be read directly (blocked sites).
- No primary source measured these tools specifically on identifier lists.

---

## Q3. Alternatives specialized for identifier search

### Takeaway
Identifier search is best served by segment-aware structures rather than raw substring indexes:
- CamelCase/underscore segmentation (Dex fuzzy trigrams, IntelliJ camel-hump matching, VS Code separator/camel bonuses);
- word-start or initials tokens;
- prefix-searchable sorted dictionaries (B-tree, ctags binary search, FST).

Raw substring indexes (trigram, suffix array) answer "contains" queries but cannot do "GAP → GetAbilityPointer".

### Cited Findings
- **Dex fuzzy trigrams** include head-jump trigrams, so abbreviations along segment heads are indexed. See Q1. — [Trigram.h](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/index/dex/Trigram.h)
- clangd segmentation roles: "e.g. XMLHttpRequest_Async … Head / Tail / Separator"; "[lol] matches "LaughingOutLoud" better than "LionPopulation"". Non-ASCII bytes are treated as lowercase and need exact case. — [FuzzyMatch.h](https://github.com/llvm/llvm-project/blob/main/clang-tools-extra/clangd/FuzzyMatch.h)
- **IntelliJ** `MinusculeMatcherImpl`: "Tells whether a string matches a specific pattern. Allows for lowercase camel-hump matching. Used in navigation, code completion, speed search etc." — [MinusculeMatcherImpl.kt](https://github.com/JetBrains/intellij-community/blob/master/platform/util/text-matching/src/com/intellij/psi/codeStyle/MinusculeMatcherImpl.kt)
- **VS Code** `fuzzyScorer.ts`:
  - "Consecutive match bonus: sequences up to 3 get the full bonus";
  - an "After separator bonus" (path separators 5, other separators 4);
  - "Inside word upper case bonus (camel case)".
  - Source: [vscode src/vs/base/common/fuzzyScorer.ts](https://github.com/microsoft/vscode/blob/main/src/vs/base/common/fuzzyScorer.ts)
- **ctags readtags:** "The NAME action will perform binary search on sorted (including "foldcase") tags files, which is much faster then on unsorted tags files." Flags `-i/--icase-match` and `-p/--prefix-match` are supported. That means exact or prefix lookup only, with no substring support. — [universal-ctags man/readtags.1.rst.in](https://github.com/universal-ctags/ctags/blob/master/man/readtags.1.rst.in)
- **FST (BurntSushi `fst` crate):** "ordered sets and maps using finite state machines … store keys in a compact format that is also easily searchable … range queries very fast". Automata such as DFAs from `regex-automata` can search an FST. — [BurntSushi/fst README](https://github.com/BurntSushi/fst/blob/master/README.md)
  - The accompanying blog: about 16M Wikipedia titles (384 MB) gave a 157 MB FST, and the experiments go up to 1.6B URLs (134 GB). — [burntsushi.net/transducers (via search snippet)](https://burntsushi.net/transducers/)
  - An FST is a prefix/automaton structure. Substring search over it needs a scan of the automaton, or indexing suffixes/segments as keys (inferred).
- **Local experiment, 1M synthetic identifiers.** Segment-oriented alternatives built inside SQLite with the standard library only:
  - **Initials column + B-tree:** a computed column `initials` (lowercase segment heads, e.g. `GetAbilityPointer` → `gap`) with a B-tree index added +12.9 MB and built in 2.4 s. `initials LIKE 'urs%'` used `SEARCH … USING COVERING INDEX` and returned 278 rows in 0.09 ms (0.04 ms with LIMIT 100).
  - **Word-start FTS5:** FTS5 `unicode61`, `detail='none'`, `prefix='2 3'` over space-separated segments ("Get Ability Pointer") added +22.4 MB and built in 3.6 s.
    - `MATCH 'paw*'` returned 26,800 rows in 7.6 ms.
    - `MATCH 'nav* AND mesh*'` returned 1,409 rows in 14 ms.
  - Script: `scratchpad/exp/fts_exp2.py` (local experiment).

### Inferences
- A practical layered design for SQLite+stdlib could be:
  1. exact match (B-tree);
  2. prefix on NOCASE name (B-tree);
  3. initials/abbreviation prefix (B-tree on a computed initials column), for queries like "GAP";
  4. word-start prefix tokens (FTS5 unicode61 with a prefix index, or a token table), for queries like "Abil";
  5. arbitrary substring (FTS5 trigram), for queries like "bilityPo";
  6. a final Python-side fuzzy score (Dex/VS Code style: segment-start bonus, consecutive bonus, case bonus, reference-count quality) over a bounded candidate set.
- A Dex-style "fuzzy trigram" index could also be emulated in SQLite: store Dex-style head-jump trigrams as tokens in a `(trigram, symbol_id)` table or as a space-separated column in FTS5 unicode61. Cost would be about 4 trigrams per character in the worst case, per the Dex algorithm. This is an inferred design option, not measured.

### Gaps
- How IntelliJ's "Go to Symbol" enumerates candidate names (stub-index name lists vs a dedicated structure) and its latency at million scale were not verified.
- How Lucene/tantivy use an FST term dictionary was not verified from primary sources in this session (the docs sites were blocked).

---

## Q4. SQLite FTS5 `trigram` tokenizer: version, behavior, options, size, performance

### Takeaway
- **Availability:** the trigram tokenizer exists from SQLite **3.34.0**. Its `remove_diacritics` option arrived in **3.45.0**, and a crash on a malformed option was fixed in **3.47.0**.
- **LIKE/GLOB:** when `case_sensitive=0` (the default) it accelerates LIKE, and GLOB too. Pattern segments shorter than 3 characters give no index help, which means a full scan of the FTS table.
- **detail='none':** cuts index size about 4× in the local experiment. It still supports LIKE (converted to an AND of trigrams plus a recheck), but not phrase MATCH.
- **Where it pays off:** rare or no-hit substrings (100+ ms → 0.1–17 ms locally).
- **Where it doesn't:** very frequent substrings without LIMIT, because recheck and content fetch dominate.

### Cited Findings
- **Introduced in 3.34.0.** `fts5TriCreate` is absent from `ext/fts5/fts5_tokenize.c` at tag `version-3.33.0` and present at `version-3.34.0`. `sqlite3Fts5ExprPattern` (LIKE/GLOB → MATCH) and `fts5ParsePhraseToAnd` (detail=column/none support) also first appear in 3.34.0. — [fts5_tokenize.c @ version-3.34.0](https://github.com/sqlite/sqlite/blob/version-3.34.0/ext/fts5/fts5_tokenize.c), [fts5_expr.c @ version-3.34.0](https://github.com/sqlite/sqlite/blob/version-3.34.0/ext/fts5/fts5_expr.c), [@ version-3.33.0](https://github.com/sqlite/sqlite/blob/version-3.33.0/ext/fts5/fts5_tokenize.c)
- **Options** (source at master, SQLite 3.54.0 dev):
  - `case_sensitive` must be `0` or `1`. The default `bFold = 1` means case-insensitive.
  - `remove_diacritics` accepts `0`, `1` or `2` and sets `iFoldParam = 2` if non-zero.
  - Any other option → `SQLITE_ERROR`.
  - Source: [fts5_tokenize.c](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_tokenize.c)
- `remove_diacritics` parsing inside `fts5TriCreate` first appears at `version-3.45.0`. It is absent at 3.44.0. — [fts5_tokenize.c @ version-3.45.0](https://github.com/sqlite/sqlite/blob/version-3.45.0/ext/fts5/fts5_tokenize.c)
- **LIKE vs GLOB acceleration**, quoted from the source:
  > "trigram" tokenizer, case_sensitive=1 - FTS5_PATTERN_GLOB / "trigram" tokenizer, case_sensitive=0 (the default) - FTS5_PATTERN_LIKE / all other tokenizers - FTS5_PATTERN_NONE

  Pattern support is returned only when `iFoldParam==0`, i.e. `remove_diacritics` is not set. — [fts5_tokenize.c `sqlite3Fts5TokenizerPattern`](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_tokenize.c)
  - In `fts5UsePatternMatch`, a LIKE-type index accepts **both** LIKE and GLOB constraints, while a GLOB-type index accepts only GLOB. — [fts5_main.c](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_main.c)
  - The LIKE/GLOB constraint is passed to FTS5 **without** `aConstraintUsage[i].omit = 1`, unlike MATCH. So SQLite core re-evaluates LIKE on every candidate row and results are exact. — [fts5_main.c `fts5BestIndexMethod`](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_main.c)
- **3-character minimum.** `sqlite3Fts5ExprPattern` builds "an FTS5 MATCH expression that will match a superset of the rows matched by the LIKE or GLOB". Only literal runs with `fts5ExprCountChar(...) >= 3` characters between wildcards (`_ %` for LIKE, `* ? [` for GLOB) become phrases. If no run qualifies, `*pp = 0`, i.e. no index constraint and a full scan.
  - If `eDetail != FTS5_DETAIL_FULL`, phrases become an AND of trigrams (`bAnd = 1`).
  - If `detail=none`, `iCol = pConfig->nCol`, meaning the column restriction is dropped and trigrams from any indexed column count.
  - Source: [fts5_expr.c](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_expr.c)
- A 2023 check-in fixed LIKE/GLOB patterns whose literal runs are 2 characters or fewer but 3+ UTF-8 bytes. — [sqlite.org check-in (via search snippet)](https://sqlite.org/src/info/0d50172477064dce)
- **Malformed option crash:** `tokenize='trigram case_sensitive'` (missing value) **segfaulted** (exit 139) with SQLite 3.45.1 in the local experiment. The `nArg%2` guard is missing in source at `version-3.45.1` and `version-3.46.1` and present from `version-3.47.0`. A crash report about the missing-value case was filed in Aug 2024. — local experiment; [fts5_tokenize.c @ version-3.47.0](https://github.com/sqlite/sqlite/blob/version-3.47.0/ext/fts5/fts5_tokenize.c); [SQLite forum (via search snippet)](https://sqlite.org/forum/forumpost/171bcc2bcd)
- **detail=none/column limitation (local experiment):** `MATCH '"pawnc"'` on a `detail='none'` trigram table raised `fts5: phrase queries are not supported (detail!=full)`. LIKE still works there because of the automatic phrase→AND conversion above.
- **Local experiment 1 — size and latency.**
  - Setup: 1M synthetic symbols; average name 19.4 chars, average qname 48.0 chars; external-content FTS5 (`content='sym', content_rowid='id'`, filled with `INSERT INTO sf(sf) VALUES('rebuild')`); VACUUMed; base table 78.8 MB.
  - Overhead and build time:

    | Configuration | FTS overhead | Build |
    |---|---|---|
    | name+qname, detail=full | +260.8 MB | 14.6 s |
    | name+qname, detail=column | +168.6 MB | 11.8 s |
    | name+qname, detail=none | +61.4 MB | 6.9 s |
    | name only, detail=full | +66.9 MB | 3.5 s |
    | name only, detail=none | +31.7 MB | 2.7–5.3 s across two runs |

  - Query latency (`name LIKE …`, no LIMIT, FTS vs plain table scan):

    | Pattern | Hits | FTS5 | Plain scan |
    |---|---|---|---|
    | `%zzq%` | 0 | 0.1–0.2 ms | 77–87 ms |
    | `%abilitypo%` | 0 | 1.3–2.2 ms | 122–135 ms |
    | `%navmeshpath%` | 3 | 5–17 ms | 117–152 ms |
    | `%pawn%` / `%Comp%` | ~60k each (6% of rows) | 81–175 ms | 120–192 ms (little gain) |
    | `%ab%` (2-char literal → no trigram) | — | 242–313 ms | 137–169 ms |

    The 2-character case is **slower** through FTS than a plain base-table scan.
  - Script: `scratchpad/exp/fts_exp.py`.
  - These sizes are consistent with the user's prototype (216 MB and 11.5 s at 1M, name+qname, detail=full, SQLite 3.45.1).
- **Local experiment 2 — LIMIT, recheck cost and ordering:**
  - `LIKE '%pawn%' LIMIT 100` took 0.13 ms via FTS and 0.18 ms via a base scan; the early stop makes both cheap.
  - Over the same 60,203 candidates, `MATCH 'paw AND awn'` (no recheck) took 20 ms vs 95 ms for `LIKE '%pawn%'`. This isolates the per-row LIKE recheck plus content-table fetch cost.
  - Joining to the base table with `ORDER BY length(name) LIMIT 50` took 94 ms, because all matches must be materialized to sort.
  - Script: `scratchpad/exp/fts_exp2.py`.
- **Forum data point on detail=none** (Enron mail corpus): FTS data was "just under 32% of the total database" with defaults and "around 7.6%" with detail=none. — [SQLite forum (via search snippet)](https://sqlite.org/forum/info/3baccecae55769ff)
- External content tables require the application to keep the index in sync, via triggers or `'rebuild'`. This is standard FTS5 behavior; the official fts5.html could not be fetched to quote it (see Gaps). The `rebuild` command was used and worked in the local experiments.

### Inferences
- **Size:**
  - For name+qname, detail=none cuts FTS overhead about 4.2× (261 → 61 MB) and build time about 2×.
  - Indexing name only with detail=none cuts it about 8× (261 → 32 MB, about 32 bytes/symbol).
  - At 5M symbols, linear extrapolation gives about 160 MB (name-only, detail=none) vs about 1.3 GB (name+qname, detail=full). This is inferred; real UE names will differ.
- **Speed:** detail=none loses no correctness for LIKE because of the recheck. It loses some selectivity, since AND of trigrams instead of positions gives more false-positive candidates to recheck. For short identifiers that cost looked small locally: `%navmeshpath%` took 10 ms with detail=none vs 17 ms with detail=full.
- **qname:** with detail=none, the column filter is dropped, so trigrams from qname also make rows candidates for `name LIKE`. Use a name-only trigram table, or separate tables per column, to avoid extra rechecks. Scope/qname matching may be better served by prefix/segment indexes on qname (e.g. `UE::Net::` scope token).
- **Query routing:**
  - If the query has fewer than 3 characters (or a literal run under 3), skip FTS and use the base-table prefix index, or a scan with LIMIT.
  - Always use LIMIT (e.g. 200–500 candidates) and rank in Python. Avoid `ORDER BY` over the whole match set.
  - For frequent substrings, consider using MATCH with explicit trigrams for candidate IDs, then fetch only the top-K rows.
- Never build tokenizer option strings from user input on SQLite < 3.47, because of the segfault.

### Gaps
- The official https://www.sqlite.org/fts5.html text (exact wording on the 3-char rule, detail-option size guidance, `contentless_delete`, `secure-delete`, `pgsz`, `automerge`, `optimize`) could not be fetched, because sqlite.org is blocked. Behavior above is taken from source code and local tests instead.
- No official SQLite-published benchmark of trigram index size and latency was found.
- The local experiment used a synthetic vocabulary. Frequency distributions for real UE identifiers (e.g. "Get", "Component", "UE") will change hit counts and the frequent-term timings.

---

## Q5. Availability: FTS5 + trigram in Windows Python builds (python.org 3.10–3.15, Store / install manager, NuGet, embeddable, conda, uv, Unreal)

### Takeaway
**Definitive for python.org Windows builds: yes.**
- Every CPython 3.10–3.15 Windows build compiles its bundled `sqlite3.dll` with `SQLITE_ENABLE_FTS5`; `PCbuild/sqlite3.vcxproj` has carried this since at least 3.6.0.
- The oldest bundled SQLite in any 3.10+ release is 3.35.5, which is at least 3.34.0, so the trigram tokenizer is always present.
- This was verified in the shipped binaries: the `sqlite3.dll` from python.org NuGet packages 3.10.0, 3.10.11, 3.11.8, 3.11.9, 3.12.10, 3.13.16, 3.14.8 and 3.15.0rc3 all contain the `ENABLE_FTS5` compile option and the `trigram` tokenizer name.
- conda (conda-forge and Anaconda defaults) also enables FTS5.
- Unreal Engine's bundled Python is 3.11.x per Epic. Whether it ships `_sqlite3` at all could not be verified.

### Cited Findings
- **Build flags (quoted), `PCbuild/sqlite3.vcxproj` line 101:**
  - 3.10 branch: `<PreprocessorDefinitions>SQLITE_ENABLE_MATH_FUNCTIONS;SQLITE_ENABLE_JSON1;SQLITE_ENABLE_FTS4;SQLITE_ENABLE_FTS5;SQLITE_ENABLE_RTREE;SQLITE_API=__declspec(dllexport);%(PreprocessorDefinitions)</PreprocessorDefinitions>` — [cpython 3.10 PCbuild/sqlite3.vcxproj](https://github.com/python/cpython/blob/3.10/PCbuild/sqlite3.vcxproj)
  - 3.11, 3.12, 3.13 and 3.14 branches: `<PreprocessorDefinitions>SQLITE_ENABLE_MATH_FUNCTIONS;SQLITE_ENABLE_FTS4;SQLITE_ENABLE_FTS5;SQLITE_ENABLE_RTREE;SQLITE_OMIT_AUTOINIT;SQLITE_API=__declspec(dllexport);%(PreprocessorDefinitions)</PreprocessorDefinitions>` — [3.11](https://github.com/python/cpython/blob/3.11/PCbuild/sqlite3.vcxproj), [3.12](https://github.com/python/cpython/blob/3.12/PCbuild/sqlite3.vcxproj), [3.13](https://github.com/python/cpython/blob/3.13/PCbuild/sqlite3.vcxproj), [3.14](https://github.com/python/cpython/blob/3.14/PCbuild/sqlite3.vcxproj)
  - `main` (3.16 dev) additionally has `SQLITE_ENABLE_PERCENTILE`. — [main PCbuild/sqlite3.vcxproj](https://github.com/python/cpython/blob/main/PCbuild/sqlite3.vcxproj)
  - `SQLITE_ENABLE_FTS4;SQLITE_ENABLE_FTS5` is already present at tags v3.6.0, v3.7.0, v3.8.0 and v3.9.0. — [v3.6.0 sqlite3.vcxproj](https://github.com/python/cpython/blob/v3.6.0/PCbuild/sqlite3.vcxproj)
- **SQLite version pins:**
  - `PCbuild/python.props` sets `<sqlite3Dir Condition="$(sqlite3Dir) == ''">$(ExternalsDir)sqlite-3.50.4.0\</sqlite3Dir>` on the 3.13/3.14 branches (3.14: line 78).
  - `PCbuild/get_externals.bat` sets `set libraries=%libraries% sqlite-3.50.4.0`.
  - Source: [3.14 python.props](https://github.com/python/cpython/blob/3.14/PCbuild/python.props), [3.14 get_externals.bat](https://github.com/python/cpython/blob/3.14/PCbuild/get_externals.bat)
- **Per-release mapping** read from `PCbuild/python.props` at each release tag (`https://github.com/python/cpython/blob/<tag>/PCbuild/python.props`):

  | Python | Bundled SQLite |
  |---|---|
  | 3.10.0–3.10.2 | 3.35.5 |
  | 3.10.3–3.10.8 | 3.37.2 |
  | 3.10.9–3.10.10 | 3.39.4 |
  | 3.10.11–3.10.22 | 3.40.1 |
  | 3.11.0 | 3.38.4 |
  | 3.11.1–3.11.2 | 3.39.4 |
  | 3.11.3 | 3.40.1 |
  | 3.11.4–3.11.6 | 3.42.0 |
  | 3.11.7–3.11.8 | 3.43.1 |
  | 3.11.9–3.11.17 | 3.45.1 |
  | 3.12.0 | 3.42.0 |
  | 3.12.1–3.12.2 | 3.43.1 |
  | 3.12.3 | 3.45.1 |
  | 3.12.4–3.12.9 | 3.45.3 |
  | 3.12.10–3.12.15 | 3.49.1 |
  | 3.13.0–3.13.2 | 3.45.3 |
  | 3.13.3–3.13.5 | 3.49.1 |
  | 3.13.6–3.13.16 | 3.50.4 |
  | 3.14.0–3.14.8 | 3.50.4 |
  | 3.15.0rc3 | 3.53.4 |

  Every 3.10+ tag has `SQLITE_ENABLE_FTS5`. — e.g. [v3.11.9 python.props](https://github.com/python/cpython/blob/v3.11.9/PCbuild/python.props), [v3.12.10 python.props](https://github.com/python/cpython/blob/v3.12.10/PCbuild/python.props), [v3.15.0rc3 python.props](https://github.com/python/cpython/blob/v3.15.0rc3/PCbuild/python.props)
- **Which releases actually have Windows binaries.**
  - PEP 619: 3.10.11 is the "Final regular bugfix release with binary installers"; later 3.10.x releases are source-only security releases; "As of 2026-10-01, 3.10 has reached the end-of-life phase" (3.10.22 released 2026-10-01). — [PEP 619](https://github.com/python/peps/blob/main/peps/pep-0619.rst)
  - PEP 664: "3.11.9: Tuesday, 2024-04-02 (Final regular bugfix release with binary installers)". — [PEP 664](https://github.com/python/peps/blob/main/peps/pep-0664.rst)
  - The official `python` NuGet package versions stop at 3.10.11, 3.11.9 and 3.12.10, and continue to 3.13.16, 3.14.8 and 3.15.0-rc3 as of 2026-10-08. — [NuGet index](https://api.nuget.org/v3-flatcontainer/python/index.json), [nuget.org/packages/python](https://www.nuget.org/packages/python)
- **Binary verification.** `tools/DLLs/sqlite3.dll` was extracted from the official NuGet packages and its strings inspected:

  | NuGet package | Bundled SQLite (version string or source-id) | ENABLE_FTS5 | "trigram" | Other tokenizer strings |
  |---|---|---|---|---|
  | 3.10.0 | `3.35.5` | yes | yes | ENABLE_FTS4, ENABLE_JSON1 |
  | 3.10.11 | `3.40.1` | yes | yes | |
  | 3.11.8 | source-id `2023-09-11 …2d3a40c05c49e1a49264` (= 3.43.1 per tag) | yes | yes | |
  | 3.11.9 | source-id `2024-01-30` (= 3.45.1) | yes | yes | |
  | 3.12.10 | `2025-02-18` (= 3.49.1) | yes | yes | adds `contentless_unindexed`, `locale`, `insttoken` |
  | 3.13.16 and 3.14.8 | `2025-07-30 …4d8adfb30e03f9cf27f8` (= 3.50.4) | yes | yes | |
  | 3.15.0rc3 | `2026-07-24` (= 3.53.4 per tag) | yes | yes | adds ENABLE_PERCENTILE |

  All carry `THREADSAFE=1`. — [api.nuget.org flat container, e.g. python.3.13.16.nupkg](https://api.nuget.org/v3-flatcontainer/python/3.13.16/python.3.13.16.nupkg) (local inspection)
- **Distribution channels (CPython docs, 3.14):**
  - "To obtain Python from the CPython team, use the Python Install Manager … from python.org/downloads or through the Microsoft Store app … The two versions are identical."
  - "Python can also be obtained as NuGet packages"; embeddable distros "can be installed using the Python install manager".
  - The traditional full installer "is deprecated since 3.14 and will not be produced for Python 3.16 or later"; the `py` launcher MSI is also deprecated since 3.14.
  - Source: [Doc/using/windows.rst @3.14](https://github.com/python/cpython/blob/3.14/Doc/using/windows.rst)
- The CPython Windows layout script, which builds the appx/Store, NuGet and embeddable packages, copies all build `.pyd`/`.dll` files except `EXCLUDE_FROM_DLLS = FileStemSet("python*", "pyshellext", "vcruntime*")`, test modules, and Tcl/Tk unless requested. There is no SQLite exclusion. — [PC/layout/main.py @3.13](https://github.com/python/cpython/blob/3.13/PC/layout/main.py), [PC/layout/support/options.py](https://github.com/python/cpython/blob/3.13/PC/layout/support/options.py)
- **conda-forge** `sqlite-feedstock` `recipe/bld.bat` includes `-DSQLITE_ENABLE_FTS3 … -DSQLITE_ENABLE_FTS4 ^ -DSQLITE_ENABLE_FTS5 ^ …`, and the recipe version at fetch time is `3.53.4`. — [conda-forge bld.bat](https://github.com/conda-forge/sqlite-feedstock/blob/main/recipe/bld.bat), [meta.yaml](https://github.com/conda-forge/sqlite-feedstock/blob/main/recipe/meta.yaml)
- **Anaconda defaults** `AnacondaRecipes/sqlite-feedstock` `bld.bat` builds `sqlite3.dll` with `/DSQLITE_ENABLE_FTS5`. — [AnacondaRecipes bld.bat](https://github.com/AnacondaRecipes/sqlite-feedstock/blob/master/recipe/bld.bat)
- **uv / python-build-standalone (Windows):** `build.py` rewrites `<sqlite3Dir>` in `python.props` to its own `sqlite-autoconf-<version>` and patches `PCbuild/sqlite3.vcxproj` version detection. It builds through CPython's own `sqlite3.vcxproj`. — [astral-sh/python-build-standalone cpython-windows/build.py](https://github.com/astral-sh/python-build-standalone/blob/main/cpython-windows/build.py)
- **Unreal Engine:**
  - Epic's docs state "The Python Editor Script Plugin contains an embedded version of Python 3.11.8", and that using another version needs `UE_PYTHON_DIR` plus an engine rebuild.
  - A UE forum thread says UE 5.8 is still on Python 3.11, and Epic staff said an upgrade to 3.13 would not land as a 5.8 hotfix.
  - The UE 4.26 docs listed Python 3.7.7.
  - Source (all via search snippets): [Epic docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python), [UE forum](https://forums.unrealengine.com/t/unreal-engine-5-8-is-on-python-3-11-when-the-vfx-reference-platform-2026-recommends-python-3-13-as-minimum-version/2745703), [UE 4.26 docs](https://docs.unrealengine.com/4.26/ProductionPipelines/ScriptingAndAutomation/Python)
  - No source was found listing whether `Engine/Binaries/ThirdParty/Python3/Win64` includes `DLLs/_sqlite3.pyd` and `sqlite3.dll`. Searches only returned third-party UE SQLite plugins and generic "DLL load failed while importing _sqlite3" reports. — [search results summary](https://bugs.python.org/issue43201)

### Inferences
- **python.org Windows Python 3.10+ (installer, install manager/Store, NuGet, embeddable):** FTS5 + trigram are always available.
  - Users can, however, swap or replace `DLLs\sqlite3.dll`, or run an embedded/vendored Python, so runtime detection is still advisable (see Q6).
  - The NuGet binaries are produced by the same CPython release build as the installers. This is inferred from the shared PC/layout pipeline and the identical SQLite versions per tag, not stated verbatim.
- **Trigram feature levels by SQLite version:**
  - `remove_diacritics` for trigram needs SQLite ≥ 3.45.0: Python 3.11.9+, 3.12.3+, 3.13.x, 3.14.x, 3.15.
  - The malformed-option crash fix needs ≥ 3.47.0. Builds still affected: all 3.10.x and 3.11.x, 3.12.0–3.12.9, and 3.13.0–3.13.2.
- **Unreal Engine:** if Epic ships the python.org 3.11.8 Windows binaries unchanged, the SQLite would be 3.43.1 with FTS5 and trigram (verified in the python.org 3.11.8 NuGet DLL). Whether UE strips `_sqlite3` is unknown; treat UE-bundled Python as "probe at runtime".
- **conda:** conda Pythons on Windows link the conda `sqlite` package, which has FTS5 in both conda-forge and defaults recipes. This linkage is the standard conda packaging model, inferred rather than verified for each Python build.
- **uv / python-build-standalone:** reusing CPython's `sqlite3.vcxproj` implies these Windows builds also inherit `SQLITE_ENABLE_FTS5`, but their exact SQLite version was not extracted.

### Gaps
- The Unreal Engine Win64 Python file listing (`_sqlite3.pyd`/`sqlite3.dll` present?) could not be verified. The UE repo is private and Epic's docs are blocked here.
- The pre-install-manager per-version Microsoft Store packages (PythonSoftwareFoundation.Python.3.x) were not inspected. They are built via the same `PC/layout` "appx" preset, which does not exclude SQLite (inferred).
- The SQLite version pinned by python-build-standalone (`pythonbuild/downloads.py`) was not extracted.
- No CPython "What's New" text specifically about FTS5 was found. The flag predates 3.6.0 in `PCbuild`, so its original bpo was not traced.

---

## Q6. Runtime detection and safe fallback

### Takeaway
Probe, don't assume:
1. Read `sqlite3.sqlite_version_info` (need ≥ 3.34.0).
2. Optionally check `PRAGMA compile_options` for `ENABLE_FTS5`.
3. Authoritatively, try creating a TEMP FTS5 trigram table inside `try/except sqlite3.OperationalError`.
4. Fall back to B-tree prefix/initials indexes plus a LIMIT-ed `LIKE` scan.
5. Route queries with fewer than 3 characters away from FTS.

### Cited Findings
- **Tested probe (local, SQLite 3.45.1):** creating `temp.__probe USING fts5(x, tokenize='trigram')`, inserting `'GetAbilityPointer'` and running `x LIKE '%abilityp%'` returned 1 row. `EXPLAIN QUERY PLAN` showed `SCAN temp.__probe VIRTUAL TABLE INDEX 0:L0`, where `L` marks the LIKE pattern constraint consumed by FTS5. Script: `scratchpad/exp/detect.py`. — local experiment; `idxStr 'L'/'G'` meaning from [fts5_main.c](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_main.c)
- **Error messages observed (local):**
  - unknown tokenizer → `no such tokenizer: trigramx`;
  - unknown module → `no such module: fts5x`.
  - Both surface as `sqlite3.OperationalError`, so a missing FTS5 or trigram raises a catchable error.
  - A missing value after `case_sensitive` crashes the process on SQLite < 3.47 instead of raising (see Q4).
- `PRAGMA compile_options` exposes `ENABLE_FTS5` on python.org Windows builds; the string was found in every inspected DLL. — local inspection of NuGet DLLs (Q5)
- Under the trigram pattern rules, LIKE literal runs shorter than 3 characters give no index constraint, so FTS falls back to scanning the FTS table. Locally this was slower than scanning the base table: 242–313 ms vs 137–169 ms at 1M rows. — [fts5_expr.c](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5_expr.c); local experiment

### Inferences
- **Recommended probe order:**
  1. `sqlite3.sqlite_version_info >= (3, 34, 0)`.
  2. Create `CREATE VIRTUAL TABLE temp.x USING fts5(n, tokenize='trigram')` in a `try` block. Use only constant, well-formed options such as `'trigram'` or `'trigram case_sensitive 0'`.
  3. Run one LIKE sanity query. Optionally check that `EXPLAIN QUERY PLAN` contains `VIRTUAL TABLE INDEX` with `L`.
  4. Store the result in a metadata table so the index builder and the searcher agree.
- **Fallback when FTS5 or trigram is unavailable:**
  - keep the current exact/prefix B-tree paths;
  - add an `initials` column with a B-tree (+13 MB/1M symbols locally) for abbreviation queries;
  - optionally add a segment-word token table;
  - for true substrings, run `LIKE '%x%' … LIMIT N`. With LIMIT the scan stops early for common terms; the worst case (rare or no hits) stays a full scan of about 100–200 ms per 1M rows.
- **Index placement:** put the FTS table in a separate SQLite file (ATTACH) or name it distinctly, so it can be dropped or rebuilt independently and its size (≈32 MB/1M for name-only detail=none) stays optional.
- **Build cost:** the `'rebuild'` command took 2.7–14.6 s per 1M depending on configuration locally. Building after the main bulk insert, in one transaction, avoids trigger overhead.

### Gaps
- None of these probes were tested on an actual Windows machine; Linux SQLite 3.45.1 was used. Windows behavior is expected to be identical because it is the same SQLite C code, but that is unverified.
- No public measurements were found for FTS5 trigram build or query times on Windows NTFS vs Linux at this scale.
