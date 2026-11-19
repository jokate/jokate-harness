#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence.py precedent — 같은 종류를 누가 어떻게 넣어 왔나. git 은 임시 저장소로, svn 은 로그 XML 로 본다."""
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import evidence  # noqa: E402


def git(root, *args, author="lee"):
    subprocess.run(["git", "-c", f"user.name={author}", "-c", f"user.email={author}@x.test", "-c", "commit.gpgsign=false",
                    *args], cwd=str(root), check=True, capture_output=True)


def commit(root, author, files, msg):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(root, "add", "-A", author=author)
    git(root, "commit", "-q", "-m", msg, author=author)


def run_precedent(root, query, me):
    evidence.UNIT_FILES.clear()
    old = sys.argv
    sys.argv = ["evidence.py", "precedent", query, "--path", str(root), "--me", me]
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            evidence.main()
    finally:
        sys.argv = old
    return out.getvalue()


class Precedent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        commit(self.root, "lee", {"Src/Registry.cpp": "r0", "Src/Tags.h": "t0"}, "base")
        commit(self.root, "lee", {"Src/Effect/Effect_Stun.h": "a", "Src/Effect/Effect_Stun.cpp": "a",
                                  "Src/Registry.cpp": "r1", "Src/Tags.h": "t1"}, "stun")
        commit(self.root, "park", {"Src/Effect/Effect_Freeze.h": "b", "Src/Effect/Effect_Freeze.cpp": "b",
                                   "Src/Registry.cpp": "r2"}, "freeze")
        commit(self.root, "kim", {"Src/Effect/Effect_Knock.h": "c", "Src/Effect/Effect_Knock.cpp": "c",
                                  "Src/Character.cpp": "x"}, "knock")

    def tearDown(self):
        self.tmp.cleanup()

    def test_other_peoples_precedents_set_the_shape(self):
        out = run_precedent(self.root, "Effect_", "kim")
        self.assertIn("다른 사람 2 · 나 1", out)
        self.assertIn("kim (나)", out)
        self.assertIn("다른 사람 선례 2건 기준", out)
        shape = out.split("넣을 때 같이 바뀌어 온 곳")[1]
        self.assertIn("| 2 | 100% | `Src/Registry.{h,cpp}` |", shape)      # 두 사람 다 등록부를 고쳤다
        self.assertNotIn("Character", shape)                                # 내 선례의 꼴은 기준에 넣지 않는다
        self.assertIn("벗어나는 이유", out)

    def test_only_my_precedents_are_not_called_team_shape(self):
        out = run_precedent(self.root, "Effect_Knock", "kim")
        self.assertIn("다른 사람 0 · 나 1", out)
        self.assertIn("팀의 꼴이라고 쓰지 않는다", out)

    def test_nothing_added_in_window_says_so(self):
        out = run_precedent(self.root, "Registry", "kim")
        self.assertIn("다른 사람 1", out)                                   # base 커밋이 넣었다
        out = run_precedent(self.root, "NoSuch", "kim")
        self.assertIn("새로 들어간 것이 없다", out)

    def test_later_edits_are_not_precedents(self):
        commit(self.root, "choi", {"Src/Effect/Effect_Stun.cpp": "a2"}, "tune stun")
        out = run_precedent(self.root, "Effect_Stun", "kim")
        self.assertIn("새로 들어간 커밋 1건", out)
        self.assertNotIn("choi", out.split("넣은 사람")[1])


SVN_LOG = """<?xml version="1.0" encoding="UTF-8"?>
<log>
<logentry revision="12"><author>park</author><date>2026-03-02T01:00:00.000000Z</date>
<paths><path kind="file" action="A">/trunk/Src/Effect/Effect_Freeze.cpp</path>
<path kind="file" action="M">/trunk/Src/Registry.cpp</path>
<path kind="dir" action="A">/trunk/Src/Effect</path>
<path kind="file" action="A">/branches/x/Other.cpp</path></paths><msg>freeze</msg></logentry>
</log>"""


class SvnLog(unittest.TestCase):
    def test_added_files_are_marked(self):
        sets = evidence.parse_svn_log(SVN_LOG, "/trunk")
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]["author"], "park")
        self.assertEqual(set(sets[0]["files"]), {"Src/Effect/Effect_Freeze.cpp", "Src/Registry.cpp"})
        self.assertEqual(sets[0]["added"], {"Src/Effect/Effect_Freeze.cpp"})

    def test_svn_prefix_with_korean_space_or_repo_root(self):
        log = SVN_LOG.replace("/trunk/", "/trunk/내 게임/")
        sets = evidence.parse_svn_log(log, "/trunk/%EB%82%B4%20%EA%B2%8C%EC%9E%84")
        self.assertEqual(set(sets[0]["files"]), {"Src/Effect/Effect_Freeze.cpp", "Src/Registry.cpp"})
        sets = evidence.parse_svn_log(SVN_LOG, "/")
        self.assertEqual(set(sets[0]["files"]), {"trunk/Src/Effect/Effect_Freeze.cpp", "trunk/Src/Registry.cpp", "branches/x/Other.cpp"})


if __name__ == "__main__":
    unittest.main()
