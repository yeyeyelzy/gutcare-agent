import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { AppError } from '../src/api/errors'
import { StartupCoordinator } from '../src/navigation/startup'
import { AppRouter } from '../src/navigation/router'
import { SessionService } from '../src/api/session'
import { MemorySecureTokenStore } from '../src/api/secureTokenStore'
import type { RequestClient } from '../src/api/requestClient'
import { useAuthStore } from '../src/stores/auth'
import type { PatientProfile } from '../src/api/openapiTypes'
import type { AuthState } from '../src/stores/auth'

const profile: PatientProfile = {
  id: 'fixture-profile-id',
  nickname: null,
  birth_year: 1990,
  timezone: 'Asia/Shanghai',
  profile_version: 1,
}

function makeStartup(profileRequest: () => Promise<PatientProfile>) {
  const auth = useAuthStore()
  const navigator = { navigateTo: vi.fn(), redirectTo: vi.fn(), reLaunch: vi.fn(), navigateBack: vi.fn() }
  const router = new AppRouter(navigator, () => auth.state as AuthState)
  const clearStoredSession = vi.fn(async () => { auth.clear() })
  const session = {
    restore: vi.fn(async () => { auth.acceptAccessToken('fixture-access-value'); return true }),
  }
  const profileApi = { getMyProfile: vi.fn(profileRequest) }
  const coordinator = new StartupCoordinator(
    session as never,
    profileApi as never,
    { clearStoredSession } as never,
    auth,
    router,
  )
  return { auth, navigator, router, clearStoredSession, profileApi, coordinator }
}

describe('startup session and patient profile state machine', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads /patients/me after restore and routes to today only after 200', async () => {
    const harness = makeStartup(async () => profile)
    await expect(harness.coordinator.start()).resolves.toBe('ready')
    expect(harness.profileApi.getMyProfile).toHaveBeenCalledOnce()
    expect(harness.auth.profile).toEqual(profile)
    expect(harness.auth.state).toBe('authenticated')
    expect(harness.navigator.reLaunch).toHaveBeenCalledWith('/pages/home/index')
    expect(harness.clearStoredSession).not.toHaveBeenCalled()
  })

  it('clears session and returns to login on 401', async () => {
    const harness = makeStartup(async () => { throw new AppError('http', 'unauthorized', { status: 401 }) })
    await expect(harness.coordinator.start()).resolves.toBe('anonymous')
    expect(harness.clearStoredSession).toHaveBeenCalledOnce()
    expect(harness.auth.accessToken).toBeNull()
    expect(harness.auth.profile).toBeNull()
    expect(harness.navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')
  })

  it('clears session and renders a safe integrity error on profile 404 without fabricating a profile', async () => {
    const harness = makeStartup(async () => {
      throw new AppError('http', 'not found', { status: 404, requestId: 'fixture-request-id' })
    })
    await expect(harness.coordinator.start()).resolves.toBe('profile_error')
    expect(harness.clearStoredSession).toHaveBeenCalledOnce()
    expect(harness.auth.profile).toBeNull()
    expect(harness.auth.profileErrorRequestId).toBe('fixture-request-id')
    expect(harness.auth.state).toBe('anonymous')
    expect(harness.navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/profile-error')
    expect(harness.navigator.reLaunch).not.toHaveBeenCalledWith('/pages/home/index')
  })

  it('keeps a valid in-memory session for transient profile loading errors without entering protected routes', async () => {
    const harness = makeStartup(async () => { throw new AppError('network', 'network unavailable') })
    await expect(harness.coordinator.start()).resolves.toBe('unavailable')
    expect(harness.clearStoredSession).not.toHaveBeenCalled()
    expect(harness.auth.accessToken).toBe('fixture-access-value')
    expect(harness.auth.state).toBe('session_ready')
    expect(harness.navigator.reLaunch).not.toHaveBeenCalledWith('/pages/home/index')
  })

  it('clears the in-memory return target and re-launches login on logout to clear the page stack', async () => {
    const auth = useAuthStore()
    auth.acceptAccessToken('fixture-access-value')
    auth.acceptProfile(profile)
    const navigator = { navigateTo: vi.fn(), redirectTo: vi.fn(), reLaunch: vi.fn(), navigateBack: vi.fn() }
    const router = new AppRouter(navigator, () => auth.state)
    router.returnToStore.save({ name: 'today' })
    const request = vi.fn(async () => undefined)
    const tokenStore = new MemorySecureTokenStore()
    await tokenStore.set('fixture-refresh-value')
    const session = new SessionService(
      { request } as unknown as RequestClient,
      tokenStore,
      auth,
      () => router.onAuthenticationRequired(),
      () => router.onLogoutCompleted(),
    )

    await session.logout()
    expect(request).toHaveBeenCalledWith(expect.objectContaining({ method: 'POST', path: '/auth/logout' }))
    expect(await tokenStore.has()).toBe(false)
    expect(auth.accessToken).toBeNull()
    expect(auth.profile).toBeNull()
    expect(router.returnToStore.take()).toBeNull()
    expect(navigator.reLaunch).toHaveBeenCalledOnce()
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')
    expect(navigator.navigateTo).not.toHaveBeenCalled()
  })
})
