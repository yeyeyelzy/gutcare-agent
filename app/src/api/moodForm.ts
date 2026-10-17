import type { MoodDetail, MoodPatch, MoodWrite } from './openapiTypes'

export const MOOD_OPTIONS = [
  { label: '愉快', level: 5 },
  { label: '平静', level: 4 },
  { label: '一般', level: 3 },
  { label: '低落', level: 2 },
  { label: '烦躁', level: 1 },
] as const

export interface MoodDraft {
  date: string
  time: string
  level: number | null
  note: string
}

export type MoodDraftResult =
  | { ok: true; body: MoodWrite }
  | { ok: false; field: keyof MoodDraft; message: string }

export type MoodPatchResult =
  | { ok: true; body: MoodPatch }
  | { ok: false; field: keyof MoodDraft; message: string }

export function createMoodDraft(date: string, time: string): MoodDraft {
  return { date, time, level: null, note: '' }
}

export function buildMoodWrite(draft: MoodDraft): MoodDraftResult {
  if (!draft.date || !draft.time) return { ok: false, field: 'date', message: '请选择有效的发生日期和时间。' }
  const occurredAt = new Date(`${draft.date}T${draft.time}:00`)
  if (Number.isNaN(occurredAt.getTime())) return { ok: false, field: 'date', message: '请选择有效的发生日期和时间。' }
  if (!MOOD_OPTIONS.some((option) => option.level === draft.level)) {
    return { ok: false, field: 'level', message: '请选择当时的心情。' }
  }
  const note = draft.note.trim()
  if (note.length > 500) return { ok: false, field: 'note', message: '备注最多 500 字。' }
  return {
    ok: true,
    body: {
      occurred_at: occurredAt.toISOString(),
      mood_level: draft.level as number,
      emotion_tags: [],
      ...(note ? { note } : {}),
    },
  }
}

export function buildMoodPatch(draft: MoodDraft, recordVersion: number): MoodPatchResult {
  const built = buildMoodWrite(draft)
  if (!built.ok) return built
  return {
    ok: true,
    body: {
      record_version: recordVersion,
      occurred_at: built.body.occurred_at,
      mood_level: built.body.mood_level,
      emotion_tags: [],
      note: built.body.note ?? null,
    },
  }
}

export function moodToDraft(detail: MoodDetail): MoodDraft {
  const date = new Date(detail.occurred_at)
  return {
    date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`,
    time: `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`,
    level: detail.mood_level,
    note: detail.note ?? '',
  }
}

export function moodLabel(level: number): string {
  return MOOD_OPTIONS.find((option) => option.level === level)?.label ?? '心情记录'
}

export function moodSummaryLabel(record: Pick<MoodDetail, 'mood_level'>): string {
  return moodLabel(record.mood_level)
}
