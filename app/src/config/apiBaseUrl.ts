const API_PATH = '/api/v1'
const INVALID_EXAMPLE_HOST = /(?:^|\.)example\.invalid$/i

export interface ApiBaseUrlOptions {
  allowLocalHttp?: boolean
}

/** Validate and normalize the public API origin without exposing its value in errors. */
export function resolveApiBaseUrl(value: string | undefined, options: ApiBaseUrlOptions = {}): string {
  if (!value?.trim()) throw new Error('API 配置无效：请设置 VITE_API_BASE_URL。')

  let parsed: URL
  try {
    parsed = new URL(value.trim())
  } catch {
    throw new Error('API 配置无效：请使用 HTTPS 地址，并指向 /api/v1。')
  }

  const hostname = parsed.hostname.toLowerCase()
  const localHost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]'
  const secureScheme = parsed.protocol === 'https:'
  const allowedLocalDevelopment = options.allowLocalHttp === true && localHost && parsed.protocol === 'http:'
  if ((!secureScheme && !allowedLocalDevelopment)
    || INVALID_EXAMPLE_HOST.test(hostname)
    || parsed.username !== ''
    || parsed.password !== ''
    || parsed.search !== ''
    || parsed.hash !== '') {
    throw new Error('API 配置无效：请使用 HTTPS 地址，并指向 /api/v1。')
  }

  const path = parsed.pathname.replace(/\/+$/, '') || '/'
  if (path !== '/' && path !== API_PATH) {
    throw new Error('API 配置无效：请使用 HTTPS 地址，并指向 /api/v1。')
  }

  return `${parsed.origin}${path === '/' ? API_PATH : path}`
}
