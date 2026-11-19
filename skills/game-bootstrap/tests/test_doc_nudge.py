#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""문서 양식 훅: 선택지를 낸 답에서만 한 번 띄우고, 고른 뒤의 답 · 무인 실행 · 꺼 둔 곳에서는 조용하다.

  python skills/game-bootstrap/tests/test_doc_nudge.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HARNESS = Path(__file__).resolve().parent.parent / "harness"
sys.path.insert(0, str(HARNESS))
import doc_nudge  # noqa: E402

OPTIONS = """한눈에: 선입력 창을 어디에 둘지 정한다.

| 선택지 | 다음 요청 때 고칠 곳 |
|---|---|
| A. 국소 패치 | 3곳 |
| B. 버퍼가 창을 갖는다 | 1곳 |

추천: B — 고칠 곳이 한 곳이다.
"""
AFTER_CHOICE = """B안으로 간다.

- A안은 버린 안에 적었다.
- B안의 검증 기준부터 쓴다.
"""
ATTENDED = {"CLAUDE_CODE_SESSION_ATTENDED": "1"}


class Detect(unittest.TestCase):
    def test_options_need_two_leading_labels_and_a_recommend_line(self):
        self.assertEqual(doc_nudge.find_options(OPTIONS), ["A", "B"])
        self.assertEqual(doc_nudge.find_options("- A안: 그대로\n- B안: 새로\n\n**추천: A안** — 싸다"), ["A", "B"])
        self.assertEqual(doc_nudge.find_options("### A) 그대로\n### B) 새로\n> 추천안: B"), ["A", "B"])

    def test_prose_about_options_is_not_options(self):
        self.assertEqual(doc_nudge.find_options(AFTER_CHOICE), [])                      # 추천 줄이 없다
        self.assertEqual(doc_nudge.find_options("A안과 B안 중 A안을 추천: 싸다"), [])    # 줄 머리 이름이 하나뿐
        self.assertEqual(doc_nudge.find_options("추천: 흐름에 붙이기\n- 문제: 외우기 어렵다"), [])
        self.assertEqual(doc_nudge.find_options("- A. 하나\n- B. 둘\n이 중에서는 추천: 없음"), [])  # 추천이 줄 머리가 아니다
        self.assertEqual(doc_nudge.find_options("API. 설명\nBUG) 설명\n추천: 없음"), [])

    def test_prompt_pointers(self):
        for prompt, skill in [("이 구현 확인받자", "diff-proto"), ("바뀐 부분 보여줘", "diff-proto"),
                              ("변경점 문서로 정리해줘", "diff-proto"), ("지금까지 결정한 것 모아줘", "collect-decision"),
                              ("결정 목록 보여줘", "collect-decision"), ("저 결정 기각할래", "reject-decision"),
                              ("결정 뒤집자", "reject-decision"), ("양식으로 고를게", "selection"),
                              ("버그 고쳐줘", "bugfix"), ("콤보가 끊기는 버그 좀 잡아줘", "bugfix"), ("고쳐줘 이 크래시", "bugfix"),
                              ("버그 고친 부분 보여줘", "diff-proto")]:
            self.assertEqual(doc_nudge.find_pointer(prompt), skill, prompt)
        for prompt in ["/selection 선입력", "버그 원인 찾아줘", "빌드 돌려줘", "프로토타입 만들어 보자", "구현해줘", "결정은 네가 해", ""]:
            self.assertIsNone(doc_nudge.find_pointer(prompt), prompt)
        self.assertIsNone(doc_nudge.find_pointer("가" * 500 + " 바뀐 부분 보여줘"))  # 붙여 넣은 긴 글의 뒤쪽


class Hook(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        t = Path(self._td.name)
        self.game, self.other = t / "Game", t / "Notes"
        self.game.mkdir()
        self.other.mkdir()
        (self.game / "Game.uproject").write_text('{"EngineAssociation": "5.7"}', encoding="utf-8")
        self.events = t / "cache" / "events.jsonl"
        p = mock.patch.dict(os.environ, {"GAME_HARNESS_EVENTS": str(self.events)})
        p.start()
        self.addCleanup(p.stop)

    def stop(self, text=OPTIONS, cwd=None, env=ATTENDED, **extra):
        data = {"hook_event_name": "Stop", "session_id": "s1", "cwd": str(cwd or self.game),
                "stop_hook_active": False, "last_assistant_message": text, "background_tasks": [], **extra}
        return doc_nudge.handle(data, env)

    def prompt(self, text, cwd=None, env=ATTENDED):
        return doc_nudge.handle({"hook_event_name": "UserPromptSubmit", "session_id": "s1",
                                 "cwd": str(cwd or self.game), "prompt": text}, env)

    def features(self):
        try:
            return [(r["feature"], r["detail"]) for r in map(json.loads, self.events.read_text(encoding="utf-8").splitlines())]
        except OSError:
            return []

    def test_form_once_then_quiet_after_the_answer(self):
        first = self.stop()
        self.assertEqual(first["decision"], "block")
        self.assertIn('scripts/decide.py" form - --project "' + self.game.resolve().as_posix() + '"', first["reason"])
        self.assertNotIn("__", first["reason"])                      # 채울 자리가 남지 않았다
        self.assertIsNone(self.stop(stop_hook_active=True))          # 양식을 띄운 차례의 끝
        self.assertIsNone(self.stop(AFTER_CHOICE))                   # 고른 뒤의 답
        self.assertEqual(self.stop()["decision"], "block")           # 다음 선택지는 다시 띄운다
        self.assertEqual([f for f, _ in self.features()], ["doc.nudge.selection", "doc.nudge.selection"])

    def test_answer_that_looks_like_options_right_after_a_form_is_skipped(self):
        self.stop()
        self.stop(stop_hook_active=True)
        self.assertIsNone(self.stop())                               # 양식 답 뒤에 선택지처럼 보이는 답
        self.assertEqual(self.features()[-1], ("doc.nudge.skip", "양식을 띄운 직후"))
        self.assertEqual(self.stop()["decision"], "block")           # 한 번만 건너뛴다

    def test_other_sessions_do_not_share_the_skip(self):
        self.stop()
        self.assertEqual(self.stop(session_id="s2")["decision"], "block")

    def test_quiet_without_options(self):
        self.assertIsNone(self.stop("고쳤다. 테스트 33개 통과."))
        self.assertEqual(self.features(), [])                        # 선택지가 없으면 기록도 없다

    def test_unattended_run_is_never_touched(self):
        for env in ({}, {"CLAUDE_CODE_SESSION_ATTENDED": "0"}):
            self.assertIsNone(self.stop(env=env))
            self.assertIsNone(self.prompt("바뀐 부분 보여줘", env=env))
        self.assertTrue(all(f == "doc.nudge.skip" and "unattended" in d for f, d in self.features()))
        self.assertEqual(self.stop(env={"GAME_HARNESS_DOC_NUDGE": "1"})["decision"], "block")  # 신호가 없는 판에서 켜기

    def test_switches(self):
        self.assertIsNone(self.stop(env={**ATTENDED, "GAME_HARNESS_DOC_NUDGE": "0"}))
        self.assertIsNone(self.stop(cwd=self.other))                 # 게임 프로젝트가 아니다
        (self.other / ".claude").mkdir()
        (self.other / ".claude" / "doc_nudge.on").write_text("", encoding="utf-8")
        self.assertEqual(self.stop(cwd=self.other, session_id="s3")["decision"], "block")
        (self.game / ".claude").mkdir()
        (self.game / ".claude" / "doc_nudge.off").write_text("", encoding="utf-8")
        self.assertIsNone(self.stop(session_id="s4"))
        sub = self.game / "Source" / "Mod"
        sub.mkdir(parents=True)
        self.assertIsNone(self.stop(cwd=sub, session_id="s5"))       # 하위 폴더에서 열어도 꺼져 있다

    def test_plan_mode_and_open_form(self):
        self.assertIsNone(self.stop(permission_mode="plan"))
        self.assertIsNone(self.stop(session_id="s6", background_tasks=[{"command": "python decide.py form x.json"}]))
        self.assertEqual([d for _, d in self.features()], ["계획 모드", "양식이 이미 떠 있음"])

    def test_form_a_skill_launched_counts_like_one_the_hook_launched(self):
        page = [{"command": "python render.py 20261119-창.md --form --project ."}]  # 구조 문서와 한 페이지로 띄운 양식
        self.assertIsNone(self.stop("양식을 띄웠다. 대화로 답해도 된다.", background_tasks=page))
        self.assertEqual(self.features(), [])                        # 선택지를 적지 않은 답 — 기록 없이 표시만 해 둔다
        self.assertIsNone(self.stop(background_tasks=page))          # 선택지를 같이 적어도 탭을 또 띄우지 않는다
        self.assertEqual(self.features()[-1], ("doc.nudge.skip", "양식이 이미 떠 있음"))
        self.assertIsNone(self.stop())                               # 답이 온 뒤의 첫 멈춤
        self.assertEqual(self.features()[-1], ("doc.nudge.skip", "양식을 띄운 직후"))
        self.assertEqual(self.stop()["decision"], "block")           # 그다음 선택지는 다시 띄운다
        plain = [{"command": "python render.py 20261119-창.md --open"}]
        self.assertEqual(self.stop(session_id="s7", background_tasks=plain)["decision"], "block")  # 문서만 연 것은 양식이 아니다

    def test_prompt_pointer(self):
        out = self.prompt("바뀐 부분 보여줘")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("diff-proto/SKILL.md", out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.prompt("빌드 돌려줘"))
        self.assertIsNone(self.prompt("바뀐 부분 보여줘", cwd=self.other))
        self.assertEqual([f for f, _ in self.features()], ["doc.nudge.diff-proto", "doc.nudge.skip"])

    def test_bug_fix_request_is_told_to_confirm_after_fixing(self):
        text = self.prompt("콤보가 끊기는 버그 고쳐줘")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("고친 뒤", text)                                # 스킬을 먼저 읽으라는 안내가 아니다 — 고치는 것이 먼저다
        self.assertIn("diff-proto/SKILL.md` 의 2~6", text)
        self.assertIn("선택지 · 추천을 내고 멈춘다", text)
        self.assertEqual(self.features()[-1][0], "doc.nudge.bugfix")
        self.assertIsNone(self.prompt("버그 고쳐줘", env={}))         # 무인 실행에는 넣지 않는다

    def run_hook(self, data, **env):
        full = {**os.environ, **ATTENDED, "GAME_HARNESS_EVENTS": str(self.events), **env}
        return subprocess.run([sys.executable, str(HARNESS / "doc_nudge.py")], input=json.dumps(data).encode("utf-8"),
                              capture_output=True, env=full, timeout=30)

    def test_process_output_is_ascii_json(self):
        r = self.run_hook({"hook_event_name": "Stop", "session_id": "p1", "cwd": str(self.game),
                           "stop_hook_active": False, "last_assistant_message": OPTIONS})
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.isascii())                          # 콘솔 코드페이지와 무관하게 읽힌다
        self.assertIn("고르기 양식", json.loads(r.stdout)["reason"])

    def test_process_never_fails(self):
        for raw in (b"", b"not json", json.dumps({"hook_event_name": "Stop"}).encode()):
            r = subprocess.run([sys.executable, str(HARNESS / "doc_nudge.py")], input=raw, capture_output=True, timeout=30)
            self.assertEqual((r.returncode, r.stdout), (0, b""))


if __name__ == "__main__":
    unittest.main()
