import { expect, mock, test } from 'claude-code/testing'

import { belongs, classify, clangdIdle, emptyCounts, historyHtml, label, mergeSessions, parse, statusText, upsertSession } from '../hooks/register'

const LOG = '/home/u/.claude/cache/game-harness/events.jsonl'
// 엔진이 경로를 그 OS 의 모양으로 바꿔 넘긴다(Windows: C:\home\u\...) — 끝 부분으로 맞춘다
const at = (p: string, tail: string) => p.replace(/\\/g, '/').toLowerCase().endsWith(tail.toLowerCase())

const line = (o: Record<string, unknown>) => JSON.stringify({
  ts: 1000, t: '2026-10-06 10:00:00', session: '', project: '', feature: 'x', ok: true, detail: '', source: 't', ...o,
})

test('기능 id 를 사람이 읽는 이름으로 바꾼다', () => {
  expect(label('skill.game-architecture')).toBe('스킬 game-architecture')
  expect(label('script.ue_q.sym')).toBe('조회 ue_q.sym')
  expect(label('context.routing')).toBe('세션 라우팅 주입')
  expect(label('diagram.render')).toBe('그림 렌더 (브라우저)')
  expect(label('weird')).toBe('weird')
})

test('세션 id 가 있으면 id 로, 없으면 프로젝트 경로와 시각으로 이 세션 것을 가른다', () => {
  const base = { ts: 5000, t: '', feature: 'x', ok: true, detail: '', source: '' }
  expect(belongs({ ...base, session: 'S1', project: '' }, 'S1', 'C:/P', 0)).toBe(true)
  expect(belongs({ ...base, session: 'S2', project: 'C:/P' }, 'S1', 'C:/P', 0)).toBe(false)
  expect(belongs({ ...base, session: '', project: 'C:\\Work\\Game' }, 'S1', 'c:/work/game/Source', 1000)).toBe(true)
  expect(belongs({ ...base, session: '', project: 'C:\\Work\\Game' }, 'S1', 'c:/work/game', 9000)).toBe(false)
  expect(belongs({ ...base, session: '', project: 'C:\\Work\\Other' }, 'S1', 'c:/work/game', 0)).toBe(false)
})

test('반쯤 쓰인 줄과 빈 줄은 버린다', () => {
  const text = [line({ feature: 'a' }), '{"ts": 1, "feat', '', line({ feature: 'b' })].join('\n')
  expect(parse(text).map(ev => ev.feature)).toEqual(['a', 'b'])
})

test('상태줄은 동작한 기능 수와 마지막 기능, 실패 수를 보인다', () => {
  expect(statusText([])).toBeUndefined()
  const list = parse([line({ feature: 'skill.game-onboard' }), line({ feature: 'script.ue_q.sym', ok: false })].join('\n'))
  expect(statusText(list)).toBe('harness ● 기능 2개 · 마지막 조회 ue_q.sym ✗ · 실패 1')
})

test('세션 시작 뒤 로그에 이 세션의 하네스 기능이 나타나면 상태줄과 토스트로 알린다', async ($, on) => {
  const clock = mock.clock(on, { now: 0 })
  mock.env(on, { HOME: '/home/u' })
  let text = line({ session: 'OTHER', feature: 'skill.game-patterns' })
  let mtime = 1
  const statuses: (string | undefined)[] = []
  const toasts: string[] = []
  on('fs.stat', ($, e) => (at(e.path, LOG)
    ? { value: { kind: 'file', size: text.length, mtimeMs: mtime, isLink: false } }
    : { deny: 'no such file' }) as never)
  on('fs.list', () => ({ value: [] }) as never)
  on('store.get', () => ({ value: undefined }) as never)
  on('store.set', () => ({ value: undefined }) as never)
  on('fs.read', () => ({ value: text }))
  on('session.id', () => ({ value: 'S1' }))
  on('session.root', () => ({ value: '/proj' }))
  on('session.usage', () => ({ value: { startedAt: 0 } }) as never)
  on('command.register', () => ({ value: undefined }) as never)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('ui.status', ($, e) => { statuses.push(e.text); return { value: undefined } as never })
  on('ui.toast', ($, e) => { toasts.push(e.text); return { value: undefined } as never })
  on('ui.open', () => ({ value: { isPlaced: true } }) as never)

  await $.session.start({ cwd: '/proj', surface: null, isInteractive: false })
  await clock.advance(10)
  expect(toasts).toEqual([])

  text += '\n' + line({ ts: 2000, session: 'S1', feature: 'context.routing' })
  text += '\n' + line({ ts: 2100, session: 'S1', feature: 'skill.game-architecture' })
  mtime = 2
  await clock.advance(3000)
  expect(toasts).toEqual(['하네스 기능 시작: 세션 라우팅 주입, 스킬 game-architecture'])
  expect(statuses.at(-1)).toBe('harness ● 기능 2개 · 마지막 스킬 game-architecture')

  text += '\n' + line({ ts: 2200, session: 'S1', feature: 'skill.game-architecture' })
  mtime = 3
  await clock.advance(3000)
  expect(toasts).toHaveLength(1)

  const ran = await $.command.run({ command: 'harness', args: '' } as never)
  expect(ran).toMatchObject({ text: '하네스 패널을 열었다 (이 세션 기록 3건). 세션들 이력은 /harness-history' })

  const props = {
    title: 'Harness', isFocused: false, bodyColumns: 60, placement: 'dock' as const,
    scroll: { offset: 0, bodyRows: 20 }, view: {},
  }
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'game-harness-monitor', surface, component: 'Pane', requestId: 'game-harness', props })
    expect(await ui.find({ type: 'Text', text: /기능 2개 · 기록 3건/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /스킬 game-architecture ×2/ })).toBeDefined()
    await ui.unmount()
  }
})

test('도구 호출을 코드 탐색 종류로 가른다 — 인덱스(gq · clangd · 위키 · ue_q) 대 직접(grep · 찾기 · 읽기)', () => {
  const bash = (command: string) => classify('Bash', { command })
  expect(bash('python ~/.claude/skills/game-onboard/scripts/cindex.py callers UFoo --root P')).toEqual({ kind: 'clangd', what: 'callers UFoo' })
  expect(bash('python "C:/x/game-onboard/scripts/gq.py" find Ability')).toEqual({ kind: 'gq', what: 'find Ability' })
  expect(bash('python ~/.claude/wiki-harness/scripts/wq.py brief --wiki W')?.kind).toBe('wiki')
  expect(bash('python ue_q.py sym AActor')?.kind).toBe('ue_q')
  expect(bash('rg -n "Hit" Source')?.kind).toBe('grep')
  expect(classify('PowerShell', { command: 'Get-ChildItem -Recurse *.h' })?.kind).toBe('glob')
  expect(bash('git status')).toBeUndefined()
  expect(classify('Grep', { pattern: 'IsHittable' })).toEqual({ kind: 'grep', what: 'IsHittable' })
  expect(classify('Glob', { pattern: '**/*.cpp' })?.kind).toBe('glob')
  expect(classify('Read', { file_path: 'C:/P/Source/A.cpp' })).toEqual({ kind: 'read', what: 'A.cpp' })
  expect(classify('Read', { file_path: 'C:\\Users\\u\\.jokate-wiki\\MNYS\\index.md' })?.kind).toBe('wiki')
  expect(classify('Edit', { file_path: 'a' })).toBeUndefined()
})

test('clangd 인덱스가 있는데 0회 · grep 5회 이상이면 알린다', () => {
  const c = { ...emptyCounts(), grep: 5 }
  expect(clangdIdle(c, { isGame: true, hasClangd: true, hasWiki: false })).toBe(true)
  expect(clangdIdle(c, { isGame: true, hasClangd: false, hasWiki: false })).toBe(false)
  expect(clangdIdle({ ...c, clangd: 1 }, { isGame: true, hasClangd: true, hasWiki: false })).toBe(false)
})

test('이력 페이지: 세션별 탐색 · 인덱스 비율 · clangd 미사용 표시 · 기능 합계 · 다크 모드', () => {
  const now = Date.UTC(2026, 9, 20, 12)
  const s = (id: string, counts: Partial<ReturnType<typeof emptyCounts>>, hasClangd = true) => ({
    id, project: 'C:/Proj/MNYS', started: now - 3600_000, updated: now - 60_000, hasClangd, counts: { ...emptyCounts(), ...counts },
  })
  let list = upsertSession([], s('A', { gq: 2, grep: 8 }))
  list = upsertSession(list, s('A', { gq: 3, grep: 9 }))  // 같은 세션은 갱신
  list = upsertSession(list, s('B', { clangd: 4, grep: 1 }))
  expect(list).toHaveLength(2)
  const evs = parse([line({ feature: 'skill.game-architecture', t: '2026-10-20 11:00:00' }),
    line({ feature: 'script.cindex.callers', ok: false, detail: 'cindex.py callers <X>' })].join('\n'))
  const page = historyHtml(list, evs, now)
  expect(page).toContain('<h1>하네스 이력</h1>')
  expect(page).toContain('MNYS')
  expect(page).toContain('class="n warn">0</td>')  // 세션 A: clangd 0 · grep 9
  expect(page).toContain('스킬 game-architecture')
  expect(page).toContain('cindex.py callers &lt;X&gt;')  // 이스케이프
  expect(page).toContain(':root[data-theme=dark]')
  expect(page).toContain('id="theme"')
})

test('코드 탐색을 세어 프롬프트 위 띠로 크게 보이고, clangd 를 처음 쓰면 토스트', async ($, on) => {
  mock.clock(on, { now: 0 })
  mock.env(on, { HOME: '/home/u' })
  const toasts: string[] = []
  const stored: Record<string, unknown> = {}
  on('fs.stat', ($, e) => (at(e.path, '/proj/Saved/ClaudeIndex/clangd.sqlite')
    ? { value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }
    : { deny: 'no such file' }) as never)
  on('fs.list', () => ({ value: [{ name: 'Game.uproject', kind: 'file', size: 1, mtimeMs: 1, isLink: false }] }) as never)
  on('store.get', ($, e) => ({ value: stored[e.key] }) as never)
  on('store.set', ($, e) => { stored[e.key] = e.value; return { value: undefined } as never })
  on('session.id', () => ({ value: 'S1' }))
  on('session.root', () => ({ value: '/proj' }))
  on('session.usage', () => ({ value: { startedAt: 0 } }) as never)
  on('command.register', () => ({ value: undefined }) as never)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('ui.status', () => ({ value: undefined }) as never)
  on('ui.toast', ($, e) => { toasts.push(e.text); return { value: undefined } as never })
  on('tool.call', () => ({ result: 'ok' }) as never)
  // 아래에 깔린 다른 플러그인의 띠 — 내 띠가 그것을 가리면 안 된다
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => $.ui.resolve(e).Text({ children: '다른 플러그인 띠' }))

  await $.session.start({ cwd: '/proj', surface: null, isInteractive: false })
  const bandProps = { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 6 }, view: {} }
  for (const surface of ['terminal', 'desktop'] as const) {  // 센 것이 없을 때: 다른 플러그인 띠만
    const ui = await $.ui.mount({ plugin: 'game-harness-monitor', surface, component: 'AbovePrompt', props: bandProps } as never)
    expect(await ui.find({ type: 'Text', text: /다른 플러그인 띠/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /코드 탐색/ })).toBeUndefined()
    await ui.unmount()
  }
  for (let i = 0; i < 5; i += 1) await $.tool.call({ tool: 'Grep', pattern: 'Hit', tool_use_id: `g${i}` } as never)
  await $.tool.call({ tool: 'Read', file_path: '/proj/Source/A.cpp', tool_use_id: 'r1' } as never)

  const props = { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 6 }, view: {} }
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'game-harness-monitor', surface, component: 'AbovePrompt', props } as never)
    expect(await ui.find({ type: 'Text', text: /코드 탐색/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /clangd 인덱스가 있는데 grep 만 씀/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /다른 플러그인 띠/ })).toBeDefined()  // 띠를 나눠 쓴다
    await ui.unmount()
  }

  await $.tool.call({ tool: 'Bash', command: 'python ~/.claude/skills/game-onboard/scripts/cindex.py callers UFoo', tool_use_id: 'c1' } as never)
  expect(toasts).toContain('clangd 의미 인덱스 사용: callers UFoo')
  const sessions = stored.sessions as { id: string; counts: Record<string, number> }[]
  expect(sessions.at(-1)?.counts).toMatchObject({ grep: 5, read: 1, clangd: 1 })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'game-harness-monitor', surface, component: 'AbovePrompt', props } as never)
    expect(await ui.find({ type: 'Text', text: /clangd 1/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /grep 만 씀/ })).toBeUndefined()
    await ui.unmount()
  }
})

test('지난 세션(대화 기록에서 센 것)과 실시간 요약을 합친다 — 같은 세션은 실시간 쪽', () => {
  const s = (id: string, grep: number) => ({ id, project: 'P', started: id === 'A' ? 1 : 2, updated: 3, hasClangd: true,
    counts: { ...emptyCounts(), grep } })
  const merged = mergeSessions([s('A', 5), s('B', 1)], [s('B', 9)])
  expect(merged.map(x => [x.id, x.counts.grep])).toEqual([['A', 5], ['B', 9]])
})
