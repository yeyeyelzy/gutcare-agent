import { describe, expect, it, vi } from 'vitest'
import { discardActivityConflictDraft, keepActivityConflictDraft, loadActivityConflictLatest } from '../src/api/activityConflict'
import type { ActivityDraft } from '../src/api/activityForm'
import type { ActivityRecord } from '../src/api/openapiTypes'

const draft: ActivityDraft = {
  activityType: 'other', description: '我的本地草稿', intensity: 'high', feeling: 'better',
  duration: '47', date: '2026-10-18', time: '09:24',
}

function record(version: number): ActivityRecord {
  return {
    id: 'activity-1', activity_type: 'walking', description: null, intensity: 'low',
    subjective_feeling: 'worse', duration_minutes: 12, occurred_at: '2026-10-17T08:00:00Z',
    record_version: version, created_at: '2026-10-17T08:00:00Z', updated_at: '2026-10-17T08:00:00Z',
  }
}

describe('F07 explicit activity conflict resolution', () => {
  it('fetches latest separately without any mutation and retains the complete draft', async () => {
    const latest = record(2)
    const api = { get: vi.fn().mockResolvedValue(latest), update: vi.fn() }
    const fetched = await loadActivityConflictLatest(api, latest.id)
    const resolved = keepActivityConflictDraft({ ...draft }, fetched)

    expect(api.get).toHaveBeenCalledOnce()
    expect(api.update).not.toHaveBeenCalled()
    expect(resolved.record.record_version).toBe(2)
    expect(resolved.draft).toEqual(draft)
    expect(resolved.draft).not.toBe(draft)
  })

  it('discards the draft only through explicit load-latest resolution', () => {
    const latest = record(2)
    const resolved = discardActivityConflictDraft(latest)
    expect(resolved.record).toBe(latest)
    expect(resolved.draft).not.toEqual(draft)
    expect(resolved.draft.activityType).toBe(latest.activity_type)
    expect(resolved.draft.duration).toBe(String(latest.duration_minutes))
    expect(resolved.draft.feeling).toBe(latest.subjective_feeling)
  })

  it('keeps the draft through repeated conflict refreshes and never auto-retries PATCH', async () => {
    const api = { get: vi.fn().mockResolvedValueOnce(record(2)).mockResolvedValueOnce(record(3)), update: vi.fn() }
    const first = keepActivityConflictDraft({ ...draft }, await loadActivityConflictLatest(api, 'activity-1'))
    const second = keepActivityConflictDraft(first.draft, await loadActivityConflictLatest(api, 'activity-1'))

    expect(first.draft).toEqual(draft)
    expect(second.draft).toEqual(draft)
    expect(second.record.record_version).toBe(3)
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(api.update).not.toHaveBeenCalled()
  })
})
