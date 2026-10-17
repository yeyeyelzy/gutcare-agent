import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const confirm = readFileSync(new URL('../src/pages/privacy/deletion-confirm.vue', import.meta.url), 'utf8')
const progress = readFileSync(new URL('../src/pages/privacy/deletion-progress.vue', import.meta.url), 'utf8')
const center = readFileSync(new URL('../src/pages/privacy/center.vue', import.meta.url), 'utf8')

describe('F13 account deletion UI contract', () => {
  it('requires explicit high-risk acknowledgement, is single-flight and does not offer cancellation', () => {
    expect(confirm).toContain('我理解注销不可取消，并确认提交注销请求')
    expect(confirm).toContain(':disabled="!confirmed || busy"')
    expect(confirm).toContain('if (!deletion || !confirmed.value || busy.value) return')
    expect(confirm).toContain('await deletion.requestAccountDeletion()')
    expect(confirm).not.toContain('cancelDeletion')
    expect(confirm).toContain('router?.requireAuthentication(\'accountDeletionConfirm\')')
    expect(center).toContain('router?.navigate(\'accountDeletionConfirm\')')
  })

  it('shows first receipt once, distinguishes null/unavailable and save failure, clears it when page hides', () => {
    expect(progress).toContain('data-testid="deletion-receipt-once"')
    expect(progress).toContain('data-testid="deletion-receipt-unavailable"')
    expect(progress).toContain('receiptStorage === \'memory_only\'')
    expect(progress).toContain('onHide(clearSensitivePageState)')
    expect(progress).toContain('onUnload(clearSensitivePageState)')
    expect(progress).toContain('系统无法恢复或重新显示一次性凭证')
    expect(progress).toContain('data-testid="deletion-receipt-save-warning"')
    expect(progress).not.toContain('selectable')
    expect(progress).not.toContain('clipboard')
    expect(progress).not.toMatch(/(?:navigate|reLaunch|redirectTo)\([^)]*(?:operationId|receipt)/)
  })

  it('clears all page-local sensitive state on hide/unload and prevents late async response refill', () => {
    const clear = progress.slice(progress.indexOf('function clearSensitivePageState()'), progress.indexOf('async function initialize('))
    for (const reset of [
      "acceptedOperationId.value = ''", "operationId.value = ''", "receipt.value = ''",
      'receiptToReveal.value = null', 'savedRecord.value = null', 'status.value = null',
      'statusError.value = null', 'queryStorageWarning.value = \'\'',
      'clearInFlightManualSecrets?.()', 'pageGeneration += 1',
    ]) expect(clear).toContain(reset)
    const query = progress.slice(progress.indexOf('async function runQuery('))
    expect(query).toContain('if (!isCurrentPage(generation)) return')
    expect(query).toContain('if (isCurrentPage(generation)) statusError.value = error')
    expect(progress).toContain('if (clearInFlightManualSecrets === clearSecrets) clearInFlightManualSecrets = null')
    expect(progress).toContain('onShow(() => {')
    expect(progress).toContain('const record = await deletion.loadSavedRecord()')
    expect(progress).toContain('if (!isCurrentPage(generation)) return\n  savedRecord.value = record')
    expect(progress).not.toContain('receiptToReveal.value = record.receipt')
  })

  it('supports manual receipt query and presents all server states without interpreting them as completion', () => {
    for (const value of ['pending', 'processing', 'overdue', 'dead_letter', 'completed']) expect(progress).toContain(`${value}:`)
    expect(progress).toContain('receipt.value = \'\'')
    expect(progress).toContain('deletion.queryManualStatus(id, token)')
    expect(progress).toContain('statusError.value.status === 404')
    expect(progress).toContain('statusError.value.status === 429')
    expect(progress).toContain('当前无法连接服务')
    expect(progress).toContain('该请求需要支持团队协助')
    expect(progress).toContain('服务端已确认注销流程完成')
  })
})
