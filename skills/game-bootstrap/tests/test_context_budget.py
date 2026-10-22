#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""항상 들어가는 글 예산 (표준 라이브러리 unittest): 하네스가 세션마다 넣는 글이 한도를 넘지 않는가.

  python skills/game-bootstrap/tests/test_context_budget.py

Harness²(arXiv 2610.14224): 항상 들어가는 글은 가장 비싸다 — 더하면 다른 것을 뺀다. 한도를 바꾸려면 이유를 docs/experience 에.
- 하네스 스킬 description 합 ≤ 4,000 B (2026-10-22 정리 뒤 3,537 B. 그 전 4,368 B — game-patterns 992 B 포함)
- 세션 시작 안내(인덱스 · 위키 · gq 가 다 있는 가장 긴 경우) ≤ 1,800 B
- bootstrap 이 쓰는 CLAUDE.local.md 의 스킬 라우팅 절 ≤ 300 B (라우팅 본문은 세션 시작 안내 한 곳에만)
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "skills" / "game-bootstrap" / "harness"))
import context_budget  # noqa: E402
import game_context  # noqa: E402


class Budget(unittest.TestCase):
    def test_skill_descriptions(self):
        total = sum(len(context_budget.description(p).encode("utf-8")) for p in (REPO / "skills").glob("game-*/SKILL.md"))
        self.assertLessEqual(total, 4000, f"하네스 스킬 description 합 {total} B")

    def test_session_start_longest_case(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            root, home = t / "Game", t / "h"
            idx = root / "Saved" / "ClaudeIndex"
            idx.mkdir(parents=True)
            (idx / "symbols.json").write_text("{}", encoding="utf-8")
            (idx / "clangd.sqlite").write_bytes(b"x")
            (home / ".jokate-wiki" / "Game").mkdir(parents=True)
            (home / ".jokate-wiki" / "Game" / "index.md").write_text("# w", encoding="utf-8")
            text = "\n".join(game_context.routing_lines(root, "Unreal Engine 5.7", home=home))
        self.assertLessEqual(len(text.encode("utf-8")), 1800, f"세션 시작 안내 {len(text.encode('utf-8'))} B")

    def test_template_routing_section_is_a_pointer(self):
        tpl = (REPO / "skills" / "game-bootstrap" / "references" / "claude-md-template.md").read_text(encoding="utf-8")
        m = re.search(r"## 스킬 라우팅 \[필수\]\n(.*?)\n\n", tpl, re.S)
        self.assertIsNotNone(m)
        self.assertLessEqual(len(m.group(1).encode("utf-8")), 300)
        self.assertNotIn("game-onboard", m.group(1))  # 스킬 이름별 라우팅은 세션 시작 안내에만

    def test_measure_counts_harness_share(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / ".claude" / "skills" / "game-x").mkdir(parents=True)
            (home / ".claude" / "skills" / "game-x" / "SKILL.md").write_text("---\nname: game-x\ndescription: 가나다\n---\n본문",
                                                                            encoding="utf-8")
            (home / ".claude" / "skills" / "other").mkdir(parents=True)
            (home / ".claude" / "skills" / "other" / "SKILL.md").write_text("---\ndescription: abc\n---\n", encoding="utf-8")
            (home / ".claude" / "CLAUDE.md").write_text(
                "앞\n<!-- game-harness:begin (관리) -->\n규칙\n<!-- game-harness:end -->\n", encoding="utf-8")
            res = context_budget.measure(None, home)
            rows = {name: (owner, n) for owner, name, n in res["rows"]}
            self.assertEqual(rows["스킬 설명 game-x"], ("하네스", 9))
            self.assertEqual(rows["스킬 설명 other"], ("그 밖", 3))
            self.assertGreater(rows["전역 CLAUDE.md 하네스 절"][1], 0)
            self.assertEqual(json.loads(json.dumps(res))["harness"], res["harness"])


if __name__ == "__main__":
    unittest.main()
