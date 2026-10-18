import { describe, expect, it } from 'vitest'
import type { MedicalDocument, MedicalFieldCandidate } from '../src/api/openapiTypes'
import { candidateDecisionValueLabel, candidateFieldLabel, candidateLocatorLabel, candidateStatusLabel, candidateValueLabel, correctedCandidateValue, excerptForOnDemandDisplay, parseOutcomeLabel, parseReasonLabel, safeCandidateForDisplay } from '../src/api/medicalCandidateReview'

const baseCandidate: MedicalFieldCandidate = {
  id: 'candidate-1', field_code: 'diagnosis', value_type: 'diagnosis', value: { text: '肠易激综合征', certainty: 'suspected' }, unit: null,
  confidence: 0.81, uncertainty: null, source_locator: { page: 2 } as unknown as MedicalFieldCandidate['source_locator'], excerpt: '患者报告腹痛。',
  review_status: 'pending', record_version: 7, chosen_value: null,
}
const baseDocument = {
  parse_status: 'needs_confirmation', parse_outcome: 'extracted', parse_reason_code: null,
} as MedicalDocument

describe('F02b medical candidate review helpers', () => {
  it('distinguishes parse outcomes from technical failure and keeps reason codes controlled', () => {
    expect(parseOutcomeLabel(baseDocument)).toContain('等待本人逐项核对')
    expect(parseOutcomeLabel({ ...baseDocument, parse_status: 'failed' })).toBe('解析任务未完成')
    expect(parseOutcomeLabel({ ...baseDocument, parse_outcome: 'no_supported_facts' })).toBe('未发现可支持的字段')
    expect(parseOutcomeLabel({ ...baseDocument, parse_outcome: 'insufficient_quality' })).toContain('质量不足')
    expect(parseReasonLabel({ ...baseDocument, parse_reason_code: 'low_quality_scan' })).toBe('扫描质量不足')
  })

  it('shows only controlled candidate values and locator labels', () => {
    expect(candidateFieldLabel(baseCandidate)).toBe('诊断记录')
    expect(candidateStatusLabel('invalidated')).toBe('来源已失效')
    expect(candidateValueLabel(baseCandidate)).toContain('疑似记录')
    expect(candidateDecisionValueLabel({ ...baseCandidate, review_status: 'corrected', chosen_value: { text: '更正后诊断', certainty: 'suspected' } })).toContain('更正后诊断')
    expect(candidateLocatorLabel({ page: 3, char_start: 5, char_end: 9, arbitrary_url: 'https://secret.invalid' })).toBe('第 3 页 · 来源文本位置')
    expect(candidateLocatorLabel({ arbitrary_url: 'https://secret.invalid' })).toBeNull()
    expect(candidateLocatorLabel({ page: 0, char_start: 5, char_end: 2 })).toBeNull()
  })

  it('preserves certainty when correcting diagnosis and requires typed correction values', () => {
    expect(correctedCandidateValue(baseCandidate, '更正诊断')) .toEqual({ text: '更正诊断', certainty: 'suspected' })
    expect(() => correctedCandidateValue({ ...baseCandidate, value_type: 'date', value: '2026-01-01' }, '2026-02-30')).toThrow('有效日期')
    expect(correctedCandidateValue({ ...baseCandidate, field_code: 'test_result', value_type: 'object', value: { result: '3.2' } }, '{"result":"3.1"}')).toEqual({ result: '3.1' })
    expect(() => correctedCandidateValue({ ...baseCandidate, value_type: 'object', value: {} }, '<img onerror=1>')).toThrow('有效 JSON')
  })

  it('removes excerpt and locator for invalidated candidates and truncates on-demand excerpt', () => {
    const invalidated = safeCandidateForDisplay({ ...baseCandidate, review_status: 'invalidated' })
    expect(invalidated.excerpt).toBeNull()
    expect(invalidated.source_locator).toBeNull()
    expect(excerptForOnDemandDisplay(invalidated)).toBeNull()
    expect(excerptForOnDemandDisplay(baseCandidate)).toBe('患者报告腹痛。')
    expect(excerptForOnDemandDisplay({ ...baseCandidate, excerpt: 'x'.repeat(400) })).toHaveLength(240)
  })
})
