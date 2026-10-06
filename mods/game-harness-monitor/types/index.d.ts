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

declare module 'claude-code' {
  interface PluginState {
    'game-harness-monitor': { events: HarnessEvent[] }
  }
}
