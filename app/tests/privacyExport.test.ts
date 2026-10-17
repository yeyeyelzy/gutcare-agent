import { describe, expect, it, vi } from 'vitest'
import { canCancelPrivacyExport, canConfirmPrivacyExport, PrivacyExportApi, PRIVACY_EXPORT_CATEGORIES, PRIVACY_EXPORT_STATUSES } from '../src/api/privacyExportApi'
import { PrivacyExportDownloadAdapter } from '../src/api/privacyExportDownload'
import type { RequestClient } from '../src/api/requestClient'

describe('F13 privacy export API and temporary download boundary', () => {
  it('uses only the six frozen operations and creates previews without confirming them', async () => {
    const request = vi.fn().mockResolvedValueOnce({ export_id: 'e1', status: 'preview', categories: ['profile'] }).mockResolvedValueOnce([]).mockResolvedValueOnce({ export_id: 'e1' }).mockResolvedValueOnce(undefined).mockResolvedValueOnce(undefined)
    const api = new PrivacyExportApi({ request } as unknown as RequestClient)
    await api.createPreview(['profile', 'profile'])
    await api.list()
    await api.get('e1')
    await api.confirm('e1')
    await api.cancel('e1')
    expect(request.mock.calls.map(([options]) => options)).toEqual([
      { method: 'POST', path: '/privacy/exports', data: { categories: ['profile'] } },
      { method: 'GET', path: '/privacy/exports' },
      { method: 'GET', path: '/privacy/exports/e1' },
      { method: 'POST', path: '/privacy/exports/e1' },
      { method: 'POST', path: '/privacy/exports/e1/cancel' },
    ])
    expect(PRIVACY_EXPORT_CATEGORIES).toHaveLength(14)
    expect(PRIVACY_EXPORT_STATUSES).toEqual(['preview', 'pending', 'processing', 'ready', 'failed', 'cancelled', 'expired'])
    expect(['preview', 'pending', 'processing', 'ready', 'failed', 'cancelled', 'expired'].filter((status) => canCancelPrivacyExport(status as never))).toEqual(['preview', 'pending', 'processing'])
    expect(PRIVACY_EXPORT_STATUSES.filter(canConfirmPrivacyExport)).toEqual(['preview'])
    await expect(api.createPreview([])).rejects.toThrow()
    await expect(api.createPreview(['unknown' as never])).rejects.toThrow()
  })

  it('places the one-time capability only in the fixed same-origin download header', async () => {
    const downloadFile = vi.fn().mockResolvedValue({ filePath: '/sandbox/export.zip', statusCode: 200 })
    const removeTemporaryFile = vi.fn().mockResolvedValue(undefined)
    const adapter = new PrivacyExportDownloadAdapter({ downloadFile, removeTemporaryFile }, 'https://api.example.test/api/v1')
    const capability = 'c'.repeat(64)
    const readyDetail = { status: 'ready' as const, download_capability: capability as string | null }
    await expect(adapter.consumeTemporaryFile(readyDetail, async (path) => { expect(path).toBe('/sandbox/export.zip') })).resolves.toBeUndefined()
    expect(readyDetail.download_capability).toBeNull()
    expect(downloadFile).toHaveBeenCalledWith({
      url: 'https://api.example.test/api/v1/privacy/exports/download',
      header: { 'X-Export-Capability': capability, Accept: 'application/zip' }, timeout: 60_000,
    })
    expect(JSON.stringify(downloadFile.mock.calls)).not.toContain(`?${capability}`)
    await expect(adapter.consumeTemporaryFile(readyDetail, vi.fn())).rejects.toThrow('不可用')
    expect(downloadFile).toHaveBeenCalledOnce()
    expect(removeTemporaryFile).toHaveBeenCalledWith('/sandbox/export.zip')
    await expect(adapter.consumeTemporaryFile({ status: 'ready', download_capability: 'short' }, vi.fn())).rejects.toThrow()
    await expect(adapter.consumeTemporaryFile({ status: 'pending', download_capability: capability }, vi.fn())).rejects.toThrow()

    const networkDetail = { status: 'ready' as const, download_capability: 'n'.repeat(64) as string | null }
    const network = new PrivacyExportDownloadAdapter({
      downloadFile: vi.fn().mockRejectedValue(new Error('offline')),
      removeTemporaryFile: vi.fn(),
    }, 'https://api.example.test/api/v1')
    await expect(network.consumeTemporaryFile(networkDetail, vi.fn())).rejects.toThrow('offline')
    expect(networkDetail.download_capability).toBeNull()

    const expiredCleanup = vi.fn().mockResolvedValue(undefined)
    const expired = new PrivacyExportDownloadAdapter({
      downloadFile: vi.fn().mockResolvedValue({ filePath: '/sandbox/expired.zip', statusCode: 404 }),
      removeTemporaryFile: expiredCleanup,
    }, 'https://api.example.test/api/v1')
    const expiredDetail = { status: 'ready' as const, download_capability: 'x'.repeat(64) as string | null }
    await expect(expired.consumeTemporaryFile(expiredDetail, vi.fn())).rejects.toThrow('刷新导出详情')
    expect(expiredDetail.download_capability).toBeNull()
    expect(expiredCleanup).toHaveBeenCalledWith('/sandbox/expired.zip')

    const failedConsumeCleanup = vi.fn().mockResolvedValue(undefined)
    const failedConsume = new PrivacyExportDownloadAdapter({
      downloadFile: vi.fn().mockResolvedValue({ filePath: '/sandbox/consume-failed.zip', statusCode: 200 }),
      removeTemporaryFile: failedConsumeCleanup,
    }, 'https://api.example.test/api/v1')
    await expect(failedConsume.consumeTemporaryFile({ status: 'ready', download_capability: 'y'.repeat(64) }, async () => { throw new Error('consumer unavailable') })).rejects.toThrow('consumer unavailable')
    expect(failedConsumeCleanup).toHaveBeenCalledWith('/sandbox/consume-failed.zip')

    let resolveDownload!: (value: { filePath: string; statusCode: number }) => void
    const hiddenCleanup = vi.fn().mockResolvedValue(undefined)
    const hidden = new PrivacyExportDownloadAdapter({
      downloadFile: vi.fn(() => new Promise<{ filePath: string; statusCode: number }>((resolve) => { resolveDownload = resolve })),
      removeTemporaryFile: hiddenCleanup,
    }, 'https://api.example.test/api/v1')
    const hiddenDetail = { status: 'ready' as const, download_capability: 'z'.repeat(64) as string | null }
    const inFlight = hidden.consumeTemporaryFile(hiddenDetail, vi.fn())
    await hidden.clearPageState()
    resolveDownload({ filePath: '/sandbox/late.zip', statusCode: 200 })
    await expect(inFlight).rejects.toThrow('页面已离开')
    expect(hiddenCleanup).toHaveBeenCalledWith('/sandbox/late.zip')
    expect(hiddenDetail.download_capability).toBeNull()

    const pageExitCleanup = vi.fn().mockResolvedValue(undefined)
    const pageExit = new PrivacyExportDownloadAdapter({
      downloadFile: vi.fn().mockResolvedValue({ filePath: '/sandbox/page-exit.zip', statusCode: 200 }),
      removeTemporaryFile: pageExitCleanup,
    }, 'https://api.example.test/api/v1')
    await pageExit.consumeTemporaryFile({ status: 'ready', download_capability: 'p'.repeat(64) }, async () => undefined)
    await pageExit.clearPageState()
    expect(pageExitCleanup).toHaveBeenCalledWith('/sandbox/page-exit.zip')
  })
})
