import { describe, expect, it, vi } from 'vitest'
import { mapProblemDetails } from '../src/api/errors'
import { RefreshCoordinator } from '../src/api/refreshCoordinator'
import { MemorySecureTokenStore, NativeSecureTokenStoreUnavailable } from '../src/api/secureTokenStore'

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
    const store = new NativeSecureTokenStoreUnavailable()
    await expect(store.get()).rejects.toThrow('已拒绝启动会话恢复')
    await expect(store.set('sensitive-refresh-token')).rejects.toThrow('已拒绝启动会话恢复')
    await expect(store.remove()).rejects.toThrow('已拒绝启动会话恢复')
    await expect(store.has()).rejects.toThrow('已拒绝启动会话恢复')
  })
})
