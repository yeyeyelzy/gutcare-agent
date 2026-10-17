import { AppError } from '../api/errors'
import { ref } from 'vue'
import type { ProfileApi } from '../api/profileApi'
import type { RequestClient } from '../api/requestClient'
import type { SessionService } from '../api/session'
import type { useAuthStore } from '../stores/auth'
import type { AppRouter } from './router'

type AuthStore = ReturnType<typeof useAuthStore>
export type StartupState = 'idle' | 'restoring' | 'loading_profile' | 'ready' | 'anonymous' | 'profile_error' | 'unavailable'

export class StartupCoordinator {
  private readonly currentState = ref<StartupState>('idle')

  get state(): StartupState { return this.currentState.value }
  private set state(value: StartupState) { this.currentState.value = value }

  constructor(
    private readonly session: SessionService,
    private readonly profile: ProfileApi,
    private readonly requestClient: RequestClient,
    private readonly auth: AuthStore,
    private readonly router: AppRouter,
  ) {}

  async start(): Promise<StartupState> {
    if (this.state !== 'idle') return this.state
    this.state = 'restoring'
    try {
      const restored = await this.session.restore()
      if (!restored) {
        this.state = 'anonymous'
        this.router.showLoginForAuthentication()
        return this.state
      }
      return await this.loadProfileAndNavigate()
    } catch (error) {
      this.auth.clear()
      this.state = isTransient(error) || isDeviceLocked(error) ? 'unavailable' : 'anonymous'
      if (this.state === 'anonymous') this.router.onAuthenticationRequired()
      return this.state
    }
  }

  async continueAfterLogin(): Promise<StartupState> {
    return this.loadProfileAndNavigate()
  }

  async retryProfileLoad(): Promise<StartupState> {
    if (!this.auth.accessToken) {
      this.state = 'anonymous'
      this.router.onAuthenticationRequired()
      return this.state
    }
    return this.loadProfileAndNavigate()
  }

  private async loadProfileAndNavigate(): Promise<StartupState> {
    this.state = 'loading_profile'
    this.auth.beginProfileLoad()
    try {
      const profile = await this.profile.getMyProfile()
      this.auth.acceptProfile(profile)
      this.state = 'ready'
      this.router.afterAuthentication()
      return this.state
    } catch (error) {
      if (error instanceof AppError && error.status === 404) {
        const requestId = error.requestId ?? error.problem?.request_id ?? null
        await this.requestClient.clearStoredSession().catch(() => undefined)
        this.auth.failProfileLoad(requestId)
        this.router.showProfileIntegrityError()
        this.state = 'profile_error'
        return this.state
      }
      if (error instanceof AppError && error.status === 401) {
        await this.requestClient.clearStoredSession().catch(() => undefined)
        this.auth.clear()
        this.router.onAuthenticationRequired()
        this.state = 'anonymous'
        return this.state
      }
      this.auth.profileLoadFailed()
      this.state = 'unavailable'
      return this.state
    }
  }
}

function isTransient(error: unknown): boolean {
  return error instanceof AppError && ['network', 'timeout', 'offline', 'unavailable'].includes(error.kind)
}

function isDeviceLocked(error: unknown): boolean {
  return error instanceof AppError && error.code === 'DEVICE_LOCKED'
}
