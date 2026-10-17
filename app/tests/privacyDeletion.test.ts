import { describe, expect, it, vi } from 'vitest'
import { PrivacyApi } from '../src/api/privacyApi'
import { NativeDeletionReceiptStore, createDeletionReceiptRecord } from '../src/api/deletionReceiptStore'
import { PrivacyDeletionService } from '../src/api/privacyDeletionService'
import type { RequestClient } from '../src/api/requestClient'
import type { PrivacyDeletionStatus } from '../src/api/openapiTypes'

const operationId = '00000000-0000-4000-8000-000000000001'
const receipt = 'r'.repeat(64)
const accepted = { operation_id: operationId, receipt, status: 'accepted' as const }
const pending: PrivacyDeletionStatus = { operation_id: operationId, status: 'pending', requested_at: '2026-10-18T00:00:00Z', due_at: '2026-11-17T00:00:00Z', completed_at: null }

describe('F13 privacy API and receipt handling', () => {
  it('uses the deletion endpoints and disables refresh for receipt-only status queries', async () => {
    const request = vi.fn().mockResolvedValueOnce(accepted).mockResolvedValueOnce(pending)
    const api = new PrivacyApi({ request } as unknown as RequestClient)
    await api.requestAccountDeletion()
    await api.getDeletionStatus(operationId, { receipt })
    expect(request).toHaveBeenNthCalledWith(1, { method: 'POST', path: '/patients/me/account-deletion' })
    expect(request).toHaveBeenNthCalledWith(2, { method: 'POST', path: `/privacy/deletion-operations/${operationId}/status`, data: { receipt }, retryOnUnauthorized: false })
  })

  it('stores receipt in dedicated secure bridge and removes malformed or expired material', async () => {
    let raw: string | null = null
    const bridge = { setDeletionReceiptRecord: (value: string) => { raw = value }, getDeletionReceiptRecord: () => raw, removeDeletionReceiptRecord: () => { raw = null } }
    const now = Date.parse('2026-10-18T00:00:00Z')
    const store = new NativeDeletionReceiptStore(bridge, () => now)
    const record = createDeletionReceiptRecord(operationId, receipt, now)
    await store.save(record)
    expect(JSON.parse(raw!)).toEqual(record)
    expect(await store.load()).toEqual(record)
    raw = '{bad json'
    expect(await store.load()).toBeNull()
    expect(raw).toBeNull()
  })

  it('persists new receipt before clearing local session; retry receipt:null only reuses matching stored receipt', async () => {
    const record = createDeletionReceiptRecord(operationId, receipt, Date.parse('2026-10-18T00:00:00Z'))
    let saved: typeof record | null = null
    const events: string[] = []
    const store = { save: vi.fn(async (next: typeof record) => { events.push('save'); saved = next }), load: vi.fn(async () => saved), remove: vi.fn(async () => { saved = null }) }
    const api = { requestAccountDeletion: vi.fn().mockResolvedValueOnce(accepted).mockResolvedValueOnce({ ...accepted, receipt: null }), getDeletionStatus: vi.fn() }
    const session = { clearForAccountDeletion: vi.fn(async () => { events.push('clear'); return null }) }
    const router = { onAccountDeletionAccepted: vi.fn(() => { events.push('navigate') }) }
    const service = new PrivacyDeletionService(api as unknown as PrivacyApi, store, session, router, () => Date.parse('2026-10-18T00:00:00Z'))
    await service.requestAccountDeletion()
    expect(events).toEqual(['save', 'clear', 'navigate'])
    expect(service.takeAcceptedProgressContext()).toMatchObject({ receiptAvailable: true, receiptStorage: 'secure', receiptForOneTimeDisplay: receipt })
    await service.requestAccountDeletion()
    expect(service.takeAcceptedProgressContext()).toMatchObject({ receiptAvailable: true, receiptStorage: 'secure', receiptForOneTimeDisplay: null })
    expect(store.save).toHaveBeenCalledTimes(1)
  })

  it('does not claim receipt recovery on null response and keeps a failed secure save only in memory', async () => {
    const store = { save: vi.fn(async () => { throw new Error('secure store unavailable') }), load: vi.fn(async () => null), remove: vi.fn(async () => undefined) }
    const api = { requestAccountDeletion: vi.fn().mockResolvedValueOnce(accepted).mockResolvedValueOnce({ ...accepted, receipt: null }), getDeletionStatus: vi.fn() }
    const session = { clearForAccountDeletion: vi.fn(async () => null) }
    const router = { onAccountDeletionAccepted: vi.fn() }
    const service = new PrivacyDeletionService(api as unknown as PrivacyApi, store, session, router, () => Date.parse('2026-10-18T00:00:00Z'))
    await service.requestAccountDeletion()
    const first = service.takeAcceptedProgressContext()
    expect(first).toMatchObject({ receiptAvailable: true, receiptStorage: 'memory_only', receiptForOneTimeDisplay: receipt, receiptStorageErrorCode: 'SECURE_STORAGE_FAILED' })
    await service.requestAccountDeletion()
    expect(service.takeAcceptedProgressContext()).toMatchObject({ receiptAvailable: true, receiptStorage: 'memory_only', receiptForOneTimeDisplay: null })

    const emptyService = new PrivacyDeletionService({ requestAccountDeletion: vi.fn().mockResolvedValue({ ...accepted, receipt: null }) } as unknown as PrivacyApi, { save: vi.fn(), load: vi.fn(async () => null), remove: vi.fn() }, session, router)
    await emptyService.requestAccountDeletion()
    expect(emptyService.takeAcceptedProgressContext()).toMatchObject({ receiptAvailable: false, receiptStorage: 'unavailable', receiptForOneTimeDisplay: null })
  })

  it('is single-flight and completed status removes only matching receipt without logout', async () => {
    let resolveRequest!: (value: typeof accepted) => void
    const api = { requestAccountDeletion: vi.fn(() => new Promise<typeof accepted>(resolve => { resolveRequest = resolve })), getDeletionStatus: vi.fn().mockResolvedValue({ ...pending, status: 'completed' }) }
    const store = { save: vi.fn(), load: vi.fn(async () => createDeletionReceiptRecord(operationId, receipt)), remove: vi.fn() }
    const session = { clearForAccountDeletion: vi.fn(async () => null) }
    const router = { onAccountDeletionAccepted: vi.fn() }
    const service = new PrivacyDeletionService(api as unknown as PrivacyApi, store, session, router)
    const first = service.requestAccountDeletion()
    const second = service.requestAccountDeletion()
    expect(api.requestAccountDeletion).toHaveBeenCalledTimes(1)
    resolveRequest(accepted)
    await Promise.all([first, second])
    await service.querySavedStatus(await store.load()!)
    expect(store.remove).toHaveBeenCalledOnce()
    expect(session.clearForAccountDeletion).toHaveBeenCalledOnce()
  })
})
