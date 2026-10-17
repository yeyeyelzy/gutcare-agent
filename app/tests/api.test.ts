import { describe, expect, it, vi } from 'vitest'
import { mapProblemDetails } from '../src/api/errors'
import { RefreshCoordinator } from '../src/api/refreshCoordinator'
import { MemorySecureTokenStore, NativeSecureTokenStore, SecureTokenStoreError, UnsupportedSecureTokenStore } from '../src/api/secureTokenStore'

describe('problem details mapping', () => {
  it('preserves stable backend error fields', () => {
    const error = mapProblemDetails(409, { type: 'about:blank', title: 'Conflict', status: 409, detail: 'Version changed', code: 'RECORD_VERSION_CONFLICT', request_id: 'req-1' })
    expect(error.kind).toBe('http')
    expect(error.status).toBe(409)
    expect(error.code).toBe('RECORD_VERSION_CONFLICT')
    expect(error.requestId).toBe('req-1')
    expect(error.message).toBe('Version changed')
  })
})

describe('refresh coordination', () => {
  it('shares one in-flight refresh operation', async () => {
    const coordinator = new RefreshCoordinator<string>()
    let release!: (value: string) => void
    const refresh = vi.fn(() => new Promise<string>((resolve) => { release = resolve }))
    const one = coordinator.run(refresh)
    const two = coordinator.run(refresh)
    expect(refresh).toHaveBeenCalledTimes(1)
    release('rotated')
    await expect(Promise.all([one, two])).resolves.toEqual(['rotated', 'rotated'])
  })
})

describe('secure token store', () => {
  it('keeps the test adapter process-local', async () => {
    const store = new MemorySecureTokenStore()
    await store.set('refresh-test-value')
    expect(await store.has()).toBe(true)
    expect(await store.get()).toBe('refresh-test-value')
    await store.remove()
    expect(await store.get()).toBeNull()
  })

  it('fails closed when the native secure adapter is absent', async () => {
    const store = new UnsupportedSecureTokenStore()
    await expect(store.get()).rejects.toMatchObject({ code: 'UNSUPPORTED_PLATFORM' })
    await expect(store.set('fixture-refresh-value')).rejects.toMatchObject({ code: 'UNSUPPORTED_PLATFORM' })
    await expect(store.remove()).rejects.toMatchObject({ code: 'UNSUPPORTED_PLATFORM' })
    await expect(store.has()).rejects.toMatchObject({ code: 'UNSUPPORTED_PLATFORM' })
  })
})

describe('native secure token adapter', () => {
  it('maps stable native error codes without forwarding native details', async () => {
    const store = new NativeSecureTokenStore({
      get: () => { throw { code: 'DEVICE_LOCKED', message: 'native detail must not escape' } },
      set: () => undefined,
      remove: () => undefined,
      has: () => false,
    })
    await expect(store.get()).rejects.toMatchObject({ code: 'DEVICE_LOCKED', message: '设备锁定期间安全存储不可用。' })
  })

  it('maps unknown native failures to one stable generic error', async () => {
    const store = new NativeSecureTokenStore({
      get: () => { throw { code: 'PLATFORM_PRIVATE_ERROR', message: 'sensitive native detail' } },
      set: () => undefined,
      remove: () => undefined,
      has: () => false,
    })
    await expect(store.get()).rejects.toMatchObject({ code: 'SECURE_STORAGE_FAILED', message: '安全令牌存储操作失败。' })
  })

  it('recognizes a UTS failure code carried by the native error message', async () => {
    const store = new NativeSecureTokenStore({
      get: () => { throw new Error('SECURE_STORE_DEVICE_LOCKED') },
      set: () => undefined,
      remove: () => undefined,
      has: () => false,
    })
    await expect(store.get()).rejects.toMatchObject({ code: 'DEVICE_LOCKED' })
  })

  it('proxies CRUD and represents an absent value as null/false', async () => {
    let value: string | null = null
    const store = new NativeSecureTokenStore({
      get: () => value,
      set: (next) => { value = next },
      remove: () => { value = null },
      has: () => value !== null,
    })
    await expect(store.get()).resolves.toBeNull()
    await expect(store.has()).resolves.toBe(false)
    await store.set('fixture-refresh-value')
    await expect(store.get()).resolves.toBe('fixture-refresh-value')
    await expect(store.has()).resolves.toBe(true)
    await store.remove()
    await expect(store.get()).resolves.toBeNull()
  })

  it('rejects empty tokens before crossing the native bridge', async () => {
    const set = vi.fn()
    const store = new NativeSecureTokenStore({ get: () => null, set, remove: () => undefined, has: () => false })
    await expect(store.set('')).rejects.toMatchObject({ code: 'INVALID_VALUE' })
    expect(set).not.toHaveBeenCalled()
  })

  it('keeps only the stable error code in the public error message', () => {
    expect(new SecureTokenStoreError('CORRUPT_DATA').message).toBe('安全存储数据无效。')
  })
})
