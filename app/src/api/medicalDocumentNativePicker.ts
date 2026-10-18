import { chooseMedicalFile, cleanupMedicalFile } from '@/../uni_modules/gutcare-medical-file-picker'
import type { MedicalFilePickerPlatform } from './medicalDocumentFiles'

/** Production adapter uses the narrow Android SAF/iOS document picker plugin; web is test-mock only. */
export const nativeMedicalFilePicker: MedicalFilePickerPlatform = {
  choose: () => new Promise((resolve, reject) => chooseMedicalFile(
    (file) => resolve({ path: file.path, name: file.name, size: file.size }),
    (reason) => reject(new Error(reason === 'cancelled' ? '文件选择已取消。' : reason === 'unsupported_type' ? '仅支持 PDF、JPEG 或 PNG 文件。' : reason === 'too_large' ? '文件超过允许大小。' : '原生文件选择暂不可用。')),
  )),
  read: (path) => new Promise((resolve, reject) => {
    if (typeof plus === 'undefined' || !plus.io) { reject(new Error('当前设备暂不支持安全读取所选文件。')); return }
    plus.io.resolveLocalFileSystemURL(path, (entry) => {
      const fileEntry = entry as unknown as PlusIoFileEntry
      if (!fileEntry.isFile || typeof fileEntry.file !== 'function') { reject(new Error('文件读取失败，请重新选择。')); return }
      fileEntry.file((file) => {
        const reader = new plus.io.FileReader()
        reader.onload = () => {
          const value = typeof reader.result === 'string' ? reader.result : ''
          const base64 = value.slice(value.indexOf(',') + 1)
          try {
            const binary = atob(base64)
            const bytes = new Uint8Array(binary.length)
            for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index)
            resolve(bytes.buffer)
          } catch { reject(new Error('文件读取失败，请重新选择。')) }
        }
        reader.onerror = () => reject(new Error('文件读取失败，请重新选择。'))
        reader.readAsDataURL(file)
      }, () => reject(new Error('文件读取失败，请重新选择。')))
    }, () => reject(new Error('文件读取失败，请重新选择。')))
  }),
  cleanup: (path) => cleanupMedicalFile(path),
}
