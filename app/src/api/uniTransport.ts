import type { HttpResponse, HttpTransport, RequestOptions } from './requestClient'

export class UniRequestTransport implements HttpTransport {
  send<T>(url: string, options: RequestOptions & { headers: Record<string, string> }): Promise<HttpResponse<T>> {
    return new Promise((resolve, reject) => {
      uni.request({
        url,
        method: options.method as UniApp.RequestOptions['method'],
        data: options.data as UniApp.RequestOptions['data'],
        header: options.headers,
        timeout: 15000,
        success: (result) => resolve({ status: result.statusCode, data: result.data as T }),
        fail: (failure) => {
          const message = failure.errMsg || 'network request failed'
          if (/timeout/i.test(message)) {
            reject(new Error('request timeout'))
            return
          }
          if (/offline/i.test(message)) {
            reject(new Error('offline'))
            return
          }
          uni.getNetworkType({
            success: (network) => reject(new Error(network.networkType === 'none' ? 'offline' : message)),
            fail: () => reject(new Error(message)),
          })
        },
      })
    })
  }
}
