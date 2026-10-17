import { get, getDeletionReceiptRecord, has, remove, removeDeletionReceiptRecord, set, setDeletionReceiptRecord } from '@/../uni_modules/gutcare-secure-store'
import { NativeSecureTokenStore } from './secureTokenStore'
import type { DeletionReceiptBridge } from './deletionReceiptStore'

export const nativeSecureTokenStore = new NativeSecureTokenStore({ get, has, remove, set })

export const nativeDeletionReceiptBridge: DeletionReceiptBridge = {
  getDeletionReceiptRecord,
  setDeletionReceiptRecord,
  removeDeletionReceiptRecord,
}
