import type { HistoryCategory } from './openapiTypes'

export const HISTORY_CATEGORIES: readonly HistoryCategory[] = [
  'diet', 'stool', 'symptom', 'mood', 'medication_checkin', 'activity', 'advice',
]

export type HistoryTargetRoute =
  | { name: 'recordDiet' | 'recordBowel' | 'recordSymptoms' | 'recordMood' | 'recordActivity'; id: string }
  | { name: 'medications' | 'advice' }
  | { name: 'unavailable' }

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

/** Only fixed contract targets can become routes; never interpret a server value as a path. */
export function mapHistoryTarget(target: unknown): HistoryTargetRoute {
  if (typeof target !== 'object' || target === null) return { name: 'unavailable' }
  const value = target as { type?: unknown; id?: unknown }
  if (typeof value.id !== 'string' || !UUID_PATTERN.test(value.id) || typeof value.type !== 'string') return { name: 'unavailable' }
  const routeByType: Record<string, HistoryTargetRoute['name']> = {
    diet_record: 'recordDiet',
    stool_record: 'recordBowel',
    symptom_record: 'recordSymptoms',
    mood_record: 'recordMood',
    activity_record: 'recordActivity',
    medication_checkin: 'medications',
    advice: 'advice',
  }
  const name = routeByType[value.type]
  if (!name) return { name: 'unavailable' }
  if (name === 'medications' || name === 'advice') return { name }
  return { name, id: value.id }
}

export interface HistoryBounds { since?: string; until?: string; error?: string }

/** Date filters are inclusive calendar days in device timezone; API bounds are UTC [since, until). */
export function historyBounds(sinceDay: string, untilDay: string, timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'): HistoryBounds {
  const sinceDate = sinceDay ? zonedStartOfDay(sinceDay, timeZone) : null
  const untilDate = untilDay ? zonedStartAfterDay(untilDay, timeZone) : null
  if ((sinceDay && !sinceDate) || (untilDay && !untilDate)) return { error: '请选择有效日期。' }
  if (sinceDate && untilDate && untilDate <= sinceDate) return { error: '结束日期需不早于开始日期。' }
  return {
    ...(sinceDate ? { since: sinceDate.toISOString() } : {}),
    ...(untilDate ? { until: untilDate.toISOString() } : {}),
  }
}

function parseDay(value: string): [number, number, number] | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const year = Number(match[1]); const month = Number(match[2]); const day = Number(match[3])
  const validation = new Date(Date.UTC(year, month - 1, day))
  if (validation.getUTCFullYear() !== year || validation.getUTCMonth() !== month - 1 || validation.getUTCDate() !== day) return null
  return [year, month, day]
}

function zonedStartOfDay(value: string, timeZone: string): Date | null {
  const parts = parseDay(value)
  if (!parts) return null
  return zonedMidnight(...parts, timeZone)
}

function zonedStartAfterDay(value: string, timeZone: string): Date | null {
  const parts = parseDay(value)
  if (!parts) return null
  const next = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + 1))
  return zonedMidnight(next.getUTCFullYear(), next.getUTCMonth() + 1, next.getUTCDate(), timeZone)
}

function zonedMidnight(year: number, month: number, day: number, timeZone: string): Date | null {
  try {
    const format = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
    const target = Date.UTC(year, month - 1, day)
    let candidate = target
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const values = Object.fromEntries(format.formatToParts(new Date(candidate)).map((part) => [part.type, part.value]))
      const localAsUtc = Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day), Number(values.hour), Number(values.minute), Number(values.second))
      const next = target - (localAsUtc - candidate)
      if (next === candidate) break
      candidate = next
    }
    const result = new Date(candidate)
    const values = Object.fromEntries(format.formatToParts(result).map((part) => [part.type, part.value]))
    if (Number(values.year) !== year || Number(values.month) !== month || Number(values.day) !== day || Number(values.hour) !== 0 || Number(values.minute) !== 0) return null
    return result
  } catch {
    return null
  }
}

export class HistoryFirstShowGate {
  private shown = false
  shouldRefresh(): boolean {
    if (!this.shown) { this.shown = true; return false }
    return true
  }
}

export function isHistoryResponseCurrent(requestGeneration: number, currentGeneration: number, visible: boolean, authorized: boolean): boolean {
  return visible && authorized && requestGeneration === currentGeneration
}

export interface HistoryListState<T> {
  items: T[]
  cursor: string | null
  moreError: string
  requestId: string
}

export function appendHistoryPage<T extends { id: string }>(state: HistoryListState<T>, page: { items: T[]; next_cursor: string | null }): HistoryListState<T> {
  const seen = new Set(state.items.map((item) => item.id))
  return { items: [...state.items, ...page.items.filter((item) => !seen.has(item.id))], cursor: page.next_cursor, moreError: '', requestId: '' }
}

export function failHistoryAppend<T>(state: HistoryListState<T>, message: string, requestId = ''): HistoryListState<T> {
  return { ...state, moreError: message, requestId }
}
