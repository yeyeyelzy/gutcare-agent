import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { APP_ROUTES, routeNameFromUrl } from '../src/navigation/routes'

const root = resolve(import.meta.dirname, '..')
const page = readFileSync(resolve(root, 'src/pages/trends/index.vue'), 'utf8')

describe('protected trend page contract', () => {
  it('routes analysis and me entry to the same authenticated page with distinct ownerTab targets', () => {
    expect(APP_ROUTES.analysisTrends.path).toBe('/pages/trends/index?owner=analysis')
    expect(APP_ROUTES.trends.path).toBe('/pages/trends/index?owner=me')
    expect(routeNameFromUrl(APP_ROUTES.analysisTrends.path)).toBe('analysisTrends')
    expect(routeNameFromUrl(APP_ROUTES.trends.path)).toBe('trends')
    expect(page).toContain('ownerTab.value = options?.owner === \'analysis\' ? \'analysis\' : \'me\'')
    expect(page).toContain('canRenderRoute(routeName.value, auth.state)')
    expect(page).toContain('router?.requireAuthentication(routeName.value)')
    expect(page).toContain('router?.switchTab(ownerTab.value)')
  })

  it('renders all six server aggregates and independent loading, empty, error, offline, and consent states', () => {
    for (const id of ['trend-activity', 'trend-stool', 'trend-symptom', 'trend-diet', 'trend-medication', 'trend-mood']) {
      expect(page).toContain(`data-testid="${id}"`)
    }
    for (const id of ['trend-loading', 'trend-error', 'trend-refresh-error', 'trend-mood-consent-required']) expect(page).toContain(id)
    expect(page).toContain('此范围暂无活动记录。')
    expect(page).toContain('当前离线，趋势未能载入')
    expect(page).toContain('心情趋势暂不可用，需要以下授权')
    expect(page).toContain('前往隐私中心')
    expect(page).toContain('response.mood.buckets.length')
  })

  it('does not expose mood notes or emotion tags, and uses server bucket values without client aggregation', () => {
    expect(page).not.toMatch(/(?:item|response|mood)\.(?:note|emotion_tags|emotionTags)|{{[^}]*\bnote\b/i)
    expect(page).toContain('item.mood_level_counts[level]')
    expect(page).toContain('item.mean_severity')
    expect(page).not.toMatch(/\.reduce\(|\.sum\(|meanSeverity\s*=|mood_level_counts\s*=\s*\{/)
    expect(page).toContain('不在客户端合并或重算')
  })

  it('uses the account timezone and invalidates requests on hide and generation changes', () => {
    expect(page).toContain("timezone.value = auth.profile?.timezone || 'UTC'")
    expect(page).toContain('onHide(() => { visible.value = false; generation += 1; busy.value = false })')
    expect(page).toContain('onShow(() =>')
    expect(page).toContain('firstShowHandled')
    expect(page).toContain('if (isCurrent(requestGeneration)) busy.value = false')
  })
})
