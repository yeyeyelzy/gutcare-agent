import { describe, expect, it, vi } from 'vitest'
import type { useAuthStore } from '../src/stores/auth'
import { SessionService } from '../src/api/session'
import { MemorySecureTokenStore, SecureTokenStoreError } from '../src/api/secureTokenStore'
import type { SecureTokenStore } from '../src/api/secureTokenStore'
import type { RequestClient } from '../src/api/requestClient'

function makeAuth() {
  return {
    state: 'anonymous' as string,
    accessToken: null as string | null,
    beginRestore() { this.state = 'restoring' },
    acceptAccessToken(token: string) { this.accessToken = token; this.state = 'authenticated' },
    clear() { this.accessToken = null; this.state = 'anonymous' },
  }
}

describe('SessionService secure-store failure handling', () => {
  it('keeps credentials on device-lock errors during restore', async () => {
    const store = new MemorySecureTokenStore()
    await store.set('fixture-preserved-refresh')
    const client = { restoreSession: async () => { throw new SecureTokenStoreError('DEVICE_LOCKED') } } as unknown as RequestClient
    const auth = makeAuth()
    const onAuthenticationRequired = vi.fn()
    const service = new SessionService(client, store, auth as unknown as ReturnType<typeof useAuthStore>, onAuthenticationRequired)

    await expect(service.restore()).rejects.toMatchObject({ code: 'DEVICE_LOCKED' })
    expect(await store.get()).toBe('fixture-preserved-refresh')
    expect(auth.accessToken).toBeNull()
    expect(onAuthenticationRequired).not.toHaveBeenCalled()
  })

  it('clears local state and requests login after a nonrecoverable restore failure', async () => {
    const store = new MemorySecureTokenStore()
    await store.set('fixture-expired-refresh')
    const client = { restoreSession: async () => { throw new SecureTokenStoreError('KEY_INVALIDATED') } } as unknown as RequestClient
    const auth = makeAuth()
    const onAuthenticationRequired = vi.fn()
    const service = new SessionService(client, store, auth as unknown as ReturnType<typeof useAuthStore>, onAuthenticationRequired)

    await expect(service.restore()).resolves.toBe(false)
    expect(await store.has()).toBe(false)
    expect(auth.accessToken).toBeNull()
    expect(onAuthenticationRequired).toHaveBeenCalledOnce()
  })

  it('deletes local credentials on logout even when the request fails', async () => {
    const store = new MemorySecureTokenStore()
    await store.set('fixture-logout-refresh')
    const client = {
      request: async () => { throw new Error('fixture network failure') },
    } as unknown as RequestClient
    const auth = makeAuth()
    auth.acceptAccessToken('fixture-access')
    const onAuthenticationRequired = vi.fn()
    const service = new SessionService(client, store, auth as unknown as ReturnType<typeof useAuthStore>, onAuthenticationRequired)

    await expect(service.logout()).rejects.toThrow('fixture network failure')
    expect(await store.has()).toBe(false)
    expect(auth.accessToken).toBeNull()
    expect(onAuthenticationRequired).toHaveBeenCalledOnce()
  })

  it('attempts server logout and clears memory but reports local deletion failure', async () => {
    const tokenStore = {
      set: async () => undefined,
      get: async () => 'fixture-retained-refresh',
      remove: vi.fn(async () => { throw new SecureTokenStoreError('SECURE_STORAGE_FAILED') }),
      has: async () => true,
    } satisfies SecureTokenStore
    const request = vi.fn(async () => undefined)
    const client = { request } as unknown as RequestClient
    const auth = makeAuth()
    auth.acceptAccessToken('fixture-access')
    const onAuthenticationRequired = vi.fn()
    const service = new SessionService(client, tokenStore, auth as unknown as ReturnType<typeof useAuthStore>, onAuthenticationRequired)

    await expect(service.logout()).rejects.toMatchObject({ code: 'SECURE_STORAGE_FAILED' })
    expect(tokenStore.remove).toHaveBeenCalledOnce()
    expect(request).toHaveBeenCalledOnce()
    expect(await tokenStore.has()).toBe(true)
    expect(auth.accessToken).toBeNull()
    expect(onAuthenticationRequired).toHaveBeenCalledOnce()
  })
})
