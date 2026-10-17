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
    setLogoutWarning(_warning: unknown) {},
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

  it('retains the exact secure-store error code for the post-logout safety notice', async () => {
    const tokenStore = {
      set: async () => undefined, get: async () => 'fixture-refresh-value',
      remove: vi.fn(async () => { throw new SecureTokenStoreError('KEY_INVALIDATED') }), has: async () => true,
    } satisfies SecureTokenStore
    const auth = makeAuth() as ReturnType<typeof makeAuth> & { warning?: unknown }
    auth.setLogoutWarning = (warning) => { auth.warning = warning }
    const request = vi.fn(async () => undefined)
    const service = new SessionService({ request } as unknown as RequestClient, tokenStore, auth as unknown as ReturnType<typeof useAuthStore>, vi.fn())
    await expect(service.logout()).rejects.toMatchObject({ code: 'KEY_INVALIDATED' })
    expect(auth.accessToken).toBeNull()
    expect(auth.warning).toEqual({ kind: 'secure_storage_cleanup_failed', code: 'KEY_INVALIDATED' })
  })

  it('coalesces concurrent logout requests and sends only one server revocation', async () => {
    const store = new MemorySecureTokenStore()
    await store.set('fixture-concurrent-refresh')
    let finishRequest!: () => void
    const request = vi.fn(() => new Promise<void>((resolve) => { finishRequest = resolve }))
    const auth = makeAuth()
    auth.acceptAccessToken('fixture-access')
    const service = new SessionService({ request } as unknown as RequestClient, store, auth as unknown as ReturnType<typeof useAuthStore>, vi.fn())
    const first = service.logout()
    const second = service.logout()
    await vi.waitFor(() => expect(request).toHaveBeenCalledOnce())
    expect(request).toHaveBeenCalledOnce()
    finishRequest()
    await expect(Promise.all([first, second])).resolves.toEqual([undefined, undefined])
  })
})
