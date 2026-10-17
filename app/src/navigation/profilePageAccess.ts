import type { AppRouter } from './router'
import type { StartupCoordinator } from './startup'
import type { AuthState } from '../stores/auth'

export interface ProtectedProfileAuth { readonly state: AuthState }
export type ProfilePageAccessResult = 'authorized' | 'login_redirected' | 'profile_error_redirected'

/** Wait for the shared session/profile restoration before allowing the profile page to mount. */
export async function enterProtectedProfilePage(
  startup: StartupCoordinator | undefined,
  auth: ProtectedProfileAuth,
  router: AppRouter | undefined,
  onAuthorized: (profileLoadedDuringStartup: boolean) => unknown | Promise<unknown>,
): Promise<ProfilePageAccessResult> {
  if (!router) return 'login_redirected'
  if (!startup) {
    router.onAuthenticationRequired()
    return 'login_redirected'
  }
  const startupWasPending = startup.state !== 'ready'
  if (startupWasPending) router.returnToStore.save({ name: 'profile' })
  const state = await startup.start()
  if (state === 'ready' && auth.state === 'authenticated') {
    await onAuthorized(startupWasPending)
    return 'authorized'
  }
  if (state === 'profile_error') return 'profile_error_redirected'
  router.onAuthenticationRequired()
  return 'login_redirected'
}
