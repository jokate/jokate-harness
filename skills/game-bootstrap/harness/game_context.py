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
    lines += [
        "스킬 라우팅 — 요청을 받으면 조회·코드 읽기보다 먼저 해당 스킬을 부른다:",
        "- 기능 추가·구현·설계·리팩터링 요청 → game-architecture (구현 전 구조 조사, 선택지와 근거 그림, 사용자 선택까지 멈춤)",
        "- 구조·위치·엔진 API 질문 → game-onboard",
        "- 기획서 읽기·사양 정리·기획과 구현 대조 → game-design-doc",
        "- 패턴 비교·선택 → game-patterns · 테스트·검증 → game-testing · 에디터 MCP 조작 → game-mcp",
    ]
    if not (root / ".claude" / "session_start.json").is_file() and not (root / "CLAUDE.md").is_file():
        lines.append("이 프로젝트는 세팅 전이다 (CLAUDE.md·인덱스 갱신 없음). 필요하면 사용자에게 /game-bootstrap 을 안내한다.")
    sys.stdout.buffer.write("\n".join(lines).encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
