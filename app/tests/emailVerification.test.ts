import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { AppError } from '../src/api/errors'
import { EmailVerificationService } from '../src/api/emailVerificationService'
import { useRegistrationDraftStore } from '../src/stores/registrationDraft'

function makeDraft() {
  const draft = useRegistrationDraftStore()
  draft.saveAccountStep({
    email: 'patient@example.test',
    password: 'fixture-password-only',
    confirmPassword: 'fixture-password-only',
    privacyPolicyAccepted: true,
    privacyPolicyVersion: 'fixture-privacy-v1',
  })
  draft.clearPasswordsAfterAccepted()
  return draft
}

describe('email verification workflow', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('sends a trimmed one-time token, clears all draft state on 204, and does not persist the token', async () => {
    const draft = makeDraft()
    const verifyEmail = vi.fn(async () => undefined)
    const service = new EmailVerificationService({ verifyEmail } as never, draft)
    await service.verify(' fixture-one-time-token ')
    expect(verifyEmail).toHaveBeenCalledWith({ token: 'fixture-one-time-token' })
    expect(draft.email).toBe('')
    expect(draft.password).toBe('')
    expect(draft.confirmPassword).toBe('')
    expect(JSON.stringify(draft.$state)).not.toContain('fixture-one-time-token')
  })

  it('retains only the non-sensitive email when RFC 9457 API errors reject verification', async () => {
    const draft = makeDraft()
    const problem = {
      type: 'https://gutcare.invalid/problems/validation_error',
      title: 'Invalid verification token',
      status: 422,
      code: 'INVALID_VERIFICATION_TOKEN',
      request_id: 'fixture-request-id',
    }
    const service = new EmailVerificationService({
      verifyEmail: vi.fn(async () => { throw new AppError('http', problem.title, { status: problem.status, problem }) }),
    } as never, draft)
    await expect(service.verify('fixture-one-time-token')).rejects.toMatchObject({
      status: 422, problem: { code: 'INVALID_VERIFICATION_TOKEN', request_id: 'fixture-request-id' },
    })
    expect(draft.email).toBe('patient@example.test')
    expect(draft.password).toBe('')
    expect(draft.confirmPassword).toBe('')
  })

  it('rejects an empty token without calling the API', async () => {
    const verifyEmail = vi.fn()
    const service = new EmailVerificationService({ verifyEmail } as never, makeDraft())
    await expect(service.verify('  ')).rejects.toThrow('请输入')
    expect(verifyEmail).not.toHaveBeenCalled()
  })
})
