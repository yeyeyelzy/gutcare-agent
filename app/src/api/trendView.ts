import type { TrendBucket, TrendResponse } from './openapiTypes'

export interface TrendRange {
  from: string
  to: string
  error: string | null
}

export function buildTrendRange(fromDay: string, untilDay: string, timezone: string): TrendRange {
  if (!isCalendarDate(fromDay) || !isCalendarDate(untilDay)) {
    return { from: '', to: '', error: '请选择有效的开始和结束日期。' }
  }
  if (fromDay >= untilDay) return { from: '', to: '', error: '结束日期必须晚于开始日期；结束边界按半开区间处理。' }
  try {
    return { from: zonedMidnight(fromDay, timezone), to: zonedMidnight(untilDay, timezone), error: null }
  } catch {
    return { from: '', to: '', error: '账户时区不可用，无法生成趋势范围。' }
  }
}

export function dateInTimezone(date: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date)
  const part = (type: string) => parts.find((item) => item.type === type)?.value
  const year = part('year'); const month = part('month'); const day = part('day')
  if (!year || !month || !day) throw new RangeError('Invalid timezone date')
  return `${year}-${month}-${day}`
}

export function shiftCalendarDate(value: string, days: number): string {
  if (!isCalendarDate(value)) throw new RangeError('Invalid calendar date')
  const [year, month, day] = value.split('-').map(Number)
  const shifted = new Date(Date.UTC(year!, month! - 1, day! + days))
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}-${String(shifted.getUTCDate()).padStart(2, '0')}`
}

export function isTrendResponseCurrent(
  requestGeneration: number,
  generation: number,
  visible: boolean,
  authorized: boolean,
): boolean {
  return requestGeneration === generation && visible && authorized
}

export function trendBucketLabel(bucket: TrendBucket): string {
  return bucket === 'week' ? '按周' : '按日'
}

export function moodMissingConsentLabel(value: 'health_data_processing' | 'mood_data_processing'): string {
  return value === 'health_data_processing' ? '健康数据处理' : '心情数据处理'
}

export function trendBucketDate(value: string): string {
  // Runtime labels are patient-local SQL bucket strings without an offset; preserve their wall-clock date.
  return value.slice(0, 10)
}

function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  const check = new Date(Date.UTC(year!, month! - 1, day!))
  return check.getUTCFullYear() === year && check.getUTCMonth() + 1 === month && check.getUTCDate() === day
}

function zonedMidnight(value: string, timezone: string): string {
  const [year, month, day] = value.split('-').map(Number)
  const desiredWallClock = Date.UTC(year!, month! - 1, day!)
  let candidate = desiredWallClock
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  })
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const parts = formatter.formatToParts(new Date(candidate))
    const values = Object.fromEntries(parts.map((part) => [part.type, Number(part.value)]))
    const year = values.year; const month = values.month; const day = values.day
    const hour = values.hour; const minute = values.minute; const second = values.second
    if (![year, month, day, hour, minute, second].every(Number.isFinite)) throw new RangeError('Invalid timezone parts')
    const actualWallClock = Date.UTC(year!, month! - 1, day!, hour!, minute!, second!)
    const delta = desiredWallClock - actualWallClock
    if (delta === 0) return new Date(candidate).toISOString()
    candidate += delta
  }
  throw new RangeError('Could not resolve timezone midnight')
}
