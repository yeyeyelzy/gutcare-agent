export const APP_ROUTES = {
  launch: { path: '/pages/launch/index', access: 'public', returnToAllowed: false },
  login: { path: '/pages/auth/login', access: 'public', returnToAllowed: false },
  register: { path: '/pages/auth/register', access: 'public', returnToAllowed: false },
  registerProfile: { path: '/pages/auth/register-profile', access: 'public', returnToAllowed: false },
  emailVerification: { path: '/pages/auth/email-verification', access: 'public', returnToAllowed: false },
  forgotPassword: { path: '/pages/auth/forgot-password', access: 'public', returnToAllowed: false },
  resetPassword: { path: '/pages/auth/reset-password', access: 'public', returnToAllowed: false },
  profileError: { path: '/pages/auth/profile-error', access: 'public', returnToAllowed: false },
  today: { path: '/pages/home/index', access: 'authenticated', returnToAllowed: true },
  profile: { path: '/pages/profile/index', access: 'authenticated', returnToAllowed: true },
} as const

export type AppRouteName = keyof typeof APP_ROUTES
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
  const path = url.split('?')[0]?.replace(/\/$/, '')
  for (const [name, route] of Object.entries(APP_ROUTES)) {
    if (route.path === path) return name as AppRouteName
  }
  return null
}

export function parseReturnTo(value: unknown): ReturnToTarget | null {
  if (typeof value !== 'object' || value === null || !('name' in value)) return null
  const name = (value as { name: unknown }).name
  if (typeof name !== 'string' || !Object.hasOwn(APP_ROUTES, name)) return null
  const route = APP_ROUTES[name as AppRouteName]
  if (route.access !== 'authenticated' || !route.returnToAllowed) return null
  return { name: name as ProtectedRouteName }
}
