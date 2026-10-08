# SQLite performance engineering for a large, read-mostly code cross-reference DB (refs 10M+, 1–3 GB, Python stdlib sqlite3)

**How the sources were read (important for the report writer):**
- sqlite.org, vldb.org, web.archive.org and most blogs could not be reached from the research sandbox (proxy policy/DNS). I read the official SQLite documentation from the **official doc bundle for SQLite 3.53.4** (Ubuntu package `sqlite3-doc_3.53.4-2_all.deb`, http://archive.ubuntu.com/ubuntu/pool/main/s/sqlite3/sqlite3-doc_3.53.4-2_all.deb). That bundle is the sqlite.org website text. Citations below use the canonical sqlite.org URLs, and quotes are verbatim from that bundle.
- CPython and SQLite C sources were read from GitHub (raw.githubusercontent.com).
- Figures from the VLDB 2022 paper come from search-result excerpts and blog summaries, not from the PDF itself. They are marked that way.
- **Local measurements ("LOCAL")** were taken in this research on Python 3.13.16 with **SQLite 3.45.1**, the same SQLite version as the target measurements. Setup: Linux, warm OS page cache, single runs, so treat the timings as directional. Synthetic DB:
  - `files`: 20,000 rows. File ids were shuffled relative to path order.
  - `refs`: 4,000,000 rows, a rowid table with a 16-hex-char TEXT `sym` and a TEXT `container`. Rows were emitted file by file, the way an indexer emits them.
  - One "hot" symbol has 1,200,612 refs (30%). There are 200k other symbols.
  - The DB is about 300 MB, roughly 1/2.5 of the target synthetic DB.
  - Scripts: `exp.py`, `exp2.py`, `thr.py` and `lj.py` in the session scratchpad. Their method is summarised inline where they are used.

## Q1. Covering indexes vs WITHOUT ROWID (clustered on sym…); TEXT vs INTEGER symbol IDs

### Takeaway
The largest structural wins for `refs` come from two changes:
- **Serve each hot query shape from one B-tree, in the order the query needs.** Either a covering index or a WITHOUT ROWID table clustered on `(sym, file, line, …)` does this.
- **Intern the 16-char TEXT symbol/container IDs to INTEGER.** Locally this cut a `(sym)` index by 56% and a `(sym,file,line)` index by 45%.

WITHOUT ROWID makes exactly one ordering free and replaces heap+index for that ordering. Every other access path still needs a covering secondary index, and that index carries the full PRIMARY KEY.

### Cited Findings
- Covering index: "If, however, all columns that were to be fetched from the table are already available in the index itself, SQLite will use the values contained in the index and will never look up the original table row. This saves one binary search for each row and can make many queries run twice as fast." — [SQLite Query Optimizer Overview §9](https://www.sqlite.org/optoverview.html#covering_indexes)
- Index entry layout: "The key to an index b-tree is a record composed of the columns that are being indexed followed by the key of the corresponding table row. For ordinary tables, the row key is the rowid, and for WITHOUT ROWID tables the row key is the PRIMARY KEY." — [Database File Format §2.5](https://www.sqlite.org/fileformat2.html#representation_of_sql_indices)
- A WITHOUT ROWID table is itself an index B-tree: "WITHOUT ROWID tables use index b-trees rather than table b-trees, so there is one index b-tree in the database file for each WITHOUT ROWID table." — [File Format](https://www.sqlite.org/fileformat2.html)
- In a secondary index on a WITHOUT ROWID table, PK columns already present in the index are not repeated. The rest of the PK is appended as the row key. — [File Format §2.5.1](https://www.sqlite.org/fileformat2.html)
- Documented benefit: "Thus, in some cases, a WITHOUT ROWID table can use about half the amount of disk space and can operate nearly twice as fast. Of course, in a real-world schema, there will typically be secondary indices and/or UNIQUE constraints, and the situation is more complicated." — [WITHOUT ROWID §3](https://www.sqlite.org/withoutrowid.html)
- When to use it: "The WITHOUT ROWID optimization is likely to be helpful for tables that have non-integer or composite (multi-column) PRIMARY KEYs and that do not store large strings or BLOBs." — [WITHOUT ROWID §4](https://www.sqlite.org/withoutrowid.html)
- Row-size rule: "the average size of a single row in a WITHOUT ROWID table should be less than about 1/20th the size of a database page. That means that rows should not contain more than about 50 bytes each for a 1KiB page size or about 200 bytes each for 4KiB page size." The reason given: WITHOUT ROWID tables "are implemented using ordinary B-Trees with content stored on both leaves and intermediate nodes", which "reduces the fan-out, increasing the search cost." — [WITHOUT ROWID §4](https://www.sqlite.org/withoutrowid.html)
- Restrictions: a PRIMARY KEY is required, "NOT NULL is enforced on every column of the PRIMARY KEY", and AUTOINCREMENT does not work. — [WITHOUT ROWID §2](https://www.sqlite.org/withoutrowid.html)
- Official advice is to measure late in development: "run tests to see if adding WITHOUT ROWID to tables with non-integer PRIMARY KEYs helps or hurts performance, and retaining the WITHOUT ROWID only in those cases where it helps." — [WITHOUT ROWID §4](https://www.sqlite.org/withoutrowid.html)
- Integer storage in records is compact. Serial types store integers in 1, 2, 3, 4, 6 or 8 bytes, and the constants 0 and 1 in 0 bytes ("Value is the integer 0", "Value is the integer 1"). A 16-char hex TEXT id always costs 16 bytes plus a header. — [File Format, Serial Type Codes](https://www.sqlite.org/fileformat2.html#record_format)
- Planner changelog: "Enhancements to covering index prediction in the query planner" (3.46.1, 2024-08-13). — [Release history](https://www.sqlite.org/changes.html)
- LOCAL, interning, index size measured by `page_count` delta:
  - `refs3(sid INTEGER)` index: **42.1 MB**, vs `refs(sym TEXT16)`: **96.0 MB** (−56%).
  - `(sid,file,line)`: **65.0 MB**, vs `(sym,file,line)` with TEXT: **118.8 MB** (−45%).
  - Dictionary table `syms(id INTEGER PRIMARY KEY, usr TEXT UNIQUE)` for 200k symbols: 10.2 MB.
- LOCAL, WITHOUT ROWID: `refs_wr(... PRIMARY KEY(sid,file,line,col,kind,container)) WITHOUT ROWID` = **146.9 MB**, vs the plain rowid heap of the same rows = **143.0 MB**.
  - On the hot symbol (1.2M refs), `ORDER BY file,line LIMIT 60` ran in ~0 ms with no sort step.
  - `count(*)` took 41 ms, vs 31 ms through a narrow covering `r3_sid` index.
  - `GROUP BY container` took **525 ms on refs_wr, vs 111 ms through a covering `refs(sym,container,kind)` index**. The clustered order does not help a different grouping.
- LOCAL, covering vs non-covering for `SELECT container,COUNT(*) … WHERE sym=? AND (kind&4)!=0 GROUP BY container ORDER BY 2 DESC LIMIT 60`:
  - Covering `refs(sym,container,kind)`: **0.111 s** (EQP: `SEARCH refs USING COVERING INDEX refs_sck (sym=?)`).
  - `refs(sym)`: **0.708 s** (EQP adds `USE TEMP B-TREE FOR GROUP BY`).
  - This 6.4x gap matches the target's 2.7 s → 0.42 s.

### Inferences
- **Projected sizes on the target DB (inferred from the local ratios):**
  - `refs(sym)`: 253 MB → ~110–140 MB with an INTEGER sym.
  - `refs(sym,file,line)`: 317 MB → ~175 MB.
  - `refs(sym,container,kind)`: 446 MB → roughly 150–250 MB if both `sym` and `container` (also a symbol ID) are interned.
  - Fewer pages per lookup also means fewer page fetches and cheaper key comparisons.
- **Candidate refs design (inferred):** `refs(sym_id INT, file_id INT, line INT, col INT, kind INT, container_id INT, PRIMARY KEY(sym_id, file_id, line, col, kind)) WITHOUT ROWID`, with `file_id` assigned in path order (see Q4).
  - After interning, rows are about 15–30 bytes, well under the ~200-byte rule for a 4 KiB page.
  - It needs one secondary covering index `(sym_id, container_id, kind)` for the callers/containers aggregate. That index also carries `file_id, line, col` as the PK suffix.
  - The PK must be unique. Exact duplicate refs (e.g., the same ref seen from several TUs) must be collapsed at build time, e.g. with `INSERT OR IGNORE`. This also gives build-time de-dup for free.
- **Cheaper alternative that keeps a rowid table (inferred):** physically insert `refs` sorted by `(sym, file, line)` at build time with `INSERT … SELECT … ORDER BY`. Rowid order then equals the hot access order, and any `sym=?` index lookup walks the heap sequentially. This is the same locality effect behind the 11.6 s anomaly in Q2.

### Gaps
- No controlled, published benchmark of WITHOUT ROWID vs rowid+covering index at 10M+ rows was found.
- A search snippet cites a LevelDB benchmark commit saying WITHOUT ROWID "fares better… with small (16-byte) keys, and worse… with large (100kb) keys" ([commit](https://github.com/google/leveldb/commit/58a89bbcb28d02d5704c5fff7aeb6e72f7ca2431)). GitHub access to that repo was not enabled in this session, so I could not verify it.
- I measured index sizes at 4M rows only. The 10M-row figures are extrapolated.

## Q2. Query planner: why a worse index was chosen (11.6 s); ANALYZE / stat1 / STAT4 / PRAGMA optimize; forcing plans; QPSG

### Takeaway
**The 11.6 s case:**
- The planner's cost model counts binary searches. It does not model the physical locality of the rowid lookups.
- `refs(sym)` and `refs(sym,container,kind)` look equally good for `sym=?`, and their stat1 first-column selectivity is identical.
- Entries for one sym in `refs(sym)` are in rowid order, which gives sequential heap access. Entries in `(sym,container,kind)` are in container order, which gives random heap access.
- LOCAL: forcing the wider index made the identical plan **7.6x slower**.

Fix this with schema/index design, not statistics. Give each query an index whose prefix also satisfies its ORDER BY or GROUP BY, or that covers it, and assert plans in tests.

**The `LIKE '%x%'` case:** the LEFT JOIN fixes the loop order. Outer joins are not reordered, and the strength-reduction prover did not demote it. Rewriting it as an inner JOIN fixed it locally, from 1.01 s to 4 ms. ANALYZE cannot help here.

### Cited Findings
- **How the index is chosen:** "When faced with a choice of two or more indexes, SQLite tries to estimate the total amount of work needed to perform the query using each option. It then selects the option that gives the least estimated work." The stat1 table "might indicate that an equality constraint on column x reduces the search space to 10 rows on average". Also, "The results of an ANALYZE command are only available to database connections that are opened after the ANALYZE command completes." — [optoverview §8](https://www.sqlite.org/optoverview.html#choosing_between_multiple_indexes)
- **Cost model:** for K result rows, "the cost of doing the query is proportional to (K+1)*logN". Indexed lookups take "two binary searches". — [Query Planning](https://www.sqlite.org/queryplanner.html)
- **WHERE index vs ORDER BY index:** "When faced with the choice of using an index to satisfy WHERE clause constraints or satisfying an ORDER BY clause, SQLite does the same cost analysis described above and chooses the index that it believes will result in the fastest answer." — [optoverview §10](https://www.sqlite.org/optoverview.html#order_by_optimizations)
- **Low-quality indexes:** "A low-quality index … is one where there are more than 10 or 20 rows in the table that have the same value for the left-most column of the index… If you must use a low-quality index, be sure to run ANALYZE." — [NGQP §6 checklist](https://www.sqlite.org/queryplanner-ng.html)
  - 3.45.0 (2024-01-15): "The query planner now does a better job of disregarding indexes that ANALYZE identifies as low-quality." — [changes](https://www.sqlite.org/changes.html)
- **Official stance on plan hacks:** "Update 2024: The query planner has been improved so much over the years that you should never need to use any of the hacks described below. The capabilities described below are still available, for backwards compatibility… If you do find a case where you are getting a suboptimal query plan, please report it to the SQLite developers on the SQLite Forum". — [NGQP §6](https://www.sqlite.org/queryplanner-ng.html)
- **likelihood():** "SQLite normally assumes that terms in the WHERE clause that cannot be used by indexes have a strong probability of being true… The unlikely() and likelihood() SQL functions can be used to provide hints". — [NGQP §6](https://www.sqlite.org/queryplanner-ng.html)
- **CROSS JOIN:** "the left table of a CROSS JOIN will always be in an outer loop relative to the right table… (Table reordering is also disabled on an outer join, but that is because outer joins are not associative or commutative. Reordering tables in OUTER JOIN changes the result.)" — [optoverview §7.1.2](https://www.sqlite.org/optoverview.html#manual_control_of_query_plans_using_cross_join)
- **OUTER JOIN strength reduction:** "if any column in the right-hand table of the LEFT JOIN must be non-NULL in order for the WHERE clause to be true, then the LEFT JOIN is demoted to an ordinary JOIN. The theorem prover that determines whether a join can be simplified is imperfect. It sometimes returns a false negative." — [optoverview §16](https://www.sqlite.org/optoverview.html#the_outer_join_strength_reduction_optimization)
- **Unary +:** "Note: Disqualifying WHERE clause terms this way is not recommended. This is a work-around… the unary + operator will prevent the term from constraining an index." It "also removes type affinity", so for a TEXT column `+x=5` "will always be false". — [optoverview §8.1](https://www.sqlite.org/optoverview.html#disqualifying_where_clause_terms_using_unary_)
- **INDEXED BY:**
  - "If index-name does not exist or cannot be used for the query, then the preparation of the SQL statement fails."
  - "The INDEXED BY clause is not intended for use in tuning the performance of a query. The intent of the INDEXED BY clause is to raise a run-time error if a schema change, such as dropping or…" an index occurs.
  - Source: [INDEXED BY](https://www.sqlite.org/lang_indexedby.html)
- **Fudging stat1:** "One method for doing this is to fudge the ANALYZE results in the sqlite_stat1 table." — [optoverview §7.1.1](https://www.sqlite.org/optoverview.html)
- **STAT4:** "The ANALYZE command is enhanced to collect histogram data from all columns of every index and store that data in the sqlite_stat4 table… The downside of this compile-time option is that it violates the query planner stability guarantee". The histogram "is only useful if the right-hand side of the constraint is a simple compile-time constant or parameter". — [compile.html SQLITE_ENABLE_STAT4](https://www.sqlite.org/compile.html#enable_stat4); [optoverview §8.2](https://www.sqlite.org/optoverview.html#range_queries)
- **QPSG:** "When the Query Planner Stability Guarantee (QPSG) is enabled SQLite will always pick the same query plan for any given SQL statement as long as: the database schema does not change in significant ways such as adding or dropping indexes, the ANALYZE command is not rerun, the same version of SQLite is used. The QPSG is disabled by default. It can be enabled at compile-time using the SQLITE_ENABLE_QPSG compile-time option, or at run-time by invoking sqlite3_db_config(db,SQLITE_DBCONFIG_ENABLE_QPSG,1,0)." — [NGQP §2.2](https://www.sqlite.org/queryplanner-ng.html#qpstab)
  - Python ≥3.12 exposes this as `Connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_QPSG, True)` ("versionadded:: 3.12"). — [CPython Doc/library/sqlite3.rst](https://github.com/python/cpython/blob/main/Doc/library/sqlite3.rst); [module.c `ADD_INT(SQLITE_DBCONFIG_ENABLE_QPSG)`](https://github.com/python/cpython/blob/main/Modules/_sqlite/module.c)
- **ANALYZE / PRAGMA optimize:**
  - "All applications should run "PRAGMA optimize;" after a schema change, especially after one or more CREATE INDEX statements." — [pragma optimize](https://www.sqlite.org/pragma.html#pragma_optimize)
  - "Since SQLite version 3.46.0 (2024-05-23), the "PRAGMA optimize" command automatically limits the scope of ANALYZE subcommands so that the overall "PRAGMA optimize" command completes quickly even on enormous databases. There is no need to use PRAGMA analysis_limit. This is the recommended way of running ANALYZE moving forward." (verbatim) — [lang_analyze §2.1](https://www.sqlite.org/lang_analyze.html)
  - Approximate ANALYZE exists since 3.32.0 (2020-05-22) via `PRAGMA analysis_limit=N`, with "Values of N between 100 and 1000 are recommended." — [lang_analyze §5](https://www.sqlite.org/lang_analyze.html#approx)
  - For frozen plans: "never run a full ANALYZE nor the "PRAGMA optimize" command in the application. Rather, only run ANALYZE during development… Then capture the result of this one-time ANALYZE" and replay it as INSERTs into sqlite_stat1. — [lang_analyze §2.2](https://www.sqlite.org/lang_analyze.html)
- **STAT4 is not in typical Python builds:**
  - LOCAL `PRAGMA compile_options` on Ubuntu's SQLite 3.45.1 shows no `ENABLE_STAT4`.
  - CPython's Windows build defines only `SQLITE_ENABLE_MATH_FUNCTIONS;SQLITE_ENABLE_FTS4;SQLITE_ENABLE_FTS5;SQLITE_ENABLE_RTREE;SQLITE_OMIT_AUTOINIT`. — [PCbuild/sqlite3.vcxproj (3.14)](https://github.com/python/cpython/blob/3.14/PCbuild/sqlite3.vcxproj)
  - The Windows python.org builds bundle SQLite **3.50.4** for 3.13/3.14 and **3.53.4** on `main`. — [PCbuild/get_externals.bat](https://github.com/python/cpython/blob/3.14/PCbuild/get_externals.bat)
- **LOCAL reproduction of the index-choice effect.** Query: `refs r LEFT JOIN files f … WHERE r.sym=? ORDER BY f.rel, r.line LIMIT 60`, hot sym = 1.2M refs.
  - With only `refs(sym)`: 0.392 s.
  - After adding `refs(sym,container,kind)`, the planner here still picked `refs_sym`: 0.379 s.
  - **Forced `INDEXED BY refs_sym`: 0.356 s. Forced `INDEXED BY refs_sck`: 2.734 s.** Both had the identical EQP shape (`SEARCH r USING INDEX … (sym=?)` / `SEARCH f USING INTEGER PRIMARY KEY` / `USE TEMP B-TREE FOR ORDER BY`).
  - After ANALYZE, stat1 was `refs_sck '4000000 20 2 2'` and `refs_sym '4000000 20'`. The first-column estimate is identical, so stats cannot tell the two indexes apart.
- **LOCAL LEFT JOIN + LIKE.** Query: `refs r {LEFT} JOIN files f … WHERE f.rel LIKE '%Mod001/%' ORDER BY f.rel, r.line LIMIT 200`.
  - LEFT JOIN: **1.013 s**, EQP `SCAN r …` then `SEARCH f … LEFT-JOIN`. The demotion did not happen.
  - INNER JOIN: **0.004 s**, EQP `SCAN f` then `SEARCH r USING INDEX refs_file (file=?)`.
  - `likelihood(f.rel LIKE ?, 0.001)` on the LEFT JOIN version: still 1.094 s.
  - The `r.file IN (SELECT id FROM files WHERE rel LIKE ?)` rewrite: 0.004 s. This matches the target's 0.93–1.09 s → 6.7 ms.

### Inferences
- **Why the planner picked the wider index in the target (inferred):** the two indexes tie under the documented `(K+1)*logN` model and identical stat1. Which one wins is then an implementation detail of tie-breaking (column count, schema order), and it is invisible to ANALYZE. The 3x–8x penalty is pure I/O locality:
  - refs were bulk-inserted file by file, so one symbol's rowids are ascending and the heap pages are visited in order.
  - Via `(sym,container,kind)`, the same rowids are visited in container order, so nearly every lookup touches a different page.
  - The default 2 MB page cache makes this worse.
- **Practical fixes, in order of robustness (inferred):**
  - (a) Make the list query's index satisfy its ORDER BY: `(sym,file,line)` plus path-ordered file IDs (Q4). The planner then gets a large cost advantage from skipping the sort plus LIMIT early exit, and stops tying.
  - (b) Make each index covering for its query, so heap locality no longer matters.
  - (c) Cluster the heap by `(sym,…)` (Q1).
  - (d) As a last resort, use `INDEXED BY`. It fails loudly if the index disappears, which is acceptable for a build-once DB.
  - Add a test that asserts `EXPLAIN QUERY PLAN` strings for each hot query. Windows users get SQLite 3.50.x/3.53.x while Linux has 3.45.1, so plans may differ across versions.
- **ANALYZE:** the DB is opened read-only, so `PRAGMA optimize` at runtime cannot persist stats. Run `ANALYZE` (or `PRAGMA optimize=0x10002`) as the last build step after `CREATE INDEX`.
- **Skew and STAT4:** stat1 stores averages (≈10 refs/sym), while a hot symbol has 3.4M. Without STAT4, which Python builds lack, the planner will always under-estimate hot symbols. Design indexes so the plan is good for both small and huge symbols. ORDER-BY-satisfying indexes are good in both cases.
- **QPSG:** turning it on only freezes plans for a given SQLite version and stats, and it does not fix a bad plan. Its use here is reproducibility.

### Gaps
- I did not read where.c's tie-breaking code, so the exact reason the target build chose `refs(sym,container,kind)` (and this local run did not) is unconfirmed.
- I found no SQLite forum post by the developers that discusses rowid-locality being absent from the cost model. That point is inferred from the documented cost formula and the local measurement.

## Q3. Precomputed aggregates / summary tables; top-N per group

### Takeaway
Because the DB is built once and read many times, per-symbol aggregates belong in summary tables built at index time:
- ref counts per sym
- counts per (sym, container, kind-class)
- counts per (sym, file)

Each is ordered or indexed so that "top-N for symbol X" is a short index range read. Locally, the top-60 containers query went from 111 ms (covering index) or 708 ms (non-covering) to ~0 ms. Building the summary took 2.2 s for 4M refs.

### Cited Findings
- GROUP BY uses an index order when one exists, otherwise a sorter/temp B-tree: "SQLite will also attempt to use indexes to help satisfy GROUP BY clauses… If the nested loops of the join can be arranged such that rows that are equivalent for the GROUP BY… are consecutive". — [optoverview §10](https://www.sqlite.org/optoverview.html#order_by_optimizations)
- "SQLite implements GROUP BY by ordering the output rows in the order suggested by the GROUP BY terms… A preexisting index is used if possible, but if no suitable index is available, a transient index is created." — [Temporary Files §2.8](https://www.sqlite.org/tempfiles.html)
- EXPLAIN QUERY PLAN reports these as "USE TEMP B-TREE FOR xxx", where xxx is "ORDER BY", "GROUP BY" or "DISTINCT", and "using the temporary b-tree can be avoided by creating an index". — [EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html)
- Window functions are available since SQLite 3.25.0 (2018-09-15). `row_number()` gives "The number of the row within the current partition", which is the standard way to keep the top-K rows per group at build time. — [Window Functions](https://www.sqlite.org/windowfunctions.html)
- 3.53.0 (2026-04-09) changelog lists query planner improvements, including "Improvements to join order selection in large multi-way joins on a star schema" and allowing "queries that use "GROUP BY e1 ORDER BY e2"" in more cases. — [changes](https://www.sqlite.org/changes.html)
- LOCAL:
  - Building `sym_cont_cnt AS SELECT sym, container, count(*) n FROM refs WHERE (kind&4)!=0 GROUP BY sym, container` plus an index `(sym, n DESC)` took **2.2 s** for 4M refs.
  - Top-60 per symbol from it: **~0 ms** (EQP `SEARCH sym_cont_cnt USING INDEX scc (sym=?)`).
  - The same aggregate from a covering index: 0.111 s. From `refs(sym)`: 0.708 s.
  - `count(*) WHERE sym=?` on the 1.2M-ref symbol took 31–41 ms through a covering index, vs 0.13 s in the target at 3.4M.

### Inferences
- **Recommended summary tables (inferred), all keyed by integer IDs:**
  - `sym_stats(sym_id PRIMARY KEY, n_refs, n_files, n_callers, …)`: constant-time counts for the UI header.
  - `sym_container_counts(sym_id, kind_class, container_id, n)` with an index `(sym_id, kind_class, n DESC)`, or WITHOUT ROWID with PK `(sym_id, kind_class, n DESC, container_id)` so top-N is a prefix scan.
  - `sym_file_counts(sym_id, file_id, n)`: "files referencing X" ordered by path via path-ordered file_id (Q4). It also enables two-level UI paging (files first, then lines).
- **Cost (inferred):** summary row count equals the number of distinct groups. Per-(sym,container) is usually far smaller than refs, but for very hot symbols it can be large.
  - Optional: truncate to top-K per sym at build time using `row_number() OVER (PARTITION BY sym_id ORDER BY n DESC) <= K`.
  - Store the remainder as an "other" bucket so totals stay exact.
- **Kind filters (inferred):** the bit tests (`kind&4`) can't use an index. Precompute per kind class (e.g., call/read/write/decl), or put `kind` before the counted column in the key.

### Gaps
- I found no published benchmark specific to summary-table patterns in SQLite. The evidence is local measurement plus general documentation.

## Q4. Pagination: keyset vs OFFSET; making ORDER BY match an index (path-ordered file IDs)

### Takeaway
If `files.id` is assigned in sorted path order at build time, `ORDER BY f.rel, r.line` can be rewritten as `ORDER BY r.file, r.line`. An index (or clustered PK) on `(sym, file, line[, col])` then returns rows already in order, so `LIMIT 60` stops after 60 rows instead of sorting millions. Locally this went from 0.36–0.41 s to ~0 ms.

Use keyset pagination with row values, `(file,line,col) > (?,?,?)`. OFFSET is documented as linear in the offset.

### Cited Findings
- Keyset pattern, official: "OFFSET requires time proportional to the offset value. What really happens with "LIMIT x OFFSET y" is that SQLite computes the query as "LIMIT x+y" and discards the first y values… A more efficient approach is to remember the last entry currently displayed and then use a row value comparison in the WHERE clause: `SELECT * FROM contacts WHERE (lastname,firstname) > (?1,?2) ORDER BY lastname, firstname LIMIT 7;` … assuming there is an appropriate index, it does so very efficiently — much more efficiently than OFFSET." — [Row Values §3.1](https://www.sqlite.org/rowvalue.html#scrolling_window_queries)
  - Row values need SQLite ≥3.15.0 (2016-10-14). — [Row Values](https://www.sqlite.org/rowvalue.html)
- Without a suitable index: "it will evaluate the query and store each row in a transient index whose data is the row data and whose key is the ORDER BY terms. After the query is evaluated, SQLite goes back and walks the transient index…" — [Temporary Files §2.8](https://www.sqlite.org/tempfiles.html)
- Partial index order: "SQLite does block sorting… many fewer rows need to be held in memory… and outputs can begin to appear before the core query has run to completion." — [optoverview §10.1](https://www.sqlite.org/optoverview.html#partial_order_by_via_index)
- Since 3.47.0 there is an "order-by-subquery" optimization that "seeks to disable sort operations in outer queries if the desired order is obtained naturally due to ORDER BY" in subqueries. — [changes](https://www.sqlite.org/changes.html)
- LOCAL results:
  - Files renumbered with `row_number() OVER (ORDER BY rel)`, refs rebuilt with an index `(sym,file,line)`: `… WHERE r.sym=? ORDER BY r.file, r.line LIMIT 60` took **~0 ms**. EQP is `SEARCH r USING INDEX refs2_sfl (sym=?)` with no TEMP B-TREE. The original `ORDER BY f.rel` version took 0.36–0.41 s.
  - Keyset page at position 1,000,000 (`(r.file,r.line) > (?,?)`): **~0 ms**, EQP `SEARCH … (sym=? AND (file,line)>(?,?))`.
  - `LIMIT 60 OFFSET 1000000`: **51 ms**.
  - OFFSET was cheaper than expected here, likely because skipped rows did not need their table row. It still grows linearly.

### Inferences
- **Make the keyset key unique (inferred):** use `(file, line, col, kind)` or include the rowid/PK, otherwise ties at a page boundary drop or duplicate rows.
- **Multiple roots/modules (inferred):** assign IDs in `(root, rel)` order, or whatever display order the UI uses, before inserting refs. If the UI needs several orderings (by path, by module), each needs its own index or summary.
- **Path-ordered IDs require a global sort of paths at build (inferred).** This is trivial (O(F log F) over ~100k files). IDs must be reassigned on every rebuild, which is fine for a build-once DB.

### Gaps
- No published benchmark numbers specific to SQLite keyset vs OFFSET at 10M rows were found beyond the official description.

## Q5. Read-only performance pragmas and settings (mmap_size, cache_size, page_size, immutable, temp_store, journal mode); Windows notes

### Takeaway
These settings are second-order compared with index design.
- With a warm OS cache on Linux, mmap, a bigger cache_size and `immutable=1` produced no measurable gain on the CPU-bound aggregate locally.
- The defaults that matter:
  - mmap is **off** (0), and its hard cap is ~2 GiB (`0x7fff0000`) on Linux and Windows, so a 3 GB file can only be partly mapped.
  - cache_size is **2 MB**.
  - Temp B-trees (ORDER BY/GROUP BY/UNION) go to **files** by default once they exceed a 500-page cache.
- `immutable=1` skips locking and change detection, but returns wrong results or SQLITE_CORRUPT if the file changes underneath.
- Page size can only be chosen at build time.

### Cited Findings
- **mmap trade-offs:** "Many operations, especially I/O intensive operations, can be faster since content need not be copied between kernel space and user space." But: "An I/O error on a memory-mapped file cannot be caught… results in a program crash." And: "Performance does not always increase with memory-mapped I/O. In fact, it is possible to construct test cases where performance is reduced by the use of memory-mapped I/O." Also: "memory-mapped I/O is disabled by default." "Memory mapped I/O is mostly a benefit for queries." — [Memory-Mapped I/O](https://www.sqlite.org/mmap.html)
- **Windows and mmap:** "Windows is unable to truncate a memory-mapped file. Hence, on Windows, if an operation such as VACUUM or auto_vacuum tries to reduce the size of a memory-mapped database file, the size reduction attempt will silently fail". This does not matter for a read-only DB. — [mmap](https://www.sqlite.org/mmap.html)
- **mmap is per file:** "The mmap_size applies separately to each database file, so the total amount of process address space that could potentially be used is the mmap_size times the number of open database files." — [mmap](https://www.sqlite.org/mmap.html)
- **Hard cap:** "The PRAGMA mmap_size statement will never increase the amount of address space used for memory-mapped I/O above the hard limit set by the SQLITE_MAX_MMAP_SIZE compile-time option". — [pragma mmap_size](https://www.sqlite.org/pragma.html#pragma_mmap_size)
  - The default cap is `0x7fff0000 /* 2147418112 */` when `__linux__ || _WIN32 || __APPLE__…`. — [sqliteInt.h](https://github.com/sqlite/sqlite/blob/master/src/sqliteInt.h)
  - LOCAL compile_options agree: `MAX_MMAP_SIZE=0x7fff0000`, `DEFAULT_MMAP_SIZE=0`, `DEFAULT_CACHE_SIZE=-2000`, `TEMP_STORE=1`, `THREADSAFE=1`, `DEFAULT_PAGE_SIZE=4096`.
- **Published mmap benchmark (blob reads):** "the entire 1GB database file is memory mapped and blobs are read (in random order) using the sqlite3_blob_read() interface. With these optimizations, SQLite is twice as fast as Android or MacOS-X and over 10 times faster than Windows". This is relative to reading individual files. Setup: 100K blobs of 8–12 KB, 4 KiB pages. — [35% Faster Than The Filesystem](https://www.sqlite.org/fasterthanfs.html)
- **cache_size:** "The default suggested cache size is -2000, which means the cache size is limited to 2048000 bytes of memory." — [pragma cache_size](https://www.sqlite.org/pragma.html#pragma_cache_size)
- **page_size:** "beginning with SQLite version 3.12.0 (2016-03-29), the default page size increased to 4096. The default page size is recommended for most applications." A new page size takes effect only when the DB is created or at the next VACUUM (not in WAL mode). — [pragma page_size](https://www.sqlite.org/pragma.html#pragma_page_size)
  - Published benchmark, Ubuntu 2011: "A database page size of 8192 or 16384 gives the best performance for large BLOB I/O." — [Internal vs External BLOBs](https://www.sqlite.org/intern-v-extern-blob.html)
- **immutable:** "SQLite always opens immutable database files read-only and it skips all file locking and change detection on immutable database files… if… a database file is immutable and that file changes anyhow, then SQLite might return incorrect query results and/or SQLITE_CORRUPT errors." — [URI filenames](https://www.sqlite.org/uri.html)
- **query_only is not read-only:** "the database is not truly read-only. You can still run a checkpoint or a COMMIT". — [pragma query_only](https://www.sqlite.org/pragma.html#pragma_query_only)
- **temp_store:**
  - "The default value of the SQLITE_TEMP_STORE compile-time parameter is 1, which means to store temporary files on disk but provide the option of overriding the behavior using the temp_store pragma." — [Temporary Files §3](https://www.sqlite.org/tempfiles.html)
  - Spill behaviour: "The temporary file is not opened and the information is not truly written to disk until the page cache is full… Each temporary table and index is given its own page cache which can store a maximum number of database pages determined by the SQLITE_DEFAULT_TEMP_CACHE_SIZE compile-time parameter. (The default value is 500 pages.)" — [Temporary Files §4](https://www.sqlite.org/tempfiles.html)
- **Journal mode for read-only use:** WAL-mode DBs on read-only media became readable only from 3.22.0, with conditions. "Older versions of SQLite could not read a WAL-mode database that was read-only… This constraint was relaxed beginning with SQLite version 3.22.0 (2018-01-22)." — [WAL §5](https://www.sqlite.org/wal.html)
- **Worker threads:** `PRAGMA threads` caps "the number of auxiliary threads that a prepared statement is allowed to launch to assist with a query. The default limit is 0". — [pragma threads](https://www.sqlite.org/pragma.html#pragma_threads)
- **Windows antivirus:**
  - "the windows VFS will retry file read, file write, and file delete operations up to 10 times, with a delay of 25 milliseconds before the first retry and with the delay increasing by an additional 25 milliseconds with each subsequent retry" (`SQLITE_FCNTL_WIN32_AV_RETRY`). — [C API file-control opcodes](https://www.sqlite.org/c3ref/c_fcntl_begin_atomic_write.html)
  - "anti-virus software slows down direct-to-disk by an order of magnitude whereas it impacts SQLite writes very little… SQLite writes only changes the single database file." — [fasterthanfs](https://www.sqlite.org/fasterthanfs.html)
- **LOCAL, warm Linux page cache.** Query: covering-less GROUP BY on the 1.2M-ref symbol, second run on a fresh connection.
  - `mmap_size=0`: 0.707 s; `mmap_size=1 GiB`: 0.700 s.
  - `cache_size=-2000`: 0.685 s; `cache_size=-262144` (256 MB): 1.033 s. This was a single noisy run with no gain.
  - `immutable=1`: 0.746 s.

### Inferences
- **What actually helps for interactive use (inferred):**
  - mmap (e.g., `PRAGMA mmap_size=2147418112`) and a moderately larger cache (e.g., 64–256 MB) mainly help **cold or semi-warm** cases and **many repeated point lookups**. They remove a `read()` syscall plus memcpy per page.
  - The local test was CPU-bound on record decoding and sorting, which is why it showed nothing.
  - Measure on Windows specifically. Its file I/O path is typically costlier per syscall, and AV filters can add per-open/read overhead, but that is not quantified in the sources.
- **page_size (inferred):** for long index range scans, 8 KiB or 16 KiB pages reduce B-tree depth and per-page overhead. Random point lookups read more bytes per lookup. Because the DB is built once, test `PRAGMA page_size=8192/16384` before the first CREATE TABLE. WITHOUT ROWID's 1/20-page rule loosens with bigger pages.
- **Journal mode and file replacement (inferred):** build in the default rollback (DELETE) journal mode, not WAL, so that `mode=ro` / `immutable=1` opens need no `-wal`/`-shm` files.
  - `immutable=1` is safe only if the builder never rewrites a file that readers have open. Build to a new filename and switch readers to it.
  - On Windows, an open (and especially a memory-mapped) file can't be replaced in place anyway. This is a general Windows file-sharing behaviour, not from the SQLite docs.
- **temp_store (inferred):** `PRAGMA temp_store=MEMORY` keeps large sorts, GROUP BYs and UNIONs (Q6) in RAM. For millions of rows that can mean hundreds of MB, so prefer eliminating the sort via indexes.

### Gaps
- No authoritative benchmark of mmap vs read() on **Windows** for B-tree query workloads was found. The Windows numbers in fasterthanfs are for blob reads.
- I did not find official docs on the effect of `PRAGMA threads` in default Python builds, which depends on `SQLITE_MAX_WORKER_THREADS`.

## Q6. Multi-database: ATTACH + UNION vs separate queries + merge; alternatives to exact de-dup

### Takeaway
`UNION` over ATTACHed DBs builds a **transient index (temp B-tree) of every row from both sides** to discard duplicates. With 3.4M+ rows of `(path, line, col, kind)` keys, that index spills to temp files (default temp_store=FILE, 500-page temp cache), which explains the 24 s.

Better options:
- Avoid duplicates at build time: assign each file to exactly one owner DB, and use a shared global file-ID space.
- Or query each DB separately with the same index-ordered keyset query, merge the already-sorted small result pages in Python, and de-dup only adjacent equal keys.

### Cited Findings
- "The UNION operator for compound queries is implemented by creating a transient index in a temporary file and storing the results of the left and right subquery in the transient index, discarding duplicates." — [Temporary Files §2.8](https://www.sqlite.org/tempfiles.html)
- "Note that the UNION ALL operator for compound queries does not use transient indices by itself (though of course the right and left subqueries of the UNION ALL might use transient indices depending on how they are composed.)" — [Temporary Files §2.8](https://www.sqlite.org/tempfiles.html)
- Temp spill rules: temp_store default and the 500-page temp cache (quoted under Q5). — [Temporary Files §3–4](https://www.sqlite.org/tempfiles.html)
- ATTACH limit: "The number of simultaneously attached databases is limited to SQLITE_MAX_ATTACHED which is set to 10 by default. The maximum number of attached databases cannot be increased above 125." — [Limits](https://www.sqlite.org/limits.html)
- A `PRAGMA mmap_size` without a schema name "becomes the default limit for all databases that are added to the database connection by subsequent ATTACH statements". — [pragma mmap_size](https://www.sqlite.org/pragma.html#pragma_mmap_size)

### Inferences
- **24 s breakdown (inferred):** about 6.8M composite keys with TEXT paths are inserted into a temp B-tree. That is a full read of both sides' rows plus random B-tree inserts plus temp-file I/O, and none of it can stop early for LIMIT.
- **Alternatives, inferred and ordered by preference:**
  1. **Ownership partitioning at build:** each source file's refs are stored in only one DB, e.g. engine DB vs project DB by root. Then there is no de-dup at all: run separate queries or `UNION ALL`.
  2. **Streaming merge:** run `SELECT … WHERE sym=? AND (file,line,col)>(?,?,?) ORDER BY file,line,col LIMIT 60` per DB, using index order (Q4). Merge with `heapq.merge` in Python and drop adjacent duplicates. This needs file IDs that are comparable across DBs, i.e. a shared global path table or sort key. Work per page is O(60·#DBs).
  3. **Counts:** show per-DB counts from the summary tables (Q3), or label the sum "≤ N". Compute an exact distinct count only on demand.
  4. **If SQL-side de-dup is required:** use integer keys (global `file_id`) rather than TEXT paths, run `temp_store=MEMORY`, and restrict to the current page window instead of the whole symbol.
- **Parallelism (inferred):** separate connections per DB can also run in parallel threads (Q7).

### Gaps
- I found no published benchmark of ATTACH+UNION vs application-side merge in SQLite.

## Q7. Concurrency: does Python's sqlite3 release the GIL during sqlite3_step? Parallel queries on two DBs

### Takeaway
Yes. CPython's `_sqlite` module wraps `sqlite3_step()` (and `sqlite3_prepare_v2()`) in `Py_BEGIN_ALLOW_THREADS`. Separate connections in separate threads therefore run in parallel inside SQLite, and only the Python row conversion holds the GIL. Locally, 2 threads with 2 connections gave a **1.88x** speedup on a heavy aggregate.

### Cited Findings
- `Modules/_sqlite/cursor.c` (main), lines ~542–551:
  ```c
  static int
  stmt_step(sqlite3_stmt *statement)
  {
      int rc;
      Py_BEGIN_ALLOW_THREADS
      rc = sqlite3_step(statement);
      Py_END_ALLOW_THREADS
      return rc;
  }
  ```
  `stmt_step` is used both by execute (`rc = stmt_step(self->statement->st);`) and by `pysqlite_cursor_iternext`, which backs `fetchone`, `fetchmany` and `fetchall`. — [cursor.c](https://github.com/python/cpython/blob/main/Modules/_sqlite/cursor.c)
- `Modules/_sqlite/statement.c`: `Py_BEGIN_ALLOW_THREADS rc = sqlite3_prepare_v2(db, sql_cstr, (int)size + 1, &stmt, &tail); Py_END_ALLOW_THREADS`. — [statement.c](https://github.com/python/cpython/blob/main/Modules/_sqlite/statement.c)
- Connections default to `check_same_thread: bool = True`. — [connection.c](https://github.com/python/cpython/blob/main/Modules/_sqlite/connection.c)
- SQLite threading modes: "Serialized. In serialized mode, API calls to affect or use any SQLite database connection or any object derived from such a database connection can be made safely from multiple threads… The default mode is serialized." In multi-thread mode, SQLite is safe "provided that no single database connection… is used simultaneously in two or more threads." — [Using SQLite In Multi-Threaded Applications](https://www.sqlite.org/threadsafe.html)
- LOCAL (Python 3.13, `sqlite3.threadsafety == 3`, SQLite `THREADSAFE=1`): the same GROUP BY on 2 separate `mode=ro` connections took **1.44 s sequentially vs 0.77 s in 2 threads (1.88x)**.

### Inferences
- **Use one connection per thread (inferred):** for example, one per DB file, or a small pool. Sharing one connection across threads serializes on the connection mutex.
- **Where the GIL still matters (inferred):** queries that return few rows (LIMIT 60, aggregates) spend nearly all their time in `sqlite3_step` and parallelize well. Queries returning millions of rows to Python are bound by tuple creation under the GIL.
- **Engine DB + project DB (inferred):** the two DBs can be queried concurrently with `concurrent.futures.ThreadPoolExecutor`, then merged (Q6).

### Gaps
- I did not test free-threaded CPython (3.13t/3.14t) or Windows. The GIL-release code path is the same on all platforms.

## Q8. Would DuckDB (columnar, vectorized) be materially better for these aggregate queries? (comparison only)

### Takeaway
For full-table OLAP scans and joins, DuckDB is much faster than SQLite. The VLDB 2022 paper (co-authored by SQLite's developers) reports DuckDB remains "considerably faster" on SSB even after SQLite's Bloom-filter work.

Our hot queries are different. They are **selective per-symbol index range reads and small aggregates**, and SQLite with covering or clustered indexes plus precomputed summaries already reaches milliseconds. DuckDB is not in the Python standard library, so it is out of scope by constraint.

### Cited Findings
- The paper is Gaffney, Prammer, Brasfield, Hipp, Kennedy, Patel, "SQLite: Past, Present, and Future", PVLDB 15(12): 3535–3547, 2022. — [PDF](https://www.vldb.org/pvldb/vol15/p3535-gaffney.pdf); code at [UWHustle/sqlite-past-present-future](https://github.com/UWHustle/sqlite-past-present-future). The README says it accompanies the VLDB 2022 paper, with SSB, TATP and Blob benchmarks.
- The following points come **via search excerpts and blog summaries; I did not read the PDF directly:**
  - Profiling with `VDBE_PROFILE` found "only two instructions are responsible for the vast majority of cycles: SeekRowid and Column". SSB joins probe dimension tables via SeekRowid for every fact row, yet "only 0.8% of the lineorder tuples satisfy the restrictions".
  - A Bloom-filter optimization shipped in SQLite **3.38.0** (Feb 2022). "On the Raspberry Pi, SQLite is now 4.2X faster on SSB. On the cloud server, they observed an overall speedup of 2.7X and individual query speedups up to 7X."
  - "While the performance gap has narrowed as a result of this work, DuckDB is still considerably faster than SQLite on SSB."
  - Per-flight gaps from a blog summary: DuckDB 30–50x faster on query flight 2, 3–8x on flight 1.
  - Sources: [Simon Willison, Notes on the SQLite DuckDB paper](https://simonwillison.net/2022/Sep/1/sqlite-duckdb-paper/); [avi.im summary](https://avi.im/blag/2024/sqlite-past-present-future/); [PVLDB PDF](https://www.vldb.org/pvldb/vol15/p3535-gaffney.pdf)
- SQLite also uses Bloom filters on subqueries since 3.47.0 ("Use a Bloom filter on subqueries on the right-hand side of the…"). — [changes](https://www.sqlite.org/changes.html)

### Inferences
- **The paper's finding supports covering and clustered layouts (inferred).** SQLite's analytic cost is dominated by `SeekRowid` (index → table lookups) and `Column` (record decoding). Covering or clustered layouts remove SeekRowid. Narrow integer records cut Column cost.
- **Where DuckDB would win (inferred):** whole-DB aggregates such as "top 100 most-referenced symbols overall" or "refs per module", computed ad hoc without a precomputed table. Even there, SQLite summary tables built at index time remove the need.
- **Where DuckDB would not obviously win (inferred):** point lookups by symbol ID. DuckDB relies mainly on min/max zonemaps and ART indexes. This was not verified in this research.

### Gaps
- I could not read the paper PDF itself (blocked), so the exact figure/section references and the DuckDB thread configuration are unverified. One blog summary claims DuckDB ran single-threaded, but I could not confirm it.
- No credible, reproducible benchmark of DuckDB vs SQLite on code-cross-reference-style workloads (selective lookups by key plus small group-bys) was found. The general "DuckDB vs SQLite" blog posts surfaced in searches did not show their methodology or numbers in a verifiable way, so they are not cited.
