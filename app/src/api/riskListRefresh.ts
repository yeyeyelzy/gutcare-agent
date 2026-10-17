import type { RiskAlertPage } from './openapiTypes'

export interface RiskListSnapshot {
  items: RiskAlertPage['items']
  cursor: string | null
}

/** Consume the initial page show, because onLoad already performs the first fetch. */
export class RiskListFirstShowGate {
  private initialShow = true

  shouldFetch(): boolean {
    if (this.initialShow) {
      this.initialShow = false
      return false
    }
    return true
  }
}

/** Refresh a visible list from the server; on failure keep its last good snapshot. */
export async function safeRefreshRiskList(
  current: RiskListSnapshot,
  fetchPage: () => Promise<RiskAlertPage>,
): Promise<{ snapshot: RiskListSnapshot; error: unknown | null }> {
  try {
    const page = await fetchPage()
    return { snapshot: { items: page.items, cursor: page.next_cursor }, error: null }
  } catch (error) {
    return { snapshot: current, error }
  }
}
