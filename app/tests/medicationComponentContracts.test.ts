import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const page = readFileSync(new URL('../src/pages/medications/index.vue', import.meta.url), 'utf8')
const today = readFileSync(new URL('../src/pages/tabs/today/index.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/medicationApi.ts', import.meta.url), 'utf8')

describe('F06 protected medication workspace UI contract', () => {
  it('gates before API access and renders actual plan, schedule, today and history endpoints', () => {
    expect(page).toContain('canRenderRoute(routeName, auth.state)')
    expect(page).toContain('router?.requireAuthentication(routeName)')
    for (const call of ['api.listPlans()', 'api.getPlan(id)', 'api.createPlan(', 'api.updatePlan(', 'api.transitionPlan(', 'api.deletePlan(', 'api.listSchedules(', 'api.createSchedule(', 'api.updateSchedule(', 'api.listTodayCheckins()', 'api.listCheckins(', 'api.updateCheckin(']) expect(page).toContain(call)
    for (const id of ['medication-loading', 'medication-error', 'medication-plans-empty', 'medication-today-empty', 'medication-history-empty', 'medication-plan-delete-confirm']) expect(page).toContain(id)
    expect(page).toContain('计划日程')
  })

  it('keeps medical boundaries, distinguishes pending, and exposes state transitions only from the helper', () => {
    for (const text of ['待确认”只表示尚未记录回应', '本人记录未服用', '不会推荐药品、推断剂量或修改处方']) expect(page).toContain(text)
    expect(page).toContain('allowedPlanActions(currentPlan)')
    expect(api).toContain('idempotencyKey: key')
    expect(page).not.toMatch(/patient_id|剂量建议|建议服用|自动停药|诊断|因果/)
    expect(today).toContain('medicationApiKey')
    expect(today).toContain('listTodayCheckins()')
    expect(today).toContain('用药计划')
    expect(today).toContain('medication-status')
    expect(today).not.toContain('patient_id')
  })

  it('keeps plan, schedule and checkin drafts on 409; offers explicit latest/discard/rebase paths only', () => {
    for (const id of ['medication-plan-conflict', 'medication-schedule-conflict', 'medication-checkin-conflict', 'medication-plan-conflict-discard', 'medication-plan-conflict-keep', 'medication-plan-conflict-retry', 'medication-schedule-conflict-discard', 'medication-schedule-conflict-keep', 'medication-schedule-conflict-retry', 'medication-checkin-conflict-discard', 'medication-checkin-conflict-keep', 'medication-checkin-conflict-retry']) expect(page).toContain(id)
    for (const fn of ['discardPlanConflict', 'keepPlanDraft', 'retryPlanConflictLatest', 'discardScheduleConflict', 'keepScheduleDraft', 'retryScheduleConflictLatest', 'discardCheckinDraft', 'keepCheckinDraft', 'retryCheckinConflictLatest']) expect(page).toContain(fn)
    expect(page).toContain('不会自动覆盖或重新提交')
    expect(page).toContain('busy || Boolean(checkinConflict) || checkinConflictPending')
    for (const guard of ['planConflictPending.value || planConflict.value', 'scheduleConflictPending.value || scheduleConflict.value', 'checkinConflictPending.value || checkinConflict.value']) expect(page).toContain(guard)
    expect(page).toContain('buildScheduleWrite({ ...scheduleToDraft(schedule), enabled: false }, schedule.record_version)')
    expect(page).not.toContain('api.deleteSchedule(schedule.id')
  })

  it('renders one non-overlapping conflict panel and one of each resolution test id per resource', () => {
    const resources = ['plan', 'schedule', 'checkin'] as const
    const occurrences = (value: string) => page.split(value).length - 1
    for (const resource of resources) {
      const panelId = `medication-${resource}-conflict`
      const panelLine = page.split('\n').find((line) => line.includes(`data-testid="${panelId}"`))
      expect(occurrences(`data-testid="${panelId}"`)).toBe(1)
      expect(panelLine).toBeDefined()
      for (const action of ['discard', 'keep', 'retry']) {
        const actionId = `medication-${resource}-conflict-${action}`
        expect(occurrences(`test-id="${actionId}"`)).toBe(1)
        expect(panelLine).toContain(actionId)
      }
      for (const other of resources.filter((candidate) => candidate !== resource)) {
        expect(panelLine).not.toContain(`medication-${other}-conflict-`)
      }
    }
  })

  it('does not fabricate success on offline and error paths or claim plan names in schedule-derived today cards', () => {
    expect(page).toContain('网络暂不可用')
    expect(page).toContain('没有记录任何成功状态')
    expect(page).toContain('requestId')
    expect(page).toContain('class="auth-pending"')
    expect(page).toContain('max-width: 430px')
    expect(page).toContain('env(safe-area-inset-bottom')
    expect(page).not.toContain('假数据')
    expect(today).toContain('用药计划')
  })
})
