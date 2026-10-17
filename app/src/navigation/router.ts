import { APP_ROUTES, APP_TABS, decideRouteAccess, isRegistrationFlowRoute, isUuid, parseReturnTo, routeNameFromUrl } from './routes'
import type { AppRouteName, AppTabName, ReturnToTarget } from './routes'
import type { AuthState } from '../stores/auth'

export interface Navigator {
  navigateTo(url: string): void
  redirectTo(url: string): void
  reLaunch(url: string): void
  navigateBack(): void
  switchTab?(url: string): void
}

export class MemoryReturnToStore {
  private value: ReturnToTarget | null = null
  private notificationTarget: { type: 'analysis_task' | 'advice'; id: string } | null = null

  save(value: unknown): void {
    this.value = parseReturnTo(value)
  }

  take(): ReturnToTarget | null {
    const value = parseReturnTo(this.value)
    this.value = null
    return value
  }

  clear(): void {
    this.value = null
    this.notificationTarget = null
  }

  saveNotificationTarget(type: 'analysis_task' | 'advice', id: string): void {
    this.notificationTarget = isUuid(id) ? { type, id } : null
  }

  takeNotificationTarget(): { type: 'analysis_task' | 'advice'; id: string } | null {
    const value = this.notificationTarget
    this.notificationTarget = null
    return value
  }
}

export class AppRouter {
  private loginRedirectPending = false

  constructor(
    private readonly navigator: Navigator,
    private readonly getAuthState: () => AuthState,
    readonly returnToStore = new MemoryReturnToStore(),
    private readonly clearRegistrationDraft: () => void = () => undefined,
  ) {}

  navigate(name: AppRouteName): boolean {
    if (!this.authorize(name)) return false
    this.clearDraftIfLeavingFlow(name)
    this.navigator.navigateTo(APP_ROUTES[name].path)
    return true
  }

  navigateRiskAlertDetail(id: string): boolean {
    if (!this.authorize('riskAlertDetail')) return false
    if (!/^[0-9a-f-]{36}$/i.test(id)) return false
    this.navigator.navigateTo(`${APP_ROUTES.riskAlertDetail.path}?alert_id=${encodeURIComponent(id)}`)
    return true
  }

  navigateNotificationDetail(id: string): boolean {
    if (!this.authorize('notificationDetail') || !isUuid(id)) return false
    this.navigator.navigateTo(`${APP_ROUTES.notificationDetail.path}?notification_id=${encodeURIComponent(id)}`)
    return true
  }

  navigateNotificationTarget(type: 'analysis_task' | 'advice', id: string): boolean {
    if (!isUuid(id)) return false
    if (!this.authorize('notificationTarget')) {
      this.returnToStore.saveNotificationTarget(type, id)
      return false
    }
    this.navigator.navigateTo(`${APP_ROUTES.notificationTarget.path}?target_type=${type}&target_id=${encodeURIComponent(id)}`)
    return true
  }

  switchTab(name: AppTabName): boolean {
    if (!this.authorize(name)) return false
    this.clearDraftIfLeavingFlow(name)
    const url = APP_ROUTES[name].path
    if (this.navigator.switchTab) this.navigator.switchTab(url)
    else this.navigator.reLaunch(url)
    return true
  }

  redirect(name: AppRouteName): boolean {
    if (!this.authorize(name)) return false
    this.clearDraftIfLeavingFlow(name)
    this.navigator.redirectTo(APP_ROUTES[name].path)
    return true
  }

  reLaunch(name: AppRouteName): boolean {
    if (!this.authorize(name)) return false
    this.clearDraftIfLeavingFlow(name)
    this.navigator.reLaunch(APP_ROUTES[name].path)
    return true
  }

  navigateBack(): void {
    this.navigator.navigateBack()
  }

  requireAuthentication(name: AppRouteName): void {
    const decision = decideRouteAccess(name, this.getAuthState())
    if (decision.action === 'redirect_to_login') this.returnToStore.save(decision.returnTo)
    this.redirectToLoginOnce()
  }

  showLoginForAuthentication(): void {
    this.redirectToLoginOnce()
  }

  afterAuthentication(): void {
    this.loginRedirectPending = false
    const notificationTarget = this.returnToStore.takeNotificationTarget()
    const target = this.returnToStore.take() ?? { name: 'today' as const }
    if (notificationTarget) {
      this.navigator.reLaunch(`${APP_ROUTES.notificationTarget.path}?target_type=${notificationTarget.type}&target_id=${encodeURIComponent(notificationTarget.id)}`)
      return
    }
    this.navigator.reLaunch(APP_ROUTES[target.name].path)
  }

  onAuthenticationRequired(): void {
    // A rejected refresh can mean expiry or account deactivation; both start with a clean public stack.
    this.returnToStore.clear()
    this.redirectToLoginOnce()
  }

  onLogoutCompleted(): void {
    this.returnToStore.clear()
    this.redirectToLoginOnce()
  }

  showProfileIntegrityError(): void {
    this.loginRedirectPending = false
    this.returnToStore.clear()
    this.navigator.reLaunch(APP_ROUTES.profileError.path)
  }

  guardUrl(url: string): boolean {
    if (containsAuthSecretQuery(url)) {
      this.clearRegistrationDraft()
      this.navigator.reLaunch(APP_ROUTES.login.path)
      return false
    }
    const name = routeNameFromUrl(url)
    if (!name) return true
    if (name === 'notificationTarget' && this.getAuthState() !== 'authenticated') {
      const query = new URLSearchParams(url.split('?')[1]?.split('#')[0] ?? '')
      const type = query.get('target_type')
      const id = query.get('target_id')
      if ((type === 'analysis_task' || type === 'advice') && isUuid(id)) {
        this.returnToStore.saveNotificationTarget(type, id)
      }
    }
    this.clearDraftIfLeavingFlow(name)
    const decision = decideRouteAccess(name, this.getAuthState())
    if (decision.action === 'allow') return true
    this.requireAuthentication(name)
    return false
  }

  private authorize(name: AppRouteName): boolean {
    const decision = decideRouteAccess(name, this.getAuthState())
    if (decision.action === 'allow') return true
    if (decision.action === 'redirect_to_login') this.requireAuthentication(name)
    return false
  }

  private redirectToLoginOnce(): void {
    if (this.loginRedirectPending) return
    this.loginRedirectPending = true
    this.navigator.reLaunch(APP_ROUTES.login.path)
  }

  private clearDraftIfLeavingFlow(name: AppRouteName): void {
    if (!isRegistrationFlowRoute(name)) this.clearRegistrationDraft()
  }
}

function containsAuthSecretQuery(url: string): boolean {
  const query = url.split('?')[1]?.split('#')[0]
  if (!query) return false
  for (const key of new URLSearchParams(query).keys()) {
    if (['token', 'access_token', 'refresh_token', 'password', 'new_password'].includes(key.toLowerCase())) return true
  }
  return false
}

/** Install before app launch so known protected pages cannot be navigated to anonymously. */
export function installGlobalRouteGuards(router: AppRouter): void {
  const interceptor = {
    invoke(args: { url?: string }) {
      if (typeof args.url === 'string' && !router.guardUrl(args.url)) return false
    },
  }
  for (const method of ['navigateTo', 'redirectTo', 'reLaunch', 'switchTab']) {
    uni.addInterceptor(method, interceptor)
  }
}

export function tabNameForRoute(name: AppRouteName | null): AppTabName | null {
  return name && APP_TABS.includes(name as AppTabName) ? name as AppTabName : null
}
