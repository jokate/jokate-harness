export type HarnessEvent = {
  ts: number
  t: string
  session: string
  project: string
  feature: string
  ok: boolean
  detail: string
  source: string
}

// 코드를 무엇으로 찾았나 — 인덱스(gq · clangd · 위키 · ue_q)와 직접 검색(grep · 파일 찾기 · 파일 읽기)
export type Kind = 'gq' | 'clangd' | 'wiki' | 'ue_q' | 'grep' | 'glob' | 'read'
export type Counts = Record<Kind, number>
export type SearchEvent = { ts: number; kind: Kind; what: string }
export type ProjectInfo = { isGame: boolean; hasClangd: boolean; hasWiki: boolean }
// 세션 하나의 탐색 요약 — $.store 'sessions' 에 세션을 넘어 남는다(이력 페이지 재료)
export type SessionSummary = {
  id: string
  project: string
  started: number
  updated: number
  hasClangd: boolean
  counts: Counts
}

declare module 'claude-code' {
  interface PluginState {
    'game-harness-monitor': {
      events: HarnessEvent[]
      counts: Counts
      searches: SearchEvent[]
      project: ProjectInfo
    }
  }
}
