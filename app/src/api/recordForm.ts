import type {
  DietRecordPayload,
  HealthRecord,
  RecordType,
  RecordWrite,
  StoolRecordPayload,
  SymptomRecordPayload,
} from './openapiTypes'

export type SymptomCode = NonNullable<SymptomRecordPayload['items'][number]['symptom_code']>
export interface RecordDraft {
  date: string
  time: string
  mealType: 'breakfast' | 'lunch' | 'dinner' | 'snack' | 'other' | ''
  description: string
  itemNames: string
  bristol: string
  bowelNotes: string
  symptomCodes: SymptomCode[]
  otherDescription: string
  severity: string
  bodyLocation: string
  duration: string
  symptomStatus: 'ongoing' | 'relieved'
  notes: string
}

export type DraftResult = { ok: true; body: RecordWrite } | { ok: false; field: keyof RecordDraft; message: string }

export const EMPTY_RECORD_DRAFT: RecordDraft = {
  date: '', time: '', mealType: '', description: '', itemNames: '', bristol: '', bowelNotes: '',
  symptomCodes: [], otherDescription: '', severity: '', bodyLocation: '', duration: '',
  symptomStatus: 'ongoing', notes: '',
}

export const SYMPTOM_OPTIONS: ReadonlyArray<{ code: SymptomCode; label: string }> = [
  { code: 'abdominal_pain', label: '腹痛' }, { code: 'bloating', label: '腹胀' },
  { code: 'diarrhea', label: '腹泻' }, { code: 'constipation', label: '便秘' },
  { code: 'nausea', label: '恶心' }, { code: 'vomiting', label: '呕吐' },
  { code: 'acid_reflux', label: '反酸' }, { code: 'appetite_change', label: '食欲变化' },
  { code: 'blood_in_stool_concern', label: '便血相关主诉' }, { code: 'other', label: '其他' },
]

export function buildRecordWrite(type: RecordType, draft: RecordDraft): DraftResult {
  const date = new Date(`${draft.date}T${draft.time}:00`)
  if (!draft.date || !draft.time || Number.isNaN(date.getTime())) {
    return { ok: false, field: 'date', message: '请选择有效的发生日期和时间。' }
  }
  const occurred_at = date.toISOString()
  if (type === 'diet-records') {
    const items = draft.itemNames.split(/\r?\n/).map((name) => name.trim()).filter(Boolean).map((name) => ({ name }))
    if (items.length > 50) return { ok: false, field: 'itemNames', message: '食物项最多 50 项。' }
    if (!draft.description.trim() && items.length === 0) {
      return { ok: false, field: 'description', message: '请填写饮食描述或至少一项食物。' }
    }
    const payload: DietRecordPayload = {
      ...(draft.mealType ? { meal_type: draft.mealType } : {}),
      ...(draft.description.trim() ? { text_description: draft.description.trim() } : {}),
      ...(items.length ? { items } : {}),
    }
    return { ok: true, body: { occurred_at, payload } }
  }
  if (type === 'stool-records') {
    const bristol = draft.bristol ? Number(draft.bristol) : null
    if (bristol !== null && (!Number.isInteger(bristol) || bristol < 1 || bristol > 7)) {
      return { ok: false, field: 'bristol', message: 'Bristol 类型请选择 1–7，或保持未填写。' }
    }
    const payload: StoolRecordPayload = {
      bristol_type: bristol,
      ...(draft.bowelNotes.trim() ? { notes: draft.bowelNotes.trim() } : {}),
    }
    return { ok: true, body: { occurred_at, payload } }
  }
  const codes = [...new Set(draft.symptomCodes)]
  if (codes.length < 1 || codes.length > 30) {
    return { ok: false, field: 'symptomCodes', message: '请选择至少 1 项症状。' }
  }
  if (codes.includes('other') && !draft.otherDescription.trim()) {
    return { ok: false, field: 'otherDescription', message: '请填写“其他”症状描述。' }
  }
  if (codes.includes('other') && draft.otherDescription.trim().length > 160) {
    return { ok: false, field: 'otherDescription', message: '“其他”描述最多 160 字。' }
  }
  const severity = draft.severity ? Number(draft.severity) : null
  if (severity !== null && (!Number.isInteger(severity) || severity < 0 || severity > 10)) {
    return { ok: false, field: 'severity', message: '严重程度请填写 0–10 的主观评分。' }
  }
  const duration = draft.duration ? Number(draft.duration) : null
  if (duration !== null && (!Number.isInteger(duration) || duration < 0 || duration > 10080)) {
    return { ok: false, field: 'duration', message: '持续时间需为 0–10080 分钟。' }
  }
  const payload: SymptomRecordPayload = {
    items: codes.map((symptom_code) => ({
      symptom_code,
      ...(symptom_code === 'other' ? { other_description: draft.otherDescription.trim() } : {}),
      ...(severity === null ? {} : { severity }),
      ...(draft.bodyLocation.trim() ? { body_location: draft.bodyLocation.trim() } : {}),
    })),
    symptom_status: draft.symptomStatus,
    ...(duration === null ? {} : { duration_minutes: duration }),
    ...(draft.notes.trim() ? { notes: draft.notes.trim() } : {}),
  }
  return { ok: true, body: { occurred_at, payload } }
}

export function recordToDraft(type: RecordType, record: HealthRecord): RecordDraft {
  const date = new Date(record.occurred_at)
  const payload = record.payload as Record<string, unknown>
  const draft: RecordDraft = {
    ...EMPTY_RECORD_DRAFT,
    date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`,
    time: `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`,
  }
  if (type === 'diet-records') {
    draft.mealType = typeof payload.meal_type === 'string' ? payload.meal_type as RecordDraft['mealType'] : ''
    draft.description = typeof payload.text_description === 'string' ? payload.text_description : ''
    draft.itemNames = Array.isArray(payload.items)
      ? payload.items.map((item) => typeof item === 'object' && item && 'name' in item ? String(item.name) : '').filter(Boolean).join('\n')
      : ''
  } else if (type === 'stool-records') {
    draft.bristol = typeof payload.bristol_type === 'number' ? String(payload.bristol_type) : ''
    draft.bowelNotes = typeof payload.notes === 'string' ? payload.notes : ''
  } else {
    draft.symptomCodes = Array.isArray(payload.items)
      ? payload.items.map((item) => typeof item === 'object' && item && 'symptom_code' in item ? item.symptom_code as SymptomCode : null).filter((value): value is SymptomCode => value !== null)
      : []
    const otherItem = Array.isArray(payload.items) ? payload.items.find((item) => typeof item === 'object' && item && 'symptom_code' in item && item.symptom_code === 'other') : undefined
    const firstItem = Array.isArray(payload.items) ? payload.items[0] : undefined
    if (typeof otherItem === 'object' && otherItem && 'other_description' in otherItem) draft.otherDescription = String(otherItem.other_description ?? '')
    if (typeof firstItem === 'object' && firstItem && 'severity' in firstItem && typeof firstItem.severity === 'number') draft.severity = String(firstItem.severity)
    if (typeof firstItem === 'object' && firstItem && 'body_location' in firstItem) draft.bodyLocation = String(firstItem.body_location ?? '')
    draft.symptomStatus = payload.symptom_status === 'relieved' ? 'relieved' : 'ongoing'
    draft.duration = typeof payload.duration_minutes === 'number' ? String(payload.duration_minutes) : ''
    draft.notes = typeof payload.notes === 'string' ? payload.notes : ''
  }
  return draft
}
