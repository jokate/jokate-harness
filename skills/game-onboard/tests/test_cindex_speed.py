#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cindex_speed.py 시험 (표준 라이브러리 unittest). clangd 없이 돈다.

  python skills/game-onboard/tests/test_cindex_speed.py

- Windows 명령줄 나누기: UE 의 compile_commands 모양(`cl.exe @"…rsp"`)에서 따옴표가 인자에 남지 않는가.
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import cindex_speed as sp  # noqa: E402


class SplitWindows(unittest.TestCase):
    def test_ue_command(self):
        # UE 5.7 GenerateClangDatabase (-Compiler=Default) 가 쓰는 모양 그대로
        cmd = ('"C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe" '
               '@"C:/Users/me/My Game/Intermediate/Build/Win64/x64/UnrealEditor/Development/G/A.cpp.obj.rsp" ')
        self.assertEqual(sp.split_windows(cmd), [
            "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe",
            "@C:/Users/me/My Game/Intermediate/Build/Win64/x64/UnrealEditor/Development/G/A.cpp.obj.rsp"])

    def test_quotes_inside_token(self):
        self.assertEqual(sp.split_windows('cl.exe /FI"C:/a b/Definitions.h" /Fo"C:/o/A.obj" /DX=1 A.cpp'),
                         ["cl.exe", "/FIC:/a b/Definitions.h", "/FoC:/o/A.obj", "/DX=1", "A.cpp"])

    def test_backslashes(self):
        # 따옴표 앞이 아니면 역슬래시는 글자, 따옴표 앞에서는 둘이 하나 · 홀수면 따옴표가 글자
        self.assertEqual(sp.split_windows(r'cl.exe C:\src\A.cpp "C:\a b\\" /DS=\"x\" ""'),
                         ["cl.exe", r"C:\src\A.cpp", "C:\\a b\\", '/DS="x"', ""])

    def test_whitespace(self):
        self.assertEqual(sp.split_windows("  a\t b\r\n c  "), ["a", "b", "c"])
        self.assertEqual(sp.split_windows(""), [])


if __name__ == "__main__":
    unittest.main()
