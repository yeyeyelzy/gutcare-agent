import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { isUuid, mapNotificationTarget } from '../src/navigation/routes'

const workspace = readFileSync(new URL('../src/components/NotificationWorkspace.vue', import.meta.url), 'utf8')
const today = readFileSync(new URL('../src/pages/tabs/today/index.vue', import.meta.url), 'utf8')
const me = readFileSync(new URL('../src/pages/tabs/me/index.vue', import.meta.url), 'utf8')
const generated = readFileSync(new URL('../src/api/openapiTypes.ts', import.meta.url), 'utf8')

describe('F12 notification UI contract', () => {
  it('gates before API calls and covers filters, cursor, loading/empty/offline/error and retry states', () => {
    expect(workspace).toContain('canRenderRoute(props.routeName, auth.state)')
    expect(workspace).toContain('router?.requireAuthentication(props.routeName)')
    for (const call of ['api.list(', 'api.get(itemId.value)', 'api.markRead(', 'api.markBatchRead(', 'api.unreadCount()', 'api.getPreferences()', 'api.updatePreferences(']) expect(workspace).toContain(call)
    for (const testId of ['notification-list-loading', 'notification-list-error', 'notification-empty', 'notification-more', 'notification-more-retry', 'notification-batch-error', 'notification-detail-loading', 'notification-detail-error', 'notification-target-unavailable']) expect(workspace).toContain(testId)
    expect(workspace).toContain('现有通知仍保留')
    expect(workspace).toContain('if (!detail.value && !isPreferences.value && !isTarget.value && firstShow.shouldRefresh()) { void reload(true); void loadUnreadCount() }')
    expect(workspace).toContain('function findOwnerTab(): AppTabName')
    expect(workspace).toContain('router?.switchTab(ownerTab.value)')
    const batch = workspace.slice(workspace.indexOf('async function markSelectedRead()'), workspace.indexOf('async function loadUnreadCount()'))
    const failureBranch = batch.slice(batch.indexOf('} catch (error)'))
    expect(failureBranch).not.toContain('items.value =')
    expect(failureBranch).not.toContain('selectedIds.value =')
    expect(workspace).toContain('router?.navigateRiskAlertDetail(target.id)')
    expect(workspace).toContain("router?.navigate('medications')")
    expect(workspace).toContain('router?.navigateNotificationTarget(target.kind, target.id)')
    expect(workspace).toContain("router?.navigateAdviceDetail(target.id, 'me', 'notification', value.id)")
  })

  it('renders each notification error region once and preserves batch selection and items on failure', () => {
    const alertTestIds = [...workspace.matchAll(/role="alert"[^>]*data-testid="([^"]+)"/g)].map((match) => match[1])
    expect(alertTestIds).toContain('notification-batch-error')
    expect(new Set(alertTestIds).size).toBe(alertTestIds.length)
    for (const testId of [
      'notification-prefs-error', 'notification-detail-error', 'notification-batch-error',
      'notification-refresh-error', 'notification-more-error',
    ]) {
      expect(workspace.split(`test-id="${testId}"`).length - 1 + workspace.split(`data-testid="${testId}"`).length - 1).toBe(1)
    }
    const batchErrorRegion = workspace.slice(workspace.indexOf('data-testid="notification-batch-error"') - 100, workspace.indexOf('data-testid="notification-batch-error"') + 180)
    expect(batchErrorRegion.match(/role="alert"/g)).toHaveLength(1)
    const batch = workspace.slice(workspace.indexOf('async function markSelectedRead()'), workspace.indexOf('async function loadUnreadCount()'))
    const failureBranch = batch.slice(batch.indexOf('} catch (error)'))
    expect(failureBranch).not.toContain('items.value =')
    expect(failureBranch).not.toContain('selectedIds.value =')
  })

  it('uses server-controlled target allowlist; null/unavailable/unknown target never routes or reveals payload', () => {
    const id = '00000000-0000-4000-8000-000000000001'
    expect(mapNotificationTarget({ type: 'risk_alert', id }, false)).toEqual({ kind: 'risk_alert', id })
    expect(mapNotificationTarget({ type: 'medication_checkin', id }, false)).toEqual({ kind: 'medication_checkin', id })
    expect(mapNotificationTarget({ type: 'analysis_task', id }, false)).toEqual({ kind: 'analysis_task', id })
    expect(mapNotificationTarget({ type: 'advice', id }, false)).toEqual({ kind: 'advice', id })
    expect(mapNotificationTarget({ type: 'https://attacker.invalid', id }, false)).toEqual({ kind: 'unavailable' })
    expect(mapNotificationTarget({ type: 'advice', id: 'bad-id' }, false)).toEqual({ kind: 'unavailable' })
    expect(mapNotificationTarget(null, false)).toEqual({ kind: 'unavailable' })
    expect(mapNotificationTarget({ type: 'risk_alert', id }, true)).toEqual({ kind: 'unavailable' })
    expect(workspace).toContain('关联页面尚未开放')
    expect(workspace).not.toContain('notification.body')
    expect(workspace).not.toContain('notification.message')
    expect(isUuid(id)).toBe(true)
    expect(isUuid('https://attacker.invalid')).toBe(false)
  })

  it('keeps preferences ordinary-only, states risk exemption, and exposes real counts without turning failures into zero', () => {
    expect(workspace).toContain('风险通知不受此开关或静默时段影响')
    expect(workspace).toContain('关闭后不接收普通提醒派发')
    expect(today).toContain('notificationApi.unreadCount()')
    expect(today).toContain('未按失败推断为 0')
    expect(today).toContain('today-notification-count')
    expect(me).toContain('notificationApi.unreadCount()')
    expect(generated).toContain("components['schemas']['PatientNotification']")
    expect(workspace).not.toContain('patient_id')
  })
})
