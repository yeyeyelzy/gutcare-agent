import { describe, expect, it, vi } from 'vitest'
import { AppRouter } from '../src/navigation/router'
import { APP_ROUTES, canRenderRoute, decideRouteAccess, parseReturnTo, PLACEHOLDER_META, placeholderRouteFromScreen, routeNameFromUrl } from '../src/navigation/routes'
import type { AuthState } from '../src/stores/auth'
import { createPinia, setActivePinia } from 'pinia'
import { useRegistrationDraftStore } from '../src/stores/registrationDraft'
import type { AnalysisResultEvidence } from '../src/api/openapiTypes'

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
    expect(canRenderRoute('history', 'authenticated')).toBe(true)
    expect(canRenderRoute('history', 'anonymous')).toBe(false)
    expect(canRenderRoute('profile', 'authenticated')).toBe(true)
    expect(canRenderRoute('records', 'authenticated')).toBe(true)
    expect(canRenderRoute('analysis', 'authenticated')).toBe(true)
    expect(canRenderRoute('me', 'authenticated')).toBe(true)
    expect(canRenderRoute('riskAlerts', 'authenticated')).toBe(true)
    expect(canRenderRoute('riskAlertDetail', 'anonymous')).toBe(false)
    expect(canRenderRoute('privacyCenter', 'anonymous')).toBe(false)
    expect(canRenderRoute('accountDeletionConfirm', 'anonymous')).toBe(false)
    expect(canRenderRoute('accountDeletionProgress', 'anonymous')).toBe(true)
  })

  it('routes history targets only through fixed registered destinations and validates resource IDs', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'authenticated')
    const id = '00000000-0000-4000-8000-000000000001'
    expect(router.navigateHistoryTarget('diet_record', id)).toBe(true)
    expect(navigator.navigateTo).toHaveBeenCalledWith(`${APP_ROUTES.recordDiet.path}?id=${id}`)
    expect(router.navigateHistoryTarget('medication_checkin', id)).toBe(true)
    expect(navigator.navigateTo).toHaveBeenCalledWith(APP_ROUTES.medications.path)
    expect(router.navigateHistoryTarget('advice', id)).toBe(true)
    expect(navigator.navigateTo).toHaveBeenCalledWith(APP_ROUTES.advice.path)
    expect(router.navigateHistoryTarget('https://example.invalid/route', id)).toBe(false)
    expect(router.navigateHistoryTarget('diet_record', 'bad-id')).toBe(false)
    expect(navigator.navigateTo).toHaveBeenCalledTimes(3)
    expect(APP_ROUTES.history.path).toBe('/pages/history/index')
    expect(routeNameFromUrl(APP_ROUTES.history.path)).toBe('history')
  })

  it('maps analysis evidence through fixed routes and refuses deleted, invalid, or unsupported sources', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'authenticated')
    const evidence = (source_type: AnalysisResultEvidence['source_type'], source_deleted = false): AnalysisResultEvidence => ({ source_type, source_id: '00000000-0000-4000-8000-000000000001', source_version: 3, locator: 'section-1', source_deleted })
    expect(router.navigateAnalysisEvidence(evidence('diet_record'), 'analysis')).toBe(true)
    expect(navigator.navigateTo).toHaveBeenLastCalledWith(`${APP_ROUTES.recordDiet.path}?id=00000000-0000-4000-8000-000000000001&owner=analysis`)
    expect(router.navigateAnalysisEvidence(evidence('risk_alert'), 'me')).toBe(true)
    expect(navigator.navigateTo).toHaveBeenLastCalledWith(`${APP_ROUTES.riskAlertDetail.path}?alert_id=00000000-0000-4000-8000-000000000001`)
    expect(router.navigateAnalysisEvidence(evidence('diet_record', true), 'analysis')).toBe(false)
    expect(router.navigateAnalysisEvidence({ ...evidence('diet_record'), source_id: 'not-a-uuid' }, 'analysis')).toBe(false)
    expect(router.navigateAnalysisEvidence({ ...evidence('diet_record'), source_type: 'unrecognized' } as unknown as AnalysisResultEvidence, 'analysis')).toBe(false)
    expect(navigator.navigateTo).toHaveBeenCalledTimes(2)
    expect(APP_ROUTES.analysisReports.path).toContain('/pages/analysis/history?owner=analysis&results=1')
    expect(routeNameFromUrl(APP_ROUTES.analysisReports.path)).toBe('analysisReports')
  })

  it('clears authenticated return targets and reLaunches a public deletion progress route after acceptance', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'authenticated')
    router.returnToStore.save({ name: 'profile' })
    router.onAccountDeletionAccepted()
    expect(router.returnToStore.take()).toBeNull()
    expect(navigator.reLaunch).toHaveBeenCalledWith(APP_ROUTES.accountDeletionProgress.path)
    expect(APP_ROUTES.accountDeletionProgress.path).not.toContain('?')
    expect(routeNameFromUrl(APP_ROUTES.accountDeletionProgress.path)).toBe('accountDeletionProgress')
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

  it('guards risk alert deep links and encodes the identifier for an authenticated detail route', () => {
    const navigator = makeNavigator()
    let state: AuthState = 'anonymous'
    const router = new AppRouter(navigator, () => state)
    expect(router.guardUrl('/pages/risk-alerts/detail?alert_id=00000000-0000-4000-8000-000000000001')).toBe(false)
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')
    state = 'authenticated'
    expect(router.navigateRiskAlertDetail('00000000-0000-4000-8000-000000000001')).toBe(true)
    expect(navigator.navigateTo).toHaveBeenCalledWith('/pages/risk-alerts/detail?alert_id=00000000-0000-4000-8000-000000000001')
  })

  it('preserves only a UUID analysis task target through an anonymous deep-link login boundary', () => {
    const navigator = makeNavigator()
    let state: AuthState = 'anonymous'
    const router = new AppRouter(navigator, () => state)
    const id = '00000000-0000-4000-8000-000000000017'
    expect(routeNameFromUrl(`${APP_ROUTES.analysisTaskDetail.path}?task_id=${id}&owner=analysis`)).toBe('analysisTaskDetail')
    expect(router.guardUrl(`${APP_ROUTES.analysisTaskDetail.path}?task_id=${id}&owner=analysis`)).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'analysisTaskDetail' })
    expect(router.navigateAnalysisTaskDetail('not-a-uuid')).toBe(false)
    expect(navigator.reLaunch).toHaveBeenCalledWith(APP_ROUTES.login.path)
    state = 'authenticated'
    router.afterAuthentication()
    expect(navigator.reLaunch).toHaveBeenLastCalledWith(`${APP_ROUTES.analysisTaskDetail.path}?task_id=${id}&owner=analysis`)
    expect(router.returnFromAnalysisTask('analysis', false)).toBe(true)
    expect(navigator.reLaunch).toHaveBeenLastCalledWith(APP_ROUTES.analysis.path)
    expect(router.navigateAnalysisTaskDetail(id, 'me')).toBe(true)
    expect(navigator.navigateTo).toHaveBeenLastCalledWith(`${APP_ROUTES.analysisTaskDetail.path}?task_id=${id}&owner=me`)
    state = 'anonymous'
    expect(router.guardUrl(`${APP_ROUTES.analysisTaskDetail.path}?task_id=${id}&owner=me`)).toBe(false)
    state = 'authenticated'
    router.afterAuthentication()
    expect(navigator.reLaunch).toHaveBeenLastCalledWith(`${APP_ROUTES.analysisTaskDetail.path}?task_id=${id}&owner=me`)
    expect(router.returnFromAnalysisTask('me', false)).toBe(true)
    expect(navigator.reLaunch).toHaveBeenLastCalledWith(APP_ROUTES.me.path)
    expect(APP_ROUTES.analysisNew.path).toBe('/pages/analysis/new')
    expect(APP_ROUTES.analysisHistory.path).toBe('/pages/analysis/history')
    expect(APP_ROUTES.analysisTaskDetail.returnToAllowed).toBe(true)
  })

  it('returns history-origin task details to history without crossing owner tabs or stacking another page', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'authenticated')
    const id = '00000000-0000-4000-8000-000000000018'
    expect(router.navigateAnalysisTaskDetail(id, 'analysis', true)).toBe(true)
    expect(navigator.navigateTo).toHaveBeenLastCalledWith(`${APP_ROUTES.analysisTaskDetail.path}?task_id=${id}&owner=analysis&from=history`)
    expect(router.returnFromAnalysisTask('analysis', true)).toBe(true)
    expect(navigator.redirectTo).toHaveBeenLastCalledWith(`${APP_ROUTES.analysisHistory.path}?owner=analysis`)
    expect(navigator.reLaunch).not.toHaveBeenCalled()

    expect(router.navigateAnalysisTaskDetail(id, 'me', true)).toBe(true)
    expect(navigator.navigateTo).toHaveBeenLastCalledWith(`${APP_ROUTES.analysisTaskDetail.path}?task_id=${id}&owner=me&from=history`)
    expect(router.returnFromAnalysisTask('me', true)).toBe(true)
    expect(navigator.redirectTo).toHaveBeenLastCalledWith(`${APP_ROUTES.analysisHistory.path}?owner=me`)
    expect(navigator.reLaunch).not.toHaveBeenCalled()
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
    expect(router.guardUrl('/pages/records/activity/index?id=00000000-0000-4000-8000-000000000004')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'recordActivity' })
    expect(router.guardUrl('/pages/placeholder/index?screen=unknown')).toBe(false)
    expect(router.returnToStore.take()).toBeNull()
    expect(placeholderRouteFromScreen('recordDiet')).toBeNull()
    expect(placeholderRouteFromScreen('assistant')).toBeNull()
    expect(PLACEHOLDER_META.analysisAdvice.ownerTab).toBe('analysis')
    expect(PLACEHOLDER_META.advice.ownerTab).toBe('me')
    expect(routeNameFromUrl(APP_ROUTES.analysisTrends.path)).toBe('analysisTrends')
    expect(routeNameFromUrl(APP_ROUTES.trends.path)).toBe('trends')
    expect(APP_ROUTES.analysisTrends.path).toContain('owner=analysis')
    expect(APP_ROUTES.trends.path).toContain('owner=me')
  })

  it('uses dedicated protected record workspaces and recognizes ID-bearing deep links', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'anonymous')
    expect(APP_ROUTES.recordDiet.path).toBe('/pages/records/diet/index')
    expect(APP_ROUTES.recordBowel.path).toBe('/pages/records/bowel/index')
    expect(APP_ROUTES.recordSymptoms.path).toBe('/pages/records/symptoms/index')
    expect(APP_ROUTES.recordMood.path).toBe('/pages/records/mood/index')
    expect(APP_ROUTES.recordActivity.path).toBe('/pages/records/activity/index')
    expect(routeNameFromUrl('/pages/records/symptoms/index?id=00000000-0000-4000-8000-000000000001')).toBe('recordSymptoms')
    expect(routeNameFromUrl('/pages/records/mood/index?id=00000000-0000-4000-8000-000000000003')).toBe('recordMood')
    expect(routeNameFromUrl('/pages/records/activity/index?id=00000000-0000-4000-8000-000000000004')).toBe('recordActivity')
    expect(router.guardUrl('/pages/records/diet/index?id=00000000-0000-4000-8000-000000000002')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'recordDiet' })
    expect(router.guardUrl('/pages/records/mood/index?id=00000000-0000-4000-8000-000000000003')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'recordMood' })
    expect(router.guardUrl('/pages/records/activity/index?id=00000000-0000-4000-8000-000000000004')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'recordActivity' })
    expect(navigator.reLaunch).toHaveBeenCalledWith(APP_ROUTES.login.path)
  })

  it('registers medication workspace as protected named child route for safe deep links', () => {
    const navigator = makeNavigator()
    const router = new AppRouter(navigator, () => 'anonymous')
    expect(APP_ROUTES.medications.path).toBe('/pages/medications/index')
    expect(routeNameFromUrl('/pages/medications/index?plan_id=private-id')).toBe('medications')
    expect(router.guardUrl('/pages/medications/index?plan_id=private-id')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'medications' })
    expect(APP_ROUTES.medications.access).toBe('authenticated')
  })

  it('registers F12 pages as protected routes and preserves only allow-listed analysis/advice target IDs through re-auth', () => {
    const navigator = makeNavigator()
    let state: AuthState = 'anonymous'
    const router = new AppRouter(navigator, () => state)
    const id = '00000000-0000-4000-8000-000000000009'
    expect(router.guardUrl('/pages/notifications/index')).toBe(false)
    expect(router.returnToStore.take()).toEqual({ name: 'notifications' })
    expect(canRenderRoute('notificationDetail', 'anonymous')).toBe(false)
    expect(router.navigateNotificationTarget('analysis_task', id)).toBe(false)
    expect(router.returnToStore.takeNotificationTarget()).toEqual({ type: 'analysis_task', id })
    expect(router.guardUrl(`/pages/notifications/target?target_type=advice&target_id=${id}`)).toBe(false)
    expect(router.returnToStore.takeNotificationTarget()).toEqual({ type: 'advice', id })
    expect(router.navigateNotificationTarget('advice', 'not-a-uuid')).toBe(false)
    expect(navigator.navigateTo).not.toHaveBeenCalled()
    state = 'authenticated'
    router.returnToStore.save({ name: 'notificationTarget' })
    router.returnToStore.saveNotificationTarget('advice', id)
    router.afterAuthentication()
    expect(navigator.reLaunch).toHaveBeenLastCalledWith(`/pages/notifications/target?target_type=advice&target_id=${id}`)
    expect(routeNameFromUrl(`/pages/notifications/target?target_type=analysis_task&target_id=${id}`)).toBe('notificationTarget')
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
