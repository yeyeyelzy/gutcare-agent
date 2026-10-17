import { createDeletionReceiptRecord } from './deletionReceiptStore'
import type { DeletionReceiptRecord, DeletionReceiptStore } from './deletionReceiptStore'
import type { PrivacyApi } from './privacyApi'
import type { PrivacyDeletionStatus } from './openapiTypes'
import type { SessionService } from './session'
import type { AppRouter } from '../navigation/router'
import { SecureTokenStoreError, mapSecureTokenStoreError } from './secureTokenStore'

export interface AccountDeletionProgressContext {
  operationId: string
  receiptAvailable: boolean
  receiptStorage: 'secure' | 'memory_only' | 'unavailable'
  receiptForOneTimeDisplay: string | null
  receiptStorageErrorCode: string | null
  refreshTokenCleanupErrorCode: string | null
}

export interface DeletionStatusResult {
  status: PrivacyDeletionStatus
  receiptStoredSecurely: boolean
  receiptStorageErrorCode: string | null
}

/** Coordinates the irreversible request, durable receipt-first cleanup, and receipt-only progress. */
export class PrivacyDeletionService {
  private requestInFlight: Promise<void> | null = null
  private acceptedContext: AccountDeletionProgressContext | null = null
  private memoryRecord: DeletionReceiptRecord | null = null

  constructor(
    private readonly api: PrivacyApi,
    private readonly receiptStore: DeletionReceiptStore,
    private readonly session: Pick<SessionService, 'clearForAccountDeletion'>,
    private readonly router: Pick<AppRouter, 'onAccountDeletionAccepted'>,
    private readonly now: () => number = Date.now,
  ) {}

  requestAccountDeletion(): Promise<void> {
    if (this.requestInFlight) return this.requestInFlight
    const pending = this.performRequest()
    this.requestInFlight = pending
    return pending.finally(() => {
      if (this.requestInFlight === pending) this.requestInFlight = null
    })
  }

  takeAcceptedProgressContext(): AccountDeletionProgressContext | null {
    const context = this.acceptedContext
    this.acceptedContext = null
    return context
  }

  async loadSavedRecord(): Promise<DeletionReceiptRecord | null> {
    if (this.memoryRecord && !isExpired(this.memoryRecord, this.now())) return this.memoryRecord
    this.memoryRecord = null
    try {
      const record = await this.receiptStore.load()
      if (record) this.memoryRecord = record
      return record
    } catch {
      return null
    }
  }

  async querySavedStatus(record: DeletionReceiptRecord): Promise<DeletionStatusResult> {
    const status = await this.api.getDeletionStatus(record.operation_id, { receipt: record.receipt })
    await this.removeCompletedReceipt(status.operation_id, status.status)
    return { status, receiptStoredSecurely: true, receiptStorageErrorCode: null }
  }

  async queryManualStatus(operationId: string, receipt: string): Promise<DeletionStatusResult> {
    if (!isUuid(operationId) || receipt.length < 40 || receipt.length > 128) {
      throw new SecureTokenStoreError('INVALID_VALUE')
    }
    const status = await this.api.getDeletionStatus(operationId, { receipt })
    if (status.status === 'completed') {
      await this.removeCompletedReceipt(status.operation_id, status.status)
      return { status, receiptStoredSecurely: false, receiptStorageErrorCode: null }
    }
    const record = createDeletionReceiptRecord(operationId, receipt, this.now())
    let storedSecurely = true
    let storageErrorCode: string | null = null
    try {
      await this.receiptStore.save(record)
      this.memoryRecord = record
    } catch (error) {
      storedSecurely = false
      storageErrorCode = mapSecureTokenStoreError(error).code
      this.memoryRecord = record
    }
    return { status, receiptStoredSecurely: storedSecurely, receiptStorageErrorCode: storageErrorCode }
  }

  private async performRequest(): Promise<void> {
    const accepted = await this.api.requestAccountDeletion()
    if (accepted.status !== 'accepted') throw new Error('Unexpected account deletion response')

    let record: DeletionReceiptRecord | null = null
    let receiptToReveal: string | null = null
    let receiptStorage: AccountDeletionProgressContext['receiptStorage'] = 'unavailable'
    let receiptStorageErrorCode: string | null = null

    if (accepted.receipt !== null) {
      record = createDeletionReceiptRecord(accepted.operation_id, accepted.receipt, this.now())
      receiptToReveal = accepted.receipt
      try {
        await this.receiptStore.save(record)
        receiptStorage = 'secure'
        this.memoryRecord = record
      } catch (error) {
        receiptStorage = 'memory_only'
        receiptStorageErrorCode = mapSecureTokenStoreError(error).code
        this.memoryRecord = record
      }
    } else {
      try {
        const existing = await this.receiptStore.load()
        if (existing?.operation_id === accepted.operation_id) {
          record = existing
          receiptStorage = 'secure'
          this.memoryRecord = existing
        }
      } catch (error) {
        receiptStorageErrorCode = mapSecureTokenStoreError(error).code
      }
      if (!record && this.memoryRecord?.operation_id === accepted.operation_id && !isExpired(this.memoryRecord, this.now())) {
        record = this.memoryRecord
        receiptStorage = 'memory_only'
      }
    }

    // The receipt has been stored (or explicitly retained only in memory) before revoking local credentials.
    const refreshTokenCleanupErrorCode = await this.session.clearForAccountDeletion()
    this.acceptedContext = {
      operationId: accepted.operation_id,
      receiptAvailable: record !== null,
      receiptStorage,
      receiptForOneTimeDisplay: receiptToReveal,
      receiptStorageErrorCode,
      refreshTokenCleanupErrorCode,
    }
    this.router.onAccountDeletionAccepted()
  }

  private async removeCompletedReceipt(operationId: string, status: PrivacyDeletionStatus['status']): Promise<void> {
    if (status !== 'completed') return
    if (this.memoryRecord?.operation_id === operationId) this.memoryRecord = null
    try {
      const saved = await this.receiptStore.load()
      if (saved?.operation_id === operationId) await this.receiptStore.remove()
    } catch {
      // Do not surface a completed server status as failed; the secure store applies its own TTL.
    }
  }
}

function isExpired(record: DeletionReceiptRecord, now: number): boolean {
  return Date.parse(record.expires_at) <= now
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
}
