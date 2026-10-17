import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { canRenderRoute } from '../src/navigation/routes'

const page = readFileSync(new URL('../src/components/PrivacyExportWorkspace.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/privacyExportApi.ts', import.meta.url), 'utf8')
const adapter = readFileSync(new URL('../src/api/privacyExportDownload.ts', import.meta.url), 'utf8')
const routes = readFileSync(new URL('../src/navigation/routes.ts', import.meta.url), 'utf8')

describe('F13 P1 APP export workflow contract', () => {
  it('gates protected history and supports category selection, preview, explicit confirm and lifecycle states', () => {
    expect(page).toContain("canRenderRoute('privacyExports', auth.state)")
    expect(page).toContain("router?.requireAuthentication('privacyExports')")
    for (const call of ['api.createPreview(', 'api.confirm(', 'api.list()', 'api.get(', 'api.cancel(']) expect(page).toContain(call)
    for (const state of ['preview', 'pending', 'processing', 'ready', 'failed', 'cancelled', 'expired']) expect(page).toContain(`${state}:`)
    for (const id of ['export-create-preview', 'export-preview', 'export-confirm', 'export-history-', 'export-detail', 'export-cancel', 'export-list-error', 'export-list-retry', 'export-empty', 'export-loading']) expect(page).toContain(id)
    expect(page).toContain("selected.has('mood')")
    expect(page).toContain('S4 敏感信息')
    expect(page).toContain('不会启动导出')
    const confirmHandler = page.slice(page.indexOf('async function confirmPreview()'), page.indexOf('async function confirmDetail()'))
    expect(confirmHandler).toContain('await api.confirm(id)')
    expect(confirmHandler).toContain('catch (error) { if (isCurrentPage(current)) actionError.value = message(error) }')
    expect(confirmHandler).not.toContain('await api.confirm(id)\n    await api.confirm(id)')
    const previewHandler = page.slice(page.indexOf('async function createPreview()'), page.indexOf('async function confirmPreview()'))
    expect(previewHandler).toContain('api.createPreview(')
    expect(previewHandler).not.toContain('api.confirm(')
    expect(page).toContain('canConfirmPrivacyExport(detail.status)')
    expect(page).toContain('canCancel(detail.status)')
    expect(page).toContain("router?.redirect('privacyCenter')")
    expect(page).not.toContain('patient_id')
    expect(page).not.toMatch(/console\.(log|info|warn|error)/)
  })

  it('does not persist, expose, URL-encode or copy capability; clears the view when hidden', () => {
    expect(adapter).toContain("'X-Export-Capability': capability")
    expect(adapter).toContain('/privacy/exports/download')
    expect(adapter).toContain('removeTemporaryFile')
    expect(adapter).not.toMatch(/uni\.(setStorage|saveFile)|clipboard|analytics|console\./i)
    expect(page).toContain('onHide(clearTransientState)')
    expect(page).toContain('onUnload(clearTransientState)')
    expect(page).toContain('detail.value = null')
    const detailLoader = page.slice(page.indexOf('async function openDetail('), page.indexOf('function clearTransientState()'))
    expect(detailLoader).toContain('const request = ++detailGeneration')
    expect(detailLoader).toContain('isCurrentPage(current) && request === detailGeneration')
    expect(detailLoader.indexOf('isCurrentPage(current) && request === detailGeneration) replaceDetail(result)')).toBeGreaterThan(detailLoader.indexOf('await api.get(id)'))
    expect(page).toContain('detailGeneration++')
    expect(page).toContain('当前版本暂不支持将 ZIP 保存或分享至应用外')
    expect(page).toContain('downloadAdapter?.clearPageState()')
    expect(page).not.toMatch(/clipboard|analytics|console\./i)
    const template = page.slice(0, page.indexOf('<script setup'))
    expect(template).not.toContain('download_capability')
    expect(routes).toContain("privacyExports: { path: '/pages/privacy/exports', access: 'authenticated'")
    expect(canRenderRoute('privacyExports', 'anonymous')).toBe(false)
    expect(canRenderRoute('privacyExports', 'authenticated')).toBe(true)
  })

  it('keeps every recoverable error region unique and keeps failed refreshes from replacing history', () => {
    for (const id of ['export-create-error', 'export-action-error', 'export-list-error', 'export-detail-error']) {
      expect(page.split(`data-testid="${id}"`).length - 1).toBe(1)
    }
    const refresh = page.slice(page.indexOf('async function refresh('), page.indexOf('async function createPreview()'))
    expect(refresh).toContain('catch (error)')
    const failure = refresh.slice(refresh.indexOf('catch (error)'))
    expect(failure).not.toContain('exports.value =')
    expect(page).toContain('v-else-if="!loading && !loadError && exports.length === 0"')
    expect(page).toContain('v-if="loadError"')
  })

  it('invalidates every in-flight page action on hide and erases capability before replacement', () => {
    expect(page).toContain('function isCurrentPage(current: number) { return visible && current === generation }')
    const clearDetail = page.slice(page.indexOf('function clearDetail()'), page.indexOf('function replaceDetail('))
    expect(clearDetail.indexOf('detail.value.download_capability = null')).toBeLessThan(clearDetail.indexOf('detail.value = null'))
    const replaceDetail = page.slice(page.indexOf('function replaceDetail('), page.indexOf('async function openDetail('))
    expect(replaceDetail.indexOf('detail.value.download_capability = null')).toBeLessThan(replaceDetail.indexOf('detail.value = value'))
    const hide = page.slice(page.indexOf('function clearTransientState()'), page.indexOf('onShow(() =>'))
    expect(hide).toContain('visible = false')
    expect(hide).toContain('generation++')
    expect(hide).toContain('detailGeneration++')
    expect(hide).toContain('clearDetail()')

    for (const [name, end] of [
      ['confirmPreview', 'async function discardPreview()'],
      ['discardPreview', 'async function confirmDetail()'],
      ['cancelDetail', 'function isCurrentPage('],
    ] as const) {
      const start = page.indexOf(`async function ${name}()`)
      const action = page.slice(start, page.indexOf(end, start))
      expect(action).toContain('const current = generation')
      expect(action).toContain('if (!isCurrentPage(current)) return')
      expect(action).toContain('await api.')
      expect(action).toContain('catch (error) { if (isCurrentPage(current))')
      expect(action).toContain('finally { if (isCurrentPage(current))')
      const firstAwait = action.indexOf('await api.')
      const nextMutation = action.indexOf('if (!isCurrentPage(current)) return', firstAwait)
      expect(nextMutation).toBeGreaterThan(firstAwait)
    }

    const refresh = page.slice(page.indexOf('async function refresh('), page.indexOf('async function createPreview()'))
    expect(refresh).toContain('if (!isCurrentPage(current)) return')
    expect(refresh).toContain('if (isCurrentPage(current)) exports.value = result')
    const openDetail = page.slice(page.indexOf('async function openDetail('), page.indexOf('function clearTransientState()'))
    expect(openDetail).toContain('if (!api || !isCurrentPage(current)) return')
    expect(openDetail).toContain('if (isCurrentPage(current) && request === detailGeneration) replaceDetail(result)')
    expect(openDetail).toContain('else result.download_capability = null')
    expect(openDetail).toContain('if (isCurrentPage(current) && request === detailGeneration) detailError.value = message(error)')

    const confirm = page.slice(page.indexOf('async function confirmPreview()'), page.indexOf('async function discardPreview()'))
    expect(confirm.indexOf('await api.confirm(id)')).toBeLessThan(confirm.indexOf('if (!isCurrentPage(current)) return', confirm.indexOf('await api.confirm(id)')))
    expect(confirm.indexOf('await openDetail(id, current)')).toBeLessThan(confirm.indexOf('if (!isCurrentPage(current)) return', confirm.indexOf('await openDetail(id, current)')))
    expect(confirm.indexOf('await openDetail(id, current)')).toBeLessThan(confirm.indexOf('await refresh(current)'))
    const discard = page.slice(page.indexOf('async function discardPreview()'), page.indexOf('async function confirmDetail()'))
    expect(discard.indexOf('await api.cancel(id)')).toBeLessThan(discard.indexOf('if (!isCurrentPage(current)) return', discard.indexOf('await api.cancel(id)')))
    expect(discard).toContain('await refresh(current)')
    const cancel = page.slice(page.indexOf('async function cancelDetail()'), page.indexOf('function isCurrentPage('))
    expect(cancel.indexOf('await api.cancel(id)')).toBeLessThan(cancel.indexOf('if (!isCurrentPage(current)) return', cancel.indexOf('await api.cancel(id)')))
    expect(cancel.indexOf('await openDetail(id, current)')).toBeLessThan(cancel.indexOf('if (!isCurrentPage(current)) return', cancel.indexOf('await openDetail(id, current)')))
  })
})
