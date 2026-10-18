import { describe, expect, it, vi } from 'vitest'
import { AppError } from '../src/api/errors'
import { RequestClient } from '../src/api/requestClient'
import { MemorySecureTokenStore, SecureTokenStoreError } from '../src/api/secureTokenStore'
import type { HttpResponse, HttpTransport, RequestOptions, SessionTokens } from '../src/api/requestClient'

const tokens: SessionTokens = {
  access_token: 'access-test', refresh_token: 'refresh-test', token_type: 'Bearer', expires_in: 300,
}

function makeClient(send: HttpTransport['send']) {
  const access = { value: null as string | null }
  const store = new MemorySecureTokenStore()
  const onAuthenticationRequired = vi.fn()
  const client = new RequestClient({
    baseUrl: 'https://api.example.invalid/api/v1', appVersion: 'test',
    transport: { send }, tokenStore: store,
    getAccessToken: () => access.value,
    setTokens: (value) => { access.value = value.access_token },
    clearSession: async () => { access.value = null },
    onAuthenticationRequired,
    createRequestId: () => 'request-test',
  })
  return { client, access, store, onAuthenticationRequired }
}

describe('RequestClient', () => {
  it('adds the frozen API headers and unwraps successful DTOs', async () => {
    let captured: (RequestOptions & { headers: Record<string, string> }) | undefined
    let capturedUrl = ''
    const send: HttpTransport['send'] = async <T>(_url: string, options: RequestOptions & { headers: Record<string, string> }): Promise<HttpResponse<T>> => {
      capturedUrl = _url
      captured = options
      return { status: 200, data: { ok: true } as T }
    }
    const { client } = makeClient(send)
    await expect(client.request({ method: 'GET', path: '/patients/me' })).resolves.toEqual({ ok: true })
    expect(capturedUrl).toBe('https://api.example.invalid/api/v1/patients/me')
    expect(captured?.path).toBe('/patients/me')
    expect(captured?.headers).toMatchObject({
      Accept: 'application/json, application/problem+json', 'X-Request-ID': 'request-test', 'X-App-Version': 'test',
    })
  })

  it('uploads raw bytes with bearer auth to the root-mounted same-origin gateway only', async () => {
    let capturedUrl = ''
    let captured: (RequestOptions & { headers: Record<string, string> }) | undefined
    const bytes = new Uint8Array([1, 2, 3]).buffer
    const send: HttpTransport['send'] = async <T>(url: string, options: RequestOptions & { headers: Record<string, string> }): Promise<HttpResponse<T>> => {
      capturedUrl = url
      captured = options
      return { status: 204, data: undefined as T }
    }
    const { client, access } = makeClient(send)
    access.value = 'upload-access'
    await expect(client.uploadThroughGateway('https://api.example.invalid/uploads/abcdefghijklmnopqrstuvwxyz123456', bytes, 'image/png')).resolves.toBeUndefined()
    expect(capturedUrl).toBe('https://api.example.invalid/uploads/abcdefghijklmnopqrstuvwxyz123456')
    expect(captured).toMatchObject({ method: 'PUT', data: bytes, headers: { Authorization: 'Bearer upload-access', 'Content-Type': 'image/png' } })
    await expect(client.uploadThroughGateway('https://other.example.invalid/uploads/abcdefghijklmnopqrstuvwxyz123456', bytes, 'image/png')).rejects.toMatchObject({ kind: 'protocol' })
    expect(capturedUrl).toBe('https://api.example.invalid/uploads/abcdefghijklmnopqrstuvwxyz123456')
  })

  it('surfaces service availability separately and preserves RFC 9457 fields', async () => {
    const send: HttpTransport['send'] = async <T>() => ({
      status: 503, data: { type: 'about:blank', title: 'Unavailable', status: 503, code: 'SERVICE_UNAVAILABLE', request_id: 'req-1' } as T,
    })
    const { client } = makeClient(send)
    await expect(client.request({ method: 'GET', path: '/patients/me' })).rejects.toMatchObject({
      kind: 'unavailable', status: 503, code: 'SERVICE_UNAVAILABLE', requestId: 'req-1',
    })
  })

  it('stores rotated refresh credentials and retries a safe GET once after 401', async () => {
    let calls = 0
    const send: HttpTransport['send'] = async <T>(_url: string, options: RequestOptions & { headers: Record<string, string> }): Promise<HttpResponse<T>> => {
      calls += 1
      if (options.path === '/auth/refresh') return { status: 200, data: tokens as T }
      if (calls === 1) return { status: 401, data: { title: 'Unauthorized', status: 401, code: 'TOKEN_EXPIRED' } as T }
      return { status: 200, data: { profile: true } as T }
    }
    const { client, access, store } = makeClient(send)
    await store.set('saved-refresh')
    await expect(client.request({ method: 'GET', path: '/patients/me' })).resolves.toEqual({ profile: true })
    expect(access.value).toBe(tokens.access_token)
    expect(await store.get()).toBe(tokens.refresh_token)
    expect(calls).toBe(3)
  })

  it('shares one refresh request across simultaneous 401 responses', async () => {
    let getCalls = 0
    let refreshCalls = 0
    let finishRefresh!: (response: HttpResponse<SessionTokens>) => void
    const send: HttpTransport['send'] = async <T>(_url: string, options: RequestOptions & { headers: Record<string, string> }): Promise<HttpResponse<T>> => {
      if (options.path === '/auth/refresh') {
        refreshCalls += 1
        return await new Promise<HttpResponse<SessionTokens>>((resolve) => { finishRefresh = resolve }) as HttpResponse<T>
      }
      getCalls += 1
      if (getCalls <= 2) return { status: 401, data: { title: 'Unauthorized', status: 401, code: 'TOKEN_EXPIRED' } as T }
      return { status: 200, data: { profile: true } as T }
    }
    const { client, store } = makeClient(send)
    await store.set('saved-refresh')
    const first = client.request({ method: 'GET', path: '/patients/me' })
    const second = client.request({ method: 'GET', path: '/patients/me' })
    await vi.waitFor(() => expect(refreshCalls).toBe(1))
    finishRefresh({ status: 200, data: tokens })
    await expect(Promise.all([first, second])).resolves.toEqual([{ profile: true }, { profile: true }])
    expect(refreshCalls).toBe(1)
    expect(getCalls).toBe(4)
  })

  it('does not refresh or replay an unauthenticated login failure', async () => {
    const send: HttpTransport['send'] = async <T>() => ({ status: 401, data: { title: 'Invalid credentials', status: 401 } as T })
    const { client, onAuthenticationRequired } = makeClient(send)
    await expect(client.request({ method: 'POST', path: '/auth/login', retryOnUnauthorized: false })).rejects.toBeInstanceOf(AppError)
    expect(onAuthenticationRequired).not.toHaveBeenCalled()
  })

  it('does not publish access credentials when refresh rotation cannot be persisted', async () => {
    const store = new MemorySecureTokenStore()
    await store.set('fixture-old-refresh')
    const set = vi.spyOn(store, 'set').mockRejectedValue(new SecureTokenStoreError('SECURE_STORAGE_FAILED'))
    let calls = 0
    const send: HttpTransport['send'] = async <T>(_url: string, options: RequestOptions & { headers: Record<string, string> }): Promise<HttpResponse<T>> => {
      calls += 1
      if (options.path === '/auth/refresh') return { status: 200, data: tokens as T }
      return { status: 401, data: { title: 'Unauthorized', status: 401, code: 'TOKEN_EXPIRED' } as T }
    }
    const access = { value: null as string | null }
    const onAuthenticationRequired = vi.fn()
    const failingClient = new RequestClient({
      baseUrl: 'https://api.example.invalid/api/v1', appVersion: 'test', transport: { send }, tokenStore: store,
      getAccessToken: () => access.value,
      setTokens: (value) => { access.value = value.access_token },
      clearSession: async () => { access.value = null },
      onAuthenticationRequired,
      createRequestId: () => 'request-test',
    })
    await expect(failingClient.request({ method: 'GET', path: '/patients/me' })).rejects.toMatchObject({ code: 'SECURE_STORAGE_FAILED' })
    expect(set).toHaveBeenCalledTimes(1)
    expect(access.value).toBeNull()
    expect(await store.has()).toBe(false)
    expect(onAuthenticationRequired).toHaveBeenCalledTimes(1)
    expect(calls).toBe(2)
  })

  it('preserves a stored refresh token when the device is locked during rotation', async () => {
    const store = new MemorySecureTokenStore()
    await store.set('fixture-locked-refresh')
    const lockedStore = {
      get: () => { throw new SecureTokenStoreError('DEVICE_LOCKED') },
      set: (value: string) => store.set(value),
      remove: () => store.remove(),
      has: () => store.has(),
    }
    const send: HttpTransport['send'] = async <T>() => ({ status: 401, data: { title: 'Unauthorized', status: 401, code: 'TOKEN_EXPIRED' } as T })
    const access = { value: 'expired-access' as string | null }
    const onAuthenticationRequired = vi.fn()
    const client = new RequestClient({
      baseUrl: 'https://api.example.invalid/api/v1', appVersion: 'test', transport: { send }, tokenStore: lockedStore,
      getAccessToken: () => access.value,
      setTokens: (value) => { access.value = value.access_token },
      clearSession: async () => { access.value = null },
      onAuthenticationRequired,
    })
    await expect(client.request({ method: 'GET', path: '/patients/me' })).rejects.toMatchObject({ code: 'DEVICE_LOCKED' })
    expect(await store.get()).toBe('fixture-locked-refresh')
    expect(access.value).toBeNull()
    expect(onAuthenticationRequired).not.toHaveBeenCalled()
  })

  it('reports native refresh-token deletion errors after clearing memory and redirects authentication', async () => {
    const tokenStore = {
      get: async () => 'fixture-revoked-refresh',
      set: async () => undefined,
      has: async () => true,
      remove: vi.fn(async () => { throw new SecureTokenStoreError('KEY_INVALIDATED') }),
    }
    const access = { value: 'fixture-expired-access' as string | null }
    const reportFailure = vi.fn()
    const onAuthenticationRequired = vi.fn()
    const send: HttpTransport['send'] = async <T>() => ({ status: 401, data: { title: 'Unauthorized', status: 401, code: 'AUTHENTICATION_REQUIRED' } as T })
    const client = new RequestClient({
      baseUrl: 'https://api.example.invalid/api/v1', appVersion: 'test', transport: { send }, tokenStore,
      getAccessToken: () => access.value,
      setTokens: (value) => { access.value = value.access_token },
      clearSession: async () => { access.value = null },
      onAuthenticationRequired,
      onSecureTokenDeletionFailure: reportFailure,
    })
    await expect(client.request({ method: 'GET', path: '/patients/me' })).rejects.toMatchObject({ status: 401 })
    expect(tokenStore.remove).toHaveBeenCalledOnce()
    expect(access.value).toBeNull()
    expect(reportFailure).toHaveBeenCalledWith(expect.objectContaining({ code: 'KEY_INVALIDATED' }))
    expect(onAuthenticationRequired).toHaveBeenCalledOnce()
  })
})
