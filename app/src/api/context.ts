import type { InjectionKey } from 'vue'
import type { RequestClient } from './requestClient'
import type { SessionService } from './session'
import type { AuthApi } from './authApi'
import type { ProfileApi } from './profileApi'
import type { AppRouter } from '../navigation/router'
import type { StartupCoordinator } from '../navigation/startup'
import type { RegistrationService } from './registrationService'
import type { EmailVerificationService } from './emailVerificationService'
import type { PasswordResetService } from './passwordResetService'
import type { RecordsApi } from './recordsApi'

export const requestClientKey: InjectionKey<RequestClient> = Symbol('gutcare-request-client')
export const sessionServiceKey: InjectionKey<SessionService> = Symbol('gutcare-session-service')
export const authApiKey: InjectionKey<AuthApi> = Symbol('gutcare-auth-api')
export const profileApiKey: InjectionKey<ProfileApi> = Symbol('gutcare-profile-api')
export const appRouterKey: InjectionKey<AppRouter> = Symbol('gutcare-app-router')
export const startupCoordinatorKey: InjectionKey<StartupCoordinator> = Symbol('gutcare-startup-coordinator')
export const registrationServiceKey: InjectionKey<RegistrationService> = Symbol('gutcare-registration-service')
export const emailVerificationServiceKey: InjectionKey<EmailVerificationService> = Symbol('gutcare-email-verification-service')
export const passwordResetServiceKey: InjectionKey<PasswordResetService> = Symbol('gutcare-password-reset-service')
export const recordsApiKey: InjectionKey<RecordsApi> = Symbol('gutcare-records-api')
