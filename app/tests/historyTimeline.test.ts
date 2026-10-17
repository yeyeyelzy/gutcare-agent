import { describe, expect, it } from 'vitest'
import { appendHistoryPage, failHistoryAppend, HISTORY_CATEGORIES, HistoryFirstShowGate, historyBounds, isHistoryResponseCurrent, mapHistoryTarget } from '../src/api/historyTimeline'

const uuid = '00000000-0000-4000-8000-000000000001'

describe('F11 history timeline helpers', () => {
  it('keeps only the seven contract categories and maps fixed targets without accepting arbitrary routes', () => {
    expect(HISTORY_CATEGORIES).toEqual(['diet', 'stool', 'symptom', 'mood', 'medication_checkin', 'activity', 'advice'])
    expect(mapHistoryTarget({ type: 'diet_record', id: uuid })).toEqual({ name: 'recordDiet', id: uuid })
    expect(mapHistoryTarget({ type: 'medication_checkin', id: uuid })).toEqual({ name: 'medications' })
    expect(mapHistoryTarget({ type: 'advice', id: uuid })).toEqual({ name: 'advice' })
    expect(mapHistoryTarget({ type: 'https://evil.invalid/path', id: uuid })).toEqual({ name: 'unavailable' })
    expect(mapHistoryTarget(null)).toEqual({ name: 'unavailable' })
    expect(mapHistoryTarget({ type: 'diet_record', id: 'not-a-uuid' })).toEqual({ name: 'unavailable' })
  })

  it('converts inclusive local days to timezone-bearing half-open UTC bounds across DST', () => {
    const bounds = historyBounds('2026-03-08', '2026-03-08', 'America/New_York')
    expect(bounds).toEqual({ since: '2026-03-08T05:00:00.000Z', until: '2026-03-09T04:00:00.000Z' })
    expect(Date.parse(bounds.until!) - Date.parse(bounds.since!)).toBe(23 * 60 * 60 * 1000)
    expect(historyBounds('2026-03-09', '2026-03-08', 'America/New_York').error).toBeTruthy()
    expect(historyBounds('2026-02-30', '', 'America/New_York').error).toBeTruthy()
  })

  it('preserves already loaded items and cursor after append failure and de-duplicates returned rows', () => {
    const initial = { items: [{ id: 'a' }], cursor: 'cursor-a', moreError: '', requestId: '' }
    expect(failHistoryAppend(initial, 'offline', 'request-1')).toEqual({ ...initial, moreError: 'offline', requestId: 'request-1' })
    expect(appendHistoryPage(initial, { items: [{ id: 'a' }, { id: 'b' }], next_cursor: null })).toEqual({ items: [{ id: 'a' }, { id: 'b' }], cursor: null, moreError: '', requestId: '' })
  })

  it('does not duplicate the first onShow load but refreshes after returning from a target', () => {
    const gate = new HistoryFirstShowGate()
    expect(gate.shouldRefresh()).toBe(false)
    expect(gate.shouldRefresh()).toBe(true)
  })

  it('invalidates responses after hiding, authentication loss or a later filter request', () => {
    expect(isHistoryResponseCurrent(4, 4, true, true)).toBe(true)
    expect(isHistoryResponseCurrent(4, 5, true, true)).toBe(false)
    expect(isHistoryResponseCurrent(4, 4, false, true)).toBe(false)
    expect(isHistoryResponseCurrent(4, 4, true, false)).toBe(false)
  })
})
