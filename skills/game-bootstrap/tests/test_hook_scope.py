#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""훅 범위 시험 (표준 라이브러리 unittest): stuck_watch · diagram_view 가 게임 프로젝트에서만 도는가.

  python skills/game-bootstrap/tests/test_hook_scope.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent / "harness"


def run(hook, data, home):
    env = dict(os.environ, USERPROFILE=str(home), HOME=str(home), GAME_HARNESS_NO_OPEN="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    r = subprocess.run([sys.executable, str(HARNESS / hook)], input=json.dumps(data).encode("utf-8"),
                       capture_output=True, env=env, cwd=str(HARNESS))
    return r.stdout.decode("utf-8", "replace")


class HookScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.home, self.game, self.plain = t / "home", t / "Game", t / "relay-workspace"
        for d in (self.home, self.game / "Source", self.plain):
            d.mkdir(parents=True)
        (self.game / "Game.uproject").write_text('{"EngineAssociation": "5.7"}', encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def edits(self, root, name, n=5, session="s1"):
        out = ""
        for _ in range(n):
            out = run("stuck_watch.py", {"hook_event_name": "PostToolUse", "tool_name": "Edit", "session_id": session,
                                         "cwd": str(root), "tool_input": {"file_path": str(root / name)}}, self.home)
        return out

    def test_stuck_watch(self):
        self.assertIn("매몰 신호", self.edits(self.game, "Source/A.cpp", session="g"))  # 게임 · 코드 → 경고
        self.assertEqual(self.edits(self.game, "Docs/PLAN.md", session="d"), "")      # 게임 · 문서 → 없음
        self.assertEqual(self.edits(self.plain, "src/a.py", session="p"), "")        # 게임 아님 → 없음

    def test_diagram_view(self):
        msg = "그림\n```mermaid\ngraph LR\n  A --> B\n```\n"
        self.assertEqual(run("diagram_view.py", {"last_assistant_message": msg, "cwd": str(self.plain)}, self.home), "")
        out = run("diagram_view.py", {"last_assistant_message": msg, "cwd": str(self.game)}, self.home)
        self.assertIn("Mermaid", out)
        self.assertTrue(any((self.game / "Saved" / "ClaudeArch").glob("*.html")))

    def test_diagram_view_renders_fresh_structure_doc(self):
        arch = self.game / "Saved" / "ClaudeArch"
        arch.mkdir(parents=True)
        doc = arch / "20261020-전투.md"
        doc.write_text("# 전투\n\n요약 줄.\n\n## 구조\n```mermaid\ngraph LR\n  A --> B\n```\n", encoding="utf-8")
        old = arch / "20260101-옛.md"
        old.write_text("# 옛\n```mermaid\ngraph LR\n  A --> B\n```\n", encoding="utf-8")
        os.utime(old, (1, 1))  # 오래된 기록은 열지 않는다
        out = run("diagram_view.py", {"last_assistant_message": "끝냈다.", "cwd": str(self.game)}, self.home)
        self.assertIn("구조 문서", json.loads(out)["systemMessage"])
        html = doc.with_suffix(".html").read_text(encoding="utf-8")
        self.assertIn("전체 내용", html)
        self.assertFalse(old.with_suffix(".html").exists())
        self.assertEqual(run("diagram_view.py", {"last_assistant_message": "또.", "cwd": str(self.game)}, self.home), "")

    def test_diagram_view_structure_figure(self):
        arch = self.game / "Saved" / "ClaudeArch"
        arch.mkdir(parents=True)
        doc = arch / "20261020-조건.md"
        doc.write_text("# 조건\n\n## 선택지\n| A | 4곳 |\n\n## 그림\n```mermaid\ngraph LR\n  A --> B\n```\n\n## 근거\n- x\n",
                       encoding="utf-8")
        msg = json.loads(run("diagram_view.py", {"last_assistant_message": "끝.", "cwd": str(self.game)}, self.home))
        self.assertIn("구조도 0장", msg["systemMessage"])  # diagram-design Before/After 가 없으면 알린다
        html = doc.with_suffix(".html")
        os.utime(html, (time.time() - 60, time.time() - 60))
        (arch / "20261020-조건-구조-A.html").write_text("<svg/>", encoding="utf-8")  # 나중에 그린 구조도
        msg = json.loads(run("diagram_view.py", {"last_assistant_message": "그림.", "cwd": str(self.game)}, self.home))
        self.assertNotIn("구조도 0장", msg["systemMessage"])
        self.assertIn('figure class=\\"dd\\"', html.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
