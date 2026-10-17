import type { AnalysisTask, AnalysisTaskPage, AnalysisTaskRequest } from './openapiTypes'
import { buildTrendRange } from './trendView'

export interface AnalysisListState {
  items: AnalysisTask[]
  cursor: string | null
  error: string
  requestId: string
}

export function buildAnalysisRequest(
  analysisType: AnalysisTaskRequest['analysis_type'],
  fromDay: string,
  untilExclusiveDay: string,
  timezone: string,
): { body: AnalysisTaskRequest; error: string | null } {
  if (!fromDay && !untilExclusiveDay) {
    if (analysisType === 'periodic_summary') return { body: { analysis_type: analysisType, requested_from: null, requested_to: null }, error: '周期总结需要明确开始与结束日期。' }
    return { body: { analysis_type: analysisType, requested_from: null, requested_to: null }, error: null }
  }
  if (!fromDay || !untilExclusiveDay) return { body: { analysis_type: analysisType, requested_from: null, requested_to: null }, error: '开始与结束日期必须同时填写。' }
  const range = buildTrendRange(fromDay, untilExclusiveDay, timezone)
  if (range.error) return { body: { analysis_type: analysisType, requested_from: null, requested_to: null }, error: range.error }
  return { body: { analysis_type: analysisType, requested_from: range.from, requested_to: range.to }, error: null }
}

export function appendAnalysisPage(state: AnalysisListState, page: AnalysisTaskPage): AnalysisListState {
  const seen = new Set(state.items.map((task) => task.id))
  return {
    items: [...state.items, ...page.items.filter((task) => !seen.has(task.id))],
    cursor: page.next_cursor,
    error: '',
    requestId: '',
  }
}

export function failAnalysisAppend(state: AnalysisListState, error: string, requestId = ''): AnalysisListState {
  return { ...state, error, requestId }
}

export function isAnalysisResponseCurrent(generationAtRequest: number, generation: number, visible: boolean, authorized: boolean): boolean {
  return generationAtRequest === generation && visible && authorized
}

export class AnalysisFirstShowGate {
  private firstShow = true
  shouldRefresh(): boolean {
    if (this.firstShow) { this.firstShow = false; return false }
    return true
  }
}

export function analysisTypeLabel(value: AnalysisTask['analysis_type']): string {
  return value === 'periodic_summary' ? '周期总结' : '综合健康分析'
}

export function analysisStatusLabel(value: AnalysisTask['status']): string {
  const labels: Record<AnalysisTask['status'], string> = {
    pending: '待处理', processing: '处理中', needs_input: '待补充信息',
    succeeded: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消',
  }
  return labels[value]
}

export function analysisErrorLabel(value: string | null): string {
  return value ? `服务端错误代码：${value}` : '服务端未提供错误代码。'
}
