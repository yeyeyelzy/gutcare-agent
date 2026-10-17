import type { RequestClient } from './requestClient'
import type { PatientProfile, PatientProfilePatch } from './openapiTypes'

export class ProfileApi {
  constructor(private readonly client: RequestClient) {}

  getMyProfile(): Promise<PatientProfile> {
    return this.client.request<PatientProfile>({ method: 'GET', path: '/patients/me' })
  }

  updateMyProfile(request: PatientProfilePatch): Promise<PatientProfile> {
    return this.client.request<PatientProfile>({ method: 'PATCH', path: '/patients/me', data: request })
  }
}
