export type RegistrationValidationError = 'email' | 'password' | 'password_mismatch' | 'privacy_consent'

export function isValidEmail(value: string): boolean {
  const email = value.trim()
  return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

export function validateRegistrationCredentials(input: {
  email: string
  password: string
  confirmPassword: string
  privacyAccepted: boolean
}): RegistrationValidationError | null {
  if (!isValidEmail(input.email)) return 'email'
  if (input.password.length < 12 || input.password.length > 128) return 'password'
  if (input.password !== input.confirmPassword) return 'password_mismatch'
  if (!input.privacyAccepted) return 'privacy_consent'
  return null
}

export function passwordResetValidationError(input: {
  token: string
  password: string
  confirmation: string
}): 'token' | 'password' | 'password_mismatch' | null {
  if (input.token.trim().length < 20) return 'token'
  if (input.password.length < 12 || input.password.length > 128) return 'password'
  if (input.password !== input.confirmation) return 'password_mismatch'
  return null
}
