import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const workspace = readFileSync(new URL('../src/components/RiskAlertWorkspace.vue', import.meta.url), 'utf8')
const today = readFileSync(new URL('../src/pages/tabs/today/index.vue', import.meta.url), 'utf8')

describe('F10 risk UI contract', () => {
  it('gates before API calls, keeps list/detail and pagination states explicit', () => {
    expect(workspace).toContain('canRenderRoute(props.routeName, auth.state)')
    expect(workspace).toContain('router?.requireAuthentication(props.routeName)')
    for (const call of ['api.list(', 'api.get(alertId.value)', 'api.markRead(', 'api.reevaluate(']) expect(workspace).toContain(call)
    for (const id of ['risk-list-loading', 'risk-list-error', 'risk-empty', 'risk-more', 'risk-more-retry', 'risk-detail-loading', 'risk-detail-error']) expect(workspace).toContain(id)
    expect(workspace).toContain('现有提示仍保留')
  })

  it('does not conflate read/reevaluation with resolution or safety and visibly prioritizes emergency action', () => {
    expect(workspace).toContain('已查看或已重新评估仅表示记录状态变化，不代表风险解除或确认安全。')
    expect(workspace).toContain('已重新评估 · 非安全结论')
    expect(workspace).toContain('{{ alert.recommended_action }}')
    expect(workspace).toContain('紧急提示')
    expect(workspace).toContain('severityIcon')
    expect(workspace).not.toContain('rule_code')
    expect(workspace).not.toContain('evidence.')
  })

  it('loads the real unread risk card and never maps request failure to no risk', () => {
    expect(today).toContain('riskApi.list({ limit: 3, unread_only: true })')
    expect(today).toContain('加载失败不代表没有风险')
    expect(today).toContain('router?.navigateRiskAlertDetail(item.id)')
    expect(today).toContain('today-risk-status')
    expect(today).toContain('item.recommended_action')
    expect(today).toContain("onShow(() => {")
    expect(today).toContain('void loadTodayMedication(current)')
    expect(today).toContain('void loadTodayRisk(current)')
  })

  it('refreshes the same list filter when returning from detail without duplicate initial fetch or losing cached cards on error', () => {
    expect(workspace).toContain('const firstShowGate = new RiskListFirstShowGate()')
    expect(workspace).toContain('if (!detail.value && firstShowGate.shouldFetch()) void reload(true)')
    expect(workspace).toContain('api.list({ limit: 20, unread_only: unreadOnly.value })')
    expect(workspace).toContain('safeRefreshRiskList({ items: alerts.value, cursor: cursor.value }, loadPage)')
    expect(workspace).toContain('refreshError.value = \'刷新失败，仍显示上次载入的风险提示；可重试。\'')
    expect(workspace).toContain('data-testid="risk-refresh-retry"')
    expect(workspace).toContain('alerts.value = result.snapshot.items')
  })
})
