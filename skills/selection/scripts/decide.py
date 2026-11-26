#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""고르는 폼과 결정 로그. 스킬 selection · collect-decision · reject-decision · diff-proto 가 같이 쓴다.

  python decide.py form <폼.json> [--project <루트>] [--keep] [--no-record] [--no-open] [--timeout <분>] [--static]
  python decide.py form - [--project <루트>]      폼 JSON 을 표준 입력으로 준다 (파일을 따로 쓰지 않는다)
  python decide.py done <폼.json> [--project <루트>] [--keep] [--no-record]
  python decide.py add --topic <주제> --choice <고른 것> [--question <질문>] [--dropped <버린 안> …] [--note <메모>]
  python decide.py list [--all]
  python decide.py collect [--print]
  python decide.py reject [--id D-003 --reason <이유>]

form 은 페이지를 메모리에서 내보낸다. HTML 파일을 남기지 않는다.
문서가 딸린 폼(game-architecture 의 `render.py --form`)은 같은 페이지 위쪽에 그 문서를 싣는다 — 읽는 곳과 고르는 곳이 한 탭이다.
사용자가 Enter 로 보내면 답을 표준 출력에 찍고, 선택 폼이면 '남김' 표시한 결정을 결정 로그에 적고, 폼 파일을 지우고 끝난다. 탭은 페이지가 스스로 닫는다.
그래서 이 명령을 백그라운드로 돌리면 사용자가 보낸 순간 답이 부른 세션으로 돌아온다.
--static 은 서버를 못 띄울 때만 쓴다: HTML 을 폼 옆에 쓰고, 사용자가 복사한 답을 <폼>.answers.json 에 저장한 뒤 done 을 돌린다.

결정 로그는 <프로젝트>/.claude/decisions.jsonl 이다. 덧붙이기만 한다 — 기각은 옛 줄을 고치지 않고 '기각' 줄을 더한다.
exit code: 0 보냄 · 1 폼 오류 · 2 보내지 않고 닫음 · 3 시간 초과 · 4 헤드리스 실행이라 띄우지 않음.

헤드리스 실행(CLAUDE_CODE_SESSION_ATTENDED=0 — `claude -p` · 릴레이 직원)에서는 폼을 띄우지 않는다. 받을 사람이 없어 명령이 끝나지 않는다.
  GAME_HARNESS_DOC_NUDGE=0   어디서든 띄우지 않는다
  GAME_HARNESS_DOC_NUDGE=1   헤드리스 실행 신호가 있어도 띄운다 (테스트)
"""

import argparse
import html
import json
import os
import re
import secrets
import sys
import tempfile
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

for _s in (sys.stdout, sys.stderr):  # 한글 Windows 콘솔(cp949)에서 '—' 를 못 찍어 죽는다
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

PAGE = Path(__file__).resolve().parent / "page.html"
ID_OK = re.compile(r"^[A-Za-z0-9_-]+$")
LONG = 120           # 한 줄에 사실 하나 (docs/READING.md)
MAX_QUESTIONS = 5    # 한 번에 묻는 수. 넘으면 다음 폼으로
MAX_OPTIONS = 4
MAX_CHECKS = 7
CLOSE_GRACE = 3.0    # 탭이 닫힌 뒤 이만큼 기다린다 — 새로 고침이면 그 사이에 다시 온다
UNATTENDED = 4       # exit code: 헤드리스 실행이라 띄우지 않았다
SWITCH, ATTENDED = "GAME_HARNESS_DOC_NUDGE", "CLAUDE_CODE_SESSION_ATTENDED"  # 훅 doc_nudge.py 와 같은 스위치
ASSET_TYPES = {".js": "text/javascript", ".html": "text/html", ".svg": "image/svg+xml", ".css": "text/css",
               ".png": "image/png", ".json": "application/json"}
BLOCKED = {"selection": "선택지와 추천은 답에 글로 내고 멈춘다. 고른 것으로 치고 진행하지 않는다.",
           "diff": "사용자 확인 단계를 건너뛴다. 결과에 '구현 확인 안 받음 — 헤드리스 실행' 이라고 적는다.",
           "review": "문서 확인 단계를 건너뛴다. 결과에 '문서 확인 안 받음 — 헤드리스 실행' 이라고 적는다.",
           "ledger": "표만 보려면 `decide.py list` 를 쓴다."}
WHY = (("problem", "문제"), ("dropped", "버린 안"), ("cost", "대가"), ("flip", "뒤집는 조건"))


# ── 폼 점검 ──────────────────────────────────────────────────────────────

def _ids_ok(ids):
    return len(set(ids)) == len(ids) and all(ID_OK.match(i) for i in ids)


def check_spec(spec):
    """→ (오류, 경고). 오류가 있으면 폼을 띄우지 않는다."""
    errors, warns = [], []
    kind = spec.get("kind")
    if kind not in ("selection", "diff", "ledger", "review"):
        return [f"kind 가 selection · diff · ledger · review 가 아니다: {kind!r}"], warns
    if not str(spec.get("title") or "").strip():
        errors.append("title 이 없다")
    if len(spec.get("context") or []) > 3:
        warns.append("context 는 3줄 이하로 쓴다")
    if kind == "review":
        docs = spec.get("docs") or []
        if not docs:
            errors.append("docs 가 비었다")
        if any(not d.get("sections") for d in docs):
            errors.append("sections 가 없는 문서가 있다")
        if not _ids_ok([str(s.get("id") or "") for d in docs for s in d.get("sections") or []]):
            errors.append("절의 id 가 비었거나 겹친다")
        return errors, warns
    if kind != "selection":
        return errors, warns
    questions = spec.get("questions") or []
    if not questions:
        errors.append("questions 가 비었다")
    if len(questions) > MAX_QUESTIONS:
        warns.append(f"질문 {len(questions)}개 — {MAX_QUESTIONS}개 이하로 줄이고 나머지는 다음 폼으로")
    if not _ids_ok([str(q.get("id") or "") for q in questions]):
        errors.append("질문 id 가 없거나 겹치거나 영문 · 숫자 · - · _ 가 아니다")
    for i, q in enumerate(questions, 1):
        if not str(q.get("title") or "").strip():
            errors.append(f"질문 {i}: title 이 없다")
        options = q.get("options") or []
        if len(options) < 2:
            errors.append(f"질문 {i}: 선택지가 2개보다 적다")
        if len(options) > MAX_OPTIONS:
            warns.append(f"질문 {i}: 선택지 {len(options)}개 — {MAX_OPTIONS}개 이하")
        option_ids = [str(o.get("id") or "") for o in options]
        if not _ids_ok(option_ids) or any(not str(o.get("name") or "").strip() for o in options):
            errors.append(f"질문 {i}: 선택지 id 나 name 이 없거나 겹친다")
        recommended = [o for o in options if o.get("recommended")]
        if len(recommended) > 1:
            errors.append(f"질문 {i}: 추천이 둘 이상이다")
        if not recommended:
            warns.append(f"질문 {i}: 추천이 없다")
        elif any(not (q.get("why") or {}).get(key) for key, _ in WHY):
            warns.append(f"질문 {i}: 추천의 왜 네 칸(문제 · 버린 안 · 대가 · 뒤집는 조건)이 비었다")
        if len(q.get("checks") or []) > MAX_CHECKS:
            warns.append(f"질문 {i}: 체크 {len(q['checks'])}개 — {MAX_CHECKS}개 이하")
        if not _ids_ok([str(k.get("id") or "") for k in q.get("asks") or []]):
            errors.append(f"질문 {i}: asks 의 id 가 없거나 겹친다")
        texts = [q.get("title"), q.get("changes"), *(q.get("checks") or []), *(k.get("text") for k in q.get("asks") or [])]
        for o in options:
            texts += [o.get("name"), o.get("summary"), o.get("next"), o.get("gain"), o.get("loss")]
        long = sum(1 for t in texts if len(str(t or "")) > LONG)
        if long:
            warns.append(f"질문 {i}: {LONG}자 넘는 줄 {long}개 — 한 줄에 사실 하나")
    return errors, warns


# ── 헤드리스 실행 ──────────────────────────────────────────────────────────────

def unattended(env=None):
    """폼을 받을 사람이 없는 실행이면 그 이유, 아니면 ''. 신호가 0 일 때만 막는다 — 신호가 없는 판(터미널 · IDE)은 띄운다."""
    env = os.environ if env is None else env
    switch = env.get(SWITCH, "")
    if switch == "1":
        return ""
    if switch == "0":
        return f"{SWITCH}=0"
    return f"{ATTENDED}=0" if env.get(ATTENDED) == "0" else ""


def blocked(kind, env=None):
    """헤드리스 실행이면 대신 할 일을 찍고 True."""
    why = unattended(env)
    if why:
        what = "diff-proto 페이지를" if kind == "diff" else "폼을"
        print(f"{what} 띄우지 않았다 — 헤드리스 실행이다({why}).\n다음: {BLOCKED.get(kind, BLOCKED['selection'])}")
    return bool(why)


# ── 페이지 · 서버 ──────────────────────────────────────────────────────────

def build_page(spec, state, token, served, name, doc=None, docs=None):
    """doc: 같은 페이지 위쪽에 실을 문서의 주소. 없으면 폼만 나온다. docs: 문서 확인 페이지가 싣는 문서들의 주소."""
    boot = json.dumps({"spec": spec, "state": state, "token": token, "served": served, "name": name, "doc": doc, "docs": docs or []},
                      ensure_ascii=False)
    for bad, safe in (("</", "<\\/"), ("<!--", "<\\!--"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        boot = boot.replace(bad, safe)  # <script> 안에서 끊기지 않게
    page = PAGE.read_text(encoding="utf-8").replace("__TITLE__", html.escape(str(spec.get("title") or "")))
    return page.replace("__BOOT__", boot)


def answers_path(spec_path):
    p = Path(spec_path)
    return p.with_name(p.stem + ".answers.json")


def read_answers(path):
    """저장된 답. 서버가 쓴 꼴({"answers": …})과 사용자가 붙여 준 꼴(답만) 둘 다 읽는다."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("answers", data) if isinstance(data, dict) else None


def write_answers(path, answers, submitted):
    body = {"saved_at": datetime.now().isoformat(timespec="seconds"), "submitted": submitted, "answers": answers}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def serve(spec, save_to, timeout_min=120, open_browser=True, port=0, on_ready=None, doc=None):
    """폼을 127.0.0.1 에서 내보내고 보낼 때까지 기다린다. → (끝 종류, 답). 끝 종류: submitted · closed · timeout.
    주소의 토큰이 없으면 페이지도 저장도 거절한다 — 다른 웹 페이지가 이 포트로 읽거나 쓰지 못한다.
    doc 은 같은 페이지에 실을 문서를 만드는 함수다: doc(url_for) → HTML. url_for(파일) 은 그 파일을 이 서버에서 읽는 주소를 준다
    (문서가 쓰는 스크립트 · 그림 — http 페이지는 file:// 을 못 읽는다)."""
    token = secrets.token_urlsafe(16)
    state = {"end": None, "answers": read_answers(save_to), "bye": None, "last": time.time()}
    name = Path(save_to).name
    assets = {}

    def url_for(path):
        key = f"{len(assets)}-{Path(path).name}"
        assets[key] = Path(path)
        return f"/a/{quote(key)}?t={token}"

    makers = list(doc) if isinstance(doc, (list, tuple)) else [doc] if doc else []
    doc_pages = [make(url_for) for make in makers]
    doc_html = doc_pages[0] if doc_pages else None
    doc_urls = [f"/doc/{i}?t={token}" for i in range(len(doc_pages))]
    doc_url = f"/doc?t={token}" if doc_html and spec.get("kind") != "review" else None  # 문서 확인 페이지는 문서를 여럿 싣는다

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, body=b"", ctype="text/plain; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            url = urlparse(self.path)
            return url.path if parse_qs(url.query).get("t", [""])[0] == token else None

        def do_GET(self):
            path = self.allowed()
            if path is None:
                return self.reply(403)
            if path == "/doc" and doc_html:
                return self.reply(200, doc_html.encode("utf-8"), "text/html; charset=utf-8")
            if path.startswith("/doc/") and path[5:].isdigit() and int(path[5:]) < len(doc_pages):
                return self.reply(200, doc_pages[int(path[5:])].encode("utf-8"), "text/html; charset=utf-8")
            if path.startswith("/a/"):
                asset = assets.get(unquote(path[3:]))
                try:
                    body = asset.read_bytes()
                except (AttributeError, OSError):
                    return self.reply(404)
                ctype = ASSET_TYPES.get(asset.suffix.lower(), "application/octet-stream")
                return self.reply(200, body, ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
            if path != "/":
                return self.reply(404)
            state["bye"], state["last"] = None, time.time()
            self.reply(200, build_page(spec, state["answers"], token, True, name, doc_url, doc_urls).encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self):
            path = self.allowed()
            if path is None:
                return self.reply(403)
            state["last"] = time.time()
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path == "/bye":
                state["bye"] = time.time()
                return self.reply(204)
            if path not in ("/save", "/submit"):
                return self.reply(404)
            try:
                answers = json.loads(raw.decode("utf-8"))["answers"]
            except (ValueError, KeyError, TypeError):
                return self.reply(400)
            if not isinstance(answers, dict):
                return self.reply(400)
            state["answers"] = answers
            write_answers(save_to, answers, submitted=path == "/submit")
            if path == "/submit":
                state["end"] = "submitted"
            self.reply(204)

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 0.3
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={token}"
    print(f"폼: {url}\n브라우저에서 고르고 Enter 로 보낸다. 보내면 이 명령이 답을 찍고 끝난다.", flush=True)
    if open_browser:
        webbrowser.open(url)
    if on_ready:
        on_ready(url)
    try:
        while state["end"] is None:
            server.handle_request()
            now = time.time()
            if state["bye"] and now - state["bye"] > CLOSE_GRACE:
                state["end"] = "closed"
            elif now - state["last"] > timeout_min * 60:
                state["end"] = "timeout"
    except KeyboardInterrupt:
        state["end"] = "closed"
    finally:
        server.server_close()
    return state["end"], state["answers"] or {}


# ── 답 요약 ────────────────────────────────────────────────────────────────

def cell(text):
    return str(text or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def option_label(question, choice):
    for o in question.get("options") or []:
        if o["id"] == choice:
            return f"{o['id']}. {o['name']}"
    return None


def rejected_options(question, answer):
    """→ [(안 이름, 이유)]. 사용자가 이유를 적어 기각한 안."""
    rejects = answer.get("rejects") or {}
    return [(f"{o['id']}. {o['name']}", str(rejects[o["id"]] or "").strip()) for o in question.get("options") or [] if o["id"] in rejects]


def selection_summary(spec, answers):
    given = answers.get("q") or {}
    lines = [f"제출됨 — {spec['title']}", "", "| # | 질문 | 고른 안 | 추천과 | 피드백 |", "|---|---|---|---|---|"]
    unchecked, replies, rejects = [], [], []
    for i, q in enumerate(spec["questions"], 1):
        a = given.get(q["id"]) or {}
        label = option_label(q, a.get("choice"))
        rejects += [f"- {i}번 {name} — {why or '(이유 없음)'}" for name, why in rejected_options(q, a)]
        recommended = next((o["id"] for o in q.get("options") or [] if o.get("recommended")), None)
        if label is None or recommended is None:
            same = "—"
        else:
            same = "같음" if a.get("choice") == recommended else f"다름 (추천 {recommended})"
        lines.append(f"| {i} | {cell(q['title'])} | {cell(label or '안 고름')} | {same} | {cell(a.get('note'))} |")
        ticks = a.get("checks") or []
        unchecked += [f"- {i}번: {c}" for j, c in enumerate(q.get("checks") or []) if not (j < len(ticks) and ticks[j])]
        for k in q.get("asks") or []:
            reply = str((a.get("asks") or {}).get(k["id"]) or "").strip()
            replies.append(f"- {i}번 · {k['text']} → {reply or '(답 없음)'}")
    if rejects:
        lines += ["", "기각한 안 (다시 내지 않는다. 고른 안이 없는 질문은 이 이유를 반영해 선택지를 다시 낸다):"] + rejects
    if unchecked:
        lines += ["", "체크하지 않은 것:"] + unchecked
    if replies:
        lines += ["", "적은 답:"] + replies
    return "\n".join(lines)


VERDICTS = {"ok": "확인함", "no": "기각"}


KEPT_MARK = "앞서 확인"
SKIP_MARK = "판정 안 함"   # 접혀 나온 나머지 변경 — 사용자는 핵심만 확인한다


def _mark(g, given):
    if g.get("locked"):
        return KEPT_MARK

    if g.get("skipped"):
        return SKIP_MARK

    return VERDICTS.get((given.get(g["id"]) or {}).get("verdict"), "미정")


def diff_marks(spec, answers):
    given = answers.get("g") or {}
    return [_mark(g, given) for g in spec["groups"]]


def skipped_fps(spec):
    return sorted({fp for g in spec["groups"] if g.get("skipped") for fp in g.get("fps") or []})


def diff_summary(spec, answers):
    given = answers.get("g") or {}
    marks = diff_marks(spec, answers)
    count = marks.count
    kept = f" · 앞서 확인 {count(KEPT_MARK)}" if count(KEPT_MARK) else ""
    unseen = f" · 나머지 hunk {len(skipped_fps(spec))}개는 보지 않음" if count(SKIP_MARK) else ""
    lines = [f"검토 제출됨 — {spec['title']}", f"확인 {count('확인함')} · 기각 {count('기각')} · 미정 {count('미정')}{kept}{unseen}", "",
             "| 그룹 | 판정 | 피드백 |", "|---|---|---|"]
    for i, (g, mark) in enumerate(zip(spec["groups"], marks), 1):
        lines.append(f"| {i}. {cell(g['title'])} | {mark} | {cell((given.get(g['id']) or {}).get('note'))} |")
    return "\n".join(lines)


# ── 문서 확인 ──────────────────────────────────────────────────────────────
# 고를 것이 없는 보고 문서도 절마다 판정과 피드백을 받는다(사용자 결정 2026-11-26). 입력 칸 없는 문서는 답을 따로 적어 보내야 해서 검수가 느리다.
REVIEW_VERDICTS = {"ok": "확인함", "no": "다시"}
UNSEEN = "안 봄"


def review_summary(spec, answers):
    given = answers.get("s") or {}
    rows, marks, noted = [], [], False
    for d in spec["docs"]:
        for s in d["sections"]:
            a = given.get(s["id"]) or {}
            mark = REVIEW_VERDICTS.get(a.get("verdict"), UNSEEN)
            marks.append(mark)
            noted = noted or (mark != "다시" and bool(str(a.get("note") or "").strip()))
            rows.append(f"| {cell(d.get('title'))} | {cell(s.get('title'))} | {mark} | {cell(a.get('note'))} |")
    count = marks.count
    lines = [f"검토 제출됨 — {spec['title']}", f"확인 {count('확인함')} · 다시 {count('다시')} · 안 봄 {count(UNSEEN)}", "",
             "| 문서 | 절 | 판정 | 피드백 |", "|---|---|---|---|", *rows, ""]
    if count("다시"):
        lines.append("다음: '다시' 인 절을 피드백대로 고친다. 고친 문서를 같은 명령으로 다시 띄운다.")
    if noted:
        lines.append("다음: '다시' 가 아닌 절에 적힌 피드백도 반영한다.")
    if count(UNSEEN):
        lines.append(f"다음: 안 본 절 {count(UNSEEN)}개는 확인받지 못했다. 확인받은 것으로 치지 않는다.")
    if not count("다시") and not count(UNSEEN):
        lines.append("다음: 문서가 전부 확인됐다.")
    return "\n".join(lines)


# ── 구현 확인 기록 ─────────────────────────────────────────────────────────
# diff-proto 페이지에서 '확인함' 을 받은 hunk 의 해시를 적어 둔다. 다음 차례에는 그 hunk 를 다시 묻지 않고,
# 그 뒤로 바뀐 hunk 는 해시가 달라져 다시 나온다 — 적용되는 코드는 확인받은 코드와 같아야 한다.

def confirmed_path(project):
    return Path(project) / ".claude" / "diff_confirmed.json"


def _load_fps(project, key):
    try:
        return set(json.loads(confirmed_path(project).read_text(encoding="utf-8")).get(key) or [])
    except (OSError, ValueError, AttributeError):
        return set()


def load_confirmed(project):
    return _load_fps(project, "fps")


def load_skipped(project):
    """접혀 나와 사용자가 판정하지 않은 hunk 의 해시."""
    return _load_fps(project, "skipped")


def confirm_diff(spec, answers, project):
    """확인받은 hunk 를 기록하고 다음에 할 일을 돌려준다. 기록은 지금 diff 에 있는 hunk 만 남긴다."""
    marks = diff_marks(spec, answers)
    units = [fp for g in spec["groups"] for fp in g.get("fps") or []]
    done = sorted({fp for g, mark in zip(spec["groups"], marks) if mark in ("확인함", KEPT_MARK) for fp in g.get("fps") or []})
    skipped = [fp for fp in skipped_fps(spec) if fp not in done]
    path = confirmed_path(project)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"updated": today(), "title": spec.get("title", ""), "fps": done, "skipped": skipped}
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        return f"확인 기록을 못 썼다: {e}"
    lines = [f"확인 누계: hunk {len(done)}/{len(units) - len(skipped)}" + (f" · 나머지 {len(skipped)}개는 보지 않음" if skipped else "")]
    given = answers.get("g") or {}
    if any(g.get("skipped") and str((given.get(g["id"]) or {}).get("note") or "").strip() for g in spec["groups"]):
        lines.append("다음: 나머지 변경에 적힌 피드백을 반영한다. 반영해서 바뀐 hunk 는 그룹에 담아 확인받는다.")
    if marks.count("기각"):
        lines.append("다음: 기각한 그룹을 피드백대로 고친다. 고친 hunk 만 이야기에 담아 같은 명령으로 다시 띄운다. "
                     "확인받은 hunk 는 다시 묻지 않는다(고치다 바뀌면 다시 나온다).")
    if marks.count("미정"):
        lines.append(f"다음: 미정 {marks.count('미정')}그룹은 확인받지 못했다. 그 그룹을 다시 띄운다. 확인받은 것으로 치지 않는다.")
    if len(done) + len(skipped) == len(units):
        lines.append("다음: 구현이 확정됐다. 코드를 다시 쓰지 않는다. 이 뒤에 코드를 바꾸면 바뀐 hunk 만 다시 확인받는다."
                     + (f" 결과에 '나머지 hunk {len(skipped)}개는 사용자가 보지 않음' 이라고 적는다." if skipped else ""))
    return "\n".join(lines)


# ── 결정 로그 ──────────────────────────────────────────────────────────────

def ledger_path(project):
    return Path(project) / ".claude" / "decisions.jsonl"


def today():
    return datetime.now().strftime("%Y-%m-%d")


def load_events(path):
    events = []
    if not Path(path).is_file():
        return events
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            print(f"결정 로그 {n}번째 줄을 못 읽어 건너뛴다: {path}", file=sys.stderr)
    return events


def append_event(path, event):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def next_id(events):
    numbers = [int(m.group(1)) for e in events if e.get("type") == "decision" for m in [re.match(r"D-(\d+)$", str(e.get("id")))] if m]
    return f"D-{max(numbers, default=0) + 1:03d}"


def split_ledger(events):
    """→ (유효한 결정, 기각된 결정). 기각된 결정에는 reason · reject_date 가 붙는다."""
    rejects = {e.get("target"): e for e in events if e.get("type") == "reject"}
    live, dead = [], []
    for e in events:
        if e.get("type") != "decision":
            continue
        r = rejects.get(e.get("id"))
        if r:
            dead.append(dict(e, reason=r.get("reason") or "", reject_date=r.get("date") or ""))
        else:
            live.append(e)
    return live, dead


def add_decision(path, topic, choice, question="", dropped=(), note="", answers=()):
    events = load_events(path)
    event = {"type": "decision", "id": next_id(events), "date": today(), "topic": topic, "question": question,
             "choice": choice, "dropped": list(dropped), "note": note}
    if answers:
        event["answers"] = list(answers)
    append_event(path, event)
    return event["id"]


def record_selection(spec, answers, path):
    """사용자가 '결정 로그에 남긴다' 를 표시하고 고른 질문만 적는다. 고른 것을 전부 적으면 사소한 선택이 쌓여 읽지 않는 목록이 된다.
    안 고른 질문은 결정이 아니다 — 기각만 한 질문은 선택지를 다시 낼 재료다.
    버린 안에는 사용자가 적은 기각 이유와 앞 폼에서 기각한 안(dropped_before)이 붙는다."""
    ids = []
    for q in spec["questions"]:
        a = (answers.get("q") or {}).get(q["id"]) or {}
        label = option_label(q, a.get("choice"))
        if label is None or not a.get("keep"):
            continue
        why = dict(rejected_options(q, a))
        dropped = [name + (f" — {why[name]}" if why.get(name) else "")
                   for name in (f"{o['id']}. {o['name']}" for o in q.get("options") or [] if o["id"] != a.get("choice"))]
        dropped += [str(d) for d in q.get("dropped_before") or []]
        replies = [{"q": k["text"], "a": str((a.get("asks") or {}).get(k["id"]) or "").strip()} for k in q.get("asks") or []]
        ids.append(add_decision(path, spec["title"], label, q["title"], dropped, str(a.get("note") or "").strip(),
                                [r for r in replies if r["a"]]))
    return ids


def reject_decisions(path, pairs):
    """pairs: [(번호, 이유)]. → (기각한 번호, 건너뛴 이유). 유효한 결정만, 이유가 있을 때만 기각한다."""
    live = {e["id"] for e in split_ledger(load_events(path))[0]}
    done, skipped = [], []
    for target, reason in pairs:
        reason = str(reason or "").strip()
        if target not in live:
            skipped.append(f"{target}: 유효한 결정이 아니다")
        elif not reason:
            skipped.append(f"{target}: 이유가 없다")
        else:
            append_event(path, {"type": "reject", "target": target, "date": today(), "reason": reason})
            live.discard(target)
            done.append(target)
    return done, skipped


def ledger_table(path, show_dead=False):
    live, dead = split_ledger(load_events(path))
    lines = ["| 번호 | 날짜 | 주제 | 결정 | 버린 안 | 메모 |", "|---|---|---|---|---|---|"]
    lines += [f"| {e['id']} | {e.get('date', '')} | {cell(e.get('topic'))} | {cell(e.get('choice'))} | "
              f"{cell(' · '.join(e.get('dropped') or []))} | {cell(e.get('note'))} |" for e in live]
    if show_dead and dead:
        lines += ["", "기각된 결정:", "| 번호 | 주제 | 결정 | 기각한 이유 | 기각한 날 |", "|---|---|---|---|---|"]
        lines += [f"| {e['id']} | {cell(e.get('topic'))} | {cell(e.get('choice'))} | {cell(e['reason'])} | {e['reject_date']} |" for e in dead]
    lines += ["", f"유효 {len(live)}건 · 기각 {len(dead)}건 — {path}"]
    return "\n".join(lines)


def ledger_spec(path, mode):
    live, dead = split_ledger(load_events(path))
    title = "기각할 결정 고르기" if mode == "reject" else "결정 모음"
    context = [f"유효 {len(live)}건 · 기각 {len(dead)}건"]
    if mode == "reject":
        context.append("기각할 결정에 이유를 한 줄 적는다. 옛 결정은 지우지 않고 기각으로 남는다.")
    return {"kind": "ledger", "mode": mode, "title": title, "context": context, "live": live, "dead": dead}


# ── 끝내기 ─────────────────────────────────────────────────────────────────

def cleanup(spec_path):
    p = Path(spec_path)
    for f in (p, answers_path(p), p.with_suffix(".html")):
        try:
            f.unlink()
        except OSError:
            pass


def finish(spec, answers, project, record=True):
    """보낸 답을 찍고, 종류에 맞게 결정 로그를 고친다."""
    ledger = ledger_path(project)
    if spec["kind"] == "selection":
        print(selection_summary(spec, answers))
        ids = record_selection(spec, answers, ledger) if record else []
        if ids:
            print(f"\n결정 로그: {' · '.join(ids)} — {ledger}")
        elif record:
            print("\n결정 로그: 남김 표시한 결정이 없어 적지 않았다")
    elif spec["kind"] == "diff":
        print(diff_summary(spec, answers))
        if any(g.get("fps") for g in spec["groups"]):
            print("\n" + confirm_diff(spec, answers, project))
    elif spec["kind"] == "review":
        print(review_summary(spec, answers))
    elif spec.get("mode") == "reject":
        picked = [(target, a.get("reason")) for target, a in (answers.get("r") or {}).items() if a.get("reject")]
        done, skipped = reject_decisions(ledger, picked)
        print(f"기각 {len(done)}건" + (f": {' · '.join(done)}" if done else ""))
        for s in skipped:
            print(f"건너뜀 — {s}")
        print(ledger_table(ledger).splitlines()[-1])
    else:
        print("닫았다.")
        print(ledger_table(ledger))


def run_form(spec, spec_path, save_to, args, record=True, doc=None):
    """폼을 띄우고 exit code 를 돌려준다. spec_path 가 있으면 보낸 뒤 폼 파일을 지운다. 헤드리스 실행이면 띄우지 않는다."""
    if blocked(spec["kind"]):
        return UNATTENDED
    kind, answers = serve(spec, save_to, args.timeout, not args.no_open, doc=doc)
    if kind != "submitted":
        why = "보내지 않고 닫았다" if kind == "closed" else f"{args.timeout}분 동안 움직임이 없어 닫았다"
        saved = f" 지금까지 답은 {save_to} 에 있다." if Path(save_to).is_file() else ""
        print(f"{why}.{saved} 다시 열려면 같은 명령을 돌린다.")
        return 2 if kind == "closed" else 3
    finish(spec, answers, args.project, record)
    if spec_path and not args.keep:
        cleanup(spec_path)
    elif not spec_path:
        try:
            Path(save_to).unlink()
        except OSError:
            pass
    return 0


def load_spec(path):
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"폼을 못 읽었다: {path}\n{e}")
    errors, warns = check_spec(spec)
    for w in warns:
        print(f"점검: {w}")
    if errors:
        raise SystemExit("폼 오류:\n" + "\n".join(f"- {e}" for e in errors))
    return spec


def spec_from_stdin():
    """`form -`: 표준 입력의 폼 JSON 을 임시 폴더에 두고 그 경로를 준다. 보내면 다른 폼처럼 지워진다.
    모델이 폼 파일을 따로 쓰지 않아도 되고, 프로젝트의 `.claude/` 아래에 쓰느라 권한을 묻지도 않는다."""
    raw = sys.stdin.buffer.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949", "replace")
    folder = Path(tempfile.gettempdir()) / "claude-decide"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.json"
    path.write_text(text, encoding="utf-8")
    return str(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["form", "done", "add", "list", "collect", "reject"])
    ap.add_argument("spec", nargs="?", help="form · done: 폼 JSON. form 은 `-` 면 표준 입력에서 읽는다")
    ap.add_argument("--project", default=".", help="프로젝트 루트. 결정 로그는 그 아래 .claude/decisions.jsonl")
    ap.add_argument("--keep", action="store_true", help="보낸 뒤에도 폼 · 답 파일을 지우지 않는다")
    ap.add_argument("--no-record", action="store_true", help="고른 것을 결정 로그에 적지 않는다")
    ap.add_argument("--no-open", action="store_true", help="브라우저를 열지 않고 주소만 찍는다")
    ap.add_argument("--timeout", type=int, default=120, help="움직임이 없으면 닫는 시간(분)")
    ap.add_argument("--static", action="store_true", help="form: 서버 없이 HTML 파일로 쓴다")
    ap.add_argument("--topic")
    ap.add_argument("--question", default="")
    ap.add_argument("--choice")
    ap.add_argument("--dropped", action="append", default=[])
    ap.add_argument("--note", default="")
    ap.add_argument("--all", action="store_true", help="list: 기각된 결정도 보인다")
    ap.add_argument("--print", action="store_true", dest="print_only", help="collect: 페이지 없이 표만 찍는다")
    ap.add_argument("--id", action="append", default=[], help="reject: 기각할 번호")
    ap.add_argument("--reason", default="")
    args = ap.parse_args(argv)
    ledger = ledger_path(args.project)

    if args.command in ("form", "done"):
        if not args.spec:
            ap.error("폼 JSON 경로가 필요하다")
        piped = args.command == "form" and args.spec == "-"
        if piped:
            args.spec = spec_from_stdin()
        try:
            spec = load_spec(args.spec)
        except SystemExit:
            if piped:
                cleanup(args.spec)
            raise
        save_to = answers_path(args.spec)
        if args.command == "form" and blocked(spec["kind"]):
            if piped:
                cleanup(args.spec)
            return UNATTENDED
        if args.command == "done":
            answers = read_answers(save_to)
            if answers is None:
                raise SystemExit(f"답이 없다: {save_to}")
            finish(spec, answers, args.project, not args.no_record)
            if not args.keep:
                cleanup(args.spec)
            return 0
        if args.static:
            out = Path(args.spec).with_suffix(".html")
            out.write_text(build_page(spec, read_answers(save_to), "", False, save_to.name), encoding="utf-8")
            print(f"폼 파일: {out}\n사용자가 Enter 로 복사한 답을 받으면 {save_to} 에 저장하고 `decide.py done {args.spec}` 를 돌린다.")
            if not args.no_open:
                webbrowser.open(out.resolve().as_uri())
            return 0
        return run_form(spec, args.spec, save_to, args, not args.no_record)

    if args.command == "add":
        if not args.topic or not args.choice:
            ap.error("add 는 --topic 과 --choice 가 필요하다")
        print(f"{add_decision(ledger, args.topic, args.choice, args.question, args.dropped, args.note)} — {ledger}")
        return 0

    if args.command == "list":
        print(ledger_table(ledger, args.all))
        return 0

    if args.command == "reject" and args.id:
        done, skipped = reject_decisions(ledger, [(i, args.reason) for i in args.id])
        print(f"기각 {len(done)}건" + (f": {' · '.join(done)}" if done else ""))
        for s in skipped:
            print(f"건너뜀 — {s}")
        return 0 if done and not skipped else 1

    mode = "reject" if args.command == "reject" else "collect"
    if args.print_only or (mode == "reject" and not split_ledger(load_events(ledger))[0]):
        print(ledger_table(ledger, True))
        return 0
    return run_form(ledger_spec(ledger, mode), None, ledger.with_name("decisions.form.answers.json"), args)


if __name__ == "__main__":
    sys.exit(main())
