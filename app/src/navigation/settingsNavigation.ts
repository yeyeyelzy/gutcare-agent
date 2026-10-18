import type { AppRouteName, AppTabName } from './routes'

export const SETTINGS_ROW_ROUTES = {
  profile: 'profile',
  notifications: 'notificationPreferences',
  consents: 'privacyConsents',
  privacyCenter: 'privacyCenter',
  export: 'privacyExports',
  deletion: 'accountDeletionConfirm',
} as const satisfies Record<string, AppRouteName>

export const ME_SETTINGS_ENTRY_ROUTE = 'settings' as const

export type SettingsRowId = keyof typeof SETTINGS_ROW_ROUTES

export function getSettingsAppVersion(versionName: unknown): string {
  return typeof versionName === 'string' && versionName.trim() ? versionName : '暂不可用'
}

export interface SettingsNavigator {
  navigate(name: AppRouteName): boolean
  navigateBack(): void
  switchTab(name: AppTabName): boolean
}

export function navigateMeEntry(router: Pick<SettingsNavigator, 'navigate'> | null | undefined, route: AppRouteName): boolean {
  return router ? router.navigate(route) : false
}

export function openSettingsRow(router: Pick<SettingsNavigator, 'navigate'> | null | undefined, row: unknown): boolean {
  if (!router || typeof row !== 'string' || !Object.hasOwn(SETTINGS_ROW_ROUTES, row)) return false
  return router.navigate(SETTINGS_ROW_ROUTES[row as SettingsRowId])
}

export function returnFromSettings(router: Pick<SettingsNavigator, 'navigateBack' | 'switchTab'> | null | undefined, stackLength: number): void {
  if (!router) return
  if (stackLength > 1) router.navigateBack()
  else router.switchTab('me')
}

export function returnFromConsents(router: Pick<SettingsNavigator, 'navigate' | 'navigateBack'> | null | undefined, stackLength: number): void {
  if (!router) return
  if (stackLength > 1) router.navigateBack()
  else router.navigate('settings')
}

export function returnFromPrivacyCenter(router: Pick<SettingsNavigator, 'navigateBack' | 'switchTab'> | null | undefined, stackLength: number): void {
  if (!router) return
  if (stackLength > 1) router.navigateBack()
  else router.switchTab('me')
}
