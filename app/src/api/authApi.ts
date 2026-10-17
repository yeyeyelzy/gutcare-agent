import type { RequestClient } from './requestClient'
import type { SessionService } from './session'
import type {
  AcceptedOperation,
  LoginRequest,
  PasswordResetConfirmRequest,
  PasswordResetRequest,
  RegisterRequest,
  VerifyEmailRequest,
} from './openapiTypes'

const REGISTER_FIELDS = [
  'email',
  'password',
  'birth_year',
  'privacy_policy_version',
  'health_data_processing_consent',
  'health_data_processing_policy_version',
] as const

export class AuthApi {
  constructor(
    private readonly client: RequestClient,
    private readonly session: SessionService,
  ) {}

  register(request: RegisterRequest): Promise<AcceptedOperation> {
    assertExactFields(request, REGISTER_FIELDS)
    return this.client.request<AcceptedOperation>({
      method: 'POST',
      path: '/auth/register',
      data: request,
      retryOnUnauthorized: false,
    })
  }

  verifyEmail(request: VerifyEmailRequest): Promise<void> {
    return this.client.request<void>({
      method: 'POST',
      path: '/auth/email/verify',
      data: request,
      retryOnUnauthorized: false,
    })
  }

  /** Login and logout delegate session persistence/rotation to B00b SessionService. */
  login(request: LoginRequest): Promise<void> {
    return this.session.login(request)
  }

  logout(): Promise<void> {
    return this.session.logout()
  }

  requestPasswordReset(request: PasswordResetRequest): Promise<AcceptedOperation> {
    return this.client.request<AcceptedOperation>({
      method: 'POST',
      path: '/auth/password/reset/request',
      data: request,
      retryOnUnauthorized: false,
    })
  }

  confirmPasswordReset(request: PasswordResetConfirmRequest): Promise<void> {
    return this.client.request<void>({
      method: 'POST',
      path: '/auth/password/reset/confirm',
      data: request,
      retryOnUnauthorized: false,
    })
  }
}

function assertExactFields(value: object, expectedFields: readonly string[]): void {
  const actual = Object.keys(value).sort()
  const expected = [...expectedFields].sort()
  if (actual.length !== expected.length || actual.some((field, index) => field !== expected[index])) {
    throw new TypeError('Registration request does not match the frozen API contract.')
  }
}
