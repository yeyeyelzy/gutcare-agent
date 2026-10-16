import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
  plugins: [uni()],
  test: { environment: 'node', include: ['tests/**/*.test.ts'] },
})
