import type { AuthApi } from './authApi'
import type { useRegistrationDraftStore } from '../stores/registrationDraft'
import { isValidEmail } from './authFormValidation'

type RegistrationDraft = ReturnType<typeof useRegistrationDraftStore>

/** Password reset inputs exist only for the lifetime of the calling screen. */
export class PasswordResetService {
  constructor(private readonly authApi: AuthApi, private readonly registrationDraft: RegistrationDraft) {}

  async request(email: string): Promise<void> {
    const normalizedEmail = email.trim()
    if (!isValidEmail(normalizedEmail)) throw new Error('请输入有效的邮箱地址。')
    this.registrationDraft.clear()
    await this.authApi.requestPasswordReset({ email: normalizedEmail })
  }

  async confirm(token: string, newPassword: string): Promise<void> {
    const normalizedToken = token.trim()
    if (normalizedToken.length < 20 || newPassword.length < 12 || newPassword.length > 128) throw new Error('请输入有效的重置令牌和新密码。')
    this.registrationDraft.clear()
    await this.authApi.confirmPasswordReset({ token: normalizedToken, new_password: newPassword })
  }
}
