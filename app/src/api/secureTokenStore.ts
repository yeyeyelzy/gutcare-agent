export interface SecureTokenStore {
  set(refreshToken: string): Promise<void>
  get(): Promise<string | null>
  remove(): Promise<void>
  has(): Promise<boolean>
}

/** Production startup must fail closed until the audited UTS Keychain/Keystore adapter is installed. */
export class NativeSecureTokenStoreUnavailable implements SecureTokenStore {
  private unavailable(): never {
    throw new Error('安全令牌存储原生适配尚未安装，已拒绝启动会话恢复。')
  }

  async set(_refreshToken: string): Promise<void> { this.unavailable() }
  async get(): Promise<string | null> { return this.unavailable() }
  async remove(): Promise<void> { this.unavailable() }
  async has(): Promise<boolean> { return this.unavailable() }
}

/** Process-local only; supplied for unit tests and never used by the APP runtime. */
export class MemorySecureTokenStore implements SecureTokenStore {
  private value: string | null = null
  async set(refreshToken: string): Promise<void> { this.value = refreshToken }
  async get(): Promise<string | null> { return this.value }
  async remove(): Promise<void> { this.value = null }
  async has(): Promise<boolean> { return this.value !== null }
}
