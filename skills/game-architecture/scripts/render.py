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
import html
import json
import os
import sys
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
  if (window.mermaid) {{ mermaid.initialize({{startOnLoad:false, theme:'default'}}); mermaid.run(); }}
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


def render(md, out, title, js_dir=None):
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
    a = ap.parse_args()
    src = Path(a.src)
    md = src.read_text(encoding="utf-8")
    title = next((ln.lstrip("# ").strip() for ln in md.splitlines() if ln.startswith("# ")), src.stem)
    out = render(md, a.out or src.with_suffix(".html"), title, a.js_dir)
    print(out)
    if a.open:
        err = open_file(out)
        if err:
            print(f"열지 못했다 ({err}). 위 경로를 브라우저로 직접 연다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
