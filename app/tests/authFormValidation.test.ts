import { describe, expect, it } from 'vitest'
import { isValidEmail, passwordResetValidationError, validateRegistrationCredentials } from '../src/api/authFormValidation'

describe('auth form validation rules', () => {
  it('validates email-only login and registration addresses', () => {
    expect(isValidEmail('  person@example.test  ')).toBe(true)
    expect(isValidEmail('not-an-email')).toBe(false)
    expect(isValidEmail('person@')).toBe(false)
    expect(isValidEmail(`${'x'.repeat(250)}@example.test`)).toBe(false)
  })

  it('requires privacy acceptance and matching 12-character registration passwords', () => {
    const base = { email: 'person@example.test', password: 'fixture-long-password', confirmPassword: 'fixture-long-password', privacyAccepted: true }
    expect(validateRegistrationCredentials(base)).toBeNull()
    expect(validateRegistrationCredentials({ ...base, privacyAccepted: false })).toBe('privacy_consent')
    expect(validateRegistrationCredentials({ ...base, password: 'short', confirmPassword: 'short' })).toBe('password')
    expect(validateRegistrationCredentials({ ...base, password: 'x'.repeat(129), confirmPassword: 'x'.repeat(129) })).toBe('password')
    expect(validateRegistrationCredentials({ ...base, confirmPassword: 'different-long-password' })).toBe('password_mismatch')
    expect(validateRegistrationCredentials({ ...base, email: 'bad' })).toBe('email')
  })

  it('requires a manually supplied reset token and matching new password', () => {
    expect(passwordResetValidationError({ token: ' fixture-one-time-reset-token ', password: 'fixture-new-password', confirmation: 'fixture-new-password' })).toBeNull()
    expect(passwordResetValidationError({ token: ' ', password: 'fixture-new-password', confirmation: 'fixture-new-password' })).toBe('token')
    expect(passwordResetValidationError({ token: 'fixture-one-time-reset-token', password: 'short', confirmation: 'short' })).toBe('password')
    expect(passwordResetValidationError({ token: 'fixture-one-time-reset-token', password: 'fixture-new-password', confirmation: 'different-password' })).toBe('password_mismatch')
  })
})
