# 동봉 스크립트 (render.py 가 쓴다)

Claude Code 대화창은 Mermaid 를 그리지 않는다. render.py 는 .md 를 HTML 로 만들어 브라우저에서 그린다.
사내망에서 CDN 이 막혀도 그려지도록 두 파일을 여기에 둔다 — 설치할 것은 없다.

| 파일 | 버전 | 출처 (npm 레지스트리 tarball, integrity 대조함) | SHA-256 | 라이선스 |
|---|---|---|---|---|
| `mermaid.min.js` | 11.17.2 | `mermaid-11.17.2.tgz` 의 `package/dist/mermaid.min.js` | `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8` | MIT (`LICENSE.mermaid`) |
| `marked.min.js` | 12.0.2 | `marked-12.0.2.tgz` 의 `package/marked.min.js` | `15fabce5b65898b32b03f5ed25e9f891a729ad4c0d6d877110a7744aa847a894` | MIT 등 (`LICENSE.marked.md`) |

메이저 버전을 바꾸면 render.py 의 렌더 스크립트(marked 12 의 `Renderer.code`, mermaid 11 의 `mermaid.run`)를 같이 확인한다.
