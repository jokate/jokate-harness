#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배경 색인 잠금 · 조용한 실행 (표준 라이브러리 unittest): 같은 프로젝트의 색인이 살아 있으면 건너뛰고,
죽었거나 오래된 잠금은 넘어간다. 기본은 낮은 우선순위로 clangd 를 띄운다.

  python skills/game-onboard/tests/test_cindex_lock.py
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import cindex  # noqa: E402
import cindex_speed  # noqa: E402


class Lock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "bg.lock"

    def tearDown(self):
        self.tmp.cleanup()

    def test_alive_lock_skips(self):
        self.path.write_text(json.dumps({"pid": os.getpid(), "started": time.time()}), encoding="utf-8")
        self.assertIsNone(cindex.take_lock(self.path))  # 이 프로세스가 살아 있다 → 건너뛴다

    def test_dead_or_stale_lock_is_taken(self):
        self.path.write_text(json.dumps({"pid": 999999, "started": time.time()}), encoding="utf-8")
        self.assertEqual(cindex.take_lock(self.path), self.path)  # 없는 pid
        self.path.write_text(json.dumps({"pid": os.getpid(), "started": time.time() - cindex.LOCK_STALE_S - 10}),
                             encoding="utf-8")
        self.assertEqual(cindex.take_lock(self.path), self.path)  # 12시간 넘은 잠금
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["pid"], os.getpid())

    def test_broken_lock_is_taken(self):
        self.path.write_text("{", encoding="utf-8")
        self.assertEqual(cindex.take_lock(self.path), self.path)

    def test_pid_alive(self):
        self.assertTrue(cindex.pid_alive(os.getpid()))
        self.assertFalse(cindex.pid_alive(999999))
        self.assertFalse(cindex.pid_alive(0))


class Unchanged(unittest.TestCase):
    """배경 색인이 샤드를 하나도 바꾸지 않았으면 DB 를 다시 쓰지 않는다."""

    def test_rules(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "clangd.sqlite"
            base = {"source": "clangd-background", "cold": False, "removed_shards": 0}
            self.assertFalse(cindex.unchanged_since(db, {**base, "newest_shard": 1.0}))  # DB 가 없다
            db.write_bytes(b"x")
            t = db.stat().st_mtime
            self.assertTrue(cindex.unchanged_since(db, {**base, "newest_shard": t - 5}))
            self.assertFalse(cindex.unchanged_since(db, {**base, "newest_shard": t + 5}))      # 새로 쓴 샤드
            self.assertFalse(cindex.unchanged_since(db, {**base, "newest_shard": t - 5, "removed_shards": 2}))
            self.assertFalse(cindex.unchanged_since(db, {**base, "newest_shard": t - 5, "cold": True}))
            self.assertFalse(cindex.unchanged_since(db, {"source": "clangd-indexer", "newest_shard": 0}))


class Gentle(unittest.TestCase):
    def test_low_priority_kwargs(self):
        kw = cindex_speed.low_priority_kwargs()
        if os.name == "nt":
            self.assertEqual(kw["creationflags"] & 0x4000, 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS
        else:
            self.assertIn("preexec_fn", kw)


if __name__ == "__main__":
    unittest.main()
