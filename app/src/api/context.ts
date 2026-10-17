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
import type { MoodApi } from './moodApi'
import type { ConsentApi } from './consentApi'
import type { ActivityApi } from './activityApi'
import type { MedicationApi } from './medicationApi'
import type { RiskApi } from './riskApi'
import type { NotificationApi } from './notificationApi'
import type { PrivacyApi } from './privacyApi'
import type { PrivacyExportApi } from './privacyExportApi'
import type { PrivacyExportDownloadAdapter } from './privacyExportDownload'
import type { PrivacyDeletionService } from './privacyDeletionService'
import type { HistoryApi } from './historyApi'

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
export const moodApiKey: InjectionKey<MoodApi> = Symbol('gutcare-mood-api')
export const consentApiKey: InjectionKey<ConsentApi> = Symbol('gutcare-consent-api')
export const activityApiKey: InjectionKey<ActivityApi> = Symbol('gutcare-activity-api')
export const historyApiKey: InjectionKey<HistoryApi> = Symbol('gutcare-history-api')
export const medicationApiKey: InjectionKey<MedicationApi> = Symbol('gutcare-medication-api')
export const riskApiKey: InjectionKey<RiskApi> = Symbol('gutcare-risk-api')
export const notificationApiKey: InjectionKey<NotificationApi> = Symbol('gutcare-notification-api')
export const privacyApiKey: InjectionKey<PrivacyApi> = Symbol('gutcare-privacy-api')
export const privacyExportApiKey: InjectionKey<PrivacyExportApi> = Symbol('gutcare-privacy-export-api')
export const privacyExportDownloadKey: InjectionKey<PrivacyExportDownloadAdapter> = Symbol('gutcare-privacy-export-download')
export const privacyDeletionServiceKey: InjectionKey<PrivacyDeletionService> = Symbol('gutcare-privacy-deletion-service')
