import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const page = readFileSync(new URL('../src/components/AnalysisWorkspace.vue', import.meta.url), 'utf8')
const routes = readFileSync(new URL('../src/navigation/routes.ts', import.meta.url), 'utf8')

describe('F08 analysis page component contracts', () => {
  it('protects all three named routes and binds task deep links to validated task IDs and analysis owner', () => {
    for (const route of ['analysisNew', 'analysisHistory', 'analysisTaskDetail']) {
      expect(page).toContain(`'${route}'`)
    }
    expect(page).toContain('canRenderRoute(routeName.value as')
    expect(page).toContain('router?.requireAuthentication(routeName.value as')
    expect(routes).toContain("analysisTaskDetail: { path: '/pages/analysis/detail', access: 'authenticated', returnToAllowed: true }")
    expect(page).toContain('isUuid(options?.task_id)')
    expect(page).toContain("ownerTab.value = options?.owner === 'me' ? 'me' : 'analysis'")
    expect(page).toContain("fromHistory.value = options?.from === 'history'")
    expect(page).toContain('router?.switchTab(ownerTab.value)')
    expect(page).toContain('router?.returnFromAnalysisTask(ownerTab.value, fromHistory.value)')
    expect(page).toContain('navigateAnalysisTaskDetail(task.id, ownerTab, true)')
    expect(page).toContain(':label="`返回${returnDestinationLabel}`"')
    expect(page).not.toContain("router?.navigate('analysisHistory')")
  })

  it('clearly labels preview as non-final and renders only the structured result allowlist', () => {
    expect(page).toContain('预览只反映当前时点，不保证与稍后创建的任务快照一致。')
    expect(page).toContain('preview.mood_record_count_in_range')
    expect(page).toContain('preview.mood_record_count_eligible')
    expect(page).toContain('preview.mood_record_count_excluded_by_consent')
    expect(page).toContain('同一授权栅栏内重新检查授权与记录')
    for (const allowed of ['task.result.summary', 'task.result.observations', 'task.result.evidence', 'task.result.uncertainties', 'task.result.missing_data']) expect(page).toContain(allowed)
    for (const forbidden of ['task.callback_id', 'task.prompt', 'task.raw_output', 'task.result.callback_id', 'task.result.raw_output', 'task.result.report_url']) expect(page).not.toContain(forbidden)
    expect(page).toContain("task.result.schema_version === '1.0'")
    expect(page).toContain('这是对记录的整理与分析，不是诊断或处方')
    expect(page).toContain('来源已删除，无法跳转。')
    expect(page).toContain('analysisEvidenceLocatorLabel(item)')
    expect(page).not.toContain('{{ item.locator }}')
  })

  it('checks response generation and visibility after each asynchronous request before updating state', () => {
    const checks = [
      ['async function loadPreview()', 'async function createTask()', 'await api.preview(', 'preview.value = result'],
      ['async function createTask()', 'async function loadList(', 'await api.create(', 'router?.navigateAnalysisTaskDetail('],
      ['async function loadList(', 'async function loadMore()', 'await api.list(', 'tasks.value = page.items'],
      ['async function loadMore()', 'async function loadDetail()', 'await api.list(', 'appendAnalysisPage('],
      ['async function loadDetail()', 'function confirmCancel()', 'await api.get(', 'task.value = result'],
    ] as const
    for (const [start, end, awaitNeedle, mutationNeedle] of checks) {
      const section = page.slice(page.indexOf(start), page.indexOf(end))
      const awaited = section.indexOf(awaitNeedle)
      const guard = section.indexOf('if (!isCurrent(requestGeneration)) return', awaited)
      const mutation = section.indexOf(mutationNeedle, awaited)
      expect(awaited).toBeGreaterThanOrEqual(0)
      expect(guard).toBeGreaterThan(awaited)
      expect(mutation).toBeGreaterThan(guard)
    }
    expect(page).toContain('onHide(() => { visible.value = false; generation += 1; stopPolling(); busy.value = false; operation.value = \'\' })')
    expect(page).toContain('onUnload(() => { visible.value = false; generation += 1; stopPolling() })')
    expect(page).toContain('firstShow.shouldRefresh()')
  })

  it('keeps pagination errors distinct and preserves existing tasks and cursor for retry', () => {
    expect(page).toContain('analysis-history-empty')
    expect(page).toContain('analysis-history-error')
    expect(page).toContain('analysis-refresh-error')
    expect(page).toContain('analysis-more-error')
    expect(page).toContain('failAnalysisAppend(')
    expect(page).toContain('tasks.value = failed.items; cursor.value = failed.cursor')
    expect(page).toContain('analysis-more-retry')
  })

  it('gates actions by backend state, confirms cancel/retry, and avoids fake progress', () => {
    expect(page).toContain("task.status === 'pending' || task.status === 'processing'")
    expect(page).toContain("task.status === 'failed'")
    expect(page).toContain('此任务已结束。补充或确认相关记录后，请新建分析任务；当前任务不能重试。')
    expect(page).toContain("uni.showModal({ title: '取消分析任务？'")
    expect(page).toContain("uni.showModal({ title: '重试分析任务？'")
    expect(page).toContain('analysisTaskActions(status).shouldPoll')
    expect(page).toContain('setTimeout(() => { pollTimer = null')
    expect(page).toContain("error.code === 'CONSENT_REQUIRED'")
    expect(page).toContain('analysis-retry-settings')
    const cancel = page.slice(page.indexOf('async function cancelTask()'), page.indexOf('function confirmRetry()'))
    const retry = page.slice(page.indexOf('async function retryTask()'), page.indexOf('function schedulePolling('))
    for (const section of [cancel, retry]) {
      expect(section.indexOf('await api.')).toBeGreaterThanOrEqual(0)
      expect(section.indexOf('if (!isCurrent(requestGeneration)) return')).toBeGreaterThan(section.indexOf('await api.'))
    }
    expect(retry).toContain('createIdempotencyKey()')
    expect(retry).toContain('retryIdempotencyKey.value')
    expect(page).not.toMatch(/progress(?:-percent)?\s*[:=]/i)
  })
})
