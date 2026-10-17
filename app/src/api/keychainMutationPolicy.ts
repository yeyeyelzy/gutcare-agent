export interface KeychainStatusCodes {
  success: number
  duplicate: number
  itemNotFound: number
}

export type KeychainSetStage = 'initial-add' | 'update' | 'retry-add' | 'retry-update'
export type KeychainSetStep = 'done' | 'update' | 'retry-add' | 'retry-update' | 'failed'

/** Pure status policy mirrored by the iOS UTS adapter; native Security calls remain device-tested. */
export function nextKeychainSetStep(
  stage: KeychainSetStage,
  status: number,
  codes: KeychainStatusCodes,
): KeychainSetStep {
  if (status === codes.success) return 'done'
  if (stage === 'initial-add' && status === codes.duplicate) return 'update'
  if (stage === 'update' && status === codes.itemNotFound) return 'retry-add'
  if (stage === 'retry-add' && status === codes.duplicate) return 'retry-update'
  return 'failed'
}

/** `errSecItemNotFound` is idempotent only for delete, never for an update/write. */
export function isKeychainDeleteSuccess(status: number, codes: KeychainStatusCodes): boolean {
  return status === codes.success || status === codes.itemNotFound
}
