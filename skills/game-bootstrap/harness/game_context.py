"""SessionStart: 게임 프로젝트(UE / Unity)면 엔진·소스 저장소·스킬 라우팅을 컨텍스트에 넣는다.
게임 프로젝트가 아니면 아무것도 안 한다. 어떤 경우에도 세션을 막지 않는다.

CLAUDE.md 가 없는 프로젝트에서도 스킬이 걸리게 하려는 것이다 (모델의 자발적 트리거에 기대지 않는다).
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


def routing_lines(root, engine, home=None):
    """스킬 라우팅과 코드 찾기 — 이 프로젝트에 있는 것만, 명령 줄 그대로. 라우팅은 여기 한 곳에만 둔다.

    - 스킬 이름만 알려 주면 모델이 스킬을 부르지 않고 grep 으로 간다 — MNYS 실제 세션 61개에서 clangd 0회 · 위키 0회 ·
      grep 714회, game-onboard 0회(2026-10-20). 그래서 인덱스 명령을 경로째 준다(PowerShell 은 python 인자의 ~ 를 안 푼다).
    - 2026-10-22 대조 시험(tools/harness_probe.py, MNYS 정답지 8과제 × 2 + 스킬 사례 5, docs/experience/routing-single-source.md):
      CLAUDE.local.md 의 같은 라우팅 절을 빼도 스킬은 5/5 불렸다(그 절은 구조 질문을 위키로, 여기는 game-onboard 로 보내
      서로 어긋났다). 위키 먼저로 바꾸며 cindex 줄을 줄였더니 cindex 22 → 11 · Grep 28 → 41 로 나빠졌고, 줄을 그대로 두고
      "코드 세부는 cindex" 를 붙이니 cindex 22 · Grep 27 · 재현율 0.908 → 0.961, 비용 같음 — 그것이 이 모양이다.
    - game-patterns 는 game-architecture 에 합쳤다(0회 불림, description 992 B). gq 는 갱신되는 프로젝트에만 권한다."""
    home = Path(home) if home else Path.home()
    idx = root / ("Library" if engine.startswith("Unity") else "Saved") / "ClaudeIndex"
    onboard = f"python {(home / '.claude' / 'skills' / 'game-onboard' / 'scripts').as_posix()}"
    wiki = home / ".jokate-wiki" / root.name
    has_wiki = (wiki / "index.md").is_file()
    has_clangd = (idx / "clangd.sqlite").is_file()
    out = ["스킬 — 요청을 받으면 코드를 읽기 전에 맞는 스킬을 부른다:",
           "- 기능 추가 · 구현 · 설계 · 리팩터링 · 패턴 고르기 → game-architecture (구현 전 구조 조사 → 선택지와 근거 그림 → 사용자 선택까지 멈춤)",
           "- 기획서 읽기 · 사양 정리 · 기획과 구현 대조 → game-design-doc · 테스트 · 검증 → game-testing · 에디터 MCP 조작 → game-mcp",
           ("- 시스템 구조 · 동작 · 이유 질문 → 맥락은 위키 먼저(wiki-query, `" + wiki.as_posix() + "/index.md`), "
            + ("코드 세부(어디서 쓰나 · 누가 부르나 · 바꾸면 영향)는 아래 cindex 로 확인. " if has_clangd else "")
            + "위키에 없으면 game-onboard"
            if has_wiki else "- 구조 · 위치 · 엔진 API 질문 → game-onboard")]
    found = []
    if (idx / "symbols.json").is_file() and keeps_gq(root):
        found.append(f"- 어디에 있나 → `{onboard}/gq.py find <이름>` · 심볼 좌표 `gq.py sym <이름>`")
    if has_clangd:
        # 이 줄을 '부르는 곳 callers · 파생 derived' 처럼 줄이면 cindex 호출이 반으로 줄었다(위 대조) — 명령을 줄 그대로 둔다
        found.append(f"- 클래스 · 함수 · 구조체 이름을 grep 하기 전에: 쓰는 곳 `{onboard}/cindex.py refs <심볼>` · "
                     "누가 부르나 `cindex.py callers <심볼>` · 파생 `cindex.py derived <클래스>` · 바꾸면 영향 `cindex.py impact <심볼>` "
                     "(clangd 의미 인덱스, 컴파일 기준 — 주석 · 문자열 · 같은 이름이 안 섞이고 생성 코드는 빠진다. grep 으로 추측하지 않는다)")
    if found:
        out += ["코드 찾기 — grep · 파일 통째 읽기보다 인덱스 먼저 (하네스 모니터가 센다):", *found,
                "- 문자열 · 주석 · 설정값 · 로그 → rg"]
    return out


def pending_guards(root):
    """MCP 실패에서 모인 가드 규칙 후보가 있으면 한 줄(없으면 없음 — 항상 들어가는 글을 늘리지 않는다)."""
    try:
        n = len(json.loads((root / ".claude" / "mcp_guards.pending.json").read_text(encoding="utf-8")).get("pending") or [])
    except (OSError, ValueError, AttributeError):
        return []
    return [f"MCP 실패 {n}종이 가드 규칙 후보로 쌓여 있다(.claude/mcp_guards.pending.json) — 에디터 MCP 작업 전 game-mcp 로 검토한다."] if n else []


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
    lines += routing_lines(root, engine) + pending_guards(root)
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
