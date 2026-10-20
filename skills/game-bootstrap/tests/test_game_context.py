#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세션 시작 라우팅의 '코드 찾기' 줄: 있는 인덱스만 명령 줄 그대로 알려 준다 (표준 라이브러리 unittest).

  python skills/game-bootstrap/tests/test_game_context.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
import game_context  # noqa: E402


class SearchRouting(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        t = Path(self._td.name)
        self.root, self.home = t / "Game", t / "home"
        (self.root / "Saved" / "ClaudeIndex").mkdir(parents=True)

    def lines(self, engine="Unreal Engine 5.7"):
        return "\n".join(game_context.search_routing(self.root, engine, home=self.home))

    def test_nothing_without_index(self):
        self.assertEqual(self.lines(), "")

    def test_only_existing_indexes(self):
        (self.root / "Saved" / "ClaudeIndex" / "symbols.json").write_text("{}", encoding="utf-8")
        out = self.lines()
        self.assertIn("gq.py find <이름>", out)
        self.assertNotIn("cindex.py", out)
        self.assertNotIn("위키", out)
        self.assertIn("→ rg", out)

    def test_clangd_and_wiki(self):
        (self.root / "Saved" / "ClaudeIndex" / "clangd.sqlite").write_bytes(b"x")
        wiki = self.home / ".jokate-wiki" / "Game"
        wiki.mkdir(parents=True)
        (wiki / "index.md").write_text("# w", encoding="utf-8")
        out = self.lines()
        self.assertIn("cindex.py callers <심볼>", out)
        self.assertIn("grep 으로 추측하지 않는다", out)
        self.assertIn(f"{wiki.as_posix()}/index.md", out)

    def test_unity_uses_library(self):
        (self.root / "Library" / "ClaudeIndex").mkdir(parents=True)
        (self.root / "Library" / "ClaudeIndex" / "symbols.json").write_text("{}", encoding="utf-8")
        self.assertIn("gq.py find", self.lines("Unity 2022.3"))


if __name__ == "__main__":
    unittest.main()
