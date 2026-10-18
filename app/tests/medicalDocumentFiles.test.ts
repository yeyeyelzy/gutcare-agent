import { describe, expect, it, vi } from 'vitest'
import { bytesMatchDeclaredSize, pickMedicalFile, preflightMedicalFile } from '../src/api/medicalDocumentFiles'

describe('F02 file preflight and native picker adapter boundary', () => {
  it('accepts exact PDF and image size limits and rejects unsupported/oversized files', () => {
    expect(preflightMedicalFile('report.PDF', 20 * 1024 * 1024).contentType).toBe('application/pdf')
    expect(preflightMedicalFile('scan.jpeg', 10 * 1024 * 1024).contentType).toBe('image/jpeg')
    expect(preflightMedicalFile('scan.png', 10 * 1024 * 1024).contentType).toBe('image/png')
    expect(() => preflightMedicalFile('report.pdf', 20 * 1024 * 1024 + 1)).toThrow('20 MiB')
    expect(() => preflightMedicalFile('scan.png', 10 * 1024 * 1024 + 1)).toThrow('10 MiB')
    expect(() => preflightMedicalFile('report.docx', 10)).toThrow('仅支持')
    expect(() => preflightMedicalFile('report.pdf', 0)).toThrow('大小无法读取')
  })

  it('normalizes native picker names, fails closed on invalid selections, and checks measured bytes', async () => {
    const choose = vi.fn().mockResolvedValue({ path: '/cache/file', name: ' report.pdf ', size: 4 })
    await expect(pickMedicalFile({ choose, read: vi.fn(), cleanup: vi.fn() })).resolves.toMatchObject({ name: 'report.pdf', contentType: 'application/pdf', sizeBytes: 4 })
    await expect(pickMedicalFile({ choose: async () => ({ path: '/cache/file', name: 'unknown', size: 4 }), read: vi.fn(), cleanup: vi.fn() })).rejects.toThrow('仅支持')
    expect(bytesMatchDeclaredSize(new ArrayBuffer(4), 4)).toBe(true)
    expect(bytesMatchDeclaredSize(new ArrayBuffer(3), 4)).toBe(false)
    expect(bytesMatchDeclaredSize(new ArrayBuffer(0), 0)).toBe(false)
  })
})
