export type SecureTokenStoreErrorCode =
  | 'DEVICE_LOCKED'
  | 'CORRUPT_DATA'
  | 'KEY_INVALIDATED'
  | 'UNSUPPORTED_PLATFORM'
  | 'INVALID_VALUE'
  | 'SECURE_STORAGE_FAILED'

export class SecureTokenStoreError extends Error {
  constructor(readonly code: SecureTokenStoreErrorCode) {
    super(secureStoreMessage(code))
    this.name = 'SecureTokenStoreError'
  }
}

export interface SecureTokenStore {
  set(refreshToken: string): Promise<void>
  get(): Promise<string | null>
  remove(): Promise<void>
  has(): Promise<boolean>
}

export interface SecureTokenStoreBridge {
  set(value: string): void
  get(): string | null
  remove(): void
  has(): boolean
}

/** The only production adapter. Platform operations are supplied by gutcare-secure-store UTS. */
export class NativeSecureTokenStore implements SecureTokenStore {
  constructor(private readonly bridge: SecureTokenStoreBridge) {}

  async set(refreshToken: string): Promise<void> {
    if (!refreshToken) throw new SecureTokenStoreError('INVALID_VALUE')
    await this.invoke(() => this.bridge.set(refreshToken))
  }

  async get(): Promise<string | null> {
    return this.invoke(() => this.bridge.get())
  }

  async remove(): Promise<void> {
    await this.invoke(() => this.bridge.remove())
  }

  async has(): Promise<boolean> {
    return this.invoke(() => this.bridge.has())
  }

  private async invoke<T>(operation: () => T): Promise<T> {
    try {
      return operation()
    } catch (error) {
      throw mapSecureTokenStoreError(error)
    }
  }
}

/** Process-local only; tests must opt in explicitly. Never used by the APP runtime. */
export class MemorySecureTokenStore implements SecureTokenStore {
  private value: string | null = null

  async set(refreshToken: string): Promise<void> {
    if (!refreshToken) throw new SecureTokenStoreError('INVALID_VALUE')
    this.value = refreshToken
  }

  async get(): Promise<string | null> { return this.value }
  async remove(): Promise<void> { this.value = null }
  async has(): Promise<boolean> { return this.value !== null }
}

/** Non-native builds never fall back to web storage. */
export class UnsupportedSecureTokenStore implements SecureTokenStore {
  private unavailable(): never { throw new SecureTokenStoreError('UNSUPPORTED_PLATFORM') }
  async set(_refreshToken: string): Promise<void> { this.unavailable() }
  async get(): Promise<string | null> { return this.unavailable() }
  async remove(): Promise<void> { this.unavailable() }
  async has(): Promise<boolean> { return this.unavailable() }
}

export function mapSecureTokenStoreError(error: unknown): SecureTokenStoreError {
  if (error instanceof SecureTokenStoreError) return error
  const code = readCode(error)
  return new SecureTokenStoreError(isSecureTokenStoreErrorCode(code) ? code : 'SECURE_STORAGE_FAILED')
}

export function isDeviceLockedError(error: unknown): boolean {
  return mapSecureTokenStoreError(error).code === 'DEVICE_LOCKED'
}

function readCode(error: unknown): string | undefined {
  if (typeof error === 'object' && error !== null && 'code' in error) {
    const code = (error as { code?: unknown }).code
    if (typeof code === 'string') return code
  }
  if (error instanceof Error) {
    const match = /^SECURE_STORE_(DEVICE_LOCKED|CORRUPT_DATA|KEY_INVALIDATED|UNSUPPORTED_PLATFORM|INVALID_VALUE|SECURE_STORAGE_FAILED)$/.exec(error.message)
    if (match?.[1]) return match[1]
  }
  return undefined
}

function isSecureTokenStoreErrorCode(value: string | undefined): value is SecureTokenStoreErrorCode {
  return value === 'DEVICE_LOCKED'
    || value === 'CORRUPT_DATA'
    || value === 'KEY_INVALIDATED'
    || value === 'UNSUPPORTED_PLATFORM'
    || value === 'INVALID_VALUE'
    || value === 'SECURE_STORAGE_FAILED'
}

function secureStoreMessage(code: SecureTokenStoreErrorCode): string {
  switch (code) {
    case 'DEVICE_LOCKED': return '设备锁定期间安全存储不可用。'
    case 'CORRUPT_DATA': return '安全存储数据无效。'
    case 'KEY_INVALIDATED': return '安全存储密钥已失效。'
    case 'UNSUPPORTED_PLATFORM': return '当前平台不支持安全令牌存储。'
    case 'INVALID_VALUE': return '安全令牌内容无效。'
    case 'SECURE_STORAGE_FAILED': return '安全令牌存储操作失败。'
  }
}
