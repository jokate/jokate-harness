#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP 실패 → 가드 규칙 후보 (표준 라이브러리 unittest): 같은 종류는 한 줄로 합치고, 세팅 안 된 곳에는 쓰지 않는다.
세션 시작 안내는 후보가 있을 때만 한 줄을 더한다.

  python skills/game-bootstrap/tests/test_mcp_pending.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent / "harness"
sys.path.insert(0, str(HARNESS))
import game_context  # noqa: E402


def call(data, home):
    env = dict(os.environ, USERPROFILE=str(home), HOME=str(home))
    subprocess.run([sys.executable, str(HARNESS / "mcp_log.py")], input=json.dumps(data).encode("utf-8"),
                   capture_output=True, env=env, cwd=str(HARNESS))


class Pending(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.home, self.game, self.plain = t / "home", t / "Game", t / "plain"
        for d in (self.home, self.game / ".claude", self.plain):
            d.mkdir(parents=True)
        (self.game / "Game.uproject").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def fail(self, cwd, err, tool="mcp__unreal__set_object_property"):
        call({"hook_event_name": "PostToolUseFailure", "tool_name": tool, "cwd": str(cwd),
              "tool_input": {"actor": "BP_A"}, "error": err}, self.home)

    def test_same_kind_merges_and_counts(self):
        self.fail(self.game, "Property 'Speed' not found on C:/P/Content/BP_A.uasset (line 12)")
        self.fail(self.game, "Property 'Damage' not found on C:/P/Content/BP_B.uasset (line 40)")
        self.fail(self.game, "Editor is not connected")
        doc = json.loads((self.game / ".claude" / "mcp_guards.pending.json").read_text(encoding="utf-8"))
        self.assertEqual([p["count"] for p in doc["pending"]], [2, 1])
        self.assertIn("<값>", doc["pending"][0]["error"])  # 이름 · 경로 · 숫자를 지워 같은 종류로 모았다
        self.assertEqual(doc["pending"][0]["tool"], "mcp__unreal__set_object_property")
        self.assertIn("MCP 실패 2종", game_context.pending_guards(self.game)[0])

    def test_success_and_unset_project_write_nothing(self):
        call({"hook_event_name": "PostToolUse", "tool_name": "mcp__unreal__get_asset_info", "cwd": str(self.game),
              "tool_input": {}, "tool_response": "ok"}, self.home)
        self.assertFalse((self.game / ".claude" / "mcp_guards.pending.json").exists())
        self.fail(self.plain, "boom")
        self.assertFalse((self.plain / ".claude").exists())  # 세팅 안 된 곳에는 만들지 않는다
        self.assertEqual(game_context.pending_guards(self.game), [])


if __name__ == "__main__":
    unittest.main()
