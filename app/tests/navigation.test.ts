import { describe, expect, it, vi } from 'vitest'
import { AppRouter } from '../src/navigation/router'
import { APP_ROUTES, canRenderRoute, decideRouteAccess, parseReturnTo, PLACEHOLDER_META, placeholderRouteFromScreen, routeNameFromUrl } from '../src/navigation/routes'
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
      for (const route of ['records', 'analysis', 'me'] as const) expect(canRenderRoute(route, state)).toBe(false)
    }
    expect(canRenderRoute('today', 'authenticated')).toBe(true)
    expect(canRenderRoute('profile', 'authenticated')).toBe(true)
    expect(canRenderRoute('records', 'authenticated')).toBe(true)
    expect(canRenderRoute('analysis', 'authenticated')).toBe(true)
    expect(canRenderRoute('me', 'authenticated')).toBe(true)
  })

  it('blocks an unauthenticated deep link before navigation and stores only the allow-listed route name', () => {
    const navigator = makeNavigator()
    let state: AuthState = 'anonymous'
    const router = new AppRouter(navigator, () => state)
    expect(router.guardUrl('/pages/tabs/today/index?note=private')).toBe(false)
    expect(navigator.navigateTo).not.toHaveBeenCalled()
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')
    expect(router.returnToStore.take()).toEqual({ name: 'today' })

    state = 'authenticated'
    expect(router.guardUrl('/pages/tabs/today/index')).toBe(true)
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

  it('switches named tabs by replacing the root rather than pushing another page onto a shared stack', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'authenticated')
    expect(router.switchTab('records')).toBe(true)
    expect(navigator.reLaunch).toHaveBeenCalledWith(APP_ROUTES.records.path)
    expect(navigator.navigateTo).not.toHaveBeenCalled()
    expect(routeNameFromUrl('/pages/tabs/analysis/index')).toBe('analysis')
    expect(routeNameFromUrl('/pages/records/mood/index?id=00000000-0000-4000-8000-000000000001')).toBe('recordMood')
  })

  it('keeps remaining placeholder deep links protected and preserves only their named safe route in returnTo', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'anonymous')
    expect(router.guardUrl('/pages/placeholder/index?screen=recordActivity')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'recordActivity' })
    expect(router.guardUrl('/pages/placeholder/index?screen=unknown')).toBe(false)
    expect(router.returnToStore.take()).toBeNull()
    expect(placeholderRouteFromScreen('recordDiet')).toBeNull()
    expect(placeholderRouteFromScreen('assistant')).toBeNull()
    expect(PLACEHOLDER_META.analysisAdvice.ownerTab).toBe('analysis')
    expect(PLACEHOLDER_META.advice.ownerTab).toBe('me')
    expect(PLACEHOLDER_META.analysisTrends.ownerTab).toBe('analysis')
    expect(PLACEHOLDER_META.trends.ownerTab).toBe('me')
  })

  it('uses dedicated protected record workspaces and recognizes ID-bearing deep links', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'anonymous')
    expect(APP_ROUTES.recordDiet.path).toBe('/pages/records/diet/index')
    expect(APP_ROUTES.recordBowel.path).toBe('/pages/records/bowel/index')
    expect(APP_ROUTES.recordSymptoms.path).toBe('/pages/records/symptoms/index')
    expect(APP_ROUTES.recordMood.path).toBe('/pages/records/mood/index')
    expect(routeNameFromUrl('/pages/records/symptoms/index?id=00000000-0000-4000-8000-000000000001')).toBe('recordSymptoms')
    expect(routeNameFromUrl('/pages/records/mood/index?id=00000000-0000-4000-8000-000000000003')).toBe('recordMood')
    expect(router.guardUrl('/pages/records/diet/index?id=00000000-0000-4000-8000-000000000002')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'recordDiet' })
    expect(router.guardUrl('/pages/records/mood/index?id=00000000-0000-4000-8000-000000000003')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'recordMood' })
    expect(navigator.reLaunch).toHaveBeenCalledWith(APP_ROUTES.login.path)
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
