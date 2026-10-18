import { describe, expect, it, vi } from 'vitest'
import { MedicalDocumentPreviewAdapter } from '../src/api/medicalDocumentPreview'
import type { DownloadGrant } from '../src/api/openapiTypes'

const grant = (url = 'https://api.example.test/uploads/abcdefghijklmnopqrstuvwxyz123456'): DownloadGrant => ({ download_url: url, expires_at: '2026-10-18T00:00:00Z' })

describe('medical document preview capability lifecycle', () => {
  it('uses same-origin bearer download once, clears the URL, and removes temporary files on clear', async () => {
    const download = vi.fn().mockResolvedValue({ filePath: '/tmp/preview.pdf', statusCode: 200 })
    const remove = vi.fn().mockResolvedValue(undefined)
    const adapter = new MedicalDocumentPreviewAdapter({ download, remove }, 'https://api.example.test/api/v1')
    const capability = grant()
    await expect(adapter.download(capability, 'access-token')).resolves.toBe('/tmp/preview.pdf')
    expect(capability.download_url).toBe('')
    expect(download).toHaveBeenCalledWith({ url: 'https://api.example.test/uploads/abcdefghijklmnopqrstuvwxyz123456', headers: { Authorization: 'Bearer access-token' } })
    await expect(adapter.download(capability, 'access-token')).rejects.toThrow('已使用')
    await adapter.clear()
    expect(remove).toHaveBeenCalledExactlyOnceWith('/tmp/preview.pdf')
  })

  it('rejects arbitrary/invalid gateway URLs before download and cleans failed response files', async () => {
    const download = vi.fn()
    const remove = vi.fn().mockResolvedValue(undefined)
    const adapter = new MedicalDocumentPreviewAdapter({ download, remove }, 'https://api.example.test/api/v1')
    for (const url of [
      'https://evil.example/uploads/abcdefghijklmnopqrstuvwxyz123456',
      'https://api.example.test/uploads/short',
      'https://api.example.test/uploads/abcdefghijklmnopqrstuvwxyz123456?token=leak',
    ]) await expect(adapter.download(grant(url), 'access-token')).rejects.toThrow()
    expect(download).not.toHaveBeenCalled()
    download.mockResolvedValue({ filePath: '/tmp/failed', statusCode: 404 })
    await expect(adapter.download(grant(), 'access-token')).rejects.toThrow('刷新档案')
    expect(remove).toHaveBeenCalledExactlyOnceWith('/tmp/failed')
  })
})
