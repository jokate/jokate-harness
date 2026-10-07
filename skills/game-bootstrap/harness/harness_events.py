"""하네스 이벤트 로그. 하네스의 훅·조회 스크립트가 "어떤 기능이 동작했는가"를 한 줄씩 남긴다.

위치: ~/.claude/cache/game-harness/events.jsonl (환경 변수 GAME_HARNESS_EVENTS 로 바꿀 수 있다)
한 줄: {"ts": 밀리초, "t": "YYYY-MM-DD HH:MM:SS", "session": 세션 id 또는 "", "project": 루트 경로,
        "feature": "skill.game-onboard" 같은 기능 id, "ok": true/false, "detail": 짧은 설명, "source": 남긴 파일}
읽는 쪽: game-harness-monitor mod(상태줄·토스트·패널), 인덱스 웹뷰의 하네스 탭.

기능 id 는 "<층>.<이름>" 이다. 층: context · session_start · index · handoff · stuck · mcp · skill · script · diagram.
기록 실패는 삼킨다 — 로그 때문에 훅이나 스크립트가 멈추면 안 된다.
파일이 MAX_BYTES 를 넘으면 마지막 KEEP_LINES 줄만 남긴다 (mod 가 한 번에 읽을 수 있는 크기로).
"""
import json
import os
import time
from pathlib import Path

MAX_BYTES = 1_000_000
KEEP_LINES = 3000
MAX_DETAIL = 300


def log_path():
    env = os.environ.get("GAME_HARNESS_EVENTS")
    return Path(env) if env else Path.home() / ".claude" / "cache" / "game-harness" / "events.jsonl"


def emit(feature, detail="", ok=True, session="", project="", source=""):
    try:
        now = time.time()
        rec = {"ts": int(now * 1000), "t": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
               "session": session or "", "project": str(project or ""), "feature": feature,
               "ok": bool(ok), "detail": str(detail)[:MAX_DETAIL], "source": source}
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if path.stat().st_size > MAX_BYTES:
            _rotate(path)
    except Exception:
        pass


def _rotate(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-KEEP_LINES:]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read(limit=500, session=None, project=None, since_ms=0):
    """최근 이벤트를 오래된 것부터. session/project 를 주면 그것만."""
    try:
        lines = log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("ts", 0) < since_ms:
            break
        if session is not None and r.get("session") != session:
            continue
        if project is not None and r.get("project") != project:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out[::-1]
