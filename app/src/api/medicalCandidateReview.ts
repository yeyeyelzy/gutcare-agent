import type { MedicalFieldCandidate, MedicalDocument } from './openapiTypes'

const fieldLabels: Record<MedicalFieldCandidate['field_code'], string> = {
  diagnosis: '诊断记录',
  document_date: '报告日期',
  recommendation: '报告建议',
  test_item: '检验项目',
  test_result: '检验结果',
  medication_name: '药品名称',
  medication_dose: '药品剂量记录',
  medication_frequency: '用药频次记录',
  medication_duration: '用药时长记录',
  allergy: '过敏记录',
}

const certaintyLabels: Record<string, string> = {
  explicit: '明确记录',
  suspected: '疑似记录',
  rule_out: '待排记录',
  history: '既往记录',
}

export function candidateFieldLabel(candidate: MedicalFieldCandidate): string {
  return fieldLabels[candidate.field_code]
}

export function candidateStatusLabel(status: MedicalFieldCandidate['review_status']): string {
  return ({ pending: '待本人核对', accepted: '已按原值确认', corrected: '已按更正值确认', rejected: '已拒绝', invalidated: '来源已失效' } as const)[status]
}

export function parseOutcomeLabel(document: MedicalDocument): string | null {
  if (document.parse_status === 'failed') return '解析任务未完成'
  if (document.parse_outcome === 'extracted') return '已提取候选，等待本人逐项核对'
  if (document.parse_outcome === 'no_supported_facts') return '未发现可支持的字段'
  if (document.parse_outcome === 'insufficient_quality') return '资料质量不足，未生成候选'
  return null
}

export function parseReasonLabel(document: MedicalDocument): string | null {
  const reason = document.parse_reason_code
  if (!reason) return null
  return ({
    no_supported_fields: '没有可支持的字段',
    unsupported_content: '资料内容暂不支持解析',
    low_quality_scan: '扫描质量不足',
    illegible_content: '资料内容无法清晰辨认',
    incomplete_document: '资料内容不完整',
  } as const)[reason]
}

export function candidateValueLabel(candidate: MedicalFieldCandidate): string {
  const value = candidate.value
  if (candidate.value_type === 'date' || candidate.value_type === 'string') return typeof value === 'string' ? value : '候选值格式不可显示'
  if (candidate.value_type === 'diagnosis') {
    if (!isObject(value) || typeof value.text !== 'string' || typeof value.certainty !== 'string') return '候选值格式不可显示'
    const certainty = certaintyLabels[value.certainty]
    return certainty ? `${value.text} · ${certainty}` : value.text
  }
  if (candidate.field_code === 'test_result' && isObject(value)) {
    const result = scalarLabel(value.result)
    return result ? `${result}${candidate.unit ? ` ${candidate.unit}` : ''}` : '候选值格式不可显示'
  }
  if (candidate.field_code === 'medication_dose' && isObject(value)) {
    const amount = scalarLabel(value.amount)
    const unit = typeof value.unit === 'string' ? value.unit : ''
    return amount && unit ? `${amount} ${unit}` : '候选值格式不可显示'
  }
  return '候选值格式不可显示'
}

export function candidateDecisionValueLabel(candidate: MedicalFieldCandidate): string {
  if ((candidate.review_status === 'accepted' || candidate.review_status === 'corrected') && candidate.chosen_value !== null) {
    return candidateValueLabel({ ...candidate, value: candidate.chosen_value })
  }
  return candidateValueLabel(candidate)
}

export function candidateLocatorLabel(locator: unknown): string | null {
  if (!isObject(locator)) return null
  const labels: string[] = []
  if (typeof locator.page === 'number' && Number.isSafeInteger(locator.page) && locator.page > 0) labels.push(`第 ${locator.page} 页`)
  const start = locator.char_start
  const end = locator.char_end
  if (typeof start === 'number' && typeof end === 'number' && Number.isSafeInteger(start) && Number.isSafeInteger(end) && start >= 0 && end > start) {
    labels.push('来源文本位置')
  }
  if (Array.isArray(locator.bbox) && locator.bbox.length === 4 && locator.bbox.every((item) => typeof item === 'number' && Number.isFinite(item) && item >= 0 && item <= 1)
      && locator.bbox[2] > 0 && locator.bbox[3] > 0 && locator.bbox[0] + locator.bbox[2] <= 1 && locator.bbox[1] + locator.bbox[3] <= 1) {
    labels.push('来源页面区域')
  }
  return labels.length ? labels.join(' · ') : null
}

export function initialCorrectionText(candidate: MedicalFieldCandidate): string {
  if (candidate.value_type === 'diagnosis' && isObject(candidate.value) && typeof candidate.value.text === 'string') return candidate.value.text
  if (candidate.value_type === 'object') {
    try { return JSON.stringify(candidate.value, null, 2) ?? '' } catch { return '' }
  }
  return typeof candidate.value === 'string' ? candidate.value : ''
}

export function correctedCandidateValue(candidate: MedicalFieldCandidate, rawValue: string): unknown {
  const input = rawValue.trim()
  if (!input) throw new Error('请填写你确认的更正内容。')
  if (candidate.value_type === 'string') {
    if (input.length > 2000) throw new Error('更正内容过长。')
    return input
  }
  if (candidate.value_type === 'date') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(input)) throw new Error('日期请使用 YYYY-MM-DD 格式。')
    const parsed = new Date(`${input}T00:00:00Z`)
    if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== input) throw new Error('请填写有效日期。')
    return input
  }
  if (candidate.value_type === 'diagnosis') {
    if (!isObject(candidate.value) || typeof candidate.value.certainty !== 'string' || !(candidate.value.certainty in certaintyLabels)) {
      throw new Error('原候选的诊断确定性不可用，无法安全更正。')
    }
    if (input.length > 2000) throw new Error('更正内容过长。')
    return { text: input, certainty: candidate.value.certainty }
  }
  let parsed: unknown
  try { parsed = JSON.parse(input) } catch { throw new Error('请按示例填写有效 JSON 对象。') }
  if (!isObject(parsed) || Object.keys(parsed).length === 0) throw new Error('更正内容必须是非空对象。')
  return parsed
}

export function safeCandidateForDisplay(candidate: MedicalFieldCandidate): MedicalFieldCandidate {
  if (candidate.review_status === 'invalidated') return { ...candidate, excerpt: null, source_locator: null }
  return candidate
}

export function excerptForOnDemandDisplay(candidate: MedicalFieldCandidate): string | null {
  if (candidate.review_status === 'invalidated' || typeof candidate.excerpt !== 'string' || candidate.excerpt.length === 0) return null
  return candidate.excerpt.slice(0, 240)
}

function scalarLabel(value: unknown): string | null {
  if (typeof value === 'string' && value.length > 0) return value.slice(0, 200)
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return null
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
