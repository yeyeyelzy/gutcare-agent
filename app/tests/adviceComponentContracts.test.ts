import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const workspace = readFileSync(new URL('../src/components/AdviceWorkspace.vue', import.meta.url), 'utf8')
const routes = readFileSync(new URL('../src/navigation/routes.ts', import.meta.url), 'utf8')
const router = readFileSync(new URL('../src/navigation/router.ts', import.meta.url), 'utf8')

describe('F09 advice workspace component contracts', () => {
  it('authenticates list/detail before API calls and invalidates hidden requests', () => {
    expect(workspace).toContain('canRenderRoute(props.routeName, auth.state)')
    expect(workspace).toContain('router?.requireAuthentication(props.routeName)')
    expect(workspace).toContain('if (!api || !visible.value')
    expect(workspace).toContain('onHide(() => { visible.value = false; generation += 1; busy.value = false })')
    expect(workspace).toContain('return visible.value && generation === requestGeneration')
    for (const testId of ['advice-list-loading', 'advice-list-error', 'advice-empty', 'advice-more-error', 'advice-detail-loading', 'advice-detail-error', 'advice-detail-refresh-error']) expect(workspace).toContain(testId)
    expect(workspace).toContain('现有内容与分页位置仍保留')
  })

  it('preserves owner/from navigation and only accepts notification returns from the in-memory allowlist', () => {
    expect(routes).toContain("analysisAdvice: { path: '/pages/advice/analysis'")
    expect(routes).toContain("advice: { path: '/pages/advice/index'")
    expect(routes).toContain("adviceDetail: { path: '/pages/advice/detail'")
    expect(workspace).toContain("options?.from === 'list' || options?.from === 'history'")
    expect(workspace).toContain("options?.from === 'notification'")
    expect(workspace).toContain("notificationReturnId.value ? 'notification' : 'external'")
    expect(workspace).toContain("router?.takeAdviceNotificationReturn() ?? null")
    expect(workspace).toContain("router?.navigateAdviceDetail(id, ownerTab.value, 'list')")
    expect(workspace).toContain('router?.returnFromAdvice(ownerTab.value, from.value, notificationReturnId.value)')
    expect(workspace).toContain('@click="goBack"')
    expect(workspace).toContain('onBackPress(() => { goBack(); return true })')
    expect(router).toContain('saveAdviceTarget')
    expect(router).toContain('navigateAdviceDetail')
  })

  it('keeps risk priority and evidence/citation rendering inside fixed safe allowlists', () => {
    expect(workspace).toContain('detail.risk_priority_context')
    expect(workspace).toContain('router?.navigateRiskAlertDetail')
    expect(workspace).toContain('riskPriorityStatusLabel')
    expect(workspace).toContain('adviceEvidenceLabel(item)')
    expect(workspace).toContain('knowledgeCitationHost(item)')
    expect(workspace).not.toContain('{{ item.locator }}')
    expect(workspace).not.toContain('detail.body,')
    for (const forbidden of ['item.note', 'item.emotion_tags', 'callback_id', 'raw_output', 'prompt', 'console.log']) expect(workspace).not.toContain(forbidden)
    expect(workspace).toContain('建议正文不会写入通知预览、日志或埋点。')
  })

  it('uses explicit read/archive/feedback actions and never auto-overwrites on 409', () => {
    for (const action of ['api.markRead(', 'api.archive(', 'api.feedback(']) expect(workspace).toContain(action)
    expect(workspace).toContain('expected_version: advice.feedback?.version ?? 0')
    expect(workspace).toContain('createIdempotencyKey()')
    expect(workspace).toContain('没有覆盖现有内容，也没有自动重新提交')
    expect(workspace).toContain('basis_updated')
  })
})
