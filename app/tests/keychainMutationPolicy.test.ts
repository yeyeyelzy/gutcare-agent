import { describe, expect, it } from 'vitest'
import { isKeychainDeleteSuccess, nextKeychainSetStep } from '../src/api/keychainMutationPolicy'

const status = { success: 0, duplicate: -25299, itemNotFound: -25300 }

describe('Keychain set status policy', () => {
  it('retries Add after an Update race and then updates a competing Add', () => {
    expect(nextKeychainSetStep('initial-add', status.duplicate, status)).toBe('update')
    expect(nextKeychainSetStep('update', status.itemNotFound, status)).toBe('retry-add')
    expect(nextKeychainSetStep('retry-add', status.duplicate, status)).toBe('retry-update')
    expect(nextKeychainSetStep('retry-update', status.success, status)).toBe('done')
  })

  it('never treats Update not-found as a persisted success', () => {
    expect(nextKeychainSetStep('update', status.itemNotFound, status)).toBe('retry-add')
    expect(nextKeychainSetStep('retry-update', status.itemNotFound, status)).toBe('failed')
  })

  it('allows not-found as success only for idempotent delete', () => {
    expect(isKeychainDeleteSuccess(status.itemNotFound, status)).toBe(true)
    expect(nextKeychainSetStep('update', status.itemNotFound, status)).not.toBe('done')
  })

  it('fails closed for unexpected Keychain status codes', () => {
    expect(nextKeychainSetStep('initial-add', -50, status)).toBe('failed')
    expect(isKeychainDeleteSuccess(-50, status)).toBe(false)
  })
})
