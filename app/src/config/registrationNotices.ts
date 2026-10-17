import artifact from '../../../contracts/consent/registration-notices.json'

export type RegistrationConsentType = 'privacy_policy' | 'health_data_processing'

export function registrationNotice(type: RegistrationConsentType): { policyVersion: string; summary: string } {
  if (import.meta.env.PROD && !isProductionApprovedArtifact()) {
    throw new Error('正式注册告知制品尚未配置。')
  }
  const notice = artifact.notices.find((entry) => entry.consent_type === type)
  if (!notice || !notice.policy_version || !notice.summary) throw new Error('注册告知制品无效。')
  return { policyVersion: notice.policy_version, summary: notice.summary }
}

function isProductionApprovedArtifact(): boolean {
  return artifact.artifact_classification === 'production_approved'
    && artifact.legal_approval_status === 'approved'
}
