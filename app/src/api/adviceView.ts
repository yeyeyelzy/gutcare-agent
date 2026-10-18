import type { Advice, RiskPriorityContext } from './openapiTypes'

export type AdviceEvidence = Advice['evidence'][number]
type PatientAdviceEvidence = Extract<AdviceEvidence, { evidence_type: 'patient' }>
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const patientLabels: Partial<Record<PatientAdviceEvidence['source_type'], string>> = {
  confirmed_medical_fact: '已确认档案事实', diet_record: '饮食记录', stool_record: '排便记录',
  symptom_record: '症状记录', mood_record: '心情记录', medication_plan: '用药计划',
  medication_checkin: '用药打卡', risk_alert: '风险提示',
}

/** Only a fixed type:id locator paired with a supported, live target can be shown or opened. */
export function adviceEvidenceLabel(evidence: AdviceEvidence): string | null {
  if (evidence.evidence_type !== 'patient' || evidence.source_deleted) return null
  const label = patientLabels[evidence.source_type]
  const locator = typeof evidence.locator === 'string'
    ? /^([a-z_]+):([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/i.exec(evidence.locator)
    : null
  if (!label || !uuidPattern.test(evidence.source_id) || !locator || locator[1]?.toLowerCase() !== evidence.source_type || locator[2]?.toLowerCase() !== evidence.source_id.toLowerCase()) return null
  if (!evidence.target || evidence.target.type !== evidence.source_type || evidence.target.id.toLowerCase() !== evidence.source_id.toLowerCase()) return null
  return `${label} · 已验证来源`
}

/** Returns a domain-only label; citation URLs are never rendered or opened by the app. */
export function knowledgeCitationHost(evidence: AdviceEvidence): string | null {
  if (evidence.evidence_type !== 'knowledge' || !evidence.citation_url) return null
  try {
    const url = new URL(evidence.citation_url)
    if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) return null
    return url.hostname
  } catch {
    return null
  }
}

export function riskPriorityLabel(context: RiskPriorityContext): string {
  return context.severity === 'emergency' ? '紧急风险提示优先查看' : '尽快就医提示优先查看'
}

export function riskPriorityStatusLabel(context: RiskPriorityContext): string {
  return context.status === 'unread' ? '未查看' : context.status === 'read' ? '已查看' : '已重新评估（不代表风险解除或安全）'
}

export function adviceStatusLabel(status: Advice['status']): string {
  return status === 'new' ? '未读' : status === 'read' ? '已读' : '已归档'
}

export function adviceEvidenceCanNavigate(evidence: AdviceEvidence): evidence is PatientAdviceEvidence {
  return adviceEvidenceLabel(evidence) !== null
}
