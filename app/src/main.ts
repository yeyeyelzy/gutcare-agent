import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './styles/global.scss'
import { createAppServices } from './api/client'
import { activityApiKey, adviceApiKey, analysisApiKey, appRouterKey, authApiKey, consentApiKey, emailVerificationServiceKey, historyApiKey, medicalFactConflictsApiKey, medicationApiKey, moodApiKey, notificationApiKey, passwordResetServiceKey, privacyApiKey, privacyDeletionServiceKey, privacyExportApiKey, privacyExportDownloadKey, profileApiKey, recordsApiKey, registrationServiceKey, requestClientKey, riskApiKey, sessionServiceKey, startupCoordinatorKey, trendApiKey } from './api/context'

export function createApp() {
  const app = createSSRApp(App)
  const pinia = createPinia()
  app.use(pinia)
  const services = createAppServices(pinia)
  app.provide(requestClientKey, services.requestClient)
  app.provide(sessionServiceKey, services.session)
  app.provide(authApiKey, services.authApi)
  app.provide(profileApiKey, services.profileApi)
  app.provide(recordsApiKey, services.recordsApi)
  app.provide(moodApiKey, services.moodApi)
  app.provide(consentApiKey, services.consentApi)
  app.provide(activityApiKey, services.activityApi)
  app.provide(historyApiKey, services.historyApi)
  app.provide(trendApiKey, services.trendApi)
  app.provide(analysisApiKey, services.analysisApi)
  app.provide(adviceApiKey, services.adviceApi)
  app.provide(medicalFactConflictsApiKey, services.medicalFactConflictsApi)
  app.provide(medicationApiKey, services.medicationApi)
  app.provide(riskApiKey, services.riskApi)
  app.provide(notificationApiKey, services.notificationApi)
  app.provide(privacyApiKey, services.privacyApi)
  app.provide(privacyExportApiKey, services.privacyExportApi)
  app.provide(privacyExportDownloadKey, services.privacyExportDownload)
  app.provide(privacyDeletionServiceKey, services.privacyDeletion)
  app.provide(registrationServiceKey, services.registration)
  app.provide(emailVerificationServiceKey, services.emailVerification)
  app.provide(passwordResetServiceKey, services.passwordReset)
  app.provide(appRouterKey, services.router)
  app.provide(startupCoordinatorKey, services.startup)
  return { app }
}
