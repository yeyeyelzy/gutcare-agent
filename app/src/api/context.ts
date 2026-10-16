import type { InjectionKey } from 'vue'
import type { RequestClient } from './requestClient'
import type { SessionService } from './session'

export const requestClientKey: InjectionKey<RequestClient> = Symbol('gutcare-request-client')
export const sessionServiceKey: InjectionKey<SessionService> = Symbol('gutcare-session-service')
