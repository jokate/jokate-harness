"""Stop: 이번 답변에 ```mermaid 블록이 있으면 HTML 로 렌더해 브라우저로 연다. 답변을 막거나 바꾸지 않는다.

Claude Code 대화창은 Mermaid 를 그리지 않고 `graph LR` · `subgraph …` 같은 코드로 보인다.
game-architecture 의 "저장 후 render.py --open" 규칙은 모델이 지켜야 동작하고, 그 스킬 밖의 답변에는 없다.
이 훅은 어떤 답변이든 그림이 있으면 연다.

저장: 게임 프로젝트면 <UE>/Saved/ClaudeArch · <Unity>/Library/ClaudeArch (VCS 가 무시하는 폴더),
      아니면 ~/.claude/cache/game-harness/diagrams. 이름은 <날짜>-chat-<내용 해시>.md/.html.
      같은 내용이 이미 렌더돼 있으면 다시 열지 않는다.
GAME_HARNESS_NO_OPEN=1 이면 파일만 만들고 열지 않는다 (평가처럼 사람이 없는 실행).
렌더는 ~/.claude/skills/game-architecture/scripts/render.py (mermaid·marked 동봉) 를 쓴다.
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENDER_DIRS = [Path.home() / ".claude" / "skills" / "game-architecture" / "scripts",
               HERE.parent.parent / "game-architecture" / "scripts"]  # 저장소에서 바로 돌릴 때
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*mermaid[ \t]*\r?\n.*?^[ \t]*\1[ \t]*$", re.M | re.S)
TAIL_BYTES = 4_000_000
CACHE = Path.home() / ".claude" / "cache" / "game-harness" / "diagrams"

try:
    from harness_events import emit as harness_emit
except Exception:  # 이벤트 로그가 설치되지 않았어도 훅은 돈다
    def harness_emit(*a, **k):
        pass


def from_transcript(path):
    """last_assistant_message 가 없는 버전용. 마지막 사용자 입력 뒤의 assistant 텍스트를 잇는다."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - TAIL_BYTES))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return ""
    texts = []
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        c = (d.get("message") or {}).get("content")
        if d.get("type") == "user":
            if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
                continue
            break
        if d.get("type") == "assistant" and isinstance(c, list):
            t = "".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
            if t:
                texts.append(t)
    return "\n\n".join(reversed(texts))


def out_dir(cwd):
    try:
        from game_context import detect
        root, engine = detect(cwd)
    except Exception:
        root, engine = None, None
    if root is not None:
        return root / ("Library" if engine.startswith("Unity") else "Saved") / "ClaudeArch", root
    return CACHE, None


def load_render():
    for d in RENDER_DIRS:
        if (d / "render.py").is_file():
            sys.path.insert(0, str(d))
            import render
            return render
    return None


def reply(msg):
    sys.stdout.write(json.dumps({"systemMessage": msg}))


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    except ValueError:
        data = {}
    text = data.get("last_assistant_message")
    if not isinstance(text, str):
        text = from_transcript(data.get("transcript_path"))
    n = len(FENCE.findall(text or ""))
    if not n:
        return
    session = data.get("session_id", "")
    folder, root = out_dir(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    if any(any(d.glob(f"*-chat-{digest}.html")) for d in (folder, CACHE)):
        return
    render = load_render()
    if render is None:
        reply(f"답변에 Mermaid 그림 {n}장이 있지만 render.py 를 못 찾아 렌더하지 못했다 — setup.bat 을 다시 돌린다.")
        harness_emit("diagram.render", "render.py 없음", ok=False, session=session, project=root or "",
                     source="diagram_view")
        return
    name = f"{time.strftime('%Y%m%d-%H%M')}-chat-{digest}"
    title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("# ")),
                 f"Claude 답변 그림 {time.strftime('%Y-%m-%d %H:%M')}")
    for d in (folder, CACHE):  # 프로젝트 폴더에 못 쓰면(읽기 전용 등) 캐시로
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.md").write_text(text, encoding="utf-8")
            html = render.render(text, d / f"{name}.html", title)
            break
        except OSError:
            html = None
    if html is None:
        return
    err = None if os.environ.get("GAME_HARNESS_NO_OPEN") == "1" else render.open_file(html)
    opened = "열지 않음 (GAME_HARNESS_NO_OPEN)" if os.environ.get("GAME_HARNESS_NO_OPEN") == "1" else \
        (f"열지 못했다: {err} — 직접 연다" if err else "브라우저로 열었다")
    reply(f"Mermaid 그림 {n}장 → {html} ({opened})")
    harness_emit("diagram.render", f"{n}장 · {html.name}", ok=err is None, session=session, project=root or "",
                 source="diagram_view")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
