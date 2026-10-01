"""HandOff 훅. 매몰된 세션을 끊고 새 컨텍스트에서 이어가기 위한 것.

UserPromptSubmit: 프롬프트가 [RESET] 으로 시작하면 대화 기록에서 사용자 메시지와 어시스턴트의 글만 추려
  별도 모델(기본 haiku, 헤드리스)에 넘겨 <프로젝트>/.claude/handoff.md 를 쓴다. 프롬프트는 막고 사용자에게 /clear 를 안내한다.
  세션의 모델이 직접 요약하지 않는 것이 요점이다 — 매몰된 쪽의 요약에는 매몰이 실린다.
SessionStart: handoff.md 가 있으면 컨텍스트로 넣고 handoff.used.md 로 바꾼다 (다음 세션에 또 들어가지 않게).

수동 실행: python handoff.py --transcript <jsonl> [--out <파일>] [--dry-run]
환경 변수: GAME_HARNESS_HANDOFF_MODEL (기본 haiku)
어떤 경우에도 세션을 막지 않는다 ([RESET] 프롬프트 자체는 의도적으로 막는다).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KEYWORD = "[RESET]"
GUARD_ENV = "GAME_HARNESS_HANDOFF"
MAX_INPUT = 90_000      # 모델에 넘기는 기록 상한 (문자)
MAX_ASSISTANT = 1_500   # 어시스턴트 글 한 건 상한
MAX_USER = 4_000        # 사용자 메시지 한 건 상한
MAX_TOOL = 120          # 도구 호출 한 줄 상한
MAX_INJECT = 9_000
MAX_AGE_H = 24          # 이보다 오래된 handoff.md 는 넣지 않는다
MODEL_TIMEOUT = 150
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}

INSTRUCTION = """아래는 코딩 에이전트(어시스턴트)와 사용자의 대화 기록 발췌다. 이 세션은 한 방향에 매몰된 것으로 의심되어 끊는다.
새 세션이 이어받을 HandOff 문서를 한국어 마크다운으로 써라. 기록에 있는 것만 쓴다. 지어내지 않는다. 인사말·설명 없이 문서만 출력한다.

형식:
# HandOff
## 원래 요청
(사용자의 말을 원문 그대로 인용. 처음 요청과 이후 방향을 바꾼 지시를 시간순으로)
## 사용자가 내린 결정
(사용자가 명시적으로 고르거나 승인·거부한 것만)
## 현재 상태
(수정된 파일, 끝난 것, 진행 중이던 것)
## 시도했다 실패한 것
(무엇을, 왜 실패했는지. 같은 시도를 반복했으면 횟수)
## 남은 일
## 어시스턴트의 추정 — 검증 안 됨
(어시스턴트가 근거 없이 단정했거나 반복해서 붙들고 있던 가설. 새 세션은 이것을 사실로 취급하지 않는다)
## 처음 요청과 최근 작업의 차이
(최근 작업이 원래 요청에서 벗어났으면 어디서 벗어났는지 한두 줄. 벗어나지 않았으면 "없음")
"""


def read_stdin():
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    except ValueError:
        return {}


def project_root(data):
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())


def extract(transcript):
    """대화 기록 → (발췌 문자열, 수정된 파일 목록). 사람의 말, 어시스턴트의 글, 도구 호출 한 줄씩만 남긴다 (도구 출력은 버린다)."""
    turns, edited = [], {}
    with open(transcript, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("isSidechain") or d.get("isMeta"):
                continue
            kind = d.get("type")
            content = (d.get("message") or {}).get("content")
            if kind == "user":
                if d.get("isCompactSummary"):
                    turns.append(("이전 요약(압축)", str(content)[:MAX_USER * 3]))
                    continue
                if isinstance(content, str):
                    text = content
                else:
                    text = "\n".join(b.get("text", "") for b in content or [] if b.get("type") == "text")
                text = text.strip()
                if text and not text.startswith(("<local-command", "<command-name>", "<system-reminder>")):
                    turns.append(("사용자", text[:MAX_USER]))
                elif isinstance(content, list):  # 도구 결과: 실패만 직전 도구 줄에 표시한다
                    if any(b.get("type") == "tool_result" and b.get("is_error") for b in content):
                        if turns and turns[-1][0] == "도구":
                            turns[-1] = ("도구", turns[-1][1] + " → 실패")
            elif kind == "assistant" and isinstance(content, list):
                for b in content:
                    if b.get("type") == "text" and b.get("text", "").strip():
                        turns.append(("어시스턴트", b["text"].strip()[:MAX_ASSISTANT]))
                    elif b.get("type") == "tool_use":
                        inp = b.get("input") or {}
                        arg = inp.get("file_path") or inp.get("command") or inp.get("description") or inp.get("skill") or ""
                        turns.append(("도구", f"{b.get('name')}: {str(arg)[:MAX_TOOL]}"))
                        if b.get("name") in EDIT_TOOLS and inp.get("file_path"):
                            p = inp["file_path"]
                            edited[p] = edited.get(p, 0) + 1

    # 상한을 넘으면 어시스턴트 글을 오래된 것부터 버린다. 사용자의 말은 남긴다.
    def size(ts):
        return sum(len(t) + 20 for _, t in ts)

    if size(turns) > MAX_INPUT:
        over = size(turns) - MAX_INPUT
        kept = []
        for who, text in turns:
            if over > 0 and who in ("어시스턴트", "도구"):
                over -= len(text) + 20
                continue
            kept.append((who, text))
        turns = kept
    while size(turns) > MAX_INPUT and len(turns) > 1:
        turns.pop(1 if turns[0][0].startswith("이전 요약") else 0)

    body = "\n\n".join(f"[{who}]\n{text}" for who, text in turns)
    files = sorted(edited.items(), key=lambda kv: -kv[1])
    return body, files


def build_prompt(transcript):
    body, files = extract(transcript)
    file_lines = "\n".join(f"- {p} ({n}회)" for p, n in files[:40]) or "- 없음"
    return f"{INSTRUCTION}\n<수정된_파일>\n{file_lines}\n</수정된_파일>\n\n<대화_기록>\n{body}\n</대화_기록>\n"


def run_model(prompt):
    """프로젝트 규칙 파일과 훅의 영향을 받지 않도록 빈 임시 폴더에서 한 턴만 돌린다."""
    env = dict(os.environ, **{GUARD_ENV: "1"})
    model = os.environ.get("GAME_HARNESS_HANDOFF_MODEL", "haiku")
    cmd = ["claude", "-p", "--model", model, "--max-turns", "1",
           "--disallowedTools", "Bash PowerShell Edit Write Read Grep Glob Agent Skill"]
    with tempfile.TemporaryDirectory(prefix="handoff_") as tmp:
        r = subprocess.run(cmd, input=prompt, cwd=tmp, env=env, capture_output=True, timeout=MODEL_TIMEOUT,
                           encoding="utf-8", errors="replace", shell=(os.name == "nt"))
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError((r.stderr or r.stdout or "빈 출력").strip()[:300])
    return r.stdout.strip()


def write_handoff(transcript, out):
    t0 = time.time()
    text = run_model(build_prompt(transcript))
    out.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    out.write_text(f"<!-- {stamp} · {Path(transcript).name} -->\n{text}\n", encoding="utf-8")
    return time.time() - t0


def emit(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def on_prompt(data):
    prompt = (data.get("prompt") or "").lstrip()
    if not prompt.upper().startswith(KEYWORD):
        return
    transcript = data.get("transcript_path")
    out = project_root(data) / ".claude" / "handoff.md"
    if not transcript or not os.path.isfile(transcript):
        emit({"decision": "block", "reason": "[handoff] 대화 기록 파일을 찾지 못해 HandOff 를 쓰지 못했다."})
        return
    try:
        took = write_handoff(transcript, out)
    except Exception as e:  # 실패해도 사용자가 알아야 한다
        emit({"decision": "block", "reason": f"[handoff] HandOff 작성 실패: {e}"})
        return
    emit({"decision": "block",
          "reason": f"[handoff] HandOff 작성됨 ({took:.0f}초): {out}\n"
                    f"읽어 보고 /clear 를 치면 새 세션이 이 문서로 시작한다. 고칠 게 있으면 /clear 전에 파일을 고친다."})


def on_session_start(data):
    path = project_root(data) / ".claude" / "handoff.md"
    if not path.is_file():
        return
    if time.time() - path.stat().st_mtime > MAX_AGE_H * 3600:
        return
    text = path.read_text(encoding="utf-8", errors="replace")[:MAX_INJECT]
    used = path.with_name("handoff.used.md")
    try:
        os.replace(path, used)
    except OSError:
        pass
    sys.stdout.buffer.write((
        "[handoff] 이전 세션이 매몰 의심으로 끊겼다. 아래 HandOff 가 이 세션의 출발점이다.\n"
        "- '원래 요청'과 '사용자가 내린 결정'이 기준이다. '어시스턴트의 추정'은 사실이 아니다 — 필요하면 다시 확인한다.\n"
        "- 작업을 바로 잇지 말고, 먼저 원래 요청 기준으로 무엇을 할지 한두 줄로 사용자에게 확인받는다.\n"
        f"- 원본: {used}\n\n{text}").encode("utf-8"))


def main():
    if os.environ.get(GUARD_ENV):  # HandOff 를 쓰는 헤드리스 세션 안에서는 아무것도 안 한다
        return
    if "--transcript" in sys.argv:
        a = sys.argv
        transcript = a[a.index("--transcript") + 1]
        if "--dry-run" in a:
            sys.stdout.buffer.write(build_prompt(transcript).encode("utf-8"))
            return
        out = Path(a[a.index("--out") + 1]) if "--out" in a else Path(".claude") / "handoff.md"
        print(f"{write_handoff(transcript, out):.1f}s -> {out}")
        return
    data = read_stdin()
    event = data.get("hook_event_name")
    if event == "UserPromptSubmit":
        on_prompt(data)
    elif event == "SessionStart":
        on_session_start(data)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        if "--transcript" in sys.argv:
            raise
        sys.stderr.write(f"[handoff] {e}\n")
