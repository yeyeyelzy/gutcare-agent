import type { TrendResponse } from './openapiTypes'
import { buildTrendRange, dateInTimezone, shiftCalendarDate } from './trendView'

export interface TodayTrendQuery {
  from: string
  to: string
  bucket: 'day'
}

export type TodayTrendMetric = {
  key: 'activity' | 'stool' | 'symptom' | 'diet' | 'medication' | 'mood'
  title: string
  state: 'ready' | 'empty' | 'consent_required'
  lines: string[]
  missingConsents?: string[]
}

export function formatTodayDateLabel(timezone: string | undefined, now = new Date()): string | null {
  if (!timezone) return null
  try {
    return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', timeZone: timezone }).format(now)
  } catch {
    return null
  }
}

export function buildTodayTrendQuery(timezone: string | undefined, now = new Date()): {
  query: TodayTrendQuery | null
  error: string | null
} {
  if (!timezone) return { query: null, error: '账户时区尚不可用，暂时无法载入今日趋势。' }
  try {
    const today = dateInTimezone(now, timezone)
    const range = buildTrendRange(today, shiftCalendarDate(today, 1), timezone)
    if (range.error) return { query: null, error: range.error }
    return { query: { from: range.from, to: range.to, bucket: 'day' }, error: null }
  } catch {
    return { query: null, error: '账户时区不可用，暂时无法载入今日趋势。' }
  }
}

export function todayTrendMetrics(response: TrendResponse): TodayTrendMetric[] {
  const activity = response.activity
  const stool = response.stool
  const symptom = response.symptom
  const diet = response.diet_confirmed_categories
  const medication = response.medication_checkins
  const mood = response.mood
  const statusLabels = {
    pending: '待回应',
    taken: '已记录服用',
    not_taken: '本人记录未服用',
    skipped: '已跳过',
  } as const

  return [
    {
      key: 'activity',
      title: '活动',
      state: activity.has_data ? 'ready' : 'empty',
      lines: activity.items.map((item) => `${item.bucket} · ${item.count} 次 · ${item.duration_minutes} 分钟`),
    },
    {
      key: 'stool',
      title: '排便',
      state: stool.has_data ? 'ready' : 'empty',
      lines: stool.items.map((item) => `${item.bucket} · ${item.count} 次 · Bristol 已确认 ${item.bristol_confirmed_count} · 未知 ${item.bristol_unknown_count}`),
    },
    {
      key: 'symptom',
      title: '症状自评',
      state: symptom.has_data ? 'ready' : 'empty',
      lines: symptom.items.map((item) => `${item.bucket} · ${item.status === 'ongoing' ? '持续中' : '已缓解'} · ${item.count} 条 · 平均自评 ${item.mean_severity ?? '未知'}`),
    },
    {
      key: 'diet',
      title: '已确认饮食分类',
      state: diet.has_data ? 'ready' : 'empty',
      lines: diet.items.map((item) => `${item.bucket} · ${item.category} · ${item.count} 项`),
    },
    {
      key: 'medication',
      title: '用药打卡',
      state: medication.has_data ? 'ready' : 'empty',
      lines: medication.items.map((item) => `${item.bucket} · ${statusLabels[item.status]} · ${item.count} 次`),
    },
    mood.availability === 'consent_required'
      ? {
          key: 'mood',
          title: '心情等级',
          state: 'consent_required',
          lines: [],
          missingConsents: mood.missing_consents,
        }
      : {
          key: 'mood',
          title: '心情等级',
          state: mood.buckets.some((item) => item.record_count > 0) ? 'ready' : 'empty',
          lines: mood.buckets.filter((item) => item.record_count > 0).map((item) => `${item.period_start} · ${item.record_count} 条 · 1–5档 ${item.mood_level_counts['1']}/${item.mood_level_counts['2']}/${item.mood_level_counts['3']}/${item.mood_level_counts['4']}/${item.mood_level_counts['5']}`),
        },
  ]
}
