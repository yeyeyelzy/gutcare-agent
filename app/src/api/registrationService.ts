import type { AuthApi } from './authApi'
import type { useRegistrationDraftStore } from '../stores/registrationDraft'

type RegistrationDraft = ReturnType<typeof useRegistrationDraftStore>

export class RegistrationService {
  constructor(private readonly authApi: AuthApi, private readonly draft: RegistrationDraft) {}

  async complete(): Promise<void> {
    const request = this.draft.buildRegisterRequest()
    await this.authApi.register(request)
    this.draft.clearPasswordsAfterAccepted()
  }
}
