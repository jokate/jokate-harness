"""render.py — 선택지 · 그림 먼저, 나머지 근거는 접는다 (2026-10-20 사용자: HTML 이 길고 난잡하다)."""
import importlib.util
import os
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

    def test_habits_counted_on_front_only(self):
        """몰아 쓴 줄 · 작업 번호는 첫 화면만 기준, 날짜 꼬리표는 문서 전체 (2026-11-05 사용자: 구구절절 · 설계점만 본다)."""
        md = ("# t\n\n## 한눈에\n- 입구는 AdmitHit 하나(트레이스 · 직접 · 변형 · 진입기)(팀 → 사망)\n"
              "- task_5e5df7c8 이 정한다\n\n## 선택지\n| A | a1c2d29 |\n\n"
              "## 근거\n### 확인한 사실\n- 근거 쪽 줄(가 · 나 · 다 · 라)(마)\n- [18시 갱신] 고친 기록\n")
        c = render.check(md, [1])
        self.assertEqual((c["packed_front"], c["packed_rest"], c["ids_front"], c["date_tags"]), (1, 1, 2, 1))
        line, ok = render.report(c)
        self.assertFalse(ok)
        self.assertIn("몰아 쓴 줄 1개", line)
        self.assertIn("근거 육하원칙 표 없음", line)

    def test_clean_doc_passes_with_five_w_table(self):
        md = ("# t\n\n## 한눈에\n- 피해 입구는 한 곳이다.\n\n## 선택지\n| A | 4곳 |\n\n추천: A. 고르는 것은 사용자.\n"
              "- 문제: 입구가 넷이면 판정 순서를 네 곳에서 맞춰야 한다.\n- 버린 안: B — 입구마다 순서가 달라진다.\n"
              "- 대가: 입구 함수 하나가 커진다.\n- 뒤집는 조건: 판정 종류마다 순서가 달라야 하면 다시 본다.\n\n"
              "## 근거\n### 확인한 사실\n| 누가 | 언제 | 어디서 | 무엇을 | 어떻게 | 왜 | 확신 |\n|---|---|---|---|---|---|---|\n"
              "| 피격 판정 | 맞을 때 | YSPlaybackTask.cpp:604 | 피해 | AdmitHit 한 곳 | 입구가 넷이면 고칠 곳도 넷 | 확인 |\n"
              "- 근거 쪽 몰아 쓴 줄은 참고(가 · 나 · 다 · 라)\n")
        c = render.check(md, [1])
        self.assertTrue(c["five_w"])
        self.assertEqual((c["packed_rest"], c["why_slots"]), (1, 4))
        self.assertTrue(render.report(c)[1])  # 근거 쪽 몰아 쓴 줄 · 근거 표의 파일:줄은 통과를 막지 않는다
        no_why = md.replace("- 대가: 입구 함수 하나가 커진다.\n", "")
        line, ok = render.report(render.check(no_why, [1]))
        self.assertFalse(ok)
        self.assertIn("추천의 왜 칸 3/4", line)

    def test_go_reul_geot_heading_is_checked_too(self):
        """'선택지' 를 GUIDE 양식의 '고를 것' 으로 바꾸고 추천을 지우면 검사를 피했다 (문서 시범 1차)."""
        md = ("# t\n\n## 결론\n- 헛 끊김은 경로 확인으로 막는다.\n\n## 고를 것\n| 안 | 방법 |\n|---|---|\n| 가 | 끊기 전 확인 |\n"
              "| 나 | 남길 때 확인 |\n\n## 근거\n- 파일 표\n")
        c = render.check(md)
        self.assertIs(c["recommend"], False)
        self.assertIsNone(c["figures"])  # 구조도 · 절 기준은 선택지 절이 있는 구조 조사 문서만
        line, ok = render.report(c)
        self.assertFalse(ok)
        self.assertIn("추천 없음", line)
        self.assertIn("근거 육하원칙 표 없음", line)
        fixed = md.replace("\n## 근거", "\n추천: 나. 고르는 것은 사용자.\n- 문제: 끊긴 뒤에는 경로를 되돌릴 수 없다.\n"
                                      "- 버린 안: 가 — 끊기 전마다 확인하면 매 프레임 비용이 든다.\n- 대가: 남길 때 한 번 더 읽는다.\n"
                                      "- 뒤집는 조건: 남기는 곳이 둘 이상이 되면 다시 본다.\n\n"
                                      "| 누가 | 언제 | 어디서 | 무엇을 | 어떻게 | 왜 | 확신 |\n|---|---|---|---|---|---|---|\n"
                                      "| 연결 관리 | 끊길 때 | Link.cpp:40 | 경로 | 남길 때 확인 | 헛 끊김 | 확인 |\n\n## 근거")
        self.assertTrue(render.report(render.check(fixed))[1], render.report(render.check(fixed))[0])

    def test_when_cell_must_not_be_writing_time(self):
        head = "| 누가 | 언제 | 어디서 | 무엇을 | 어떻게 | 왜 | 확신 |\n|---|---|---|---|---|---|---|\n"
        for when, n in (("구조 검토 시점", 1), ("질문 2 검토", 1), ("공격이 맞을 때", 0), ("2026-11-05 검토", 0),
                        ("커밋 a1c2d29 조사", 0)):
            md = f"# t\n\n## 근거\n{head}| 판정 | {when} | A.cpp:1 | 피해 | 한 곳 | 고칠 곳 | 확인 |\n"
            self.assertEqual(render.check(md)["vague_when"], n, when)
        line, ok = render.report(render.check(f"# t\n\n## 근거\n{head}| 판정 | 구조 검토 시점 | A.cpp:1 | 피 | 한 곳 | 왜 | 확인 |\n"))
        self.assertFalse(ok)
        self.assertIn("'언제' 칸에 문서를 쓴 때를 적은 줄 1개", line)

    def test_ids_inside_front_five_w_table_are_allowed(self):
        """번호는 근거 표에 둔다. 결정 블록 밑 근거 표가 첫 화면에 있어도 번호를 세지 않는다."""
        md = ("# t\n\n## 결정\n- 입구는 한 곳이다.\n\n| 누가 | 언제 | 어디서 | 무엇을 | 어떻게 | 왜 | 확신 |\n"
              "|---|---|---|---|---|---|---|\n| Claude | 커밋 a1c2d29 | A.cpp:1 | 입구 | grep | 넷인지 | 확인 |\n\n"
              "- 본문의 task_5e5df7c8 은 센다\n")
        self.assertEqual(render.check(md)["ids_front"], 1)

    def test_each_decision_block_needs_why_and_five_w(self):
        """선택지 절 없이 '### 결정:' 블록만 써도 블록마다 왜 네 칸과 근거 표를 본다 (문서 시범 2차)."""
        good = ("### 결정: 입구는 한 곳이다\n- 문제: 넷이면 순서를 네 곳에서 맞춘다.\n- 버린 안: B — 순서가 갈린다.\n"
                "- 대가: 함수 하나가 커진다.\n- 뒤집는 조건: 순서가 판정마다 달라야 하면.\n\n"
                "| 누가 | 언제 | 어디서 | 무엇을 | 어떻게 | 왜 | 확신 |\n|---|---|---|---|---|---|---|\n"
                "| 판정 | 맞을 때 | A.cpp:1 | 피해 | 한 곳 | 고칠 곳 | 확인 |\n")
        md = f"# t\n\n## 정한 것\n- 입구는 한 곳이다.\n\n## 입구\n{good}\n## 기록\n{good.replace('- 대가: 함수 하나가 커진다.' + chr(10), '')}"
        c = render.check(md)
        self.assertEqual((c["decisions"], c["decisions_incomplete"]), (2, 1))
        line, ok = render.report(c)
        self.assertFalse(ok)
        self.assertIn("결정 블록 2개 중 칸이 빈 것 1개", line)
        self.assertTrue(render.report(render.check(f"# t\n\n## 정한 것\n- 한 곳.\n\n## 입구\n{good}"))[1])

    def test_date_tag_patterns(self):
        for s in ("[10-24]", "[18시 갱신 · 21:50]", "(사용자 결정 2026-11-03)", "16:34 뒤 이어진 길"):
            self.assertEqual(len(render.DATE_TAG.findall(s)), 1, s)
        for s in ("값 범위 [0-1]", "[1-2] 구간", "비율 16:9", "```\n[10-24]\n```"):
            self.assertEqual(len(render.DATE_TAG.findall(render._no_code(s))), 0, s)

    def test_check_flags_sections_after_evidence(self):
        self.assertEqual(render.check(NUMBERED)["extra_sections"], ["요청 축", "C 설계 노트"])
        ends = "# t\n\n## 한눈에\n- a\n\n## 선택지\n| A |\n\n## 결정할 것\n1. q\n\n## 근거\n### 신호\n"
        self.assertEqual(render.check(ends)["extra_sections"], [])
        self.assertEqual(render.check("# 메모\n\n## 아무 절\n글\n")["extra_sections"], [])  # 구조 조사 문서가 아니면 안 본다


class DiagramDesignFigureTest(unittest.TestCase):
    """diagram-design 구조도(<문서 이름>-구조*.html)를 '그림' 절에 끼워 넣고, 없으면 읽기 점검이 잡는다."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.dir = Path(self._td.name)
        self.doc = self.dir / "20261020-조건.md"
        self.doc.write_text(NUMBERED, encoding="utf-8")
        old, render.DD_EXPORT = render.DD_EXPORT, self.dir / "없는-export_svg.py"  # 설치본과 무관하게: 기본은 iframe
        self.addCleanup(setattr, render, "DD_EXPORT", old)

    def test_inline_svg_when_exported(self):
        fig = self.dir / "20261020-조건-구조-C.html"
        fig.write_text("<html></html>", encoding="utf-8")
        svg = fig.with_suffix(".svg")
        svg.write_text('<?xml version="1.0"?>\n<svg viewBox="0 0 1200 600">\n\n  <title id="t">조건 판정 전후</title>\n</svg>\n',
                       encoding="utf-8")
        os.utime(fig, (1, 1))  # 내보낸 SVG 가 더 새롭다 → 다시 만들지 않고 쓴다
        out = render.embed_figs(NUMBERED, [fig], self.dir)
        self.assertIn('<div class="ddsvg"><svg viewBox="0 0 1200 600">', out)
        self.assertNotIn("<iframe", out)
        self.assertNotIn("<?xml", out)
        block = out.split('<figure class="dd">')[1].split("</figure>")[0]
        self.assertNotIn("\n\n", block)  # 빈 줄이 있으면 마크다운이 HTML 덩어리를 끊는다
        self.assertIn("<figcaption>조건 판정 전후 · ", out)

    def test_page_has_theme_toggle_and_dark_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            page = render.render(NUMBERED, Path(td) / "d.html", "t").read_text(encoding="utf-8")
        for part in ('id="theme"', ":root[data-theme=dark]", "prefers-color-scheme:dark", "localStorage", "theme: isDark()"):
            self.assertIn(part, page)
        self.assertNotIn("__MD__", page)

    def test_figures_found_beside_doc(self):
        (self.dir / "20261020-조건-구조-C.html").write_text("<svg/>", encoding="utf-8")
        (self.dir / "20261020-조건-구조-A.html").write_text("<svg/>", encoding="utf-8")
        (self.dir / "20261020-다른.md").write_text("x", encoding="utf-8")
        self.assertEqual([p.name for p in render.dd_figs(self.doc)],
                         ["20261020-조건-구조-A.html", "20261020-조건-구조-C.html"])

    def test_embed_into_figure_section_and_fold_mermaid_as_text(self):
        fig = self.dir / "20261020-조건-구조-C.html"
        fig.write_text("<svg/>", encoding="utf-8")
        out = render.embed_figs(NUMBERED, [fig], self.dir)
        sec = out.split("## 3. 현재 구조")[1].split("## 6.")[0]
        self.assertIn('<iframe src="20261020-%EC%A1%B0%EA%B1%B4-%EA%B5%AC%EC%A1%B0-C.html"', sec)
        self.assertIn("<summary>Mermaid 원본</summary>", sec)
        self.assertIn("```text", sec)
        self.assertNotIn("```mermaid", sec)

    def test_no_figure_section_appends_one(self):
        fig = self.dir / "x-구조.html"
        out = render.embed_figs("# t\n\n## 선택지\n| A |\n", [fig], self.dir)
        self.assertIn("## 그림\n\n<figure", out)

    def test_render_with_src_embeds_and_check_counts(self):
        html_out = self.doc.with_suffix(".html")
        self.assertEqual(render.check(NUMBERED, render.dd_figs(self.doc))["figures"], 0)
        line, ok = render.report(render.check(NUMBERED, []))
        self.assertFalse(ok)
        self.assertIn("구조도 0장", line)
        (self.dir / "20261020-조건-구조-C.html").write_text("<svg/>", encoding="utf-8")
        render.render(NUMBERED, html_out, "t", src=self.doc)
        self.assertIn("figure class=\\\"dd\\\"", html_out.read_text(encoding="utf-8"))
        self.assertEqual(render.check(NUMBERED, render.dd_figs(self.doc, exclude=html_out))["figures"], 1)
        self.assertIsNone(render.check("# 메모\n\n글\n")["figures"])  # 구조 조사 문서가 아니면 안 본다

    def test_counter_review_follows_options(self):
        md = ("# t\n\n## 한눈에\n- a\n\n## 그림\ng\n\n## 반대 검토\n| 안 |\n\n"
              "## 선택지\n| A |\n\n## 근거\n### 신호\n")
        out = render.summary_first(md)
        self.assertLess(out.index("## 선택지"), out.index("## 반대 검토"))
        self.assertLess(out.index("## 반대 검토"), out.index("## 그림"))
        self.assertEqual(render.check(md)["extra_sections"], [])

    def test_question_section_is_front(self):
        md = NUMBERED.replace("## 8. 사용자 결정", "## 질문")
        head = render.summary_first(md).split("<details>")[0]
        self.assertIn("## 질문", head)


if __name__ == "__main__":
    unittest.main()
