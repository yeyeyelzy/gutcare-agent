import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './styles/global.scss'
import { createAppServices } from './api/client'
import { appRouterKey, authApiKey, consentApiKey, emailVerificationServiceKey, moodApiKey, passwordResetServiceKey, profileApiKey, recordsApiKey, registrationServiceKey, requestClientKey, sessionServiceKey, startupCoordinatorKey } from './api/context'

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
  app.provide(registrationServiceKey, services.registration)
  app.provide(emailVerificationServiceKey, services.emailVerification)
  app.provide(passwordResetServiceKey, services.passwordReset)
  app.provide(appRouterKey, services.router)
  app.provide(startupCoordinatorKey, services.startup)
  return { app }
}
