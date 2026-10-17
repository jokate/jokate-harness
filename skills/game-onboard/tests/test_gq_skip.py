"""gq index — Unity·빌드 캐시 폴더 이름(Library 등)은 프로젝트 루트 바로 아래일 때만 뺀다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GQ = Path(__file__).resolve().parent.parent / "scripts" / "gq.py"

UCLASS = "UCLASS()\nclass M_API {name} : public UObject\n{{\n\tGENERATED_BODY()\n}};\n"


class SkipDirsTest(unittest.TestCase):
    def test_library_inside_source_is_indexed(self):
        # 2026-10-17 MNYS: Source/MNYS/Public/Library 가 통째로 빠져 UYSBlueprintFunctionLibrary 가 인덱스에 없었다
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "P"
            files = {
                "Source/M/Public/Library/MyLib.h": "UMyLib",
                "Source/M/Public/Build/BuildCfg.h": "UBuildCfg",
                "Source/M/Public/Core/Core.h": "UCore",
                "Library/Cache/Cached.h": "UCached",
                "Source/M/Intermediate/Gen.h": "UGen",
            }
            for rel, name in files.items():
                f = p / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(UCLASS.format(name=name), encoding="utf-8")
            (p / "P.uproject").write_text(json.dumps({"Modules": [{"Name": "M", "Type": "Runtime"}]}), encoding="utf-8")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, str(GQ), "index"], cwd=str(p), capture_output=True, text=True,
                               encoding="utf-8", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            rows = json.loads((p / "Saved" / "ClaudeIndex" / "symbols.json").read_text(encoding="utf-8"))
            names = {row[0] for row in rows}
        self.assertIn("UMyLib", names)
        self.assertIn("UBuildCfg", names)
        self.assertIn("UCore", names)
        self.assertNotIn("UCached", names)  # 루트의 Library 는 캐시다
        self.assertNotIn("UGen", names)     # Intermediate 는 어디서든 뺀다


if __name__ == "__main__":
    unittest.main()
