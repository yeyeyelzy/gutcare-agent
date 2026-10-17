import { describe, expect, it } from 'vitest'
import { AnalysisFirstShowGate, appendAnalysisPage, buildAnalysisRequest, failAnalysisAppend, isAnalysisResponseCurrent } from '../src/api/analysisView'
import type { AnalysisTask } from '../src/api/openapiTypes'

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
})
