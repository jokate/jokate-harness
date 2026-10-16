#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""engine_cdb.py 시험 (표준 라이브러리 unittest). UBT · clangd 없이 가짜 엔진 폴더로 돈다.

  python skills/game-onboard/tests/test_engine_cdb.py

- 모듈 rsp + 모듈 폴더의 .cpp 로 항목을 합성하는가. 다른 플랫폼 폴더 · 안에 든 다른 모듈 · 엔진 밖 모듈을 빼는가.
- .generated.h 마다 빈 .gen.cpp 를 만드는가 (런처 설치 엔진에는 .gen.cpp 가 없다).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import engine_cdb  # noqa: E402


def touch(p, text=""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class Synthesize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.eng, self.vs = t / "Engine", t / "Proj" / ".vscode"
        core = self.eng / "Source" / "Runtime" / "Core"
        touch(core / "Core.Build.cs")
        touch(core / "Private" / "A.cpp")
        touch(core / "Private" / "Windows" / "W.cpp")
        touch(core / "Private" / "Linux" / "L.cpp")           # 다른 플랫폼
        touch(core / "Private" / "Inner" / "Inner.Build.cs")  # 안에 든 다른 모듈
        touch(core / "Private" / "Inner" / "I.cpp")
        gas = self.eng / "Plugins" / "Runtime" / "GAS" / "Source" / "GAS"
        touch(gas / "GAS.Build.cs")
        touch(gas / "Private" / "G.cpp")
        touch(self.eng / "Plugins" / "Runtime" / "GAS" / "Intermediate" / "Build" / "Win64" / "UnrealEditor" / "Inc" / "GAS" / "UHT"
              / "G.generated.h")
        touch(self.eng / "Intermediate" / "Build" / "Win64" / "UnrealEditor" / "Inc" / "Core" / "UHT" / "A.generated.h")
        touch(self.vs / "compileCommands_Proj.json", json.dumps([{"file": "x.cpp", "directory": ".", "arguments": ["cl.exe", "@x.rsp"]}]))
        for name in ("Core.1.rsp", "GAS.2.rsp", "Inner.3.rsp", "MyGame.4.rsp"):
            touch(self.vs / "compileCommands_Proj" / name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_entries(self):
        out = Path(self.tmp.name) / "out"
        stubs = out / "stubs"
        self.assertEqual(engine_cdb.gen_stubs(self.eng, stubs), 2)
        self.assertEqual(engine_cdb.gen_stubs(self.eng, stubs), 0)  # 다시 돌려도 더 만들지 않는다
        self.assertEqual(sorted(p.name for p in stubs.iterdir()), ["A.gen.cpp", "G.gen.cpp"])
        mods, tus, missing = engine_cdb.synthesize(self.vs, self.eng, out, stubs=stubs)
        data = json.loads((out / "compile_commands.json").read_text(encoding="utf-8"))
        self.assertEqual((mods, tus, missing), (3, 4, 1))  # MyGame 은 엔진 밖
        self.assertEqual(sorted(Path(e["file"]).name for e in data), ["A.cpp", "G.cpp", "I.cpp", "W.cpp"])
        a = next(e for e in data if e["file"].endswith("A.cpp"))["arguments"]
        self.assertEqual(a[0], "cl.exe")
        self.assertTrue(a[1].startswith("@") and a[1].endswith("Core.1.rsp"))
        self.assertEqual(a[2:], ["/std:c++20", f"/I{stubs}", a[-1]])

    def test_only(self):
        out = Path(self.tmp.name) / "out2"
        self.assertEqual(engine_cdb.synthesize(self.vs, self.eng, out, only={"GAS"}), (1, 1, 0))


if __name__ == "__main__":
    unittest.main()
