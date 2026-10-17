import type {
  MedicationCheckin, MedicationCheckinUpdate, MedicationPlan, MedicationPlanCreate,
  MedicationPlanPatch, MedicationPlanTransition, MedicationSchedule, MedicationSchedulePatch,
  MedicationScheduleWrite,
} from './openapiTypes'

export interface MedicationPlanDraft {
  medicationName: string
  dosageText: string
  routeCode: string
  startDate: string
  endDate: string
}

export interface MedicationScheduleDraft {
  localTime: string
  timezone: string
  rrule: string
  validFrom: string
  validTo: string
  enabled: boolean
}

export interface MedicationCheckinDraft {
  status: MedicationCheckin['status']
  takenAt: string
  note: string
}

export type FormResult<T, K extends string> = { ok: true; body: T } | { ok: false; field: K; message: string }

export function buildPlanCreate(draft: MedicationPlanDraft): FormResult<MedicationPlanCreate, keyof MedicationPlanDraft> {
  const name = draft.medicationName.trim()
  if (!name || name.length > 160) return { ok: false, field: 'medicationName', message: '请填写 1–160 字的药品名称。' }
  if (draft.dosageText.trim().length > 160) return { ok: false, field: 'dosageText', message: '剂量说明不能超过 160 字，请按已确认来源原文填写。' }
  if (draft.routeCode.trim().length > 32) return { ok: false, field: 'routeCode', message: '途径代码不能超过 32 字。' }
  if (!validDateRange(draft.startDate, draft.endDate)) return { ok: false, field: 'endDate', message: '结束日期不能早于开始日期。' }
  return { ok: true, body: {
    medication_name: name,
    dosage_text: draft.dosageText.trim() || null,
    route_code: draft.routeCode.trim() || null,
    start_date: draft.startDate || null,
    end_date: draft.endDate || null,
    source_type: 'manual',
    source_document_id: null,
  } }
}

export function buildPlanPatch(draft: MedicationPlanDraft, plan: MedicationPlan): FormResult<MedicationPlanPatch, keyof MedicationPlanDraft> {
  const result = buildPlanCreate(draft)
  if (!result.ok) return result
  return { ok: true, body: {
    medication_name: result.body.medication_name,
    dosage_text: result.body.dosage_text,
    route_code: result.body.route_code,
    start_date: result.body.start_date,
    end_date: result.body.end_date,
    record_version: plan.record_version,
  } }
}

export function buildScheduleWrite(draft: MedicationScheduleDraft, version?: number): FormResult<MedicationScheduleWrite | MedicationSchedulePatch, keyof MedicationScheduleDraft> {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(draft.localTime)) return { ok: false, field: 'localTime', message: '请选择有效的本地时间。' }
  if (!draft.timezone.trim() || draft.timezone.length > 64) return { ok: false, field: 'timezone', message: '请使用账户时区或有效的 IANA 时区。' }
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(draft.validFrom) || (draft.validTo && !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(draft.validTo))) return { ok: false, field: 'validFrom', message: '请选择有效的生效日期。' }
  if (draft.validTo && draft.validTo < draft.validFrom) return { ok: false, field: 'validTo', message: '结束日期不能早于生效日期。' }
  const rrule = draft.rrule.trim()
  if (rrule.length > 256) return { ok: false, field: 'rrule', message: '重复规则不能超过 256 字。' }
  const body: MedicationScheduleWrite = {
    local_time: `${draft.localTime}:00`, timezone: draft.timezone.trim(), rrule: rrule || null,
    valid_from: draft.validFrom, valid_to: draft.validTo || null, enabled: draft.enabled,
  }
  return { ok: true, body: version === undefined ? body : { ...body, record_version: version } }
}

export function buildCheckinUpdate(draft: MedicationCheckinDraft, checkin: MedicationCheckin): FormResult<MedicationCheckinUpdate, keyof MedicationCheckinDraft> {
  let takenAt: string | null = null
  if (draft.status === 'taken') {
    if (!draft.takenAt) return { ok: false, field: 'takenAt', message: '标记为已服用时，请填写实际服用时间。' }
    const parsed = new Date(draft.takenAt)
    if (Number.isNaN(parsed.getTime()) || !/[zZ]|[+-]\d{2}:?\d{2}$/.test(draft.takenAt)) return { ok: false, field: 'takenAt', message: '实际服用时间必须包含时区。' }
    takenAt = parsed.toISOString()
  }
  if (draft.note.trim().length > 500) return { ok: false, field: 'note', message: '备注不能超过 500 字。' }
  return { ok: true, body: { record_version: checkin.record_version, status: draft.status, taken_at: takenAt, note: draft.note.trim() || null } }
}

export function allowedPlanActions(plan: Pick<MedicationPlan, 'confirmation_status' | 'plan_status'>): MedicationPlanTransition['action'][] {
  const actions: MedicationPlanTransition['action'][] = []
  if (plan.confirmation_status !== 'confirmed') actions.push('confirm')
  if (plan.plan_status !== 'active' && plan.confirmation_status !== 'needs_review') actions.push('review')
  if (plan.confirmation_status === 'confirmed' && plan.plan_status !== 'active') actions.push('activate')
  if (plan.plan_status === 'active') actions.push('end', 'discontinue')
  return actions
}

export function planToDraft(plan: MedicationPlan): MedicationPlanDraft {
  return { medicationName: plan.medication_name, dosageText: plan.dosage_text ?? '', routeCode: plan.route_code ?? '', startDate: plan.start_date ?? '', endDate: plan.end_date ?? '' }
}

export function scheduleToDraft(schedule: MedicationSchedule): MedicationScheduleDraft {
  return { localTime: schedule.local_time.slice(0, 5), timezone: schedule.timezone, rrule: schedule.rrule ?? '', validFrom: schedule.valid_from, validTo: schedule.valid_to ?? '', enabled: schedule.enabled }
}

export function checkinToDraft(checkin: MedicationCheckin): MedicationCheckinDraft {
  const takenAt = checkin.taken_at ?? ''
  return { status: checkin.status, takenAt, note: checkin.note ?? '' }
}

function validDateRange(start: string, end: string): boolean {
  if (start && !/^\d{4}-\d{2}-\d{2}$/.test(start)) return false
  if (end && !/^\d{4}-\d{2}-\d{2}$/.test(end)) return false
  return !(start && end && end < start)
}
