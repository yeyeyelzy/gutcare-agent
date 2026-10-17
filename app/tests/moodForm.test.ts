import { describe, expect, it } from 'vitest'
import { buildMoodPatch, buildMoodWrite, createMoodDraft, moodLabel, MOOD_OPTIONS } from '../src/api/moodForm'

describe('F14 mood form contract', () => {
  it('maps the five frozen labels to exact levels and always writes empty emotion tags', () => {
    expect(MOOD_OPTIONS).toEqual([
      { label: '愉快', level: 5 }, { label: '平静', level: 4 }, { label: '一般', level: 3 },
      { label: '低落', level: 2 }, { label: '烦躁', level: 1 },
    ])
    for (const option of MOOD_OPTIONS) {
      const draft = createMoodDraft('2026-10-18', '09:30')
      draft.level = option.level
      const result = buildMoodWrite(draft)
      expect(result.ok).toBe(true)
      if (result.ok) {
        expect(result.body.mood_level).toBe(option.level)
        expect(result.body.emotion_tags).toEqual([])
        expect(result.body.occurred_at).toMatch(/Z$/)
        expect(moodLabel(option.level)).toBe(option.label)
        expect(Object.keys(result.body)).not.toContain('patient_id')
      }
    }
  })

  it('requires a selected level and bounds note while preserving note only in the explicit write DTO', () => {
    const draft = createMoodDraft('2026-10-18', '09:30')
    expect(buildMoodWrite(draft)).toMatchObject({ ok: false, field: 'level' })
    draft.level = 3
    draft.note = '  留给自己的记录  '
    const result = buildMoodWrite(draft)
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.body.note).toBe('留给自己的记录')
    draft.note = 'x'.repeat(501)
    expect(buildMoodWrite(draft)).toMatchObject({ ok: false, field: 'note' })
  })

  it('sends explicit record_version, empty tags, and null to clear a previously stored note', () => {
    const draft = createMoodDraft('2026-10-18', '09:30')
    draft.level = 4
    const patch = buildMoodPatch(draft, 7)
    expect(patch).toEqual({
      ok: true,
      body: { record_version: 7, occurred_at: expect.stringMatching(/Z$/), mood_level: 4, emotion_tags: [], note: null },
    })
  })
})
