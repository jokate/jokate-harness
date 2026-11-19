"""문서 양식 훅 (Stop / UserPromptSubmit). 문서 스킬 넷을 제때 띄우게 한다.

  Stop              방금 답이 선택지를 냈으면(줄 머리 A · B 이름 둘 이상 + 줄 머리 `추천:`) 한 번 더 이어 가게 해서
                    고르기 양식(selection)을 띄우게 한다.
  UserPromptSubmit  프롬프트가 문서 스킬의 일이면(시안 · 바뀐 부분 · 결정 모음 · 결정 기각 · 양식으로 고르기)
                    그 스킬 파일을 가리키는 한 줄을 넣는다.

맞는 것이 없으면 아무것도 내지 않는다(토큰 0). 어떤 경우에도 세션을 막지 않는다.

켜지는 곳: 사람이 보고 있는 세션(CLAUDE_CODE_SESSION_ATTENDED=1)의 게임 프로젝트.
  <프로젝트>/.claude/doc_nudge.off   그 프로젝트에서 끈다 (위 폴더에 두면 그 아래 전부)
  <폴더>/.claude/doc_nudge.on        게임 프로젝트가 아닌 폴더에서 켠다
  GAME_HARNESS_DOC_NUDGE=0           전부 끈다
  GAME_HARNESS_DOC_NUDGE=1           사람이 보는지 묻지 않고 켠다 (신호가 없는 판 · 시험)

기록(harness_events):
  doc.nudge.<스킬>   넣었다
  doc.nudge.skip     선택지를 봤지만 넣지 않았다 — detail 에 이유
"""
import json
import os
import re
import sys
import time
from pathlib import Path

SWITCH = "GAME_HARNESS_DOC_NUDGE"
ATTENDED = "CLAUDE_CODE_SESSION_ATTENDED"
PENDING_TTL = 3 * 3600  # 양식의 제한 시간(120분)보다 길게
KEEP_SESSIONS = 50
PROMPT_HEAD = 400       # 붙여 넣은 긴 글에서 낱말이 걸리지 않게 앞부분만 본다

# 줄 머리의 선택지 이름: "| A. 국소 패치 |", "- B안: ...", "**C안 — ...**", "### A) ..."
LABEL = re.compile(r"^[\s|>*#-]*\**\s*([A-D])(?:안|[.)])(?=[\s*:|—–-]|$)", re.M)
RECOMMEND = re.compile(r"^[\s|>*#-]*\**\s*추천(?:안)?\s*\**\s*[:：]", re.M)

# 걸릴 때마다 모델이 읽는 글이다. 스킬 파일을 다시 읽게 하지 않고 명령 하나로 끝나게 한다 —
# 스킬을 읽고 양식 파일을 따로 쓰게 했을 때는 모델이 다섯 번 더 돌았다(docs/VERIFICATION.md 2026-11-19 훅 절).
SELECTION_REASON = """하네스 훅(doc_nudge): 방금 답이 선택지를 냈다. 사용자가 양식으로 고를 수 있게 고르기 양식을 띄운다.
방금 답의 선택지 · 추천 · 왜 네 칸을 아래 꼴의 JSON 으로 그대로 옮긴다. 새 선택지 · 새 질문 · 방금 답에 없는 내용을 만들지 않는다. 없는 칸은 뺀다.
{"kind":"selection","title":"무엇을 정하나","questions":[{"id":"q1","title":"질문","changes":"답에 따라 바뀌는 것","options":[{"id":"A","name":"이름","summary":"무엇을 하나","next":"다음 요청 때 고칠 곳","gain":"얻는 것","loss":"잃는 것","recommended":true},{"id":"B","name":"이름"}],"why":{"problem":"문제","dropped":["버린 안 — 이유"],"cost":"대가","flip":"뒤집는 조건"}}]}
한 칸은 120자 이하, id 는 영문 · 숫자만 쓴다.
아래 명령 하나를 백그라운드로 돌린다. JSON 은 표준 입력으로 준다. 스킬 파일을 읽거나 양식 파일을 따로 쓰지 않는다.
python "__DECIDE__" form - --project "__ROOT__" <<'JSON'
{ ... }
JSON
띄웠으면 '고르기 양식을 띄웠다. 대화로 답해도 된다.' 한 줄만 쓰고 멈춘다. 선택지를 다시 쓰지 않는다.
명령이 끝났다는 알림이 오면 출력을 읽는다. `양식 오류` 면 고쳐 다시 돌린다. 답이면 따른다: 고른 안으로 진행한다 · 피드백은 지시다 · 기각한 안은 다시 내지 않는다 · 안 고른 질문은 미결이다.
사용자가 양식 대신 대화로 답하면 양식 명령을 멈추고 그 답을 따른다.
방금 답이 사용자에게 고르라고 낸 선택지가 아니면 양식을 띄우지 않고 그대로 멈춘다."""

POINTERS = [
    ("diff-proto", re.compile(
        r"(시안|프로토\s*타입|프로토).{0,12}(짜|만들|작성|뽑)"
        r"|(바뀐|변경된|고친)\s*(부분|곳|데).{0,12}(보여|정리|문서|설명)"
        r"|변경\s*점.{0,10}(보여|정리|문서)|변경\s*설명")),
    ("reject-decision", re.compile(r"결정\S*.{0,14}(기각|뒤집|철회|무르)|(기각|뒤집).{0,8}결정")),
    ("collect-decision", re.compile(
        r"결정\S*.{0,12}(모아|모음|모은|목록|정리해|뭐였|뭐\s*있)"
        r"|(정한|결정한)\s*(것|거|사항).{0,10}(모아|정리|보여|목록)")),
    ("selection", re.compile(r"(양식|체크\s*리스트)으로.{0,12}(골라|고[르를른]|정[하할]|선택)|고르기\s*양식")),
]


def pointer_text(skill):
    return (f"하네스 훅(doc_nudge): 이 요청은 문서 스킬 `{skill}` 의 일로 보인다. "
            f"`~/.claude/skills/{skill}/SKILL.md` 를 읽고 그 순서를 따른다. 요청과 맞지 않으면 이 안내를 무시한다.")


try:
    from harness_events import emit, log_path
except Exception:  # 이벤트 로그가 없어도 훅은 돈다
    def emit(*a, **k):
        pass

    def log_path():
        return Path.home() / ".claude" / "cache" / "game-harness" / "events.jsonl"


def find_options(text):
    """답이 고르라고 낸 선택지의 이름들. 줄 머리 이름이 둘 이상이고 줄 머리 `추천:` 이 있을 때만."""
    labels = sorted(set(LABEL.findall(text)))
    return labels if len(labels) >= 2 and RECOMMEND.search(text) else []


def find_pointer(prompt):
    head = prompt.lstrip()[:PROMPT_HEAD]
    if not head or head.startswith("/"):  # 슬래시로 부른 것은 이미 그 스킬이 실린다
        return None
    return next((name for name, pat in POINTERS if pat.search(head)), None)


def marker(cwd, name):
    try:
        p = Path(cwd).resolve()
    except OSError:
        return False
    return any((d / ".claude" / name).is_file() for d in [p, *p.parents])


def game_root(cwd):
    try:
        from game_context import detect
        return detect(cwd)[0]
    except Exception:
        return None


def scope(cwd, env):
    """(켜짐, 꺼진 이유)."""
    switch = env.get(SWITCH, "")
    if switch == "0":
        return False, f"{SWITCH}=0"
    if switch != "1" and env.get(ATTENDED) != "1":
        return False, f"unattended ({ATTENDED}={env.get(ATTENDED, '없음')})"
    if marker(cwd, "doc_nudge.off"):
        return False, "doc_nudge.off"
    if game_root(cwd) is None and not marker(cwd, "doc_nudge.on"):
        return False, "게임 프로젝트 아님"
    return True, ""


def selection_reason(cwd):
    decide = Path.home() / ".claude" / "skills" / "selection" / "scripts" / "decide.py"
    root = game_root(cwd) or Path(cwd)
    return SELECTION_REASON.replace("__DECIDE__", decide.as_posix()).replace("__ROOT__", Path(root).as_posix())


def state_path():
    return log_path().parent / "doc_nudge_state.json"


def load_state():
    try:
        d = json.loads(state_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    keep = dict(sorted(state.items(), key=lambda kv: kv[1])[-KEEP_SESSIONS:])
    try:
        p = state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(keep), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def form_open(data):
    """고르기 · 변경 설명 양식이 이미 백그라운드에서 돌고 있는가."""
    blob = json.dumps(data.get("background_tasks") or [], ensure_ascii=False)
    return "decide.py" in blob or "diffdoc.py" in blob


def on_stop(data, env):
    if data.get("stop_hook_active"):  # 훅이 이어 가게 한 차례의 끝 — 다시 잡으면 끝나지 않는다
        return None
    sid = str(data.get("session_id", ""))
    state = load_state()
    nudged_at = state.pop(sid, None)  # 양식을 띄운 뒤의 첫 멈춤 — 고른 뒤의 답이 선택지처럼 보여도 다시 띄우지 않는다
    if nudged_at is not None:
        save_state(state)
    labels = find_options(str(data.get("last_assistant_message") or ""))
    if not labels:
        return None
    common = {"session": sid, "project": data.get("cwd", ""), "source": "doc_nudge"}
    ok, why = scope(data.get("cwd") or ".", env)
    if ok and nudged_at is not None and time.time() - float(nudged_at) < PENDING_TTL:
        ok, why = False, "양식을 띄운 직후"
    if ok and data.get("permission_mode") == "plan":
        ok, why = False, "계획 모드"
    if ok and form_open(data):
        ok, why = False, "양식이 이미 떠 있음"
    if not ok:
        emit("doc.nudge.skip", why, **common)
        return None
    state[sid] = time.time()
    save_state(state)
    emit("doc.nudge.selection", "선택지 " + " · ".join(labels), **common)
    return {"decision": "block", "reason": selection_reason(data.get("cwd") or ".")}


def on_prompt(data, env):
    skill = find_pointer(str(data.get("prompt") or ""))
    if not skill:
        return None
    common = {"session": data.get("session_id", ""), "project": data.get("cwd", ""), "source": "doc_nudge"}
    ok, why = scope(data.get("cwd") or ".", env)
    if not ok:
        emit("doc.nudge.skip", f"{skill}: {why}", **common)
        return None
    emit(f"doc.nudge.{skill}", "프롬프트 낱말", **common)
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": pointer_text(skill)}}


def handle(data, env):
    event = data.get("hook_event_name")
    if event == "Stop":
        return on_stop(data, env)
    if event == "UserPromptSubmit":
        return on_prompt(data, env)
    return None


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    out = handle(data, os.environ)
    if out:
        sys.stdout.write(json.dumps(out))  # ASCII 로 내보낸다 — 콘솔 코드페이지에 한글이 깨지지 않게


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
