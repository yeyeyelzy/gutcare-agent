export const APP_ROUTES = {
  launch: { path: '/pages/launch/index', access: 'public', returnToAllowed: false },
  login: { path: '/pages/auth/login', access: 'public', returnToAllowed: false },
  register: { path: '/pages/auth/register', access: 'public', returnToAllowed: false },
  registerProfile: { path: '/pages/auth/register-profile', access: 'public', returnToAllowed: false },
  emailVerification: { path: '/pages/auth/email-verification', access: 'public', returnToAllowed: false },
  forgotPassword: { path: '/pages/auth/forgot-password', access: 'public', returnToAllowed: false },
  resetPassword: { path: '/pages/auth/reset-password', access: 'public', returnToAllowed: false },
  profileError: { path: '/pages/auth/profile-error', access: 'public', returnToAllowed: false },
  accountDeletionProgress: { path: '/pages/privacy/deletion-progress', access: 'public', returnToAllowed: false },
  today: { path: '/pages/tabs/today/index', logicalPath: '/tabs/today', access: 'authenticated', returnToAllowed: true, tab: true },
  records: { path: '/pages/tabs/records/index', logicalPath: '/tabs/records', access: 'authenticated', returnToAllowed: true, tab: true },
  analysis: { path: '/pages/tabs/analysis/index', logicalPath: '/tabs/analysis', access: 'authenticated', returnToAllowed: true, tab: true },
  me: { path: '/pages/tabs/me/index', logicalPath: '/tabs/me', access: 'authenticated', returnToAllowed: true, tab: true },
  profile: { path: '/pages/profile/index', access: 'authenticated', returnToAllowed: true },
  privacyCenter: { path: '/pages/privacy/center', access: 'authenticated', returnToAllowed: true },
  privacyExports: { path: '/pages/privacy/exports', access: 'authenticated', returnToAllowed: true },
  accountDeletionConfirm: { path: '/pages/privacy/deletion-confirm', access: 'authenticated', returnToAllowed: false },
  placeholder: { path: '/pages/placeholder/index', access: 'authenticated', returnToAllowed: false },
  recordDiet: { path: '/pages/records/diet/index', access: 'authenticated', returnToAllowed: true },
  recordBowel: { path: '/pages/records/bowel/index', access: 'authenticated', returnToAllowed: true },
  recordSymptoms: { path: '/pages/records/symptoms/index', access: 'authenticated', returnToAllowed: true },
  recordMood: { path: '/pages/records/mood/index', access: 'authenticated', returnToAllowed: true },
  recordActivity: { path: '/pages/records/activity/index', access: 'authenticated', returnToAllowed: true },
  medications: { path: '/pages/medications/index', access: 'authenticated', returnToAllowed: true },
  riskAlerts: { path: '/pages/risk-alerts/index', access: 'authenticated', returnToAllowed: true },
  history: { path: '/pages/history/index', access: 'authenticated', returnToAllowed: true },
  analysisTrends: { path: '/pages/trends/index?owner=analysis', access: 'authenticated', returnToAllowed: true },
  trends: { path: '/pages/trends/index?owner=me', access: 'authenticated', returnToAllowed: true },
  riskAlertDetail: { path: '/pages/risk-alerts/detail', access: 'authenticated', returnToAllowed: false },
  notifications: { path: '/pages/notifications/index', access: 'authenticated', returnToAllowed: true },
  notificationDetail: { path: '/pages/notifications/detail', access: 'authenticated', returnToAllowed: false },
  notificationPreferences: { path: '/pages/notifications/preferences', access: 'authenticated', returnToAllowed: true },
  notificationTarget: { path: '/pages/notifications/target', access: 'authenticated', returnToAllowed: true },
  analysisNew: { path: '/pages/placeholder/index?screen=analysisNew', access: 'authenticated', returnToAllowed: true },
  analysisHistory: { path: '/pages/placeholder/index?screen=analysisHistory', access: 'authenticated', returnToAllowed: true },
  analysisReports: { path: '/pages/placeholder/index?screen=analysisReports', access: 'authenticated', returnToAllowed: true },
  analysisAdvice: { path: '/pages/placeholder/index?screen=analysisAdvice', access: 'authenticated', returnToAllowed: true },
  advice: { path: '/pages/placeholder/index?screen=advice', access: 'authenticated', returnToAllowed: true },
  healthArchive: { path: '/pages/placeholder/index?screen=healthArchive', access: 'authenticated', returnToAllowed: true },
  settings: { path: '/pages/placeholder/index?screen=settings', access: 'authenticated', returnToAllowed: true },
} as const

export type AppRouteName = keyof typeof APP_ROUTES
export const APP_TABS = ['today', 'records', 'analysis', 'me'] as const
export type AppTabName = typeof APP_TABS[number]
export type RecordWorkspaceRouteName = 'recordDiet' | 'recordBowel' | 'recordSymptoms'
export type MoodWorkspaceRouteName = 'recordMood'
export type ActivityWorkspaceRouteName = 'recordActivity'
export type MedicationWorkspaceRouteName = 'medications'
export type RiskRouteName = 'riskAlerts' | 'riskAlertDetail'
export type NotificationRouteName = 'notifications' | 'notificationDetail' | 'notificationPreferences' | 'notificationTarget'
export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
}
export type SafeNotificationTarget =
  | { kind: 'risk_alert'; id: string }
  | { kind: 'medication_checkin'; id: string }
  | { kind: 'analysis_task'; id: string }
  | { kind: 'advice'; id: string }
  | { kind: 'unavailable' }

export function mapNotificationTarget(target: { type: string; id: string } | null, targetUnavailable: boolean): SafeNotificationTarget {
  if (targetUnavailable || !target || !isUuid(target.id)) return { kind: 'unavailable' }
  if (target.type === 'risk_alert' || target.type === 'medication_checkin' || target.type === 'analysis_task' || target.type === 'advice') {
    return { kind: target.type, id: target.id }
  }
  return { kind: 'unavailable' }
}
export type PlaceholderRouteName = Exclude<AppRouteName, 'launch' | 'login' | 'register' | 'registerProfile' | 'emailVerification' | 'forgotPassword' | 'resetPassword' | 'profileError' | 'accountDeletionProgress' | 'today' | 'records' | 'analysis' | 'me' | 'profile' | 'privacyCenter' | 'privacyExports' | 'accountDeletionConfirm' | 'placeholder' | 'history' | 'trends' | 'analysisTrends' | RecordWorkspaceRouteName | MoodWorkspaceRouteName | ActivityWorkspaceRouteName | MedicationWorkspaceRouteName | RiskRouteName | NotificationRouteName>
export type ProtectedRouteName = {
  [Name in AppRouteName]: typeof APP_ROUTES[Name]['access'] extends 'authenticated' ? Name : never
}[AppRouteName]
export type ReturnToTarget = { name: ProtectedRouteName }
export type RouteAuthState = 'anonymous' | 'restoring' | 'session_ready' | 'loading_profile' | 'authenticated'

export function isRegistrationFlowRoute(name: AppRouteName): boolean {
  return name === 'register' || name === 'registerProfile' || name === 'emailVerification'
}

export type RouteDecision =
  | { action: 'allow' }
  | { action: 'redirect_to_login'; returnTo: ReturnToTarget }
  | { action: 'deny' }

export function decideRouteAccess(name: AppRouteName, state: RouteAuthState): RouteDecision {
  if (APP_ROUTES[name].access === 'public' || state === 'authenticated') return { action: 'allow' }
  if (APP_ROUTES[name].returnToAllowed) return { action: 'redirect_to_login', returnTo: { name: name as ProtectedRouteName } }
  return { action: 'deny' }
}

export function canRenderRoute(name: AppRouteName, state: RouteAuthState): boolean {
  return decideRouteAccess(name, state).action === 'allow'
}

export function routeNameFromUrl(url: string): AppRouteName | null {
  const normalized = (url.split('#')[0] ?? url).replace(/\/$/, '')
  for (const [name, route] of Object.entries(APP_ROUTES)) {
    if (route.path === normalized) return name as AppRouteName
  }
  const path = normalized.split('?')[0] ?? ''
  for (const [name, route] of Object.entries(APP_ROUTES)) {
    if (route.path.split('?')[0] === path && route.path.includes('?screen=')) {
      const expected = route.path.split('?')[1]
      if (normalized.slice(path.length + 1) === expected) return name as AppRouteName
    }
  }
  for (const [name, route] of Object.entries(APP_ROUTES)) {
    if (!route.path.includes('?') && route.path === path) return name as AppRouteName
  }
  return null
}

export const PLACEHOLDER_META: Record<PlaceholderRouteName, { title: string; ownerTab: AppTabName }> = {
  analysisNew: { title: '发起分析', ownerTab: 'analysis' },
  analysisHistory: { title: '分析历史', ownerTab: 'analysis' },
  analysisReports: { title: '分析报告', ownerTab: 'analysis' },
  analysisAdvice: { title: '个性化建议', ownerTab: 'analysis' },
  advice: { title: '个性化建议', ownerTab: 'me' },
  healthArchive: { title: '健康档案', ownerTab: 'me' },
  settings: { title: '设置', ownerTab: 'me' },
}

export function placeholderRouteFromScreen(screen: unknown): PlaceholderRouteName | null {
  return typeof screen === 'string' && Object.hasOwn(PLACEHOLDER_META, screen)
    ? screen as PlaceholderRouteName
    : null
}

export function parseReturnTo(value: unknown): ReturnToTarget | null {
  if (typeof value !== 'object' || value === null || !('name' in value)) return null
  const name = (value as { name: unknown }).name
  if (typeof name !== 'string' || !Object.hasOwn(APP_ROUTES, name)) return null
  const route = APP_ROUTES[name as AppRouteName]
  if (route.access !== 'authenticated' || !route.returnToAllowed) return null
  return { name: name as ProtectedRouteName }
}
