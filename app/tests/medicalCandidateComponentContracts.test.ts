import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const api = readFileSync(new URL('../src/api/medicalDocumentsApi.ts', import.meta.url), 'utf8')
const workspace = readFileSync(new URL('../src/components/MedicalArchiveWorkspace.vue', import.meta.url), 'utf8')
const review = readFileSync(new URL('../src/components/MedicalCandidateReview.vue', import.meta.url), 'utf8')
const helper = readFileSync(new URL('../src/api/medicalCandidateReview.ts', import.meta.url), 'utf8')

describe('F02b candidate review UI and lifecycle contracts', () => {
  it('uses generated candidate DTOs, per-field decisions, record versions, and an independent idempotency key', () => {
    expect(api).toContain('Promise<MedicalFieldCandidate[]>')
    expect(api).toContain("path: `/medical-documents/${encodeURIComponent(documentId)}/candidates`")
    expect(api).toContain("path: `/medical-field-candidates/${encodeURIComponent(candidateId)}/decision`")
    expect(api).toContain('data: body, idempotencyKey')
    expect(workspace).toContain('record_version: candidate.record_version')
    expect(workspace).toContain('createIdempotencyKey()')
    expect(review).toContain("candidate.review_status === 'pending'")
    expect(review).toContain("emit('decide', candidate, 'accept', candidate.value)")
    expect(review).toContain("emit('decide', candidate, 'reject', null)")
    expect(review).toContain("emit('decide', candidate, 'correct', value)")
    expect(review).not.toMatch(/confirmAll|batch|批量确认|自动确认/)
  })

  it('handles 409 by retaining the current review surface, fetching latest state, and never auto-resubmitting', () => {
    const conflict = workspace.indexOf("error.status === 409")
    const reload = workspace.indexOf('await reloadAfterCandidateConflict(generation)', conflict)
    expect(conflict).toBeGreaterThanOrEqual(0)
    expect(reload).toBeGreaterThan(conflict)
    expect(workspace).toContain('候选已发生变化；当前决定未自动重发')
    const reloadBody = workspace.slice(workspace.indexOf('async function reloadAfterCandidateConflict'), workspace.indexOf('function shouldLoadCandidates'))
    expect(reloadBody).toContain('await api.get(document.value.id)')
    expect(reloadBody).toContain('await api.listCandidates(currentDocument.id)')
    expect(reloadBody).not.toContain('decideCandidate(')
    expect(reloadBody).not.toContain('api.decideCandidate')
  })

  it('clears protected candidate evidence on hide/unload and treats inaccessible resources uniformly', () => {
    expect(workspace).toMatch(/onHide\(\(\) => \{[\s\S]*?candidates\.value = \[\]/)
    expect(workspace).toMatch(/onUnload\(\(\) => \{[\s\S]*?candidates\.value = \[\]/)
    expect(workspace).toContain('function clearSensitiveDetail()')
    expect(workspace).toContain("if (isNotFound(error))")
    expect(workspace).toContain("'档案或候选不存在或当前不可用。'")
    expect(helper).toContain("candidate.review_status === 'invalidated'")
    expect(review).toContain('excerptForOnDemandDisplay(candidate)')
    expect(review).not.toMatch(/v-html|router\.navigate.*candidate|console\.(log|info|warn|error)/)
    expect(workspace).not.toMatch(/localStorage|uni\.setStorage|console\.(log|info|warn|error)/)
  })

  it('renders controlled outcome and technical failure distinctions in the protected detail', () => {
    expect(workspace).toContain('data-testid="medical-document-parse-outcome"')
    expect(workspace).toContain('getParseOutcomeLabel')
    expect(workspace).toContain('getParseReasonLabel')
    expect(helper).toContain("document.parse_status === 'failed'")
    expect(helper).toContain("document.parse_outcome === 'no_supported_facts'")
    expect(helper).toContain("document.parse_outcome === 'insufficient_quality'")
  })
})
