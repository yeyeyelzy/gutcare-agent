import { describe, expect, it } from 'vitest'
import { allowedPlanActions, buildCheckinUpdate, buildPlanCreate, buildPlanPatch, buildScheduleWrite, checkinToDraft, planToDraft, scheduleToDraft } from '../src/api/medicationForm'
import type { MedicationCheckin, MedicationPlan, MedicationSchedule } from '../src/api/openapiTypes'

const plan = { id: 'p1', medication_name: '记录名称', dosage_text: null, route_code: null, start_date: null, end_date: null, source_type: 'manual', source_document_id: null, confirmation_status: 'pending', plan_status: 'discontinued', record_version: 9, source_deleted: false } as MedicationPlan
const checkin = { id: 'c1', record_version: 4, status: 'pending', taken_at: null, note: null } as MedicationCheckin

describe('F06 medication payload and state builders', () => {
  it('creates only explicit manual patient-plan fields and patches only mutable fields', () => {
    const draft = { medicationName: '  本人记录  ', dosageText: '', routeCode: '', startDate: '2026-10-01', endDate: '' }
    const create = buildPlanCreate(draft)
    expect(create).toMatchObject({ ok: true, body: { medication_name: '本人记录', dosage_text: null, source_type: 'manual', source_document_id: null } })
    if (create.ok) for (const field of ['patient_id', 'record_version']) expect(Object.keys(create.body)).not.toContain(field)
    const edit = buildPlanPatch(draft, plan)
    expect(edit).toMatchObject({ ok: true, body: { record_version: 9, dosage_text: null } })
    if (edit.ok) for (const field of ['source_type', 'source_document_id', 'patient_id']) expect(Object.keys(edit.body)).not.toContain(field)
  })

  it('validates plan dates and bounds without deriving medical recommendations', () => {
    const blank = { medicationName: '', dosageText: '', routeCode: '', startDate: '', endDate: '' }
    expect(buildPlanCreate({ ...blank, medicationName: '  ', startDate: '2026-10-20', endDate: '2026-10-19' })).toMatchObject({ ok: false })
    expect(buildPlanCreate({ ...blank, medicationName: 'x'.repeat(161) })).toMatchObject({ ok: false, field: 'medicationName' })
    expect(buildPlanCreate({ ...blank, medicationName: '用户填写', dosageText: 'x'.repeat(161) })).toMatchObject({ ok: false, field: 'dosageText' })
  })

  it('sends schedule version only on update and validates local time, timezone and dates', () => {
    const draft = { localTime: '08:30', timezone: 'Asia/Shanghai', rrule: '', validFrom: '2026-10-18', validTo: '', enabled: true }
    const create = buildScheduleWrite(draft)
    expect(create).toMatchObject({ ok: true, body: { local_time: '08:30:00', timezone: 'Asia/Shanghai' } })
    if (create.ok) expect(Object.keys(create.body)).not.toContain('record_version')
    const update = buildScheduleWrite(draft, 6)
    if (update.ok) expect(update.body).toHaveProperty('record_version', 6)
    expect(buildScheduleWrite({ ...draft, localTime: '24:30' })).toMatchObject({ ok: false, field: 'localTime' })
    expect(buildScheduleWrite({ ...draft, timezone: '' })).toMatchObject({ ok: false, field: 'timezone' })
    expect(buildScheduleWrite({ ...draft, validFrom: 'bad' })).toMatchObject({ ok: false, field: 'validFrom' })
    expect(buildScheduleWrite({ ...draft, validTo: '2026-10-17' })).toMatchObject({ ok: false, field: 'validTo' })
    expect(buildScheduleWrite({ ...draft, rrule: 'x'.repeat(257) })).toMatchObject({ ok: false, field: 'rrule' })
  })

  it('requires zoned actual taken time, bounds note, and keeps non-taken distinct from pending', () => {
    expect(buildCheckinUpdate({ status: 'taken', takenAt: '', note: '' }, checkin)).toMatchObject({ ok: false, field: 'takenAt' })
    expect(buildCheckinUpdate({ status: 'taken', takenAt: '2026-10-18T08:30', note: '' }, checkin)).toMatchObject({ ok: false, field: 'takenAt' })
    const taken = buildCheckinUpdate({ status: 'taken', takenAt: '2026-10-18T08:30+08:00', note: '' }, checkin)
    expect(taken).toMatchObject({ ok: true, body: { record_version: 4, status: 'taken', taken_at: '2026-10-18T00:30:00.000Z' } })
    expect(buildCheckinUpdate({ status: 'pending', takenAt: '', note: '' }, checkin)).toMatchObject({ ok: true, body: { status: 'pending', taken_at: null } })
    expect(buildCheckinUpdate({ status: 'not_taken', takenAt: '', note: '' }, checkin)).toMatchObject({ ok: true, body: { status: 'not_taken', taken_at: null } })
    expect(buildCheckinUpdate({ status: 'skipped', takenAt: '', note: 'x'.repeat(501) }, checkin)).toMatchObject({ ok: false, field: 'note' })
  })

  it('exposes only legal status actions from current confirmation and lifecycle state', () => {
    expect(allowedPlanActions(plan)).toEqual(['confirm', 'review'])
    expect(allowedPlanActions({ confirmation_status: 'needs_review', plan_status: 'discontinued' })).toEqual(['confirm'])
    expect(allowedPlanActions({ confirmation_status: 'confirmed', plan_status: 'discontinued' })).toEqual(['review', 'activate'])
    expect(allowedPlanActions({ confirmation_status: 'confirmed', plan_status: 'active' })).toEqual(['end', 'discontinue'])
  })

  it('maps server records into editable drafts without losing schedule or timestamp timezone', () => {
    const planDraft = planToDraft({ ...plan, dosage_text: '按原文' })
    expect(planDraft.dosageText).toBe('按原文')
    const schedule = { id: 's1', local_time: '08:30:00', timezone: 'Asia/Shanghai', rrule: 'FREQ=DAILY', valid_from: '2026-10-18', valid_to: null, enabled: true, record_version: 3 } as MedicationSchedule
    expect(scheduleToDraft(schedule)).toMatchObject({ localTime: '08:30', timezone: 'Asia/Shanghai', rrule: 'FREQ=DAILY' })
    expect(checkinToDraft({ ...checkin, status: 'taken', taken_at: '2026-10-18T08:30:00+08:00' })).toMatchObject({ takenAt: '2026-10-18T08:30:00+08:00' })
  })
})
