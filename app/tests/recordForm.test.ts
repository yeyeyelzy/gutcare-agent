import { describe, expect, it } from 'vitest'
import { buildRecordWrite, EMPTY_RECORD_DRAFT, recordToDraft } from '../src/api/recordForm'
import type { RecordDraft } from '../src/api/recordForm'

function draft(overrides: Partial<RecordDraft> = {}): RecordDraft {
  return { ...EMPTY_RECORD_DRAFT, date: '2026-10-14', time: '09:30', ...overrides }
}

describe('F03-F05 record form contract', () => {
  it('requires a diet description or at least one item and never adds image/source fields', () => {
    expect(buildRecordWrite('diet-records', draft())).toMatchObject({ ok: false, field: 'description' })
    const result = buildRecordWrite('diet-records', draft({ itemNames: '米饭\n 青菜 ' }))
    expect(result).toMatchObject({ ok: true, body: { payload: { items: [{ name: '米饭' }, { name: '青菜' }] } } })
    if (result.ok) {
      expect(result.body.occurred_at).toMatch(/Z$/)
      expect(JSON.stringify(result.body)).not.toMatch(/patient_id|source_type|image_object_id|confirmed_by_patient/i)
    }
  })

  it('allows an unset Bristol type and constrains non-null values to 1 through 7', () => {
    expect(buildRecordWrite('stool-records', draft())).toMatchObject({ ok: true, body: { payload: { bristol_type: null } } })
    expect(buildRecordWrite('stool-records', draft({ bristol: '8' }))).toMatchObject({ ok: false, field: 'bristol' })
    expect(buildRecordWrite('stool-records', draft({ bristol: '1' }))).toMatchObject({ ok: true, body: { payload: { bristol_type: 1 } } })
  })

  it('requires 1-30 controlled symptoms and requires a bounded description only for other', () => {
    expect(buildRecordWrite('symptom-records', draft())).toMatchObject({ ok: false, field: 'symptomCodes' })
    expect(buildRecordWrite('symptom-records', draft({ symptomCodes: ['other'] }))).toMatchObject({ ok: false, field: 'otherDescription' })
    const result = buildRecordWrite('symptom-records', draft({ symptomCodes: ['bloating', 'other'], otherDescription: '食欲异常', severity: '10' }))
    expect(result).toMatchObject({ ok: true, body: { payload: { items: [{ symptom_code: 'bloating', severity: 10 }, { symptom_code: 'other', other_description: '食欲异常', severity: 10 }] } } })
    if (result.ok) expect(result.body.occurred_at).toMatch(/Z$/)
  })

  it('round-trips visible values from a server-owned record without using ownership/source fields', () => {
    const value = recordToDraft('diet-records', {
      id: 'record', occurred_at: '2026-10-14T01:30:00Z', record_version: 2,
      created_at: '2026-10-14T01:30:00Z', updated_at: '2026-10-14T01:30:00Z',
      payload: { text_description: '早餐', items: [{ name: '米饭' }] },
    })
    expect(value.description).toBe('早餐')
    expect(value.itemNames).toBe('米饭')
  })
})
