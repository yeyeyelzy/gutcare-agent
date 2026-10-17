import { describe, expect, it } from 'vitest'
import { buildTrendRange, dateInTimezone, isTrendResponseCurrent, moodMissingConsentLabel, shiftCalendarDate, trendBucketDate } from '../src/api/trendView'
import type { TrendResponse } from '../src/api/openapiTypes'

function emptyTrend(mood: TrendResponse['mood'] = { availability: 'available', buckets: [] }): TrendResponse {
  return {
    timezone: 'Asia/Shanghai', from: '2026-10-01T00:00:00+08:00', to: '2026-10-08T00:00:00+08:00', bucket: 'day',
    activity: { has_data: false, items: [] }, stool: { has_data: false, items: [] }, symptom: { has_data: false, items: [] },
    diet_confirmed_categories: { has_data: false, items: [] }, medication_checkins: { has_data: false, items: [] }, mood,
  }
}

describe('trend view safety and date helpers', () => {
  it('creates account-timezone UTC half-open ranges across spring and fall DST boundaries', () => {
    expect(buildTrendRange('2026-03-08', '2026-03-08', 'America/New_York').error).toBeTruthy()
    const spring = buildTrendRange('2026-03-08', '2026-03-08', 'America/New_York')
    expect(spring.error).toContain('结束日期')
    const fullSpringDay = buildTrendRange('2026-03-08', '2026-03-09', 'America/New_York')
    expect(fullSpringDay).toEqual({ from: '2026-03-08T05:00:00.000Z', to: '2026-03-09T04:00:00.000Z', error: null })
    const fallBack = buildTrendRange('2026-11-01', '2026-11-02', 'America/New_York')
    expect(fallBack).toEqual({ from: '2026-11-01T04:00:00.000Z', to: '2026-11-02T05:00:00.000Z', error: null })
  })

  it('rejects malformed or impossible calendar dates and handles calendar shifts without DST math', () => {
    expect(buildTrendRange('2026-02-30', '2026-03-01', 'UTC').error).toBeTruthy()
    expect(shiftCalendarDate('2026-03-01', -1)).toBe('2026-02-28')
    expect(dateInTimezone(new Date('2026-03-08T07:00:00.000Z'), 'America/New_York')).toBe('2026-03-08')
  })

  it('distinguishes consent-required mood from authorized empty mood without inventing data', () => {
    const denied = emptyTrend({ availability: 'consent_required', reason_code: 'CONSENT_REQUIRED', missing_consents: ['mood_data_processing'] })
    expect(denied.mood).toEqual({ availability: 'consent_required', reason_code: 'CONSENT_REQUIRED', missing_consents: ['mood_data_processing'] })
    expect(denied.mood.availability === 'consent_required' && 'buckets' in denied.mood).toBe(false)
    expect(moodMissingConsentLabel('health_data_processing')).toBe('健康数据处理')
    const authorizedEmpty = emptyTrend()
    expect(authorizedEmpty.mood).toEqual({ availability: 'available', buckets: [] })
    expect(authorizedEmpty.mood.availability).toBe('available')
  })

  it('reports server-provided items as available and preserves patient-local bucket labels', () => {
    const trend = emptyTrend()
    trend.activity = { has_data: true, items: [{ bucket: '2026-03-08T00:00:00', count: 2, duration_minutes: 35 }] }
    expect(trend.activity.has_data).toBe(true)
    expect(trendBucketDate('2026-03-08T00:00:00')).toBe('2026-03-08')
  })

  it('invalidates late responses after hide, route change, or auth loss', () => {
    expect(isTrendResponseCurrent(3, 3, true, true)).toBe(true)
    expect(isTrendResponseCurrent(3, 4, true, true)).toBe(false)
    expect(isTrendResponseCurrent(3, 3, false, true)).toBe(false)
    expect(isTrendResponseCurrent(3, 3, true, false)).toBe(false)
  })
})
