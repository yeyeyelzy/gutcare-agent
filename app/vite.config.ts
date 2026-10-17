import { createRequire } from 'node:module'
import { defineConfig, loadEnv } from 'vite'
import type { Plugin } from 'vite'
import { resolveApiBaseUrl } from './src/config/apiBaseUrl'

type UniPluginFactory = typeof import('@dcloudio/vite-plugin-uni').default

function resolveUniPluginFactory(moduleValue: unknown): UniPluginFactory {
  if (typeof moduleValue === 'function') return moduleValue as UniPluginFactory
  if (typeof moduleValue === 'object' && moduleValue !== null && 'default' in moduleValue) {
    const defaultExport = (moduleValue as { default?: unknown }).default
    if (typeof defaultExport === 'function') return defaultExport as UniPluginFactory
  }
  throw new Error('无法加载固定版本的 uni-app Vite 插件。')
}

const require = createRequire(import.meta.url)
const uni = resolveUniPluginFactory(require('@dcloudio/vite-plugin-uni'))

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBaseUrl = resolveApiBaseUrl(env.VITE_API_BASE_URL, { allowLocalHttp: command === 'serve' })
  const plugins: Plugin[] = uni()

  return {
    plugins,
    define: {
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBaseUrl),
    },
  }
})
