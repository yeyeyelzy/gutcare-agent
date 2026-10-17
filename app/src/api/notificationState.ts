import type { PatientNotification } from './openapiTypes'

export class NotificationFirstShowGate {
  private first = true
  shouldRefresh(): boolean {
    if (this.first) { this.first = false; return false }
    return true
  }
}

export function applyNotificationRead(items: PatientNotification[], updated: PatientNotification[]): PatientNotification[] {
  const byId = new Map(updated.map((item) => [item.id, item]))
  return items.map((item) => byId.get(item.id) ?? item)
}

export function unreadCountAfterUpdates(count: number, before: PatientNotification[], updated: PatientNotification[]): number {
  const beforeUnread = new Set(before.filter((item) => item.read_at === null).map((item) => item.id))
  const nowRead = updated.filter((item) => item.read_at !== null && beforeUnread.has(item.id)).length
  return Math.max(0, count - nowRead)
}
