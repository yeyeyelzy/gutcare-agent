import { describe, expect, it, vi } from 'vitest'
import { MedicalFactConflictsApi } from '../src/api/medicalFactConflictsApi'
import type { RequestClient } from '../src/api/requestClient'
import type { MedicalFactConflict } from '../src/api/openapiTypes'
import { canKeepBoth, conflictDocumentIdLabel, conflictFieldLabel, conflictMemberValueLabel, conflictStatusLabel, conflictSampledOnLabel } from '../src/api/medicalFactConflictView'

const conflict: MedicalFactConflict = {
  id: '00000000-0000-4000-8000-000000000001', status: 'open', record_version: 4, created_at: '2026-10-18T01:00:00Z', resolution: null,
  members: [
    { fact_id: '00000000-0000-4000-8000-000000000002', source_document_id: '00000000-0000-4000-8000-000000000003', field_code: 'test_item', value: '血红蛋白', unit: null, sampled_on: '2026-10-01' },
    { fact_id: '00000000-0000-4000-8000-000000000004', source_document_id: '00000000-0000-4000-8000-000000000005', field_code: 'test_result', value: { result: '5.2', prompt: 'not rendered' }, unit: 'g/L', sampled_on: '2026-10-01' },
  ],
}
const [itemMember, resultMember] = conflict.members!

describe('F02c medical fact conflict API and view helpers', () => {
  it('uses the three generated operations and keeps resolution version and idempotency explicit', async () => {
    const request = vi.fn().mockResolvedValue([])
    const api = new MedicalFactConflictsApi({ request } as unknown as RequestClient)
    await api.list()
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medical-fact-conflicts?status=open' })
    await api.list('invalidated')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medical-fact-conflicts?status=invalidated' })
    await api.get('conflict/id')
    expect(request).toHaveBeenLastCalledWith({ method: 'GET', path: '/medical-fact-conflicts/conflict%2Fid' })
    const body = { record_version: 4 }
    await api.keepBoth('conflict/id', body, 'keep-both-key-001')
    expect(request).toHaveBeenLastCalledWith({ method: 'POST', path: '/medical-fact-conflicts/conflict%2Fid/resolve', data: body, idempotencyKey: 'keep-both-key-001' })
  })

  it('renders only controlled fact fields and values and enables keep_both only for open groups', () => {
    expect(conflictStatusLabel('open')).toBe('待本人核对')
    expect(conflictFieldLabel(itemMember!.field_code)).toBe('检验项目')
    expect(conflictMemberValueLabel(itemMember!)).toBe('血红蛋白')
    expect(conflictMemberValueLabel(resultMember!)).toBe('5.2')
    expect(conflictMemberValueLabel({ ...resultMember!, value: { result: { raw: 'secret' }, report: 'hidden' } })).toBe('字段内容暂不可显示')
    expect(conflictSampledOnLabel('2026-10-01')).toBe('2026-10-01')
    expect(conflictSampledOnLabel('bad-date')).toBe('采样日期未记录')
    expect(conflictDocumentIdLabel(itemMember!.source_document_id)).toBe(itemMember!.source_document_id)
    expect(conflictDocumentIdLabel('https://bucket.invalid/file')).toBe('来源档案不可用')
    expect(canKeepBoth(conflict)).toBe(true)
    expect(canKeepBoth({ ...conflict, status: 'resolved' })).toBe(false)
    expect(canKeepBoth({ ...conflict, members: [itemMember!] })).toBe(false)
  })
})
