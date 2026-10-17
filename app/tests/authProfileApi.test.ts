import { describe, expect, it, vi } from 'vitest'
import { AuthApi } from '../src/api/authApi'
import { ProfileApi } from '../src/api/profileApi'
import type { RequestClient, RequestOptions } from '../src/api/requestClient'
import type { SessionService } from '../src/api/session'
import type { RegisterRequest } from '../src/api/openapiTypes'

const validRegister: RegisterRequest = {
  email: 'patient@example.test',
  password: 'fixture-password-only',
  birth_year: 1990,
  privacy_policy_version: 'fixture-privacy-v1',
  health_data_processing_consent: true,
  health_data_processing_policy_version: 'fixture-health-v1',
}

describe('auth and profile contract adapters', () => {
  it('uses the exact registration operation body and refuses extra fields at runtime', async () => {
    const request = vi.fn(async (_options: RequestOptions) => ({ operation_id: 'fixture-operation-id', status: 'accepted' as const }))
    const client = { request } as unknown as RequestClient
    const session = { login: vi.fn(), logout: vi.fn() } as unknown as SessionService
    const authApi = new AuthApi(client, session)

    await authApi.register(validRegister)
    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      method: 'POST',
      path: '/auth/register',
      data: validRegister,
      retryOnUnauthorized: false,
    }))
    expect(Object.keys(request.mock.calls[0]?.[0] as object)).toEqual(['method', 'path', 'data', 'retryOnUnauthorized'])

    const invalid = { ...validRegister, confirm_password: 'fixture-confirm-only' } as RegisterRequest
    expect(() => authApi.register(invalid)).toThrow('does not match the frozen API contract')
    expect(request).toHaveBeenCalledOnce()
  })

  it('delegates login and logout to SessionService without implementing refresh again', async () => {
    const request = vi.fn()
    const login = vi.fn(async () => undefined)
    const logout = vi.fn(async () => undefined)
    const authApi = new AuthApi(
      { request } as unknown as RequestClient,
      { login, logout } as unknown as SessionService,
    )
    await authApi.login({ email: 'patient@example.test', password: 'fixture-password-only' })
    await authApi.logout()
    expect(login).toHaveBeenCalledOnce()
    expect(logout).toHaveBeenCalledOnce()
    expect(request).not.toHaveBeenCalled()
  })

  it('posts only the entered one-time token to the frozen verification endpoint', async () => {
    const request = vi.fn(async () => undefined)
    const authApi = new AuthApi(
      { request } as unknown as RequestClient,
      { login: vi.fn(), logout: vi.fn() } as unknown as SessionService,
    )
    await authApi.verifyEmail({ token: 'fixture-one-time-token' })
    expect(request).toHaveBeenCalledWith({
      method: 'POST', path: '/auth/email/verify', data: { token: 'fixture-one-time-token' }, retryOnUnauthorized: false,
    })
  })

  it('maps profile get and patch to the frozen paths', async () => {
    const request = vi.fn(async (_options: RequestOptions) => ({ id: 'fixture-profile-id' }))
    const profileApi = new ProfileApi({ request } as unknown as RequestClient)
    await profileApi.getMyProfile()
    await profileApi.updateMyProfile({ profile_version: 1, nickname: 'Test user' })
    expect(request.mock.calls.map(([options]) => options)).toEqual([
      { method: 'GET', path: '/patients/me' },
      { method: 'PATCH', path: '/patients/me', data: { profile_version: 1, nickname: 'Test user' } },
    ])
  })
})
