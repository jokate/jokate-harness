#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세션 시작 안내: 그 프로젝트에 있는 위키 · 인덱스만, 명령 줄 그대로 (표준 라이브러리 unittest).

  python skills/game-bootstrap/tests/test_game_context.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
import game_context  # noqa: E402


class Facts(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        t = Path(self._td.name)
        self.root, self.home = t / "Game", t / "home"
        (self.root / "Saved" / "ClaudeIndex").mkdir(parents=True)

    def lines(self, engine="Unreal Engine 5.7"):
        return "\n".join(game_context.fact_lines(self.root, engine, home=self.home))

    def test_nothing_to_say_without_index_or_wiki(self):
        self.assertEqual(self.lines(), "")

    def test_no_request_to_skill_table(self):
        """요청별 스킬 줄은 넣지 않는다 — 스킬 설명이 한다 (2026-11-10 대조)."""
        (self.root / "Saved" / "ClaudeIndex" / "clangd.sqlite").write_bytes(b"x")
        out = self.lines()
        for name in ("game-architecture", "game-design-doc", "game-testing", "game-mcp", "→"):
            self.assertNotIn(name, out)  # game-onboard 는 명령 경로에 들어 있어 보지 않는다
        self.assertNotIn("MCP 실패", out)

    def test_only_existing_indexes(self):
        (self.root / "Saved" / "ClaudeIndex" / "symbols.json").write_text("{}", encoding="utf-8")
        out = self.lines()
        self.assertIn("gq.py find <이름>", out)
        self.assertNotIn("cindex.py", out)
        self.assertNotIn("위키", out)

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
        # 명령 넷은 줄 그대로 — 줄이면 cindex 호출이 반으로 줄었다 (2026-10-22 대조)
        for cmd in ("cindex.py refs <심볼>", "cindex.py callers <심볼>", "cindex.py derived <클래스>", "cindex.py impact <심볼>"):
            self.assertIn(cmd, out)
        self.assertIn(f"python {self.home.as_posix()}/.claude/skills/game-onboard/scripts/cindex.py", out)
        self.assertNotIn("~/", out)
        self.assertIn(f"위키 `{wiki.as_posix()}/index.md`", out)
        self.assertIn("rg", out)

    def test_team_feedback_ledger_is_listed_only_when_it_has_entries(self):
        ledger = self.root / ".claude" / "team_feedback.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("# 팀 피드백\n", encoding="utf-8")
        self.assertEqual(self.lines(), "")
        ledger.write_text("# 팀 피드백\n\n## 2026-11-15 · 데이터 구조\n- 누가: 동료\n\n## 2026-11-20 · 세팅 방식\n", encoding="utf-8")
        out = self.lines()
        self.assertIn("팀 피드백 장부", out)
        self.assertIn("2건", out)
        self.assertIn("game-architecture", out)

    def test_unity_uses_library(self):
        (self.root / "Library" / "ClaudeIndex").mkdir(parents=True)
        (self.root / "Library" / "ClaudeIndex" / "symbols.json").write_text("{}", encoding="utf-8")
        self.assertIn("gq.py find", self.lines("Unity 2022.3"))


if __name__ == "__main__":
    unittest.main()
