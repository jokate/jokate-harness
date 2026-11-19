#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""고르는 양식과 결정 장부. 스킬 selection · collect-decision · reject-decision · diff-proto 가 같이 쓴다.

  python decide.py form <양식.json> [--project <루트>] [--keep] [--no-record] [--no-open] [--timeout <분>] [--static]
  python decide.py done <양식.json> [--project <루트>] [--keep] [--no-record]
  python decide.py add --topic <주제> --choice <고른 것> [--question <질문>] [--dropped <버린 안> …] [--note <메모>]
  python decide.py list [--all]
  python decide.py collect [--print]
  python decide.py reject [--id D-003 --reason <이유>]

form 은 페이지를 메모리에서 내보낸다. HTML 파일을 남기지 않는다.
사용자가 Enter 로 보내면 답을 표준 출력에 찍고, 고르기 양식이면 '남김' 표시한 결정을 장부에 적고, 양식 파일을 지우고 끝난다. 탭은 페이지가 스스로 닫는다.
그래서 이 명령을 백그라운드로 돌리면 사용자가 보낸 순간 답이 부른 세션으로 돌아온다.
--static 은 서버를 못 띄울 때만 쓴다: HTML 을 양식 옆에 쓰고, 사용자가 복사한 답을 <양식>.answers.json 에 저장한 뒤 done 을 돌린다.

장부는 <프로젝트>/.claude/decisions.jsonl 이다. 덧붙이기만 한다 — 기각은 옛 줄을 고치지 않고 '기각' 줄을 더한다.
끝 코드: 0 보냄 · 1 양식 오류 · 2 보내지 않고 닫음 · 3 시간 초과.
"""

import argparse
import html
import json
import re
import secrets
import sys
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

for _s in (sys.stdout, sys.stderr):  # 한글 Windows 콘솔(cp949)에서 '—' 를 못 찍어 죽는다
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

PAGE = Path(__file__).resolve().parent / "page.html"
ID_OK = re.compile(r"^[A-Za-z0-9_-]+$")
LONG = 120           # 한 줄에 사실 하나 (docs/READING.md)
MAX_QUESTIONS = 5    # 한 번에 묻는 수. 넘으면 다음 양식으로
MAX_OPTIONS = 4
MAX_CHECKS = 7
CLOSE_GRACE = 3.0    # 탭이 닫힌 뒤 이만큼 기다린다 — 새로 고침이면 그 사이에 다시 온다
WHY = (("problem", "문제"), ("dropped", "버린 안"), ("cost", "대가"), ("flip", "뒤집는 조건"))


# ── 양식 점검 ──────────────────────────────────────────────────────────────

def _ids_ok(ids):
    return len(set(ids)) == len(ids) and all(ID_OK.match(i) for i in ids)


def check_spec(spec):
    """→ (오류, 경고). 오류가 있으면 양식을 띄우지 않는다."""
    errors, warns = [], []
    kind = spec.get("kind")
    if kind not in ("selection", "diff", "ledger"):
        return [f"kind 가 selection · diff · ledger 가 아니다: {kind!r}"], warns
    if not str(spec.get("title") or "").strip():
        errors.append("title 이 없다")
    if len(spec.get("context") or []) > 3:
        warns.append("context 는 3줄 이하로 쓴다")
    if kind != "selection":
        return errors, warns
    questions = spec.get("questions") or []
    if not questions:
        errors.append("questions 가 비었다")
    if len(questions) > MAX_QUESTIONS:
        warns.append(f"질문 {len(questions)}개 — {MAX_QUESTIONS}개 이하로 줄이고 나머지는 다음 양식으로")
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


# ── 페이지 · 서버 ──────────────────────────────────────────────────────────

def build_page(spec, state, token, served, name):
    boot = json.dumps({"spec": spec, "state": state, "token": token, "served": served, "name": name}, ensure_ascii=False)
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


def serve(spec, save_to, timeout_min=120, open_browser=True, port=0, on_ready=None):
    """양식을 127.0.0.1 에서 내보내고 보낼 때까지 기다린다. → (끝 종류, 답). 끝 종류: submitted · closed · timeout.
    주소의 토큰이 없으면 페이지도 저장도 거절한다 — 다른 웹 페이지가 이 포트로 읽거나 쓰지 못한다."""
    token = secrets.token_urlsafe(16)
    state = {"end": None, "answers": read_answers(save_to), "bye": None, "last": time.time()}
    name = Path(save_to).name

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
            if path != "/":
                return self.reply(403 if path is None else 404)
            state["bye"], state["last"] = None, time.time()
            self.reply(200, build_page(spec, state["answers"], token, True, name).encode("utf-8"), "text/html; charset=utf-8")

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
    print(f"양식: {url}\n브라우저에서 고르고 Enter 로 보낸다. 보내면 이 명령이 답을 찍고 끝난다.", flush=True)
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


def diff_summary(spec, answers):
    given = answers.get("g") or {}
    marks = [VERDICTS.get((given.get(g["id"]) or {}).get("verdict"), "미정") for g in spec["groups"]]
    count = marks.count
    lines = [f"검토 제출됨 — {spec['title']}", f"확인 {count('확인함')} · 기각 {count('기각')} · 미정 {count('미정')}", "",
             "| 묶음 | 판정 | 피드백 |", "|---|---|---|"]
    for i, (g, mark) in enumerate(zip(spec["groups"], marks), 1):
        lines.append(f"| {i}. {cell(g['title'])} | {mark} | {cell((given.get(g['id']) or {}).get('note'))} |")
    return "\n".join(lines)


# ── 결정 장부 ──────────────────────────────────────────────────────────────

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
            print(f"장부 {n}번째 줄을 못 읽어 건너뛴다: {path}", file=sys.stderr)
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
    """사용자가 '장부에 남긴다' 를 표시하고 고른 질문만 적는다. 고른 것을 전부 적으면 사소한 선택이 쌓여 읽지 않는 목록이 된다.
    안 고른 질문은 결정이 아니다 — 기각만 한 질문은 선택지를 다시 낼 재료다.
    버린 안에는 사용자가 적은 기각 이유와 앞 양식에서 기각한 안(dropped_before)이 붙는다."""
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
    """보낸 답을 찍고, 종류에 맞게 장부를 고친다."""
    ledger = ledger_path(project)
    if spec["kind"] == "selection":
        print(selection_summary(spec, answers))
        ids = record_selection(spec, answers, ledger) if record else []
        if ids:
            print(f"\n장부: {' · '.join(ids)} — {ledger}")
        elif record:
            print("\n장부: 남김 표시한 결정이 없어 적지 않았다")
    elif spec["kind"] == "diff":
        print(diff_summary(spec, answers))
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


def run_form(spec, spec_path, save_to, args, record=True):
    """양식을 띄우고 끝 코드를 돌려준다. spec_path 가 있으면 보낸 뒤 양식 파일을 지운다."""
    kind, answers = serve(spec, save_to, args.timeout, not args.no_open)
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
        raise SystemExit(f"양식을 못 읽었다: {path}\n{e}")
    errors, warns = check_spec(spec)
    for w in warns:
        print(f"점검: {w}")
    if errors:
        raise SystemExit("양식 오류:\n" + "\n".join(f"- {e}" for e in errors))
    return spec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["form", "done", "add", "list", "collect", "reject"])
    ap.add_argument("spec", nargs="?", help="form · done: 양식 JSON")
    ap.add_argument("--project", default=".", help="프로젝트 루트. 장부는 그 아래 .claude/decisions.jsonl")
    ap.add_argument("--keep", action="store_true", help="보낸 뒤에도 양식 · 답 파일을 지우지 않는다")
    ap.add_argument("--no-record", action="store_true", help="고른 것을 장부에 적지 않는다")
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
            ap.error("양식 JSON 경로가 필요하다")
        spec, save_to = load_spec(args.spec), answers_path(args.spec)
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
            print(f"양식 파일: {out}\n사용자가 Enter 로 복사한 답을 받으면 {save_to} 에 저장하고 `decide.py done {args.spec}` 를 돌린다.")
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
