import { defineStore } from 'pinia'

export type AuthState = 'anonymous' | 'restoring' | 'authenticated'

export const useAuthStore = defineStore('auth', {
  state: () => ({ state: 'anonymous' as AuthState, accessToken: null as string | null }),
  actions: {
    beginRestore() { this.state = 'restoring'; this.accessToken = null },
    acceptAccessToken(token: string) { this.accessToken = token; this.state = 'authenticated' },
    clear() { this.accessToken = null; this.state = 'anonymous' },
  },
})
