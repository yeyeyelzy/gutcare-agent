import { get, has, remove, set } from '@/../uni_modules/gutcare-secure-store'
import { NativeSecureTokenStore } from './secureTokenStore'

export const nativeSecureTokenStore = new NativeSecureTokenStore({ get, has, remove, set })
