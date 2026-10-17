import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const page = readFileSync(new URL('../src/pages/history/index.vue', import.meta.url), 'utf8')
const recordsTab = readFileSync(new URL('../src/pages/tabs/records/index.vue', import.meta.url), 'utf8')

describe('F11 history page contract', () => {
  it('is a protected named route with first-show deduplication and stale-response invalidation', () => {
    expect(page).toContain("canRenderRoute('history', auth.state)")
    expect(page).toContain("router?.requireAuthentication('history')")
    expect(page).toContain('firstShow.shouldRefresh()')
    expect(page).toContain('onHide(() => { generation += 1; busy.value = false })')
    expect(page).toContain('isHistoryResponseCurrent(requestGeneration, generation, pageReady.value, canRenderRoute(\'history\', auth.state))')
    expect(page).toContain("router?.switchTab(ownerTab.value)")
    expect(recordsTab).toContain("router?.navigate('history')")
  })

  it('shows only category, time and fixed target actions without mood notes or sensitive summaries', () => {
    expect(page).toContain('labelFor(event.type)')
    expect(page).toContain('formatDate(event.occurred_at)')
    expect(page).toContain('mapHistoryTarget(event.target)')
    expect(page).toContain('mapHistoryTarget(event.target).name !== \'unavailable\'')
    expect(page).not.toContain('event.note')
    expect(page).not.toContain('event.emotion_tags')
    expect(page).not.toContain('event.summary')
    expect(page).toContain('时间线不包含备注、心情标签、摘要或诊断推断。')
  })

  it('distinguishes empty, network error, refresh failure and append failure while preserving old cursor and items', () => {
    expect(page).toContain('history-empty')
    expect(page).toContain('history-error')
    expect(page).toContain('history-refresh-error')
    expect(page).toContain('history-more-error')
    expect(page).toContain('failHistoryAppend(')
    expect(page).toContain('items.value = failed.items; cursor.value = failed.cursor')
    expect(page).toContain('history-more-retry')
    expect(page).toContain('cursor.value = null')
    expect(page).toContain('category: selectedCategories.value, since: bounds.since, until: bounds.until')
  })

  it('checks visibility and request generation after every list await before applying success or failure', () => {
    const reload = page.slice(page.indexOf('async function reload('), page.indexOf('async function loadMore('))
    const append = page.slice(page.indexOf('async function loadMore('), page.indexOf('function toggleCategory('))
    const reloadAwait = reload.indexOf('await api.list(')
    const reloadSuccessGuard = reload.indexOf('if (!isCurrentPage(requestGeneration)) return', reloadAwait)
    const reloadMutation = reload.indexOf('items.value = page.items', reloadAwait)
    const reloadFailureGuard = reload.indexOf('if (!isCurrentPage(requestGeneration)) return', reloadSuccessGuard + 1)
    const appendAwait = append.indexOf('await api.list(')
    const appendSuccessGuard = append.indexOf('if (!isCurrentPage(requestGeneration)) return', appendAwait)
    const appendMutation = append.indexOf('const next = appendHistoryPage', appendAwait)
    const appendFailureGuard = append.indexOf('if (!isCurrentPage(requestGeneration)) return', appendSuccessGuard + 1)
    expect(reloadAwait).toBeGreaterThanOrEqual(0)
    expect(reloadSuccessGuard).toBeGreaterThan(reloadAwait)
    expect(reloadMutation).toBeGreaterThan(reloadSuccessGuard)
    expect(reloadFailureGuard).toBeGreaterThan(reloadMutation)
    expect(appendSuccessGuard).toBeGreaterThan(appendAwait)
    expect(appendMutation).toBeGreaterThan(appendSuccessGuard)
    expect(appendFailureGuard).toBeGreaterThan(appendMutation)
  })
})
