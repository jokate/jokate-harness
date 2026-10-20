"""Stop: 이번 답변에 ```mermaid 블록이 있거나, 이번에 저장한 구조 문서(ClaudeArch/*.md)의 HTML 이 없거나 낡았으면
HTML 로 렌더해 브라우저로 연다. 답변을 막거나 바꾸지 않는다.

보기: render.py 기본 보기 — game-architecture 답변은 선택지 · 그림 먼저, 그 밖의 글은 제목 → 요약 3줄 → 그림,
나머지는 접는다. 그림은 누르면 크게. 긴 HTML 이 볼 때마다 불편하다는 사용자 피드백(2026-10-20).

Claude Code 대화창은 Mermaid 를 그리지 않고 `graph LR` · `subgraph …` 같은 코드로 보인다.
game-architecture 의 "저장 후 render.py --open" 규칙은 모델이 지켜야 동작하고, 그 스킬 밖의 답변에는 없다.
이 훅은 어떤 답변이든 그림이 있으면 연다.

범위: 게임 프로젝트(UE / Unity)에서만 돈다 — 게임이 아닌 세션(릴레이 작업 등)에서 브라우저가 뜨지 않게.
저장: <UE>/Saved/ClaudeArch · <Unity>/Library/ClaudeArch (VCS 가 무시하는 폴더). 거기에 못 쓰면 ~/.claude/cache/game-harness/diagrams.
      이름은 <날짜>-chat-<내용 해시>.md/.html.
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
DOC_WINDOW = 3600  # 구조 문서: 최근 1시간 안에 저장된 .md 만 (오래된 기록을 갑자기 열지 않게)
MAX_DOCS = 3
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


def fresh_docs(folder, now=None):
    """이번에 저장된 구조 문서 — ClaudeArch 의 .md 중 그림이 있고, 최근 저장됐고, HTML 이 없거나 더 오래된 것.
    모델이 render.py 를 빠뜨려도 구조 문서는 보기 좋게 열린다. 훅이 만든 '-chat-' 기록은 뺀다."""
    now = time.time() if now is None else now
    out = []
    try:
        cands = sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return out
    for p in cands:
        try:
            mt = p.stat().st_mtime
            if "-chat-" in p.name or now - mt > DOC_WINDOW:
                continue
            h = p.with_suffix(".html")
            if h.is_file() and h.stat().st_mtime >= mt:
                continue
            if FENCE.search(p.read_text(encoding="utf-8", errors="replace")):
                out.append(p)
        except OSError:
            continue
        if len(out) >= MAX_DOCS:
            break
    return out


def title_of(text, fallback):
    return next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("# ")), fallback)


def reply(msg):
    sys.stdout.write(json.dumps({"systemMessage": msg}))


def render_answer(render, text, folder):
    """답변 속 그림 → <날짜>-chat-<해시>.md/.html. 같은 내용이 이미 있으면 None."""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    if any(any(d.glob(f"*-chat-{digest}.html")) for d in (folder, CACHE)):
        return None
    name = f"{time.strftime('%Y%m%d-%H%M')}-chat-{digest}"
    title = title_of(text, f"Claude 답변 그림 {time.strftime('%Y-%m-%d %H:%M')}")
    for d in (folder, CACHE):  # 프로젝트 폴더에 못 쓰면(읽기 전용 등) 캐시로
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.md").write_text(text, encoding="utf-8")
            return render.render(text, d / f"{name}.html", title)
        except OSError:
            continue
    return None


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    except ValueError:
        data = {}
    text = data.get("last_assistant_message")
    if not isinstance(text, str):
        text = from_transcript(data.get("transcript_path"))
    n = len(FENCE.findall(text or ""))
    session = data.get("session_id", "")
    folder, root = out_dir(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    if root is None:  # 게임 프로젝트가 아니다
        return
    docs = fresh_docs(folder)
    if not n and not docs:
        return
    render = load_render()
    if render is None:
        reply("그림이 있지만 render.py 를 못 찾아 렌더하지 못했다 — setup.bat 을 다시 돌린다.")
        harness_emit("diagram.render", "render.py 없음", ok=False, session=session, project=root or "",
                     source="diagram_view")
        return
    made = []
    for p in docs:  # 구조 문서 — 같은 이름의 .html 로
        try:
            t = p.read_text(encoding="utf-8")
            made.append(("구조 문서", render.render(t, p.with_suffix(".html"), title_of(t, p.stem))))
        except OSError:
            continue
    if n:
        h = render_answer(render, text, folder)
        if h:
            made.append((f"Mermaid 그림 {n}장", h))
    if not made:
        return
    no_open = os.environ.get("GAME_HARNESS_NO_OPEN") == "1"
    errs = [] if no_open else [e for e in (render.open_file(h) for _, h in made) if e]
    opened = "열지 않음 (GAME_HARNESS_NO_OPEN)" if no_open else \
        (f"열지 못했다: {errs[0]} — 직접 연다" if errs else "브라우저로 열었다")
    reply(" · ".join(f"{k} → {h}" for k, h in made) + f" ({opened})")
    harness_emit("diagram.render", " · ".join(f"{k} {h.name}" for k, h in made), ok=not errs, session=session,
                 project=root or "", source="diagram_view")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
