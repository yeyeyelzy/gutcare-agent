import { describe, expect, it, vi } from 'vitest'
import { AppRouter } from '../src/navigation/router'
import { canRenderRoute, decideRouteAccess, parseReturnTo } from '../src/navigation/routes'
import type { AuthState } from '../src/stores/auth'
import { createPinia, setActivePinia } from 'pinia'
import { useRegistrationDraftStore } from '../src/stores/registrationDraft'

function makeNavigator() {
  return { navigateTo: vi.fn(), redirectTo: vi.fn(), reLaunch: vi.fn(), navigateBack: vi.fn() }
}

describe('named route registry and protected navigation', () => {
  it('does not render protected routes while anonymous or while profile is unresolved', () => {
    for (const state of ['anonymous', 'restoring', 'session_ready', 'loading_profile'] as const) {
      expect(canRenderRoute('today', state)).toBe(false)
      expect(decideRouteAccess('today', state).action).toBe('redirect_to_login')
      expect(canRenderRoute('profile', state)).toBe(false)
    }
    expect(canRenderRoute('today', 'authenticated')).toBe(true)
    expect(canRenderRoute('profile', 'authenticated')).toBe(true)
  })

  it('blocks an unauthenticated deep link before navigation and stores only the allow-listed route name', () => {
    const navigator = makeNavigator()
    let state: AuthState = 'anonymous'
    const router = new AppRouter(navigator, () => state)
    expect(router.guardUrl('/pages/home/index?note=private')).toBe(false)
    expect(navigator.navigateTo).not.toHaveBeenCalled()
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')
    expect(router.returnToStore.take()).toEqual({ name: 'today' })

    state = 'authenticated'
    expect(router.guardUrl('/pages/home/index')).toBe(true)
  })

  it('allows only the protected profile route as a safe profile return target and drops it after auth invalidation', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'anonymous')
    expect(router.guardUrl('/pages/profile/index?nickname=private')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'profile' })
    router.returnToStore.save({ name: 'profile' })
    router.onAuthenticationRequired()
    expect(router.returnToStore.take()).toBeNull()
    expect(navigator.reLaunch).toHaveBeenLastCalledWith('/pages/auth/login')
  })

  it('rejects non-registered and public destinations from returnTo and strips extra properties', () => {
    expect(parseReturnTo({ name: 'login' })).toBeNull()
    expect(parseReturnTo({ name: 'profileError' })).toBeNull()
    expect(parseReturnTo({ name: 'toString' })).toBeNull()
    expect(parseReturnTo({ name: 'today', query: { email: 'private@example.test' } })).toEqual({ name: 'today' })
  })

  it('registers email verification as a public named route without query-carried token state', () => {
    expect(canRenderRoute('emailVerification', 'anonymous')).toBe(true)
    expect(parseReturnTo({ name: 'emailVerification', token: 'fixture-token' })).toBeNull()
  })

  it('registers forgot/reset password screens as public routes without allowing them as return targets', () => {
    expect(canRenderRoute('forgotPassword', 'anonymous')).toBe(true)
    expect(canRenderRoute('resetPassword', 'anonymous')).toBe(true)
    expect(parseReturnTo({ name: 'forgotPassword', email: 'private@example.test' })).toBeNull()
    expect(parseReturnTo({ name: 'resetPassword', token: 'fixture-reset-token' })).toBeNull()
  })

  it('rejects auth secrets placed in a route query and does not retain that route', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'anonymous')
    expect(router.guardUrl('/pages/auth/reset-password?token=fixture-reset-token')).toBe(false)
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')
    expect(router.guardUrl('/pages/auth/email-verification?access_token=fixture-access-token')).toBe(false)
    expect(navigator.reLaunch).toHaveBeenCalledTimes(2)
  })

  it('clears the complete registration draft before rejecting secrets on registration routes', () => {
    setActivePinia(createPinia())
    const draft = useRegistrationDraftStore()
    draft.saveAccountStep({ email: 'person@example.test', password: 'fixture-password-123', confirmPassword: 'fixture-password-123', privacyPolicyAccepted: true, privacyPolicyVersion: 'fixture-policy' })
    draft.enterProfileStep()
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'anonymous', undefined, () => draft.cancelWorkflow())

    expect(router.guardUrl('/pages/auth/register-profile?token=fixture-token')).toBe(false)
    expect(draft.password).toBe('')
    expect(draft.email).toBe('')
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')

    draft.saveAccountStep({ email: 'person@example.test', password: 'fixture-password-456', confirmPassword: 'fixture-password-456', privacyPolicyAccepted: true, privacyPolicyVersion: 'fixture-policy' })
    expect(router.guardUrl('/pages/auth/register?password=fixture-password-456')).toBe(false)
    expect(draft.password).toBe('')
    expect(draft.confirmPassword).toBe('')
    draft.saveAccountStep({ email: 'person@example.test', password: 'fixture-password-789', confirmPassword: 'fixture-password-789', privacyPolicyAccepted: true, privacyPolicyVersion: 'fixture-policy' })
    expect(router.guardUrl('/some/unknown?refresh_token=fixture-refresh')).toBe(false)
    expect(draft.password).toBe('')
  })
})
