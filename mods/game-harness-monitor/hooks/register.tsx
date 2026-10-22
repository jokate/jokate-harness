// game-harness-monitor — 하네스가 이 세션에서 "어떤 기능을 동작시켰는지"와 "코드를 무엇으로 찾았는지" 보여준다.
//
// 근거 자료 두 가지:
//  1) 하네스 훅·스크립트가 남기는 이벤트 로그 (~/.claude/cache/game-harness/events.jsonl,
//     형식은 skills/game-bootstrap/harness/harness_events.py) — 읽기만 한다.
//  2) 이 세션의 도구 호출 — 인덱스(gq · clangd · 위키 · ue_q)로 찾았나, 직접(grep · 파일 찾기 · 파일 읽기) 찾았나를 센다.
//     세션 요약은 $.store 에 남겨 이력 페이지를 만든다. 도구 호출을 막거나 결과를 바꾸지 않는다 — 소스에서 C++ 심볼을
//     grep 하고 그 심볼이 clangd 인덱스에 있으면 결과 뒤에 cindex 명령 한 줄을 붙일 뿐이다(세션당 3번).
//     로그 · 문서 · 설정 · 명령 출력을 거르는 grep 은 코드 탐색이 아니라 세지 않는다.
//
//   프롬프트 위 띠  코드 탐색 │ gq 3 · clangd 0 · 위키 2 · ue_q 0 │ 직접 grep 12 · 찾기 4 · 읽기 30   (게임 프로젝트)
//   상태줄          harness ● 기능 N개 · 마지막 <기능>
//   토스트          기능이 처음 동작할 때, clangd · 위키를 이 세션에서 처음 쓸 때
//   /harness         패널: 코드 탐색 횟수 · 하네스 기능 · 최근 기록
//   /harness-history 이력 HTML(세션별 탐색 · 기능 · 최근 기록)을 만들어 브라우저로 연다
// 사용자: "clangd 가 많이 안 불리는 것 같은데 하단에 쥐똥만하게 나온다 — 확실하게 알 수 있게, 이력은 상세 페이지로"(2026-10-20).
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Counts, HarnessEvent, Kind, ProjectInfo, SearchEvent, SessionSummary } from '../types'

const PANE = 'game-harness'
const POLL_MS = 3000
const KEEP = 300
const KEEP_SEARCH = 200
const KEEP_SESSIONS = 200

export const INDEX_KINDS: readonly Kind[] = ['gq', 'clangd', 'wiki', 'ue_q']
export const DIRECT_KINDS: readonly Kind[] = ['grep', 'glob', 'read']
const SHORT: Record<Kind, string> = {
  gq: 'gq', clangd: 'clangd', wiki: '위키', ue_q: 'ue_q', grep: 'grep', glob: '찾기', read: '읽기',
}
const LONG: Record<Kind, string> = {
  gq: 'gq 좌표 인덱스', clangd: 'clangd 의미 인덱스', wiki: '위키', ue_q: 'ue_q 엔진 인덱스',
  grep: 'grep 직접 검색', glob: '파일 찾기', read: '파일 읽기',
}

export function emptyCounts(): Counts {
  return { gq: 0, clangd: 0, wiki: 0, ue_q: 0, grep: 0, glob: 0, read: 0 }
}

const events = atom({ plugin: 'game-harness-monitor', key: 'events' } as const, [] as HarnessEvent[])
const counts = atom({ plugin: 'game-harness-monitor', key: 'counts' } as const, emptyCounts())
const searches = atom({ plugin: 'game-harness-monitor', key: 'searches' } as const, [] as SearchEvent[])
const project = atom({ plugin: 'game-harness-monitor', key: 'project' } as const,
  { isGame: false, hasClangd: false, hasWiki: false } as ProjectInfo)

const LABELS: Record<string, string> = {
  'context.routing': '세션 라우팅 주입',
  'stuck.warn': '매몰 경고',
  'mcp.guard': 'MCP 가드 경고',
  'mcp.call': 'MCP 호출 기록',
}

const PREFIXES: [string, string][] = [
  ['skill.', '스킬 '],
  ['script.', '조회 '],
  ['session_start.', '세션 시작 명령 '],
  ['index.', '인덱스 '],
]

export function label(feature: string): string {
  const fixed = LABELS[feature]
  if (fixed !== undefined) return fixed
  for (const [prefix, name] of PREFIXES) {
    if (feature.startsWith(prefix)) return name + feature.slice(prefix.length)
  }
  return feature
}

const norm = (p: string) => p.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
const base = (p: string) => p.replace(/\\/g, '/').replace(/\/+$/, '').split('/').pop() ?? p

// 세션 id 가 있는 이벤트(훅이 남긴 것)는 id 로, 없는 것(스크립트가 직접 남긴 것)은 프로젝트 경로와 시각으로 가른다.
export function belongs(ev: HarnessEvent, sessionId: string, root: string, startedAt: number): boolean {
  if (ev.session !== '') return ev.session === sessionId
  if (ev.ts < startedAt || ev.project === '') return false
  const p = norm(ev.project)
  const r = norm(root)
  return r === p || r.startsWith(p + '/') || p.startsWith(r + '/')
}

export function parse(text: string): HarnessEvent[] {
  const out: HarnessEvent[] = []
  for (const line of text.split('\n')) {
    if (line.trim() === '') continue
    try {
      const ev = JSON.parse(line) as HarnessEvent
      if (typeof ev.feature === 'string' && typeof ev.ts === 'number') out.push(ev)
    } catch {
      // 반쯤 쓰인 줄은 다음 폴링에서 다시 읽힌다
    }
  }
  return out
}

export function statusText(list: readonly HarnessEvent[]): string | undefined {
  const last = list.at(-1)
  if (last === undefined) return undefined
  const features = new Set(list.map(ev => ev.feature)).size
  const failed = list.filter(ev => !ev.ok).length
  return `harness ● 기능 ${features}개 · 마지막 ${label(last.feature)}${last.ok ? '' : ' ✗'}` +
    (failed > 0 ? ` · 실패 ${failed}` : '')
}

const INDEX_SCRIPT = /(cindex|gq|wq|ue_q)\.py["']?(?:\s+([a-z][\w-]*))?(?:\s+([^\s|;&>"']+))?/
const KIND_OF_SCRIPT: Record<string, Kind> = { cindex: 'clangd', gq: 'gq', wq: 'wiki', ue_q: 'ue_q' }
const GREP_CMD = /(^|[\s|;&(])(rg|grep|egrep|findstr|Select-String|sls)(\s|$)/
const FIND_CMD = /(^|[\s|;&(])(find|fd|Get-ChildItem|gci|dir|ls)(\s|$)/

// grep 이 코드를 찾는가. 로그 · 문서 · 설정 · 앞 명령의 출력을 거르는 grep 은 코드 탐색이 아니라 세지 않는다 —
// MNYS 세션 52개(10-20~22)의 grep 대부분이 Saved/Logs 의 로그 줄 · Docs 의 기획 용어 · git 출력이었고, 그것까지 세서
// "clangd 인덱스가 있는데 grep 만 씀" 이 늘 떴다.
const CODE_TARGET = /(^|[\s"'=:/\\])(Source|Plugins)([/\\\s"']|$)|\.(h|hpp|cpp|cc|cxx|inl|cs)\b|--type[= ]?(cpp|c|cs)\b|(^|\s)-t\s*(cpp|c|cs)\b/i
const TEXT_TARGET = /Saved[/\\]Logs|\.(log|md|txt|json|ini|csv|ya?ml)\b|(^|[\s"'=:/\\])(Docs|Config|Saved)([/\\\s"']|$)/i
const PIPED_GREP = /\|\s*(rg|grep|egrep|findstr|Select-String|sls)\b[^|;&]*/g
const PATHLIKE = /[A-Za-z]:[/\\]\S*|\S*\/\S*/g
// C++ 심볼처럼 보이는 이름: A::B, UE 접두 타입(FYSInput · UThing · AActor · EKind · IFace · TArray), 두 마디 이상 CamelCase
const SYMBOL = /\b[A-Za-z_]\w*::[A-Za-z_]\w*|\b[AUFEIT][A-Z]\w*[a-z]\w*|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b/g
const hasSymbol = (text: string) => new RegExp(SYMBOL.source).test(text)

export function grepTarget(tool: string, args: Record<string, unknown>): 'code' | 'text' {
  const s = (k: string) => (typeof args[k] === 'string' ? (args[k] as string) : '')
  if (tool === 'Grep') {
    const where = `${s('path')} ${s('glob')}`
    if (CODE_TARGET.test(where) || /^(cpp|c|cs|csharp)$/i.test(s('type'))) return 'code'
    if (TEXT_TARGET.test(where) || /^(md|markdown|json|log|txt|ini|yaml)$/i.test(s('type'))) return 'text'
    return hasSymbol(s('pattern')) ? 'code' : 'text'
  }
  const cmd = s('command')
  if (CODE_TARGET.test(cmd)) return 'code'
  if (TEXT_TARGET.test(cmd)) return 'text'
  const own = cmd.replace(PIPED_GREP, ' ')
  if (!GREP_CMD.test(own)) return 'text' // 앞 명령의 출력만 거른다 (git log | grep …)
  return hasSymbol(own.replace(PATHLIKE, ' ')) ? 'code' : 'text'
}

// grep 이 찾던 C++ 심볼 후보 (한정 이름 → UE 접두 타입 → 그 밖, 3개까지). 경로 · 뒤에 붙은 grep 은 뺀다.
export function symbolCandidates(tool: string, args: Record<string, unknown>): string[] {
  const s = (k: string) => (typeof args[k] === 'string' ? (args[k] as string) : '')
  const text = tool === 'Grep' ? s('pattern') : s('command').replace(PIPED_GREP, ' ').replace(PATHLIKE, ' ')
  const names = [...new Set([...text.matchAll(SYMBOL)].map(m => m[0]))]
  const rank = (n: string) => (n.includes('::') ? 0 : /^[AUFEIT][A-Z]/.test(n) ? 1 : 2)
  return names.sort((a, b) => rank(a) - rank(b)).slice(0, 3)
}

// `cindex.py sym <이름>` 출력의 첫 줄 — 정확히 맞는 심볼이 없으면 undefined
export function symbolLine(out: string): string | undefined {
  const first = out.split(/\r?\n/).find(l => l.trim() !== '')
  if (first === undefined || /^(#|없음|clangd 인덱스 없음)/.test(first.trim())) return undefined
  return first.trim().replace(/\s+/g, ' ')
}

export function nudgeText(name: string, found: string, script: string): string {
  const cmd = `python ${script}`
  return `[game-harness] grep 한 \`${name}\` 은 clangd 인덱스에 있다 — ${found}. ` +
    `쓰는 곳 \`${cmd} refs ${name}\` · 부르는 곳 \`callers\` · 파생 \`derived\` · 바꾸면 영향 \`impact\` ` +
    '(컴파일 기준이라 주석 · 문자열 · 같은 이름이 안 섞이고 생성 코드는 빠진다. 같은 이름이 여럿이면 A::B 로 좁힌다). ' +
    '코드 심볼은 다음부터 이쪽을 먼저 쓴다 — 문자열 · 주석 · 로그를 찾을 때만 grep.'
}

// 도구 호출 하나 → 코드 탐색 종류. 탐색이 아니면 undefined.
export function classify(tool: string, args: Record<string, unknown>): { kind: Kind; what: string } | undefined {
  const s = (k: string) => (typeof args[k] === 'string' ? (args[k] as string) : '')
  if (tool === 'Bash' || tool === 'PowerShell') {
    const cmd = s('command')
    const m = INDEX_SCRIPT.exec(cmd)
    if (m) return { kind: KIND_OF_SCRIPT[m[1]], what: [m[2], m[3]].filter(Boolean).join(' ') }
    if (GREP_CMD.test(cmd)) return grepTarget(tool, args) === 'code' ? { kind: 'grep', what: cmd.slice(0, 80) } : undefined
    if (FIND_CMD.test(cmd)) return { kind: 'glob', what: cmd.slice(0, 80) }
    return undefined
  }
  if (tool === 'Grep') return grepTarget(tool, args) === 'code' ? { kind: 'grep', what: s('pattern') } : undefined
  if (tool === 'Glob') return { kind: 'glob', what: s('pattern') }
  if (tool === 'Read') {
    const p = s('file_path')
    return { kind: /[\\/]\.jokate-wiki[\\/]/.test(p) ? 'wiki' : 'read', what: base(p) }
  }
  return undefined
}

const total = (c: Counts, kinds: readonly Kind[]) => kinds.reduce((n, k) => n + c[k], 0)

// clangd 인덱스가 있는데 안 쓰고 grep 으로만 찾고 있으면 알린다
export function clangdIdle(c: Counts, proj: ProjectInfo): boolean {
  return proj.hasClangd && c.clangd === 0 && c.grep >= 5
}

export function upsertSession(list: readonly SessionSummary[], s: SessionSummary): SessionSummary[] {
  return [...list.filter(x => x.id !== s.id), s].sort((a, b) => a.started - b.started).slice(-KEEP_SESSIONS)
}

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const pct = (a: number, b: number) => (b === 0 ? 0 : Math.round((a * 100) / b))
const stamp = (ms: number) => {
  const d = new Date(ms)
  const two = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`
}

const PAGE_CSS = [
  ':root{--bg:#f6f5f2;--card:#fff;--fg:#1d2125;--mute:#5f6b76;--line:#e4e2dc;--soft:#f1efea;--accent:#bf4520;--tint:rgba(191,69,32,.07);--ok:#2f7d4f;--warn:#9a6a12;--warnbg:#f6eedb;--idx:#3d6fb6;--dir:#9aa4ad;color-scheme:light}',
  '@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1215;--card:#171b20;--fg:#e4e7ea;--mute:#98a2ad;--line:#2a3037;--soft:#1d2228;--accent:#f0875a;--tint:rgba(240,135,90,.10);--ok:#7fc79a;--warn:#e0b85f;--warnbg:#2f2817;--idx:#7aa7e6;--dir:#4a535c;color-scheme:dark}}',
  ':root[data-theme=dark]{--bg:#0f1215;--card:#171b20;--fg:#e4e7ea;--mute:#98a2ad;--line:#2a3037;--soft:#1d2228;--accent:#f0875a;--tint:rgba(240,135,90,.10);--ok:#7fc79a;--warn:#e0b85f;--warnbg:#2f2817;--idx:#7aa7e6;--dir:#4a535c;color-scheme:dark}',
  '*{box-sizing:border-box} html,body{background:var(--bg)}',
  'body{margin:0;color:var(--fg);font:15px/1.65 "Pretendard Variable",Pretendard,"Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;word-break:keep-all}',
  '.wrap{max-width:1040px;margin:0 auto;padding:32px 20px 64px}',
  '.top{display:flex;justify-content:space-between;align-items:center;gap:12px} .eyebrow{font-size:12px;color:var(--mute);letter-spacing:.06em}',
  '.theme{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:999px;padding:5px 14px;font:inherit;font-size:13px;cursor:pointer}',
  'h1{font-size:28px;letter-spacing:-.02em;margin:4px 0 20px} h2{font-size:17px;margin:0 0 12px;display:flex;gap:10px;align-items:center}',
  'h2::before{content:"";width:4px;height:17px;border-radius:2px;background:var(--accent)}',
  'section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 22px;margin:0 0 16px}',
  'section.lead{background:var(--tint);border-color:transparent} .note{color:var(--mute);font-size:13px;margin:8px 0 0}',
  '.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}',
  '.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px} .kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums} .kpi span{color:var(--mute);font-size:12.5px}',
  '.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:10px}',
  'table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}',
  'th{background:var(--soft);color:var(--mute);font-weight:600;font-size:12px;text-align:left;white-space:nowrap}',
  'th,td{padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:middle} tr:last-child td{border-bottom:0}',
  'td.n{text-align:right} td.zero{color:var(--mute)} td.warn{background:var(--warnbg);color:var(--warn);font-weight:600}',
  '.bar{display:flex;height:8px;border-radius:4px;overflow:hidden;min-width:120px;background:var(--soft)} .bar i{display:block} .bar .x{background:var(--idx)} .bar .d{background:var(--dir)}',
  '.ok{color:var(--ok)} .bad{color:var(--warn)} code{font-family:ui-monospace,Consolas,monospace;font-size:.9em}',
].join('\n')

const PAGE_JS = [
  'try{var t=localStorage.getItem("gh-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;}catch(e){}',
  'var L={auto:"자동",light:"밝게",dark:"어둡게"},N={auto:"light",light:"dark",dark:"auto"},m=document.documentElement.dataset.theme||"auto";',
  'function ap(){if(m==="auto")delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=m;document.getElementById("theme").textContent="테마: "+L[m];}',
  'document.addEventListener("DOMContentLoaded",function(){ap();document.getElementById("theme").onclick=function(){m=N[m];try{localStorage.setItem("gh-theme",m)}catch(e){}ap();};});',
].join('\n')

// 이력 페이지 — 세션별 코드 탐색(인덱스 대 직접), 하네스 기능 합계, 최근 기능 기록
export function historyHtml(sessions: readonly SessionSummary[], evs: readonly HarnessEvent[], now: number): string {
  const recent = [...sessions].sort((a, b) => b.started - a.started)
  const week = recent.filter(s => s.updated >= now - 7 * 24 * 3600 * 1000)
  const sum = emptyCounts()
  for (const s of week) for (const k of Object.keys(sum) as Kind[]) sum[k] += s.counts[k] ?? 0
  const idx = total(sum, INDEX_KINDS)
  const dir = total(sum, DIRECT_KINDS)
  const idle = week.filter(s => clangdIdle(s.counts, { isGame: true, hasClangd: s.hasClangd, hasWiki: false })).length
  const kpi = (v: string, k: string, cls = '') => `<div class="kpi"><b class="${cls}">${v}</b><span>${k}</span></div>`
  const lead = [
    kpi(`${pct(idx, idx + dir)}%`, '인덱스로 찾은 비율 (7일)', pct(idx, idx + dir) >= 30 ? 'ok' : 'bad'),
    ...INDEX_KINDS.map(k => kpi(String(sum[k]), LONG[k], sum[k] === 0 ? 'bad' : '')),
    kpi(String(sum.grep), LONG.grep), kpi(String(sum.read), LONG.read),
  ].join('')
  const rows = recent.slice(0, 60).map(s => {
    const c = s.counts
    const i = total(c, INDEX_KINDS)
    const d = total(c, DIRECT_KINDS)
    const cells = (Object.keys(SHORT) as Kind[]).map(k => {
      const warn = k === 'clangd' && clangdIdle(c, { isGame: true, hasClangd: s.hasClangd, hasWiki: false })
      return `<td class="n ${warn ? 'warn' : c[k] === 0 ? 'zero' : ''}">${c[k] ?? 0}</td>`
    }).join('')
    const bar = `<div class="bar" title="인덱스 ${i} · 직접 ${d}"><i class="x" style="width:${pct(i, i + d)}%"></i><i class="d" style="width:${100 - pct(i, i + d)}%"></i></div>`
    return `<tr><td>${esc(stamp(s.started))}</td><td>${esc(base(s.project))}${s.hasClangd ? '' : ' <span class="note">clangd 없음</span>'}</td>${cells}<td>${bar}</td></tr>`
  }).join('')
  const head = (Object.keys(SHORT) as Kind[]).map(k => `<th>${esc(SHORT[k])}</th>`).join('')
  const feats = new Map<string, { n: number; failed: number; last: string }>()
  for (const ev of evs) {
    const r = feats.get(ev.feature) ?? { n: 0, failed: 0, last: '' }
    r.n += 1
    r.failed += ev.ok ? 0 : 1
    r.last = ev.t
    feats.set(ev.feature, r)
  }
  const featRows = [...feats.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 40)
    .map(([f, r]) => `<tr><td>${esc(label(f))}</td><td class="n">${r.n}</td><td class="n ${r.failed ? 'warn' : 'zero'}">${r.failed}</td><td>${esc(r.last)}</td></tr>`).join('')
  const lines = evs.slice(-40).reverse()
    .map(ev => `<tr><td>${esc(ev.t)}</td><td class="${ev.ok ? '' : 'warn'}">${ev.ok ? '✓' : '✗'} ${esc(label(ev.feature))}</td><td><code>${esc(ev.detail.slice(0, 120))}</code></td></tr>`).join('')
  return [
    '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
    '<title>하네스 이력</title>',
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">',
    `<style>${PAGE_CSS}</style><script>${PAGE_JS}</script></head><body><div class="wrap">`,
    `<div class="top"><span class="eyebrow">game-harness-monitor · ${esc(stamp(now))}</span><button class="theme" id="theme" type="button">테마: 자동</button></div>`,
    '<h1>하네스 이력</h1>',
    `<section class="lead"><h2>최근 7일 코드 탐색</h2><div class="kpis">${lead}</div>`,
    `<p class="note">세션 ${week.length}개 · 인덱스 ${idx}회 · 직접 검색 ${dir}회${idle ? ` · clangd 인덱스가 있는데 grep 으로만 찾은 세션 ${idle}개` : ''}</p></section>`,
    `<section><h2>세션별</h2><div class="tbl"><table><thead><tr><th>시작</th><th>프로젝트</th>${head}<th>인덱스 : 직접</th></tr></thead><tbody>`,
    rows || '<tr><td colspan="10" class="zero">아직 기록이 없다</td></tr>',
    '</tbody></table></div><p class="note">노란 칸: clangd 인덱스가 있는데 0회, grep 5회 이상. 막대: 파란색 인덱스, 회색 직접 검색.</p></section>',
    `<section><h2>하네스 기능</h2><div class="tbl"><table><thead><tr><th>기능</th><th>횟수</th><th>실패</th><th>마지막</th></tr></thead><tbody>${featRows}</tbody></table></div></section>`,
    `<section><h2>최근 기능 기록</h2><div class="tbl"><table><thead><tr><th>시각</th><th>기능</th><th>내용</th></tr></thead><tbody>${lines}</tbody></table></div></section>`,
    '</div></body></html>',
  ].join('\n')
}

async function home($: EngineInterface): Promise<string> {
  return ((await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? '').replace(/[\\/]+$/, '')
}

async function logPath($: EngineInterface): Promise<string> {
  const custom = await $.env.get('GAME_HARNESS_EVENTS')
  if (custom) return custom
  return `${await home($)}/.claude/cache/game-harness/events.jsonl`
}

// 모듈 변수는 핫 리로드 때 처음으로 돌아간다. 그래도 화면이 읽는 기록은 $.state 에 있어 남는다.
let path = ''
let seenMtime = -1
let seenSize = -1
let isPolling = false

async function poll($: EngineInterface): Promise<void> {
  if (path === '') path = await logPath($)
  const stat = await $.fs.stat(path).catch(() => undefined)
  if (stat === undefined || (stat.mtimeMs === seenMtime && stat.size === seenSize)) return
  seenMtime = stat.mtimeMs
  seenSize = stat.size
  const text = await $.fs.read(path)
  const sessionId = await $.session.id()
  const root = await $.session.root()
  const { startedAt } = await $.session.usage()
  const mine = parse(typeof text === 'string' ? text : '')
    .filter(ev => belongs(ev, sessionId, root, startedAt))
    .slice(-KEEP)
  const before = await read($, events)
  if (mine.length === before.length && mine.at(-1)?.ts === before.at(-1)?.ts) return
  const known = new Set(before.map(ev => ev.feature))
  const fresh = [...new Set(mine.map(ev => ev.feature))].filter(f => !known.has(f))
  await update($, events, () => mine)
  $.ui.status(statusText(mine))
  if (fresh.length > 0) {
    $.ui.toast(`하네스 기능 시작: ${fresh.map(label).join(', ')}`)
  }
}

function pollSafely($: EngineInterface): void {
  if (isPolling) return
  isPolling = true
  poll($).catch(() => undefined).finally(() => { isPolling = false })
}

async function detectProject($: EngineInterface): Promise<ProjectInfo> {
  const root = (await $.session.root()).replace(/[\\/]+$/, '')
  const names = (await $.fs.list(root).catch(() => [])).map(x => x.name)
  const isGame = names.some(n => n.endsWith('.uproject')) || (names.includes('Assets') && names.includes('ProjectSettings'))
  const exists = async (p: string) => (await $.fs.stat(p).catch(() => undefined)) !== undefined
  return {
    isGame,
    hasClangd: await exists(`${root}/Saved/ClaudeIndex/clangd.sqlite`),
    hasWiki: await exists(`${await home($)}/.jokate-wiki/${base(root)}`),
  }
}

async function record($: EngineInterface, kind: Kind, what: string): Promise<void> {
  const now = await $.clock.now()
  const before = await read($, counts)
  const next = { ...before, [kind]: before[kind] + 1 }
  await update($, counts, () => next)
  await update($, searches, list => [...list, { ts: now, kind, what }].slice(-KEEP_SEARCH))
  if (before[kind] === 0 && (kind === 'clangd' || kind === 'wiki')) {
    $.ui.toast(`${LONG[kind]} 사용${what ? `: ${what}` : ''}`)
  }
  const proj = await read($, project)
  const id = await $.session.id()
  const { startedAt } = await $.session.usage()
  const list = ((await $.store.get('sessions')) ?? []) as SessionSummary[]
  await $.store.set('sessions', upsertSession(list, {
    id, project: await $.session.root(), started: startedAt, updated: now, hasClangd: proj.hasClangd, counts: next,
  }))
}

// 소스에서 C++ 심볼을 grep 하면: 그 이름이 clangd 인덱스에 정확히 있는지 `cindex.py sym` 으로 보고, 있으면 결과 뒤에
// cindex 명령 한 줄을 붙인다. 세션 시작 안내만으로는 모델이 grep 으로 갔다(10-20 뒤 MNYS 세션에서 clangd 0회).
// 세션당 알림 3번 · 조회 8번까지, 심볼마다 한 번. 모듈 변수라 mod 가 다시 읽히면 처음부터 센다.
const MAX_NUDGES = 3
const MAX_LOOKUPS = 8
const nudged = new Map<string, { names: Set<string>; lookups: number }>()

async function lookupSymbol($: EngineInterface, script: string, root: string, name: string): Promise<string | undefined> {
  for (const py of ['python', 'python3']) {
    const ran = await $.process.run([py, script, 'sym', name, '--root', root, '--limit', '1'], { timeoutMs: 8000 })
      .catch(() => undefined)
    if (ran === undefined || ran.exitCode !== 0) continue
    return symbolLine(ran.stdout)
  }
  return undefined
}

async function nudge($: EngineInterface, tool: string, args: Record<string, unknown>): Promise<string | undefined> {
  if (!(await read($, project)).hasClangd) return undefined
  const names = symbolCandidates(tool, args)
  if (names.length === 0) return undefined
  const id = await $.session.id()
  const st = nudged.get(id) ?? { names: new Set<string>(), lookups: 0 }
  nudged.set(id, st)
  const root = (await $.session.root()).replace(/[\\/]+$/, '')
  const script = `${await home($)}/.claude/skills/game-onboard/scripts/cindex.py`.replace(/\\/g, '/')
  for (const name of names) {
    if (st.names.size >= MAX_NUDGES || st.lookups >= MAX_LOOKUPS) return undefined
    if (st.names.has(name)) continue
    st.lookups += 1
    const found = await lookupSymbol($, script, root, name)
    // 엔진 심볼([E])은 프로젝트 인덱스가 엔진 .cpp 를 안 봐서 refs 가 반쪽이다 — 엔진 안은 ue_q 몫이라 알리지 않는다
    if (found === undefined || found.includes('[E] ')) continue
    st.names.add(name)
    return nudgeText(name, found, script)
  }
  return undefined
}

// 지난 세션: 대화 기록에서 센 요약(game-onboard/scripts/search_history.py). mod 가 켜지기 전 세션까지 들어온다.
// 같은 세션은 mod 가 실시간으로 센 쪽($.store)을 쓴다. 파이썬이나 스크립트가 없으면 $.store 만.
async function pastSessions($: EngineInterface): Promise<SessionSummary[]> {
  const script = `${await home($)}/.claude/skills/game-onboard/scripts/search_history.py`
  const root = await $.session.root()
  for (const py of ['python', 'python3']) {
    const ran = await $.process.run([py, script, root], { timeoutMs: 120000 }).catch(() => undefined)
    if (ran === undefined || ran.exitCode !== 0) continue
    try {
      const list = JSON.parse(ran.stdout) as SessionSummary[]
      return Array.isArray(list) ? list : []
    } catch {
      return []
    }
  }
  return []
}

export function mergeSessions(past: readonly SessionSummary[], live: readonly SessionSummary[]): SessionSummary[] {
  let out = [...past]
  for (const s of live) out = upsertSession(out, s)
  return out
}

async function openHistory($: EngineInterface): Promise<string> {
  await poll($).catch(() => undefined)
  const now = await $.clock.now()
  const live = ((await $.store.get('sessions')) ?? []) as SessionSummary[]
  const sessions = mergeSessions(await pastSessions($), live)
  const logText = await $.fs.read(path || (await logPath($))).catch(() => '')
  const evs = parse(typeof logText === 'string' ? logText : '').slice(-3000)
  const out = `${await home($)}/.claude/cache/game-harness/history.html`
  await $.fs.write(out, historyHtml(sessions, evs, now))
  const isWindows = ((await $.env.get('OS')) ?? '').startsWith('Windows')
  const isMac = out.startsWith('/Users/')
  const argv = isWindows ? ['cmd', '/c', 'start', '', out.replace(/\//g, '\\')] : [isMac ? 'open' : 'xdg-open', out]
  const ran = await $.process.run(argv, { timeoutMs: 15000 }).catch(() => undefined)
  return ran !== undefined && ran.exitCode === 0
    ? `하네스 이력 페이지를 열었다: ${out} (세션 ${sessions.length}개)`
    : `하네스 이력 페이지를 만들었다 — 브라우저로 연다: ${out}`
}

// 내 한 줄 — 한 줄을 넘지 않게 잘라 다른 플러그인 몫의 줄을 남긴다
function searchRow($: EngineInterface, e: Parameters<EngineInterface['ui']['resolve']>[0], c: Counts, idle: boolean) {
  const { Box, Text } = $.ui.resolve(e)
  return (
    <Box key="game-harness-search" flexDirection="row" flexWrap="nowrap">
      <Text bold color="claude">코드 탐색 </Text>
      <Text dimColor>│ 인덱스 </Text>
      {INDEX_KINDS.map((k, i) => (
        <Text key={k} color={c[k] > 0 ? 'success' : k === 'clangd' && idle ? 'warning' : 'subtle'}>
          {i > 0 ? ' · ' : ''}{SHORT[k]} {c[k]}
        </Text>
      ))}
      <Text dimColor> │ 직접 </Text>
      <Text dimColor>{DIRECT_KINDS.map(k => `${SHORT[k]} ${c[k]}`).join(' · ')}</Text>
      {idle ? <Text color="warning"> │ clangd 인덱스가 있는데 grep 만 씀</Text> : <Text dimColor> │ /harness 상세</Text>}
    </Box>
  )
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    $.clock.every(POLL_MS, () => pollSafely($))
    pollSafely($)
    const info = await detectProject($).catch(() => undefined)
    if (info !== undefined) await update($, project, () => info)
    await $.command.register({
      name: 'harness',
      description: '이 세션의 코드 탐색(인덱스 대 직접 검색)과 하네스 기능(훅·스킬·조회 스크립트)을 패널로 보여준다',
    }).catch(() => undefined) // 명령 등록이 막혀도 띠·상태줄·토스트는 돈다
    await $.command.register({
      name: 'harness-history',
      description: '세션별 코드 탐색 · 하네스 기능 이력을 HTML 상세 페이지로 만들어 브라우저로 연다',
    }).catch(() => undefined)
    return next(e)
  })

  // 도구 호출마다: 코드 탐색이면 센다. 하네스 추적 훅(PostToolUse)이 로그를 쓴 직후를 놓치지 않으려고 한 번 더 읽는다.
  // 소스 심볼 grep 이면 결과 뒤에 cindex 안내 한 줄(context)을 붙인다 — 결과 자체는 바꾸지 않는다.
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    const tool = String(e.tool)
    if (tool === 'Skill' || tool === 'Bash' || tool === 'PowerShell' || tool.startsWith('mcp__')) {
      $.clock.after(700, () => pollSafely($))
    }
    if (ran.deny !== undefined) return ran
    const args = e as unknown as Record<string, unknown>
    const hit = classify(tool, args)
    if (hit !== undefined) await record($, hit.kind, hit.what).catch(() => undefined)
    if (hit?.kind !== 'grep') return ran
    const hint = await nudge($, tool, args).catch(() => undefined)
    return hint === undefined ? ran : { ...ran, context: [...(ran.context ?? []), hint] }
  }).catch(($, e, next) => next(e))

  on('command.run', { command: 'harness' }, async $ => {
    await poll($).catch(() => undefined)
    const opened = await $.ui.open({ id: PANE, title: 'Harness' })
    const list = await read($, events)
    if (!opened.isPlaced) {
      return { text: `하네스 패널을 열지 못했다. 이 세션 기록 ${list.length}건 · 로그 ${path} · 이력은 /harness-history` }
    }
    return { text: `하네스 패널을 열었다 (이 세션 기록 ${list.length}건). 세션들 이력은 /harness-history` }
  })

  on('command.run', { command: 'harness-history' }, async $ => ({ text: await openHistory($) }))

  // 프롬프트 위 띠: 이번 세션에 코드를 무엇으로 찾았나. 게임 프로젝트이거나 인덱스를 한 번이라도 썼을 때만.
  // 띠는 다른 플러그인과 나눠 쓴다 — 아래 플러그인(과 엔진)이 그린 것을 next(e) 로 받아 내 한 줄 밑에 그대로 둔다.
  // 내 줄만 돌려주면 그 아래 플러그인의 띠가 사라진다(사용자: "다른 플러그인도 잡아먹는다", 2026-10-20).
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const rest = await next(e)
    const c = await read($, counts)
    const proj = await read($, project)
    const idx = total(c, INDEX_KINDS)
    const dir = total(c, DIRECT_KINDS)
    if (e.props.hasSurvey || idx + dir === 0 || (!proj.isGame && idx === 0)) return rest
    const { Box } = $.ui.resolve(e)
    const idle = clangdIdle(c, proj)
    return (
      <Box flexDirection="column">
        {searchRow($, e, c, idle)}
        {rest}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, events)
    const c = await read($, counts)
    const proj = await read($, project)
    const found = await read($, searches)
    const width = Math.max(20, e.props.bodyColumns)
    const room = Math.max(6, (e.viewport?.rows ?? 30) - 4)
    const idx = total(c, INDEX_KINDS)
    const dir = total(c, DIRECT_KINDS)
    const barW = Math.max(10, Math.min(30, width - 34))
    const max = Math.max(1, ...Object.values(c))
    const byFeature = new Map<string, { count: number; failed: number; last: string }>()
    for (const ev of list) {
      const row = byFeature.get(ev.feature) ?? { count: 0, failed: 0, last: '' }
      row.count += 1
      row.failed += ev.ok ? 0 : 1
      row.last = ev.t.slice(11)
      byFeature.set(ev.feature, row)
    }
    const summary = [...byFeature.entries()]
    const lines = Math.max(2, room - 12 - summary.length)
    const recent = found.slice(-Math.ceil(lines / 2))
    const timeline = list.slice(-Math.floor(lines / 2))
    return (
      <Box flexDirection="column">
        <Text bold>
          코드 탐색 · 인덱스 {idx} · 직접 {dir} ({pct(idx, idx + dir)}% 인덱스)
          {proj.hasClangd ? '' : ' · clangd 인덱스 없음'}
        </Text>
        {(Object.keys(SHORT) as Kind[]).map(k => (
          <Text key={k} wrap="truncate-end"
            color={INDEX_KINDS.includes(k) ? (c[k] > 0 ? 'success' : k === 'clangd' && clangdIdle(c, proj) ? 'warning' : 'subtle') : undefined}
            dimColor={DIRECT_KINDS.includes(k)}>
            {LONG[k].padEnd(12, ' ')} {'█'.repeat(Math.round((c[k] / max) * barW)) || '·'} {c[k]}
          </Text>
        ))}
        <Text dimColor>{'─'.repeat(Math.min(width, 40))}</Text>
        <Text bold>하네스 기능 {summary.length}개 · 기록 {list.length}건</Text>
        {summary.map(([feature, row]) => (
          <Text key={feature} wrap="truncate-end" color={row.failed > 0 ? 'warning' : undefined}>
            {row.failed > 0 ? '✗' : '●'} {label(feature)} ×{row.count}
            {row.failed > 0 ? ` (실패 ${row.failed})` : ''} · {row.last}
          </Text>
        ))}
        <Text dimColor>{'─'.repeat(Math.min(width, 40))}</Text>
        {recent.map(s => (
          <Text key={`s${s.ts}${s.kind}`} wrap="truncate-end" color={INDEX_KINDS.includes(s.kind) ? 'success' : undefined}
            dimColor={DIRECT_KINDS.includes(s.kind)}>
            {stamp(s.ts).slice(11)} {SHORT[s.kind]} {s.what}
          </Text>
        ))}
        {timeline.map(ev => (
          <Text key={`e${ev.ts}${ev.feature}`} wrap="truncate-end" dimColor={ev.ok} color={ev.ok ? undefined : 'error'}>
            {ev.t.slice(11)} {ev.ok ? '✓' : '✗'} {label(ev.feature)}{ev.detail ? ` — ${ev.detail}` : ''}
          </Text>
        ))}
        <Text dimColor>세션들 이력: /harness-history</Text>
      </Box>
    )
  })
}
