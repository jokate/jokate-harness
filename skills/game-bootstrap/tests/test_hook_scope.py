#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""뺀 훅 시험 (표준 라이브러리 unittest): 뺀 훅의 하네스 등록만 지우는가.

  python skills/game-bootstrap/tests/test_hook_scope.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
import install  # noqa: E402



class DropObsolete(unittest.TestCase):
    """뺀 훅(handoff · diagram_view · stuck_watch)의 하네스 등록만 지우고, 다른 훅과 같은 이름의 남의 훅은 둔다."""

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

    def test_plain_install_also_drops_the_registration(self):
        """install.bat(--apply-settings 없음)도 등록을 지운다 — 파일만 치우면 프롬프트마다 오류가 떴다(2026-10-23)."""
        with tempfile.TemporaryDirectory() as d:
            claude, saved = Path(d) / ".claude", install.CLAUDE
            (claude / "hooks").mkdir(parents=True)
            cmd = f"python {claude / 'hooks' / 'handoff.py'}"
            keep = {"type": "command", "command": f"python {claude / 'hooks' / 'game_context.py'}"}
            settings = {"model": "x", "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd}]}],
                                                "SessionStart": [{"hooks": [keep]}]}}
            (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            install.CLAUDE = claude
            try:
                self.assertTrue(install.drop_obsolete_settings(dry=False))
                got = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
                self.assertEqual(got, {"model": "x", "hooks": {"SessionStart": [{"hooks": [keep]}]}})
                self.assertTrue((claude / "settings.json.bak").is_file())
                self.assertTrue(install.drop_obsolete_settings(dry=False))  # 두 번째는 할 일 없음
                (claude / "settings.json").write_text("{ broken", encoding="utf-8")
                self.assertFalse(install.drop_obsolete_settings(dry=False))  # 못 읽으면 False → 뺀 훅 파일을 둔다
            finally:
                install.CLAUDE = saved

    def test_stuck_watch_groups_go_and_neighbours_stay(self):
        """stuck_watch 만 든 묶음은 통째로 사라지고, 같은 이벤트의 다른 훅은 남는다."""
        hooks_dir = str(Path.home() / ".claude" / "hooks")
        h = lambda n: {"type": "command", "command": "python", "args": [os.path.join(hooks_dir, n)]}  # noqa: E731
        hooks = {"PostToolUse": [{"matcher": "mcp__.*", "hooks": [h("mcp_log.py")]},
                                 {"matcher": "Edit|Write|NotebookEdit|Bash|PowerShell", "hooks": [h("stuck_watch.py")]},
                                 {"matcher": "Skill|Bash|PowerShell", "hooks": [h("harness_trace.py")]}],
                 "PostToolUseFailure": [{"matcher": "Bash|PowerShell", "hooks": [h("stuck_watch.py")]}]}
        removed = install.drop_obsolete(hooks)
        self.assertEqual(sorted(removed), ["PostToolUse:stuck_watch.py", "PostToolUseFailure:stuck_watch.py"])
        self.assertEqual([g["matcher"] for g in hooks["PostToolUse"]], ["mcp__.*", "Skill|Bash|PowerShell"])
        self.assertNotIn("PostToolUseFailure", hooks)

    def test_snippet_has_no_obsolete(self):
        text = json.dumps(install.settings_snippet())
        for name in install.OBSOLETE_HOOKS:
            self.assertNotIn(name, text)
            self.assertNotIn(name, install.HOOKS)


if __name__ == "__main__":
    unittest.main()
