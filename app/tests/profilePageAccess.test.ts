import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { AppError } from '../src/api/errors'
import { enterProtectedProfilePage } from '../src/navigation/profilePageAccess'
import { AppRouter } from '../src/navigation/router'
import type { AppRouter as AppRouterType } from '../src/navigation/router'
import { StartupCoordinator } from '../src/navigation/startup'
import type { StartupState } from '../src/navigation/startup'
import { useAuthStore } from '../src/stores/auth'
import type { AuthState } from '../src/stores/auth'

function harness(startState: StartupState, authState: AuthState) {
  const startup = { state: startState, start: vi.fn(async () => startState) } as unknown as StartupCoordinator
  const router = { onAuthenticationRequired: vi.fn(), returnToStore: { save: vi.fn() } } as unknown as AppRouterType
  const auth = { state: authState }
  const profileApi = { getMyProfile: vi.fn(async () => ({ id: 'fixture-profile-id' })) }
  const enter = () => enterProtectedProfilePage(startup, auth, router, () => profileApi.getMyProfile())
  return { startup, router, auth, profileApi, enter }
}

describe('protected profile page cold-entry gate', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('denies an anonymous session before calling ProfileApi', async () => {
    const page = harness('anonymous', 'anonymous')
    await expect(page.enter()).resolves.toBe('login_redirected')
    expect(page.profileApi.getMyProfile).not.toHaveBeenCalled()
    expect(page.router.onAuthenticationRequired).toHaveBeenCalledOnce()
  })

  it('waits during session restoration and only loads after the shared coordinator authorizes', async () => {
    let resolveRestore!: (state: StartupState) => void
    const restore = new Promise<StartupState>((resolve) => { resolveRestore = resolve })
    const startup = { state: 'restoring', start: vi.fn(() => restore) } as unknown as StartupCoordinator
    const router = { onAuthenticationRequired: vi.fn(), returnToStore: { save: vi.fn() } } as unknown as AppRouterType
    const auth = { state: 'restoring' as AuthState }
    const profileApi = { getMyProfile: vi.fn(async () => ({ id: 'fixture-profile-id' })) }
    const entering = enterProtectedProfilePage(startup, auth, router, () => profileApi.getMyProfile())

    await Promise.resolve()
    expect(profileApi.getMyProfile).not.toHaveBeenCalled()
    expect(router.onAuthenticationRequired).not.toHaveBeenCalled()
    expect(router.returnToStore.save).toHaveBeenCalledWith({ name: 'profile' })

    auth.state = 'authenticated'
    resolveRestore('ready')
    await expect(entering).resolves.toBe('authorized')
    expect(profileApi.getMyProfile).toHaveBeenCalledOnce()
  })

  it('fails closed after restore 401 and never requests profile data', async () => {
    const navigator = { navigateTo: vi.fn(), redirectTo: vi.fn(), reLaunch: vi.fn(), navigateBack: vi.fn() }
    const router = new AppRouter(navigator, () => 'anonymous')
    const startup = { start: vi.fn(async () => 'anonymous' as const) } as unknown as StartupCoordinator
    const profileApi = { getMyProfile: vi.fn(async () => ({ id: 'fixture-profile-id' })) }
    router.returnToStore.save({ name: 'profile' })
    router.onAuthenticationRequired() // SessionService handles the rejected refresh.
    await expect(enterProtectedProfilePage(startup, { state: 'anonymous' }, router, () => profileApi.getMyProfile())).resolves.toBe('login_redirected')
    expect(profileApi.getMyProfile).not.toHaveBeenCalled()
    expect(navigator.reLaunch).toHaveBeenCalledOnce()
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')
    expect(router.returnToStore.take()).toBeNull()
  })

  it('loads exactly once when restoration is complete and the auth store is authorized', async () => {
    const page = harness('ready', 'authenticated')
    await expect(page.enter()).resolves.toBe('authorized')
    expect(page.profileApi.getMyProfile).toHaveBeenCalledOnce()
    expect(page.router.onAuthenticationRequired).not.toHaveBeenCalled()
  })

  it('reuses the profile already fetched by cold startup instead of issuing a duplicate GET', async () => {
    const auth = useAuthStore()
    const navigator = { navigateTo: vi.fn(), redirectTo: vi.fn(), reLaunch: vi.fn(), navigateBack: vi.fn() }
    const router = new AppRouter(navigator, () => auth.state)
    const profile = { id: 'fixture-profile-id', nickname: 'Mina', birth_year: 1990, timezone: 'Asia/Shanghai', profile_version: 1 }
    const profileApi = { getMyProfile: vi.fn(async () => profile) }
    const session = { restore: vi.fn(async () => { auth.acceptAccessToken('fixture-access-value'); return true }) }
    const startup = new StartupCoordinator(session as never, profileApi as never, { clearStoredSession: vi.fn() } as never, auth, router)
    const onAuthorized = vi.fn(async (profileLoadedDuringStartup: boolean) => {
      if (!profileLoadedDuringStartup && !auth.profile) await profileApi.getMyProfile()
    })

    await expect(enterProtectedProfilePage(startup, auth, router, onAuthorized)).resolves.toBe('authorized')
    expect(onAuthorized).toHaveBeenCalledWith(true)
    expect(profileApi.getMyProfile).toHaveBeenCalledOnce()
    expect(auth.profile).toEqual(profile)
  })

  it('preserves the profile 404 security route and request id without a second login redirect', async () => {
    const auth = useAuthStore()
    const navigator = { navigateTo: vi.fn(), redirectTo: vi.fn(), reLaunch: vi.fn(), navigateBack: vi.fn() }
    const router = new AppRouter(navigator, () => auth.state)
    const profileApi = { getMyProfile: vi.fn(async () => { throw new AppError('http', 'not found', { status: 404, requestId: 'fixture-profile-404-id' }) }) }
    const session = { restore: vi.fn(async () => { auth.acceptAccessToken('fixture-access-value'); return true }) }
    const requestClient = { clearStoredSession: vi.fn(async () => { auth.clear() }) }
    const startup = new StartupCoordinator(session as never, profileApi as never, requestClient as never, auth, router)
    const onAuthorized = vi.fn()

    await expect(enterProtectedProfilePage(startup, auth, router, onAuthorized)).resolves.toBe('profile_error_redirected')
    expect(profileApi.getMyProfile).toHaveBeenCalledOnce()
    expect(onAuthorized).not.toHaveBeenCalled()
    expect(auth.profile).toBeNull()
    expect(auth.profileErrorRequestId).toBe('fixture-profile-404-id')
    expect(auth.startupError?.requestId).toBe('fixture-profile-404-id')
    expect(router.returnToStore.take()).toBeNull()
    expect(navigator.reLaunch).toHaveBeenCalledOnce()
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/profile-error')
    expect(navigator.reLaunch).not.toHaveBeenCalledWith('/pages/auth/login')
  })

  it('keeps personal fields behind the page-level authorization gate', async () => {
    const page = await import('node:fs/promises').then(({ readFile }) => readFile(new URL('../src/pages/profile/index.vue', import.meta.url), 'utf8'))
    expect(page).toContain("pageGate !== 'authorized'")
    expect(page).toContain('v-else class="profile-scroll"')
    expect(page).toContain('enterProtectedProfilePage(startup, auth, router')
    expect(page.indexOf('await enterProtectedProfilePage')).toBeLessThan(page.indexOf('await loadProfile()'))
  })

  it('keeps other protected roots and placeholders behind auth checks during cold deep links', async () => {
    const read = (path: string) => import('node:fs/promises').then(({ readFile }) => readFile(new URL(path, import.meta.url), 'utf8'))
    for (const root of ['today', 'records', 'analysis', 'me']) {
      const page = await read(`../src/pages/tabs/${root}/index.vue`)
      expect(page).toContain(':authorized="authorized"')
      expect(page).toContain('onShow(() => { if (!authorized.value) router?.requireAuthentication(')
    }
    const placeholder = await read('../src/pages/placeholder/index.vue')
    expect(placeholder).toContain('v-else-if="pageMeta"')
    expect(placeholder).toContain('if (!canRenderRoute(name, auth.state))')
    expect(placeholder).toContain('if (!name)')
  })
})
