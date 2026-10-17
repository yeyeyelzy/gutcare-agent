import { describe, expect, it } from 'vitest'
import { buildActivityWrite, EMPTY_ACTIVITY_DRAFT } from '../src/api/activityForm'

function validDraft() {
  return { ...EMPTY_ACTIVITY_DRAFT, date: '2026-10-18', time: '09:30' }
}

describe('F07 activity form contract', () => {
  it('maps activity data to strict DTO with timezone and never adds patient/device/AI source fields', () => {
    const draft = validDraft()
    const result = buildActivityWrite(draft)
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.body).toEqual({
        activity_type: 'walking', description: null, intensity: 'moderate', subjective_feeling: 'same',
        duration_minutes: 30, occurred_at: expect.stringMatching(/Z$/),
      })
      for (const forbidden of ['patient_id', 'source_type', 'device_source', 'ai_source']) expect(Object.keys(result.body)).not.toContain(forbidden)
    }
  })

  it('enforces duration and `other` description bounds without modifying frozen API semantics', () => {
    const draft = validDraft()
    for (const duration of ['0', '1441', '1.5', '']) {
      draft.duration = duration
      expect(buildActivityWrite(draft)).toMatchObject({ ok: false, field: 'duration' })
    }
    draft.duration = '1440'
    draft.activityType = 'other'
    expect(buildActivityWrite(draft)).toMatchObject({ ok: false, field: 'description' })
    draft.description = '  徒步  '
    const result = buildActivityWrite(draft)
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.body).toMatchObject({ activity_type: 'other', description: '徒步', duration_minutes: 1440 })
    draft.description = 'x'.repeat(161)
    expect(buildActivityWrite(draft)).toMatchObject({ ok: false, field: 'description' })
  })
})
