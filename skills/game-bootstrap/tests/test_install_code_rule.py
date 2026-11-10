"""install.py — C++ · C# 코드 규칙은 전역 CLAUDE.md 가 아니라 파일을 다룰 때만 실리는 규칙 파일로 둔다."""
import argparse
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import install  # noqa: E402
import uninstall  # noqa: E402


def quiet(fn, *args):
    with redirect_stdout(io.StringIO()) as buf:
        fn(*args)
    return buf.getvalue()


class CodeRule(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.claude = Path(self.td.name) / ".claude"
        self.saved = (install.CLAUDE, uninstall.CLAUDE)
        install.CLAUDE = uninstall.CLAUDE = self.claude
        self.addCleanup(self.restore)
        self.dst = self.claude / "rules" / install.CODE_RULE

    def restore(self):
        install.CLAUDE, uninstall.CLAUDE = self.saved

    def ns(self, **kw):
        return argparse.Namespace(**{"dry_run": False, "force": False, **kw})

    def test_source_is_path_scoped_and_global_block_only_points(self):
        code = (ROOT / "rules" / "code.md").read_text(encoding="utf-8")
        self.assertTrue(code.startswith("---\npaths:\n"))
        for ext in ("cpp", "h", "cs"):
            self.assertIn(f'"**/*.{ext}"', code)
        common = (ROOT / "rules" / "common.md").read_text(encoding="utf-8")
        self.assertNotIn("IsValid(x) == false", common)  # 본문은 code.md 한 곳에만
        self.assertNotIn("```cpp", common)
        self.assertIn("새 파일을 쓰기 전에는", common)      # 새 파일은 규칙이 실리기 전에 쓰일 수 있다

    def test_install_writes_updates_and_leaves_foreign_file(self):
        quiet(install.install_code_rule, self.ns())
        self.assertEqual(self.dst.read_text(encoding="utf-8"), (ROOT / "rules" / "code.md").read_text(encoding="utf-8"))
        self.assertIn("= rules/", quiet(install.install_code_rule, self.ns()))
        self.dst.write_text("내가 쓴 규칙", encoding="utf-8")
        self.assertIn("건너뜀", quiet(install.install_code_rule, self.ns()))
        self.assertEqual(self.dst.read_text(encoding="utf-8"), "내가 쓴 규칙")

    def test_dry_run_writes_nothing(self):
        quiet(install.install_code_rule, self.ns(dry_run=True))
        self.assertFalse(self.dst.exists())

    def test_uninstall_removes_only_ours(self):
        quiet(install.install_code_rule, self.ns())
        quiet(uninstall.remove_code_rule, False)
        self.assertFalse(self.dst.exists())
        self.dst.write_text("내가 쓴 규칙", encoding="utf-8")
        quiet(uninstall.remove_code_rule, False)
        self.assertTrue(self.dst.exists())

    def test_agy_gets_the_body_always(self):
        text = install.agy_rules_text()
        self.assertIn("IsValid(x) == false", text)
        self.assertEqual(text.count("## 코드 (C++ · C#)"), 1)
        self.assertNotIn("paths:", text)
        self.assertNotIn("따로 실린다", text)


if __name__ == "__main__":
    unittest.main()
