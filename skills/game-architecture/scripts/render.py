#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown(+Mermaid) → 단일 HTML. SVN 처럼 .md 를 렌더하지 않는 환경이나, Mermaid 를 그리지 않는 Claude Code 대화창 대신 브라우저로 연다.

  python render.py <입력.md> [-o 출력.html] [--js-dir <폴더>] [--open]
  python render.py <입력.md> --form [--project <루트>]     문서와 고르기 양식을 한 페이지로 띄운다
  python render.py --attach <HTML…> [--project <루트>]     남이 쓴 HTML 에 문서 메모 칸을 붙인다 (--detach 로 뗀다)

스크립트(marked·mermaid)는 이 폴더의 vendor/ 에 동봉돼 있다 — 설치할 것이 없고 인터넷이 없어도 그려진다.
HTML 은 동봉 파일을 먼저 불러오고, 못 불러오면(다른 PC 로 HTML 만 옮긴 경우) CDN 으로 넘어간다.
--js-dir 를 주면 그 폴더의 marked.min.js, mermaid.min.js 만 쓴다. 어느 쪽도 못 불러오면 원문을 그대로 보인다.
game-architecture 가 구조 문서를 저장한 뒤 `render.py --form` 으로 쓴다.

--form 은 문서의 '선택지' · '질문' 절을 고르기 양식으로 옮겨 문서와 한 페이지에 낸다(selection 의 decide.py 서버).
읽는 곳(그림 · 근거)과 고르는 곳(안마다 고름 · 기각 · 피드백)이 한 탭이다. Enter 로 보내면 이 명령이 답을 찍고 끝난다.
선택지 절이 없거나 못 읽으면 문서만 연다. 무인 실행이면 문서만 만들고 띄우지 않는다(끝 코드 4).

만든 HTML 에는 문서 메모 칸(notes.html)이 붙는다. 나중에 보다가 이상한 곳을 긋거나 제목 옆 ✎ 를 눌러 적는다.
'Claude 로 열기'는 claude-cli:// 주소로 그 프로젝트에 새 세션을 열고 요청을 채운다. '복사'는 같은 글을 클립보드에 둔다.
"""

import argparse
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import webbrowser
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # 한글 Windows 콘솔(cp949)에서 읽기 점검 줄의 '—' 를 못 찍어 죽었다
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"  # marked 12.0.2 · mermaid 11.17.2 (vendor/README.md)
CDN = {"marked": "https://cdn.jsdelivr.net/npm/marked@12/marked.min.js",
       "mermaid": "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"}

# 페이지 틀 — __TITLE__ · __STAMP__ · __RAW__ · __SCRIPTS__ · __MD__ 를 한 번에 바꿔 넣는다(page()).
# 절마다 카드, '한눈에' 는 강조 카드, 표는 둥근 테두리, 접힌 근거는 펼침 카드. 다크 모드: 시스템 설정을 따르고
# 오른쪽 위 버튼으로 자동 → 밝게 → 어둡게(브라우저에 기억). Mermaid 는 테마에 맞춰 다시 그리고,
# diagram-design 구조도(iframe)는 어두울 때 색을 뒤집어 맞춘다. 사용자: "딱딱하지 않게 예쁘게 · 다크 모드"(2026-10-20).
PAGE = """<!doctype html>
<html lang="ko"__EMBED__><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
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
html[data-embed]{--bg:#f6f7f9}
@media (prefers-color-scheme:dark){html[data-embed]:not([data-theme=light]){--bg:#14171d}}
[data-embed] .top,[data-embed] h1{display:none} [data-embed] .wrap{max-width:none;padding:0}
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
</script>
__NOTES__
</body></html>
"""


def page(**vals):
    """PAGE 의 __이름__ 자리를 한 번에 바꾼다(바꿔 넣은 글 안의 같은 모양은 건드리지 않는다)."""
    vals.setdefault("embed", "")
    vals.setdefault("notes", "")
    return re.sub(r"__(TITLE|STAMP|RAW|SCRIPTS|MD|EMBED|NOTES)__", lambda m: vals[m.group(1).lower()], PAGE)


def scripts(js_dir=None, url_for=None):
    """<script> 태그들. --js-dir 이면 그 폴더만, 아니면 동봉 파일 → (못 불러오면) CDN.
    url_for(파일) → 주소 를 주면 동봉 파일을 그 주소로 부른다 — 양식 서버가 내보낸 http 페이지는 file:// 을 못 읽는다."""
    if js_dir:
        d = Path(js_dir).resolve()
        return "".join(f'<script src="{html.escape((d / f"{k}.min.js").as_uri())}"></script>' for k in CDN)
    local = {"marked": VENDOR / "marked.min.js", "mermaid": VENDOR / "mermaid.min.js"}
    src = url_for or (lambda p: p.as_uri())
    tags = "".join(f'<script src="{html.escape(src(p))}"></script>' for p in local.values() if p.is_file())
    # 동봉 파일을 못 읽었을 때만 CDN 을 붙인다 (document.write 는 파싱 중이라 다음 스크립트보다 먼저 실행된다)
    fallback = "".join(
        f"if (!window.{k}) document.write('<script src=\"{u}\"><\\/script>');" for k, u in CDN.items())
    return tags + f"<script>{fallback}</script>"


# 먼저 보일 절, 이 순서로 — 제목 앞 번호와 뒤 설명은 무시하고 앞 낱말로 맞춘다("## 6. 선택지 — …" → 선택지).
# 나머지(요청 축 · 확장 지점 · 신호 · 설계 노트 · 검증 …)는 접힌 '근거'로.
FIG_HEADS = ("그림", "현재 구조")
FRONT = (("결론", "한눈에", "요약"), ("선택지",), ("반대",), FIG_HEADS, ("질문", "결정", "사용자 결정", "고를 것"))
VISIBLE_MAX = 30  # 첫 화면(접힌 근거 위) 글 줄 수 기준 — 그림 한 장은 한 줄로 센다
LONG = 120  # 보이는 부분에서 이보다 긴 줄은 첫 문장만 보이고 나머지는 '더보기'로 접는다
# 사람이 못 읽는 버릇 세 가지 (docs/READING.md). 기준값은 docs/VERIFICATION.md 의 사용자 지적 문서 측정에서 정했다.
PACK_DOTS, PACK_PARENS = 3, 2  # 한 줄에 가운뎃점 3개 이상 또는 괄호 2개 이상이면 사실을 몰아 쓴 줄
DATE_TAG = re.compile(
    r"\[[^\]\n]{0,20}?(?:\d{2}-\d{2}|\d{1,2}시|\d{1,2}:\d{2})[^\]\n]{0,20}\]"  # [10-24] · [18시 갱신 · 21:50]
    r"|\((?:사용자 )?(?:결정|갱신|확인)[^)\n]{0,12}\d{4}-\d{2}-\d{2}\)"        # (사용자 결정 2026-11-03)
    r"|\d{1,2}:\d{2}\s*(?:갱신|뒤|이후)")                                        # 16:34 뒤
WORK_ID = re.compile(r"\btask_[0-9a-f]{6,}\b|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")  # 작업 · 커밋 번호
FIVE_W = re.compile(r"^\|\s*누가\s*\|.*언제.*어디서.*무엇.*어떻게.*왜", re.M)  # 근거 육하원칙 표 머리줄
WHY_SLOTS = ("문제", "버린 안", "대가", "뒤집는 조건")  # 추천 밑 결정 블록 (docs/READING.md)
CHOICE_HEADS = ("선택지", "고를 것")  # 고를 것: 릴레이 GUIDE 의 결재 양식. 이 절이 있으면 추천 · 왜 · 근거 표를 본다
RECOMMEND = re.compile(r"^\s*(?:#{1,6}\s*)?(?:[-*]\s*)?\**추천\**\s*(?:[:：]|[—–]\s)", re.M)
# '언제' 칸에 문서를 쓰거나 검토한 때를 적은 줄("구조 검토 시점"). 코드가 불리는 때 · 확인한 날짜 · 커밋은 통과한다
VAGUE_WHEN = re.compile(r"검토|작성|문서|조사")
REAL_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|\b[0-9a-f]{7,40}\b|\b(?:task|inb|run)_\w+")


def _sec_name(head):
    t = re.sub(r"^\d+(\.\d+)*\.?\s*", "", head.lstrip("#").strip())
    return re.split(r"\s+[—–]\s+|\s+-\s+|\s*\(", t)[0].strip()


def _front_rank(name, hide=()):
    if hide and name.startswith(tuple(hide)):
        return None
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


def summary_first(md, hide=()):
    """game-architecture 답변이면 결론 · 선택지 · 그림 · 결정 절을 위로, 나머지 절은 접힌 <details> 하나로 내린다.
    보이는 절의 긴 줄은 첫 문장만 남기고 접는다. 긴 줄글 HTML 이 읽기 힘들다는 사용자 피드백(2026-10-20).
    '선택지' 절이 없는 글은 그대로 둔다. hide 로 시작하는 절은 위에 두지 않고 접는다(양식이 그 절을 카드로 보일 때)."""
    lines = md.splitlines()
    heads = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    if not any(_sec_name(lines[i]).startswith("선택지") for i in heads):
        return md
    pre = "\n".join(lines[:heads[0]]).rstrip()
    secs = []
    for n, i in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        secs.append((_sec_name(lines[i]), n, "\n".join(lines[i:end]).rstrip()))
    front = sorted((s for s in secs if _front_rank(s[0], hide) is not None), key=lambda s: (_front_rank(s[0], hide), s[1]))
    rest = [s for s in secs if _front_rank(s[0], hide) is None]
    out = ([_fold_long(pre)] if pre else []) + [_fold_long(t) for _, _, t in front]
    if rest:
        subs = lambda t: [_sec_name(ln) for ln in t.splitlines() if ln.startswith("### ")]  # noqa: E731
        names = " · ".join(n for name, _, t in rest for n in (subs(t) if name == "근거" else [name]))
        out.append(f"<details><summary>근거 — {names}</summary>\n\n" + "\n\n".join(t for _, _, t in rest) + "\n\n</details>")
    return "\n\n".join(out) + "\n"


def _packed(line):
    return line.count("·") >= PACK_DOTS or line.count("(") >= PACK_PARENS


def _no_code(md):
    """코드 블록(mermaid 포함)을 뺀 글 — 꼬리표 · 번호 검사용."""
    out, fence = [], None
    for ln in md.splitlines():
        m = re.match(r"\s*(`{3,}|~{3,})", ln)
        if fence:
            fence = None if m and m.group(1).startswith(fence) else fence
        elif m:
            fence = m.group(1)
        else:
            out.append(ln)
    return "\n".join(out)


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _five_w_tables(text):
    """육하원칙 표마다 (머리줄 칸, 본문 줄의 칸들, 표가 차지한 줄 번호들)."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        if not FIVE_W.match(lines[i]):
            i += 1
            continue
        head, rows, idx = _cells(lines[i]), [], [i]
        i += 1
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            idx.append(i)
            if not re.fullmatch(r"\s*\|[\s:|-]*", lines[i]):
                rows.append(_cells(lines[i]))
            i += 1
        out.append((head, rows, idx))
    return out


DECISION_HEAD = re.compile(r"^(#{2,4})\s*(?:미)?결정\s*[:：]")  # docs/READING.md '결정 블록'의 머리


def _decision_blocks(md):
    """'### 결정: …' 블록마다 머리 아래 글. 같은 단계 이상의 다음 제목에서 끝난다."""
    lines, out = _no_code(md).splitlines(), []
    for i, ln in enumerate(lines):
        m = DECISION_HEAD.match(ln)
        if not m:
            continue
        j = i + 1
        while j < len(lines) and not re.match(rf"^#{{1,{len(m.group(1))}}}\s", lines[j]):
            j += 1
        out.append("\n".join(lines[i + 1:j]))
    return out


def _block_complete(block):
    slots = all(re.search(rf"^\s*[-*]\s*\**{s}\**\s*:", block, re.M) for s in WHY_SLOTS)
    return slots and bool(FIVE_W.search(block))


def _vague_when(tables):
    n = 0
    for head, rows, _ in tables:
        if "언제" not in head:
            continue
        k = head.index("언제")
        for row in rows:
            cell = row[k] if k < len(row) else ""
            if VAGUE_WHEN.search(cell) and not REAL_WHEN.search(cell):
                n += 1
    return n


def check(md, figs=None):
    """읽기 점검 — 보이는 부분(접힌 근거 위) 줄 수 · 긴 줄 · 몰아 쓴 줄 · 날짜 꼬리표 · 번호 · 근거 밖 절 · 구조도 · 육하원칙 표.
    render.py 가 출력해 모델이 고칠 근거로 쓴다. 기준은 첫 화면만 본다(근거 쪽 몰아 쓴 줄은 수만 알린다).
    날짜 꼬리표는 문서 어디에도 두지 않는다. 선택지나 고를 것 절이 있으면 추천 · 왜 칸 · 육하원칙 표를 본다.
    절 · 구조도는 선택지 절이 있는 구조 조사 문서만 본다. 육하원칙 표의 '언제' 칸은 표가 있으면 어디서든 본다."""
    front = readable(md).split("<details>")[0]
    view = MERMAID.sub("(그림)", front)
    vis = [ln for ln in view.splitlines() if ln.strip()]
    long_ = [ln for ln in _prose(md, clip=False) if len(ln) > LONG]
    packed_front = [ln for ln in _prose(front, clip=False) if _packed(ln)]
    packed_all = [ln for ln in _prose(md, clip=False) if _packed(ln)]
    names = [_sec_name(ln) for ln in md.splitlines() if ln.startswith("## ")]
    arch = any(n.startswith("선택지") for n in names)
    choice = any(n.startswith(CHOICE_HEADS) for n in names)  # 고를 것을 내는 글. 이름을 바꿔 검사를 피하지 못하게 한다
    extra = [n for n in names if _front_rank(n) is None and n != "근거"] if arch else []  # '근거' 에서 끝난다
    in_table = {i for *_, idx in _five_w_tables(front) for i in idx}  # 번호는 근거 표에 둔다 — 첫 화면의 근거 표는 세지 않는다
    front_text = "\n".join(ln for i, ln in enumerate(front.splitlines()) if i not in in_table)
    return {"visible_lines": len(vis), "long_lines": len(long_), "extra_sections": extra,
            "figures": len(figs or []) if arch else None,
            "packed_front": len(packed_front), "packed_rest": max(0, len(packed_all) - len(packed_front)),
            "date_tags": len(DATE_TAG.findall(_no_code(md))),
            "ids_front": len(WORK_ID.findall(_no_code(front_text))),
            "vague_when": _vague_when(_five_w_tables(md)),
            "decisions": len(blocks := _decision_blocks(md)),
            "decisions_incomplete": sum(not _block_complete(b) for b in blocks),
            "five_w": bool(FIVE_W.search(md)) if choice else None,
            "recommend": bool(RECOMMEND.search(front)) if choice else None,
            "why_slots": sum(bool(re.search(rf"^\s*[-*]\s*\**{s}\**\s*:", front, re.M)) for s in WHY_SLOTS)
            if choice else None}


def report(c):
    """check() 결과 → (한 줄, 기준 안인가)."""
    ok = (c["visible_lines"] <= VISIBLE_MAX and c["long_lines"] == 0 and not c["extra_sections"] and c["figures"] != 0
          and c.get("packed_front", 0) == 0 and c.get("date_tags", 0) == 0 and c.get("ids_front", 0) == 0
          and c.get("five_w") is not False and c.get("why_slots") in (None, len(WHY_SLOTS))
          and c.get("recommend") is not False and c.get("vague_when", 0) == 0
          and c.get("decisions_incomplete", 0) == 0)
    line = f"읽기 점검: 첫 화면 {c['visible_lines']}줄(기준 {VISIBLE_MAX} 이하) · {LONG}자 넘는 줄 {c['long_lines']}개(기준 0)"
    if "packed_front" in c:
        line += (f" · 몰아 쓴 줄 {c['packed_front']}개(기준 0 — 가운뎃점 {PACK_DOTS}개 · 괄호 {PACK_PARENS}개 이상,"
                 f" 근거 쪽 {c['packed_rest']}개는 참고) · 날짜 꼬리표 {c['date_tags']}개(기준 0)"
                 f" · 첫 화면 작업 · 커밋 번호 {c['ids_front']}개(기준 0)")
    if c.get("five_w") is not None:
        line += (f" · 추천 {'있음' if c.get('recommend') else '없음'}(기준 있음 — 선택지나 고를 것을 내면 추천 하나)"
                 f" · 추천의 왜 칸 {c['why_slots']}/{len(WHY_SLOTS)}(기준 {len(WHY_SLOTS)} — {', '.join(WHY_SLOTS)})"
                 f" · 근거 육하원칙 표 {'있음' if c['five_w'] else '없음'}(기준 있음)")
    if c.get("decisions"):
        line += (f" · 결정 블록 {c['decisions']}개 중 칸이 빈 것 {c['decisions_incomplete']}개"
                 f"(기준 0 — 블록마다 왜 네 칸과 육하원칙 표)")
    if c.get("vague_when"):
        line += (f" · 근거 표 '언제' 칸에 문서를 쓴 때를 적은 줄 {c['vague_when']}개"
                 f"(기준 0 — 일이 일어나는 때, 또는 확인한 날짜 · 커밋)")
    if c["figures"] is not None:
        line += f" · 근거 밖 절 {len(c['extra_sections'])}개(기준 0" + (
            ": " + ", ".join(c["extra_sections"]) if c["extra_sections"] else "") + ")"
        line += (f" · 구조도 {c['figures']}장(기준 1 이상 — diagram-design 전 · 후, 형식은 바뀌는 것에 맞게 references/diagram-types.md,"
                 f" <문서 이름>{FIG_SUFFIX}-<선택지>-<형식>[-전|-후].html)")
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


def readable(md, hide=()):
    """기본 보기: game-architecture 답변이면 summary_first, 그 밖에 그림이 든 글이면 diagram_first."""
    s = summary_first(md, hide)
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


def _plain_fig(fig, folder):
    """문서 메모 칸을 뺀 구조도 HTML. 내보내기 도구가 페이지의 <style> 을 SVG 에 담아서, 붙인 채로 내보내면 그림마다 메모 칸 스타일이 따라 들어간다.
    이름은 지킨다 — 정의 ID 가 파일 이름에서 나온다."""
    try:
        text = Path(fig).read_bytes().decode("utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return Path(fig)
    if not NOTES_BLOCK.search(text):
        return Path(fig)
    plain = Path(folder) / Path(fig).name
    plain.write_text(NOTES_BLOCK.sub("", text), encoding="utf-8")
    return plain


def dd_svg(fig):
    """diagram-design 구조도 HTML → 문서에 바로 넣을 SVG 글. diagram-design 의 export_svg.py 가
    스타일을 SVG 안에 담고 정의 ID 에 파일 이름을 붙여 준다(여러 장이 한 문서에 있어도 안 섞인다).
    결과는 옆에 <이름>.svg 로 두고 구조도가 바뀔 때만 다시 만든다. 도구가 없거나 실패하면 None."""
    svg = Path(fig).with_suffix(".svg")
    try:
        if not svg.is_file() or svg.stat().st_mtime < Path(fig).stat().st_mtime:
            if not DD_EXPORT.is_file():
                return None
            with tempfile.TemporaryDirectory() as tmp:
                r = subprocess.run([sys.executable, str(DD_EXPORT), str(_plain_fig(fig, tmp)), str(svg)], capture_output=True,
                                   timeout=60, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
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


def embed_figs(md, figs, out_dir, url_for=None):
    """'그림' 절 맨 앞에 diagram-design 구조도를 끼워 넣는다. 그 절의 Mermaid 는 원본 코드로 접는다
    (닫힌 <details> 안에서는 mermaid 가 크기를 못 재므로 그리지 않고 글로 둔다). '그림' 절이 없으면 새로 만든다.
    url_for 를 주면 구조도 파일을 그 주소로 가리킨다(양식 서버가 내보낼 때)."""
    if not figs:
        return md
    tags = []
    for p in figs:
        rel = html.escape(url_for(p)) if url_for else urllib.parse.quote(os.path.relpath(p, out_dir).replace(os.sep, "/"))
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
    at = next((n for n, i in enumerate(heads) if _sec_name(lines[i]).startswith(FIG_HEADS)), None)
    if at is None:
        return md.rstrip() + f"\n\n## 그림\n\n{block}\n"
    i, end = heads[at], heads[at + 1] if at + 1 < len(heads) else len(lines)
    body = "\n".join(lines[i + 1:end]).strip()
    if body:
        src = re.sub(r"^([ \t]*(?:`{3,}|~{3,})[ \t]*)mermaid", r"\1text", body, flags=re.M)
        block += f"\n\n<details><summary>Mermaid 원본</summary>\n\n{src}\n\n</details>"
    return "\n".join(lines[:i + 1] + ["", block, ""] + lines[end:]) + "\n"


# ── 문서 메모 ──────────────────────────────────────────────────────────────
# 문서를 나중에 보다가 이상한 곳이 보이면 그 자리에서 적어 Claude 로 보낸다(사용자 2026-11-19).
# 그때는 떠 있는 서버도 세션도 없다. 그래서 파일로 연 HTML 안에서 돌고, claude-cli:// 주소나 클립보드로 보낸다.
NOTES_FILE = HERE / "notes.html"
NOTES_BLOCK = re.compile(r"<!-- gh-notes -->.*?<!-- /gh-notes -->\n?", re.S)
NOTES_CFG = re.compile(r"const CFG = (\{.*?\});")
LINK_MAX = 2000  # claude-cli:// 주소 길이 상한. Chromium 은 Windows 에서 2,048자 넘는 바깥 프로그램 주소를 버릴 수 있다. 넘으면 폴더만 열고 글은 붙여 넣게 한다
ROOT_MARKS = (".claude", ".git", ".svn", "ProjectSettings")


def project_root(folder, given=None):
    """문서가 든 프로젝트의 루트. 못 찾으면 None. 홈 폴더(.claude 가 있다)는 프로젝트로 치지 않는다."""
    if given:
        return Path(given).resolve()
    home, folder = Path.home().resolve(), Path(folder).resolve()
    for d in (folder, *folder.parents):
        if d == home:
            break
        if any((d / m).exists() for m in ROOT_MARKS) or any(d.glob("*.uproject")):
            return d
    return None


def notes_block(page_path, src=None, project=None):
    """HTML 에 실을 문서 메모 칸. src 는 고칠 원본이다(없으면 그 HTML 자신).
    경로를 박지 않는다: 원본은 HTML 폴더 기준 상대 경로, 루트는 올라갈 폴더 수로 적는다. 폴더째 옮겨도 맞는다."""
    try:
        block = NOTES_FILE.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    except OSError:
        return ""
    folder = Path(page_path).resolve().parent
    root = project_root(folder, project)
    try:
        up = len(folder.relative_to(root).parts) if root else None
    except ValueError:  # 문서가 그 루트 밖에 있다
        up = None
    rel = ""
    if src:
        try:
            rel = os.path.relpath(Path(src).resolve(), folder).replace(os.sep, "/")
        except ValueError:  # 다른 드라이브
            rel = Path(src).resolve().as_posix()
    cfg = json.dumps({"src": rel, "up": up, "max": LINK_MAX}, ensure_ascii=False).replace("</", "<\\/")
    return block.replace("__GN__", cfg)


def attach(targets, project=None, remove=False):
    """남이 쓴 HTML(직원 보고서 · 구조도 페이지)에 문서 메모 칸을 붙이거나 뗀다. 다시 붙이면 바꿔 끼운다. 바꾼 파일 수를 돌려준다."""
    files = []
    for t in targets:
        p = Path(t)
        files += sorted(p.glob("*.html")) if p.is_dir() else [p] if p.is_file() else [Path(f) for f in sorted(glob.glob(str(t)))]
    done = 0
    for f in files:
        try:
            raw = f.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"건너뜀: {f} ({type(e).__name__})")
            continue
        text = raw.replace("\r\n", "\n")
        old = NOTES_BLOCK.search(text)
        kept = NOTES_CFG.search(old.group(0)) if old else None
        src = json.loads(kept.group(1)).get("src") if kept else ""  # render.py 가 만든 문서면 원본(.md)을 그대로 가리킨다
        new = NOTES_BLOCK.sub("", text)
        if not remove:
            block, at = notes_block(f, f.parent / src if src else None, project), new.lower().rfind("</body>")
            new = new[:at] + block + "\n" + new[at:] if at >= 0 else new.rstrip("\n") + "\n" + block + "\n"
        if new != text:
            f.write_bytes((new.replace("\n", "\r\n") if "\r\n" in raw else new).encode("utf-8"))
            done += 1
        print(f"{'그대로' if new == text else '뗐다' if remove else '붙였다'}: {f}")
    if not files:
        print("HTML 을 찾지 못했다.")
    return done


def render_html(md, out, title, js_dir=None, full=False, src=None, url_for=None, hide=(), project=None):
    """HTML 글. src(원본 .md 경로)를 주면 옆의 diagram-design 구조도(<이름>-구조*.html)를 '그림' 절에 끼워 넣는다.
    url_for 를 주면 양식 페이지에 싣는 꼴이다: 스크립트 · 구조도를 그 주소로 부르고, 제목 줄과 테마 단추를 감춘다.
    문서 메모 칸은 파일로 남는 HTML 에만 싣는다. 양식 페이지에는 기각 이유 · 답 칸이 따로 있다."""
    md = embed_figs(md, dd_figs(src, exclude=out), Path(out).parent, url_for)
    md = md if full else readable(md, hide)
    stamp = f"{Path(src).name if src else Path(out).stem} · {time.strftime('%Y-%m-%d %H:%M')}"
    return page(title=html.escape(title), stamp=html.escape(stamp), raw=html.escape(md),
                md=json.dumps(md).replace("</", "<\\/"), scripts=scripts(js_dir, url_for),
                embed=" data-embed" if url_for else "", notes="" if url_for else notes_block(out, src, project))


def render(md, out, title, js_dir=None, full=False, src=None, project=None):
    out = Path(out)
    out.write_text(render_html(md, out, title, js_dir, full, src, project=project), encoding="utf-8")
    return out


# ── 문서 → 고르기 양식 (--form) ────────────────────────────────────────────
# 구조 문서가 이미 선택지 · 추천 · 왜 · 질문을 담고 있다. 양식을 따로 쓰게 하면 같은 것을 두 번 쓰고 두 탭이 뜬다.
# 그래서 문서에서 읽어 양식으로 옮기고, 문서와 한 페이지에 낸다(사용자 2026-11-19: HTML 로 띄우는 것과 양식을 하나로).
QUESTION_HEADS = ("질문",)
FORM_HIDES = CHOICE_HEADS + QUESTION_HEADS  # 양식이 카드로 보이는 절 — 실은 문서에서는 접힌 근거로 내린다
OPTION = re.compile(r"^([A-Z])(?:안|[.)])?(?:\s*[:—–-]\s*|\s+|$)(.*)$")
WHY_KEYS = {"문제": "problem", "버린 안": "dropped", "대가": "cost", "뒤집는 조건": "flip"}
WHY_LINE = re.compile(r"^\s*[-*]\s*\**(문제|버린 안|대가|뒤집는 조건)\**\s*[:：]\s*(.+)$", re.M)
DROPPED_BEFORE = re.compile(r"^\s*[-*]?\s*\**앞서 기각(?:한 안)?\**\s*[:：]\s*(.+)$", re.M)
EMPTY_CELL = ("", "…", "...", "-", "—")


def _plain(text):
    """표 칸 · 제목의 마크다운 표시를 걷는다 — 양식은 글자 그대로 보인다."""
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", str(text or ""))
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t.replace("**", "").replace("`", "")).strip()


def _section(md, heads):
    """이름이 heads 로 시작하는 첫 `## ` 절의 본문. 없으면 ''."""
    lines = _no_code(md).splitlines()
    at = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    for n, i in enumerate(at):
        if _sec_name(lines[i]).startswith(heads):
            return "\n".join(lines[i + 1:at[n + 1] if n + 1 < len(at) else len(lines)])
    return ""


def _tables(text):
    """(머리줄 칸, 본문 줄의 칸들) — 절 안의 표마다."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("|"):
            i += 1
            continue
        block = []
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            block.append(lines[i])
            i += 1
        rows = [_cells(ln) for ln in block if not re.fullmatch(r"\s*\|[\s:|-]*", ln)]
        if len(rows) >= 2:
            out.append(([_plain(c) for c in rows[0]], rows[1:]))
    return out


def _option(text):
    m = OPTION.match(_plain(text))
    return (m.group(1), m.group(2).strip(" —–-:") or m.group(1) + "안") if m else None


LETTER = re.compile(r"(?<![A-Za-z])([A-Z])안?(?![A-Za-z])")
MARKED = re.compile(r"([①-⑳])\s*([A-Z])")  # "추천: ①C, ②B" — 결정 표의 행 표시와 고른 안
SLOT_HEADS = (("next", ("다음 요청", "고칠 곳")), ("gain", ("얻는",)), ("loss", ("잃는",)))


def _slot(text):
    return next((k for k, keys in SLOT_HEADS if any(key in text for key in keys)), None)


def _row_options(sec):
    """표의 행마다 안 하나: 첫 칸이 `A. 이름`, 나머지 칸은 머리줄 이름으로 고칠 곳 · 얻는 것 · 잃는 것."""
    for head, rows in _tables(sec):
        slots = [(i, _slot(h)) for i, h in enumerate(head)]
        options = []
        for row in rows:
            got = _option(row[0]) if row else None
            if not got or any(o["id"] == got[0] for o in options):
                continue
            o = {"id": got[0], "name": got[1]}
            o.update({k: _plain(row[i]) for i, k in slots if k and i < len(row) and _plain(row[i]) not in EMPTY_CELL})
            options.append(o)
        if options:
            return options
    return []


def _column_options(sec):
    """표의 열마다 안 하나(머리줄이 `| | A. 이름 | B. 이름 |`): 행은 고칠 곳 · 얻는 것 · 잃는 것 같은 기준이다."""
    for head, rows in _tables(sec):
        cols = [(i, _option(h)) for i, h in enumerate(head) if i > 0]
        cols = [(i, got) for i, got in cols if got]
        if len(cols) < 2 or "결정" in head[0] or any("정함" in h for h in head):
            continue
        options = [{"id": got[0], "name": got[1]} for _, got in cols]
        for row in rows:
            key = _slot(_plain(row[0])) if row else None
            for (i, _), o in zip(cols, options):
                if key and i < len(row) and _plain(row[i]) not in EMPTY_CELL:
                    o[key] = _plain(row[i])
        return options
    return []


def _heading_options(sec):
    """소제목마다 안 하나: `### A. 플래그 — 다음 요청 때 3곳`."""
    options = []
    for ln in sec.splitlines():
        if ln.startswith("###"):
            name, _, tail = _plain(ln.lstrip("#")).partition(" — ")
            got = _option(name)
            if got and not any(o["id"] == got[0] for o in options):
                options.append({"id": got[0], "name": got[1], **({"summary": tail.strip()} if tail.strip() else {})})
    return options


def _decision_questions(sec, rec_line):
    """결정이 여럿인 표(행마다 결정 하나, 열마다 안): `| 결정 | A. 국소 패치 | B | C | 정함 |` → 행마다 질문 하나."""
    marks = dict(MARKED.findall(rec_line))
    for head, rows in _tables(sec):
        cols = [(i, _option(h)) for i, h in enumerate(head) if i > 0]
        cols = [(i, got[0]) for i, got in cols if got]
        pick_i = next((i for i, h in enumerate(head) if i > 0 and "정함" in h), None)
        if len(cols) < 2 or not ("결정" in head[0] or pick_i is not None):
            continue
        out = []
        for row in rows:
            name = _plain(row[0]) if row else ""
            options = [{"id": oid, "name": _plain(row[i])} for i, oid in cols if i < len(row) and _plain(row[i]) not in EMPTY_CELL]
            if not name or len(options) < 2:
                continue
            picked = _plain(row[pick_i]) if pick_i is not None and pick_i < len(row) else ""
            picked = picked[0] if re.fullmatch(r"[A-Z]안?", picked) else marks.get(name[0], "")
            for o in options:
                if o["id"] == picked:
                    o["recommended"] = True
            out.append({"id": f"q{len(out) + 1}", "title": name, "options": options})
        if out:
            return out
    return []


def doc_form(md, title):
    """구조 문서 → (고르기 양식, 못 읽은 이유들). '선택지' 절의 안 · 추천 · 왜 네 칸과 '질문' 절의 표를 옮긴다.
    안은 표의 행(첫 칸 `A. 국소 패치`)이나 열(머리줄 `| | A. … | B. … |`)이나 소제목(`### A. 국소 패치 — …`)에서 읽는다.
    결정이 여럿인 표(`| 결정 | A | B | 정함 |`)는 행마다 질문 하나가 된다."""
    sec = _section(md, CHOICE_HEADS)
    if not sec.strip():
        return None, ["'선택지' 절이 없다"]
    rec = RECOMMEND.search(sec)
    rec_line = sec[rec.end():].splitlines()[0] if rec and sec[rec.end():] else ""
    rec_ids = LETTER.findall(_plain(rec_line).split(" — ")[0].split(".")[0])  # "B" · "B안" · "B + E" — 이유 글의 글자는 세지 않는다
    questions = _decision_questions(sec, rec_line)
    single = not questions
    if single:
        options = _row_options(sec) or _column_options(sec) or _heading_options(sec)
        if len(options) < 2:
            return None, [f"'선택지' 절에서 안을 {len(options)}개만 읽었다 — 표 첫 칸을 `A. 이름` 꼴로 쓴다"]
        questions = [{"id": "q1", "title": "어느 안으로 가나", "options": options}]
    main, asks = questions[0], []
    ids = [o["id"] for o in main["options"]]
    for head, rows in _tables(_section(md, QUESTION_HEADS))[:1]:
        col = lambda key, default: next((i for i, h in enumerate(head) if key in h), default)  # noqa: E731
        q_i, fork_i, rec_i, chg_i = col("질문", 1), col("갈래", 2), col("추천", 3), col("바뀌는", 4)
        cell = lambda row, i: _plain(row[i]) if i < len(row) else ""  # noqa: E731
        for n, row in enumerate(rows, 1):
            text, changes = cell(row, q_i), cell(row, chg_i)
            forks = [f.strip() for f in re.split(r"\s*/\s*", cell(row, fork_i)) if f.strip()]
            if not text:
                continue
            groups = [LETTER.findall(f) if re.fullmatch(r"[A-Z]안?(?:\s*[·,+]\s*[A-Z]안?)*", f) else None for f in forks]
            if single and forks and all(g and set(g) <= set(ids) for g in groups):  # 구조를 묻는 행 — 선택지 카드가 답한다
                main["title"] = text
                if changes not in EMPTY_CELL:
                    main["changes"] = changes
                if any(len(g) > 1 for g in groups):  # 축이 여럿이다("A·B·C / D·E") — 축마다 하나씩 고르게 가른다
                    by_id = {o["id"]: o for o in main["options"]}
                    used = {i for g in groups for i in g}
                    groups[0] += [i for i in ids if i not in used]
                    questions[:1] = [{**main, "id": f"q{k}", "title": f"{text} — {' · '.join(g)}", "options": [by_id[i] for i in g]}
                                     for k, g in enumerate(groups, 1)]
                    main = questions[0]
                continue
            if len(forks) < 2:  # 갈래 없이 묻는 것 — 답을 적는 칸으로
                asks.append({"id": f"a{n}", "text": text})
                continue
            picked = cell(row, rec_i)
            best = max((f for f in forks if picked.startswith(f)), key=len, default=None)
            reason = picked[len(best):].strip(" —–-:") if best else ""  # 추천 칸의 이유 한 구절 — 그 갈래 카드에 보인다
            q = {"title": text, "options": [{"id": str(k), "name": f} for k, f in enumerate(forks, 1)]}
            for o in q["options"]:
                if o["name"] == best:
                    o.update({"recommended": True}, **({"summary": reason} if reason else {}))
            if changes not in EMPTY_CELL:
                q["changes"] = changes
            questions.append(q)
    if single:  # 안을 고르는 질문마다 추천 하나 — 추천 줄에 먼저 나온 안
        for q in questions:
            if q["options"] and q["options"][0]["id"] in ids:
                best = next((i for i in rec_ids if any(o["id"] == i for o in q["options"])), None)
                for o in q["options"]:
                    if o["id"] == best:
                        o["recommended"] = True
    why = {}
    for key, value in WHY_LINE.findall(sec):
        if WHY_KEYS[key] == "dropped":
            why.setdefault("dropped", []).append(_plain(value))
        else:
            why.setdefault(WHY_KEYS[key], _plain(value))
    if why:
        main["why"] = why
    before = [_plain(d) for d in DROPPED_BEFORE.findall(sec)]
    if before:
        main["dropped_before"] = before
    if asks:
        main["asks"] = asks
    for k, q in enumerate(questions, 1):
        q["id"] = f"q{k}"
    return {"kind": "selection", "title": title, "questions": questions}, []


def load_decide():
    """selection 스킬의 양식 엔진. 설치가 반쪽이면 None — 그때는 문서만 연다."""
    folder = HERE.parent.parent / "selection" / "scripts"
    if not (folder / "decide.py").is_file():
        return None
    sys.path.insert(0, str(folder))
    try:
        import decide
        return decide
    except Exception:
        return None


def run_form(src, md, title, out, a):
    """문서와 고르기 양식을 한 페이지로 띄우고 끝 코드를 돌려준다. 양식을 못 만들면 문서만 연다."""
    decide = load_decide()
    spec, errors = doc_form(md, title)
    if decide and spec:
        spec_errors, warns = decide.check_spec(spec)
        errors = spec_errors
        for w in warns:
            if "왜 네 칸" in w and not w.startswith("질문 1:"):
                continue  # 곁 질문의 추천 이유는 질문 표 추천 칸의 한 구절이 전부다 — 문서에서 고칠 것이 없다
            print(f"점검: {w}")
    elif not decide:
        errors = ["selection 스킬(decide.py)이 없다 — setup.bat 을 다시 돌린다"]
    if decide and decide.unattended():
        print(f"띄우지 않았다 — 무인 실행이다({decide.unattended()}). 문서만 만들었다.\n"
              "다음: 선택지와 추천은 답에 글로 내고 멈춘다. 고른 것으로 치고 진행하지 않는다.")
        return decide.UNATTENDED
    if errors:
        print("고르기 양식을 붙이지 못했다 — 문서만 연다:\n" + "\n".join(f"- {e}" for e in errors))
        err = None if a.no_open else open_file(out)
        if err:
            print(f"열지 못했다 ({err}). 위 경로를 브라우저로 직접 연다.")
        return 0
    doc = lambda url_for: render_html(md, out, title, a.js_dir, src=src, url_for=url_for, hide=FORM_HIDES)  # noqa: E731
    return decide.run_form(spec, None, Path(src).with_name(Path(src).stem + ".answers.json"), a, doc=doc)


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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("more", nargs="*", help="--attach · --detach: HTML 을 더 준다(폴더 · * 도 된다)")
    ap.add_argument("-o", "--out")
    ap.add_argument("--js-dir")
    ap.add_argument("--open", action="store_true", help="만든 HTML 을 기본 브라우저로 연다")
    ap.add_argument("--full", action="store_true",
                    help="절 순서를 바꾸지 않고 전부 펼친다 (기본: 선택지 · 그림 먼저, 그 밖의 글은 요약 · 그림 먼저, 나머지는 접기)")
    ap.add_argument("--form", action="store_true", help="문서와 고르기 양식을 한 페이지로 띄운다. 보낼 때까지 기다린다 — 백그라운드로 돌린다")
    ap.add_argument("--project", help="프로젝트 루트. --form 은 '남김' 표시한 결정을 그 아래 결정 장부에 적는다. "
                                      "문서 메모의 'Claude 로 열기'가 여는 폴더다(안 주면 문서 위쪽 폴더에서 찾는다)")
    ap.add_argument("--attach", action="store_true", help="남이 쓴 HTML 에 문서 메모 칸을 붙인다(다시 붙이면 바꿔 끼운다)")
    ap.add_argument("--detach", action="store_true", help="붙인 문서 메모 칸을 뗀다")
    ap.add_argument("--no-open", action="store_true", help="--form: 브라우저를 열지 않고 주소만 찍는다")
    ap.add_argument("--timeout", type=int, default=120, help="--form: 움직임이 없으면 닫는 시간(분)")
    a = ap.parse_args(argv)
    project, a.project = a.project, a.project or "."
    if a.attach or a.detach:
        attach([a.src, *a.more], project, remove=a.detach)
        return 0
    if a.more:
        ap.error("문서는 하나만 받는다")
    src = Path(a.src)
    md = src.read_text(encoding="utf-8")
    title = next((ln.lstrip("# ").strip() for ln in md.splitlines() if ln.startswith("# ")), src.stem)
    out = render(md, a.out or src.with_suffix(".html"), title, a.js_dir, a.full, src=src, project=project)
    print(out)
    print(report(check(md, dd_figs(src, exclude=out)))[0], flush=True)
    if a.form:
        return run_form(src, md, title, out, a)
    if a.open:
        err = open_file(out)
        if err:
            print(f"열지 못했다 ({err}). 위 경로를 브라우저로 직접 연다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
