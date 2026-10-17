import { describe, expect, it } from 'vitest'
import { resolveApiBaseUrl } from '../src/config/apiBaseUrl'

describe('API base URL configuration', () => {
  it('normalizes an HTTPS origin to the versioned API path', () => {
    expect(resolveApiBaseUrl('https://api.gutcare.test/')).toBe('https://api.gutcare.test/api/v1')
  })

  it('accepts and normalizes the versioned API path', () => {
    expect(resolveApiBaseUrl('https://api.gutcare.test/api/v1/')).toBe('https://api.gutcare.test/api/v1')
  })

  it('allows HTTP only for localhost during development', () => {
    expect(resolveApiBaseUrl('http://localhost:8000', { allowLocalHttp: true }))
      .toBe('http://localhost:8000/api/v1')
    expect(() => resolveApiBaseUrl('http://localhost:8000')).toThrow('API 配置无效')
    expect(() => resolveApiBaseUrl('http://api.gutcare.test', { allowLocalHttp: true })).toThrow('API 配置无效')
  })

  it.each([
    undefined,
    '',
    'https://api.example.invalid/api/v1',
    'https://sub.example.invalid/api/v1',
    'http://api.gutcare.test/api/v1',
    'https://api.gutcare.test/wrong-path',
    'https://user:secret@api.gutcare.test/api/v1',
    'https://api.gutcare.test/api/v1?token=secret',
  ])('rejects unsafe or incomplete configuration: %s', (value) => {
    expect(() => resolveApiBaseUrl(value)).toThrow('API 配置无效')
  })

  it('does not include the configured URL in validation errors', () => {
    const sensitiveValue = 'http://private.internal.invalid/private/path?key=secret'
    try {
      resolveApiBaseUrl(sensitiveValue)
      throw new Error('expected configuration validation to fail')
    } catch (error) {
      expect(error).toBeInstanceOf(Error)
      expect((error as Error).message).not.toContain('private.internal.invalid')
      expect((error as Error).message).not.toContain('secret')
    }
  })
})
