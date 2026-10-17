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

  it('clearly labels preview as non-final, uses server preview values, and does not expose raw results', () => {
    expect(page).toContain('预览只反映当前时点，不保证与稍后创建的任务快照一致。')
    expect(page).toContain('preview.mood_record_count_in_range')
    expect(page).toContain('preview.mood_record_count_eligible')
    expect(page).toContain('preview.mood_record_count_excluded_by_consent')
    expect(page).toContain('同一授权栅栏内重新检查授权与记录')
    expect(page).toContain('task.result ?')
    expect(page).not.toContain('task.result.summary')
    expect(page).not.toContain('task.result.observations')
    expect(page).not.toContain('task.prompt')
    expect(page).not.toContain('task.result.')
    expect(page).toContain('任务详情不展示 prompt、模型原始输出、报告正文或证据内容。')
  })

  it('checks response generation and visibility after each asynchronous request before updating state', () => {
    const checks = [
      ['async function loadPreview()', 'async function createTask()', 'await api.preview(', 'preview.value = result'],
      ['async function createTask()', 'async function loadList(', 'await api.create(', 'router?.navigateAnalysisTaskDetail('],
      ['async function loadList(', 'async function loadMore()', 'await api.list(', 'tasks.value = page.items'],
      ['async function loadMore()', 'async function loadDetail()', 'await api.list(', 'appendAnalysisPage('],
      ['async function loadDetail()', 'function setAnalysisType(', 'await api.get(', 'task.value = result'],
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
    expect(page).toContain('onHide(() => { visible.value = false; generation += 1; busy.value = false; operation.value = \'\' })')
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
})
