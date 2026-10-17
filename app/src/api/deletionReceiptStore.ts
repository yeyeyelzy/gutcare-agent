import { SecureTokenStoreError, mapSecureTokenStoreError } from './secureTokenStore'

export interface DeletionReceiptRecord {
  operation_id: string
  receipt: string
  created_at: string
  expires_at: string
}

export interface DeletionReceiptBridge {
  setDeletionReceiptRecord(value: string): void
  getDeletionReceiptRecord(): string | null
  removeDeletionReceiptRecord(): void
}

export interface DeletionReceiptStore {
  save(record: DeletionReceiptRecord): Promise<void>
  load(): Promise<DeletionReceiptRecord | null>
  remove(): Promise<void>
}

export const DELETION_RECEIPT_MAX_AGE_MS = 35 * 24 * 60 * 60 * 1000

/** Stores only a minimal, short-lived deletion receipt in a dedicated native secure namespace. */
export class NativeDeletionReceiptStore implements DeletionReceiptStore {
  constructor(
    private readonly bridge: DeletionReceiptBridge,
    private readonly now: () => number = Date.now,
  ) {}

  async save(record: DeletionReceiptRecord): Promise<void> {
    if (!validRecord(record) || Date.parse(record.expires_at) <= this.now()) {
      throw new SecureTokenStoreError('INVALID_VALUE')
    }
    this.invoke(() => this.bridge.setDeletionReceiptRecord(JSON.stringify(record)))
  }

  async load(): Promise<DeletionReceiptRecord | null> {
    const raw = this.invoke(() => this.bridge.getDeletionReceiptRecord())
    if (raw === null) return null
    let parsed: unknown
    try { parsed = JSON.parse(raw) } catch {
      await this.remove()
      return null
    }
    if (!validRecord(parsed)) {
      await this.remove()
      return null
    }
    if (Date.parse(parsed.expires_at) <= this.now()) {
      await this.remove()
      return null
    }
    return parsed
  }

  async remove(): Promise<void> {
    this.invoke(() => this.bridge.removeDeletionReceiptRecord())
  }

  private invoke<T>(operation: () => T): T {
    try { return operation() } catch (error) { throw mapSecureTokenStoreError(error) }
  }
}

export function createDeletionReceiptRecord(operationId: string, receipt: string, now = Date.now()): DeletionReceiptRecord {
  if (!isUuid(operationId) || receipt.length < 40 || receipt.length > 128) {
    throw new SecureTokenStoreError('INVALID_VALUE')
  }
  const created = new Date(now)
  return {
    operation_id: operationId,
    receipt,
    created_at: created.toISOString(),
    expires_at: new Date(now + DELETION_RECEIPT_MAX_AGE_MS).toISOString(),
  }
}

function validRecord(value: unknown): value is DeletionReceiptRecord {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Partial<DeletionReceiptRecord>
  return isUuid(record.operation_id)
    && typeof record.receipt === 'string' && record.receipt.length >= 40 && record.receipt.length <= 128
    && typeof record.created_at === 'string' && Number.isFinite(Date.parse(record.created_at))
    && typeof record.expires_at === 'string' && Number.isFinite(Date.parse(record.expires_at))
}

function isUuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
}
