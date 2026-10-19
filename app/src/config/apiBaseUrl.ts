const API_PATH = '/api/v1'
const INVALID_EXAMPLE_HOST = /(?:^|\.)example\.invalid$/i

export interface ApiBaseUrlOptions {
  allowLocalHttp?: boolean
}

/** Parse and normalize an API URL using only deterministic string operations. */
export function resolveApiBaseUrl(value: string | undefined, options: ApiBaseUrlOptions = {}): string {
  if (value === undefined || value.length === 0) throw new Error('API 配置无效：请设置 VITE_API_BASE_URL。')
  if (/\s|[\u0000-\u001f\u007f]/.test(value)) throw invalidConfiguration()

  const match = /^(https?):\/\/([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$/i.exec(value)
  if (!match) throw invalidConfiguration()

  const scheme = match[1]!.toLowerCase()
  const authority = match[2]
  const rawPath = match[3] || '/'
  const search = match[4] || ''
  const hash = match[5] || ''
  if (!authority || search || hash || authority.includes('@') || value.includes('\\')) {
    throw invalidConfiguration()
  }

  const hostPort = parseAuthority(authority)
  if (!hostPort) throw invalidConfiguration()
  const { hostname, port, ipv6 } = hostPort
  const localHost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
  const secureScheme = scheme === 'https'
  const allowedLocalDevelopment = options.allowLocalHttp === true && localHost && scheme === 'http'
  if ((!secureScheme && !allowedLocalDevelopment) || INVALID_EXAMPLE_HOST.test(hostname)) {
    throw invalidConfiguration()
  }

  if (rawPath !== '/' && rawPath !== API_PATH && rawPath !== `${API_PATH}/`) throw invalidConfiguration()
  const path = rawPath === '/' ? '/' : API_PATH

  const defaultPort = (scheme === 'https' && port === '443') || (scheme === 'http' && port === '80')
  const origin = `${scheme}://${ipv6 ? `[${hostname}]` : hostname}${port && !defaultPort ? `:${port}` : ''}`
  return `${origin}${path === '/' ? API_PATH : path}`
}

function parseAuthority(authority: string): { hostname: string; port: string; ipv6: boolean } | undefined {
  if (authority.startsWith('[')) {
    const end = authority.indexOf(']')
    if (end < 0) return undefined
    const hostname = authority.slice(1, end).toLowerCase()
    const suffix = authority.slice(end + 1)
    if (!isValidIpv6(hostname)) return undefined
    const port = suffix ? parsePort(suffix) : ''
    if (suffix && !port) return undefined
    return { hostname, port: port || '', ipv6: true }
  }

  const colon = authority.lastIndexOf(':')
  const hasPort = colon >= 0
  const rawHost = hasPort ? authority.slice(0, colon) : authority
  const port = hasPort ? parsePort(authority.slice(colon)) : ''
  if (!rawHost || (hasPort && !port) || rawHost.includes(':')) return undefined
  const hostname = rawHost.toLowerCase()
  if (!/^(?:[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)$/.test(hostname) || hostname.includes('..')) return undefined
  return { hostname, port: port || '', ipv6: false }
}

/** Validate the RFC 4291 textual forms without relying on browser URL parsing. */
function isValidIpv6(hostname: string): boolean {
  if (!hostname.includes(':') || hostname.includes(':::')) return false
  const halves = hostname.split('::')
  if (halves.length > 2) return false
  const parseGroups = (part: string): number | undefined => {
    if (!part) return 0
    const groups = part.split(':')
    let count = 0
    for (let index = 0; index < groups.length; index += 1) {
      const group = groups[index]!
      if (group.includes('.')) {
        if (index !== groups.length - 1 || !isValidIpv4(group)) return undefined
        count += 2
      } else {
        if (!/^[0-9a-f]{1,4}$/i.test(group)) return undefined
        count += 1
      }
    }
    return count
  }
  const left = parseGroups(halves[0]!)
  const right = parseGroups(halves.length === 2 ? halves[1]! : '')
  if (left === undefined || right === undefined) return false
  return halves.length === 2 ? left + right < 8 : left === 8
}

function isValidIpv4(address: string): boolean {
  const parts = address.split('.')
  return parts.length === 4 && parts.every((part) =>
    /^\d{1,3}$/.test(part) && Number(part) <= 255,
  )
}

function parsePort(suffix: string): string | undefined {
  if (!/^:[0-9]+$/.test(suffix)) return undefined
  const port = Number(suffix.slice(1))
  if (!Number.isInteger(port) || port < 1 || port > 65535) return undefined
  return String(port)
}

function invalidConfiguration(): Error {
  return new Error('API 配置无效：请使用 HTTPS 地址，并指向 /api/v1。')
}
