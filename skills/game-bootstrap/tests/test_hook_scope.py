#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""훅 범위 시험 (표준 라이브러리 unittest): stuck_watch 가 게임 프로젝트에서만 도는가 · 뺀 훅의 등록을 지우는가.

  python skills/game-bootstrap/tests/test_hook_scope.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent / "harness"
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
import install  # noqa: E402


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
        out = self.edits(self.game, "Source/A.cpp", session="g")                    # 게임 · 코드 → 경고
        self.assertIn("매몰 신호", out)
        self.assertNotIn("[RESET]", out)  # HandOff 를 뺐다 — 없는 명령을 안내하지 않는다
        self.assertEqual(self.edits(self.game, "Docs/PLAN.md", session="d"), "")      # 게임 · 문서 → 없음
        self.assertEqual(self.edits(self.plain, "src/a.py", session="p"), "")        # 게임 아님 → 없음


class DropObsolete(unittest.TestCase):
    """뺀 훅(handoff · diagram_view)의 하네스 등록만 지우고, 다른 훅과 같은 이름의 남의 훅은 둔다."""

    def test_only_harness_entries_go(self):
        hooks_dir = str(Path.home() / ".claude" / "hooks")
        h = lambda n: {"type": "command", "command": "python", "args": [os.path.join(hooks_dir, n)]}  # noqa: E731
        other = {"type": "command", "command": "python D:/mine/handoff.py"}
        hooks = {"SessionStart": [{"hooks": [h("session_start.py"), h("game_context.py"), h("handoff.py")]}],
                 "UserPromptSubmit": [{"hooks": [h("handoff.py")]}],
                 "Stop": [{"hooks": [h("diagram_view.py"), other]}]}
        removed = install.drop_obsolete(hooks)
        self.assertEqual(sorted(removed), ["SessionStart:handoff.py", "Stop:diagram_view.py", "UserPromptSubmit:handoff.py"])
        self.assertNotIn("UserPromptSubmit", hooks)  # 빈 이벤트는 지운다
        self.assertEqual([x["args"][0].rsplit(os.sep, 1)[-1] for x in hooks["SessionStart"][0]["hooks"]],
                         ["session_start.py", "game_context.py"])
        self.assertEqual(hooks["Stop"][0]["hooks"], [other])  # 하네스 것이 아닌 handoff.py 는 둔다

    def test_snippet_has_no_obsolete(self):
        text = json.dumps(install.settings_snippet())
        for name in install.OBSOLETE_HOOKS:
            self.assertNotIn(name, text)
            self.assertNotIn(name, install.HOOKS)


if __name__ == "__main__":
    unittest.main()
