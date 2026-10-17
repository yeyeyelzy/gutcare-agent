import { describe, expect, it, vi } from 'vitest'
import { AppRouter } from '../src/navigation/router'
import { canRenderRoute, decideRouteAccess, parseReturnTo } from '../src/navigation/routes'
import type { AuthState } from '../src/stores/auth'

function makeNavigator() {
  return { navigateTo: vi.fn(), redirectTo: vi.fn(), reLaunch: vi.fn(), navigateBack: vi.fn() }
}

describe('named route registry and protected navigation', () => {
  it('does not render protected routes while anonymous or while profile is unresolved', () => {
    for (const state of ['anonymous', 'restoring', 'session_ready', 'loading_profile'] as const) {
      expect(canRenderRoute('today', state)).toBe(false)
      expect(decideRouteAccess('today', state).action).toBe('redirect_to_login')
    }
    expect(canRenderRoute('today', 'authenticated')).toBe(true)
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
})
