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


DOC = """# 전투 구조

전투는 어빌리티와 피격 두 갈래다.
피격 판정은 HitComponent 가 맡는다.

## 모듈
| a | b |
|---|---|
| 1 | 2 |

## 현재 구조
```mermaid
graph LR
  A-->B
```

## 피격 흐름
```mermaid
sequenceDiagram
  A->>B: hit
```
뒤 설명.
"""


class DiagramFirstTest(unittest.TestCase):
    def test_title_summary_figures_then_folded(self):
        out = render.diagram_first(DOC)
        self.assertTrue(out.startswith("# 전투 구조\n\n- 전투는 어빌리티와 피격 두 갈래다."))
        self.assertLess(out.index("### 현재 구조"), out.index("### 피격 흐름"))
        self.assertLess(out.index("### 피격 흐름"), out.index("<details>"))
        head, folded = out.split("<details>")
        self.assertNotIn("| 1 | 2 |", head)  # 표 · 긴 설명은 접힌 쪽으로
        self.assertNotIn("```mermaid", folded)  # 그림은 위에만 한 번
        for part in ("| 1 | 2 |", "뒤 설명.", "*(위 그림 2)*"):
            self.assertIn(part, folded)
        self.assertEqual(out.count("# 전투 구조"), 1)

    def test_summary_capped(self):
        md = "\n".join(f"줄 {i}" for i in range(10)) + "\n```mermaid\ngraph LR\n  A-->B\n```\n"
        head = render.diagram_first(md).split("```mermaid")[0]
        self.assertEqual(head.count("- 줄"), render.SUMMARY_LINES)

    def test_no_diagram_unchanged(self):
        md = "# 메모\n\n글\n"
        self.assertIs(render.readable(md), md)

    def test_readable_prefers_options_layout(self):
        self.assertIn("근거 —", render.readable(ANSWER))
        self.assertIn("전체 내용", render.readable(DOC))

    def test_page_has_click_zoom(self):
        with tempfile.TemporaryDirectory() as td:
            html = render.render(DOC, Path(td) / "d.html", "t").read_text(encoding="utf-8")
        self.assertIn("classList.toggle('zoom')", html)


NUMBERED = """# 조건 구조

## 1. 결론
- 짧은 결론.

## 2. 요청 축
| 축 | 내용 |

## 3. 현재 구조
```mermaid
graph LR
  A-->B
```

## 6. 선택지 — 다음 요청 기준
| 선택지 | 곳 |
|---|---|
| A | 4 |

## 7. C 설계 노트
긴 설계.

## 8. 사용자 결정
1. C1 인가 C2 인가
"""


class ReadabilityTest(unittest.TestCase):
    def test_numbered_headings_order_and_fold(self):
        out = render.summary_first(NUMBERED)
        head, folded = out.split("<details><summary>근거")
        order = [head.index(h) for h in ("## 1. 결론", "## 6. 선택지", "## 3. 현재 구조", "## 8. 사용자 결정")]
        self.assertEqual(order, sorted(order))
        self.assertIn("요청 축 · C 설계 노트", folded)
        self.assertNotIn("긴 설계.", head)

    def test_long_line_keeps_first_sentence(self):
        line = "- **컴포넌트가 맞다.** 조건 슬롯과 캐시는 상태다. " + "그래서 인터페이스로는 중복이 남는다 " * 5
        out = render._fold_long(line)
        self.assertTrue(out.startswith("- **컴포넌트가 맞다.** 조건 슬롯과 캐시는 상태다."))
        self.assertIn('<details class="more"><summary>더보기</summary>그래서', out)
        self.assertEqual(render._fold_long("| " + "x" * 200 + " |"), "| " + "x" * 200 + " |")  # 표는 그대로
        short = "- 짧은 줄. 둘째."
        self.assertEqual(render._fold_long(short), short)

    def test_check_counts(self):
        c = render.check(NUMBERED)
        self.assertEqual(c["long_lines"], 0)
        self.assertLessEqual(c["visible_lines"], render.VISIBLE_MAX)
        long_doc = NUMBERED.replace("- 짧은 결론.", "- " + "가" * 200)
        self.assertEqual(render.check(long_doc)["long_lines"], 1)

    def test_check_flags_sections_after_evidence(self):
        self.assertEqual(render.check(NUMBERED)["extra_sections"], ["요청 축", "C 설계 노트"])
        ends = "# t\n\n## 한눈에\n- a\n\n## 선택지\n| A |\n\n## 결정할 것\n1. q\n\n## 근거\n### 신호\n"
        self.assertEqual(render.check(ends)["extra_sections"], [])
        self.assertEqual(render.check("# 메모\n\n## 아무 절\n글\n")["extra_sections"], [])  # 구조 조사 문서가 아니면 안 본다


if __name__ == "__main__":
    unittest.main()
