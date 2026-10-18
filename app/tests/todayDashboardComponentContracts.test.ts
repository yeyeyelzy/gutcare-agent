import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const page = readFileSync(new URL('../src/pages/tabs/today/index.vue', import.meta.url), 'utf8')

describe('B09b today real-data dashboard contract', () => {
  it('uses at most five independent APIs, minimal advice/risk pages, and profile-local trend range', () => {
    for (const key of ['riskApiKey', 'medicationApiKey', 'notificationApiKey', 'adviceApiKey', 'trendApiKey']) expect(page).toContain(key)
    expect(page).toContain("riskApi.list({ limit: 3, unread_only: true })")
    expect(page).toContain('medicationApi.listTodayCheckins()')
    expect(page).toContain('notificationApi.unreadCount()')
    expect(page).toContain('adviceApi.list({ limit: 1 })')
    expect(page).toContain('formatTodayDateLabel(auth.profile?.timezone, dashboardNow.value)')
    expect(page).toContain('buildTodayTrendQuery(auth.profile?.timezone, dashboardNow.value)')
    expect(page).toContain('dashboardNow.value = new Date()')
    expect(page).toContain('trendApi.get(range.query)')
    expect(page).not.toContain('riskApi.get(')
    expect(page).not.toContain('adviceApi.get(')
  })

  it('keeps risk before recent advice, displays backend status, and never implies pending/valid advice', () => {
    expect(page.indexOf('data-testid="today-risk-alerts"')).toBeLessThan(page.indexOf('data-testid="today-summary"'))
    expect(page).toContain('最近建议')
    expect(page).toContain('adviceStatusLabel(advice.status)')
    expect(page).not.toMatch(/待处理建议|有效建议/)
    expect(page).toContain('item.recommended_action')
    expect(page).toContain('riskAlerts.value = result.items')
  })

  it('retains per-card retry/error states and invalidates asynchronous writes while hidden', () => {
    for (const id of ['today-risk-refresh-retry', 'today-notification-retry', 'today-advice-retry', 'today-medication-refresh-retry', 'today-trend-retry']) expect(page).toContain(id)
    for (const text of ['加载失败不代表没有风险', '未按失败推断为 0', '仍显示上次载入']) expect(page).toContain(text)
    expect(page).toContain('onHide(() => invalidatePageRequests())')
    expect(page).toContain('onUnload(() => invalidatePageRequests())')
    expect(page).toContain('generation += 1')
    expect(page).toContain('return visible && generation === current && authorized.value')
    expect(page).toContain('if (visible) return')
  })

  it('renders consent-required mood independently from an available empty bucket and uses protected routes', () => {
    expect(page).toContain("metric.state === 'consent_required'")
    expect(page).toContain('当前不是空数据')
    expect(page).toContain("router?.navigate('privacyCenter')")
    expect(page).toContain("router?.navigateRiskAlertDetail(item.id)")
    expect(page).toContain("navigateAdviceDetail(advice.id, 'me', 'list')")
    expect(page).not.toContain('patient_id')
    expect(page).not.toContain('health summary')
  })
})
