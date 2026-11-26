#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decide.py · diffdoc.py — 폼 점검, 서버 왕복(저장 · 보내기 · 토큰), 결정 로그(적기 · 기각), diff 묶기, 헤드리스 실행 차단, 딸린 문서."""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

os.environ["GAME_HARNESS_DOC_NUDGE"] = "1"  # 헤드리스 실행(직원 · CI)에서 이 테스트를 돌려도 폼이 뜬다. 차단은 Unattended 가 따로 본다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import decide  # noqa: E402
import diffdoc  # noqa: E402

WHY = {"problem": "입구가 넷이다", "dropped": ["A — 땜질"], "cost": "파일 하나가 는다", "flip": "입구가 하나로 줄면"}
SPEC = {"kind": "selection", "title": "피해 입구", "context": ["입구가 넷이다"], "questions": [
    {"id": "q1", "title": "구조는?", "why": WHY, "checks": ["선례와 같은 꼴인가", "기획자가 혼자 세팅하나"],
     "asks": [{"id": "a1", "text": "NPC 도 받나?"}],
     "options": [{"id": "A", "name": "땜질 수정"}, {"id": "B", "name": "입구 하나", "recommended": True}]},
    {"id": "q2", "title": "이름은?", "options": [{"id": "A", "name": "Hit"}, {"id": "B", "name": "Damage"}]}]}


def http(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode("utf-8"), method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, ""


class SpecCheck(unittest.TestCase):
    def test_good_spec_only_warns_about_missing_recommendation(self):
        errors, warns = decide.check_spec(SPEC)
        self.assertEqual(errors, [])
        self.assertEqual(warns, ["질문 2: 추천이 없다"])

    def test_structural_problems_are_errors(self):
        bad = {"kind": "selection", "title": "", "questions": [
            {"id": "q 1", "title": "x", "options": [{"id": "A", "name": "a", "recommended": True}]},
            {"id": "q2", "title": "y", "options": [{"id": "A", "name": "a", "recommended": True}, {"id": "A", "name": "b", "recommended": True}]}]}
        errors, _ = decide.check_spec(bad)
        joined = "\n".join(errors)
        for needle in ("title 이 없다", "질문 id", "질문 1: 선택지가 2개보다 적다", "질문 2: 선택지 id", "질문 2: 추천이 둘 이상"):
            self.assertIn(needle, joined)

    def test_too_many_questions_and_long_lines_warn(self):
        q = lambda i: {"id": f"q{i}", "title": "가" * 130, "options": [{"id": "A", "name": "a"}, {"id": "B", "name": "b"}]}
        _, warns = decide.check_spec({"kind": "selection", "title": "t", "questions": [q(i) for i in range(6)]})
        self.assertTrue(any("질문 6개" in w for w in warns))
        self.assertTrue(any("120자 넘는 줄 1개" in w for w in warns))

    def test_page_embeds_data_without_closing_the_script(self):
        spec = dict(SPEC, title="</script><b>x")
        page = decide.build_page(spec, None, "tok", True, "n")
        self.assertIn("<title>&lt;/script&gt;&lt;b&gt;x</title>", page)
        self.assertEqual(page.count("</script>"), 2)  # 템플릿의 스크립트 둘뿐


class ReviewSummary(unittest.TestCase):
    SPEC = {"kind": "review", "title": "검수", "docs": [
        {"id": "d1", "title": "검수", "name": "검수.md", "sections": [{"id": "d1s1", "title": "결론"}, {"id": "d1s2", "title": "근거 | 표"}]}]}

    def test_spec_needs_docs_and_unique_sections(self):
        self.assertEqual(decide.check_spec(self.SPEC)[0], [])
        self.assertIn("docs 가 비었다", decide.check_spec({"kind": "review", "title": "t", "docs": []})[0])
        twice = {"kind": "review", "title": "t", "docs": [{"sections": [{"id": "a", "title": "x"}, {"id": "a", "title": "y"}]}]}
        self.assertIn("절의 id 가 비었거나 겹친다", decide.check_spec(twice)[0])

    def test_unseen_sections_are_not_confirmed(self):
        text = decide.review_summary(self.SPEC, {"s": {"d1s1": {"verdict": "ok", "note": ""}}})
        self.assertIn("확인 1 · 다시 0 · 안 봄 1", text)
        self.assertIn("| 검수 | 근거 \\| 표 | 안 봄 |  |", text)
        self.assertIn("다음: 안 본 절 1개는 확인받지 못했다", text)
        self.assertNotIn("문서가 전부 확인됐다", text)


class ServerRoundTrip(unittest.TestCase):
    def serve(self, spec, save_to):
        ready, result = threading.Event(), {}
        def run():
            with redirect_stdout(io.StringIO()):
                result["end"], result["answers"] = decide.serve(spec, save_to, 1, False, on_ready=lambda u: (result.update(url=u), ready.set()))
        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.assertTrue(ready.wait(5))
        return t, result

    def test_save_then_submit_returns_answers_and_stops(self):
        with tempfile.TemporaryDirectory() as d:
            save_to = Path(d) / "x.answers.json"
            t, result = self.serve(SPEC, save_to)
            base, token = result["url"].split("/?t=")
            self.assertEqual(http(result["url"])[0], 200)
            self.assertEqual(http(base + "/")[0], 403)                     # 토큰 없는 읽기
            self.assertEqual(http(base + "/save?t=wrong", {"answers": {}})[0], 403)
            self.assertEqual(http(f"{base}/save?t={token}", {"answers": {"q": {"q1": {"choice": "A"}}}})[0], 204)
            self.assertFalse(json.loads(save_to.read_text(encoding="utf-8"))["submitted"])
            self.assertIn('"choice": "A"', http(result["url"])[1])       # 다시 열면 저장한 답이 실린다
            self.assertEqual(http(f"{base}/submit?t={token}", {"answers": {"q": {"q1": {"choice": "B"}}}})[0], 204)
            t.join(5)
            self.assertFalse(t.is_alive())
            self.assertEqual(result["end"], "submitted")
            self.assertEqual(result["answers"]["q"]["q1"]["choice"], "B")
            self.assertTrue(json.loads(save_to.read_text(encoding="utf-8"))["submitted"])

    def test_closing_the_tab_without_sending_ends_as_closed(self):
        old, decide.CLOSE_GRACE = decide.CLOSE_GRACE, 0.2
        try:
            with tempfile.TemporaryDirectory() as d:
                t, result = self.serve(SPEC, Path(d) / "x.answers.json")
                base, token = result["url"].split("/?t=")
                self.assertEqual(http(f"{base}/bye?t={token}", {})[0], 204)
                t.join(5)
                self.assertEqual(result["end"], "closed")
        finally:
            decide.CLOSE_GRACE = old


ANSWERS = {"q": {"q1": {"choice": "B", "keep": True, "rejects": {"A": "다음에 또 네 곳"}, "checks": [True, False], "asks": {"a1": "예"}, "note": "이름은 X 로"},
                 "q2": {"choice": None, "rejects": {"A": "엔진 이름과 겹친다", "B": ""}, "note": "동사로 시작하게"}}}


class PipedForm(unittest.TestCase):
    """`form -`: 폼을 표준 입력으로 받는다 — 모델이 파일을 따로 쓰지 않는다."""

    def run_piped(self, spec, *flags):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**__import__("os").environ, "TMP": tmp, "TEMP": tmp, "TMPDIR": tmp, "PYTHONIOENCODING": "utf-8"}
            r = subprocess.run([sys.executable, str(Path(decide.__file__)), "form", "-", "--project", tmp, *flags],
                               input=json.dumps(spec, ensure_ascii=False).encode("utf-8"), capture_output=True, env=env, timeout=30)
            left = sorted(f.suffix for f in Path(tmp).rglob("*") if f.is_file())
            return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace"), left

    def test_bad_form_leaves_nothing(self):
        code, out, left = self.run_piped({"kind": "selection", "title": "x", "questions": []})
        self.assertEqual(code, 1)
        self.assertIn("폼 오류", out)
        self.assertEqual(left, [])

    def test_good_form_is_read_from_stdin(self):
        code, out, left = self.run_piped(SPEC, "--static")
        self.assertEqual(code, 0, out)
        self.assertIn("폼 파일:", out)
        self.assertEqual(left, [".html", ".json"])


class Unattended(unittest.TestCase):
    """헤드리스 실행(`claude -p` · 릴레이 직원)에서는 폼을 띄우지 않는다 — 받을 사람이 없어 명령이 끝나지 않는다."""

    def test_only_an_explicit_zero_blocks(self):
        self.assertEqual(decide.unattended({}), "")                                  # 신호가 없는 판(터미널 · IDE)은 띄운다
        self.assertEqual(decide.unattended({"CLAUDE_CODE_SESSION_ATTENDED": "1"}), "")
        self.assertIn("ATTENDED=0", decide.unattended({"CLAUDE_CODE_SESSION_ATTENDED": "0"}))
        self.assertEqual(decide.unattended({"CLAUDE_CODE_SESSION_ATTENDED": "0", "GAME_HARNESS_DOC_NUDGE": "1"}), "")
        self.assertIn("NUDGE=0", decide.unattended({"CLAUDE_CODE_SESSION_ATTENDED": "1", "GAME_HARNESS_DOC_NUDGE": "0"}))

    def run_cli(self, *args, stdin=None):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "TMP": tmp, "TEMP": tmp, "TMPDIR": tmp, "PYTHONIOENCODING": "utf-8", "CLAUDE_CODE_SESSION_ATTENDED": "0"}
            env.pop("GAME_HARNESS_DOC_NUDGE")
            r = subprocess.run([sys.executable, str(Path(decide.__file__)), *args, "--project", tmp], input=stdin, capture_output=True, env=env, timeout=30)
            return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace"), sorted(f.name for f in Path(tmp).rglob("*") if f.is_file())

    def test_form_is_not_served_and_leaves_nothing(self):
        for flags in ((), ("--static",)):
            code, out, left = self.run_cli("form", "-", *flags, stdin=json.dumps(SPEC, ensure_ascii=False).encode("utf-8"))
            self.assertEqual(code, decide.UNATTENDED, out)
            self.assertIn("헤드리스 실행", out)
            self.assertIn("다음: 선택지와 추천은 답에 글로", out)
            self.assertNotIn("폼: http", out)
            self.assertEqual(left, [])

    def test_ledger_and_diff_pages_are_not_served(self):
        code, out, _ = self.run_cli("collect")
        self.assertEqual(code, decide.UNATTENDED, out)
        args = argparse.Namespace(timeout=1, no_open=True, project=".", keep=True)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ATTENDED": "0"}), redirect_stdout(io.StringIO()) as buf:
            os.environ.pop("GAME_HARNESS_DOC_NUDGE")
            code = decide.run_form({"kind": "diff", "title": "x", "groups": []}, None, "x.answers.json", args)
        self.assertEqual(code, decide.UNATTENDED)
        self.assertIn("diff-proto 페이지를 띄우지 않았다", buf.getvalue())
        self.assertIn("구현 확인 안 받음", buf.getvalue())

    def test_diff_page_says_so_at_the_first_command(self):
        """이야기를 쓰기 전의 첫 명령(--status)에서 안다 — 헤드리스 실행이 확인 단계에 토큰을 쓰지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "CLAUDE_CODE_SESSION_ATTENDED": "0"}
            env.pop("GAME_HARNESS_DOC_NUDGE")
            for flags in (["--status"], ["none.json", "--check"]):
                r = subprocess.run([sys.executable, str(Path(diffdoc.__file__)), *flags, "--path", tmp, "--project", tmp],
                                   capture_output=True, env=env, timeout=30)
                self.assertEqual(r.returncode, decide.UNATTENDED, r.stdout.decode("utf-8", "replace"))
                self.assertIn("헤드리스 실행", r.stdout.decode("utf-8", "replace"))


class DocPage(unittest.TestCase):
    """문서가 딸린 폼: 문서와 문서가 쓰는 파일을 같은 서버가 토큰을 받고 내보낸다 — 읽는 곳과 고르는 곳이 한 탭이다."""

    def test_doc_and_its_files_are_served_behind_the_token(self):
        with tempfile.TemporaryDirectory() as d:
            lib = Path(d) / "lib.min.js"
            lib.write_text("window.lib = 1;", encoding="utf-8")
            ready, result = threading.Event(), {}

            def run():
                with redirect_stdout(io.StringIO()):
                    result["end"], _ = decide.serve(SPEC, Path(d) / "x.answers.json", 1, False,
                                                    on_ready=lambda u: (result.update(url=u), ready.set()),
                                                    doc=lambda url_for: f'<html><script src="{url_for(lib)}"></script>문서 본문</html>')
            t = threading.Thread(target=run, daemon=True)
            t.start()
            self.assertTrue(ready.wait(5))
            base, token = result["url"].split("/?t=")
            self.assertIn(f'"doc": "/doc?t={token}"', http(result["url"])[1])   # 폼 페이지가 문서를 가리킨다
            code, body = http(f"{base}/doc?t={token}")
            self.assertEqual(code, 200)
            self.assertIn("문서 본문", body)
            asset = re.search(r'src="([^"]+)"', body).group(1)
            self.assertEqual(http(base + asset), (200, "window.lib = 1;"))
            self.assertEqual(http(base + asset.split("?")[0])[0], 403)          # 토큰 없이는 못 읽는다
            self.assertEqual(http(f"{base}/doc")[0], 403)
            self.assertEqual(http(f"{base}/a/9-none.js?t={token}")[0], 404)     # 문서가 가리킨 파일만 내보낸다
            self.assertEqual(http(f"{base}/submit?t={token}", {"answers": {}})[0], 204)
            t.join(5)
            self.assertEqual(result["end"], "submitted")

    def test_form_without_a_doc_has_no_doc_frame(self):
        self.assertIn('"doc": null', decide.build_page(SPEC, None, "tok", True, "x.answers.json"))


class LedgerFlow(unittest.TestCase):
    def test_summary_shows_choice_unchecked_items_and_replies(self):
        text = decide.selection_summary(SPEC, ANSWERS)
        self.assertIn("| 1 | 구조는? | B. 입구 하나 | 같음 | 이름은 X 로 |", text)
        self.assertIn("| 2 | 이름은? | 안 고름 | — | 동사로 시작하게 |", text)
        self.assertIn("- 1번 A. 땜질 수정 — 다음에 또 네 곳", text)
        self.assertIn("- 2번 A. Hit — 엔진 이름과 겹친다", text)
        self.assertIn("- 2번 B. Damage — (이유 없음)", text)
        self.assertIn("- 1번: 기획자가 혼자 세팅하나", text)
        self.assertNotIn("선례와 같은 꼴인가", text)
        self.assertIn("- 1번 · NPC 도 받나? → 예", text)

    def test_only_chosen_questions_are_recorded_and_reject_keeps_history(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = decide.ledger_path(d)
            self.assertEqual(decide.record_selection(SPEC, ANSWERS, ledger), ["D-001"])
            second = decide.add_decision(ledger, "카메라", "어깨 너머", dropped=["탑뷰"])
            self.assertEqual(second, "D-002")
            first = decide.load_events(ledger)[0]
            self.assertEqual((first["choice"], first["dropped"], first["note"]), ("B. 입구 하나", ["A. 땜질 수정 — 다음에 또 네 곳"], "이름은 X 로"))
            self.assertEqual(first["answers"], [{"q": "NPC 도 받나?", "a": "예"}])
            before = ledger.read_text(encoding="utf-8")
            done, skipped = decide.reject_decisions(ledger, [("D-001", "입구가 다시 갈렸다"), ("D-002", ""), ("D-009", "x")])
            self.assertEqual(done, ["D-001"])
            self.assertEqual(skipped, ["D-002: 이유가 없다", "D-009: 유효한 결정이 아니다"])
            self.assertTrue(ledger.read_text(encoding="utf-8").startswith(before))   # 옛 줄은 그대로, 뒤에 덧붙였다
            live, dead = decide.split_ledger(decide.load_events(ledger))
            self.assertEqual(([e["id"] for e in live], [e["id"] for e in dead]), (["D-002"], ["D-001"]))
            self.assertEqual(dead[0]["reason"], "입구가 다시 갈렸다")
            self.assertNotIn("D-001", decide.ledger_table(ledger))
            self.assertIn("입구가 다시 갈렸다", decide.ledger_table(ledger, True))
            self.assertEqual(decide.reject_decisions(ledger, [("D-001", "또")])[1], ["D-001: 유효한 결정이 아니다"])

    def test_rejections_from_an_earlier_form_reach_the_ledger(self):
        spec = {"kind": "selection", "title": "이름", "questions": [
            {"id": "q", "title": "이름은?", "dropped_before": ["Hit — 엔진 이름과 겹친다"],
             "options": [{"id": "A", "name": "ReceiveDamage", "recommended": True}, {"id": "B", "name": "TakeHit"}]}]}
        self.assertEqual(decide.check_spec(spec)[0], [])
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(decide.record_selection(spec, {"q": {"q": {"choice": "A"}}}, decide.ledger_path(d)), [])   # 남김 표시가 없다
            self.assertFalse(decide.ledger_path(d).exists())
            decide.record_selection(spec, {"q": {"q": {"choice": "A", "keep": True}}}, decide.ledger_path(d))
            self.assertEqual(decide.load_events(decide.ledger_path(d))[0]["dropped"], ["B. TakeHit", "Hit — 엔진 이름과 겹친다"])

    def test_finish_records_and_cleanup_removes_form_files(self):
        with tempfile.TemporaryDirectory() as d:
            spec_path = Path(d) / "form.json"
            spec_path.write_text(json.dumps(SPEC), encoding="utf-8")
            decide.write_answers(decide.answers_path(spec_path), ANSWERS, True)
            out = io.StringIO()
            with redirect_stdout(out):
                code = decide.main(["done", str(spec_path), "--project", d])
            self.assertEqual(code, 0)
            self.assertIn("결정 로그: D-001", out.getvalue())
            self.assertEqual(list(Path(d).glob("form*")), [])
            self.assertTrue(decide.ledger_path(d).is_file())

    def test_reject_form_answers_apply_to_the_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = decide.ledger_path(d)
            decide.add_decision(ledger, "카메라", "어깨 너머")
            spec = decide.ledger_spec(ledger, "reject")
            self.assertEqual((spec["mode"], len(spec["live"])), ("reject", 1))
            with redirect_stdout(io.StringIO()) as out:
                decide.finish(spec, {"r": {"D-001": {"reject": True, "reason": "탑뷰로 바꿈"}}}, d)
            self.assertIn("기각 1건: D-001", out.getvalue())
            self.assertEqual(decide.split_ledger(decide.load_events(ledger))[0], [])


GIT_DIFF = """diff --git a/Src/Buffer.cpp b/Src/Buffer.cpp
index 1111111..2222222 100644
--- a/Src/Buffer.cpp
+++ b/Src/Buffer.cpp
@@ -10,4 +10,5 @@ void Tick()
 keep
--- old comment
+++ new comment
+added
 keep2
 keep3
@@ -40 +41,2 @@
-one
+uno
+dos
diff --git a/Src/New.h b/Src/New.h
new file mode 100644
--- /dev/null
+++ b/Src/New.h
@@ -0,0 +1,2 @@
+#pragma once
+struct FNew {};
diff --git a/Art/icon.png b/Art/icon.png
Binary files a/Art/icon.png and b/Art/icon.png differ
"""

SVN_DIFF = """Index: Src/Effect.cpp
===================================================================
--- Src/Effect.cpp\t(revision 12)
+++ Src/Effect.cpp\t(working copy)
@@ -1,2 +1,2 @@
-old
+new
 same
Index: Src/Added.cpp
===================================================================
--- Src/Added.cpp\t(nonexistent)
+++ Src/Added.cpp\t(working copy)
@@ -0,0 +1 @@
+int x;
"""


class DiffDoc(unittest.TestCase):
    def test_git_diff_keeps_deleted_lines_that_look_like_headers(self):
        files = diffdoc.parse_diff(GIT_DIFF)
        self.assertEqual([(f["path"], f["status"], len(f["hunks"]), f["binary"]) for f in files],
                         [("Src/Buffer.cpp", "수정", 2, False), ("Src/New.h", "추가", 1, False), ("Art/icon.png", "수정", 0, True)])
        first = files[0]["hunks"][0]["lines"]
        self.assertEqual(first[1], ["-", 11, None, "-- old comment"])
        self.assertEqual(first[2], ["+", None, 11, "++ new comment"])
        self.assertEqual(first[-1], [" ", 13, 14, "keep3"])
        self.assertEqual(files[0]["hunks"][1]["lines"], [["-", 40, None, "one"], ["+", None, 41, "uno"], ["+", None, 42, "dos"]])

    def test_svn_diff_marks_added_files(self):
        files = diffdoc.parse_diff(SVN_DIFF)
        self.assertEqual([(f["path"], f["status"]) for f in files], [("Src/Effect.cpp", "수정"), ("Src/Added.cpp", "추가")])

    def test_story_groups_hunks_and_leftovers_go_to_rest(self):
        story = {"title": "버퍼 시안", "groups": [
            {"title": "버퍼 규칙을 한 곳으로", "why": "두 곳에서 갈렸다", "risk": "높음", "match": ["Buffer.cpp#1"]},
            {"title": "새 타입", "match": ["Src/*.h"]}]}
        spec, report, errors = diffdoc.build(diffdoc.parse_diff(GIT_DIFF), story)
        self.assertEqual(errors, [])
        self.assertEqual([(g["id"], g["title"], g["added"], g["removed"]) for g in spec["groups"]],
                         [("g1", "버퍼 규칙을 한 곳으로", 2, 1), ("g2", "새 타입", 2, 0), ("rest", diffdoc.REST, 2, 1)])
        self.assertEqual([f["path"] for f in spec["groups"][2]["files"]], ["Src/Buffer.cpp", "Art/icon.png"])
        self.assertIn("핵심 hunk 2개 · 판정 안 하는 나머지 2개", report)
        self.assertIn("나머지: Src/Buffer.cpp#2 · Art/icon.png", report)   # 무엇을 접어 두는지 쓰는 쪽이 본다
        self.assertEqual([g["skipped"] for g in spec["groups"]], [False, False, True])
        self.assertEqual(decide.check_spec(spec)[0], [])
        text = decide.diff_summary(spec, {"g": {"g1": {"verdict": "ok", "note": "경계 확인"}, "g2": {"verdict": "no", "note": "이름을 바꿔라"}}})
        self.assertIn("확인 1 · 기각 1 · 미정 0 · 나머지 hunk 2개는 보지 않음", text)
        self.assertIn("| 1. 버퍼 규칙을 한 곳으로 | 확인함 | 경계 확인 |", text)
        self.assertIn("| 2. 새 타입 | 기각 | 이름을 바꿔라 |", text)
        self.assertIn("| 3. 나머지 변경 | 판정 안 함 |  |", text)

    def test_story_pointing_outside_the_diff_is_an_error(self):
        story = {"title": "t", "groups": [{"title": "없는 변경", "match": ["Src/Ghost.cpp"]}, {"title": "", "match": ["x"]},
                                          {"title": "위험 오타", "risk": "큼", "match": ["Src/New.h"]}]}
        _, _, errors = diffdoc.build(diffdoc.parse_diff(GIT_DIFF), story)
        joined = "\n".join(errors)
        for needle in ("diff 에 없는 것을 가리킨다 — Src/Ghost.cpp", "그룹 2: title 이 없다", "risk 는 높음 · 중간 · 낮음"):
            self.assertIn(needle, joined)

    def test_cp949_source_is_decoded(self):
        self.assertEqual(diffdoc.decode("// 피해 입구".encode("cp949")), "// 피해 입구")

    def test_git_working_copy_includes_untracked_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@x.test", "-c", "commit.gpgsign=false", *a],
                                            cwd=d, check=True, capture_output=True)
            git("init", "-q")
            (root / "a.cpp").write_text("one\ntwo\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-q", "-m", "init")
            (root / "a.cpp").write_text("one\n2\n", encoding="utf-8")
            (root / "b.cpp").write_text("new\n", encoding="utf-8")
            story = root / "story.json"
            story.write_text(json.dumps({"title": "t", "groups": [{"title": "둘 다", "match": ["*.cpp"]}]}), encoding="utf-8")
            decide.write_answers(decide.answers_path(story), {}, False)   # 하네스가 쓴 파일은 변경으로 세지 않는다
            decide.add_decision(decide.ledger_path(d), "주제", "고른 것")
            (root / ".claude" / "decide").mkdir()
            (root / ".claude" / "decide" / "other.json").write_text("{}", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                code = diffdoc.main([str(story), "--path", d, "--check"])
            self.assertEqual(code, 0, out.getvalue())
            self.assertIn("파일 2개", out.getvalue())
            self.assertIn("핵심 hunk 2개 · 판정 안 하는 나머지 0개", out.getvalue())

    def test_mixed_encoding_diff_is_decoded_line_by_line(self):
        raw = "Index: 소스/효과.cpp\n".encode("cp949") + "+// 피해 입구\n".encode("utf-8")
        self.assertEqual(diffdoc.decode(raw), "Index: 소스/효과.cpp\n+// 피해 입구\n")


class ImplementationCycle(unittest.TestCase):
    """구현 확인 사이클: 확인 → 기각 → 고침 → 다시 확인 → 확정. 적용되는 코드는 확인받은 코드와 같다."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.repo = Path(self._td.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.write({})
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
        self.story = Path(self._td.name) / "story.json"

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def write(self, changed):
        lines = [changed.get(i, f"line {i}") for i in range(1, 31)]
        (self.repo / "a.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def run_doc(self, *flags, groups=None, verdicts=None):
        """diffdoc 을 돌린다. verdicts 를 주면 뜬 폼에 그 판정을 보내고 끝까지 기다린다. → 출력."""
        cmd = [sys.executable, "-u", str(Path(diffdoc.__file__)), "--path", str(self.repo), "--project", str(self.repo), "--no-open", *flags]
        if groups is not None:
            self.story.write_text(json.dumps({"title": "선입력 창", "groups": groups}, ensure_ascii=False), encoding="utf-8")
            cmd.insert(3, str(self.story))
        env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.repo, env=env)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        seen = []
        if verdicts is not None:
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace")
                seen.append(line)
                if line.startswith("폼: "):
                    base, token = line.split()[1].split("/?t=")
                    self.assertEqual(http(f"{base}/submit?t={token}", {"answers": {"g": verdicts}})[0], 204)
                    break
        out, _ = proc.communicate(timeout=30)
        return "".join(seen) + out.decode("utf-8", "replace")

    def test_reject_fix_reshow_then_confirmed(self):
        both = [{"title": "만료를 건너뛴다", "match": ["a.txt#1"]}, {"title": "창 길이를 버퍼가 갖는다", "match": ["a.txt#2"]}]
        self.write({3: "new 3", 25: "hard-coded 25"})
        out = self.run_doc(groups=both, verdicts={"g1": {"verdict": "ok", "note": ""}, "g2": {"verdict": "no", "note": "테이블에서 읽어라"}})
        self.assertIn("확인 1 · 기각 1 · 미정 0", out)
        self.assertIn("확인 누계: hunk 1/2", out)
        self.assertIn("다음: 기각한 그룹을 피드백대로 고친다", out)
        self.assertNotIn("구현이 확정됐다", out)

        self.write({3: "new 3", 25: "from table 25"})                      # 기각 그룹만 고쳤다
        status = self.run_doc("--status")
        self.assertIn("hunk 2개 · 확인 1개 · 남은 것 1개", status)
        self.assertIn("- a.txt#2", status)
        self.assertNotIn("a.txt#1", status)

        again = [{"title": "창 길이를 테이블에서 읽는다", "match": ["a.txt#2"]}]
        check = self.run_doc("--check", groups=again)
        self.assertIn("핵심 hunk 1개 · 판정 안 하는 나머지 0개 · 앞서 확인한 것 1개", check)  # 확인한 hunk 가 '나머지 변경' 으로 돌아오지 않는다
        out = self.run_doc(groups=again, verdicts={"g1": {"verdict": "ok", "note": ""}})
        self.assertIn("확인 1 · 기각 0 · 미정 0 · 앞서 확인 1", out)
        self.assertIn("확인 누계: hunk 2/2", out)
        self.assertIn("다음: 구현이 확정됐다", out)
        self.assertIn("구현이 확정됐다", self.run_doc("--status"))            # 새 프로세스(새 세션)에서도 남아 있다

    def test_code_changed_after_confirmation_comes_back(self):
        self.write({3: "new 3"})
        out = self.run_doc(groups=[{"title": "하나", "match": ["a.txt"]}], verdicts={"g1": {"verdict": "ok", "note": ""}})
        self.assertIn("다음: 구현이 확정됐다", out)
        self.write({3: "new 3 polished"})                                  # 확인 뒤에 다듬었다
        status = self.run_doc("--status")
        self.assertIn("남은 것 1개", status)
        self.assertIn("- a.txt#1", status)
        self.write({3: "new 3", 25: "extra"})                              # 확인한 hunk 는 그대로, 새 hunk 가 생겼다
        status = self.run_doc("--status")
        self.assertIn("hunk 2개 · 확인 1개 · 남은 것 1개", status)
        self.assertIn("- a.txt#2", status)

    def test_only_key_hunks_are_judged_and_the_rest_is_recorded_as_unseen(self):
        """핵심만 확인받는다(사용자 결정 2026-11-26). 나머지는 접혀 나오고, 보지 않았다는 것이 결과와 기록에 남는다."""
        self.write({3: "new 3", 25: "renamed 25"})
        key = [{"title": "만료를 건너뛴다", "risk": "높음", "match": ["a.txt#1"]}]
        check = self.run_doc("--check", groups=key)
        self.assertIn("핵심 hunk 1개 · 판정 안 하는 나머지 1개", check)
        self.assertIn("나머지: a.txt#2", check)
        out = self.run_doc(groups=key, verdicts={"g1": {"verdict": "ok", "note": ""}})
        self.assertIn("확인 1 · 기각 0 · 미정 0 · 나머지 hunk 1개는 보지 않음", out)
        self.assertIn("확인 누계: hunk 1/1 · 나머지 1개는 보지 않음", out)
        self.assertIn("다음: 구현이 확정됐다", out)
        self.assertIn("'나머지 hunk 1개는 사용자가 보지 않음' 이라고 적는다", out)
        status = self.run_doc("--status")
        self.assertIn("hunk 2개 · 확인 1개 · 보지 않은 나머지 1개 · 남은 것 0개", status)
        self.assertIn("핵심 hunk 는 전부 확인됐다. 나머지 1개는 사용자가 보지 않았다", status)

        self.write({3: "new 3", 25: "renamed again 25"})                   # 보지 않은 hunk 가 그 뒤에 바뀌었다
        status = self.run_doc("--status")
        self.assertIn("남은 것 1개", status)
        self.assertIn("동작이 바뀌는 hunk 는 그룹에 담아 확인받는다", status)

    def test_line_range_shows_only_the_key_function_of_a_new_file(self):
        """새 파일은 hunk 하나가 파일 전체다. 줄 범위로 핵심 함수만 보이고, 그 hunk 는 '핵심 줄만 봄' 으로 적힌다."""
        (self.repo / "b.txt").write_text("\n".join(f"new {i}" for i in range(1, 201)) + "\n", encoding="utf-8", newline="\n")
        whole = self.run_doc("--check", groups=[{"title": "새 파일", "match": ["b.txt"]}])
        self.assertIn("점검: 그룹 '새 파일' 이 200줄이다 — 핵심 함수만 줄 범위로 고른다", whole)
        self.assertIn("점검: --doc 이 없다", whole)

        key = [{"title": "만료 판정", "risk": "높음", "match": ["b.txt:40-49"]}, {"title": "초기화", "match": ["b.txt:120-124"]}]
        check = self.run_doc("--check", groups=key)
        self.assertIn("핵심 그룹 2개 · 핵심 hunk 1개 · 판정 안 하는 나머지 0개 · 판정받을 줄 15", check)  # 그룹 둘이 hunk 하나를 나눠 본다
        self.assertNotIn("줄 범위로 고른다", check)
        files = diffdoc.collect(type("A", (), {"path": str(self.repo), "base": None, "patch": None, "add": [], "story": str(self.story)})())
        spec, _, errors = diffdoc.build(files, {"title": "t", "groups": key})
        self.assertEqual(errors, [])
        self.assertEqual([h["header"] for h in spec["groups"][0]["files"][0]["hunks"]], ["@@ 40–49줄 @@"])
        rest = spec["groups"][-1]
        self.assertEqual([h["header"] for h in rest["files"][0]["hunks"]], ["@@ 1–39줄 @@", "@@ 50–119줄 @@", "@@ 125–200줄 @@"])  # 빠지는 줄은 없다
        self.assertEqual((rest["fps"], rest["part_fps"], rest["skipped"]), ([], [], True))

        out = self.run_doc(groups=key, verdicts={"g1": {"verdict": "ok", "note": ""}, "g2": {"verdict": "no", "note": "이름"}})
        self.assertIn("확인 누계: hunk 0/1", out)                               # 그 hunk 를 담은 그룹이 하나라도 기각이면 본 것이 아니다
        self.assertNotIn("구현이 확정됐다", out)
        out = self.run_doc(groups=key, verdicts={"g1": {"verdict": "ok", "note": ""}, "g2": {"verdict": "ok", "note": ""}})
        self.assertIn("확인 누계: hunk 1/1 · 그 가운데 1개는 핵심 줄만 봄", out)
        self.assertIn("'hunk 1개는 핵심 줄만 확인' 도 적는다", out)
        self.assertIn("hunk 1개 · 확인 1개(핵심 줄만 본 것 1개 포함) · 남은 것 0개", self.run_doc("--status"))

        self.write({3: "new 3"})                                           # 다른 파일을 고쳐 다시 확인받아도 그 기록은 남는다
        out = self.run_doc(groups=[{"title": "a 를 고쳤다", "match": ["a.txt"]}], verdicts={"g1": {"verdict": "ok", "note": ""}})
        self.assertIn("확인 누계: hunk 2/2 · 그 가운데 1개는 핵심 줄만 봄", out)

    def test_feedback_on_the_folded_rest_reaches_the_session(self):
        self.write({3: "new 3", 25: "renamed 25"})
        key = [{"title": "만료를 건너뛴다", "match": ["a.txt#1"]}]
        out = self.run_doc(groups=key, verdicts={"g1": {"verdict": "ok", "note": ""}, "rest": {"verdict": None, "note": "25번 줄 이름이 이상하다"}})
        self.assertIn("| 2. 나머지 변경 | 판정 안 함 | 25번 줄 이름이 이상하다 |", out)
        self.assertIn("다음: 나머지 변경에 적힌 피드백을 반영한다", out)

    def test_design_doc_is_served_above_the_groups(self):
        """--doc: 설계 포인트 문서가 같은 페이지 맨 위에 실린다."""
        self.write({3: "new 3"})
        design = Path(self._td.name) / "설계.md"
        design.write_text("# 선입력 창 설계\n\n## 설계 포인트\n\n| 클래스 | 책임 |\n|---|---|\n| InputBuffer | 창 길이를 갖는다 |\n", encoding="utf-8")
        self.story.write_text(json.dumps({"title": "선입력 창", "groups": [{"title": "하나", "match": ["a.txt"]}]}, ensure_ascii=False), encoding="utf-8")
        cmd = [sys.executable, "-u", str(Path(diffdoc.__file__)), str(self.story), "--doc", str(design), "--path", str(self.repo),
               "--project", str(self.repo), "--no-open"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.repo,
                                env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace")
            if line.startswith("폼: "):
                base, token = line.split()[1].split("/?t=")
                page = http(f"{base}/?t={token}")[1]
                doc = http(f"{base}/doc?t={token}")
                self.assertEqual(http(f"{base}/submit?t={token}", {"answers": {"g": {"g1": {"verdict": "ok", "note": ""}}}})[0], 204)
                break
        proc.communicate(timeout=30)
        self.assertIn('"doc": "/doc?t=', page)
        self.assertEqual(doc[0], 200)
        self.assertIn("InputBuffer", doc[1])
        self.assertFalse(design.with_suffix(".html").exists())             # 입력 칸 없는 HTML 을 따로 남기지 않는다

    def test_missing_design_doc_stops_before_the_form(self):
        self.write({3: "new 3"})
        out = self.run_doc("--doc", str(Path(self._td.name) / "없음.md"), "--check", groups=[{"title": "하나", "match": ["a.txt"]}])
        self.assertIn("설계 문서가 없다", out)

    def test_undecided_group_is_not_confirmed(self):
        self.write({3: "new 3", 25: "new 25"})
        both = [{"title": "하나", "match": ["a.txt#1"]}, {"title": "둘", "match": ["a.txt#2"]}]
        out = self.run_doc(groups=both, verdicts={"g1": {"verdict": "ok", "note": ""}, "g2": {"verdict": None, "note": ""}})
        self.assertIn("다음: 미정 1그룹은 확인받지 못했다", out)
        self.assertNotIn("구현이 확정됐다", out)
        self.assertIn("남은 것 1개", self.run_doc("--status"))


if __name__ == "__main__":
    unittest.main()
