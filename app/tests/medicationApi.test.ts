import { describe, expect, it, vi } from 'vitest'
import { MedicationApi } from '../src/api/medicationApi'
import type { RequestClient } from '../src/api/requestClient'

describe('MedicationApi F06 contract routes', () => {
  it('uses the generated plan and schedule endpoints with idempotency only on contract writes', async () => {
    const request = vi.fn().mockResolvedValue([])
    const api = new MedicationApi({ request } as unknown as RequestClient)
    await api.listPlans()
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medication-plans' })
    await api.getPlan('plan/id')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medication-plans/plan%2Fid' })
    const plan = { medication_name: '原记录', dosage_text: null, route_code: null, start_date: null, end_date: null, source_type: 'manual' as const, source_document_id: null }
    await api.createPlan(plan, 'plan-key')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/medication-plans', data: plan, idempotencyKey: 'plan-key' })
    const transition = { action: 'confirm' as const, record_version: 2 }
    await api.transitionPlan('p1', transition, 'transition-key')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/medication-plans/p1/transitions', data: transition, idempotencyKey: 'transition-key' })
    const schedule = { local_time: '08:00:00', timezone: 'Asia/Shanghai', rrule: null, valid_from: '2026-10-18', valid_to: null, enabled: true }
    await api.createSchedule('p1', schedule, 'schedule-key')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/medication-plans/p1/schedules', data: schedule, idempotencyKey: 'schedule-key' })
  })

  it('places record versions in patch bodies/delete queries and does not invent checkin idempotency', async () => {
    const request = vi.fn().mockResolvedValue([])
    const api = new MedicationApi({ request } as unknown as RequestClient)
    const patch = { record_version: 7, local_time: '08:00:00', timezone: 'Asia/Shanghai', rrule: null, valid_from: '2026-10-18', valid_to: null, enabled: false }
    await api.updateSchedule('schedule/1', patch)
    expect(request).toHaveBeenLastCalledWith({ method: 'PATCH', path: '/medication-schedules/schedule%2F1', data: patch })
    await api.deletePlan('p1', 3)
    expect(request).toHaveBeenLastCalledWith({ method: 'DELETE', path: '/medication-plans/p1?record_version=3' })
    await api.deleteSchedule('s1', 4)
    expect(request).toHaveBeenLastCalledWith({ method: 'DELETE', path: '/medication-schedules/s1?record_version=4' })
    await api.listTodayCheckins()
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medication-checkins/today' })
    await api.listCheckins('2026-10-01', '2026-10-31')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medication-checkins?start=2026-10-01&end=2026-10-31' })
    const checkin = { record_version: 5, status: 'pending' as const, taken_at: null, note: null }
    await api.updateCheckin('c1', checkin)
    expect(request).toHaveBeenLastCalledWith({ method: 'PATCH', path: '/medication-checkins/c1', data: checkin })
    for (const [input] of request.mock.calls) expect(JSON.stringify(input)).not.toContain('patient_id')
    expect(request.mock.calls.at(-1)?.[0]).not.toHaveProperty('idempotencyKey')
  })
})
