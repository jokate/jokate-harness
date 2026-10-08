#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cindex.py 조회 계층 시험 (표준 라이브러리 unittest). clangd 없이 합성 원본 표로 돈다.

  python skills/game-onboard/tests/test_cindex_query.py

- 정답 대조: 프로젝트+엔진 합쳐 보기의 참조·개수·호출자·모듈·파일·피호출 함수가 "파일마다 주인은 하나" 규칙으로
  파이썬에서 직접 센 값과 같은가. 빌드 때 표시한 소유권 / 조회 때 계산한 소유권 / 옛 스키마 인덱스 세 경로 모두.
- 커서로 끝까지 넘기면 한 번에 받은 목록과 같은가.
- 실행 계획 단언: 핫 경로가 의도한 인덱스를 쓰는가 (SQLite 버전이 바뀌어도 이 모양이 유지되는지 지킨다).
"""
import random
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import cindex  # noqa: E402

REF, DECL, DEF, CALL = cindex.REF, cindex.DECL, cindex.DEF, cindex.CALL


def make_raw(path, files, symbols, refs, relations=(), scope="project", old_schema=False):
    """적재 직후 모양(스키마 1)의 원본 DB. files: [(path, root, rel, module)] — id 는 넣은 순서(경로 순이 아니게 섞어서 준다).
    symbols: [(id, name, scope, kind, decl_path)]. refs: [(sym, kind, path, line, col, container)]."""
    con = sqlite3.connect(str(path))
    con.executescript(cindex.SCHEMA)
    fid = {}
    for p, root, rel, mod in files:
        cur = con.execute("INSERT INTO files(path, module, root, rel, mtime) VALUES(?,?,?,?,0)", (p, mod, root, rel))
        fid[p] = cur.lastrowid
    for sid, name, sc, kind, decl in symbols:
        con.execute("INSERT INTO symbols VALUES(?,?,?,?,?,'C++',?,?,1,NULL,NULL,NULL,'','','','',0,0,'')",
                    (sid, name, sc, sc + name, kind, fid.get(decl), 1))
    con.executemany("INSERT INTO refs VALUES(?,?,?,?,?,?)", [(s, k, fid[p], ln, c, ct) for s, k, p, ln, c, ct in refs])
    con.executemany("INSERT INTO relations VALUES(?,?,?)", relations)
    roots = [["project", "/proj"], ["engine", "/eng"]]
    con.executemany("INSERT INTO meta VALUES(?,?)", [("roots", __import__("json").dumps(roots)), ("scope", scope),
                                                     ("generated_at", f"2026-10-08 00:00:{random.randint(0, 59):02d}"),
                                                     ("counts", __import__("json").dumps({"refs": len(refs)}))])
    if old_schema:  # 스키마 1 인덱스 그대로 (옛 인덱스)
        con.executescript("CREATE INDEX symbols_name ON symbols(name COLLATE NOCASE); CREATE INDEX symbols_qname ON symbols(qname COLLATE NOCASE);"
                          "CREATE INDEX symbols_decl ON symbols(decl_file); CREATE INDEX refs_sym ON refs(sym);"
                          "CREATE INDEX refs_container ON refs(container); CREATE INDEX rel_subject ON relations(subject, predicate);"
                          "CREATE INDEX rel_object ON relations(object, predicate);")
    con.commit()
    con.close()


class Fixture:
    """엔진 파일 E0..E5, 프로젝트 파일 P0..P3. 프로젝트 인덱스는 엔진 헤더 E0·E1(엔진 인덱스에도 있음)과 E9(엔진 TU 가 안 연 헤더)를 본다."""

    def __init__(self, tmp, seed=3):
        rnd = random.Random(seed)
        self.tmp = Path(tmp)
        eng_files = [(f"/eng/Source/Runtime/M{i % 3}/Public/E{i}.h", "engine", f"Source/Runtime/M{i % 3}/Public/E{i}.h", f"M{i % 3}")
                     for i in range(6)]
        e9 = ("/eng/Source/Runtime/M9/Public/E9.h", "engine", "Source/Runtime/M9/Public/E9.h", "M9")
        proj_files = [(f"/proj/Source/Game/P{i}.cpp", "project", f"Source/Game/P{i}.cpp", "Game") for i in range(4)]
        syms = [(f"S{i:02d}", f"Name{i}", "UThing::" if i % 4 else "", "InstanceMethod" if i % 4 else "Class",
                 eng_files[i % 6][0]) for i in range(24)]
        funcs = [s[0] for s in syms if s[3] == "InstanceMethod"]
        hot = "S01"
        eng_refs, shared = [], []
        for f in eng_files:
            for n in range(rnd.randint(30, 60)):
                sym = hot if rnd.random() < 0.4 else rnd.choice(syms)[0]
                r = (sym, rnd.choice([REF, REF | CALL, DECL, DEF, REF]), f[0], rnd.randint(1, 400), rnd.randint(1, 80),
                     rnd.choice(funcs + [cindex.NULL_ID]))
                eng_refs.append(r)
                if f in eng_files[:2]:
                    shared.append(r)  # 프로젝트 TU 도 이 엔진 헤더를 파싱했다 → 같은 참조가 프로젝트 인덱스에도
        proj_refs = list(shared)
        for f in proj_files + [e9]:
            for n in range(rnd.randint(20, 40)):
                sym = hot if rnd.random() < 0.4 else rnd.choice(syms)[0]
                proj_refs.append((sym, rnd.choice([REF, REF | CALL, DECL, REF]), f[0], rnd.randint(1, 400),
                                  rnd.randint(1, 80), rnd.choice(funcs + [cindex.NULL_ID])))
        eng_refs = list(dict.fromkeys(eng_refs))
        proj_refs = list(dict.fromkeys(proj_refs))
        rnd.shuffle(eng_files)  # 파일 id 가 경로 순이 아니게
        all_proj_files = proj_files + eng_files[:0] + [x for x in eng_files if x[0] in {r[2] for r in shared}] + [e9]
        rnd.shuffle(all_proj_files)
        self.syms, self.hot, self.funcs = syms, hot, funcs
        self.eng_refs, self.proj_refs = eng_refs, proj_refs
        self.eng_files, self.proj_files_all = eng_files, all_proj_files
        self.module = {f[0]: f[3] for f in eng_files + all_proj_files}
        self.rel = {f[0]: ("[E] " if f[1] == "engine" else "") + f[2] for f in eng_files + all_proj_files}
        self.eng_owned = {r[2] for r in eng_refs}
        # 정답: 엔진 참조 전부 + 프로젝트 참조 중 엔진이 주인이 아닌 파일의 것
        self.truth_proj = [r for r in proj_refs if r[2] not in self.eng_owned]
        self.truth = self.truth_proj + eng_refs

    def build(self, old_project=False, old_engine=False):
        er, pr = self.tmp / "eng.raw", self.tmp / "proj.raw"
        for f in (er, pr):
            f.unlink(missing_ok=True)
        make_raw(er, self.eng_files, self.syms, self.eng_refs, scope="engine", old_schema=old_engine)
        make_raw(pr, self.proj_files_all, self.syms, self.proj_refs, scope="project", old_schema=old_project)
        edb, pdb = self.tmp / "eng.sqlite", self.tmp / "proj.sqlite"
        if old_engine:
            er.replace(edb)
        else:
            cindex.finalize(er, edb)
        if old_project:
            pr.replace(pdb)
        else:
            cindex.finalize(pr, pdb, engine_db=edb)
        return pdb, edb

    def open(self, pdb, edb):
        return cindex.MultiIndex([cindex.Index(pdb, "project"), cindex.Index(edb, "engine")])


def key(r):
    return (r["path"], r["line"], r["col"], r["kind"])


class MergedQueryTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.fx = Fixture(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def truth_for(self, sym, mask=None):
        return [r for r in self.fx.truth if r[0] == sym and (not mask or r[1] & mask)]

    def expected_order(self, sym, mask=None):
        """프로젝트 몫 경로 순 → 엔진 몫 경로 순."""
        fx = self.fx
        part = lambda rs: sorted(((fx.rel[r[2]], r[3], r[4], r[1]) for r in rs if r[0] == sym and (not mask or r[1] & mask)))
        return part(fx.truth_proj) + part(fx.eng_refs)

    def check_all(self, mx, label):
        fx = self.fx
        for sym in [s[0] for s in fx.syms]:
            want = self.expected_order(sym)
            got = [key(r) for r in mx.refs(sym, None, 10_000)]
            self.assertEqual(got, want, f"{label}: refs 순서·내용 {sym}")
            self.assertEqual(mx.ref_count(sym), len(want), f"{label}: ref_count {sym}")
            use = self.truth_for(sym, REF)
            self.assertEqual(sum(n for _, n in mx.ref_parts(sym, REF)), len(use), f"{label}: 사용 수 {sym}")
            calls = {}
            for r in use:
                calls[r[5]] = calls.get(r[5], 0) + 1
            got_calls = {c: n for c, n, *_ in mx._callers(sym, 10_000)}
            self.assertEqual(got_calls, calls, f"{label}: 호출자 {sym}")
            self.assertEqual(mx.callers_total(sym), len(set(r[5] for r in use if r[2] not in fx.eng_owned))
                             + len(set(r[5] for r in use if r[2] in fx.eng_owned)), f"{label}: 호출자 수 {sym}")
            mods = {}
            for r in use:
                mods[fx.module[r[2]]] = mods.get(fx.module[r[2]], 0) + 1
            self.assertEqual(dict(mx.modules(sym, 100)[0]), mods, f"{label}: 모듈 {sym}")
            files = {}
            for r in use:
                files[fx.rel[r[2]]] = files.get(fx.rel[r[2]], 0) + 1
            frows, ftotal = mx.files(sym, 100)
            self.assertEqual(dict(frows), files, f"{label}: 파일 {sym}")
            self.assertEqual(ftotal, len(files), f"{label}: 파일 수 {sym}")
        for f in fx.funcs[:6]:
            want = {}
            for r in fx.truth:
                if r[5] == f and (r[1] & (REF | CALL)) == (REF | CALL):
                    want[r[0]] = want.get(r[0], 0) + 1
            want = {k: v for k, v in want.items() if dict((s[0], s[3]) for s in fx.syms)[k] in cindex.FUNC_KINDS}
            self.assertEqual({x["id"]: n for x, n in mx.callees(f)}, want, f"{label}: 피호출 {f}")

    def page_through(self, mx, sym, step):
        out, cur, guard = [], None, 0
        while True:
            rows, more, nxt = mx.refs_page(sym, None, step, cur)
            out += [key(r) for r in rows]
            guard += 1
            self.assertLess(guard, 10_000)
            if not more:
                return out
            self.assertIsNotNone(nxt)
            cur = nxt

    def test_owner_marked_at_build(self):
        pdb, edb = self.fx.build()
        mx = self.fx.open(pdb, edb)
        self.assertEqual(mx.parts[0][1], "owned_out")
        self.assertTrue(mx.parts[0][2] and mx.parts[1][2], "요약 표를 쓴다")
        self.check_all(mx, "빌드 표시")
        for step in (1, 3, 7):
            self.assertEqual(self.page_through(mx, self.fx.hot, step), self.expected_order(self.fx.hot), f"커서 {step}")

    def test_owner_computed_at_query(self):
        pdb, edb = self.fx.build()
        cindex.finalize(self.fx.tmp / "eng.sqlite", self.fx.tmp / "eng2.sqlite")  # 다른 build_id 의 엔진 인덱스
        mx = self.fx.open(pdb, self.fx.tmp / "eng2.sqlite")
        self.assertEqual(mx.parts[0][1], "temp.owned_tmp")
        self.assertFalse(mx.parts[0][2], "표시가 낡았으면 프로젝트 요약 표를 안 쓴다")
        self.check_all(mx, "조회 때 계산")
        cindex.refresh_owner(pdb, self.fx.tmp / "eng2.sqlite", log=lambda m: None)
        mx = self.fx.open(pdb, self.fx.tmp / "eng2.sqlite")
        self.assertEqual(mx.parts[0][1], "owned_out")
        self.check_all(mx, "refresh_owner 뒤")

    def test_old_schema(self):
        pdb, edb = self.fx.build(old_project=True, old_engine=True)
        mx = self.fx.open(pdb, edb)
        self.assertFalse(any(ok for _, _, ok in mx.parts))
        self.assertFalse(mx.ixs[0].path_order)
        self.check_all(mx, "옛 스키마")
        self.assertEqual(self.page_through(mx, self.fx.hot, 4), self.expected_order(self.fx.hot), "옛 스키마 커서(OFFSET)")
        cindex.upgrade_db(edb, None, log=lambda m: None)
        cindex.upgrade_db(pdb, edb, log=lambda m: None)
        mx = self.fx.open(pdb, edb)
        self.assertEqual(mx.parts[0][1], "owned_out")
        self.check_all(mx, "optimize 뒤")

    def test_project_alone_ignores_own_stats(self):
        """엔진 인덱스 없이 프로젝트 인덱스만 보면 엔진 헤더 참조도 다 센다 — 'own' 요약 표를 쓰면 안 된다."""
        pdb, _ = self.fx.build()
        mx = cindex.MultiIndex([cindex.Index(pdb, "project")])
        self.assertFalse(mx.parts[0][2])
        n = sum(1 for r in self.fx.proj_refs if r[0] == self.fx.hot)
        self.assertEqual(mx.ref_count(self.fx.hot), n)


class PlanTest(unittest.TestCase):
    """핫 경로의 실행 계획. 스키마 2 인덱스에서."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        fx = Fixture(cls.tmpdir.name)
        cls.pdb, cls.edb = fx.build()
        cls.con = sqlite3.connect(str(cls.edb))

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmpdir.cleanup()

    def plan(self, sql, args):
        return " | ".join(r[3] for r in self.con.execute("EXPLAIN QUERY PLAN " + sql, args))

    def test_refs_page_uses_ordered_index(self):
        p = self.plan("SELECT r.kind FROM refs r LEFT JOIN files f ON f.id=r.file WHERE r.sym=? "
                      "ORDER BY r.file, r.line, r.col LIMIT 61", ("S01",))
        self.assertIn("refs_sym_file", p)
        self.assertNotIn("TEMP B-TREE", p, "경로 순 정렬을 인덱스가 준다")

    def test_only_one_sym_leading_refs_index(self):
        idx = [r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='refs'")]
        leading = [n for n in idx if self.con.execute(f"PRAGMA index_info({n})").fetchone()[2] == "sym"]
        self.assertEqual(leading, ["refs_sym_file"], "sym 으로 시작하는 인덱스가 둘이면 플래너가 나쁜 쪽을 고를 수 있다")

    def test_stats_lookups(self):
        self.assertIn("sym_callers_sym", self.plan("SELECT container, n FROM sym_callers WHERE sym=? ORDER BY n DESC LIMIT 60", ("S01",)))
        self.assertIn("PRIMARY KEY", self.plan("SELECT n_refs FROM sym_stats WHERE sym=?", ("S01",)))

    def test_members_and_file_syms(self):
        self.assertIn("symbols_scope", self.plan(cindex.Index.SYM + "WHERE s.scope = ?", ("UThing::",)))
        p = self.plan(cindex.Index.FILE_SYM, ("%E1%", 200))
        self.assertIn("symbols_decl", p)
        self.assertNotIn("SCAN s ", p + " ")

    def test_prefix_search_uses_index(self):
        p = self.plan(cindex.Index.SYM + "WHERE s.name LIKE ? ESCAPE '\\' OR s.qname LIKE ? ESCAPE '\\' LIMIT 80", ("Name1%", "Name1%"))
        self.assertIn("symbols_name", p)
        self.assertIn("symbols_qname", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
