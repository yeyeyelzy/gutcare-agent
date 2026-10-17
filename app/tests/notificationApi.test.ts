import { describe, expect, it, vi } from 'vitest'
import { NotificationApi } from '../src/api/notificationApi'
import type { RequestClient } from '../src/api/requestClient'

describe('NotificationApi', () => {
  it('uses generated F12 endpoints and preserves category/unread/cursor query semantics', async () => {
    const request = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const api = new NotificationApi({ request } as unknown as RequestClient)
    await api.list({ limit: 20, cursor: 'opaque next', category: 'risk', unread_only: true })
    expect(request).toHaveBeenCalledWith({ method: 'GET', path: '/notifications?limit=20&cursor=opaque+next&category=risk&unread_only=true' })
    await api.unreadCount()
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/notifications/unread-count' })
  })

  it('uses contract DTOs for details, single/batch read and ordinary preferences only', async () => {
    const request = vi.fn().mockResolvedValue({ items: [] })
    const api = new NotificationApi({ request } as unknown as RequestClient)
    await api.get('id/one')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/notifications/id%2Fone' })
    await api.markRead('id-1')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/notifications/id-1/read' })
    await api.markBatchRead(['a', 'b'])
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/notifications/read-batch', data: { notification_ids: ['a', 'b'] } })
    const preferences = { ordinary_in_app_enabled: false, quiet_start: '22:00', quiet_end: '07:00', timezone: 'Asia/Shanghai' }
    await api.getPreferences()
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/notifications/preferences' })
    await api.updatePreferences(preferences)
    expect(request).toHaveBeenLastCalledWith({ method: 'PUT', path: '/notifications/preferences', data: preferences })
  })
})
