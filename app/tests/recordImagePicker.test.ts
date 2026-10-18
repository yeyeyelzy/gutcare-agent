import { describe, expect, it, vi } from 'vitest'
import { chooseRecordImages, type RecordImagePickerPlatform } from '../src/api/recordImagePicker'

function platform(files: { path: string; size: number; type?: string; name?: string }[] = []): RecordImagePickerPlatform & { choose: ReturnType<typeof vi.fn>; cleanup: ReturnType<typeof vi.fn> } {
  return { isSupported: () => true, choose: vi.fn().mockResolvedValue(files), cleanup: vi.fn() }
}

describe('native record image picker adapter', () => {
  it('fails closed outside Android/iOS and never invokes a web substitute', async () => {
    const p = platform()
    p.isSupported = () => false
    await expect(chooseRecordImages(10, p)).rejects.toThrow('仅在 Android/iOS')
    expect(p.choose).not.toHaveBeenCalled()
  })

  it('treats picker cancellation as cancellation and preserves the local fallback', async () => {
    const p = platform()
    p.choose.mockRejectedValue(new Error('chooseImage:fail cancel'))
    await expect(chooseRecordImages(10, p)).rejects.toThrow('已取消')
  })

  it('accepts JPEG/PNG up to exactly 10 MiB and rejects unsupported types and oversize input with cleanup', async () => {
    const valid = platform([{ path: '/tmp/exact.jpg', size: 10 * 1024 * 1024, type: 'image/jpeg' }])
    await expect(chooseRecordImages(10, valid)).resolves.toMatchObject([{ sizeBytes: 10 * 1024 * 1024, contentType: 'image/jpeg' }])
    const badType = platform([{ path: '/tmp/a.gif', size: 4, type: 'image/gif' }])
    await expect(chooseRecordImages(10, badType)).rejects.toThrow('仅支持 JPEG 或 PNG')
    expect(badType.cleanup).toHaveBeenCalledWith('/tmp/a.gif')
    const tooLarge = platform([{ path: '/tmp/b.png', size: 10 * 1024 * 1024 + 1, type: 'image/png' }])
    await expect(chooseRecordImages(10, tooLarge)).rejects.toThrow('不超过 10 MiB')
    expect(tooLarge.cleanup).toHaveBeenCalledWith('/tmp/b.png')
  })

  it('rejects more returned files than the requested count and cleans all paths', async () => {
    const p = platform([{ path: '/tmp/a.jpg', size: 1, type: 'image/jpeg' }, { path: '/tmp/b.jpg', size: 1, type: 'image/jpeg' }])
    await expect(chooseRecordImages(1, p)).rejects.toThrow('数量超出')
    expect(p.cleanup).toHaveBeenCalledTimes(2)
  })
})
