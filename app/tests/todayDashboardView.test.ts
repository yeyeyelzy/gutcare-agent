import { describe, expect, it } from 'vitest'
import { buildTodayTrendQuery, formatTodayDateLabel, todayTrendMetrics } from '../src/api/todayDashboardView'
import type { TrendResponse } from '../src/api/openapiTypes'

function response(mood: TrendResponse['mood'] = { availability: 'available', buckets: [] }): TrendResponse {
  return {
    timezone: 'America/Los_Angeles', from: '2026-11-01T07:00:00.000Z', to: '2026-11-02T08:00:00.000Z', bucket: 'day',
    activity: { has_data: false, items: [] }, stool: { has_data: false, items: [] }, symptom: { has_data: false, items: [] },
    diet_confirmed_categories: { has_data: false, items: [] }, medication_checkins: { has_data: false, items: [] }, mood,
  }
}

describe('today dashboard view helpers', () => {
  it('builds the patient-local today range as a UTC half-open interval across DST', () => {
    expect(buildTodayTrendQuery('America/Los_Angeles', new Date('2026-11-01T12:00:00.000Z'))).toEqual({
      query: { from: '2026-11-01T07:00:00.000Z', to: '2026-11-02T08:00:00.000Z', bucket: 'day' }, error: null,
    })
    expect(buildTodayTrendQuery(undefined).query).toBeNull()
    expect(buildTodayTrendQuery('not/a-zone').query).toBeNull()
  })

  it('formats the header date from the same profile timezone at UTC date boundaries', () => {
    const instant = new Date('2026-11-01T02:00:00.000Z')
    expect(formatTodayDateLabel('America/Los_Angeles', instant)).toBe('10月31日')
    expect(formatTodayDateLabel('UTC', instant)).toBe('11月1日')
    expect(formatTodayDateLabel(undefined, instant)).toBeNull()
    expect(formatTodayDateLabel('invalid/zone', instant)).toBeNull()
    expect(buildTodayTrendQuery('America/Los_Angeles', instant).query?.from).toBe('2026-10-31T07:00:00.000Z')
  })

  it('preserves the six server aggregates and separates mood consent from authorized empty', () => {
    const availableEmpty = response()
    availableEmpty.mood = { availability: 'available', buckets: [{ period_start: '2026-11-01', period_end: '2026-11-02', has_data: false, record_count: 0, mood_level_counts: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 } }] }
    const metrics = todayTrendMetrics(availableEmpty)
    expect(metrics.map((metric) => metric.key)).toEqual(['activity', 'stool', 'symptom', 'diet', 'medication', 'mood'])
    expect(metrics.map((metric) => metric.state)).toEqual(['empty', 'empty', 'empty', 'empty', 'empty', 'empty'])
    expect(metrics[5]!.lines).toEqual([])
    const consent = todayTrendMetrics(response({ availability: 'consent_required', reason_code: 'CONSENT_REQUIRED', missing_consents: ['mood_data_processing'] }))
    expect(consent[5]).toMatchObject({ state: 'consent_required', lines: [], missingConsents: ['mood_data_processing'] })
  })

  it('renders exact backend values without client aggregation or reordering', () => {
    const data = response()
    data.activity = { has_data: true, items: [{ bucket: '2026-11-01', count: 2, duration_minutes: 35 }] }
    data.stool = { has_data: true, items: [{ bucket: '2026-11-01', has_data: true, count: 1, bristol_confirmed_count: 0, bristol_unknown_count: 1 }] }
    data.symptom = { has_data: true, items: [{ bucket: '2026-11-01', has_data: true, count: 1, mean_severity: 4, status: 'ongoing' }] }
    data.diet_confirmed_categories = { has_data: true, items: [{ bucket: '2026-11-01', category: 'vegetables', count: 1 }] }
    data.medication_checkins = { has_data: true, items: [{ bucket: '2026-11-01', status: 'pending', count: 1 }, { bucket: '2026-11-01', status: 'taken', count: 2 }] }
    const metrics = todayTrendMetrics(data)
    expect(metrics[0]!.lines).toEqual(['2026-11-01 · 2 次 · 35 分钟'])
    expect(metrics[4]!.lines).toEqual(['2026-11-01 · 待回应 · 1 次', '2026-11-01 · 已记录服用 · 2 次'])
  })
})
