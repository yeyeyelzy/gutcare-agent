import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './styles/global.scss'
import { createAppServices } from './api/client'
import { requestClientKey, sessionServiceKey } from './api/context'

export function createApp() {
  const app = createSSRApp(App)
  const pinia = createPinia()
  app.use(pinia)
  const services = createAppServices(pinia)
  app.provide(requestClientKey, services.requestClient)
  app.provide(sessionServiceKey, services.session)
  return { app }
}
