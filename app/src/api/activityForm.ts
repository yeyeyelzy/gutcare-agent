import type { ActivityPatch, ActivityRecord, ActivityWrite } from './openapiTypes'

export interface ActivityDraft {
  activityType: ActivityWrite['activity_type']
  description: string
  intensity: ActivityWrite['intensity']
  feeling: ActivityWrite['subjective_feeling']
  duration: string
  date: string
  time: string
}

export const EMPTY_ACTIVITY_DRAFT: ActivityDraft = {
  activityType: 'walking', description: '', intensity: 'moderate', feeling: 'same', duration: '30', date: '', time: '',
}

export type ActivityFormResult =
  | { ok: true; body: ActivityWrite }
  | { ok: false; field: keyof ActivityDraft; message: string }

export function buildActivityWrite(draft: ActivityDraft): ActivityFormResult {
  const duration = Number(draft.duration)
  if (!Number.isInteger(duration) || duration < 1 || duration > 1440) {
    return { ok: false, field: 'duration', message: '时长需为 1–1440 分钟的整数。' }
  }
  const description = draft.description.trim()
  if (draft.activityType === 'other' && (!description || description.length > 160)) {
    return { ok: false, field: 'description', message: '选择“其他”时请填写 1–160 字描述。' }
  }
  if (draft.activityType !== 'other' && description) {
    return { ok: false, field: 'description', message: '仅“其他”活动类型填写描述。' }
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.date) || !/^\d{2}:\d{2}$/.test(draft.time)) {
    return { ok: false, field: 'date', message: '请选择有效的开始日期和时间。' }
  }
  const occurredAt = new Date(`${draft.date}T${draft.time}:00`)
  if (Number.isNaN(occurredAt.getTime())) return { ok: false, field: 'date', message: '请选择有效的开始日期和时间。' }
  return {
    ok: true,
    body: {
      activity_type: draft.activityType,
      description: draft.activityType === 'other' ? description : null,
      intensity: draft.intensity,
      subjective_feeling: draft.feeling,
      duration_minutes: duration,
      occurred_at: occurredAt.toISOString(),
    },
  }
}

export function activityToDraft(record: ActivityRecord): ActivityDraft {
  const date = new Date(record.occurred_at)
  const pad = (value: number) => String(value).padStart(2, '0')
  return {
    activityType: record.activity_type,
    description: record.description ?? '',
    intensity: record.intensity,
    feeling: record.subjective_feeling,
    duration: String(record.duration_minutes),
    date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    time: `${pad(date.getHours())}:${pad(date.getMinutes())}`,
  }
}

export function buildActivityPatch(draft: ActivityDraft, record: ActivityRecord): ActivityPatch | null {
  const result = buildActivityWrite(draft)
  if (!result.ok) return null
  return { ...result.body, record_version: record.record_version }
}
