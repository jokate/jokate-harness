#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown(+Mermaid) → 단일 HTML. SVN 처럼 .md 를 렌더하지 않는 환경이나, Mermaid 를 그리지 않는 Claude Code 대화창 대신 브라우저로 연다.

  python render.py <입력.md> [-o 출력.html] [--js-dir <폴더>] [--open]

스크립트(marked·mermaid)는 이 폴더의 vendor/ 에 동봉돼 있다 — 설치할 것이 없고 인터넷이 없어도 그려진다.
HTML 은 동봉 파일을 먼저 불러오고, 못 불러오면(다른 PC 로 HTML 만 옮긴 경우) CDN 으로 넘어간다.
--js-dir 를 주면 그 폴더의 marked.min.js, mermaid.min.js 만 쓴다. 어느 쪽도 못 불러오면 원문을 그대로 보인다.
Stop 훅 diagram_view.py 가 이 모듈의 render()·open_file() 을 쓴다.
"""

import argparse
import glob
import html
import json
import os
import re
import sys
import urllib.parse
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"  # marked 12.0.2 · mermaid 11.17.2 (vendor/README.md)
CDN = {"marked": "https://cdn.jsdelivr.net/npm/marked@12/marked.min.js",
       "mermaid": "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"}

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#fff;--fg:#1f2328;--mute:#59636e;--line:#d1d9e0;--code:#f6f8fa}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--fg:#e6edf3;--mute:#9198a1;--line:#3d444d;--code:#151b23}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,"Malgun Gothic",sans-serif;max-width:980px;margin:0 auto;padding:24px 16px}}
table{{border-collapse:collapse;display:block;overflow-x:auto}} th,td{{border:1px solid var(--line);padding:4px 10px}}
code,pre{{background:var(--code);border-radius:4px}} pre{{padding:12px;overflow-x:auto}} code{{padding:1px 4px}}
.mermaid{{background:#fff;border:1px solid var(--line);border-radius:6px;padding:8px;margin:12px 0;overflow-x:auto}}
#raw{{white-space:pre-wrap}} .note{{color:var(--mute);font-size:13px}}
details{{border-top:1px solid var(--line);margin-top:20px;padding-top:8px}} summary{{color:var(--mute);cursor:pointer}}
.mermaid{{cursor:zoom-in}} .mermaid.zoom{{cursor:zoom-out}} .mermaid.zoom svg{{max-width:none!important;width:auto!important;height:auto}}
figure.dd{{margin:12px 0}} figure.dd iframe{{width:100%;height:min(80vh,760px);min-height:420px;border:1px solid var(--line);border-radius:6px;background:#fff;resize:vertical}}
figure.dd figcaption{{color:var(--mute);font-size:13px}}
</style></head><body>
<div id="out"><pre id="raw">{raw}</pre><p class="note">스크립트를 불러오지 못해 원문을 표시한다 (render.py 옆 vendor/ 폴더가 있는지, 또는 --js-dir).</p></div>
{scripts}
<script>
const md = {md_json};
if (window.marked) {{
  const r = new marked.Renderer(), code = r.code.bind(r);
  r.code = (t, lang) => {{ const x = typeof t === 'object' ? t : {{text: t, lang}};
    return x.lang === 'mermaid' ? '<div class="mermaid">' + x.text.replace(/</g,'&lt;') + '</div>' : code(t, lang); }};
  document.getElementById('out').innerHTML = marked.parse(md, {{renderer: r}});
  if (window.mermaid) {{ mermaid.initialize({{startOnLoad:false, theme:'default'}});
    // 그림을 누르면 원래 크기로 (큰 그림이 화면 폭에 맞춰 줄어 글자가 작을 때)
    Promise.resolve(mermaid.run()).then(() => document.querySelectorAll('.mermaid').forEach(el => {{
      el.title = '누르면 크게 / 다시 누르면 맞춤'; el.onclick = () => el.classList.toggle('zoom'); }})); }}
}}
</script></body></html>
"""


def scripts(js_dir=None):
    """<script> 태그들. --js-dir 이면 그 폴더만, 아니면 동봉 파일 → (못 불러오면) CDN."""
    if js_dir:
        d = Path(js_dir).resolve()
        return "".join(f'<script src="{html.escape((d / f"{k}.min.js").as_uri())}"></script>' for k in CDN)
    local = {"marked": VENDOR / "marked.min.js", "mermaid": VENDOR / "mermaid.min.js"}
    tags = "".join(f'<script src="{html.escape(p.as_uri())}"></script>' for p in local.values() if p.is_file())
    # 동봉 파일을 못 읽었을 때만 CDN 을 붙인다 (document.write 는 파싱 중이라 다음 스크립트보다 먼저 실행된다)
    fallback = "".join(
        f"if (!window.{k}) document.write('<script src=\"{u}\"><\\/script>');" for k, u in CDN.items())
    return tags + f"<script>{fallback}</script>"


# 먼저 보일 절, 이 순서로 — 제목 앞 번호와 뒤 설명은 무시하고 앞 낱말로 맞춘다("## 6. 선택지 — …" → 선택지).
# 나머지(요청 축 · 확장 지점 · 신호 · 설계 노트 · 검증 …)는 접힌 '근거'로.
FRONT = (("결론", "한눈에", "요약"), ("선택지",), ("그림", "현재 구조"), ("질문", "결정", "사용자 결정", "고를 것"))
VISIBLE_MAX = 30  # 첫 화면(접힌 근거 위) 글 줄 수 기준 — 그림 한 장은 한 줄로 센다
LONG = 120  # 보이는 부분에서 이보다 긴 줄은 첫 문장만 보이고 나머지는 '더보기'로 접는다


def _sec_name(head):
    t = re.sub(r"^\d+(\.\d+)*\.?\s*", "", head.lstrip("#").strip())
    return re.split(r"\s+[—–]\s+|\s+-\s+|\s*\(", t)[0].strip()


def _front_rank(name):
    return next((r for r, keys in enumerate(FRONT) if name.startswith(keys)), None)


def _fold_long(text, limit=LONG):
    """긴 목록 · 글 줄을 '첫 문장 + 접힌 나머지' 로. 코드 블록 · 표 · 제목은 그대로."""
    out, fence = [], None
    for ln in text.splitlines():
        s = ln.strip()
        if fence or re.match(r"(`{3,}|~{3,})", s):
            if fence and s.startswith(fence):
                fence = None
            elif not fence:
                fence = re.match(r"(`{3,}|~{3,})", s).group(1)
            out.append(ln)
            continue
        if len(s) <= limit or s.startswith(("#", "|", "<", ">")):
            out.append(ln)
            continue
        m = re.search(r"[.!?](?=\s)", ln[12:])  # 앞 12자 안의 마침표(번호 · 약어)는 문장 끝으로 안 본다
        cut = m.end() + 12 if m else -1
        if cut <= 0 or len(ln) - cut < 15:
            out.append(ln)
            continue
        out.append(f"{ln[:cut]} <details class=\"more\"><summary>더보기</summary>{ln[cut:].strip()}</details>")
    return "\n".join(out)


def summary_first(md):
    """game-architecture 답변이면 결론 · 선택지 · 그림 · 결정 절을 위로, 나머지 절은 접힌 <details> 하나로 내린다.
    보이는 절의 긴 줄은 첫 문장만 남기고 접는다. 긴 줄글 HTML 이 읽기 힘들다는 사용자 피드백(2026-10-20).
    '선택지' 절이 없는 글은 그대로 둔다."""
    lines = md.splitlines()
    heads = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    if not any(_sec_name(lines[i]).startswith("선택지") for i in heads):
        return md
    pre = "\n".join(lines[:heads[0]]).rstrip()
    secs = []
    for n, i in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        secs.append((_sec_name(lines[i]), n, "\n".join(lines[i:end]).rstrip()))
    front = sorted((s for s in secs if _front_rank(s[0]) is not None), key=lambda s: (_front_rank(s[0]), s[1]))
    rest = [s for s in secs if _front_rank(s[0]) is None]
    out = ([_fold_long(pre)] if pre else []) + [_fold_long(t) for _, _, t in front]
    if rest:
        subs = lambda t: [_sec_name(ln) for ln in t.splitlines() if ln.startswith("### ")]  # noqa: E731
        names = " · ".join(n for name, _, t in rest for n in (subs(t) if name == "근거" else [name]))
        out.append(f"<details><summary>근거 — {names}</summary>\n\n" + "\n\n".join(t for _, _, t in rest) + "\n\n</details>")
    return "\n\n".join(out) + "\n"


def check(md, figs=None):
    """읽기 점검 — 보이는 부분(접힌 근거 위) 줄 수 · 긴 줄 수 · 근거 밖 절 · 구조도 장 수.
    render.py 와 Stop 훅이 출력해 모델이 고칠 근거로 쓴다. 구조 조사 문서(선택지 절이 있는 글)가 아니면 절 · 구조도는 안 본다."""
    view = MERMAID.sub("(그림)", readable(md).split("<details>")[0])
    vis = [ln for ln in view.splitlines() if ln.strip()]
    long_ = [ln for ln in _prose(md, clip=False) if len(ln) > LONG]
    names = [_sec_name(ln) for ln in md.splitlines() if ln.startswith("## ")]
    arch = any(n.startswith("선택지") for n in names)
    extra = [n for n in names if _front_rank(n) is None and n != "근거"] if arch else []  # '근거' 에서 끝난다
    return {"visible_lines": len(vis), "long_lines": len(long_), "extra_sections": extra,
            "figures": len(figs or []) if arch else None}


def report(c):
    """check() 결과 → (한 줄, 기준 안인가)."""
    ok = c["visible_lines"] <= VISIBLE_MAX and c["long_lines"] == 0 and not c["extra_sections"] and c["figures"] != 0
    line = f"읽기 점검: 첫 화면 {c['visible_lines']}줄(기준 {VISIBLE_MAX} 이하) · {LONG}자 넘는 줄 {c['long_lines']}개(기준 0)"
    if c["figures"] is not None:
        line += f" · 근거 밖 절 {len(c['extra_sections'])}개(기준 0" + (
            ": " + ", ".join(c["extra_sections"]) if c["extra_sections"] else "") + ")"
        line += f" · 구조도 {c['figures']}장(기준 1 이상 — diagram-design Before/After, <문서 이름>{FIG_SUFFIX}-<선택지>.html)"
    return line + ("" if ok else " — 넘었다. SKILL.md '읽기 규칙'대로 고쳐 다시 저장 · 렌더한다"), ok


MERMAID = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*mermaid[ \t]*\r?\n.*?^[ \t]*\1[ \t]*$", re.M | re.S)
SUMMARY_LINES = 3


def _prose(md, clip=True):
    """요약 후보 줄 — 코드 블록 · 표 · 제목 · HTML · 인용 · 구분선을 뺀 글."""
    out, fence = [], None
    for ln in md.splitlines():
        s = ln.strip()
        if fence:
            fence = None if s.startswith(fence) else fence
            continue
        m = re.match(r"(`{3,}|~{3,})", s)
        if m:
            fence = m.group(1)
            continue
        if s and not s.startswith(("#", "|", "<", ">")) and not set(s) <= set("-=*_ "):
            out.append(s if not clip or len(s) <= 140 else s[:139] + "…")
    return out


def diagram_first(md, keep=SUMMARY_LINES):
    """그림이 든 글(구조 문서 · 답변)을 '제목 → 요약 몇 줄 → 그림 → 접힌 전체 내용' 으로. 그림이 없으면 그대로.
    그림 제목은 그 블록 바로 앞의 소제목. 긴 HTML 이 볼 때마다 불편하다는 사용자 피드백(2026-10-20)."""
    blocks = list(MERMAID.finditer(md))
    if not blocks:
        return md
    title = next((ln for ln in md.splitlines() if ln.startswith("# ")), "")
    lead = _prose(md[:blocks[0].start()]) or _prose(md)  # 첫 그림 앞의 글을 먼저
    summary = [s if re.match(r"([-*]|\d+\.) ", s) else "- " + s for s in lead[:keep]]
    figs = []
    for i, m in enumerate(blocks, 1):
        heads = [ln.lstrip("#").strip() for ln in md[:m.start()].splitlines() if re.match(r"#{2,4} ", ln)]
        figs.append(f"### {heads[-1] if heads else f'그림 {i}'}\n\n{m.group(0).strip()}")
    n = iter(range(1, len(blocks) + 1))
    rest = MERMAID.sub(lambda m: f"*(위 그림 {next(n)})*", md)
    rest = "\n".join(ln for ln in rest.splitlines() if ln != title).strip()
    out = ([title] if title else []) + (["\n".join(summary)] if summary else []) + figs
    out.append(f"<details><summary>전체 내용</summary>\n\n{rest}\n\n</details>")
    return "\n\n".join(out) + "\n"


def readable(md):
    """기본 보기: game-architecture 답변이면 summary_first, 그 밖에 그림이 든 글이면 diagram_first."""
    s = summary_first(md)
    return s if s is not md else diagram_first(md)


# 같은 출처로 열리면(웹 서버) 그림 높이에 맞춘다. file:// 은 브라우저가 막아 CSS 높이를 그대로 쓴다
FIT = "try{this.style.height=this.contentDocument.documentElement.scrollHeight+'px'}catch(e){}"
FIG_SUFFIX = "-구조"  # diagram-design 이 그린 Before/After 구조도: <문서 이름>-구조[-<선택지>].html, 문서와 같은 폴더


def dd_figs(src, exclude=None):
    """문서 옆의 diagram-design 구조도 파일들. 없으면 []."""
    if not src:
        return []
    src = Path(src)
    try:
        return sorted(p for p in src.parent.glob(f"{glob.escape(src.stem)}{FIG_SUFFIX}*.html")
                      if exclude is None or p.resolve() != Path(exclude).resolve())
    except OSError:
        return []


def embed_figs(md, figs, out_dir):
    """'그림' 절 맨 앞에 diagram-design 구조도를 끼워 넣는다. 그 절의 Mermaid 는 원본 코드로 접는다
    (닫힌 <details> 안에서는 mermaid 가 크기를 못 재므로 그리지 않고 글로 둔다). '그림' 절이 없으면 새로 만든다."""
    if not figs:
        return md
    tags = []
    for p in figs:
        rel = urllib.parse.quote(os.path.relpath(p, out_dir).replace(os.sep, "/"))
        tags.append(f'<figure class="dd"><iframe src="{rel}" loading="lazy" title="{html.escape(p.stem)}" onload="{FIT}"></iframe>'
                    f'<figcaption>{html.escape(p.stem)} · <a href="{rel}" target="_blank">새 창으로 크게</a></figcaption></figure>')
    block = "\n\n".join(tags)
    lines = md.splitlines()
    heads = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    at = next((n for n, i in enumerate(heads) if _sec_name(lines[i]).startswith(FRONT[2])), None)  # 그림 · 현재 구조
    if at is None:
        return md.rstrip() + f"\n\n## 그림\n\n{block}\n"
    i, end = heads[at], heads[at + 1] if at + 1 < len(heads) else len(lines)
    body = "\n".join(lines[i + 1:end]).strip()
    if body:
        src = re.sub(r"^([ \t]*(?:`{3,}|~{3,})[ \t]*)mermaid", r"\1text", body, flags=re.M)
        block += f"\n\n<details><summary>Mermaid 원본</summary>\n\n{src}\n\n</details>"
    return "\n".join(lines[:i + 1] + ["", block, ""] + lines[end:]) + "\n"


def render(md, out, title, js_dir=None, full=False, src=None):
    """src(원본 .md 경로)를 주면 옆의 diagram-design 구조도(<이름>-구조*.html)를 '그림' 절에 끼워 넣는다."""
    md = embed_figs(md, dd_figs(src, exclude=out), Path(out).parent)
    md = md if full else readable(md)
    out = Path(out)
    out.write_text(PAGE.format(title=html.escape(title), raw=html.escape(md),
                               md_json=json.dumps(md).replace("</", "<\\/"), scripts=scripts(js_dir)),
                   encoding="utf-8")
    return out


def open_file(path):
    """기본 브라우저로 연다. 실패하면 이유 문자열, 성공하면 None."""
    try:
        if os.name == "nt":
            os.startfile(str(Path(path).resolve()))  # noqa: S606 — 기본 브라우저로 연다
        elif not webbrowser.open(Path(path).resolve().as_uri()):
            return "브라우저를 찾지 못했다"
    except OSError as e:
        return str(e)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out")
    ap.add_argument("--js-dir")
    ap.add_argument("--open", action="store_true", help="만든 HTML 을 기본 브라우저로 연다")
    ap.add_argument("--full", action="store_true",
                    help="절 순서를 바꾸지 않고 전부 펼친다 (기본: 선택지 · 그림 먼저, 그 밖의 글은 요약 · 그림 먼저, 나머지는 접기)")
    a = ap.parse_args()
    src = Path(a.src)
    md = src.read_text(encoding="utf-8")
    title = next((ln.lstrip("# ").strip() for ln in md.splitlines() if ln.startswith("# ")), src.stem)
    out = render(md, a.out or src.with_suffix(".html"), title, a.js_dir, a.full, src=src)
    print(out)
    print(report(check(md, dd_figs(src, exclude=out)))[0])
    if a.open:
        err = open_file(out)
        if err:
            print(f"열지 못했다 ({err}). 위 경로를 브라우저로 직접 연다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
