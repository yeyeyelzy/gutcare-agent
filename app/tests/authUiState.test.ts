import { describe, expect, it } from 'vitest'
import { AppError } from '../src/api/errors'
import { isGcButtonDisabled, presentAuthProblem } from '../src/api/authUiState'

describe('shared authentication UI state', () => {
  it('keeps one non-enumerating 401 message and never displays server detail', () => {
    const unknownAccount = new AppError('http', 'secret account detail', { status: 401, requestId: 'fixture-request-id' })
    const wrongPassword = new AppError('http', 'different server detail', { status: 401 })
    expect(presentAuthProblem(unknownAccount, 'fallback')).toEqual({
      message: '邮箱或密码不正确，或邮箱尚未验证。', requestId: 'fixture-request-id',
    })
    expect(presentAuthProblem(wrongPassword, 'fallback')?.message).toBe(presentAuthProblem(unknownAccount, 'fallback')?.message)
  })

  it.each([
    [new AppError('offline', 'private text'), '网络暂不可用，请检查连接后重试。'],
    [new AppError('http', 'private text', { status: 429 }), '操作过于频繁，请稍后重试。'],
    [new AppError('http', 'private text', { status: 422 }), '请检查输入信息或令牌后重试。'],
    [new AppError('http', 'private text', { status: 500, requestId: 'fixture-500-request-id' }), '服务暂时不可用，请稍后重试。'],
  ])('presents a safe actionable message for common API failures', (error, message) => {
    expect(presentAuthProblem(error, 'fallback')?.message).toBe(message)
  })

  it('shows unknown error fallback and hides empty/loading states', () => {
    expect(presentAuthProblem(null, 'fallback')).toBeNull()
    expect(presentAuthProblem(new Error('secret'), 'fallback')).toEqual({ message: 'fallback' })
  })

  it('renders projected startup errors with safe copy and the original request id', () => {
    expect(presentAuthProblem({ kind: 'unavailable', status: 503, code: 'service_unavailable', requestId: 'fixture-startup-id' }, 'fallback'))
      .toEqual({ message: '服务暂时不可用，请稍后重试。', requestId: 'fixture-startup-id' })
    expect(presentAuthProblem({ kind: 'timeout', status: 504, requestId: 'fixture-timeout-id' }, 'fallback'))
      .toEqual({ message: '网络暂不可用，请检查连接后重试。', requestId: 'fixture-timeout-id' })
  })

  it('treats busy as disabled to prevent duplicate submissions', () => {
    expect(isGcButtonDisabled(false, false)).toBe(false)
    expect(isGcButtonDisabled(false, true)).toBe(true)
    expect(isGcButtonDisabled(true, false)).toBe(true)
  })
})
