import type { RequestClient } from './requestClient'
import type { NotificationCategory, NotificationPage, NotificationPreference, NotificationPreferencesWrite, NotificationUnreadCount, PatientNotification } from './openapiTypes'

export interface NotificationListQuery {
  limit?: number
  cursor?: string
  category?: NotificationCategory
  unread_only?: boolean
}

export class NotificationApi {
  constructor(private readonly client: RequestClient) {}

  list(query: NotificationListQuery = {}): Promise<NotificationPage> {
    const params = new URLSearchParams()
    if (query.limit !== undefined) params.set('limit', String(query.limit))
    if (query.cursor) params.set('cursor', query.cursor)
    if (query.category) params.set('category', query.category)
    if (query.unread_only !== undefined) params.set('unread_only', String(query.unread_only))
    return this.client.request({ method: 'GET', path: `/notifications${params.size ? `?${params.toString()}` : ''}` })
  }

  unreadCount(): Promise<NotificationUnreadCount> {
    return this.client.request({ method: 'GET', path: '/notifications/unread-count' })
  }

  getPreferences(): Promise<NotificationPreference> {
    return this.client.request({ method: 'GET', path: '/notifications/preferences' })
  }

  updatePreferences(value: NotificationPreferencesWrite): Promise<NotificationPreference> {
    return this.client.request({ method: 'PUT', path: '/notifications/preferences', data: value })
  }

  get(id: string): Promise<PatientNotification> {
    return this.client.request({ method: 'GET', path: `/notifications/${encodeURIComponent(id)}` })
  }

  markRead(id: string): Promise<PatientNotification> {
    return this.client.request({ method: 'POST', path: `/notifications/${encodeURIComponent(id)}/read` })
  }

  markBatchRead(ids: string[]): Promise<{ items: PatientNotification[] }> {
    return this.client.request({ method: 'POST', path: '/notifications/read-batch', data: { notification_ids: ids } })
  }
}
