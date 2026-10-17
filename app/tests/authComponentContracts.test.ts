import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const read = (path: string) => readFileSync(resolve(appRoot, path), 'utf8')

describe('authentication component and page contracts', () => {
  it('provides labeled, stable-testable, touch-sized reusable controls and live problems', () => {
    const field = read('src/components/GcField.vue')
    const button = read('src/components/GcButton.vue')
    const notice = read('src/components/NoticeCard.vue')
    const problem = read('src/components/InlineProblem.vue')
    expect(field).toContain(':aria-label="label"')
    expect(field).toContain(':aria-describedby="descriptionId"')
    expect(field).toContain(':data-testid="testId"')
    expect(field).toContain('min-height: 44px')
    expect(button).toContain(':disabled="isGcButtonDisabled(disabled, busy)"')
    expect(button).toContain(':aria-busy="busy"')
    expect(button).toContain(':data-testid="testId"')
    expect(notice).toContain(':data-testid="testId"')
    expect(notice).toContain('版本 {{ version }}')
    expect(problem).toContain('role="alert" aria-live="polite"')
    expect(problem).toContain('支持编号：{{ requestId }}')
    expect(read('src/components/GcButton.vue')).toContain('min-height: 48px')
    expect(read('src/components/GcButton.vue')).toContain('border-radius: 16px')
    expect(read('src/components/AuthScaffold.vue')).toContain('max-width: 430px')
  })

  it('connects the public auth screens to named routes and excludes phone/SMS credential controls', () => {
    const routes = read('src/navigation/routes.ts')
    const pages = read('src/pages.json')
    expect(routes).toContain("forgotPassword: { path: '/pages/auth/forgot-password', access: 'public'")
    expect(routes).toContain("resetPassword: { path: '/pages/auth/reset-password', access: 'public'")
    for (const page of ['pages/launch/index', 'pages/auth/login', 'pages/auth/register', 'pages/auth/register-profile', 'pages/auth/email-verification', 'pages/auth/forgot-password', 'pages/auth/reset-password', 'pages/auth/profile-error']) {
      expect(pages).toContain(`"path": "${page}"`)
    }
    for (const page of ['src/pages/auth/login.vue', 'src/pages/auth/register.vue']) {
      const source = read(page)
      expect(source).not.toMatch(/type=["']tel["']|手机号登录|短信验证码/)
      expect(source).toContain('data-testid=')
    }
    expect(read('src/pages/auth/reset-password.vue')).not.toMatch(/getCurrentPages|onLoad\(.*options|query.*token/i)
  })

  it('keeps registration notice cards separate and gates birth-year input behind health consent', () => {
    const account = read('src/pages/auth/register.vue')
    const profile = read('src/pages/auth/register-profile.vue')
    expect(account).toContain('privacy-notice')
    expect(account).not.toContain('health-processing-notice')
    expect(profile).toContain('health-processing-notice')
    expect(profile).toContain('v-if="accepted" class="birth-card"')
    expect(profile).toContain('暂不同意并退出注册')
    expect(profile).toContain('registration.complete()')
  })

  it('keeps launch artwork code-native, with three features and paired account actions', () => {
    const welcome = read('src/pages/launch/index.vue')
    expect(welcome).toContain('<svg class="hero-illustration"')
    expect(welcome.match(/class="feature-row"/g)).toHaveLength(3)
    expect(welcome.indexOf('welcome-register')).toBeLessThan(welcome.indexOf('welcome-login'))
    expect(welcome).toContain('display: flex; gap: 11px;')
  })

  it('provides a controlled support guidance action without automatic data transmission', () => {
    const page = read('src/pages/auth/profile-error.vue')
    expect(page).toContain('profile-error-support')
    expect(page).toContain('不会发送账户或健康资料')
    expect(page).toContain('此入口不会自动发送任何资料')
  })
})
