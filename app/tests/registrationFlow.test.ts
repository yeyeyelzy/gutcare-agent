import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { RegistrationService } from '../src/api/registrationService'
import { useRegistrationDraftStore } from '../src/stores/registrationDraft'
import { AppRouter } from '../src/navigation/router'
import type { AuthState } from '../src/stores/auth'

function fillCompleteDraft() {
  const draft = useRegistrationDraftStore()
  draft.saveAccountStep({
    email: 'patient@example.test', password: 'fixture-password-only', confirmPassword: 'fixture-password-only',
    privacyPolicyAccepted: true, privacyPolicyVersion: 'fixture-privacy-v1',
  })
  draft.enterProfileStep()
  draft.decideHealthDataProcessing(true, 'fixture-health-v1')
  draft.setBirthYear(1990)
  return draft
}

function makeRouter(draft: ReturnType<typeof useRegistrationDraftStore>) {
  const navigator = { navigateTo: vi.fn(), redirectTo: vi.fn(), reLaunch: vi.fn(), navigateBack: vi.fn() }
  const router = new AppRouter(navigator, () => 'anonymous' as AuthState, undefined, () => draft.cancelWorkflow())
  return { router, navigator }
}

describe('registration page transition and cleanup policy', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('returns from page 17 to page 22 with draft intact and can continue successfully', async () => {
    const draft = fillCompleteDraft()
    const { router, navigator } = makeRouter(draft)

    router.navigateBack()
    expect(navigator.navigateBack).toHaveBeenCalledOnce()
    expect(draft.password).toBe('fixture-password-only')
    expect(draft.confirmPassword).toBe('fixture-password-only')
    expect(draft.birthYear).toBe(1990)

    expect(router.navigate('registerProfile')).toBe(true)
    expect(draft.password).toBe('fixture-password-only')
    const registration = new RegistrationService({
      register: vi.fn(async () => ({ operation_id: 'fixture-operation-id', status: 'accepted' as const })),
    } as never, draft)
    await registration.complete()
    expect(draft.password).toBe('')
    expect(draft.confirmPassword).toBe('')
    expect(draft.email).toBe('patient@example.test')
    expect(router.reLaunch('emailVerification')).toBe(true)
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/email-verification')
  })

  it('clears all draft fields when the user explicitly cancels registration', () => {
    const draft = fillCompleteDraft()
    const { router, navigator } = makeRouter(draft)
    draft.cancelWorkflow()
    router.reLaunch('login')
    expect(draft.password).toBe('')
    expect(draft.confirmPassword).toBe('')
    expect(draft.email).toBe('')
    expect(navigator.reLaunch).toHaveBeenCalledWith('/pages/auth/login')
  })

  it('clears the draft when navigating from registration to a non-registration public route', () => {
    const draft = fillCompleteDraft()
    const { router } = makeRouter(draft)
    expect(router.navigate('login')).toBe(true)
    expect(draft.password).toBe('')
    expect(draft.confirmPassword).toBe('')
    expect(draft.email).toBe('')
  })
})
