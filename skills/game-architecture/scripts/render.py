#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown(+Mermaid) → 단일 HTML. SVN 처럼 .md 를 렌더하지 않는 환경에서 브라우저로 연다.

  python render.py <입력.md> [-o 출력.html] [--js-dir <폴더>]

기본은 CDN 의 marked·mermaid 를 쓴다. 사내망에서 CDN 이 막히면 두 파일을 받아 둔 폴더를
--js-dir 로 준다 (marked.min.js, mermaid.min.js). 스크립트를 못 불러오면 원문을 그대로 보인다.
"""

import argparse
import html
import json
import sys
from pathlib import Path

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
.mermaid{{background:#fff;border:1px solid var(--line);border-radius:6px;padding:8px;margin:12px 0}}
#raw{{white-space:pre-wrap}} .note{{color:var(--mute);font-size:13px}}
</style></head><body>
<div id="out"><pre id="raw">{raw}</pre><p class="note">스크립트를 불러오지 못해 원문을 표시한다 (사내망이면 --js-dir).</p></div>
<script src="{marked}"></script><script src="{mermaid}"></script>
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out")
    ap.add_argument("--js-dir")
    a = ap.parse_args()
    src = Path(a.src)
    md = src.read_text(encoding="utf-8")
    js = dict(CDN)
    if a.js_dir:
        d = Path(a.js_dir).resolve()
        js = {k: (d / f"{k}.min.js").as_uri() for k in CDN}
    title = next((ln.lstrip("# ").strip() for ln in md.splitlines() if ln.startswith("# ")), src.stem)
    out = Path(a.out) if a.out else src.with_suffix(".html")
    out.write_text(PAGE.format(title=html.escape(title), raw=html.escape(md), md_json=json.dumps(md).replace("</", "<\\/"),
                               marked=js["marked"], mermaid=js["mermaid"]), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
