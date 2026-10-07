// game-harness-monitor — 하네스가 이 세션에서 "어떤 기능을 동작시키기 시작했는지" 보여준다.
//
// 근거 자료는 하네스 훅·스크립트가 남기는 이벤트 로그 하나다
// (~/.claude/cache/game-harness/events.jsonl, 형식은 skills/game-bootstrap/harness/harness_events.py).
// 이 mod 는 그 로그를 읽기만 한다. 로그에 쓰지 않고, 도구 호출을 막거나 바꾸지 않는다.
//
//   상태줄  harness ● 기능 N개 · 마지막 <기능>   (이 세션에서 하나라도 동작한 뒤부터)
//   토스트  기능이 이 세션에서 처음 동작할 때 한 번
//   /harness 패널: 기능별 횟수와 시간순 기록
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { HarnessEvent } from '../types'

const PANE = 'game-harness'
const POLL_MS = 3000
const KEEP = 300
const events = atom({ plugin: 'game-harness-monitor', key: 'events' } as const, [] as HarnessEvent[])

const LABELS: Record<string, string> = {
  'context.routing': '세션 라우팅 주입',
  'handoff.inject': 'HandOff 주입',
  'handoff.write': 'HandOff 작성',
  'stuck.warn': '매몰 경고',
  'mcp.guard': 'MCP 가드 경고',
  'mcp.call': 'MCP 호출 기록',
  'diagram.render': '그림 렌더 (브라우저)',
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

async function logPath($: EngineInterface): Promise<string> {
  const custom = await $.env.get('GAME_HARNESS_EVENTS')
  if (custom) return custom
  const home = (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? ''
  return `${home.replace(/[\\/]+$/, '')}/.claude/cache/game-harness/events.jsonl`
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

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    $.clock.every(POLL_MS, () => pollSafely($))
    pollSafely($)
    await $.command.register({
      name: 'harness',
      description: '이 세션에서 동작한 하네스 기능(훅·스킬·조회 스크립트)을 패널로 보여준다',
    }).catch(() => undefined) // 명령 등록이 막혀도 상태줄·토스트는 돈다
    return next(e)
  })

  // 하네스 추적 훅(PostToolUse)이 로그를 쓴 직후를 놓치지 않으려고, 해당 도구 호출 뒤에 한 번 더 읽는다.
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    const tool = String(e.tool)
    if (tool === 'Skill' || tool === 'Bash' || tool === 'PowerShell' || tool.startsWith('mcp__')) {
      $.clock.after(700, () => pollSafely($))
    }
    return ran
  }).catch(($, e, next) => next(e))

  on('command.run', { command: 'harness' }, async $ => {
    await poll($).catch(() => undefined)
    const opened = await $.ui.open({ id: PANE, title: 'Harness' })
    const list = await read($, events)
    if (!opened.isPlaced) {
      return { text: `하네스 패널을 열지 못했다. 이 세션 기록 ${list.length}건 · 로그 ${path}` }
    }
    return { text: `하네스 패널을 열었다 (이 세션 기록 ${list.length}건).` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, events)
    const width = Math.max(20, e.props.bodyColumns)
    const room = Math.max(4, (e.viewport?.rows ?? 30) - 4)
    if (list.length === 0) {
      return (
        <Box flexDirection="column">
          <Text>이 세션에서 동작한 하네스 기능이 아직 없다.</Text>
          <Text dimColor wrap="truncate-middle">로그: {path === '' ? '(아직 안 읽음)' : path}</Text>
        </Box>
      )
    }
    const byFeature = new Map<string, { count: number; failed: number; last: string }>()
    for (const ev of list) {
      const row = byFeature.get(ev.feature) ?? { count: 0, failed: 0, last: '' }
      row.count += 1
      row.failed += ev.ok ? 0 : 1
      row.last = ev.t.slice(11)
      byFeature.set(ev.feature, row)
    }
    const summary = [...byFeature.entries()]
    const timeline = list.slice(-Math.max(1, room - summary.length - 2))
    return (
      <Box flexDirection="column">
        <Text bold>기능 {summary.length}개 · 기록 {list.length}건</Text>
        {summary.map(([feature, row]) => (
          <Text wrap="truncate-end" color={row.failed > 0 ? 'warning' : undefined}>
            {row.failed > 0 ? '✗' : '●'} {label(feature)} ×{row.count}
            {row.failed > 0 ? ` (실패 ${row.failed})` : ''} · {row.last}
          </Text>
        ))}
        <Text dimColor>{'─'.repeat(Math.min(width, 40))}</Text>
        {timeline.map(ev => (
          <Text wrap="truncate-end" dimColor={ev.ok} color={ev.ok ? undefined : 'error'}>
            {ev.t.slice(11)} {ev.ok ? '✓' : '✗'} {label(ev.feature)}{ev.detail ? ` — ${ev.detail}` : ''}
          </Text>
        ))}
      </Box>
    )
  })
}
