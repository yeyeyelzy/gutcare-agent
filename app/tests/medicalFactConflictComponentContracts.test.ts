import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const workspace = readFileSync(new URL('../src/components/MedicalFactConflictWorkspace.vue', import.meta.url), 'utf8')
const archive = readFileSync(new URL('../src/components/MedicalArchiveWorkspace.vue', import.meta.url), 'utf8')
const generator = readFileSync(new URL('../scripts/openapi-types.mjs', import.meta.url), 'utf8')
const dto = readFileSync(new URL('../src/api/generated/openapi.ts', import.meta.url), 'utf8')

describe('F02c conflict inbox/detail contracts', () => {
  it('uses generated API operations without pagination or client-side reordering', () => {
    for (const operation of ['listMedicalFactConflicts', 'getMedicalFactConflict', 'resolveMedicalFactConflict']) expect(generator).toContain(`'${operation}'`)
    expect(dto).toContain('listMedicalFactConflicts:')
    expect(dto).toContain('getMedicalFactConflict:')
    expect(dto).toContain('resolveMedicalFactConflict:')
    expect(workspace).toContain('items.value = result')
    expect(workspace).toContain('Preserve the exact service ordering')
    expect(workspace).not.toMatch(/\.sort\(|cursor|next_cursor|loadMore/)
    expect(workspace).toContain("value: 'open', label: '待核对'")
    expect(workspace).toContain("value: 'resolved', label: '已处理'")
    expect(workspace).toContain("value: 'invalidated', label: '来源失效'")
    expect(workspace).toContain("value: 'all', label: '全部'")
  })

  it('offers only explicit keep_both for open conflicts and refreshes 409 without resubmitting', () => {
    expect(workspace).toContain("detail.status === 'open'")
    expect(workspace).toContain('uni.showModal')
    expect(workspace).toContain("{ record_version: detail.value.record_version }")
    expect(workspace).toContain('createIdempotencyKey()')
    expect(workspace).toContain('await refreshDetailAfterConflict(current)')
    const conflictRefresh = workspace.slice(workspace.indexOf('async function refreshDetailAfterConflict'), workspace.indexOf('async function refreshDetailAfterAction'))
    expect(conflictRefresh).toContain('await api.get(conflictId.value)')
    expect(conflictRefresh).not.toContain('keepBoth(')
    expect(workspace).toContain('双方将作为独立事实保留')
    expect(workspace).toContain('双方为独立事实')
    expect(workspace).toContain("detail.status === 'open'")
  })

  it('is protected, uses fixed source-document navigation, and never renders report excerpts or agent output', () => {
    expect(workspace).toContain('canRenderRoute(routeName.value, auth.state)')
    expect(workspace).toContain('router?.requireAuthentication(routeName.value)')
    expect(workspace).toContain('router?.navigateMedicalDocumentDetail(member.source_document_id)')
    expect(workspace).toContain('generation++')
    expect(workspace).toContain('if (!isCurrent(current)) return')
    expect(workspace).not.toMatch(/excerpt|report_body|agent_output|storage_url|bucket|object_key|v-html/)
    expect(archive).toContain('medical-fact-conflicts-open')
    expect(archive).toContain("navigate('medicalFactConflicts')")
  })
})
