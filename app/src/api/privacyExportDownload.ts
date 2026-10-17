import { resolveApiBaseUrl } from '../config/apiBaseUrl'
import type { PrivacyExportDetail } from './openapiTypes'

export interface TemporaryExportDownload { filePath: string; statusCode: number }
export interface ExportDownloadPlatform {
  downloadFile(options: { url: string; header: Record<string, string>; timeout?: number }): Promise<TemporaryExportDownload>
  removeTemporaryFile(filePath: string): Promise<void>
}

/** Capability is used exactly once in a header and is never included in a URL or persisted. */
export class PrivacyExportDownloadAdapter {
  private consumedDetails = new WeakSet<object>()
  private readonly temporaryFiles = new Set<string>()
  private generation = 0

  constructor(private readonly platform: ExportDownloadPlatform, private readonly apiBaseUrl: string) {}

  private download(detail: Pick<PrivacyExportDetail, 'status' | 'download_capability'>): Promise<TemporaryExportDownload> {
    const capability = detail.status === 'ready' ? detail.download_capability : null
    if (!capability || capability.length < 40 || capability.length > 128) return Promise.reject(new Error('下载能力不可用，请刷新导出详情。'))
    if (this.consumedDetails.has(detail)) return Promise.reject(new Error('该下载能力已使用，请刷新导出详情获取新的能力。'))
    // Consume the detail object's capability before I/O; do not retain the credential in adapter state.
    this.consumedDetails.add(detail)
    detail.download_capability = null
    const current = this.generation
    return this.platform.downloadFile({
      url: `${this.apiBaseUrl.replace(/\/$/, '')}/privacy/exports/download`,
      header: { 'X-Export-Capability': capability, Accept: 'application/zip' },
      timeout: 60_000,
    }).then(async (result) => {
      if (current !== this.generation) {
        await this.cleanup(result.filePath)
        throw new Error('下载页面已离开，请刷新导出详情获取新的能力。')
      }
      this.temporaryFiles.add(result.filePath)
      return result
    })
  }

  async consumeTemporaryFile(detail: Pick<PrivacyExportDetail, 'status' | 'download_capability'>, consume: (filePath: string) => Promise<void>): Promise<void> {
    const result = await this.download(detail)
    try {
      if (result.statusCode === 404) throw new Error('下载能力已过期或已使用，请刷新导出详情后重试。')
      if (result.statusCode !== 200) throw new Error('导出文件暂不可下载，请刷新详情后重试。')
      await consume(result.filePath)
    } finally {
      await this.cleanup(result.filePath)
    }
  }

  private cleanup(filePath: string): Promise<void> {
    this.temporaryFiles.delete(filePath)
    return this.platform.removeTemporaryFile(filePath)
  }

  async clearPageState(): Promise<void> {
    this.generation++
    this.consumedDetails = new WeakSet<object>()
    await Promise.all([...this.temporaryFiles].map((filePath) => this.cleanup(filePath)))
  }
}

const platform: ExportDownloadPlatform = {
  downloadFile: (options) => new Promise((resolve, reject) => {
    uni.downloadFile({
      ...options,
      success: (result) => resolve({ filePath: result.tempFilePath, statusCode: result.statusCode }),
      fail: () => reject(new Error('下载连接暂不可用，请稍后刷新详情重试。')),
    })
  }),
  removeTemporaryFile: (filePath) => new Promise((resolve) => {
    // Uni temporary paths are app-sandbox files; never promote them to persistent storage.
    if (typeof plus === 'undefined' || !plus.io) { resolve(); return }
    plus.io.resolveLocalFileSystemURL(filePath, (entry) => entry.remove(() => resolve(), () => resolve()), () => resolve())
  }),
}

export function createPrivacyExportDownloadAdapter() {
  return new PrivacyExportDownloadAdapter(
    platform,
    resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL, { allowLocalHttp: import.meta.env.DEV }),
  )
}
