"""SessionStart: 게임 프로젝트(UE / Unity)면 엔진 · 소스 저장소 · 그 프로젝트에 있는 위키와 인덱스 명령을 컨텍스트에 넣는다.
게임 프로젝트가 아니면 아무것도 안 한다. 어떤 경우에도 세션을 막지 않는다.

모델이 저장소만 봐서는 알 수 없는 것(인덱스가 있는지, 명령 경로)만 알린다.
"""
import json
import os
import re
import sys
from pathlib import Path

SKILLS = Path.home() / ".claude" / "skills"

try:
    from harness_events import emit as harness_emit
except Exception:  # 이벤트 로그가 설치되지 않았어도 훅은 돈다
    def harness_emit(*a, **k):
        pass


def detect(start):
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        up = sorted(cand.glob("*.uproject"))
        if up:
            try:
                ver = json.loads(up[0].read_text(encoding="utf-8")).get("EngineAssociation", "?")
            except (OSError, ValueError):
                ver = "?"
            return cand, f"Unreal Engine {ver}"
        pv = cand / "ProjectSettings" / "ProjectVersion.txt"
        if pv.is_file() and (cand / "Assets").is_dir():
            m = re.search(r"m_EditorVersion:\s*(\S+)", pv.read_text(encoding="utf-8", errors="replace"))
            return cand, f"Unity {m.group(1) if m else '?'}"
    return None, None


def source_repo(root):
    try:
        sys.path.insert(0, str(SKILLS / "game-architecture" / "scripts"))
        from evidence import vcs_roots
    except Exception:
        return None
    roots = vcs_roots(root)
    if not roots:
        return "VCS 없음 — 변경 이력 신호를 쓸 수 없다."
    k, d, n, src = max(roots, key=lambda r: ((r[3] or 0), (r[2] or 0)))
    rel = os.path.relpath(d, root).replace("\\", "/")
    if rel == ".":
        return f"소스 저장소: 루트 ({k}, 커밋 {n})."
    return f"소스 저장소: `{rel}` ({k}, 커밋 {n}, 소스 {src}) — 루트와 별도 저장소다. evidence.py 는 `--path {rel}`."


def keeps_gq(root):
    """이 프로젝트가 gq 인덱스를 세션마다 갱신하는가 — `.claude/session_start.json` 이 없으면(세팅 전) 그렇다고 본다.
    MNYS 처럼 자기 조회 도구(Tools/mnys_q.py)를 CLAUDE.md 에 적고 gq 갱신을 끈 프로젝트에는 gq 를 권하지 않는다 —
    낡은 인덱스를 권하게 되고, 같은 일을 하는 도구 둘을 함께 안내하게 된다(2026-10-22 감사: gq 25회 · mnys_q 441회)."""
    f = root / ".claude" / "session_start.json"
    try:
        spec = json.loads(f.read_text(encoding="utf-8"))
    except OSError:
        return True
    except ValueError:
        return True
    return any("gq.py" in " ".join(map(str, c.get("run", []))) for c in spec.get("commands", []) if isinstance(c, dict))


def fact_lines(root, engine, home=None):
    """이 프로젝트에 있는 위키 · 인덱스만 사실로 적는다. 명령은 경로째 준다(PowerShell 은 python 인자의 ~ 를 안 푼다).

    스킬 고르기는 스킬 설명이 한다 — 여기서 되풀이하지 않는다. 2026-11-10 대조(Sonnet, 첫 6턴, MNYS):
    "요청 → 스킬" 줄 3개를 빼도 스킬 호출은 구현 · 테스트 · 기획 대조 · 엔진 조회에서 그대로였다. 사용자가 구조를 직접 낸
    요청만 0/4 로 떨어졌고, game-architecture 설명에 그 경우를 한 구절 넣자 4/4 로 돌아왔다. 인덱스 사용은 두 팔이 같았다.
    MCP 가드 후보 수를 세션마다 알리던 줄도 뺐다(50건이 쌓이도록 검토 0회 — game-mcp 스킬이 다룬다).
    docs/experience/model-generation-recheck.md."""
    home = Path(home) if home else Path.home()
    idx = root / ("Library" if engine.startswith("Unity") else "Saved") / "ClaudeIndex"
    onboard = f"python {(home / '.claude' / 'skills' / 'game-onboard' / 'scripts').as_posix()}"
    wiki = home / ".jokate-wiki" / root.name
    out = []
    if (wiki / "index.md").is_file():
        out.append(f"- 위키 `{wiki.as_posix()}/index.md`: 시스템 구조 · 동작 · 이유의 맥락이 있다. wiki-query 스킬이 읽는다.")
    if (idx / "symbols.json").is_file() and keeps_gq(root):
        out.append(f"- 좌표 인덱스: 어디에 있나 `{onboard}/gq.py find <이름>` · 심볼 좌표 `gq.py sym <이름>`")
    if (idx / "clangd.sqlite").is_file():
        # 명령은 줄 그대로 둔다 — 'callers · derived' 로 줄였을 때 cindex 호출이 반으로 줄었다(2026-10-22 대조)
        out.append(f"- clangd 의미 인덱스: 쓰는 곳 `{onboard}/cindex.py refs <심볼>` · 누가 부르나 `cindex.py callers <심볼>` · "
                   "파생 `cindex.py derived <클래스>` · 바꾸면 영향 `cindex.py impact <심볼>`. "
                   "컴파일 기준이라 주석 · 문자열 · 같은 이름이 섞이지 않고 생성 코드는 빠진다. "
                   "클래스 · 함수 · 구조체 이름은 grep 보다 이쪽이 정확하다. 문자열 · 주석 · 설정값 · 로그는 rg 가 맞다.")
    ledger = root / ".claude" / "team_feedback.md"
    if ledger.is_file():
        try:
            n = sum(1 for ln in ledger.read_text(encoding="utf-8", errors="replace").splitlines() if ln.startswith("## "))
        except OSError:
            n = 0
        if n:
            out.append(f"- 팀 피드백 로그 `{ledger.as_posix()}`: 동료에게 받은 지적 {n}건. game-architecture 스킬이 구조를 내기 전에 읽는다.")
    return (["이 프로젝트에 있는 것:"] + out) if out else []


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    except ValueError:
        data = {}
    root, engine = detect(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    if root is None:
        return
    lines = [f"[game-harness] {root.name}: {engine} 프로젝트."]
    repo = source_repo(root)
    if repo:
        lines.append(repo)
    lines += fact_lines(root, engine)
    is_setup = (root / ".claude" / "session_start.json").is_file() or (root / "CLAUDE.md").is_file()
    if not is_setup:
        lines.append("이 프로젝트는 세팅 전이다 (CLAUDE.md·인덱스 갱신 없음). 필요하면 사용자에게 /game-bootstrap 을 안내한다.")
    harness_emit("context.routing", f"{engine} · {'세팅됨' if is_setup else '세팅 전'}",
                 session=data.get("session_id", ""), project=root, source="game_context")
    sys.stdout.buffer.write("\n".join(lines).encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
