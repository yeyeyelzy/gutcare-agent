import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { getSettingsAppVersion, openSettingsRow, returnFromConsents, returnFromPrivacyCenter, returnFromSettings } from '../src/navigation/settingsNavigation'

const page = readFileSync(new URL('../src/pages/settings/index.vue', import.meta.url), 'utf8')
const manifest = JSON.parse(readFileSync(new URL('../src/manifest.json', import.meta.url), 'utf8')) as { versionName: string }
const profile = readFileSync(new URL('../src/pages/profile/index.vue', import.meta.url), 'utf8')
const consents = readFileSync(new URL('../src/pages/privacy/consents.vue', import.meta.url), 'utf8')
const privacyCenter = readFileSync(new URL('../src/pages/privacy/center.vue', import.meta.url), 'utf8')
const mePage = readFileSync(new URL('../src/pages/tabs/me/index.vue', import.meta.url), 'utf8')

describe('protected Settings hub', () => {
  it('exposes only supported destinations and uses manifest version as the single version source', () => {
    for (const testId of ['settings-profile', 'settings-notifications', 'settings-consents', 'settings-privacy-center', 'settings-export', 'settings-deletion']) expect(page).toContain(`data-testid="${testId}"`)
    expect(page).toContain("canRenderRoute('settings', auth.state)")
    expect(page).toContain('openSettingsRow(router, row)')
    expect(page).toContain('{{ version }}')
    expect(page).toContain('原生文件保存能力尚未验收')
    expect(page).not.toContain('privacy_policy')
    expect(page).not.toContain('sensitive_image')
    expect(page).not.toContain('密码修改')
    expect(page).not.toContain('推送通知')
    expect(manifest.versionName).toMatch(/^\d+\.\d+\.\d+$/)
    expect(getSettingsAppVersion(manifest.versionName)).toBe(manifest.versionName)
    expect(getSettingsAppVersion(undefined)).toBe('暂不可用')
    expect(getSettingsAppVersion(' ')).toBe('暂不可用')
  })

  it('executes every supported row mapping through the named router and rejects unknown rows', () => {
    const navigate = vi.fn(() => true)
    const router = { navigate }
    const cases = [
      ['profile', 'profile'], ['notifications', 'notificationPreferences'], ['consents', 'privacyConsents'],
      ['privacyCenter', 'privacyCenter'], ['export', 'privacyExports'], ['deletion', 'accountDeletionConfirm'],
    ] as const
    for (const [row, route] of cases) {
      expect(openSettingsRow(router, row)).toBe(true)
      expect(navigate).toHaveBeenLastCalledWith(route)
    }
    expect(navigate).toHaveBeenCalledTimes(6)
    expect(openSettingsRow(router, 'unknown')).toBe(false)
    expect(openSettingsRow(router, '__proto__')).toBe(false)
    expect(openSettingsRow(undefined, 'profile')).toBe(false)
    expect(navigate).toHaveBeenCalledTimes(6)
  })

  it('keeps logout ownership in the profile page and gives settings controls touch-sized rows', () => {
    expect(page).toContain('退出登录位于个人资料页')
    expect(page).not.toContain('logout(')
    expect(page).toContain('min-height:68px')
    expect(page).toContain('width:44px;height:44px')
    expect(profile).toContain('function goBack()')
    expect(consents).toContain('returnFromConsents(router, getCurrentPages().length)')
    expect(privacyCenter).toContain('function goBack()')
    expect(mePage).toContain('route: ME_SETTINGS_ENTRY_ROUTE, title: \'设置与隐私\'')
    expect(mePage).toContain('@click="navigateEntry(item.route)"')
  })

  it('executes settings and consent stack fallbacks through their navigation helpers', () => {
    const navigate = vi.fn(() => true)
    const navigateBack = vi.fn()
    const switchTab = vi.fn(() => true)
    const router = { navigate, navigateBack, switchTab }

    returnFromSettings(router, 2)
    expect(navigateBack).toHaveBeenCalledOnce()
    expect(switchTab).not.toHaveBeenCalled()
    returnFromSettings(router, 1)
    expect(switchTab).toHaveBeenCalledWith('me')

    navigateBack.mockClear()
    returnFromConsents(router, 2)
    expect(navigateBack).toHaveBeenCalledOnce()
    expect(navigate).not.toHaveBeenCalled()
    returnFromConsents(router, 1)
    expect(navigate).toHaveBeenCalledWith('settings')

    navigateBack.mockClear()
    returnFromPrivacyCenter(router, 2)
    expect(navigateBack).toHaveBeenCalledOnce()
    returnFromPrivacyCenter(router, 1)
    expect(switchTab).toHaveBeenLastCalledWith('me')
  })
})
