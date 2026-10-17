import type { AuthApi } from './authApi'
import type { useRegistrationDraftStore } from '../stores/registrationDraft'

type RegistrationDraft = ReturnType<typeof useRegistrationDraftStore>

export class EmailVerificationService {
  constructor(private readonly authApi: AuthApi, private readonly draft: RegistrationDraft) {}

  async verify(token: string): Promise<void> {
    const normalizedToken = token.trim()
    if (!normalizedToken) throw new Error('请输入邮箱验证令牌。')
    await this.authApi.verifyEmail({ token: normalizedToken })
    this.draft.clear()
  }
}
