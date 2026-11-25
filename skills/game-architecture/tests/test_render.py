"""render.py — 선택지 · 그림 먼저, 나머지 근거는 접는다 (2026-10-20 사용자: HTML 이 길고 난잡하다)."""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
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
        """'선택지' 를 GUIDE 폼의 '고를 것' 으로 바꾸고 추천을 지우면 검사를 피했다 (문서 시범 1차)."""
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


class NotesTest(unittest.TestCase):
    """문서 메모 칸 — 나중에 보다가 그 자리에서 적어 Claude 로 보낸다."""

    def project(self, tmp):
        root = Path(tmp) / "Game"
        (root / ".git").mkdir(parents=True)
        (root / "Saved" / "ClaudeArch").mkdir(parents=True)
        md = root / "Saved" / "ClaudeArch" / "입력.md"
        md.write_text("# 입력\n\n## 한눈에\n- 하나\n", encoding="utf-8")
        return root, md

    def cfg(self, text):
        blocks = render.NOTES_BLOCK.findall(text)
        self.assertEqual(len(blocks), 1)
        return json.loads(render.NOTES_CFG.search(blocks[0]).group(1))

    def test_page_says_which_doc_and_where_the_project_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, md = self.project(tmp)
            out = render.render(md.read_text(encoding="utf-8"), md.with_suffix(".html"), "입력", src=md)
            text = out.read_text(encoding="utf-8")
            self.assertEqual(self.cfg(text), {"src": "입력.md", "up": 2, "max": render.LINK_MAX})  # 경로를 박지 않는다
            self.assertNotIn(str(root), text.split("<!-- gh-notes -->")[1])
            self.assertLess(text.index("<!-- /gh-notes -->"), text.index("</body>"))
            self.assertIn("@media print{.gn,.gn-add,.gn-sel{display:none!important}}", text)  # PDF 에 실리지 않는다

    def test_no_project_found_means_no_folder_to_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "x.md"
            md.write_text("# x\n", encoding="utf-8")
            self.assertIsNone(render.project_root(tmp))
            self.assertEqual(self.cfg(render.render_html("# x\n", md.with_suffix(".html"), "x", src=md))["up"], None)
            self.assertEqual(render.project_root(tmp, given=tmp), Path(tmp).resolve())

    def test_page_inside_the_form_has_no_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "x.md"
            text = render.render_html("# x\n", md.with_suffix(".html"), "x", src=md, url_for=lambda p: "/a/" + p.name)
            self.assertNotIn("gh-notes", text)  # 폼 페이지에는 기각 이유 · 답 칸이 따로 있다

    def test_attach_to_someone_elses_html_and_take_it_off_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, md = self.project(tmp)
            page = md.with_name("보고.html")
            original = "<!doctype html>\r\n<html><body>\r\n<h2>결론</h2>\r\n</body></html>\r\n".encode("utf-8")
            page.write_bytes(original)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(render.main([str(page), "--attach"]), 0)
                once = page.read_bytes()
                self.assertEqual(self.cfg(once.decode("utf-8")), {"src": "", "up": 2, "max": render.LINK_MAX})  # 고칠 것은 그 HTML 이다
                self.assertNotIn(b"\n", once.replace(b"\r\n", b""))  # 줄 끝을 지킨다
                render.main([str(md.parent), "--attach"])  # 폴더째 · 두 번 붙여도 하나다
                self.assertEqual(page.read_bytes(), once)
                render.main([str(page), "--detach"])
            self.assertEqual(page.read_bytes(), original)

    def test_attached_figure_page_does_not_leak_into_the_figure(self):
        """구조도 페이지에 메모 칸을 붙여도 문서에 실리는 그림은 그대로다 — 내보내기 도구는 메모 칸을 뺀 글을 받는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root, md = self.project(tmp)
            fig = md.with_name("입력-구조-B.html")
            fig.write_text('<html><body><style>.n{fill:red}</style><svg viewBox="0 0 10 10"><title>전후</title></svg></body></html>', encoding="utf-8")
            exporter = Path(tmp) / "export_svg.py"  # 진짜 도구처럼 페이지의 <style> 을 전부 SVG 에 담는다
            exporter.write_text("import re, sys\nt = open(sys.argv[1], encoding='utf-8').read()\n"
                                "open(sys.argv[2], 'w', encoding='utf-8').write('<svg><style>' + ''.join(re.findall(r'<style[^>]*>(.*?)</style>', t, re.S)) + '</style></svg>')\n",
                                encoding="utf-8")
            old, render.DD_EXPORT = render.DD_EXPORT, exporter
            self.addCleanup(setattr, render, "DD_EXPORT", old)
            before = render.dd_svg(fig)
            with contextlib.redirect_stdout(io.StringIO()):
                render.attach([fig])
            self.assertIn("gn-pill", fig.read_text(encoding="utf-8"))
            self.assertEqual(render.dd_svg(fig), before)
            self.assertIn(".n{fill:red}", before)

    def test_attach_keeps_the_source_of_a_rendered_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, md = self.project(tmp)
            out = render.render(md.read_text(encoding="utf-8"), md.with_suffix(".html"), "입력", src=md)
            before = out.read_text(encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                render.attach([out])
            self.assertEqual(out.read_text(encoding="utf-8"), before)  # 원본(.md)을 그대로 가리킨다


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


FORM_DOC = """# 선입력 창 — 구조 조사

## 한눈에
- 문제: 창 길이가 세 곳에 흩어져 있다

## 선택지
| 선택지 | 다음 요청 때 고칠 곳 | 얻는 것 | 잃는 것 | 근거 |
|---|---|---|---|---|
| A. 땜질 수정 | 3곳 | 지금 빠르다 | 다음에 또 세 곳 | 확인 |
| **B. 버퍼가 창을 갖는다** | 1곳 | 한 곳만 고친다 | 파일 하나가 는다 | 확인 |

추천: B. 고르는 것은 사용자.
- 문제: 창 길이를 바꾸면 세 곳을 고친다
- 버린 안: A — 다음에 또 세 곳
- 대가: 파일 하나가 는다
- 뒤집는 조건: 창이 하나로 줄면
- 앞서 기각: C. 전역 설정 — 엔진 설정과 겹친다

## 그림
```mermaid
graph LR
  A-->B
```

## 질문
| # | 질문 | 갈래 | 추천 | 답에 따라 바뀌는 것 |
|---|---|---|---|---|
| 1 | 구조: A / B 중 무엇? | A / B | B — 한 곳 | 구현 범위 전체 |
| 2 | 창 길이는 테이블에서 읽나 | 예 / 아니오 / 모름 | 예 — 기획이 고친다 | 데이터 행 |
| 3 | 패드 입력도 같은 창을 쓰나 | | | 입력 경로 |

## 근거
### 요청 축
언제: 공격 중
"""


def http(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode("utf-8"), method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, ""


class DocFormTest(unittest.TestCase):
    """구조 문서의 선택지 · 추천 · 왜 · 질문을 선택 폼으로 옮긴다 — 같은 것을 두 번 쓰지 않는다."""

    def test_options_recommendation_why_and_questions_are_read(self):
        spec, errors = render.doc_form(FORM_DOC, "선입력 창")
        self.assertEqual(errors, [])
        main, extra = spec["questions"]
        self.assertEqual((main["title"], main["changes"]), ("구조: A / B 중 무엇?", "구현 범위 전체"))
        self.assertEqual(main["options"], [
            {"id": "A", "name": "땜질 수정", "next": "3곳", "gain": "지금 빠르다", "loss": "다음에 또 세 곳"},
            {"id": "B", "name": "버퍼가 창을 갖는다", "next": "1곳", "gain": "한 곳만 고친다", "loss": "파일 하나가 는다", "recommended": True}])
        self.assertEqual(main["why"], {"problem": "창 길이를 바꾸면 세 곳을 고친다", "dropped": ["A — 다음에 또 세 곳"],
                                       "cost": "파일 하나가 는다", "flip": "창이 하나로 줄면"})
        self.assertEqual(main["dropped_before"], ["C. 전역 설정 — 엔진 설정과 겹친다"])
        self.assertEqual(main["asks"], [{"id": "a3", "text": "패드 입력도 같은 창을 쓰나"}])   # 갈래 없는 질문은 답 적는 칸
        self.assertEqual((extra["id"], extra["title"], extra["changes"]), ("q2", "창 길이는 테이블에서 읽나", "데이터 행"))
        self.assertEqual(extra["options"], [{"id": "1", "name": "예", "recommended": True, "summary": "기획이 고친다"},
                                            {"id": "2", "name": "아니오"}, {"id": "3", "name": "모름"}])

    def test_heading_style_options(self):
        spec, _ = render.doc_form(ANSWER + "\n**추천: B안** — 한 곳\n", "입력 버퍼")
        self.assertEqual(spec["questions"][0]["options"], [{"id": "A", "name": "플래그", "summary": "다음 요청 때 3곳"},
                                                            {"id": "B", "name": "상태", "summary": "다음 요청 때 1곳"}])  # 추천 줄이 다른 절에 있다

    def test_table_with_one_decision_per_row_becomes_one_question_per_row(self):
        doc = ("# 조작표\n\n## 선택지\n| 결정 | A. 땜질 수정 | B | C | 정함 |\n|---|---|---|---|---|\n"
               "| ① 우클릭 태그 | 기존 태그 재사용 | 새 태그 | 생성기 고침 | C |\n"
               "| ② 길게 누르기 | 타이머 | IA 두 개 | 홀드 표 | |\n"
               "| ③ 배치 모드 | 행만 | IMC 얹기 | | 보류 |\n\n"
               "추천: ①C, ②B 로 간다. ③ 은 다시 고른다.\n- 문제: 짧게와 길게를 못 가른다\n")
        spec, errors = render.doc_form(doc, "조작표")
        self.assertEqual(errors, [])
        picks = [(q["id"], q["title"], [o["id"] + ("*" if o.get("recommended") else "") for o in q["options"]]) for q in spec["questions"]]
        self.assertEqual(picks, [("q1", "① 우클릭 태그", ["A", "B", "C*"]),      # 정함 칸
                                 ("q2", "② 길게 누르기", ["A", "B*", "C"]),      # 추천 줄의 ②B
                                 ("q3", "③ 배치 모드", ["A", "B"])])             # 보류 — 추천 없음, 빈 칸은 안이 아니다
        self.assertEqual(spec["questions"][0]["options"][0]["name"], "기존 태그 재사용")
        self.assertEqual(spec["questions"][0]["why"], {"problem": "짧게와 길게를 못 가른다"})

    def test_options_on_two_axes_split_into_one_question_per_axis(self):
        doc = ("# 계층\n\n## 선택지\n| 선택지 | 다음 요청 때 고칠 곳 |\n|---|---|\n| A. 데이터만 | 3곳 |\n| B. 칸 묶음 | 1곳 |\n"
               "| D. 시작 규칙 | 2곳 |\n| E. 지금 입구 | 1곳 |\n\n추천: B + E. 고르는 것은 사용자.\n\n"
               "## 질문\n| # | 질문 | 갈래 | 추천 | 답에 따라 바뀌는 것 |\n|---|---|---|---|---|\n"
               "| 1 | 그래프 축, 진입 축 중 무엇? | A·B / D·E | B + E | 작업 범위 |\n| 2 | 합치나? | 유지 / 합침 | 유지 — 쿨이 다르다 | 넘기기 |\n")
        spec, _ = render.doc_form(doc, "계층")
        picks = [(q["id"], [o["id"] + ("*" if o.get("recommended") else "") for o in q["options"]]) for q in spec["questions"]]
        self.assertEqual(picks, [("q1", ["A", "B*"]), ("q2", ["D", "E*"]), ("q3", ["1*", "2"])])
        self.assertEqual(spec["questions"][1]["title"], "그래프 축, 진입 축 중 무엇? — D · E")

    def test_options_as_columns(self):
        doc = "# x\n\n## 선택지\n| | A. 땜질 수정 | B. 버퍼 |\n|---|---|---|\n| 다음 요청 때 고칠 곳 | 3곳 | 1곳 |\n| 잃는 것 | 또 세 곳 | 파일 하나 |\n\n추천: B — 한 곳\n"
        spec, _ = render.doc_form(doc, "x")
        self.assertEqual(spec["questions"][0]["options"], [{"id": "A", "name": "땜질 수정", "next": "3곳", "loss": "또 세 곳"},
                                                            {"id": "B", "name": "버퍼", "next": "1곳", "loss": "파일 하나", "recommended": True}])

    def test_recommendation_ignores_letters_in_the_reason(self):
        doc = "# x\n\n## 선택지\n| 선택지 | 값 |\n|---|---|\n| A. 하나 | 1 |\n| B. 둘 | 2 |\n\n추천: B — A 보다 고칠 곳이 적다. GAS 는 그대로다.\n"
        options = render.doc_form(doc, "x")[0]["questions"][0]["options"]
        self.assertEqual([o["id"] for o in options if o.get("recommended")], ["B"])

    def test_unreadable_doc_gives_reasons(self):
        self.assertEqual(render.doc_form("# x\n\n## 요약\n글\n", "x"), (None, ["'선택지' 절이 없다"]))
        spec, errors = render.doc_form("# x\n\n## 선택지\n| 안 | 값 |\n|---|---|\n| API 설계 | 1 |\n| A. 하나 | 2 |\n", "x")
        self.assertIsNone(spec)
        self.assertIn("1개만", errors[0])

    def test_embedded_doc_folds_what_the_form_shows(self):
        head, fold = render.summary_first(FORM_DOC, render.FORM_HIDES).split("<details>", 1)
        self.assertEqual([ln for ln in head.splitlines() if ln.startswith("## ")], ["## 한눈에", "## 그림"])
        self.assertIn("근거 — 선택지 · 질문", fold.splitlines()[0])        # 지우지 않는다 — 접힌 근거에서 표를 볼 수 있다
        self.assertIn("## 선택지", render.summary_first(FORM_DOC).split("<details>")[0])

    def test_embedded_page_loads_its_files_from_the_form_server(self):
        with tempfile.TemporaryDirectory() as d:
            page = render.render_html(FORM_DOC, Path(d) / "x.html", "선입력 창", url_for=lambda p: f"/a/{Path(p).name}?t=tok")
            self.assertIn('<html lang="ko" data-embed>', page)
            self.assertIn('src="/a/marked.min.js?t=tok"', page)
            self.assertNotIn("file:///", page)                           # http 페이지는 file:// 스크립트를 못 읽는다
            plain = render.render_html(FORM_DOC, Path(d) / "x.html", "선입력 창")
            self.assertIn('<html lang="ko">', plain)
            self.assertIn("file:///", plain)


class OnePageTest(unittest.TestCase):
    """--form: 문서와 선택 폼이 한 페이지로 뜨고, 보내면 이 명령이 답을 찍고 끝난다."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.dir = Path(self._td.name)
        self.src = self.dir / "20261119-창.md"

    def launch(self, md, answers=None, **env):
        self.src.write_text(md, encoding="utf-8")
        full = {**os.environ, "PYTHONIOENCODING": "utf-8", "GAME_HARNESS_DOC_NUDGE": "1", **env}
        full = {k: v for k, v in full.items() if v is not None}
        proc = subprocess.Popen([sys.executable, "-u", str(HERE.parent / "scripts" / "render.py"), str(self.src), "--form", "--no-open",
                                 "--project", str(self.dir)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=full)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        seen = []
        if answers is not None:
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace")
                seen.append(line)
                if line.startswith("폼: "):
                    base, token = line.split()[1].split("/?t=")
                    self.page, self.doc = http(f"{base}/?t={token}")[1], http(f"{base}/doc?t={token}")[1]
                    self.assertEqual(http(f"{base}/submit?t={token}", {"answers": answers})[0], 204)
                    break
        out, _ = proc.communicate(timeout=30)
        return proc.returncode, "".join(seen) + out.decode("utf-8", "replace")

    def files(self):
        return sorted(f.name for f in self.dir.iterdir() if f.is_file())

    def test_one_page_then_the_answer_comes_back(self):
        code, out = self.launch(FORM_DOC, {"q": {"q1": {"choice": "B", "keep": True, "note": "이름은 InputWindow"}, "q2": {"choice": "1"}}})
        self.assertEqual(code, 0, out)
        self.assertIn("읽기 점검:", out)
        self.assertNotIn("점검: 질문 2", out)                             # 곁 질문에 왜 네 칸을 요구하지 않는다
        self.assertIn('"doc": "/doc?t=', self.page)                       # 폼 페이지 한 장에 문서가 실린다
        self.assertIn('"name": "버퍼가 창을 갖는다"', self.page)
        self.assertIn("data-embed", self.doc)
        self.assertIn("## 한눈에", self.doc)
        self.assertIn("제출됨 — 선입력 창", out)
        self.assertIn("B. 버퍼가 창을 갖는다", out)
        self.assertIn("이름은 InputWindow", out)
        self.assertIn("결정 로그: D-001", out)
        self.assertEqual(self.files(), ["20261119-창.html", "20261119-창.md"])  # 답 파일은 지우고 문서는 남긴다

    def test_unattended_run_writes_the_doc_and_serves_nothing(self):
        code, out = self.launch(FORM_DOC, CLAUDE_CODE_SESSION_ATTENDED="0", GAME_HARNESS_DOC_NUDGE=None)
        self.assertEqual(code, 4, out)
        self.assertIn("헤드리스 실행", out)
        self.assertNotIn("폼: http", out)
        self.assertEqual(self.files(), ["20261119-창.html", "20261119-창.md"])

    def test_doc_without_options_stays_a_plain_doc(self):
        code, out = self.launch("# 구조 지도\n\n## 요약\n- 한 줄\n")
        self.assertEqual(code, 0, out)
        self.assertIn("선택 폼을 붙이지 못했다", out)
        self.assertIn("'선택지' 절이 없다", out)
        self.assertNotIn("폼: http", out)


if __name__ == "__main__":
    unittest.main()
