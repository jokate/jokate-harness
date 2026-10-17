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
