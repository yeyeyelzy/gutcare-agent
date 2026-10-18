import type { WorkflowImage } from './recordImageBehavior'

export type PickedRecordImage = WorkflowImage
export interface NativeImageFile { path: string; size: number; type?: string; name?: string }
export interface RecordImagePickerPlatform {
  isSupported(): boolean
  choose(count: number): Promise<NativeImageFile[]>
  cleanup(path: string): void
}

const MAX_IMAGE_BYTES = 10 * 1024 * 1024

/** Native camera/album picker. Unsupported targets deliberately fail closed. */
export async function chooseRecordImages(count: number, platform: RecordImagePickerPlatform = nativePicker): Promise<PickedRecordImage[]> {
  if (!Number.isInteger(count) || count <= 0) return []
  if (!platform.isSupported()) throw new Error('图片选择仅在 Android/iOS 应用中可用。')
  const raw = await platform.choose(count).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : ''
    throw new Error(/cancel/i.test(message) ? '已取消图片选择。' : '图片选择暂不可用，请重试。')
  })
  try {
    if (raw.length > count) throw new Error('图片数量超出允许范围。')
    return raw.map((file) => {
      const contentType = contentTypeFor(file)
      if (!Number.isSafeInteger(file.size) || file.size <= 0 || file.size > MAX_IMAGE_BYTES) throw new Error('每张图片需大于 0 且不超过 10 MiB。')
      if (!contentType) throw new Error('仅支持 JPEG 或 PNG 图片。')
      if (!file.path) throw new Error('图片路径暂不可用，请重新选择。')
      return { path: file.path, sizeBytes: file.size, contentType }
    })
  } catch (error) {
    raw.forEach((file) => platform.cleanup(file.path))
    throw error
  }
}

function contentTypeFor(file: NativeImageFile): PickedRecordImage['contentType'] | null {
  const name = typeof file.name === 'string' ? file.name.toLowerCase() : ''
  const type = typeof file.type === 'string' ? file.type.toLowerCase() : ''
  if (type === 'image/png' || name.endsWith('.png')) return 'image/png'
  if (type === 'image/jpeg' || name.endsWith('.jpg') || name.endsWith('.jpeg')) return 'image/jpeg'
  return null
}

export function readRecordImage(path: string): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    if (typeof plus === 'undefined' || !plus.io) { reject(new Error('当前设备暂不支持安全读取图片。')); return }
    plus.io.resolveLocalFileSystemURL(path, (entry) => {
      const fileEntry = entry as unknown as { isFile: boolean; file: (ok: (file: File) => void, fail: () => void) => void }
      if (!fileEntry.isFile) { reject(new Error('图片读取失败，请重新选择。')); return }
      fileEntry.file((pickedFile) => {
        const file = pickedFile as unknown as PlusIoFile
        const reader = new plus.io.FileReader()
        reader.onload = () => {
          try {
            const raw = typeof reader.result === 'string' ? reader.result : ''
            const binary = atob(raw.slice(raw.indexOf(',') + 1))
            const bytes = new Uint8Array(binary.length)
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
            if (bytes.byteLength !== file.size || bytes.byteLength > MAX_IMAGE_BYTES) throw new Error()
            resolve(bytes.buffer)
          } catch { reject(new Error('图片读取失败，请重新选择。')) }
        }
        reader.onerror = () => reject(new Error('图片读取失败，请重新选择。'))
        reader.readAsDataURL(file)
      }, () => reject(new Error('图片读取失败，请重新选择。')))
    }, () => reject(new Error('图片读取失败，请重新选择。')))
  })
}

export function cleanupRecordImage(path: string): void {
  if (typeof plus === 'undefined' || !plus.io) return
  plus.io.resolveLocalFileSystemURL(path, (entry) => entry.remove(() => undefined, () => undefined), () => undefined)
}

const nativePicker: RecordImagePickerPlatform = {
  isSupported: () => typeof plus !== 'undefined' && Boolean(plus.io),
  choose: (count) => new Promise((resolve, reject) => {
    uni.chooseImage({ count, sizeType: ['original'], sourceType: ['album', 'camera'], success: (result) => {
      const rawFiles = result.tempFiles as unknown as NativeImageFile | NativeImageFile[] | undefined
      resolve(rawFiles ? (Array.isArray(rawFiles) ? rawFiles : [rawFiles]) : [])
    }, fail: (error) => reject(new Error(error.errMsg ?? 'picker failed')) })
  }),
  cleanup: cleanupRecordImage,
}
