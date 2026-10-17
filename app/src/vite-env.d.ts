/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_APP_VERSION?: string
}

declare module '@/../uni_modules/gutcare-secure-store' {
  export function set(value: string): void
  export function get(): string | null
  export function remove(): void
  export function has(): boolean
  export function setDeletionReceiptRecord(value: string): void
  export function getDeletionReceiptRecord(): string | null
  export function removeDeletionReceiptRecord(): void
  export function hasDeletionReceiptRecord(): boolean
}
