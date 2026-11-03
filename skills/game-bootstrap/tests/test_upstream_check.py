#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""빌려 온 바깥 스킬 원본 추적 (표준 라이브러리 unittest): 플러그인 설치본과 사본을 비교하고, --accept 로 올린다.

  python skills/game-bootstrap/tests/test_upstream_check.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
import upstream_check  # noqa: E402

PLUGIN = "p@market"


class Check(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        t = Path(self._td.name)
        self.repo, self.home, self.cache = t / "repo", t / "home", t / "cache" / "1.1"
        snap = self.repo / "docs" / "third_party" / "p"
        for root, text in ((snap, "a\nb\n"), (self.cache, "a\r\nb\r\n")):  # 설치본은 CRLF — 차이로 세지 않는다
            (root / "skills" / "x").mkdir(parents=True)
            (root / "skills" / "x" / "SKILL.md").write_bytes(text.encode("utf-8"))
        self.spec = self.repo / "docs" / "third_party" / "upstream.json"
        self.spec.write_text(json.dumps({"sources": [{
            "name": "p", "plugin": PLUGIN, "version": "1.0", "commit": "old", "snapshot": "docs/third_party/p",
            "borrowed": [{"upstream": "skills/x/SKILL.md", "into": ["skills/game-testing/SKILL.md"], "what": "w"}]}]}),
            encoding="utf-8")

    def install(self, sha="new"):
        f = self.home / ".claude" / "plugins" / "installed_plugins.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"version": 2, "plugins": {PLUGIN: [
            {"scope": "user", "installPath": str(self.cache), "version": "1.1", "gitCommitSha": sha}]}}), encoding="utf-8")

    def rows(self):
        return upstream_check.check(self.spec, home=self.home, repo=self.repo)

    def test_absent_plugin_is_not_an_error(self):
        r = self.rows()[0]
        self.assertEqual(r["status"], "absent")
        self.assertIn("claude plugin install p@market", upstream_check.summary([r])[0])

    def test_same_ignores_line_endings(self):
        self.install()
        r = self.rows()[0]
        self.assertEqual(r["status"], "same")
        self.assertIn("그대로", upstream_check.summary([r])[0])

    def test_changed_lists_where_to_review_then_accept(self):
        self.install()
        (self.cache / "skills" / "x" / "SKILL.md").write_text("a\nb\nc\n", encoding="utf-8")
        r = self.rows()[0]
        self.assertEqual(r["status"], "changed")
        self.assertEqual(r["changed"], [("skills/x/SKILL.md", ["skills/game-testing/SKILL.md"], "바뀜")])
        self.assertIn("1개 바뀜", upstream_check.summary([r])[0])
        self.assertEqual(upstream_check.accept([r], self.spec, self.repo), ["p"])
        got = json.loads(self.spec.read_text(encoding="utf-8"))["sources"][0]
        self.assertEqual((got["version"], got["commit"]), ("1.1", "new"))
        self.assertEqual(self.rows()[0]["status"], "same")

    def test_removed_upstream_keeps_snapshot(self):
        self.install()
        (self.cache / "skills" / "x" / "SKILL.md").unlink()
        r = self.rows()[0]
        self.assertEqual(r["changed"][0][2], "원본에서 사라짐")
        upstream_check.accept([r], self.spec, self.repo)
        self.assertTrue((self.repo / "docs" / "third_party" / "p" / "skills" / "x" / "SKILL.md").is_file())


class GitSource(unittest.TestCase):
    """깔지 않는 원본(kind: git): --remote 일 때만 받아 비교, 네트워크가 안 되면 '확인 못 함'."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.repo = Path(self._td.name) / "repo"
        snap = self.repo / "docs" / "third_party" / "g" / "core"
        snap.mkdir(parents=True)
        (snap / "a.md").write_text("a\nb\n", encoding="utf-8")
        self.spec = self.repo / "docs" / "third_party" / "upstream.json"
        self.spec.write_text(json.dumps({"sources": [{
            "name": "g", "kind": "git", "repo": "https://github.com/o/g", "branch": "main", "version": "main@old",
            "commit": "old0000", "snapshot": "docs/third_party/g",
            "borrowed": [{"upstream": "core/a.md", "into": ["skills/game-testing/SKILL.md"], "what": "w"}]}]}),
            encoding="utf-8")
        self.remote = {"core/a.md": b"a\r\nb\r\n"}
        self.calls = []

    def fetch(self, repo, branch, path=None):
        self.calls.append(path)
        return "abcdef1234567" if path is None else self.remote.get(path)

    def rows(self, remote=True, fetch=None):
        return upstream_check.check(self.spec, home=self.repo, repo=self.repo, remote=remote, fetch=fetch or self.fetch)

    def test_offline_by_default_no_network(self):
        r = self.rows(remote=False)[0]
        self.assertEqual((r["status"], self.calls), ("offline", []))
        self.assertIn("--remote", upstream_check.summary([r])[0])

    def test_same_ignores_line_endings(self):
        r = self.rows()[0]
        self.assertEqual(r["status"], "same")
        self.assertIn("그대로", upstream_check.summary([r])[0])

    def test_unreachable_is_not_same(self):
        def down(*_a, **_k):
            raise OSError("timed out")
        r = self.rows(fetch=down)[0]
        self.assertEqual(r["status"], "unreachable")
        line = upstream_check.summary([r])[0]
        self.assertIn("확인 못 함", line)
        self.assertNotIn("그대로 (", line)

    def test_changed_then_accept(self):
        self.remote["core/a.md"] = b"a\nb\nc\n"
        r = self.rows()[0]
        self.assertEqual(r["changed"], [("core/a.md", ["skills/game-testing/SKILL.md"], "바뀜")])
        self.assertIn("--remote", upstream_check.summary([r])[0])
        self.assertEqual(upstream_check.accept([r], self.spec, self.repo), ["g"])
        got = json.loads(self.spec.read_text(encoding="utf-8"))["sources"][0]
        self.assertEqual((got["version"], got["commit"]), ("main@abcdef1", "abcdef1234567"))
        self.assertEqual(self.rows()[0]["status"], "same")

    def test_removed_upstream(self):
        del self.remote["core/a.md"]
        self.assertEqual(self.rows()[0]["changed"][0][2], "원본에서 사라짐")


class RepoSpec(unittest.TestCase):
    """저장소의 대응표: 사본 · 옮긴 곳 · 라이선스가 실제로 있고, 옮긴 참고 문서는 출처를 밝힌다."""

    def test_files_exist_and_notice(self):
        spec = json.loads(upstream_check.SPEC.read_text(encoding="utf-8"))
        for s in spec["sources"]:
            self.assertTrue((REPO / s["license"]).is_file(), s["license"])
            for b in s["borrowed"]:
                self.assertTrue((REPO / s["snapshot"] / b["upstream"]).is_file(), b["upstream"])
                for into in b["into"]:
                    p = REPO / into
                    self.assertTrue(p.is_file(), into)
                    if "/references/" in into:
                        text = p.read_text(encoding="utf-8")
                        self.assertIn("MIT", text, into)
                        self.assertIn(s["name"], text, into)  # 어느 원본에서 왔는지
                        self.assertIn("docs/UPSTREAM.md", text, into)


if __name__ == "__main__":
    unittest.main()
