"""install.py — agy(Antigravity CLI) 플러그인. 규칙과 스킬만 두고, 릴레이 가드가 쓰는 계정 파일은 건드리지 않는다."""
import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import install  # noqa: E402
import uninstall  # noqa: E402


def ns(**kw):
    d = dict(link=os.name == "nt", force=False, dry_run=False)
    d.update(kw)
    return argparse.Namespace(**d)


def run(fn, *args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


class AgyPluginTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.home = Path(self.td.name) / "acct"
        cfg = self.home / ".gemini" / "config"
        cfg.mkdir(parents=True)
        self.guard = {n: cfg / n for n in install.AGY_FORBIDDEN}  # 릴레이가 쓰는 계정 파일
        for p in self.guard.values():
            p.write_text('{"relay": true}', encoding="utf-8")
        self.stamp = {n: p.stat().st_mtime_ns for n, p in self.guard.items()}
        self.root = install.agy_plugin_dir(self.home)

    def tearDown(self):
        if self.root.exists():
            install.drop_path(self.root)
        self.td.cleanup()

    def assert_guard_untouched(self):
        for n, p in self.guard.items():
            self.assertEqual(p.read_text(encoding="utf-8"), '{"relay": true}')
            self.assertEqual(p.stat().st_mtime_ns, self.stamp[n])

    def test_rules_and_four_skills_only(self):
        run(install.install_agy, ns(), [self.home])
        self.assertTrue(install.agy_ours(self.root))
        rules = (self.root / "rules" / "AGENTS.md").read_text(encoding="utf-8")
        common = (ROOT / "rules" / "common.md").read_text(encoding="utf-8").splitlines()
        self.assertIn(common[1], rules)
        self.assertIn("## agy 에서 쓸 때", rules)
        self.assertIn(str(ROOT / "docs" / "READING.md"), rules)
        self.assertNotIn("하네스 docs/READING.md", rules)
        self.assertLess(len(rules.encode("utf-8")), 24000)  # agy 의 규칙 파일 한도
        self.assertEqual(sorted(p.name for p in (self.root / "skills").iterdir()), sorted(install.AGY_SKILLS))
        for name in install.AGY_SKILLS:  # agy 는 정션을 읽지 않아 복사본이어야 한다
            self.assertTrue((self.root / "skills" / name / "SKILL.md").is_file())
            self.assertFalse(install.is_link(self.root / "skills" / name))
            self.assertFalse((self.root / "skills" / name / "tests").exists())
        for name in install.AGY_FORBIDDEN:  # agy 는 플러그인 맨 위의 hooks.json 만 읽는다
            self.assertFalse((self.root / name).exists())
        self.assert_guard_untouched()

    def test_second_run_changes_nothing(self):
        run(install.install_agy, ns(), [self.home])
        out = run(install.install_agy, ns(), [self.home])
        self.assertFalse([ln for ln in out.splitlines() if ln.strip().startswith(("+", "x"))], out)

    def test_changed_copy_is_replaced(self):
        run(install.install_agy, ns(), [self.home])
        skill = self.root / "skills" / "game-testing" / "SKILL.md"
        skill.write_text("stale", encoding="utf-8")
        out = run(install.install_agy, ns(), [self.home])
        self.assertIn("+ skills/game-testing", out)
        self.assertEqual(skill.read_bytes(), (ROOT / "skills" / "game-testing" / "SKILL.md").read_bytes())

    @unittest.skipUnless(os.name == "nt", "정션은 Windows")
    def test_old_junction_is_replaced_by_copy(self):
        dst = self.root / "skills" / "game-testing"
        dst.parent.mkdir(parents=True)
        install.link(ROOT / "skills" / "game-testing", dst)
        (self.root / "plugin.json").write_text('{"name": "game-harness"}', encoding="utf-8")
        run(install.install_agy, ns(), [self.home])
        self.assertFalse(install.is_link(dst))
        self.assertTrue((ROOT / "skills" / "game-testing" / "SKILL.md").is_file())

    def test_dry_run_writes_nothing(self):
        out = run(install.install_agy, ns(dry_run=True), [self.home])
        self.assertFalse(self.root.exists())
        self.assertIn("+ rules/AGENTS.md", out)

    def test_foreign_plugin_with_same_name_is_left(self):
        self.root.mkdir(parents=True)
        (self.root / "plugin.json").write_text('{"name": "someone-else"}', encoding="utf-8")
        out = run(install.install_agy, ns(), [self.home])
        self.assertIn("건너뜀", out)
        self.assertFalse((self.root / "rules").exists())

    def test_forbidden_file_in_plugin_is_moved_out(self):
        run(install.install_agy, ns(), [self.home])
        (self.root / "hooks.json").write_text("{}", encoding="utf-8")
        run(install.install_agy, ns(), [self.home])
        self.assertFalse((self.root / "hooks.json").exists())
        self.assertTrue((self.root / "hooks.json.removed").exists())

    def test_skill_taken_off_the_list_is_removed(self):
        run(install.install_agy, ns(), [self.home])
        extra = self.root / "skills" / "game-mcp"
        extra.mkdir()
        (extra / "SKILL.md").write_text("x", encoding="utf-8")
        run(install.install_agy, ns(), [self.home])
        self.assertFalse(extra.exists())

    def test_no_home_is_skipped(self):
        self.assertIn("agy 홈 없음", run(install.install_agy, ns(), []))

    def test_homes_are_user_home_and_accounts_with_gemini(self):
        fake = Path(self.td.name) / "user"
        (fake / ".gemini").mkdir(parents=True)
        (fake / ".agy-accounts" / "1" / ".gemini").mkdir(parents=True)
        (fake / ".agy-accounts" / "2").mkdir(parents=True)  # 로그인 전 계정: .gemini 없음
        with mock.patch.object(install.Path, "home", return_value=fake):
            self.assertEqual(install.agy_homes(), [fake, fake / ".agy-accounts" / "1"])
        self.assertEqual(install.agy_homes(["x"]), [Path("x")])

    def test_uninstall_unlinks_without_touching_repo_or_guard(self):
        run(install.install_agy, ns(), [self.home])
        run(uninstall.remove_agy, False, [self.home])
        self.assertFalse(self.root.exists())
        for name in install.AGY_SKILLS:
            self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file())
        self.assert_guard_untouched()

    def test_uninstall_leaves_foreign_plugin(self):
        self.root.mkdir(parents=True)
        (self.root / "plugin.json").write_text('{"name": "someone-else"}', encoding="utf-8")
        run(uninstall.remove_agy, False, [self.home])
        self.assertTrue((self.root / "plugin.json").exists())


if __name__ == "__main__":
    unittest.main()
