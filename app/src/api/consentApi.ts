import type { ConsentDecision, ConsentNotice, ConsentStatus } from './openapiTypes'
import type { RequestClient } from './requestClient'

export type ManagedConsentType = 'health_data_processing' | 'mood_data_processing' | 'mood_ai_sharing' | 'third_party_ai'

export class ConsentApi {
  constructor(private readonly client: RequestClient) {}

  list(): Promise<ConsentStatus[]> {
    return this.client.request<ConsentStatus[]>({ method: 'GET', path: '/patients/me/consents' })
  }

  notice(consentType: ManagedConsentType): Promise<ConsentNotice> {
    const query = new URLSearchParams({ consent_type: consentType })
    return this.client.request<ConsentNotice>({ method: 'GET', path: `/consent-notices?${query.toString()}` })
  }

  decide(decision: ConsentDecision): Promise<ConsentDecision> {
    return this.client.request<ConsentDecision>({ method: 'POST', path: '/patients/me/consents', data: decision })
  }
}
