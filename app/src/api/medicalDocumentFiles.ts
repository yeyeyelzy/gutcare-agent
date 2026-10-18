export type MedicalFileMime = 'application/pdf' | 'image/jpeg' | 'image/png'
export interface PickedMedicalFile { path: string; name: string; sizeBytes: number; contentType: MedicalFileMime }
export interface MedicalFilePickerPlatform {
  choose(): Promise<{ path: string; name?: string; size: number }>
  read(path: string): Promise<ArrayBuffer>
  cleanup(path: string): void
}

const MAX_PDF_BYTES = 20 * 1024 * 1024
const MAX_IMAGE_BYTES = 10 * 1024 * 1024

export function preflightMedicalFile(name: string, sizeBytes: number): { contentType: MedicalFileMime; maxBytes: number } {
  if (!Number.isSafeInteger(sizeBytes) || sizeBytes <= 0) throw new Error('文件大小无法读取，请重新选择文件。')
  const extension = name.trim().toLowerCase().split('.').pop() ?? ''
  const contentType: MedicalFileMime | null = extension === 'pdf' ? 'application/pdf'
    : extension === 'jpg' || extension === 'jpeg' ? 'image/jpeg'
      : extension === 'png' ? 'image/png' : null
  if (!contentType) throw new Error('仅支持 PDF、JPEG 或 PNG 文件。')
  const maxBytes = contentType === 'application/pdf' ? MAX_PDF_BYTES : MAX_IMAGE_BYTES
  if (sizeBytes > maxBytes) throw new Error(contentType === 'application/pdf' ? 'PDF 文件不能超过 20 MiB。' : 'JPEG/PNG 文件不能超过 10 MiB。')
  return { contentType, maxBytes }
}

export async function pickMedicalFile(platform: MedicalFilePickerPlatform): Promise<PickedMedicalFile> {
  const selected = await platform.choose()
  const name = selected.name?.trim() || basename(selected.path)
  const { contentType } = preflightMedicalFile(name, selected.size)
  return { ...selected, name, contentType, sizeBytes: selected.size }
}

export function bytesMatchDeclaredSize(bytes: ArrayBuffer, expectedSize: number): boolean {
  return bytes.byteLength > 0 && bytes.byteLength === expectedSize
}

function basename(path: string): string {
  const last = path.split(/[\\/]/).pop() ?? ''
  try { return decodeURIComponent(last) } catch { return last }
}
