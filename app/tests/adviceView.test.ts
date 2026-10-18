import { describe, expect, it } from 'vitest'
import { adviceEvidenceCanNavigate, adviceEvidenceLabel, knowledgeCitationHost, riskPriorityStatusLabel } from '../src/api/adviceView'
import type { AdviceEvidence, RiskPriorityContext } from '../src/api/openapiTypes'

const patientEvidence: AdviceEvidence = {
  evidence_type: 'patient', source_type: 'mood_record', source_id: '00000000-0000-4000-8000-000000000001',
  source_version: 2, locator: 'mood_record:00000000-0000-4000-8000-000000000001', source_deleted: false,
  target: { type: 'mood_record', id: '00000000-0000-4000-8000-000000000001' },
}

describe('advice display safety helpers', () => {
  it('allows only exact supported live source locators and never returns raw locators', () => {
    expect(adviceEvidenceLabel(patientEvidence)).toBe('心情记录 · 已验证来源')
    expect(adviceEvidenceCanNavigate(patientEvidence)).toBe(true)
    for (const value of [
      { ...patientEvidence, source_deleted: true },
      { ...patientEvidence, source_type: 'unknown' as never },
      { ...patientEvidence, locator: 'mood_record:https://example.org/private' },
      { ...patientEvidence, locator: 'mood_record:00000000-0000-4000-8000-000000000002' },
      { ...patientEvidence, target: null },
      { ...patientEvidence, target: { type: 'diet_record', id: patientEvidence.source_id } },
    ]) {
      expect(adviceEvidenceLabel(value)).toBeNull()
      expect(adviceEvidenceCanNavigate(value)).toBe(false)
    }
  })

  it('shows only validated HTTPS citation hostname and preserves non-safety status wording', () => {
    const knowledge: AdviceEvidence = { evidence_type: 'knowledge', knowledge_ref: 'kb:guide', knowledge_version: 'v1', title: 'Guide', publisher: 'Publisher', citation_url: 'https://knowledge.example.org/path?token=private' }
    expect(knowledgeCitationHost(knowledge)).toBe('knowledge.example.org')
    expect(knowledgeCitationHost({ ...knowledge, citation_url: 'https://user:secret@knowledge.example.org/private' })).toBeNull()
    expect(knowledgeCitationHost({ ...knowledge, citation_url: 'javascript:alert(1)' })).toBeNull()
    const context: RiskPriorityContext = { alert_id: patientEvidence.source_id, severity: 'emergency', status: 'reevaluated', triggered_at: '2026-10-01T00:00:00Z' }
    expect(riskPriorityStatusLabel(context)).toContain('不代表风险解除或安全')
  })
})
