#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세션 시작 안내: 스킬 라우팅(한 곳) + 있는 인덱스만 명령 줄 그대로 (표준 라이브러리 unittest).

  python skills/game-bootstrap/tests/test_game_context.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
import game_context  # noqa: E402


class Routing(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        t = Path(self._td.name)
        self.root, self.home = t / "Game", t / "home"
        (self.root / "Saved" / "ClaudeIndex").mkdir(parents=True)

    def lines(self, engine="Unreal Engine 5.7"):
        return "\n".join(game_context.routing_lines(self.root, engine, home=self.home))

    def test_skills_always_index_only_when_present(self):
        out = self.lines()
        self.assertIn("game-architecture", out)
        self.assertIn("구조 · 위치 · 엔진 API 질문 → game-onboard", out)  # 위키가 없으면 game-onboard
        self.assertNotIn("코드 찾기", out)
        self.assertNotIn("game-patterns", out)  # game-architecture 에 합쳤다

    def test_only_existing_indexes(self):
        (self.root / "Saved" / "ClaudeIndex" / "symbols.json").write_text("{}", encoding="utf-8")
        out = self.lines()
        self.assertIn("gq.py find <이름>", out)
        self.assertNotIn("cindex.py", out)
        self.assertNotIn("위키", out)
        self.assertIn("→ rg", out)

    def test_gq_only_when_the_project_refreshes_it(self):
        (self.root / "Saved" / "ClaudeIndex" / "symbols.json").write_text("{}", encoding="utf-8")
        (self.root / ".claude").mkdir()
        spec = self.root / ".claude" / "session_start.json"
        spec.write_text(json.dumps({"commands": [{"run": ["Tools/my_q.py", "index"]}]}), encoding="utf-8")
        self.assertNotIn("gq.py", self.lines())  # 자기 조회 도구를 쓰고 gq 갱신을 끈 프로젝트 (MNYS)
        spec.write_text(json.dumps({"commands": [{"run": ["~/.claude/skills/game-onboard/scripts/gq.py", "index"]}]}),
                        encoding="utf-8")
        self.assertIn("gq.py find", self.lines())

    def test_clangd_and_wiki(self):
        (self.root / "Saved" / "ClaudeIndex" / "clangd.sqlite").write_bytes(b"x")
        wiki = self.home / ".jokate-wiki" / "Game"
        wiki.mkdir(parents=True)
        (wiki / "index.md").write_text("# w", encoding="utf-8")
        out = self.lines()
        self.assertIn("cindex.py callers <심볼>", out)
        self.assertIn("cindex.py refs <심볼>", out)
        self.assertIn("grep 으로 추측하지 않는다", out)
        self.assertIn(f"python {self.home.as_posix()}/.claude/skills/game-onboard/scripts/cindex.py", out)
        self.assertNotIn("~/", out)
        self.assertIn(f"맥락은 위키 먼저(wiki-query, `{wiki.as_posix()}/index.md`)", out)
        self.assertIn("코드 세부(어디서 쓰나 · 누가 부르나 · 바꾸면 영향)는 아래 cindex", out)

    def test_unity_uses_library(self):
        (self.root / "Library" / "ClaudeIndex").mkdir(parents=True)
        (self.root / "Library" / "ClaudeIndex" / "symbols.json").write_text("{}", encoding="utf-8")
        self.assertIn("gq.py find", self.lines("Unity 2022.3"))


if __name__ == "__main__":
    unittest.main()
