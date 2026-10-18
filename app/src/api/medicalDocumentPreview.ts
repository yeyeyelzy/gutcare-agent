import type { DownloadGrant } from './openapiTypes'

export interface DownloadedMedicalFile { filePath: string; statusCode: number }
export interface MedicalPreviewPlatform {
  download(options: { url: string; headers: Record<string, string> }): Promise<DownloadedMedicalFile>
  remove(filePath: string): Promise<void>
}

/** A download grant is a bearer capability in its URL. Consume it once, then erase the caller's copy. */
export class MedicalDocumentPreviewAdapter {
  private readonly temporaryPaths = new Set<string>()
  private consumed = new WeakSet<object>()
  constructor(private readonly platform: MedicalPreviewPlatform, private readonly apiBaseUrl: string) {}

  async download(grant: DownloadGrant, accessToken: string): Promise<string> {
    const url = grant.download_url
    grant.download_url = ''
    if (this.consumed.has(grant)) throw new Error('该预览授权已使用，请重新获取。')
    this.consumed.add(grant)
    if (!url || !accessToken) throw new Error('预览授权不可用，请重新获取。')
    let parsed: URL
    try { parsed = new URL(url) } catch { throw new Error('预览授权不可用，请重新获取。') }
    if (parsed.origin !== new URL(this.apiBaseUrl).origin || parsed.username || parsed.password || parsed.search || parsed.hash
      || !/^\/uploads\/[A-Za-z0-9_-]{32,128}$/.test(parsed.pathname)) {
      throw new Error('预览授权不可用，请重新获取。')
    }
    const result = await this.platform.download({ url: parsed.href, headers: { Authorization: `Bearer ${accessToken}` } })
    if (result.statusCode !== 200) {
      await this.platform.remove(result.filePath)
      if (result.statusCode === 404) throw new Error('文件暂不可预览，请刷新档案后重试。')
      if (result.statusCode === 401) throw new Error('登录状态已失效，请重新登录后重试。')
      throw new Error('文件预览暂不可用，请稍后重试。')
    }
    this.temporaryPaths.add(result.filePath)
    return result.filePath
  }

  async remove(filePath: string): Promise<void> {
    this.temporaryPaths.delete(filePath)
    await this.platform.remove(filePath)
  }

  async clear(): Promise<void> {
    await Promise.all([...this.temporaryPaths].map((path) => this.remove(path)))
    this.consumed = new WeakSet<object>()
  }
}

export const nativeMedicalPreviewPlatform: MedicalPreviewPlatform = {
  download: (options) => new Promise((resolve, reject) => {
    uni.downloadFile({ ...options, timeout: 60_000,
      success: (result) => resolve({ filePath: result.tempFilePath, statusCode: result.statusCode }),
      fail: () => reject(new Error('文件下载暂不可用，请检查网络后重试。')),
    })
  }),
  remove: (filePath) => new Promise((resolve) => {
    if (typeof plus === 'undefined' || !plus.io) { resolve(); return }
    plus.io.resolveLocalFileSystemURL(filePath, (entry) => entry.remove(() => resolve(), () => resolve()), () => resolve())
  }),
}
