"""render.py — 선택지 · 그림 먼저, 나머지 근거는 접는다 (2026-10-20 사용자: HTML 이 길고 난잡하다)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("render", HERE.parent / "scripts" / "render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

ANSWER = """# 입력 버퍼

## 요청 축
언제: 공격 중

## 기존 확장 지점
- A

## 신호
| 파일 | 수 |
|---|---|
| X | 3 |

## 선택지
### A. 플래그 — 다음 요청 때 3곳
### B. 상태 — 다음 요청 때 1곳

## 그림
```mermaid
graph LR
  A-->B
```
"""


class SummaryFirstTest(unittest.TestCase):
    def test_options_and_diagram_first_rest_folded(self):
        out = render.summary_first(ANSWER)
        self.assertLess(out.index("## 선택지"), out.index("## 그림"))
        self.assertLess(out.index("## 그림"), out.index("<details>"))
        self.assertIn("근거 — 요청 축 · 기존 확장 지점 · 신호", out)
        self.assertTrue(out.startswith("# 입력 버퍼"))
        for part in ("언제: 공격 중", "| X | 3 |", "graph LR"):
            self.assertIn(part, out)  # 아무것도 버리지 않는다

    def test_other_text_unchanged(self):
        md = "# 메모\n\n## 아무 절\n내용\n"
        self.assertEqual(render.summary_first(md), md)

    def test_full_flag_keeps_order(self):
        with tempfile.TemporaryDirectory() as td:
            p = render.render(ANSWER, Path(td) / "a.html", "t", full=True)
            html = p.read_text(encoding="utf-8")
        self.assertNotIn("근거 —", html)


if __name__ == "__main__":
    unittest.main()
