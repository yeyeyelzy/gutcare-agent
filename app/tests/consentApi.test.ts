import { describe, expect, it, vi } from 'vitest'
import { ConsentApi } from '../src/api/consentApi'
import type { RequestClient } from '../src/api/requestClient'

describe('ConsentApi', () => {
  it('loads own consent status and server notice by exact consent type', async () => {
    const request = vi.fn().mockResolvedValue([])
    const api = new ConsentApi({ request } as unknown as RequestClient)
    await api.list()
    expect(request).toHaveBeenCalledWith({ method: 'GET', path: '/patients/me/consents' })
    await api.notice('mood_data_processing')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/consent-notices?consent_type=mood_data_processing' })
  })

  it('posts only the selected independent decision and policy version', async () => {
    const request = vi.fn().mockResolvedValue({})
    const api = new ConsentApi({ request } as unknown as RequestClient)
    const decision = { consent_type: 'mood_ai_sharing', policy_version: 'test-only-mood-ai-v1', granted: false } as const
    await api.decide(decision)
    expect(request).toHaveBeenCalledWith({ method: 'POST', path: '/patients/me/consents', data: decision })
  })
})
