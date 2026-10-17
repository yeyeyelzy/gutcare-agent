import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { RegistrationService } from '../src/api/registrationService'
import { useRegistrationDraftStore } from '../src/stores/registrationDraft'
import type { RegisterRequest } from '../src/api/openapiTypes'

function fillAccountStep() {
  const draft = useRegistrationDraftStore()
  draft.saveAccountStep({
    email: 'patient@example.test',
    password: 'fixture-password-only',
    confirmPassword: 'fixture-password-only',
    privacyPolicyAccepted: true,
    privacyPolicyVersion: 'fixture-privacy-v1',
  })
  return draft
}

describe('in-memory two-screen registration draft', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('does not store step-22 fields until privacy choice and confirmation are valid', () => {
    const draft = useRegistrationDraftStore()
    expect(() => draft.saveAccountStep({
      email: 'patient@example.test', password: 'fixture-password-only', confirmPassword: 'fixture-password-only',
      privacyPolicyAccepted: false, privacyPolicyVersion: 'fixture-privacy-v1',
    })).toThrow('隐私政策')
    expect(draft.password).toBe('')
    expect(() => draft.saveAccountStep({
      email: 'patient@example.test', password: 'fixture-password-only', confirmPassword: 'different-fixture-password',
      privacyPolicyAccepted: true, privacyPolicyVersion: 'fixture-privacy-v1',
    })).toThrow('不一致')
    expect(draft.email).toBe('')
  })

  it('requires step 17 and explicit health processing consent before birth year collection', () => {
    const draft = fillAccountStep()
    expect(() => draft.setBirthYear(1990)).toThrow('同意健康数据处理前')
    expect(() => draft.buildRegisterRequest()).toThrow('尚未完成')
    draft.enterProfileStep()
    expect(() => draft.setBirthYear(1990)).toThrow('同意健康数据处理前')
    draft.decideHealthDataProcessing(false, 'fixture-health-v1')
    expect(() => draft.setBirthYear(1990)).toThrow('同意健康数据处理前')
    expect(() => draft.buildRegisterRequest()).toThrow('尚未完成')
    expect(draft.password).toBe('fixture-password-only')
    expect(draft.birthYear).toBeNull()
  })

  it('clears the entire draft, including password and email, when registration is cancelled', () => {
    const draft = fillAccountStep()
    draft.enterProfileStep()
    draft.decideHealthDataProcessing(true, 'fixture-health-v1')
    draft.setBirthYear(1990)
    draft.cancelWorkflow()
    expect(draft.$state).toMatchObject({
      email: '', password: '', confirmPassword: '', privacyPolicyAccepted: false, privacyPolicyVersion: '',
      profileStepVisited: false, healthDataProcessingConsent: false, healthDataProcessingPolicyVersion: '', birthYear: null,
    })
    expect(draft.password).toBe('')
    expect(draft.confirmPassword).toBe('')
    expect(draft.email).toBe('')
    expect(draft.birthYear).toBeNull()
  })

  it('constructs exactly the six frozen fields and clears passwords after accepted registration', async () => {
    const draft = fillAccountStep()
    draft.enterProfileStep()
    draft.decideHealthDataProcessing(true, 'fixture-health-v1')
    draft.setBirthYear(1990)
    const request = draft.buildRegisterRequest()
    expect(Object.keys(request).sort()).toEqual([
      'birth_year', 'email', 'health_data_processing_consent', 'health_data_processing_policy_version',
      'password', 'privacy_policy_version',
    ].sort())
    expect(request).toEqual({
      email: 'patient@example.test',
      password: 'fixture-password-only',
      birth_year: 1990,
      privacy_policy_version: 'fixture-privacy-v1',
      health_data_processing_consent: true,
      health_data_processing_policy_version: 'fixture-health-v1',
    } satisfies RegisterRequest)
    const register = vi.fn(async (body: RegisterRequest) => {
      expect(Object.keys(body)).toHaveLength(6)
      return { operation_id: 'fixture-operation-id', status: 'accepted' as const }
    })
    await new RegistrationService({ register } as never, draft).complete()
    expect(register).toHaveBeenCalledOnce()
    expect(draft.password).toBe('')
    expect(draft.confirmPassword).toBe('')
    expect(draft.email).toBe('patient@example.test')
  })

  it('retains the draft for a safe retry when registration is rejected', async () => {
    const draft = fillAccountStep()
    draft.enterProfileStep()
    draft.decideHealthDataProcessing(true, 'fixture-health-v1')
    draft.setBirthYear(1990)
    const registration = new RegistrationService({ register: async () => { throw new Error('fixture request rejected') } } as never, draft)
    await expect(registration.complete()).rejects.toThrow('fixture request rejected')
    expect(draft.password).toBe('fixture-password-only')
    expect(draft.confirmPassword).toBe('fixture-password-only')
  })
})
