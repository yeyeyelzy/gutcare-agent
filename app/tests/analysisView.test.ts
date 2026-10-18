import { describe, expect, it } from 'vitest'
import { AnalysisFirstShowGate, analysisEvidenceCanNavigate, analysisEvidenceLocatorLabel, analysisErrorLabel, analysisTaskActions, appendAnalysisPage, buildAnalysisRequest, failAnalysisAppend, isAnalysisResponseCurrent } from '../src/api/analysisView'
import type { AnalysisResultEvidence, AnalysisTask } from '../src/api/openapiTypes'

function task(id: string): AnalysisTask {
  return { id, analysis_type: 'comprehensive_health_analysis', status: 'pending', input_summary: { included_mood_record_count: 0 }, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z', attempt: 1, retry_of: null, result: null, error_code: null }
}

describe('F08 APP analysis views', () => {
  it('allows no range only for comprehensive analysis and enforces explicit periodic UTC half-open range', () => {
    expect(buildAnalysisRequest('comprehensive_health_analysis', '', '', 'Asia/Shanghai')).toEqual({ body: { analysis_type: 'comprehensive_health_analysis', requested_from: null, requested_to: null }, error: null })
    expect(buildAnalysisRequest('periodic_summary', '', '', 'Asia/Shanghai').error).toContain('需要明确')
    expect(buildAnalysisRequest('comprehensive_health_analysis', '2026-10-01', '', 'Asia/Shanghai').error).toContain('同时')
    const range = buildAnalysisRequest('periodic_summary', '2026-10-01', '2026-10-08', 'Asia/Shanghai')
    expect(range.error).toBeNull()
    expect(range.body.requested_from).toBe('2026-09-30T16:00:00.000Z')
    expect(range.body.requested_to).toBe('2026-10-07T16:00:00.000Z')
  })

  it('keeps append failures recoverable and deduplicates stable IDs without discarding old cursor/items', () => {
    const initial = { items: [task('00000000-0000-4000-8000-000000000001')], cursor: 'cursor-1', error: '', requestId: '' }
    const failed = failAnalysisAppend(initial, 'offline', 'request-1')
    expect(failed.items).toEqual(initial.items)
    expect(failed.cursor).toBe('cursor-1')
    const recovered = appendAnalysisPage(failed, { items: [initial.items[0]!, task('00000000-0000-4000-8000-000000000002')], next_cursor: null })
    expect(recovered.items.map((item) => item.id)).toEqual(['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002'])
    expect(recovered.error).toBe('')
    expect(recovered.cursor).toBeNull()
  })

  it('deduplicates initial onShow and rejects stale or hidden responses', () => {
    const gate = new AnalysisFirstShowGate()
    expect(gate.shouldRefresh()).toBe(false)
    expect(gate.shouldRefresh()).toBe(true)
    expect(isAnalysisResponseCurrent(3, 3, true, true)).toBe(true)
    expect(isAnalysisResponseCurrent(3, 4, true, true)).toBe(false)
    expect(isAnalysisResponseCurrent(3, 3, false, true)).toBe(false)
    expect(isAnalysisResponseCurrent(3, 3, true, false)).toBe(false)
  })

  it('exposes only status-allowed actions and polls only nonterminal task states', () => {
    expect(analysisTaskActions('pending')).toEqual({ canCancel: true, canRetry: false, needsNewTask: false, shouldPoll: true })
    expect(analysisTaskActions('processing')).toEqual({ canCancel: true, canRetry: false, needsNewTask: false, shouldPoll: true })
    expect(analysisTaskActions('failed')).toEqual({ canCancel: false, canRetry: true, needsNewTask: false, shouldPoll: false })
    for (const status of ['needs_input', 'succeeded', 'partial', 'cancelled'] as const) {
      expect(analysisTaskActions(status)).toEqual({ canCancel: false, canRetry: false, needsNewTask: status === 'needs_input', shouldPoll: false })
    }
  })

  it('shows only controlled locators for supported, matching, non-deleted evidence', () => {
    const evidence: AnalysisResultEvidence = { source_type: 'diet_record', source_id: '00000000-0000-4000-8000-000000000001', source_version: 2, locator: 'diet_record:00000000-0000-4000-8000-000000000001', source_deleted: false }
    expect(analysisEvidenceCanNavigate(evidence)).toBe(true)
    expect(analysisEvidenceLocatorLabel(evidence)).toBe('饮食记录 · 已验证来源定位')
    expect(analysisEvidenceLocatorLabel({ ...evidence, source_deleted: true })).toBeNull()
    expect(analysisEvidenceCanNavigate({ ...evidence, source_deleted: true })).toBe(false)
    expect(analysisEvidenceLocatorLabel({ ...evidence, source_type: 'unrecognized' } as unknown as AnalysisResultEvidence)).toBeNull()
    expect(analysisEvidenceLocatorLabel({ ...evidence, source_type: 'medical_fact_conflict' } as unknown as AnalysisResultEvidence)).toBeNull()
    for (const locator of [null, 'diet_record:/tmp/private', 'https://private.example/object', 'diet_record:00000000-0000-4000-8000-000000000099']) {
      expect(analysisEvidenceLocatorLabel({ ...evidence, locator })).toBeNull()
      expect(analysisEvidenceCanNavigate({ ...evidence, locator })).toBe(false)
    }
    expect(analysisErrorLabel('INTERNAL_AGENT_TRACE_123')).not.toContain('INTERNAL_AGENT_TRACE_123')
    expect(analysisErrorLabel('INTERNAL_AGENT_TRACE_123')).toBe(analysisErrorLabel('ANALYSIS_PROCESSING_FAILED'))
  })
})
