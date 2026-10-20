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
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"  # marked 12.0.2 · mermaid 11.17.2 (vendor/README.md)
CDN = {"marked": "https://cdn.jsdelivr.net/npm/marked@12/marked.min.js",
       "mermaid": "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"}

# 페이지 틀 — __TITLE__ · __STAMP__ · __RAW__ · __SCRIPTS__ · __MD__ 를 한 번에 바꿔 넣는다(page()).
# 절마다 카드, '한눈에' 는 강조 카드, 표는 둥근 테두리, 접힌 근거는 펼침 카드. 다크 모드: 시스템 설정을 따르고
# 오른쪽 위 버튼으로 자동 → 밝게 → 어둡게(브라우저에 기억). Mermaid 는 테마에 맞춰 다시 그리고,
# diagram-design 구조도(iframe)는 어두울 때 색을 뒤집어 맞춘다. 사용자: "딱딱하지 않게 예쁘게 · 다크 모드"(2026-10-20).
PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<script>try{var t=localStorage.getItem('gh-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;}catch(e){}</script>
<style>
:root{--bg:#f6f5f2;--card:#fff;--fg:#1d2125;--mute:#5f6b76;--line:#e4e2dc;--soft:#f1efea;--code:#f3f1ec;--accent:#bf4520;--tint:rgba(191,69,32,.07);--shadow:0 1px 2px rgba(29,33,37,.05);color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1215;--card:#171b20;--fg:#e4e7ea;--mute:#98a2ad;--line:#2a3037;--soft:#1d2228;--code:#1f252b;--accent:#f0875a;--tint:rgba(240,135,90,.10);--shadow:none;color-scheme:dark}}
:root[data-theme=dark]{--bg:#0f1215;--card:#171b20;--fg:#e4e7ea;--mute:#98a2ad;--line:#2a3037;--soft:#1d2228;--code:#1f252b;--accent:#f0875a;--tint:rgba(240,135,90,.10);--shadow:none;color-scheme:dark}
*{box-sizing:border-box}
html,body{background:var(--bg)}
body{margin:0;color:var(--fg);font:15.5px/1.7 "Pretendard Variable",Pretendard,"Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;word-break:keep-all;-webkit-font-smoothing:antialiased}
.wrap{max-width:920px;margin:0 auto;padding:36px 20px 72px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:6px}
.eyebrow{font-size:12px;letter-spacing:.06em;color:var(--mute)}
.theme{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:999px;padding:5px 14px;font:inherit;font-size:13px;cursor:pointer}
.theme:hover{border-color:var(--accent)} .theme:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
h1{font-size:30px;line-height:1.3;letter-spacing:-.02em;margin:4px 0 22px;text-wrap:balance}
h2{font-size:18px;line-height:1.4;margin:0 0 12px;display:flex;align-items:center;gap:10px}
h2::before{content:"";flex:none;width:4px;height:18px;border-radius:2px;background:var(--accent)}
h3{font-size:15px;margin:18px 0 8px}
section.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 24px;margin:0 0 16px;box-shadow:var(--shadow)}
section.card>:last-child{margin-bottom:0}
section.lead{background:var(--tint);border-color:transparent}
p{margin:8px 0} ul,ol{padding-left:1.3em;margin:8px 0} li{margin:5px 0} li::marker{color:var(--mute)}
strong{font-weight:650} a{color:var(--accent);text-underline-offset:2px}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:12px 0;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th{background:var(--soft);color:var(--mute);font-weight:600;font-size:12.5px;text-align:left;white-space:nowrap}
th,td{padding:9px 14px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0} tbody tr:hover td{background:var(--tint)}
code{font-family:ui-monospace,D2Coding,Consolas,monospace;font-size:.88em;background:var(--code);border-radius:5px;padding:1px 5px}
pre{background:var(--code);border-radius:10px;padding:14px 16px;overflow-x:auto;line-height:1.55} pre code{background:none;padding:0}
.mermaid{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0;overflow-x:auto;text-align:center;cursor:zoom-in}
.mermaid.zoom{cursor:zoom-out} .mermaid.zoom svg{max-width:none!important;width:auto!important;height:auto}
figure.dd{margin:12px 0} figure.dd iframe{display:block;width:100%;height:min(80vh,760px);min-height:420px;border:1px solid var(--line);border-radius:12px;background:#f5f5f5;resize:vertical}
.ddsvg{background:#f5f5f5;border:1px solid var(--line);border-radius:12px;padding:6px;overflow-x:auto;cursor:zoom-in}
.ddsvg.zoom{cursor:zoom-out} .ddsvg svg{display:block;width:100%;height:auto}
[data-scheme=dark] figure.dd iframe,[data-scheme=dark] .ddsvg{filter:invert(.9) hue-rotate(180deg)}
figure.dd figcaption{color:var(--mute);font-size:13px;margin-top:6px}
details.fold{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:0 0 16px}
details.fold>summary{list-style:none;cursor:pointer;padding:15px 24px;color:var(--mute);font-weight:600;display:flex;gap:10px;align-items:center}
details.fold>summary::-webkit-details-marker{display:none}
details.fold>summary::before{content:"\\25B8";transition:transform .15s}
details.fold[open]>summary::before{transform:rotate(90deg)}
details.fold>.body{padding:0 24px 20px}
section details:not(.more){margin-top:12px} section details:not(.more)>summary{cursor:pointer;color:var(--mute);font-size:13px}
details.more{display:inline} details.more>summary{display:inline;list-style:none;cursor:pointer;color:var(--accent);font-size:12.5px;margin-left:4px}
details.more>summary::-webkit-details-marker{display:none} details.more[open]>summary{display:none}
#raw{white-space:pre-wrap} .note{color:var(--mute);font-size:13px}
@media (max-width:640px){.wrap{padding:22px 16px 56px} h1{font-size:24px} section.card{padding:16px 18px}}
@media print{.theme{display:none} section.card,details.fold{break-inside:avoid;box-shadow:none}}
</style></head><body><div class="wrap">
<div class="top"><span class="eyebrow">__STAMP__</span><button class="theme" id="theme" type="button" aria-label="화면 테마 바꾸기">테마: 자동</button></div>
<div id="out"><pre id="raw">__RAW__</pre><p class="note">스크립트를 불러오지 못해 원문을 표시한다 (render.py 옆 vendor/ 폴더가 있는지, 또는 --js-dir).</p></div>
</div>
__SCRIPTS__
<script>
const md = __MD__;
const root = document.documentElement, out = document.getElementById('out');
const mq = matchMedia('(prefers-color-scheme: dark)');
const isDark = () => root.dataset.theme === 'dark' || (root.dataset.theme !== 'light' && mq.matches);
const LABEL = {auto: '자동', light: '밝게', dark: '어둡게'}, NEXT = {auto: 'light', light: 'dark', dark: 'auto'};
let mode = root.dataset.theme || 'auto';
const btn = document.getElementById('theme');
function applyTheme() {
  if (mode === 'auto') delete root.dataset.theme; else root.dataset.theme = mode;
  root.dataset.scheme = isDark() ? 'dark' : 'light';
  btn.textContent = '테마: ' + LABEL[mode];
}
async function drawMermaid() {
  if (!window.mermaid) return;
  const els = [...document.querySelectorAll('.mermaid')];
  mermaid.initialize({startOnLoad: false, theme: isDark() ? 'dark' : 'neutral',
                      fontFamily: '"Pretendard Variable", "Malgun Gothic", sans-serif'});
  els.forEach(el => { if (!el.dataset.src) el.dataset.src = el.textContent;
                      el.removeAttribute('data-processed'); el.textContent = el.dataset.src; });
  try { await mermaid.run({nodes: els}); } catch (e) {}
  // 그림을 누르면 원래 크기로 (큰 그림이 화면 폭에 맞춰 줄어 글자가 작을 때)
  els.forEach(el => { el.title = '누르면 크게 / 다시 누르면 맞춤'; el.onclick = () => el.classList.toggle('zoom'); });
}
function decorate() {
  // 절(h2)마다 카드로 묶는다. 제목 앞 글은 첫 카드, 접힌 근거는 펼침 카드.
  let sec = null;
  for (const n of [...out.childNodes]) {
    const tag = n.nodeType === 1 ? n.tagName : '';
    const sum = tag === 'DETAILS' && n.querySelector('summary') ? n.querySelector('summary').textContent.trim() : '';
    if (tag === 'H1' || /^(근거|전체 내용)/.test(sum)) { sec = null; continue; }  // 'Mermaid 원본' 등은 그 절 카드 안에 둔다
    if (tag === 'H2' || (!sec && (tag || n.textContent.trim()))) {
      sec = document.createElement('section'); sec.className = 'card';
      if (tag === 'H2' && /^[0-9. ]*(한눈에|결론|요약)/.test(n.textContent.trim())) sec.classList.add('lead');
      out.insertBefore(sec, n);
    }
    if (sec) sec.appendChild(n);
  }
  document.querySelectorAll('.ddsvg').forEach(el => {  // 구조도도 누르면 원래 크기(가로 스크롤)
    el.title = '누르면 크게 / 다시 누르면 맞춤';
    el.onclick = () => { const s = el.querySelector('svg'), z = el.classList.toggle('zoom');
      if (s) s.style.width = z && s.viewBox && s.viewBox.baseVal ? s.viewBox.baseVal.width + 'px' : ''; };
  });
  out.querySelectorAll(':scope > details').forEach(d => {
    d.classList.add('fold');
    const body = document.createElement('div'); body.className = 'body';
    [...d.childNodes].filter(n => n.tagName !== 'SUMMARY').forEach(n => body.appendChild(n));
    d.appendChild(body);
  });
  out.querySelectorAll('table').forEach(t => {
    const w = document.createElement('div'); w.className = 'tbl'; t.parentNode.insertBefore(w, t); w.appendChild(t);
  });
}
applyTheme();
btn.onclick = () => { mode = NEXT[mode]; try { localStorage.setItem('gh-theme', mode); } catch (e) {} applyTheme(); drawMermaid(); };
mq.addEventListener('change', () => { if (mode === 'auto') { applyTheme(); drawMermaid(); } });
if (window.marked) {
  const r = new marked.Renderer(), code = r.code.bind(r);
  r.code = (t, lang) => { const x = typeof t === 'object' ? t : {text: t, lang};
    return x.lang === 'mermaid' ? '<div class="mermaid">' + x.text.replace(/</g,'&lt;') + '</div>' : code(t, lang); };
  out.innerHTML = marked.parse(md, {renderer: r});
  decorate();
  drawMermaid();
}
</script></body></html>
"""


def page(**vals):
    """PAGE 의 __이름__ 자리를 한 번에 바꾼다(바꿔 넣은 글 안의 같은 모양은 건드리지 않는다)."""
    return re.sub(r"__(TITLE|STAMP|RAW|SCRIPTS|MD)__", lambda m: vals[m.group(1).lower()], PAGE)


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


DD_EXPORT = Path.home() / ".claude" / "skills" / "diagram-design" / "scripts" / "export_svg.py"


def dd_svg(fig):
    """diagram-design 구조도 HTML → 문서에 바로 넣을 SVG 글. diagram-design 의 export_svg.py 가
    스타일을 SVG 안에 담고 정의 ID 에 파일 이름을 붙여 준다(여러 장이 한 문서에 있어도 안 섞인다).
    결과는 옆에 <이름>.svg 로 두고 구조도가 바뀔 때만 다시 만든다. 도구가 없거나 실패하면 None."""
    svg = Path(fig).with_suffix(".svg")
    try:
        if not svg.is_file() or svg.stat().st_mtime < Path(fig).stat().st_mtime:
            if not DD_EXPORT.is_file():
                return None
            r = subprocess.run([sys.executable, str(DD_EXPORT), str(fig), str(svg)], capture_output=True, timeout=60,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            if r.returncode != 0 or not svg.is_file():
                return None
        text = svg.read_text(encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        return None
    i = text.find("<svg")
    if i < 0:
        return None
    # 마크다운의 HTML 덩어리는 빈 줄에서 끝나므로 빈 줄을 없앤다
    return "\n".join(ln for ln in text[i:].splitlines() if ln.strip())


def embed_figs(md, figs, out_dir):
    """'그림' 절 맨 앞에 diagram-design 구조도를 끼워 넣는다. 그 절의 Mermaid 는 원본 코드로 접는다
    (닫힌 <details> 안에서는 mermaid 가 크기를 못 재므로 그리지 않고 글로 둔다). '그림' 절이 없으면 새로 만든다."""
    if not figs:
        return md
    tags = []
    for p in figs:
        rel = urllib.parse.quote(os.path.relpath(p, out_dir).replace(os.sep, "/"))
        svg = dd_svg(p)
        # SVG 를 문서에 바로 넣으면 폭에 맞춰 Before · 바뀌는 것 · After 가 한눈에 보인다. 못 꺼내면 iframe 으로
        body = f'<div class="ddsvg">{svg}</div>' if svg else \
            f'<iframe src="{rel}" loading="lazy" title="{html.escape(p.stem)}" onload="{FIT}"></iframe>'
        cap = re.search(r"<title[^>]*>(.*?)</title>", svg or "", re.S)
        cap = cap.group(1).strip() if cap else html.escape(p.stem)  # SVG 제목(이미 이스케이프된 글) → 없으면 파일 이름
        tags.append(f'<figure class="dd">{body}'
                    f'<figcaption>{cap} · <a href="{rel}" target="_blank">새 창으로 크게</a></figcaption></figure>')
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
    stamp = f"{Path(src).name if src else out.stem} · {time.strftime('%Y-%m-%d %H:%M')}"
    out.write_text(page(title=html.escape(title), stamp=html.escape(stamp), raw=html.escape(md),
                        md=json.dumps(md).replace("</", "<\\/"), scripts=scripts(js_dir)),
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
