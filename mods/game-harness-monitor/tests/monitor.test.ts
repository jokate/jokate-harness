import { expect, mock, test } from 'claude-code/testing'

import { belongs, label, parse, statusText } from '../hooks/register'

const LOG = '/home/u/.claude/cache/game-harness/events.jsonl'

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
  on('fs.stat', ($, e) => {
    expect(e.path).toBe(LOG)
    return { value: { kind: 'file', size: text.length, mtimeMs: mtime, isLink: false } }
  })
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
  expect(ran).toMatchObject({ text: '하네스 패널을 열었다 (이 세션 기록 3건).' })

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
