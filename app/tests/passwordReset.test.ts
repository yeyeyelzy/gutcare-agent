import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { PasswordResetService } from '../src/api/passwordResetService'
import { useRegistrationDraftStore } from '../src/stores/registrationDraft'

function seedRegistrationDraft() {
  const draft = useRegistrationDraftStore()
  draft.saveAccountStep({
    email: 'fixture-register@example.test',
    password: 'fixture-long-password',
    confirmPassword: 'fixture-long-password',
    privacyPolicyAccepted: true,
    privacyPolicyVersion: 'fixture-privacy-v1',
  })
  return draft
}

describe('password reset public flow', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('submits the email-only request and gives no account-existence signal', async () => {
    const requestPasswordReset = vi.fn(async () => ({ operation_id: 'fixture-operation-id', status: 'accepted' as const }))
    const draft = seedRegistrationDraft()
    const service = new PasswordResetService({ requestPasswordReset } as never, draft)
    await service.request('  patient@example.test  ')
    expect(requestPasswordReset).toHaveBeenCalledWith({ email: 'patient@example.test' })
    expect(draft.email).toBe('')
    expect(draft.password).toBe('')
  })

  it('rejects an invalid email before the account-neutral request', async () => {
    const requestPasswordReset = vi.fn()
    const service = new PasswordResetService({ requestPasswordReset } as never, seedRegistrationDraft())
    await expect(service.request('not-an-email')).rejects.toThrow('有效')
    expect(requestPasswordReset).not.toHaveBeenCalled()
  })

  it('accepts manually entered token/new password only and clears registration memory before request', async () => {
    const confirmPasswordReset = vi.fn(async () => undefined)
    const draft = seedRegistrationDraft()
    const service = new PasswordResetService({ confirmPasswordReset } as never, draft)
    await service.confirm(' fixture-reset-one-time-token ', 'fixture-new-password')
    expect(confirmPasswordReset).toHaveBeenCalledWith({ token: 'fixture-reset-one-time-token', new_password: 'fixture-new-password' })
    expect(draft.password).toBe('')
    expect(draft.email).toBe('')
  })

  it('does not persist a token or password when the confirmation request fails', async () => {
    const confirmPasswordReset = vi.fn(async () => { throw new Error('fixture error') })
    const service = new PasswordResetService({ confirmPasswordReset } as never, seedRegistrationDraft())
    await expect(service.confirm('fixture-reset-one-time-token', 'fixture-new-password')).rejects.toThrow('fixture error')
    expect(confirmPasswordReset).toHaveBeenCalledOnce()
    expect(JSON.stringify(useRegistrationDraftStore().$state)).not.toContain('fixture-reset-one-time-token')
    expect(JSON.stringify(useRegistrationDraftStore().$state)).not.toContain('fixture-new-password')
  })

  it('rejects contract-short tokens and passwords before a request', async () => {
    const confirmPasswordReset = vi.fn()
    const service = new PasswordResetService({ confirmPasswordReset } as never, seedRegistrationDraft())
    await expect(service.confirm('too-short', 'fixture-new-password')).rejects.toThrow('有效')
    await expect(service.confirm('fixture-reset-one-time-token', 'short')).rejects.toThrow('有效')
    expect(confirmPasswordReset).not.toHaveBeenCalled()
  })
})
