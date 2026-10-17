"""setup.py — 위키 하네스(jokate-wiki)를 찾으면 같이 세팅한다."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("harness_setup", ROOT / "setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def fake_wiki(base: Path) -> Path:
    (base / "scripts").mkdir(parents=True)
    (base / "install.py").write_text("", encoding="utf-8")
    (base / "scripts" / "wq.py").write_text("", encoding="utf-8")
    return base


class FindWikiTest(unittest.TestCase):
    def test_env_first_then_sibling_then_inside(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "game-harness"
            repo.mkdir()
            self.assertIsNone(setup.find_wiki(env={}, repo=repo))
            inside = fake_wiki(repo / "jokate-wiki")
            self.assertEqual(setup.find_wiki(env={}, repo=repo), inside.resolve())
            sib = fake_wiki(td / "jokate-wiki")
            self.assertEqual(setup.find_wiki(env={}, repo=repo), sib.resolve())
            other = fake_wiki(td / "elsewhere")
            self.assertEqual(setup.find_wiki(env={"JOKATE_WIKI_DIR": str(other)}, repo=repo), other.resolve())

    def test_needs_both_files(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "game-harness"
            repo.mkdir()
            (Path(td) / "jokate-wiki").mkdir()
            (Path(td) / "jokate-wiki" / "install.py").write_text("", encoding="utf-8")
            self.assertIsNone(setup.find_wiki(env={}, repo=repo))


if __name__ == "__main__":
    unittest.main()


class ClangdOptionTest(unittest.TestCase):
    def test_existing_index_detected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            self.assertIsNone(setup.clangd_index(p))
            db = p / "Saved" / "ClaudeIndex" / "clangd.sqlite"
            db.parent.mkdir(parents=True)
            db.write_text("", encoding="utf-8")
            self.assertEqual(setup.clangd_index(p), db)

    def test_background_build_is_project_only_with_log(self):
        calls = []

        class FakePopen:
            def __init__(self, argv, **kw):
                calls.append((argv, kw))

        with tempfile.TemporaryDirectory() as td:
            orig = setup.subprocess.Popen
            setup.subprocess.Popen = FakePopen
            try:
                log = setup.start_clangd_bg(Path(td) / "MyGame", home=td)
            finally:
                setup.subprocess.Popen = orig
            self.assertTrue(log.is_file())
        argv, kw = calls[0]
        self.assertTrue(argv[1].endswith("index_all.py"))
        self.assertIn("--project-only", argv)
        self.assertIn("MyGame", log.name)

    def test_no_question_without_terminal(self):
        orig = setup.sys.stdin
        try:
            setup.sys.stdin = None
            self.assertFalse(setup.ask_yes("?"))
        finally:
            setup.sys.stdin = orig
