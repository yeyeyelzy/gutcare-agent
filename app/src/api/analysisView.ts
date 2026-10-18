import type { AnalysisResultEvidence, AnalysisTask, AnalysisTaskPage, AnalysisTaskRequest } from './openapiTypes'
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
  // The backend may persist an agent-provided code; do not reveal arbitrary values.
  return value ? '服务端提供了任务说明；请以当前任务状态和允许的操作为准。' : '服务端未提供可展示的错误代码。'
}

export type AnalysisTaskActions = { canCancel: boolean; canRetry: boolean; needsNewTask: boolean; shouldPoll: boolean }

export function analysisTaskActions(status: AnalysisTask['status']): AnalysisTaskActions {
  return {
    canCancel: status === 'pending' || status === 'processing',
    canRetry: status === 'failed',
    needsNewTask: status === 'needs_input',
    shouldPoll: status === 'pending' || status === 'processing',
  }
}

export function analysisEvidenceCanNavigate(evidence: AnalysisResultEvidence): boolean {
  return analysisEvidenceLocatorLabel(evidence) !== null
}

const ANALYSIS_EVIDENCE_LOCATOR_LABELS: Partial<Record<AnalysisResultEvidence['source_type'], string>> = {
  confirmed_medical_fact: '已确认医疗事实',
  diet_record: '饮食记录',
  stool_record: '排便记录',
  symptom_record: '症状记录',
  mood_record: '心情记录',
  medication_plan: '用药计划',
  medication_checkin: '用药打卡',
  risk_alert: '风险提示',
}

/** Return only a controlled label; never render a raw locator/path/URL from the service. */
export function analysisEvidenceLocatorLabel(evidence: AnalysisResultEvidence): string | null {
  if (evidence.source_deleted || !isSupportedAnalysisEvidenceType(evidence.source_type)) return null
  const label = ANALYSIS_EVIDENCE_LOCATOR_LABELS[evidence.source_type]
  const locator = typeof evidence.locator === 'string' ? /^([a-z_]+):([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/i.exec(evidence.locator) : null
  if (!label || !locator || locator[1]?.toLowerCase() !== evidence.source_type || locator[2]?.toLowerCase() !== evidence.source_id.toLowerCase()) return null
  return `${label} · 已验证来源定位`
}

function isSupportedAnalysisEvidenceType(value: unknown): value is AnalysisResultEvidence['source_type'] {
  return typeof value === 'string' && Object.hasOwn(ANALYSIS_EVIDENCE_LOCATOR_LABELS, value)
}
