#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decide.py · diffdoc.py — 양식 점검, 서버 왕복(저장 · 보내기 · 토큰), 결정 장부(적기 · 기각), diff 묶기."""
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import decide  # noqa: E402
import diffdoc  # noqa: E402

WHY = {"problem": "입구가 넷이다", "dropped": ["A — 땜질"], "cost": "파일 하나가 는다", "flip": "입구가 하나로 줄면"}
SPEC = {"kind": "selection", "title": "피해 입구", "context": ["입구가 넷이다"], "questions": [
    {"id": "q1", "title": "구조는?", "why": WHY, "checks": ["선례와 같은 꼴인가", "기획자가 혼자 세팅하나"],
     "asks": [{"id": "a1", "text": "NPC 도 받나?"}],
     "options": [{"id": "A", "name": "국소 패치"}, {"id": "B", "name": "입구 하나", "recommended": True}]},
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


ANSWERS = {"q": {"q1": {"choice": "B", "rejects": {"A": "다음에 또 네 곳"}, "checks": [True, False], "asks": {"a1": "예"}, "note": "이름은 X 로"},
                 "q2": {"choice": None, "rejects": {"A": "엔진 이름과 겹친다", "B": ""}, "note": "동사로 시작하게"}}}


class LedgerFlow(unittest.TestCase):
    def test_summary_shows_choice_unchecked_items_and_replies(self):
        text = decide.selection_summary(SPEC, ANSWERS)
        self.assertIn("| 1 | 구조는? | B. 입구 하나 | 같음 | 이름은 X 로 |", text)
        self.assertIn("| 2 | 이름은? | 안 고름 | — | 동사로 시작하게 |", text)
        self.assertIn("- 1번 A. 국소 패치 — 다음에 또 네 곳", text)
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
            self.assertEqual((first["choice"], first["dropped"], first["note"]), ("B. 입구 하나", ["A. 국소 패치 — 다음에 또 네 곳"], "이름은 X 로"))
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
            decide.record_selection(spec, {"q": {"q": {"choice": "A"}}}, decide.ledger_path(d))
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
            self.assertIn("장부: D-001", out.getvalue())
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
        self.assertIn("조각 4개 · 묶은 것 2개 · 묶이지 않은 것 2개", report)
        self.assertEqual(decide.check_spec(spec)[0], [])
        text = decide.diff_summary(spec, {"g": {"g1": {"verdict": "ok", "note": "경계 확인"}, "g2": {"verdict": "no", "note": "이름을 바꿔라"}}})
        self.assertIn("확인 1 · 기각 1 · 미정 1", text)
        self.assertIn("| 1. 버퍼 규칙을 한 곳으로 | 확인함 | 경계 확인 |", text)
        self.assertIn("| 2. 새 타입 | 기각 | 이름을 바꿔라 |", text)
        self.assertIn("| 3. 묶이지 않은 변경 | 미정 |  |", text)

    def test_story_pointing_outside_the_diff_is_an_error(self):
        story = {"title": "t", "groups": [{"title": "없는 변경", "match": ["Src/Ghost.cpp"]}, {"title": "", "match": ["x"]},
                                          {"title": "위험 오타", "risk": "큼", "match": ["Src/New.h"]}]}
        _, _, errors = diffdoc.build(diffdoc.parse_diff(GIT_DIFF), story)
        joined = "\n".join(errors)
        for needle in ("diff 에 없는 것을 가리킨다 — Src/Ghost.cpp", "묶음 2: title 이 없다", "risk 는 높음 · 중간 · 낮음"):
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
            self.assertIn("묶은 것 2개 · 묶이지 않은 것 0개", out.getvalue())

    def test_mixed_encoding_diff_is_decoded_line_by_line(self):
        raw = "Index: 소스/효과.cpp\n".encode("cp949") + "+// 피해 입구\n".encode("utf-8")
        self.assertEqual(diffdoc.decode(raw), "Index: 소스/효과.cpp\n+// 피해 입구\n")


if __name__ == "__main__":
    unittest.main()
